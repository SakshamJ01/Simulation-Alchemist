"""Generic guided simulation search: a deterministic beam search (Task 1.9).

This is the FIRST *discovery loop* of the framework.  It searches a space of
world variants for the behavior an explicit ``InterestingnessProfile`` ranks
as most interesting, alternating four phases:

    GENERATE -> RUN -> ANALYZE -> SELECT -> (repeat)

Concretely the loop is a **beam search over world variants**:

* generation 0 executes the unmutated base world as a control;
* each generation mutates the current beam (the ``beam_width`` most
  interesting known worlds), runs the generated children, and keeps the
  ``beam_width`` most interesting worlds among the parents plus the new
  children;
* every step reuses the existing generic machinery -- ``apply_mutations`` /
  ``ParameterSpec`` validation (Task 1.6), deterministic ``run_id`` identity
  (Task 1.6), ``rank_by_profile`` (Task 1.8) -- so no new simulation concept
  exists here.

Everything is **deterministic**:

* child mutation sets are produced in a documented, fixed order
  (dimension-major, value-minor, no-op values skipped; single-parameter sets);
* every world is identified by its content via ``world_hash``; identical
  worlds are visited once and never re-executed (skips are counted);
* candidate ids, generation structure, scores, and the final ranking are pure
  functions of (world, mutation space, profile, search seed);
* ties break by ``run_id`` ascending, exactly like the Task 1.7 ranking.

Only compact metadata is persisted (one ``searches`` table row in the same
``LineageStore``): the spec, per-candidate identity/rank record, and timing.
Per-step observables and feature vectors stay in memory; run records (with
feature snapshots) are persisted by the shared lineage layer.

This is a bounded, exhaustive-in-depth heuristic that keeps the *best known*
frontier and discards the rest.  It never claims global optimality; it only
finds the most interesting behavior within the beam that was actually tried.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from sim_alchemist.core.behavior import (
    BehaviorAnalyzer,
    BehaviorFeatures,
    BehaviorRankingResult,
    FeaturedRun,
    FrontierDiagnostics,
    InterestingnessProfile,
    ObservableSeries,
    behavior_vector,
    compute_frontier_diagnostics,
    rank_by_profile,
    select_diverse_frontier,
)
from sim_alchemist.core.lineage import (
    LineageStore,
    RunRecord,
    SearchRecord,
    run_id_of,
    world_hash,
)
from sim_alchemist.core.mutation import (
    Mutation,
    MutationRecord,
    ParameterSpec,
    apply_mutations,
)
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.sweep import MutationSpace
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "SearchCandidate",
    "SearchGeneration",
    "SearchResult",
    "SearchRunner",
    "SearchSpec",
    "SearchTiming",
    "SelectionProfile",
    "child_mutations",
    "search_id_of",
]


@dataclass(frozen=True)
class SelectionProfile:
    """Configures diversity-aware beam selection.

    ``quality_weight`` controls how much the selection favors interestingness
    (the ranking score); ``diversity_weight`` controls how much it favors
    behavioral distance from already-selected candidates.  Both must be
    non-negative and their sum must be positive.

    When ``diversity_weight == 0`` the selection is identical to quality-only
    (Task 1.9 behavior).  When ``quality_weight == 0`` the selection is
    pure diversity (maximize behavioral distance from the frontier).
    """

    quality_weight: float = 1.0
    diversity_weight: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.quality_weight, (int, float)):
            raise TypeError(
                f"quality_weight must be numeric, got {type(self.quality_weight).__name__}"
            )
        if not isinstance(self.diversity_weight, (int, float)):
            raise TypeError(
                f"diversity_weight must be numeric, got {type(self.diversity_weight).__name__}"
            )
        qw = float(self.quality_weight)
        dw = float(self.diversity_weight)
        if not math.isfinite(qw) or qw < 0.0:
            raise ValueError(f"quality_weight must be finite and >= 0, got {qw}")
        if not math.isfinite(dw) or dw < 0.0:
            raise ValueError(f"diversity_weight must be finite and >= 0, got {dw}")
        if qw + dw <= 0.0:
            raise ValueError(
                f"quality_weight + diversity_weight must be > 0, got {qw + dw}"
            )

    def as_dict(self) -> dict[str, float]:
        return {
            "quality_weight": self.quality_weight,
            "diversity_weight": self.diversity_weight,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SelectionProfile:
        return cls(
            quality_weight=float(data["quality_weight"]),
            diversity_weight=float(data["diversity_weight"]),
        )


@dataclass(frozen=True)
class SearchSpec:
    """The declarative configuration of one guided search.

    Fields:

    * ``name`` -- a free-form label (must be non-empty);
    * ``generations`` -- how many beam-expansion steps run after generation 0
      (must be >= 1);
    * ``beam_width`` -- how many worlds survive each generation (>= 1);
    * ``children_per_parent`` -- how many child mutation sets each survivor
      generates (>= 1);
    * ``mutation_space`` -- the declared ``MutationSpace`` being searched;
    * ``profile`` -- the ``InterestingnessProfile`` that defines what counts
      as interesting (explicit weights and directions only);
    * ``seed`` -- a deterministic replay key encoded into the search id.  The
      search itself has no random component (candidate order and tie-breaks
      are fixed); the seed only tells two otherwise-identical searches apart.
    """

    name: str
    generations: int
    beam_width: int
    children_per_parent: int
    mutation_space: MutationSpace
    profile: InterestingnessProfile
    seed: int = 0
    selection_profile: SelectionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("a search needs a non-empty name")
        for label, value in (
            ("generations", self.generations),
            ("beam_width", self.beam_width),
            ("children_per_parent", self.children_per_parent),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive int, got {value!r}")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError(f"seed must be an int, got {self.seed!r}")
        if not self.mutation_space.dimensions:
            raise ValueError("a search needs a non-empty mutation space")
        if not self.profile.weights:
            raise ValueError("a search needs a profile with at least one weight")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "generations": self.generations,
            "beam_width": self.beam_width,
            "children_per_parent": self.children_per_parent,
            "mutation_space": self.mutation_space.to_dict(),
            "profile": self.profile.as_dict(),
            "seed": self.seed,
        }
        if self.selection_profile is not None:
            out["selection_profile"] = self.selection_profile.as_dict()
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SearchSpec:
        sp_data = data.get("selection_profile")
        return cls(
            name=str(data["name"]),
            generations=int(data["generations"]),
            beam_width=int(data["beam_width"]),
            children_per_parent=int(data["children_per_parent"]),
            mutation_space=MutationSpace.from_dict(data["mutation_space"]),
            profile=InterestingnessProfile.from_dict(data["profile"]),
            seed=int(data.get("seed", 0)),
            selection_profile=(
                None if sp_data is None else SelectionProfile.from_dict(sp_data)
            ),
        )


@dataclass(frozen=True)
class SearchTiming:
    """Compact instrumentation of one search (no per-step data).

    ``n_generated`` counts every child mutation set examined; ``n_skipped``
    those rejected (no-op or already-visited world); ``n_executed`` the worlds
    actually run (the root control plus every unique child).
    ``analysis_seconds`` is ``total_seconds - execution_seconds`` (feature
    extraction, ranking, and bookkeeping); ``mean_seconds`` divides the
    execution time by the worlds executed, so it is comparable across beam
    sizes.
    """

    n_generated: int
    n_skipped: int
    n_executed: int
    total_seconds: float
    execution_seconds: float
    analysis_seconds: float
    mean_seconds: float
    n_distance_calcs: int = 0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_generated": self.n_generated,
            "n_skipped": self.n_skipped,
            "n_executed": self.n_executed,
            "total_seconds": self.total_seconds,
            "execution_seconds": self.execution_seconds,
            "analysis_seconds": self.analysis_seconds,
            "mean_seconds": self.mean_seconds,
            "n_distance_calcs": self.n_distance_calcs,
        }


@dataclass(frozen=True)
class SearchCandidate:
    """One evaluated world inside a search.

    ``score`` is the candidate's score in the *final* global ranking (the
    ranking normalizes across every evaluated candidate, so it is stable
    until the search finishes); ``selection_rank`` is the rank of the pool
    (surviving parents + that generation's new children) in which the
    candidate was *created* -- a world without a creation pool keeps ``None``;
    ``final_rank`` is the final global rank (1 = best).  ``observables`` and
    ``features`` live in memory only and are never persisted.
    """

    candidate_id: str
    run_id: str
    world: WorldDefinition
    generation: int
    kind: str  # "baseline" (root control) | "variant" (any child)
    parent_candidate_id: str | None = None
    parent_run_id: str | None = None
    mutations: tuple[MutationRecord, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    features: BehaviorFeatures | None = None
    observables: Mapping[str, ObservableSeries] = field(default_factory=dict)
    score: float | None = None
    selection_rank: int | None = None
    final_rank: int | None = None
    behavior_vector: dict[str, float] | None = None
    selection_quality_score: float | None = None
    selection_diversity_score: float | None = None
    selection_combined_score: float | None = None
    selection_reason: str | None = None

    @property
    def world_hash(self) -> str:
        return world_hash(self.world)

    def mutation_display(self) -> str:
        parts = [m.display() for m in self.mutations]
        return "; ".join(parts) if parts else "(none)"

    def as_dict(self) -> dict[str, Any]:
        """Compact, canonical-safe metadata (no timing, no series, no grid)."""
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "world_id": self.world.id,
            "world_hash": self.world_hash,
            "generation": self.generation,
            "kind": self.kind,
            "parent_candidate_id": self.parent_candidate_id,
            "parent_run_id": self.parent_run_id,
            "mutations": [m.to_dict() for m in self.mutations],
            "metrics": dict(self.metrics),
            "score": self.score,
            "selection_rank": self.selection_rank,
            "final_rank": self.final_rank,
            "selection_quality_score": self.selection_quality_score,
            "selection_diversity_score": self.selection_diversity_score,
            "selection_combined_score": self.selection_combined_score,
            "selection_reason": self.selection_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SearchCandidate:
        return cls(
            candidate_id=str(data["candidate_id"]),
            run_id=str(data["run_id"]),
            world=WorldDefinition(id=str(data["world_id"]), components=()),  # metadata-only
            generation=int(data["generation"]),
            kind=str(data["kind"]),
            parent_candidate_id=data.get("parent_candidate_id"),
            parent_run_id=data.get("parent_run_id"),
            mutations=tuple(
                MutationRecord.from_dict(m) for m in data.get("mutations", [])
            ),
            metrics={k: float(v) for k, v in data.get("metrics", {}).items()},
            score=None if data.get("score") is None else float(data["score"]),
            selection_rank=(
                None
                if data.get("selection_rank") is None
                else int(data["selection_rank"])
            ),
            final_rank=(
                None if data.get("final_rank") is None else int(data["final_rank"])
            ),
            behavior_vector=(
                None
                if data.get("behavior_vector") is None
                else {k: float(v) for k, v in data["behavior_vector"].items()}
            ),
            selection_quality_score=(
                None
                if data.get("selection_quality_score") is None
                else float(data["selection_quality_score"])
            ),
            selection_diversity_score=(
                None
                if data.get("selection_diversity_score") is None
                else float(data["selection_diversity_score"])
            ),
            selection_combined_score=(
                None
                if data.get("selection_combined_score") is None
                else float(data["selection_combined_score"])
            ),
            selection_reason=data.get("selection_reason"),
        )


@dataclass(frozen=True)
class SearchGeneration:
    """One beam-expansion step: what was tried and what survived.

    ``parent_candidate_ids`` is the beam selected by the previous generation
    (root only for generation 1); ``child_candidate_ids`` are the newly
    executed children in evaluation order; ``selected_candidate_ids`` the beam
    carried into the next generation (best-first).  Generation 0 is recorded
    for uniformity (parent empty, child list = the root).
    """

    generation: int
    parent_candidate_ids: tuple[str, ...]
    child_candidate_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    best_candidate_id: str | None
    best_score: float | None
    diagnostics: FrontierDiagnostics | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "generation": self.generation,
            "parent_candidate_ids": list(self.parent_candidate_ids),
            "child_candidate_ids": list(self.child_candidate_ids),
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "best_candidate_id": self.best_candidate_id,
            "best_score": self.best_score,
        }
        if self.diagnostics is not None:
            out["diagnostics"] = self.diagnostics.as_dict()
        return out


def search_id_of(world: WorldDefinition, spec: SearchSpec) -> str:
    """Deterministic search identity: base world content + search spec.

    The same world + spec always yield the same search id, so recorded search
    metadata is replayable and idempotent.
    """
    payload = json.dumps(
        {"world_hash": world_hash(world), "spec": spec.to_dict()},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def child_mutations(
    world: WorldDefinition,
    space: MutationSpace,
    children_per_parent: int,
    *,
    validators: Mapping[str, Callable[[Any], bool]] | None = None,
) -> tuple[tuple[Mutation, ...], ...]:
    """Deterministic child mutation sets for one parent world.

    The sets are produced in **documented order**: dimension-major (dimensions
    in declared sweep order), value-minor (values in declared order), and a
    value equal to the parent's current leaf is skipped (a no-op cannot extend
    the beam).  Every set mutates exactly one declared parameter (single-param
    children); the loop stops as soon as ``children_per_parent`` non-empty
    sets have been collected.  Mutation validity (type + declared parameter
    specs) is verified per candidate via ``apply_mutations``, so an invalid
    value raises before anything would be simulated.
    """
    if isinstance(children_per_parent, bool) or not isinstance(
        children_per_parent, int
    ) or children_per_parent <= 0:
        raise ValueError(
            f"children_per_parent must be a positive int, got {children_per_parent!r}"
        )
    out: list[tuple[Mutation, ...]] = []
    for dimension in space.dimensions:
        for value in dimension.values:
            mutation = Mutation(dimension.path, value)
            child, _ = apply_mutations(world, (mutation,), validators=validators)
            if child.as_dict() == world.as_dict():
                continue  # no-op for this parent (value repeats its current leaf)
            out.append((mutation,))
            if len(out) >= children_per_parent:
                break
        if len(out) >= children_per_parent:
            break
    return tuple(out)


class SearchRunner:
    """Sequential, deterministic guided beam search over one executor.

    Reuses ``apply_mutations``/``ParameterSpec`` validation (Task 1.6),
    deterministic ``run_id`` identity (Task 1.6), the ``LineageStore``, and
    ``rank_by_profile`` (Task 1.8).  The base world is always executed and
    recorded first as the control (generation 0); every executed child is
    recorded with its parent run link; identical worlds are visited once.
    """

    def __init__(
        self,
        store: LineageStore,
        executor: Callable[[WorldDefinition], ExecOutcome],
        observables: Callable[[ExecOutcome], Mapping[str, ObservableSeries]],
        *,
        parameter_specs: Mapping[str, ParameterSpec] | None = None,
        analyzer: BehaviorAnalyzer | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._observables = observables
        self._specs = dict(parameter_specs or {})
        self._analyzer = analyzer or BehaviorAnalyzer()

    @property
    def store(self) -> LineageStore:
        return self._store

    def _validators(self) -> dict[str, Callable[[Any], bool]]:
        out: dict[str, Callable[[Any], bool]] = {}
        for path, spec in self._specs.items():
            fn = spec.validator()
            if fn is not None:
                out[path] = fn
        return out

    def search(
        self,
        base_world: WorldDefinition,
        spec: SearchSpec,
        *,
        search_id: str | None = None,
    ) -> SearchResult:
        """Run one guided beam search from ``base_world`` under ``spec``.

        Validation mirrors ``SweepRunner`` phase 1: every combination in the
        declared mutation space is type- and spec-checked against the base
        world *before any simulation starts* (an invalid value aborts the
        search with nothing executed or recorded).  Generation 0 executes the
        root control; each later generation expands the current beam, runs the
        unique children, and keeps the most interesting ``beam_width`` worlds.
        The final ranking covers *every* evaluated candidate.
        """
        if search_id is None:
            search_id = search_id_of(base_world, spec)

        validators = self._validators()
        # Phase 0 (no simulation): reject any invalid declared value up front.
        for mutations in spec.mutation_space.variant_mutation_sets():
            apply_mutations(base_world, mutations, validators=validators)

        total_start = time.monotonic()
        execution_seconds = 0.0
        candidates_by_id: dict[str, SearchCandidate] = {}
        by_run_id: dict[str, SearchCandidate] = {}
        candidate_order: list[str] = []
        visited: set[str] = set()
        n_skipped = 0
        n_generated = 0
        n_distance_calcs = 0
        counter = 0
        baseline_obs: Mapping[str, ObservableSeries] | None = None

        def _run_world(
            world: WorldDefinition,
            *,
            mutations: tuple[MutationRecord, ...],
            parent_run_id: str | None,
            parent_candidate_id: str | None,
            generation: int,
            kind: str,
        ) -> SearchCandidate:
            nonlocal execution_seconds, counter
            exec_start = time.monotonic()
            outcome = self._executor(world)
            execution_seconds += time.monotonic() - exec_start
            observables = dict(self._observables(outcome))
            features = self._analyzer.features(observables, baseline=baseline_obs)
            record = RunRecord(
                run_id=run_id_of(world),
                world=world,
                parent_run_id=parent_run_id,
                mutations=mutations,
                metrics=outcome.metrics,
                feature_snapshot=features.as_dict(),
            )
            self._store.record_run(record)
            candidate = SearchCandidate(
                candidate_id=f"candidate-{counter:03d}",
                run_id=record.run_id,
                world=world,
                generation=generation,
                kind=kind,
                parent_candidate_id=parent_candidate_id,
                parent_run_id=parent_run_id,
                mutations=mutations,
                metrics=outcome.metrics,
                features=features,
                observables=observables,
            )
            counter += 1
            candidates_by_id[candidate.candidate_id] = candidate
            by_run_id[candidate.run_id] = candidate
            candidate_order.append(candidate.candidate_id)
            return candidate

        # Generation 0: the root control.
        root = _run_world(
            base_world,
            mutations=(),
            parent_run_id=None,
            parent_candidate_id=None,
            generation=0,
            kind="baseline",
        )
        baseline_obs = root.observables
        visited.add(root.world_hash)

        generations: list[SearchGeneration] = []
        selected_candidate_ids: tuple[str, ...] = (root.candidate_id,)
        generations.append(
            SearchGeneration(
                generation=0,
                parent_candidate_ids=(),
                child_candidate_ids=(root.candidate_id,),
                selected_candidate_ids=(root.candidate_id,),
                best_candidate_id=root.candidate_id,
                best_score=None,
            )
        )

        def _rank_pool(
            pool: tuple[SearchCandidate, ...],
        ) -> BehaviorRankingResult:
            population = [
                FeaturedRun(
                    run_id=c.run_id,
                    kind=c.kind,
                    world=c.world,
                    mutations=c.mutations,
                    metrics=c.metrics,
                    features=c.features or BehaviorFeatures(units={}),
                    observables=c.observables,
                )
                for c in pool
            ]
            return rank_by_profile(population, spec.profile)

        for gen in range(1, spec.generations + 1):
            parents = tuple(
                candidates_by_id[cid] for cid in selected_candidate_ids
            )
            child_candidate_ids: list[str] = []
            new_children: list[SearchCandidate] = []
            for parent in parents:
                for mutations in child_mutations(
                    parent.world,
                    spec.mutation_space,
                    spec.children_per_parent,
                    validators=validators,
                ):
                    n_generated += 1
                    child_world, records = apply_mutations(
                        parent.world, mutations, validators=validators
                    )
                    if (
                        child_world.as_dict() == parent.world.as_dict()
                        or world_hash(child_world) in visited
                    ):
                        n_skipped += 1
                        continue
                    visited.add(world_hash(child_world))
                    child = _run_world(
                        child_world,
                        mutations=records,
                        parent_run_id=parent.run_id,
                        parent_candidate_id=parent.candidate_id,
                        generation=gen,
                        kind="variant",
                    )
                    new_children.append(child)
                    child_candidate_ids.append(child.candidate_id)

            pool = (*parents, *new_children)
            if pool:
                ranking = _rank_pool(pool)
                rows = ranking.rows
                rows_by_run = {r.run_id: r for r in rows}
                for cand in pool:
                    row = rows_by_run[cand.run_id]
                    if cand.selection_rank is None:
                        updated = replace(cand, selection_rank=row.rank)
                        candidates_by_id[cand.candidate_id] = updated
                        by_run_id[cand.run_id] = updated
                beam = spec.selection_profile
                pool_vectors = {
                    c.candidate_id: behavior_vector(
                        c.features or BehaviorFeatures(units={})
                    )
                    for c in pool
                }
                if beam is not None:
                    # Diversity-aware greedy selection (Task 2.0).
                    entries = select_diverse_frontier(
                        candidates=[
                            (
                                c.run_id,
                                rows_by_run[c.run_id].score,
                                pool_vectors[c.candidate_id],
                            )
                            for c in pool
                        ],
                        beam_width=spec.beam_width,
                        quality_weight=beam.quality_weight,
                        diversity_weight=beam.diversity_weight,
                    )
                    for rid, quality, div_dist, combined, _min_dist, reason in entries:
                        cand = by_run_id[rid]
                        candidates_by_id[cand.candidate_id] = replace(
                            cand,
                            selection_quality_score=float(quality),
                            selection_diversity_score=float(div_dist),
                            selection_combined_score=float(combined),
                            selection_reason=reason,
                        )
                        by_run_id[rid] = candidates_by_id[cand.candidate_id]
                    selected_run_ids = tuple(e[0] for e in entries)
                    n_distance_calcs += sum(
                        k * (len(pool) - k)
                        for k in range(1, min(spec.beam_width, len(pool)))
                    )
                else:
                    # Quality-only selection (Task 1.9 semantics).
                    selected_run_ids = tuple(
                        row.run_id
                        for row in rows[: min(spec.beam_width, len(rows))]
                    )
                    for rid in selected_run_ids:
                        cand = by_run_id[rid]
                        candidates_by_id[cand.candidate_id] = replace(
                            cand,
                            selection_quality_score=float(rows_by_run[rid].score),
                            selection_reason="highest_quality",
                        )
                        by_run_id[rid] = candidates_by_id[cand.candidate_id]
                best_row = rows[0]
                best_id = by_run_id[best_row.run_id].candidate_id
                best_score = best_row.score
                selected_candidate_ids = tuple(
                    by_run_id[rid].candidate_id for rid in selected_run_ids
                )
                # Collapse diagnostics over this generation's kept beam.
                beam_cands = [
                    candidates_by_id[cid] for cid in selected_candidate_ids
                ]
                beam_q = [
                    c.selection_quality_score
                    for c in beam_cands
                    if c.selection_quality_score is not None
                ]
                beam_vec = [
                    behavior_vector(c.features or BehaviorFeatures(units={}))
                    for c in beam_cands
                ]
                if beam_q and beam_vec:
                    diagnostics = compute_frontier_diagnostics(beam_q, beam_vec)
                else:
                    diagnostics = None
            else:
                best_id = None
                best_score = None
                diagnostics = None
            generations.append(
                SearchGeneration(
                    generation=gen,
                    parent_candidate_ids=tuple(p.candidate_id for p in parents),
                    child_candidate_ids=tuple(child_candidate_ids),
                    selected_candidate_ids=selected_candidate_ids,
                    best_candidate_id=best_id,
                    best_score=best_score,
                    diagnostics=diagnostics,
                )
            )

        total_seconds = time.monotonic() - total_start

        # Final global ranking over every evaluated candidate; the reference
        # for divergence stays the root control's observables.
        all_candidates = tuple(
            candidates_by_id[cid] for cid in candidate_order
        )
        final_ranking = _rank_pool(all_candidates)
        for row in final_ranking.rows:
            cand = next(c for c in all_candidates if c.run_id == row.run_id)
            candidates_by_id[cand.candidate_id] = replace(
                candidates_by_id[cand.candidate_id],
                score=row.score,
                final_rank=row.rank,
            )
        ranked_candidates = tuple(
            candidates_by_id[cid] for cid in candidate_order
        )

        # Collapse diagnostics over the final kept beam (the last selected
        # set), using final scores.
        final_beam_ids = generations[-1].selected_candidate_ids
        final_beam_cands = [
            candidates_by_id[cid] for cid in final_beam_ids
        ]
        final_beam_q = [
            c.score for c in final_beam_cands if c.score is not None
        ]
        final_beam_vec = [
            behavior_vector(c.features or BehaviorFeatures(units={}))
            for c in final_beam_cands
        ]
        if final_beam_q and final_beam_vec:
            frontier_diagnostics = compute_frontier_diagnostics(
                final_beam_q, final_beam_vec
            )
        else:
            frontier_diagnostics = None

        timing = SearchTiming(
            n_generated=n_generated,
            n_skipped=n_skipped,
            n_executed=len(candidate_order),
            total_seconds=total_seconds,
            execution_seconds=execution_seconds,
            analysis_seconds=max(0.0, total_seconds - execution_seconds),
            mean_seconds=execution_seconds / max(1, len(candidate_order)),
            n_distance_calcs=n_distance_calcs,
        )

        result = SearchResult(
            search_id=search_id,
            world=base_world,
            spec=spec,
            root=root,
            candidates=ranked_candidates,
            generations=tuple(generations),
            final_ranking=final_ranking,
            timing=timing,
            frontier_diagnostics=frontier_diagnostics,
        )
        self._store.record_search(
            SearchRecord.from_result(result, created_at=None)
        )
        return result


@dataclass(frozen=True)
class SearchResult:
    """The full outcome of one guided search (in-memory).

    ``candidates`` holds every executed world in evaluation order (root
    first); ``final_ranking`` ranks all of them against the profile.
    Per-step observables live only on the candidates and never enter the
    lineage store.
    """

    search_id: str
    world: WorldDefinition
    spec: SearchSpec
    root: SearchCandidate
    candidates: tuple[SearchCandidate, ...]
    generations: tuple[SearchGeneration, ...]
    final_ranking: BehaviorRankingResult
    timing: SearchTiming
    frontier_diagnostics: FrontierDiagnostics | None = None

    def candidate(self, candidate_id: str) -> SearchCandidate | None:
        return next(
            (c for c in self.candidates if c.candidate_id == candidate_id), None
        )

    def by_run_id(self, run_id: str) -> SearchCandidate | None:
        return next((c for c in self.candidates if c.run_id == run_id), None)

    def best(self) -> SearchCandidate | None:
        return next(
            (c for c in self.candidates if c.final_rank == 1), None
        )

    def rank_of(self, candidate_id: str) -> int | None:
        cand = self.candidate(candidate_id)
        return cand.final_rank if cand is not None else None

    def lineage_path(self, candidate_id: str) -> tuple[str, ...]:
        """Candidate ids from the root through ``candidate_id`` (root first)."""
        cand = self.candidate(candidate_id)
        if cand is None:
            return ()
        chain: list[str] = []
        current: SearchCandidate | None = cand
        while current is not None:
            chain.append(current.candidate_id)
            current = (
                self.candidate(current.parent_candidate_id)
                if current.parent_candidate_id is not None
                else None
            )
        return tuple(reversed(chain))

    def mutation_path(self, candidate_id: str) -> tuple[MutationRecord, ...]:
        """Every mutation applied along the root->candidate chain, in order."""
        out: list[MutationRecord] = []
        for cid in self.lineage_path(candidate_id):
            cand = self.candidate(cid)
            if cand is not None:
                out.extend(cand.mutations)
        return tuple(out)

    def explain_best(self, *, top: int | None = None) -> list[str]:
        row = next(
            (r for r in self.final_ranking.rows if r.run_id == self.best().run_id),
            None,
        ) if self.best() is not None else None
        return row.explanation(top=top) if row is not None else []

    def explain_selection(self, candidate_id: str) -> list[str]:
        """Explain why a candidate was kept in the beam.

        Reports the measured values that drove selection: the pool (ranking)
        quality score, the minimum normalized behavioral distance to any
        already-kept candidate, the combined diversity-aware selection score,
        and the selection reason ("highest_quality" for the frontier seed,
        "diversity_balanced" for later slots).  Everything comes from measured
        values -- no invented numbers.
        """
        cand = self.candidate(candidate_id)
        if cand is None:
            return []
        sp = self.spec.selection_profile
        q = cand.selection_quality_score
        d = cand.selection_diversity_score
        combined = cand.selection_combined_score
        reason = cand.selection_reason or "highest_quality"
        lines: list[str] = [
            (
                f"candidate {cand.candidate_id} ({cand.kind}, generation "
                f"{cand.generation})"
            ),
            f"  selection reason: {reason}",
        ]
        if sp is not None:
            lines.append(
                f"  selection profile: quality_weight={sp.quality_weight:g}, "
                f"diversity_weight={sp.diversity_weight:g}"
            )
        lines.append(
            f"  quality score (creation-pool ranking): "
            f"{q:.4g}" if q is not None else "  quality score: undefined"
        )
        if d is not None:
            lines.append(
                "  min behavioral distance to kept frontier: "
                f"{d:.4g} (normalized-vector Euclidean)"
            )
        if combined is not None:
            lines.append(
                f"  combined selection score: {combined:.4g}"
            )
        return lines

    def explain_frontier(self) -> list[str]:
        """Human-readable collapse diagnostics for the final kept beam."""
        d = self.frontier_diagnostics
        if d is None:
            return []
        lines = [
            "FRONTIER COLLAPSE DIAGNOSTICS (final kept beam)",
            f"  candidates in final beam: {d.n_candidates}",
            f"  unique behavioral signatures: {d.n_unique_signatures}",
            f"  mean quality score: {d.mean_quality:.4g}",
            (
                f"  pairwise distance  mean {d.mean_pairwise_distance:.4g} / "
                f"min {d.min_pairwise_distance:.4g} / "
                f"max {d.max_pairwise_distance:.4g} (normalized vectors)"
            ),
            (
                "  -> evidence of behavioral collapse: no spread among the kept "
                "candidates"
                if d.n_unique_signatures <= 1
                else "  -> behaviorally diverse frontier retained"
            ),
        ]
        return lines

    def as_dict(self, *, canonical: bool = False) -> dict[str, Any]:
        """Compact description of the whole search.

        ``canonical=True`` drops the (wall-clock) timing so two runs can be
        compared bit for bit; every identity, order, score, and rank is still
        included.
        """
        data = {
            "search_id": self.search_id,
            "world_id": self.world.id,
            "world_hash": world_hash(self.world),
            "spec": self.spec.to_dict(),
            "root_run_id": self.root.run_id,
            "candidates": [c.as_dict() for c in self.candidates],
            "generations": [g.as_dict() for g in self.generations],
            "final_ranking": self.final_ranking.as_dict(),
            "frontier_diagnostics": (
                self.frontier_diagnostics.as_dict()
                if self.frontier_diagnostics is not None
                else None
            ),
        }
        if not canonical:
            data["timing"] = self.timing.as_dict()
        return data