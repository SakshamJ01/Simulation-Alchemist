#!/usr/bin/env python
"""Task 2.8 — Adaptive Discovery Comparison CLI (analysis-only)."""
from __future__ import annotations
import sys
sys.path.insert(0, "src")

import argparse
from sim_alchemist.core.adaptive_comparison import AdaptiveDiscoveryAnalyst
from sim_alchemist.core.adaptive_exploration import AdaptiveExplorationResult


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--session-ids", nargs="+", default=["2f41779e1947f870b32140e3"])
    p.add_argument("--profile", default="default")
    p.add_argument("--no-figure", action="store_true")
    args = p.parse_args()
    analyst = AdaptiveDiscoveryAnalyst()
    # Analysis-only: synthetic session results from known exploration ids
    synthetic = [
        AdaptiveExplorationResult(
            exploration_id=sid,
            spec_dict={"composition_ids":["C"],"profile":"default","seed":0,"budget":2,"constraints":[]},
            status="VALID",
            eligible_compositions=("C",),
            subspace_size=9,
            explanation="real C bounded demo",
        )
        for sid in args.session_ids
    ]
    result = analyst.compare_adaptive_discovery(synthetic, comparison_profile=args.profile)
    print("[COMPARE] comparison_id:", result.comparison_id)
    print("[COMPARE] profile:", result.profile)
    print("[COMPARE] sessions:", result.source_session_ids)
    print("[COMPARE] ranked:", result.ranked_order)
    print("[COMPARE] frontier:", result.frontend_ids)
    print("[COMPARE] explanation:", result.explanation)


if __name__ == "__main__":
    main()
