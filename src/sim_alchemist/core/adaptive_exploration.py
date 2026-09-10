"""Task 2.7 Build Stage 1 — Researcher-Constrained Adaptive Exploration Specification.

Plan-only design implementation (no execution, no CLI, no lineage writes).
Experiment-free; consumes generic MutationSpace / CompositionCatalog abstractions.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

# Existing generic core imports — only pure projection / identity APIs
from sim_alchemist.core.sweep import MutationSpace, ParameterSweep

# Note: no SweepRunner.run, CrossCompositionSweep.run, AdaptiveSweepRunner.run,
# adapter.initialize, engine.step, LineageStore write APIs (see design §14).


@dataclass(frozen=True)
class ParameterConstraint:
    """A researcher-declared restriction on one declared mutation dimension."""
    path: str
    freeze: bool = False
    allowed: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("ParameterConstraint.path must be non-empty str")
        if self.freeze and self.allowed is not None:
            raise ValueError("freeze and allowed are mutually exclusive")
        if self.allowed is not None:
            if not isinstance(self.allowed, tuple) or len(self.allowed) == 0:
                raise ValueError("allowed must be a non-empty tuple of floats")
            for v in self.allowed:
                if not isinstance(v, (int, float)) or math.isinf(v) or math.isnan(v):
                    raise ValueError("each allowed value must be a finite float")


@dataclass(frozen=True)
class AdaptiveExplorationSpec:
    """Immutable researcher-declared exploration plan (Stage 1 foundation)."""
    composition_ids: tuple[str, ...]
    profile: str | None = None
    seed: int = 0
    budget: int = 3
    constraints: tuple[ParameterConstraint, ...] = ()

    def __post_init__(self) -> None:
        # Composition IDs: deterministic canonical, no duplicates
        if not self.composition_ids:
            raise ValueError("composition_ids must be non-empty")
        for c in self.composition_ids:
            if not isinstance(c, str) or not c:
                raise ValueError("each composition_ids entry must be non-empty str")
        if len(self.composition_ids) != len(set(self.composition_ids)):
            raise ValueError("duplicate composition_ids")
        # Ordering: canonical sorted for identity (set semantics preserved)
        # We do not reject unsorted input; identity sorts internally.
        if self.budget <= 0:
            raise ValueError("budget must be positive")
        if self.profile is not None and (
            not isinstance(self.profile, str) or not self.profile
        ):
            raise ValueError("profile must be non-empty str or None")
        # Constraints: unique paths
        paths = [c.path for c in self.constraints]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate constraint paths")
        # Constraints refer to declared dimensions: deferred to subspace filter,
        # but basic path format validated here.

    def as_dict(self) -> dict:
        return {
            "composition_ids": sorted(self.composition_ids),
            "profile": self.profile,
            "seed": int(self.seed),
            "budget": int(self.budget),
            "constraints": [
                {
                    "path": c.path,
                    "freeze": bool(c.freeze),
                    "allowed": list(c.allowed) if c.allowed else None,
                }
                for c in sorted(self.constraints, key=lambda c: c.path)
            ],
        }


@dataclass(frozen=True)
class AdaptiveExplorationStatus:
    """Explicit planning status (never silent conversion)."""
    status: str  # VALID / INVALID / EMPTY_SUBSPACE
    reason: str
    eligible_compositions: tuple[str, ...]
    constrained_subspace_size: int
    explanation: str

    def __post_init__(self) -> None:
        if self.status not in ("VALID", "INVALID", "EMPTY_SUBSPACE"):
            raise ValueError("status must be VALID / INVALID / EMPTY_SUBSPACE")


@dataclass(frozen=True)
class AdaptiveExplorationResult:
    """Planning-only result; no simulation results, no run IDs, no lineage writes."""
    exploration_id: str
    spec_dict: dict
    status: AdaptiveExplorationStatus
    eligible_compositions: tuple[str, ...]
    subspace_size: int
    explanation: str

    def __post_init__(self) -> None:
        if not self.exploration_id or not isinstance(self.exploration_id, str):
            raise ValueError("exploration_id required")
        if len(self.exploration_id) != 24:
            raise ValueError("exploration_id must be 24-hex content-addressed")


def adaptive_exploration_id_of(
    spec: AdaptiveExplorationSpec | dict,
    seed: int = 0,
) -> str:
    """Deterministic 24-hex identity over canonical spec (no timestamps/repr/order)."""
    if isinstance(spec, AdaptiveExplorationSpec):
        payload = json.dumps(spec.as_dict(), separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    else:
        # Assumes caller passes a canonical dict (sorted, no extras)
        payload = json.dumps(dict(sorted(spec.items())), separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def filter_subspace(
    space: MutationSpace,
    constraints: Sequence[ParameterConstraint],
) -> MutationSpace:
    """Pure projection: constrain a legitimate MutationSpace without inventing values.

    - Frozen dimensions are excluded from the product (do not vary).
    - Allowed dimensions replace the original values with the allowed subset.
    - Unknown paths are rejected clearly.
    - Empty valid subspace (all frozen / all excluded) is distinguishable.
    - Source MutationSpace never mutated.
    """
    # Map paths to original dimensions for validation
    original_paths = {d.path for d in space.dimensions}
    for c in constraints:
        if c.path not in original_paths:
            raise ValueError(f"constraint path '{c.path}' not found in MutationSpace")

    # Build constrained dimensions deterministically (canonical order by path)
    dims = []
    frozen_count = 0
    for d in sorted(space.dimensions, key=lambda d: d.path):
        c = next((con for con in constraints if con.path == d.path), None)
        if c is not None and c.freeze:
            frozen_count += 1
            # Freeze: exclude from variation (do not include in product)
            continue
        if c is not None and c.allowed is not None:
            # Restrict to allowed subset (must be non-empty; validated by ParameterConstraint)
            dims.append(ParameterSweep(path=d.path, values=tuple(c.allowed)))
        else:
            # Unconstrained: preserve original ordered values
            dims.append(ParameterSweep(path=d.path, values=d.values))

    if not dims:
        # All dimensions frozen or excluded: empty valid subspace (distinct from invalid / no-space)
        # Represent as MutationSpace with zero dimensions — but MutationSpace requires at least one
        # per its __post_init__. To distinguish EMPTY_SUBSPACE from INVALID/NO_SPACE,
        # we represent it with a single synthetic dimension of one value (empty product = 1)
        # but mark it explicitly via status model rather than space object.
        # Here we return a 1-value single-dimension space as the structural representation,
        # and rely on AdaptiveExplorationStatus.EMPTY_SUBSPACE for semantic distinction.
        dims.append(ParameterSweep(path="__empty_subspace_marker__", values=(1,)))

    return MutationSpace(dimensions=tuple(dims))


def evaluate_exploration_spec(
    spec: AdaptiveExplorationSpec,
    mutation_space: MutationSpace | None = None,
    catalog_compositions: tuple[str, ...] | None = None,
) -> AdaptiveExplorationResult:
    """Pure planning evaluation (no execution, no persistence).

    If mutation_space is provided, apply subspace filter and compute size.
    If catalog_compositions provided, validate composition_ids.
    Otherwise assume valid for planning only.
    """
    # Composition validation (pure; uses catalog if provided; otherwise accepts)
    eligible: tuple[str, ...] = ()
    if catalog_compositions is not None:
        catalog_set = set(catalog_compositions)
        unknown = [c for c in spec.composition_ids if c not in catalog_set]
        if unknown:
            return AdaptiveExplorationResult(
                exploration_id=adaptive_exploration_id_of(spec, seed=spec.seed),
                spec_dict=spec.as_dict(),
                status=AdaptiveExplorationStatus(
                    status="INVALID",
                    reason=f"unknown composition_ids: {sorted(unknown)}",
                    eligible_compositions=(),
                    constrained_subspace_size=0,
                    explanation="unknown composition identifiers rejected",
                ),
                eligible_compositions=(),
                subspace_size=0,
                explanation=f"invalid: unknown compositions {sorted(unknown)}",
            )
        eligible = tuple(sorted(set(spec.composition_ids) & catalog_set))
    else:
        eligible = tuple(sorted(set(spec.composition_ids)))

    # Subspace evaluation
    subspace_size = 0
    status_str = "VALID"
    explanation = "valid exploration specification"
    if mutation_space is not None:
        try:
            constrained = filter_subspace(mutation_space, list(spec.constraints))
            subspace_size = constrained.variant_count
            # If subspace is structurally empty (marker dimension only) but constraints valid -> EMPTY_SUBSPACE
            has_marker = any(d.path == "__empty_subspace_marker__" for d in constrained.dimensions)
            if has_marker:
                status_str = "EMPTY_SUBSPACE"
                explanation = "all mutation dimensions frozen or excluded; valid but empty subspace"
            elif subspace_size == 1 and len(spec.constraints) > 0:
                # All dimensions frozen to one value each: technically valid subspace of size 1
                pass  # keep VALID
            if subspace_size == 0:
                # Should not occur given marker representation; defensive
                status_str = "EMPTY_SUBSPACE"
                explanation = "subspace variant count is zero"
        except ValueError as e:
            return AdaptiveExplorationResult(
                exploration_id=adaptive_exploration_id_of(spec, seed=spec.seed),
                spec_dict=spec.as_dict(),
                status=AdaptiveExplorationStatus(
                    status="INVALID",
                    reason=f"constraint error: {e}",
                    eligible_compositions=eligible,
                    constrained_subspace_size=0,
                    explanation="invalid parameter constraints",
                ),
                eligible_compositions=eligible,
                subspace_size=0,
                explanation=f"invalid constraint: {e}",
            )
    else:
        # No mutation space provided: planning-only; subspace size unknown (report 0 with note)
        subspace_size = 0
        explanation = "spec valid; mutation-space subspace size not computed (no space provided)"

    identity = adaptive_exploration_id_of(spec, seed=spec.seed)
    return AdaptiveExplorationResult(
        exploration_id=identity,
        spec_dict=spec.as_dict(),
        status=AdaptiveExplorationStatus(
            status=status_str,
            reason="" if status_str == "VALID" else explanation,
            eligible_compositions=eligible,
            constrained_subspace_size=subspace_size,
            explanation=explanation,
        ),
        eligible_compositions=eligible,
        subspace_size=subspace_size,
        explanation=explanation,
    )
