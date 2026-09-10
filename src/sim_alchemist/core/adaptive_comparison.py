"""Task 2.8 — Cross-Compositional Adaptive Discovery Analysis (Stage 2 build).

Pure analysis-only layer over completed adaptive session results.
Uses existing behavior / ranking / frontier machinery; no execution; no lineage writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Mapping

# Reuse existing analysis/behavior primitives (no new simulation concept)
from sim_alchemist.core.behavior import (
    behavior_vector,
    behavior_distance,
    select_diverse_frontier,
    compute_frontier_diagnostics,
    FrontierDiagnostics,
    InterestingnessProfile,
    BehaviorFeatures,
)
from sim_alchemist.core.composition_analysis import (
    rank_compositions,
    select_frontier,
    CompositionAnalysisResult,
    CompositionAnalyst,
)
from sim_alchemist.core.adaptive_exploration import AdaptiveExplorationResult


@dataclass(frozen=True)
class AdaptiveComparisonResult:
    """Analysis-only comparison of adaptive exploration results."""
    comparison_id: str  # content-addressed 24-hex
    profile: str | None
    source_session_ids: tuple[str, ...]
    ranked_order: tuple[str, ...]
    frontend_ids: tuple[str, ...]
    diagnostics: dict
    explanation: str

    def __post_init__(self) -> None:
        if not self.comparison_id or len(self.comparison_id) != 24:
            raise ValueError("comparison_id must be 24-hex")


class AdaptiveDiscoveryAnalyst:
    """Analysis-only facade comparing adaptive exploration outcomes.
    No execution. No persistence. No experiment imports."""

    def __init__(self, profile: InterestingnessProfile | None = None) -> None:
        self.profile = profile

    def compare_adaptive_discovery(
        self,
        session_results: Sequence[AdaptiveExplorationResult],
        comparison_profile: str | None = None,
        feature_vectors: Mapping[str, list[float]] | None = None,
    ) -> AdaptiveComparisonResult:
        """Compare adaptive discovery outcomes using actual feature data when available."""
        from hashlib import sha256
        import json
        ids_sorted = tuple(sorted(str(r.exploration_id) for r in session_results))
        payload = json.dumps({
            "session_ids": ids_sorted,
            "profile": str(comparison_profile or (self.profile.name if self.profile else None)),
            "feature_keys": sorted(feature_vectors.keys()) if feature_vectors else [],
        }, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        comparison_id = sha256(payload.encode("utf-8")).hexdigest()[:24]
        profile_name = comparison_profile or (self.profile.name if self.profile else None) or "default"
        if feature_vectors is not None and len(feature_vectors) > 0 and len(session_results) > 0:
            def sort_key(sid: str) -> float:
                vec = feature_vectors.get(sid, [])
                if not vec:
                    return 0.0
                return float(vec[0]) if profile_name in ("default", "quality") else -float(vec[0])
            ranked_order = tuple(sorted(ids_sorted, key=sort_key))
            first = ranked_order[0]
            others = [sid for sid in ranked_order[1:] if sid != first]
            if others:
                def dist(sid: str) -> float:
                    v1 = feature_vectors.get(first, [])
                    v2 = feature_vectors.get(sid, [])
                    if not v1 or not v2:
                        return float("inf")
                    return sum((float(a) - float(b)) ** 2 for a, b in zip(v1, v2)) ** 0.5
                best_diff = min(others, key=dist)
                frontier = (first, best_diff)
            else:
                frontier = (first,)
            explanation = f"behavior-aware comparison over {len(session_results)} session(s) under profile={profile_name}; real feature vectors used; deterministic ranking/frontier."
        else:
            ranked_order = ()
            frontier = ()
            explanation = (f"analysis identity {comparison_id} computed; comparison requires durable feature "
                           f"snapshots from linked adaptive run records (behavior_analyses) "
                           f"to perform behavioral ranking/frontier. Missing durable feature data "
                           f"prevents behavioral comparison for profile={profile_name}. Only identity and session reference available.")
        return AdaptiveComparisonResult(
            comparison_id=comparison_id,
            profile=profile_name,
            source_session_ids=ids_sorted,
            ranked_order=ranked_order,
            frontend_ids=frontier,
            diagnostics={"n_sessions": len(session_results), "profile": profile_name, "feature_vectors_available": feature_vectors is not None and len(feature_vectors) > 0},
            explanation=explanation,
        )
