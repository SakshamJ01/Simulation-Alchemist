"""Coupling template registry + executable taxonomy tests (Task 2.3 Stage 3).

Covers the CouplingTemplate authored surface, the explicit registry, and the
ordered classification funnel that turns a capability-valid shape into an
EXECUTABLE composition (A: morphogenesis, B: field-guided movers, C: adaptive
network morphogenesis) or a precisely-typed non-executable verdict.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from chemomech.coupling import (
    MORPHOGENESIS_SCHEDULE,
    MorphogenesisState,
    build_morphogenesis_operations,
    build_morphogenesis_template,
)
from chemomech.simulation import Trajectory, WorldConfig
from experiments.catalog import (
    build_repository_adapters,
    repository_surfaces,
    repository_templates,
)
from experiments.field_guided_movers.coupling import (
    FIELD_GUIDED_MOVERS_CONTRACTS,
    FIELD_GUIDED_MOVERS_SCHEDULE,
    build_field_guided_movers_operations,
    build_field_guided_movers_registry,
    build_field_guided_movers_template,
)
from experiments.field_guided_movers.model import (
    MoversAdapter,
    MoversConfig,
    MoversState,
    MoversTrajectory,
)
from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    NETWORK_MORPHOGENESIS_SCHEDULE,
    NetworkMorphogenesisState,
    build_network_morphogenesis_operations,
    build_network_morphogenesis_registry,
    build_network_morphogenesis_template,
)
from experiments.network_morphogenesis.model import (
    NetworkMorphogenesisConfig,
    NetworkMorphogenesisTrajectory,
)
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core import (
    CAPABILITY_INVALID,
    CLOCK_INVALID,
    COUPLING_INVALID,
    COUPLING_UNAVAILABLE,
    EXECUTABLE,
    SCHEDULE_INVALID,
    ComponentBinding,
    CompositionShape,
    CouplingContract,
    CouplingTemplate,
    CouplingTemplateRegistry,
    DuplicateTemplateError,
    classify_composition,
    composition_id,
    generate_world,
    template_composition_id,
)
from sim_alchemist.core.composer import build_components
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.registry import default_registry

MESA = ComponentBinding("mesa")
PDE = ComponentBinding("py-pde")
WALLS = ComponentBinding("pymunk", "walls")
MOVERS = ComponentBinding("pymunk", "movers")
NETWORK = ComponentBinding("network")

SHAPE_A = CompositionShape((MESA, PDE, WALLS))
SHAPE_B = CompositionShape((PDE, MOVERS))
SHAPE_C = CompositionShape((NETWORK, PDE, WALLS))


def _field_sensing_contract() -> CouplingContract:
    return CouplingContract(
        name="field-sensing",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("u", "array_1d"), ("v", "array_1d")),
        transform="field-sensing",
        coordinate_system="unit-square-2d",
    )


def _synthetic(
    name: str,
    bindings: tuple[ComponentBinding, ...],
    *,
    contracts: tuple[CouplingContract, ...] | None = None,
    schedule: tuple[str, ...] = ("observables.record",),
    operations: tuple[str, ...] = ("observables.record",),
    macro_timestep: float = 0.2,
    requires: tuple[str, ...] = (),
) -> CouplingTemplate:
    return CouplingTemplate(
        name=name,
        bindings=bindings,
        world_id=f"world-{name}",
        contracts=(_field_sensing_contract(),) if contracts is None else contracts,
        schedule=schedule,
        operations=operations,
        requires=requires,
        macro_timestep=macro_timestep,
    )


def _classify(shape: CompositionShape, templates: Any):
    registry = (
        templates
        if isinstance(templates, CouplingTemplateRegistry)
        else CouplingTemplateRegistry.from_sequence(templates)
    )
    return classify_composition(
        shape,
        repository_surfaces(),
        registry,
        build_adapters=build_repository_adapters,
    )


# ----------------------------------------------------------------------
# Well-formedness + registry (the authored surface)
# ----------------------------------------------------------------------
class TestTemplateWellFormed:
    def test_minimal_valid_template(self) -> None:
        t = _synthetic("ok", (MESA, PDE))
        assert t.name == "ok"
        assert t.bindings == (MESA, PDE)
        assert len(t.as_dict()["bindings"]) == 2

    @pytest.mark.parametrize(
        "malformed",
        [
            {"name": " "},
            {"bindings": ()},
            {"world_id": ""},
            {"contracts": ()},
            {"schedule": ()},
            {"operations": ()},
        ],
        ids=["blank-name", "no-bindings", "blank-world-id", "no-contracts", "no-schedule", "no-operations"],
    )
    def test_rejects_malformed_template(self, malformed: dict[str, Any]) -> None:
        fields: dict[str, Any] = {
            "name": "t",
            "bindings": (MESA, PDE),
            "world_id": "w",
            "contracts": (_field_sensing_contract(),),
            "schedule": ("observables.record",),
            "operations": ("observables.record",),
        }
        fields.update(malformed)
        with pytest.raises(ValueError):
            CouplingTemplate(**fields)

    def test_template_is_frozen(self) -> None:
        t = _synthetic("frozen", (MESA, PDE))
        with pytest.raises(FrozenInstanceError):
            setattr(t, "bindings", ())  # noqa: B010  (dynamic guard: frozen dataclass)


class TestTemplateRegistry:
    def test_empty_registry_surfaces_nothing(self) -> None:
        registry = CouplingTemplateRegistry()
        assert len(registry) == 0
        assert registry.templates() == ()

    def test_duplicate_by_name_rejected(self) -> None:
        registry = CouplingTemplateRegistry()
        registry.register(build_field_guided_movers_template())
        with pytest.raises(DuplicateTemplateError, match="already registered"):
            registry.register(
                _synthetic("field_guided_movers", (MESA, PDE))
            )

    def test_duplicate_by_shape_rejected(self) -> None:
        registry = CouplingTemplateRegistry()
        registry.register(build_field_guided_movers_template())
        with pytest.raises(DuplicateTemplateError, match="duplicates the component set"):
            registry.register(_synthetic("other-name", (PDE, MOVERS)))

    def test_lookup_by_canonical_identity(self) -> None:
        registry = CouplingTemplateRegistry()
        template = build_field_guided_movers_template()
        registry.register(template)
        assert registry.lookup(CompositionShape((MOVERS, PDE))) is template
        assert registry.lookup(CompositionShape((PDE, WALLS))) is None
        assert registry.by_name("field_guided_movers") is template
        assert registry.by_name("missing") is None

    def test_canonicalizes_binding_order_on_construction(self) -> None:
        t = _synthetic("canon", (WALLS, MESA, PDE))
        assert t.bindings == (MESA, PDE, WALLS)

    def test_template_sequence_is_sorted_deterministically(self) -> None:
        names = [t.name for t in repository_templates().templates()]
        assert names == ["adaptive_network", "field_guided_movers", "morphogenesis"]
        assert len({t.shape.shape_id for t in repository_templates().templates()}) == 3

    def test_deterministic_canonical_serialization(self) -> None:
        for build in (
            build_morphogenesis_template,
            build_field_guided_movers_template,
            build_network_morphogenesis_template,
        ):
            original = build()
            restored = CouplingTemplate.from_dict(original.as_dict())
            assert restored == original
            assert restored.bindings == original.bindings
            assert restored.shape.shape_id == original.shape.shape_id
            assert template_composition_id(restored) == template_composition_id(original)


# ----------------------------------------------------------------------
# The classification funnel
# ----------------------------------------------------------------------
class TestClassification:
    def test_repository_templates_classify_a_b_c_as_executable(self) -> None:
        verdict = _classify(SHAPE_A, repository_templates())
        assert verdict.status == EXECUTABLE
        assert verdict.template == "morphogenesis"
        assert verdict.executable
        assert verdict.composition_id is not None
        assert len(verdict.composition_id) == 24

    def test_executable_verdicts_are_composition_identical(self) -> None:
        templates = repository_templates()
        ids = {
            _classify(shape, templates).composition_id
            for shape in (SHAPE_A, SHAPE_B, SHAPE_C)
        }
        assert len(ids) == 3

    def test_executable_composition_id_matches_template_id(self) -> None:
        templates = repository_templates()
        for shape, build in (
            (SHAPE_A, build_morphogenesis_template),
            (SHAPE_B, build_field_guided_movers_template),
            (SHAPE_C, build_network_morphogenesis_template),
        ):
            verdict = _classify(shape, templates)
            assert verdict.composition_id == template_composition_id(build())

    def test_capability_gap_never_matches_a_template(self) -> None:
        verdict = _classify(CompositionShape((MESA, NETWORK)), repository_templates())
        assert verdict.status == CAPABILITY_INVALID
        assert verdict.template is None
        assert verdict.missing_capabilities
        assert verdict.composition_id is None
        assert "capability" in verdict.reasons[0]

    def test_pymunk_variant_sorts_walls_from_movers(self) -> None:
        templates = repository_templates()
        assert _classify(CompositionShape((PDE, MOVERS)), templates).status == EXECUTABLE
        assert _classify(CompositionShape((PDE, WALLS)), templates).status == CAPABILITY_INVALID


class TestTaxonomy:
    @pytest.mark.parametrize(
        "shape",
        [
            CompositionShape((MESA, PDE, MOVERS)),
            CompositionShape((NETWORK, PDE, MOVERS)),
            CompositionShape((MESA, NETWORK, PDE, MOVERS)),
            CompositionShape((MESA, NETWORK, PDE, WALLS)),
        ],
        ids=["a-with-movers", "c-with-movers", "ac-with-movers", "ac-with-walls"],
    )
    def test_known_unwired_shapes_never_executable(self, shape) -> None:
        verdict = _classify(shape, repository_templates())
        assert verdict.status == COUPLING_UNAVAILABLE
        assert verdict.reasons
        assert "no declared CouplingTemplate" in verdict.reasons[0]
        assert not verdict.executable

    def test_coupling_invalid_when_declared_consumer_absent(self) -> None:
        template = _synthetic(
            "broken-edge",
            (PDE, MOVERS),
            contracts=(_field_sensing_contract(),),  # consumer 'mesa' not composed
            schedule=("movers.step", "nope.missing"),
            operations=("movers.step",),
        )
        verdict = _classify(CompositionShape((PDE, MOVERS)), [template])
        assert verdict.status == COUPLING_INVALID
        assert verdict.template == "broken-edge"
        assert any("contract 'field-sensing'" in r for r in verdict.reasons)

    def test_schedule_invalid_for_unregistered_operation(self) -> None:
        template = _synthetic(
            "bad-schedule",
            (PDE, MOVERS),
            contracts=FIELD_GUIDED_MOVERS_CONTRACTS,
            schedule=("movers.step", "no-such-op"),
        )
        verdict = _classify(CompositionShape((PDE, MOVERS)), [template])
        assert verdict.status == SCHEDULE_INVALID
        assert verdict.template == "bad-schedule"
        assert verdict.composition_id is not None  # bound (identity still known)
        assert "no-such-op" in verdict.reasons[0]

    def test_clock_invalid_when_native_dt_does_not_divide_macro(self) -> None:
        template = _synthetic(
            "slow-clock",
            (PDE, MOVERS),
            contracts=FIELD_GUIDED_MOVERS_CONTRACTS,
            schedule=("movers.step",),
            operations=("movers.step",),
            macro_timestep=0.21,
        )
        verdict = _classify(CompositionShape((PDE, MOVERS)), [template])
        assert verdict.status == CLOCK_INVALID
        assert verdict.composition_id is not None
        assert "native timestep" in verdict.reasons[0]

    def test_capability_invalid_precedes_template_lookup(self) -> None:
        template = _synthetic(
            "cap-gap",
            (MESA, PDE),
            schedule=("movers.step",),
            operations=("movers.step",),
        )
        verdict = _classify(CompositionShape((MESA, PDE)), [template])
        assert verdict.status == CAPABILITY_INVALID
        assert verdict.template == "cap-gap"  # matched but filtered on capability

    def test_coupling_invalid_precedes_schedule_validation(self) -> None:
        template = _synthetic(
            "both-bad",
            (PDE, MOVERS),
            contracts=(_field_sensing_contract(),),  # consumer 'mesa' absent
            schedule=("movers.step", "nope.missing"),
            operations=("movers.step",),
        )
        verdict = _classify(CompositionShape((PDE, MOVERS)), [template])
        assert verdict.status == COUPLING_INVALID  # contracts checked first

    def test_verdict_explain_is_useful(self) -> None:
        verdict = _classify(SHAPE_A, repository_templates())
        text = verdict.explain()
        assert verdict.status in text
        assert "composition id" in text
        assert verdict.shape.shape_id in text

    def test_registry_equivalence_with_sequence(self) -> None:
        template = build_field_guided_movers_template()
        as_seq = _classify(SHAPE_B, [template])
        as_reg = _classify(SHAPE_B, CouplingTemplateRegistry([template]))
        assert as_seq == as_reg


# ----------------------------------------------------------------------
# composition_id: deterministic, content-addressed identity
# ----------------------------------------------------------------------
class TestCompositionId:
    def test_deterministic(self) -> None:
        template = build_field_guided_movers_template()
        assert template_composition_id(template) == template_composition_id(
            CouplingTemplate.from_dict(template.as_dict())
        )

    def test_distinguishing(self) -> None:
        template = build_field_guided_movers_template()
        base = template_composition_id(template)
        assert base != composition_id(
            template.shape,
            contracts=template.contracts,
            schedule=template.schedule[1:],  # drop observables.record
            requires=template.requires,
            macro_timestep=template.macro_timestep,
        )
        assert base != composition_id(
            template.shape,
            contracts=template.contracts,
            schedule=template.schedule,
            requires=template.requires + ("extra",),
            macro_timestep=template.macro_timestep,
        )
        assert base != composition_id(
            template.shape,
            contracts=template.contracts,
            schedule=template.schedule,
            requires=template.requires,
            macro_timestep=template.macro_timestep + 0.1,
        )
        assert base != composition_id(
            CompositionShape((PDE,)),
            contracts=template.contracts,
            schedule=template.schedule,
            requires=template.requires,
            macro_timestep=template.macro_timestep,
        )

    def test_hex_identity_format(self) -> None:
        cid = template_composition_id(build_morphogenesis_template())
        assert len(cid) == 24
        assert all(c in "0123456789abcdef" for c in cid)


# ----------------------------------------------------------------------
# Drift guard: template.operations == the operations the coupling builders
# actually register (built with constructor-only real adapters).
# ----------------------------------------------------------------------
class TestTemplateOperationsMatchBuilders:
    def test_morphogenesis_operations(self) -> None:
        template = build_morphogenesis_template()
        world = generate_world(template)
        adapters = build_components(default_registry(), world)
        cfg = WorldConfig(**dict(world.config))
        traj = Trajectory(config=cfg)
        ops = build_morphogenesis_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(PymunkAdapter, adapter_by_id(adapters, "pymunk")),
            cast(MesaAdapter, adapter_by_id(adapters, "mesa")),
            cfg,
            traj,
            MorphogenesisState(),
        )
        assert set(ops) == set(template.operations)
        assert set(ops) == set(MORPHOGENESIS_SCHEDULE)

    def test_field_guided_movers_operations(self) -> None:
        template = build_field_guided_movers_template()
        world = generate_world(template)
        adapters = build_components(build_field_guided_movers_registry(), world)
        cfg = MoversConfig(**dict(world.config))
        ops = build_field_guided_movers_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(MoversAdapter, adapter_by_id(adapters, "pymunk")),
            cfg,
            MoversTrajectory(config=cfg),
            MoversState(),
        )
        assert set(ops) == set(template.operations)
        assert set(ops) == set(FIELD_GUIDED_MOVERS_SCHEDULE)

    def test_network_morphogenesis_operations(self) -> None:
        template = build_network_morphogenesis_template()
        world = generate_world(template)
        adapters = build_components(build_network_morphogenesis_registry(), world)
        cfg = NetworkMorphogenesisConfig.from_world(world)
        ops = build_network_morphogenesis_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(PymunkAdapter, adapter_by_id(adapters, "pymunk")),
            cast(AdaptiveNetworkAdapter, adapter_by_id(adapters, "network")),
            dict(world.config),
            NetworkMorphogenesisTrajectory(config=cfg),
            NetworkMorphogenesisState(),
        )
        assert set(ops) == set(template.operations)
        assert set(ops) == set(NETWORK_MORPHOGENESIS_SCHEDULE)