"""Coupling templates, registry, and executable classification (Task 2.3).

Stage 3 refines the Stage 1+2 capability verdict into an *executable* verdict
by binding a composed component shape to a declared ``CouplingTemplate``::

    capability filter -> template lookup -> coupling contracts
        -> schedule -> clock -> EXECUTABLE

A ``CouplingTemplate`` is authored next to an experiment's coupling logic.  It
declares the exact binding set, the identity/defaults of the world the
generator would produce, the experiment's coupling contracts and macro-step
order, the per-component configs, and the clock parameters.  ``generate_world``
turns a template into a fully declarative ``WorldDefinition`` (Stage 4): the
same composition the experiment facade builds, with the template's pointer to
the concrete binding.

The ``CouplingTemplateRegistry`` is an explicit map from shape identity to
template.  There is no dynamic discovery and no coupling is ever *invented*:
capability compatibility alone never creates an edge, and a shape with no
declared template is classified ``COUPLING_UNAVAILABLE`` (never executable).

Classification is an ordered, deterministic gate that reuses the existing
generic machinery (static surfaces, ``resolve_contracts``) plus two
adapter-only static checks (schedule registration, clock divisibility).  Only
shapes with a declared template cause adapters to be *constructed*, and then
purely to read their constructor metadata -- nothing is initialized or stepped.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.capabilities import SimulationEngine
from sim_alchemist.core.composition import (
    CAPABILITY_INVALID,
    CapabilitySurface,
    ComponentBinding,
    CompositionShape,
    classify_shape,
)
from sim_alchemist.core.contracts import (
    ContractIssue,
    CouplingContract,
    UnresolvedContractError,
    contracts_key,
    resolve_contracts,
)
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

COUPLING_UNAVAILABLE = "COUPLING_UNAVAILABLE"
COUPLING_INVALID = "COUPLING_INVALID"
SCHEDULE_INVALID = "SCHEDULE_INVALID"
CLOCK_INVALID = "CLOCK_INVALID"
EXECUTABLE = "EXECUTABLE"

_MACRO_DT_TOLERANCE = 1e-12


@dataclass(frozen=True)
class CouplingTemplate:
    """The declared description of one composite world (authoring surface).

    ``bindings`` names the elementary component identities of the composition
    (canonically sorted on construction).  ``world_id`` and the clock/seed
    fields are exactly what ``generate_world`` stamps into the produced
    ``WorldDefinition``; ``component_configs`` supplies each component's
    constructor config keyed by component id (unique per shape thanks to
    variant exclusivity).

    ``contracts`` and ``schedule``/``operations`` are the experiment's declared
    coupling edges and macro-step order.  ``executor_ref`` is an opaque,
    experiment-owned identifier of the executor that would run the generated
    world; the core never resolves it.
    """

    name: str
    bindings: tuple[ComponentBinding, ...]
    world_id: str
    contracts: tuple[Any, ...]
    schedule: tuple[str, ...]
    operations: tuple[str, ...]
    requires: tuple[str, ...] = ()
    executor_ref: str | None = None
    component_configs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    macro_timestep: float = 0.2
    max_steps: int = 160
    seed: int = 0
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("template name must be a non-empty string")
        if not self.bindings:
            raise ValueError("a template requires at least one binding")
        shape = CompositionShape(self.bindings)
        object.__setattr__(self, "bindings", shape.bindings)
        if not isinstance(self.world_id, str) or not self.world_id.strip():
            raise ValueError("template world_id must be a non-empty string")
        if not self.contracts:
            raise ValueError("a template requires at least one declared contract")
        if not self.schedule:
            raise ValueError("a template requires a non-empty macro-step schedule")
        if not self.operations:
            raise ValueError("a template requires the registered operation names")
        if not isinstance(self.macro_timestep, (int, float)):
            raise TypeError("macro_timestep must be a number")
        if not isinstance(self.max_steps, int):
            raise TypeError("max_steps must be an integer")

    @property
    def shape(self) -> CompositionShape:
        return CompositionShape(self.bindings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bindings": [b.as_dict() for b in self.bindings],
            "world_id": self.world_id,
            "contracts": [c.as_dict() for c in self.contracts],
            "schedule": list(self.schedule),
            "operations": list(self.operations),
            "requires": list(self.requires),
            "executor_ref": self.executor_ref,
            "component_configs": {
                component: dict(config)
                for component, config in self.component_configs.items()
            },
            "macro_timestep": self.macro_timestep,
            "max_steps": self.max_steps,
            "seed": self.seed,
            "config": dict(self.config),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CouplingTemplate:
        return cls(
            name=str(data["name"]),
            bindings=tuple(
                ComponentBinding.from_dict(b) for b in data["bindings"]
            ),
            world_id=str(data["world_id"]),
            contracts=tuple(
                _contract_from_dict(c) for c in data["contracts"]
            ),
            schedule=tuple(str(op) for op in data["schedule"]),
            operations=tuple(str(op) for op in data["operations"]),
            requires=tuple(str(r) for r in data.get("requires", [])),
            executor_ref=data.get("executor_ref"),
            component_configs={
                str(k): dict(v)
                for k, v in dict(data.get("component_configs", {})).items()
            },
            macro_timestep=float(data.get("macro_timestep", 0.2)),
            max_steps=int(data.get("max_steps", 160)),
            seed=int(data.get("seed", 0)),
            config=dict(data.get("config", {})),
        )


@dataclass(frozen=True)
class CompositionVerdict:
    """The finite result of classifying one shape against the taxonomy."""

    shape: CompositionShape
    status: str
    missing_capabilities: tuple[str, ...] = ()
    template: str | None = None
    reasons: tuple[str, ...] = ()
    composition_id: str | None = None

    @property
    def executable(self) -> bool:
        return self.status == EXECUTABLE

    def explain(self) -> str:
        lines = [f"composition {self.shape.shape_id} -> {self.status}"]
        if self.missing_capabilities:
            lines.append("missing capability(ies): " + ", ".join(self.missing_capabilities))
        if self.template:
            lines.append(f"matched template: {self.template}")
        if self.composition_id:
            lines.append(f"composition id: {self.composition_id}")
        for reason in self.reasons:
            lines.append(f"  {reason}")
        return "\n".join(lines)


class DuplicateTemplateError(ValueError):
    """Raised when a template is registered twice (same name or same shape)."""


class CouplingTemplateRegistry:
    """Explicit, deterministic catalog of coupling templates.

    Registration is the only way templates enter the catalog; detection is by
    name and by canonical shape identity, so two templates for the same
    component set are rejected up front.
    """

    def __init__(self, templates: Sequence[CouplingTemplate] = ()) -> None:
        self._by_name: dict[str, CouplingTemplate] = {}
        self._by_shape: dict[str, CouplingTemplate] = {}
        for template in templates:
            self.register(template)

    def register(self, template: CouplingTemplate) -> CouplingTemplate:
        if not isinstance(template, CouplingTemplate):
            raise TypeError("only CouplingTemplate instances may be registered")
        if template.name in self._by_name:
            raise DuplicateTemplateError(
                f"template name {template.name!r} is already registered"
            )
        shape_id = template.shape.shape_id
        if shape_id in self._by_shape:
            raise DuplicateTemplateError(
                f"template {template.name!r} duplicates the component set of "
                f"{self._by_shape[shape_id].name!r}"
            )
        self._by_name[template.name] = template
        self._by_shape[shape_id] = template
        return template

    def lookup(self, shape: CompositionShape) -> CouplingTemplate | None:
        return self._by_shape.get(shape.shape_id)

    def by_name(self, name: str) -> CouplingTemplate | None:
        return self._by_name.get(name)

    def templates(self) -> tuple[CouplingTemplate, ...]:
        return tuple(self._by_name[name] for name in sorted(self._by_name))

    def __iter__(self):
        return iter(self.templates())

    def __len__(self) -> int:
        return len(self._by_name)

    @classmethod
    def from_sequence(cls, templates: Sequence[CouplingTemplate]) -> CouplingTemplateRegistry:
        return cls(templates)


def classify_composition(
    shape: CompositionShape,
    surfaces: Mapping[ComponentBinding, CapabilitySurface],
    templates: Sequence[CouplingTemplate] | CouplingTemplateRegistry,
    *,
    build_adapters: Callable[[CompositionShape, CouplingTemplate], Sequence[SimulationEngine]],
) -> CompositionVerdict:
    """Classify one shape against the full executable-taxonomy pipeline.

    The funnel is strictly ordered and deterministic:

    1. capability filter (with the template's world-level ``requires`` folded in
       when a template matches);
    2. template lookup -- no template, ``COUPLING_UNAVAILABLE``;
    3. coupling contracts -- a declared edge that does not resolve, ``COUPLING_INVALID``;
    4. schedule -- an operation the template does not register, ``SCHEDULE_INVALID``;
    5. clock -- a component whose native timestep does not divide the macro
       timestep, ``CLOCK_INVALID``.

    Only shapes with a declared template cause adapter construction (via
    ``build_adapters``), and adapters are only ever *constructed* here, never
    initialized or stepped.  ``EXECUTABLE`` therefore means the composition is
    statically known to compose; it says nothing about running it.
    """
    registry = templates if isinstance(templates, CouplingTemplateRegistry) else CouplingTemplateRegistry.from_sequence(templates)
    template = registry.lookup(shape)
    required = tuple(template.requires) if template is not None else ()
    classification = classify_shape(shape, surfaces, required)

    if classification.status == CAPABILITY_INVALID:
        reason = (
            "capability filter rejects the composition; "
            "missing capability(ies): "
            + ", ".join(classification.missing_capabilities)
        )
        return CompositionVerdict(
            shape=shape,
            status=CAPABILITY_INVALID,
            missing_capabilities=classification.missing_capabilities,
            template=template.name if template is not None else None,
            reasons=(reason,),
        )

    if template is None:
        reason = f"no declared CouplingTemplate binds this component set: {_shape_label(shape)}"
        return CompositionVerdict(
            shape=shape,
            status=COUPLING_UNAVAILABLE,
            reasons=(reason,),
        )

    adapters = tuple(build_adapters(shape, template))

    try:
        resolve_contracts(adapters, template.contracts)
    except UnresolvedContractError as error:
        reasons = tuple(_contract_reason(issue) for issue in error.issues)
        return _bound_verdict(shape, template, COUPLING_INVALID, reasons)

    registered = set(template.operations)
    unknown = tuple(sorted(name for name in template.schedule if name not in registered))
    if unknown:
        reason = (
            "schedule names operation(s) the template does not register: "
            + ", ".join(unknown)
        )
        return _bound_verdict(shape, template, SCHEDULE_INVALID, (reason,))

    non_divisible = [
        (adapter.engine_id, adapter.native_timestep)
        for adapter in adapters
        if _does_not_divide(template.macro_timestep, adapter.native_timestep)
    ]
    if non_divisible:
        reasons = tuple(
            f"component '{engine_id}' native timestep {dt} "
            f"does not divide macro timestep {template.macro_timestep}"
            for engine_id, dt in sorted(non_divisible, key=lambda item: item[0])
        )
        return _bound_verdict(shape, template, CLOCK_INVALID, reasons)

    return CompositionVerdict(
        shape=shape,
        status=EXECUTABLE,
        template=template.name,
        composition_id=composition_id(
            shape,
            contracts=template.contracts,
            schedule=template.schedule,
            requires=template.requires,
            macro_timestep=template.macro_timestep,
        ),
    )


def generate_world(template: CouplingTemplate) -> WorldDefinition:
    """Generate the declarative ``WorldDefinition`` a template describes.

    Each component spec is stamped with the template's concrete binding
    variant (``None`` when the component id is unambiguous), producing exactly
    the composition the experiment facade builds -- with its variant identity
    made explicit.  Generation never constructs or consults an adapter.
    """
    components = tuple(
        ComponentSpec(
            binding.component,
            dict(template.component_configs.get(binding.component, {})),
            variant=binding.variant,
        )
        for binding in template.shape
    )
    return WorldDefinition(
        id=template.world_id,
        components=components,
        requires=tuple(template.requires),
        schedule=tuple(template.schedule),
        macro_timestep=template.macro_timestep,
        max_steps=template.max_steps,
        seed=template.seed,
        config=dict(template.config),
    )


def composition_id(
    shape: CompositionShape,
    *,
    contracts: Sequence[Any],
    schedule: Sequence[str],
    requires: Sequence[str],
    macro_timestep: float = 0.2,
) -> str:
    """Deterministic, content-addressed identity of a composition.

    The identity covers the shape plus the declared contracts, macro-step
    order, world-level requirements, and clock macro timestep -- the things
    that determine how a composed world behaves.  Structurally identical
    templates map to the same id; any of these differing yields a different id.
    """
    payload = json.dumps(
        {
            "shape": shape.shape_id,
            "contracts": contracts_key(contracts),
            "schedule": list(schedule),
            "requires": sorted(set(requires)),
            "macro_timestep": macro_timestep,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def template_composition_id(template: CouplingTemplate) -> str:
    return composition_id(
        template.shape,
        contracts=template.contracts,
        schedule=template.schedule,
        requires=template.requires,
        macro_timestep=template.macro_timestep,
    )


def _bound_verdict(
    shape: CompositionShape,
    template: CouplingTemplate,
    status: str,
    reasons: tuple[str, ...],
) -> CompositionVerdict:
    return CompositionVerdict(
        shape=shape,
        status=status,
        template=template.name,
        reasons=reasons,
        composition_id=composition_id(
            shape,
            contracts=template.contracts,
            schedule=template.schedule,
            requires=template.requires,
            macro_timestep=template.macro_timestep,
        ),
    )


def _contract_reason(issue: ContractIssue) -> str:
    variant = f", variant '{issue.variant}'" if issue.variant else ""
    return (
        f"contract '{issue.contract}' "
        f"({issue.producer} -> {issue.consumer}{variant}): "
        f"{issue.what}. {issue.fix}"
    )


def _binding_label(binding: ComponentBinding) -> str:
    if binding.variant:
        return f"{binding.component}/{binding.variant}"
    return binding.component


def _shape_label(shape: CompositionShape) -> str:
    return " + ".join(_binding_label(binding) for binding in shape)


def _does_not_divide(macro_timestep: float, native_dt: float) -> bool:
    if native_dt is None or native_dt <= 0:
        return True
    return macro_timestep % native_dt > _MACRO_DT_TOLERANCE


def _contract_from_dict(data: Mapping[str, Any]) -> CouplingContract:
    return CouplingContract.from_dict(data)


__all__ = [
    "CLOCK_INVALID",
    "COUPLING_INVALID",
    "COUPLING_UNAVAILABLE",
    "EXECUTABLE",
    "SCHEDULE_INVALID",
    "CompositionVerdict",
    "CouplingTemplate",
    "CouplingTemplateRegistry",
    "DuplicateTemplateError",
    "classify_composition",
    "composition_id",
    "generate_world",
    "template_composition_id",
]