"""Composition catalog: reproducible, explainable classification of a space.

Stage 5 turns ``classify_composition`` into a queryable, decision-reachable
catalog over an entire ``CompositionSpace``: every shape is classified once, in
a deterministic enumeration order, and the result is a flat tuple of
``CatalogCandidate`` rows (shape identity, taxonomy status, missing
capabilities, matched template, verdict reasons, composition identity, and --
when requested -- the generated ``WorldDefinition`` of every executable
candidate).

Construction is eager but cheap: nothing is simulated, persisted, searched, or
written.  The interesting classification work is adapter *construction* for
template-matched shapes only (read metadata from constructors, never
initialize or step), and ``generate_worlds=True`` merely materializes the
declarative worlds of the executable candidates.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from sim_alchemist.core.capabilities import SimulationEngine
from sim_alchemist.core.composition import (
    CapabilitySurface,
    ComponentBinding,
    CompositionShape,
    CompositionSpace,
)
from sim_alchemist.core.templates import (
    EXECUTABLE,
    CouplingTemplate,
    CouplingTemplateRegistry,
    classify_composition,
    generate_world,
)
from sim_alchemist.core.world import WorldDefinition


@dataclass(frozen=True)
class CatalogCandidate:
    """One classified shape of a composition space."""

    shape: CompositionShape
    status: str
    shape_id: str
    bindings: tuple[ComponentBinding, ...]
    missing_capabilities: tuple[str, ...]
    template: str | None
    reason: str | None
    composition_id: str | None
    generated_world: WorldDefinition | None

    @property
    def generated_world_available(self) -> bool:
        return self.status == EXECUTABLE

    def explain(self) -> str:
        lines = [f"{self.shape_id} -> {self.status}"]
        if self.missing_capabilities:
            lines.append("  missing capability(ies): " + ", ".join(self.missing_capabilities))
        if self.template:
            lines.append(f"  matched template: {self.template}")
        if self.composition_id:
            lines.append(f"  composition id: {self.composition_id}")
        if self.reason:
            lines.append(f"  reason: {self.reason}")
        return "\n".join(lines)


class CompositionCatalog:
    """All shapes of a space, pre-classified through the executable taxonomy.

    The catalog is an immutable snapshot: it is built once from the space,
    its surfaces, and its template registry, then can only be queried.  There
    is no persistence, no search, and no automatic coupling -- a candidate's
    status is fully explained by its row.
    """

    def __init__(
        self,
        space: CompositionSpace,
        surfaces: Mapping[ComponentBinding, CapabilitySurface],
        templates: Sequence[CouplingTemplate] | CouplingTemplateRegistry,
        *,
        build_adapters: Callable[[CompositionShape, CouplingTemplate], Sequence[SimulationEngine]],
        generate_worlds: bool = False,
    ) -> None:
        registry = (
            templates
            if isinstance(templates, CouplingTemplateRegistry)
            else CouplingTemplateRegistry.from_sequence(templates)
        )
        if not isinstance(space, CompositionSpace):
            raise TypeError("space must be a CompositionSpace")
        self.space = space
        self.surfaces = dict(surfaces)
        self.templates = registry
        self.build_adapters = build_adapters
        self.generate_worlds = generate_worlds

        candidates: list[CatalogCandidate] = []
        for shape in space.enumerate_shapes():
            verdict = classify_composition(
                shape,
                self.surfaces,
                registry,
                build_adapters=build_adapters,
            )
            generated = None
            template = None
            if verdict.template is not None:
                template = registry.by_name(verdict.template)
                if generate_worlds and verdict.status == EXECUTABLE and template is not None:
                    generated = generate_world(template)
            candidates.append(
                CatalogCandidate(
                    shape=shape,
                    status=verdict.status,
                    shape_id=shape.shape_id,
                    bindings=shape.bindings,
                    missing_capabilities=verdict.missing_capabilities,
                    template=verdict.template,
                    reason="; ".join(verdict.reasons) if verdict.reasons else None,
                    composition_id=verdict.composition_id,
                    generated_world=generated,
                )
            )
        self.candidates = tuple(candidates)

    def all(self) -> tuple[CatalogCandidate, ...]:
        return self.candidates

    def executable(self) -> tuple[CatalogCandidate, ...]:
        return tuple(c for c in self.candidates if c.status == EXECUTABLE)

    def invalid(self) -> tuple[CatalogCandidate, ...]:
        return tuple(c for c in self.candidates if c.status != EXECUTABLE)

    def by_status(self, status: str) -> tuple[CatalogCandidate, ...]:
        return tuple(c for c in self.candidates if c.status == status)

    def by_shape_id(self, shape_id: str) -> CatalogCandidate | None:
        for candidate in self.candidates:
            if candidate.shape_id == shape_id:
                return candidate
        return None

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in self.candidates:
            counts[candidate.status] = counts.get(candidate.status, 0) + 1
        return dict(sorted(counts.items()))

    def explain(self, shape_id: str) -> str:
        candidate = self.by_shape_id(shape_id)
        if candidate is None:
            return f"no candidate with shape id {shape_id}"
        return candidate.explain()


__all__ = ["CatalogCandidate", "CompositionCatalog"]