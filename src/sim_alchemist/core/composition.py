"""Composition shapes, spaces, and static capability filtering (Task 2.3).

Stage 1+2 of the composition design: a component set is expressed as an
*unordered, variant-distinct* set of ``ComponentBinding`` identities, becomes an
immutable, content-addressed ``CompositionShape``, and is enumerated in a
bounded, deterministic way by ``CompositionSpace``.  A static capability
filter then classifies a shape as ``CAPABILITY_VALID`` or
``CAPABILITY_INVALID`` using adapter *capability surfaces* read from the
registry's factories without ever initializing or stepping an engine.

     ComponentBinding          one (component, variant) identity
     CompositionShape          a canonically-sorted binding set
     CompositionSpace          a bounded, deterministic enumeration
     CapabilitySurface         a binding's static provides/requires
     CompositionClassification the capability filter verdict

Variant identity is part of the binding: two variants of one component id
are distinct bindings, distinct shapes, and distinct identities.  Nothing
in this module knows about any concrete experiment, engine, or operation
name; capability metadata comes only from the in-process registry.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.capabilities import SimulationEngine
from sim_alchemist.core.registry import ComponentRegistry

CAPABILITY_VALID = "CAPABILITY_VALID"
CAPABILITY_INVALID = "CAPABILITY_INVALID"


def _normalize_variant(variant: str | None) -> str | None:
    if variant is None:
        return None
    if not isinstance(variant, str):
        raise TypeError(f"variant must be a str or None, got {type(variant).__name__}")
    if not variant.strip():
        return None
    return variant


def _canonical_key(binding: ComponentBinding) -> tuple[str, str]:
    return (binding.component, binding.variant or "")


def _variant_exclusive(bindings: Sequence[ComponentBinding]) -> bool:
    return len({b.component for b in bindings}) == len(bindings)


@dataclass(frozen=True)
class ComponentBinding:
    """One elementary component identity: a component id plus a variant."""

    component: str
    variant: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.component, str) or not self.component.strip():
            raise ValueError("component must be a non-empty string")
        object.__setattr__(self, "variant", _normalize_variant(self.variant))

    def as_dict(self) -> dict[str, Any]:
        return {"component": self.component, "variant": self.variant}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ComponentBinding:
        return cls(component=data["component"], variant=data.get("variant"))


@dataclass(frozen=True)
class CompositionShape:
    """An unordered, variant-distinct set of component bindings.

    The shape normalizes its bindings to a canonical, sorted order (component,
    then variant, empty variant last within a component) so that two shapes
    built from the same bindings in a different order are equal and share the
    same content-addressed ``shape_id``.  A component id may appear at most
    once; two variants of the same component in one shape are rejected.
    """

    bindings: tuple[ComponentBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        if not self.bindings:
            raise ValueError("a composition shape requires at least one binding")
        ordered = tuple(sorted(self.bindings, key=_canonical_key))
        seen: dict[str, ComponentBinding] = {}
        for binding in ordered:
            prior = seen.get(binding.component)
            if prior is not None:
                if prior == binding:
                    raise ValueError(f"duplicate binding {binding.as_dict()!r} in composition")
                raise ValueError(
                    "variant exclusivity violation: two bindings share component "
                    f"'{binding.component}' ({prior.variant!r} and {binding.variant!r})"
                )
            seen[binding.component] = binding
        object.__setattr__(self, "bindings", ordered)

    def __len__(self) -> int:
        return len(self.bindings)

    def __iter__(self) -> Iterator[ComponentBinding]:
        return iter(self.bindings)

    def components(self) -> tuple[str, ...]:
        return tuple(b.component for b in self.bindings)

    @property
    def shape_id(self) -> str:
        canonical = json.dumps(
            [b.as_dict() for b in self.bindings],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    def as_dict(self) -> dict[str, Any]:
        return {"bindings": [b.as_dict() for b in self.bindings]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompositionShape:
        return cls(tuple(ComponentBinding.from_dict(item) for item in data["bindings"]))


@dataclass(frozen=True)
class CompositionSpace:
    """A named universe of bindings with bounded, deterministic enumeration.

    ``universe`` is the full set of registered bindings (it may legitimately
    contain two variants of the same component id).  Enumeration is
    size-first -- ``k`` from ``max(min_size, 1)`` to
    ``max_size`` -- then canonical universe order with the right-most element
    of each combination changing fastest (``itertools.combinations``).  Shapes
    that would repeat a component id are skipped (variant exclusivity); an
    empty shape is never enumerated even when ``min_size`` is 0.
    """

    name: str
    universe: tuple[ComponentBinding, ...]
    min_size: int = 2
    max_size: int = 4

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.universe, tuple):
            object.__setattr__(self, "universe", tuple(self.universe))
        if not self.universe:
            raise ValueError("universe must not be empty")
        ordered = tuple(sorted(self.universe, key=_canonical_key))
        for previous, binding in itertools.pairwise(ordered):
            if previous == binding:
                raise ValueError(f"duplicate binding {binding.as_dict()!r} in universe")
        object.__setattr__(self, "universe", ordered)
        if not isinstance(self.min_size, int) or self.min_size < 0:
            raise ValueError("min_size must be a non-negative integer")
        if not isinstance(self.max_size, int):
            raise TypeError("max_size must be an integer")
        if not (self.min_size <= self.max_size <= len(self.universe)):
            raise ValueError(
                "invalid bounds: need 0 <= min_size <= max_size <= len(universe), "
                f"got min_size={self.min_size}, max_size={self.max_size}, "
                f"universe={len(self.universe)}"
            )

    def enumerate_shapes(self) -> tuple[CompositionShape, ...]:
        shapes: list[CompositionShape] = []
        for k in range(max(self.min_size, 1), self.max_size + 1):
            for combo in itertools.combinations(self.universe, k):
                if _variant_exclusive(combo):
                    shapes.append(CompositionShape(combo))
        return tuple(shapes)


@dataclass(frozen=True)
class CapabilitySurface:
    """Static capability metadata of one binding (no engine constructed)."""

    provides: frozenset[str]
    requires: frozenset[str]


@dataclass(frozen=True)
class CompositionClassification:
    """Verdict of the static capability filter for one shape."""

    shape: CompositionShape
    status: str
    missing_capabilities: tuple[str, ...] = ()


def capability_surfaces_from_registry(
    registry: ComponentRegistry,
) -> dict[ComponentBinding, CapabilitySurface]:
    """Read static capability surfaces from a registry's factories.

    Each adapter is *constructed* once with an empty config (constructor-only;
    never initialized, never stepped) to read its declared provides/requires
    and its concrete variant.  The result maps each distinct binding to its
    surface.
    """
    surfaces: dict[ComponentBinding, CapabilitySurface] = {}
    for component, factory in registry:
        adapter = factory.build({})
        binding = ComponentBinding(component=component, variant=_adapter_variant(adapter))
        surfaces[binding] = CapabilitySurface(
            provides=frozenset(capability.name for capability in adapter.provides),
            requires=frozenset(capability.name for capability in adapter.requires),
        )
    return surfaces


def bindings_from_registry(registry: ComponentRegistry) -> tuple[ComponentBinding, ...]:
    """The variant-distinct bindings a registry can supply, canonically sorted."""
    return tuple(sorted(capability_surfaces_from_registry(registry), key=_canonical_key))


def classify_shape(
    shape: CompositionShape,
    surfaces: Mapping[ComponentBinding, CapabilitySurface],
    required: Sequence[str] = (),
) -> CompositionClassification:
    """Classify a shape against pre-built capability surfaces.

    ``provided`` is the union of the surfaces of the shape's bindings;
    ``needed`` is the union of those surfaces' ``requires`` plus the optional
    world-level ``required`` names.  The status is ``CAPABILITY_VALID`` when no
    name is missing, else ``CAPABILITY_INVALID``; ``missing_capabilities`` is
    the deterministic, sorted tuple of the gap.  Capability-valid does not
    imply an executable composition (coupling templates are a later stage).
    """
    provided: set[str] = set()
    needed: set[str] = set(required)
    for binding in shape:
        surface = surfaces.get(binding)
        if surface is None:
            raise ValueError(f"no capability surface for binding {binding.as_dict()!r}")
        provided.update(surface.provides)
        needed.update(surface.requires)
    missing = tuple(sorted(name for name in needed if name not in provided))
    status = CAPABILITY_INVALID if missing else CAPABILITY_VALID
    return CompositionClassification(
        shape=shape,
        status=status,
        missing_capabilities=missing,
    )


def classify_shapes(
    shapes: Iterable[CompositionShape],
    surfaces: Mapping[ComponentBinding, CapabilitySurface],
    required: Sequence[str] = (),
) -> tuple[CompositionClassification, ...]:
    """Deterministic batch form of :func:`classify_shape`."""
    return tuple(classify_shape(shape, surfaces, required) for shape in shapes)


def _adapter_variant(adapter: SimulationEngine) -> str | None:
    variant: object = getattr(adapter, "variant", None)
    if variant is None:
        return None
    if not isinstance(variant, str):
        raise TypeError(f"adapter variant must be a str or None, got {type(variant).__name__}")
    return variant


__all__ = [
    "CAPABILITY_INVALID",
    "CAPABILITY_VALID",
    "CapabilitySurface",
    "ComponentBinding",
    "CompositionClassification",
    "CompositionShape",
    "CompositionSpace",
    "bindings_from_registry",
    "capability_surfaces_from_registry",
    "classify_shape",
    "classify_shapes",
]