"""Cross-composition ranking + diversity frontier (Task 2.4 Stages 4+5).

Stage 4 consumes a Stage 3 ``CompositionSearchResult`` -- the ordered
``CompositionEvaluation`` snapshots plus the per-composition
``CommonObservableSet`` envelope -- and answers, under an explicit common
profile:

    which executable compositions rank highest, and which compositions form
    the behaviorally diverse frontier?

Everything is analysis-only.  Nothing here executes a world, nothing is
recorded, and nothing mutates the search result: the analysis is a pure,
deterministic projection of data the evaluation pass already produced.

The existing generic machinery is reused unchanged, never rewritten:

* ``rank_by_profile`` (Task 1.8) owns the ranking: pool-level min-max
  normalization per feature, weight/direction scoring, and the per-feature
  contribution explanation;
* ``select_diverse_frontier`` (Task 2.0) owns frontier selection: greedy
  diversity-aware beam selection over normalized behavioral vectors;
* ``behavior_distance`` / ``compute_frontier_diagnostics`` (Task 2.0) own the
  behavioral distance and the frontier diagnostics;
* ``SelectionProfile`` (Task 2.0) owns the quality/diversity weight contract.

The smallest surface introduced by this stage is ``CompositionFeaturedRun``:
it exposes exactly the duck-typed interface ``rank_by_profile`` consumes
(``run_id``, ``kind``, ``features.flatten()``) with feature keys equal to the
common observable names and values equal to the recorded common-observable
values, verbatim.

Only *genuinely common* observables -- available in every evaluated
composition's set -- may enter the ranking or the diversity vectors.  A
profile that references a feature which is not available in every set raises
a clear ``CompositionAnalysisError``; composition identity is never a
distance term.  The raw values are preserved byte-for-byte; normalization is
computed only for ranking and for the diversity vectors, over the whole pool
as a single basis.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.behavior import (
    BehaviorFeatures,
    Contribution,
    FrontierDiagnostics,
    InterestingnessProfile,
    behavior_distance,
    compute_frontier_diagnostics,
    rank_by_profile,
    select_diverse_frontier,
)
from sim_alchemist.core.composition_search import (
    CompositionEvaluation,
    CompositionSearchResult,
)
from sim_alchemist.core.observables import CommonObservableSet
from sim_alchemist.core.search import SelectionProfile

__all__ = [
    "CompositionAnalysisError",
    "CompositionAnalysisResult",
    "CompositionAnalysisTiming",
    "CompositionAnalyst",
    "CompositionFeaturedRun",
    "CompositionFrontier",
    "CompositionFrontierMember",
    "CompositionRankedRow",
    "CompositionRanking",
    "common_observable_vocabulary",
    "composition_analysis_id_of",
    "rank_compositions",
    "select_frontier",
]

_EPS = 1e-12


class CompositionAnalysisError(ValueError):
    """A Stage-4 analysis step could not be built from the search result."""


# ---------------------------------------------------------------------------
# The common-feature pool (genuinely common observables only)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CommonBehaviorFeatures:
    """Duck-typed behavior-feature surface for ``rank_by_profile``.

    ``values`` maps a common observable name to its recorded, verbatim
    value.  ``flatten()`` is the single contract the ranking machinery uses
    to read a featured run; the keys ARE the common observable names.
    """

    values: Mapping[str, float]

    def flatten(self) -> dict[str, float]:
        return dict(self.values)


@dataclass(frozen=True)
class CompositionFeaturedRun:
    """The minimal wrapper that makes a common-observable set rankable.

    Replaces ``FeaturedRun`` for cross-composition ranking while preserving
    its ``CompositionEvaluation`` and ``CommonObservableSet`` sources, so the
    ranked rows can always point back at measured data.
    """

    evaluation: CompositionEvaluation
    observable_set: CommonObservableSet
    features: CommonBehaviorFeatures
    run_id: str
    kind: str = "composition"

    @classmethod
    def from_observable_set(
        cls,
        evaluation: CompositionEvaluation,
        observable_set: CommonObservableSet,
        vocabulary: Sequence[str],
    ) -> CompositionFeaturedRun:
        if evaluation.composition_id != observable_set.composition_id:
            raise CompositionAnalysisError(
                f"evaluation {evaluation.composition_id!r} and observable set "
                f"{observable_set.composition_id!r} are not aligned"
            )
        values: dict[str, float] = {}
        for name in vocabulary:
            row = observable_set.observable(name)
            if row is None or not row.available:
                raise CompositionAnalysisError(
                    f"common observable {name!r} is not available for "
                    f"composition {evaluation.composition_id!r}"
                )
            values[name] = row.value if row.value is not None else 0.0
        return cls(
            evaluation=evaluation,
            observable_set=observable_set,
            features=CommonBehaviorFeatures(values=values),
            run_id=evaluation.run_id,
        )


def common_observable_vocabulary(
    result: CompositionSearchResult,
) -> tuple[str, ...]:
    """The sorted names available in *every* evaluated composition's set.

    An empty pool yields the empty vocabulary.  This is the only vocabulary
    the ranking and the diversity vectors may use.
    """
    if not isinstance(result, CompositionSearchResult):
        raise TypeError(
            "result must be a CompositionSearchResult, got "
            f"{type(result).__name__}"
        )
    if not result.evaluations:
        return ()
    if not result.observable_sets:
        raise CompositionAnalysisError(
            "the search result carries no common-observable envelope for its "
            "evaluations; Stage 3 extraction must run first"
        )
    if len(result.observable_sets) != len(result.evaluations):
        raise CompositionAnalysisError(
            "the search result has "
            f"{len(result.observable_sets)} observable sets for "
            f"{len(result.evaluations)} evaluations"
        )
    names = set(result.observable_sets[0].available_names)
    for observable in result.observable_sets[1:]:
        names &= set(observable.available_names)
    return tuple(sorted(names))


def _featured_runs(
    result: CompositionSearchResult,
    vocabulary: Sequence[str],
) -> tuple[CompositionFeaturedRun, ...]:
    runs: list[CompositionFeaturedRun] = []
    for evaluation, observable_set in zip(
        result.evaluations, result.observable_sets
    ):
        runs.append(
            CompositionFeaturedRun.from_observable_set(
                evaluation, observable_set, vocabulary
            )
        )
    return tuple(runs)


# ---------------------------------------------------------------------------
# Cross-composition ranking (reuses rank_by_profile exactly)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CompositionRankedRow:
    """One ranked composition with its measured-data explanation.

    ``raw`` is the verbatim common-observable value of each scored feature;
    ``normalized`` is its pool-level min-max value (both ``None`` when the
    value is genuinely undefined).  ``contributions`` reuses the Task 1.8
    ``Contribution`` records.
    """

    rank: int
    composition_id: str
    shape_id: str
    run_id: str
    world_hash: str
    world_id: str
    status: str
    score: float
    raw: Mapping[str, float | None] = field(default_factory=dict)
    normalized: Mapping[str, float | None] = field(default_factory=dict)
    contributions: Mapping[str, Contribution] = field(default_factory=dict)
    explanation: tuple[str, ...] = ()
    evaluation: CompositionEvaluation | None = None
    observable_set: CommonObservableSet | None = None

    def contribution(self, feature: str) -> Contribution | None:
        return self.contributions.get(feature)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "composition_id": self.composition_id,
            "shape_id": self.shape_id,
            "run_id": self.run_id,
            "world_hash": self.world_hash,
            "world_id": self.world_id,
            "status": self.status,
            "score": self.score,
            "raw": dict(self.raw),
            "normalized": dict(self.normalized),
            "contributions": {
                key: contribution.as_dict()
                for key, contribution in self.contributions.items()
            },
            "explanation": list(self.explanation),
        }


@dataclass(frozen=True)
class CompositionRanking:
    """The ordered composition ranking for one explicit profile."""

    profile: InterestingnessProfile
    vocabulary: tuple[str, ...]
    rows: tuple[CompositionRankedRow, ...]

    def ranked_ids(self) -> list[str]:
        return [row.composition_id for row in self.rows]

    def row(self, composition_id: str) -> CompositionRankedRow | None:
        return next(
            (row for row in self.rows if row.composition_id == composition_id),
            None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.as_dict(),
            "vocabulary": list(self.vocabulary),
            "rows": [row.as_dict() for row in self.rows],
        }


def _validate_profile_features(
    profile: InterestingnessProfile,
    vocabulary: Sequence[str],
) -> None:
    invalid: list[tuple[str, str]] = []
    for key in profile.weights:
        if not isinstance(key, str):
            raise CompositionAnalysisError(
                f"profile feature keys must be str, got {type(key).__name__}"
            )
        if key not in vocabulary:
            invalid.append((key, "not a common observable"))
    for key, reason in invalid:
        raise CompositionAnalysisError(
            f"profile {profile.name!r} references {key!r}, which is {reason}; "
            "only observables available in every evaluated composition may "
            f"enter cross-composition ranking.  Common observables: "
            f"{', '.join(vocabulary) or '(none)'}"
        )


def _explanation(
    row: CompositionRankedRow,
    profile: InterestingnessProfile,
) -> tuple[str, ...]:
    ordered = sorted(
        row.contributions.values(),
        key=lambda c: (abs(c.contribution), c.feature),
        reverse=True,
    )
    lines = [
        (
            f"rank {row.rank} composition {row.composition_id} "
            f"score {row.score:.4g}"
        )
    ]
    for c in ordered:
        direction = "max" if profile.direction(c.feature) else "min"
        if c.normalized is None:
            lines.append(
                f"  {c.feature}: undefined (not scored), weight {c.weight:g}"
            )
            continue
        lines.append(
            f"  {c.feature}: raw {c.raw:g}, norm {c.normalized:g}, "
            f"direction {direction}, weight {c.weight:g} "
            f"-> contribution {c.contribution:+.4g}"
        )
    return tuple(lines)


def rank_compositions(
    result: CompositionSearchResult,
    profile: InterestingnessProfile,
) -> CompositionRanking:
    """Rank every evaluated composition under ``profile``.

    Raw common-observable values are normalized (min-max) across the pool per
    feature; each contribution is ``weight * directional`` where
    ``directional`` is the normalized value (maximized) or ``1 - normalized``
    (minimized).  Undefined features score zero and are explained as such.
    Both formulas are the documented Task 1.8 contract, reused verbatim.
    """
    if not isinstance(profile, InterestingnessProfile):
        raise TypeError(
            f"profile must be an InterestingnessProfile, got "
            f"{type(profile).__name__}"
        )
    vocabulary = common_observable_vocabulary(result)
    if vocabulary:
        _validate_profile_features(profile, vocabulary)
    runs = _featured_runs(result, vocabulary)
    ranked = rank_by_profile(runs, profile)  # type: ignore[arg-type]

    run_map = {run.run_id: run for run in runs}
    built: list[CompositionRankedRow] = []
    for behavior_row in ranked.rows:
        run = run_map[behavior_row.run_id]
        built.append(
            CompositionRankedRow(
                rank=behavior_row.rank,
                composition_id=run.evaluation.composition_id,
                shape_id=run.evaluation.shape_id,
                run_id=behavior_row.run_id,
                world_hash=run.evaluation.world_hash,
                world_id=run.evaluation.world_id,
                status=run.evaluation.status,
                score=behavior_row.score,
                raw={
                    key: behavior_row.raw_features.get(key)
                    for key in behavior_row.contributions
                },
                normalized={
                    key: contribution.normalized
                    for key, contribution in behavior_row.contributions.items()
                },
                contributions=behavior_row.contributions,
                evaluation=run.evaluation,
                observable_set=run.observable_set,
            )
        )
    rows = tuple(
        _replace_row(row, _explanation(row, profile)) for row in built
    )
    return CompositionRanking(
        profile=profile,
        vocabulary=vocabulary,
        rows=rows,
    )


def _replace_row(
    row: CompositionRankedRow, explanation: tuple[str, ...]
) -> CompositionRankedRow:
    return CompositionRankedRow(
        rank=row.rank,
        composition_id=row.composition_id,
        shape_id=row.shape_id,
        run_id=row.run_id,
        world_hash=row.world_hash,
        world_id=row.world_id,
        status=row.status,
        score=row.score,
        raw=row.raw,
        normalized=row.normalized,
        contributions=row.contributions,
        explanation=explanation,
        evaluation=row.evaluation,
        observable_set=row.observable_set,
    )


# ---------------------------------------------------------------------------
# Diversity vector + frontier (reuses Task 2.0 machinery exactly)
# ---------------------------------------------------------------------------
def _min_max_vectors(
    vectors: Sequence[Mapping[str, float]],
) -> list[dict[str, float]]:
    """Pool-level min-max normalization of the diversity feature vectors.

    The formula is the documented Task 1.8/2.0 rule: per feature,
    ``(value - min) / (max - min)`` across the whole pool; a constant
    (zero-range) feature normalizes to ``0.0`` for every candidate.
    """
    if not vectors:
        return []
    keys = sorted({key for vector in vectors for key in vector})
    key_lo: dict[str, float] = {}
    key_hi: dict[str, float] = {}
    for key in keys:
        values = [vector[key] for vector in vectors if key in vector]
        key_lo[key] = min(values)
        key_hi[key] = max(values)
    out: list[dict[str, float]] = []
    for vector in vectors:
        norm: dict[str, float] = {}
        for key in keys:
            if key not in vector:
                norm[key] = 0.0
                continue
            lo, hi = key_lo[key], key_hi[key]
            if hi - lo <= _EPS:
                norm[key] = 0.0
            else:
                norm[key] = (vector[key] - lo) / (hi - lo)
        out.append(norm)
    return out


def _pool_isolation(
    vectors: Sequence[Mapping[str, float]],
) -> list[float]:
    """Min normalized Euclidean distance from each candidate to any other.

    Uses ``behavior_distance`` unchanged over the pool-level normalized
    common-feature vectors; an isolated composition (no behaviorally similar
    peer) has a high value.  ``0.0`` when the pool has fewer than two
    candidates.
    """
    normalized = _min_max_vectors(vectors)
    isolation: list[float] = []
    for i, vector in enumerate(normalized):
        if len(normalized) < 2:
            isolation.append(0.0)
            continue
        isolation.append(
            min(
                behavior_distance(
                    BehaviorFeatures(units={}),
                    BehaviorFeatures(units={}),
                    vector_a=vector,
                    vector_b=other,
                )
                for j, other in enumerate(normalized)
                if j != i
            )
        )
    return isolation


@dataclass(frozen=True)
class CompositionFrontierMember:
    """One composition selected into the diversity-aware frontier."""

    composition_id: str
    run_id: str
    rank: int
    quality_score: float
    diversity_score: float
    combined_score: float
    selection_reason: str
    evaluation: CompositionEvaluation | None = None
    observable_set: CommonObservableSet | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "run_id": self.run_id,
            "rank": self.rank,
            "quality_score": self.quality_score,
            "diversity_score": self.diversity_score,
            "combined_score": self.combined_score,
            "selection_reason": self.selection_reason,
        }


@dataclass(frozen=True)
class CompositionFrontier:
    """The selected frontier, its diagnostics, and per-candidate diversity.

    ``isolation`` maps every evaluated ``composition_id`` to its minimum
    normalized behavioral distance to any other evaluated composition -- the
    value drawn by the Stage 5 view.  ``members`` are the selected frontier
    in selection order; ``diagnostics`` summarizes their pool.
    """

    profile: InterestingnessProfile
    selection: SelectionProfile
    beam_width: int
    vocabulary: tuple[str, ...]
    members: tuple[CompositionFrontierMember, ...]
    diagnostics: FrontierDiagnostics
    isolation: Mapping[str, float]

    def member_ids(self) -> list[str]:
        return [member.composition_id for member in self.members]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.as_dict(),
            "selection": self.selection.as_dict(),
            "beam_width": self.beam_width,
            "vocabulary": list(self.vocabulary),
            "members": [member.as_dict() for member in self.members],
            "diagnostics": self.diagnostics.as_dict(),
            "isolation": dict(self.isolation),
        }


def select_frontier(
    result: CompositionSearchResult,
    profile: InterestingnessProfile,
    *,
    ranking: CompositionRanking | None = None,
    quality_weight: float = 1.0,
    diversity_weight: float = 1.0,
    beam_width: int | None = None,
) -> CompositionFrontier:
    """Select the diversity-aware frontier over the evaluated pool.

    Quality scores are the profile's ranking scores; the behavioral vectors
    are the common-observable values.  Selection reuses
    ``select_diverse_frontier`` unchanged: the highest-quality composition
    anchors the frontier, and each further slot greedily maximizes
    ``quality_weight * quality + diversity_weight * min distance to the
    selected frontier`` over normalized vectors.  ``beam_width`` defaults to
    the whole pool.
    """
    selection = SelectionProfile(
        quality_weight=quality_weight, diversity_weight=diversity_weight
    )
    if ranking is None:
        ranking = rank_compositions(result, profile)
    vocabulary = ranking.vocabulary
    if not ranking.rows:
        diagnostics = compute_frontier_diagnostics([], [])
        return CompositionFrontier(
            profile=profile,
            selection=selection,
            beam_width=beam_width if beam_width is not None else 0,
            vocabulary=vocabulary,
            members=(),
            diagnostics=diagnostics,
            isolation={},
        )
    width = beam_width if beam_width is not None else len(ranking.rows)
    run_ids: list[str] = []
    scores: list[float] = []
    vectors: list[dict[str, float]] = []
    vector_by_run: dict[str, dict[str, float]] = {}
    for row in ranking.rows:
        run_ids.append(row.run_id)
        scores.append(row.score)
        values = {key: value for key, value in row.raw.items() if value is not None}
        vectors.append(values)
        vector_by_run[row.run_id] = values
    selected = select_diverse_frontier(
        list(zip(run_ids, scores, vectors)),
        width,
        selection.quality_weight,
        selection.diversity_weight,
    )
    members: list[CompositionFrontierMember] = []
    rank_by_run = {row.run_id: row.rank for row in ranking.rows}
    for run_id, quality, div, combined, _min_distance, reason in selected:
        row = next(r for r in ranking.rows if r.run_id == run_id)
        members.append(
            CompositionFrontierMember(
                composition_id=row.composition_id,
                run_id=run_id,
                rank=rank_by_run[run_id],
                quality_score=quality,
                diversity_score=div,
                combined_score=combined,
                selection_reason=reason,
                evaluation=row.evaluation,
                observable_set=row.observable_set,
            )
        )
    isolation = dict(
        zip(
            [row.composition_id for row in ranking.rows],
            _pool_isolation(vectors),
        )
    )
    diagnostics = compute_frontier_diagnostics(
        [member.quality_score for member in members],
        [vector_by_run[member.run_id] for member in members],
    )
    return CompositionFrontier(
        profile=profile,
        selection=selection,
        beam_width=width,
        vocabulary=vocabulary,
        members=tuple(members),
        diagnostics=diagnostics,
        isolation=isolation,
    )


# ---------------------------------------------------------------------------
# Identity + timed orchestration
# ---------------------------------------------------------------------------
def composition_analysis_id_of(
    discovery_id: str,
    profile: InterestingnessProfile,
    *,
    quality_weight: float = 1.0,
    diversity_weight: float = 1.0,
    beam_width: int | None = None,
) -> str:
    """Deterministic 24-hex identity of one Stage-4 analysis pass.

    Content-addressed over the discovery id, the explicit profile, and the
    frontier-selection configuration; no transient runtime data.
    """
    payload = json.dumps(
        {
            "discovery_id": discovery_id,
            "profile": profile.as_dict(),
            "quality_weight": quality_weight,
            "diversity_weight": diversity_weight,
            "beam_width": beam_width,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class CompositionAnalysisTiming:
    """Wall-clock split of one analysis (extraction/ranking/frontier)."""

    extraction_seconds: float
    ranking_seconds: float
    frontier_seconds: float
    total_seconds: float

    def as_dict(self) -> dict[str, float]:
        return {
            "extraction_seconds": self.extraction_seconds,
            "ranking_seconds": self.ranking_seconds,
            "frontier_seconds": self.frontier_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True)
class CompositionAnalysisResult:
    """The outcome of analyzing one search result under one profile.

    Canonical serialization excludes the timing (wall-clock never participates
    in a deterministic replay comparison).
    """

    analysis_id: str
    discovery_id: str
    profile: InterestingnessProfile
    vocabulary: tuple[str, ...]
    ranking: CompositionRanking
    frontier: CompositionFrontier
    timing: CompositionAnalysisTiming

    def ranked_ids(self) -> list[str]:
        return self.ranking.ranked_ids()

    def frontier_ids(self) -> list[str]:
        return self.frontier.member_ids()

    def as_dict(self, *, canonical: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "analysis_id": self.analysis_id,
            "discovery_id": self.discovery_id,
            "profile": self.profile.as_dict(),
            "vocabulary": list(self.vocabulary),
            "ranking": self.ranking.as_dict(),
            "frontier": self.frontier.as_dict(),
        }
        if not canonical:
            data["timing"] = self.timing.as_dict()
        return data


class CompositionAnalyst:
    """Analysis-only orchestrator over one ``CompositionSearchResult``.

    Holds no world-execution state and records nothing: it consumes an
    already-evaluated search result and computes ranking + frontier per
    explicit profile.  Repeated calls with the same result + profile +
    selection configuration are deterministic and never evaluate a world.
    """

    def analyze(
        self,
        result: CompositionSearchResult,
        profile: InterestingnessProfile,
        *,
        quality_weight: float = 1.0,
        diversity_weight: float = 1.0,
        beam_width: int | None = None,
        analysis_id: str | None = None,
    ) -> CompositionAnalysisResult:
        if not isinstance(result, CompositionSearchResult):
            raise TypeError(
                f"result must be a CompositionSearchResult, got "
                f"{type(result).__name__}"
            )
        if analysis_id is None:
            analysis_id = composition_analysis_id_of(
                result.discovery_id,
                profile,
                quality_weight=quality_weight,
                diversity_weight=diversity_weight,
                beam_width=beam_width,
            )
        start = time.monotonic()
        extraction_start = time.monotonic()
        vocabulary = common_observable_vocabulary(result)
        runs = _featured_runs(result, vocabulary)
        extraction_seconds = time.monotonic() - extraction_start

        ranking_start = time.monotonic()
        ranking = rank_compositions(result, profile)
        ranking_seconds = time.monotonic() - ranking_start

        frontier_start = time.monotonic()
        frontier = select_frontier(
            result,
            profile,
            ranking=ranking,
            quality_weight=quality_weight,
            diversity_weight=diversity_weight,
            beam_width=beam_width,
        )
        frontier_seconds = time.monotonic() - frontier_start
        total_seconds = time.monotonic() - start
        del runs
        return CompositionAnalysisResult(
            analysis_id=analysis_id,
            discovery_id=result.discovery_id,
            profile=profile,
            vocabulary=vocabulary,
            ranking=ranking,
            frontier=frontier,
            timing=CompositionAnalysisTiming(
                extraction_seconds=extraction_seconds,
                ranking_seconds=ranking_seconds,
                frontier_seconds=frontier_seconds,
                total_seconds=total_seconds,
            ),
        )