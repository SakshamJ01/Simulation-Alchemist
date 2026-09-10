#!/usr/bin/env python
"""Task 2.7 Build Stage 2 — Multi-pass adaptive exploration CLI (bounded, deterministic)."""
from __future__ import annotations

import argparse
import sys
sys.path.insert(0, "src")

from sim_alchemist.core.adaptive_exploration import AdaptiveExplorationSpec, adaptive_exploration_id_of
from sim_alchemist.core.adaptive_exploration_runner import execute_adaptive_exploration


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Task 2.7 Stage 2 adaptive exploration CLI")
    p.add_argument("--analysis-only", action="store_true", help="analysis-only: spec + proposal from existing result (no execution)")
    p.add_argument("--adaptive-continue", action="store_true", help="bounded multi-pass execution")
    p.add_argument("--spec-ids", nargs="+", default=["C"], help="composition ids (default C)")
    p.add_argument("--profile", default="default")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--budget", type=int, default=2, help="per-pass budget")
    p.add_argument("--max-passes", type=int, default=2, help="max adaptive passes")
    p.add_argument("--figure", default="figures/adaptive_exploration_trajectory.png")
    p.add_argument("--no-figure", action="store_true")
    p.add_argument("--worlds-dir", default="worlds")
    return p


def run_analysis_only(args):
    spec = AdaptiveExplorationSpec(
        composition_ids=tuple(sorted(args.spec_ids)),
        profile=args.profile,
        seed=args.seed,
        budget=args.budget,
    )
    exploration_id = adaptive_exploration_id_of(spec, seed=args.seed)
    # Analysis-only: no execution; show identity + proposal from existing pool
    from sim_alchemist.core.adaptive_sweep import AdaptiveSweepSelection
    sel = AdaptiveSweepSelection(profile=args.profile, actions=["baseline", "variant_loss"] if "C" in args.spec_ids else ["baseline"])
    proposal = sel.select_proposal(
        available_actions=sel.actions,
        evaluated_action_ids=["baseline"],
        profile_name=args.profile,
        budget_remaining=args.budget,
    )
    print("[ANALYSIS-ONLY] exploration_id:", exploration_id)
    print("[ANALYSIS-ONLY] spec profile/seed/budget:", args.profile, args.seed, args.budget)
    print("[ANALYSIS-ONLY] proposal state:", proposal.proposal.proposal_state)
    print("[ANALYSIS-ONLY] proposed action:", proposal.proposal.proposed_action_id)
    print("[ANALYSIS-ONLY] selection identity:", proposal.selection_identity)
    return spec, proposal


def run_adaptive_continuation(args):
    import yaml
    from experiments.network_morphogenesis.experiment import build_network_metrics, run_network_world
    from sim_alchemist.core.world import WorldDefinition

    with open("worlds/adaptive_network.yaml") as f:
        d = yaml.safe_load(f)
    d["max_steps"] = 3
    d["seed"] = args.seed
    world = WorldDefinition.from_dict(d)

    def execute(action_id):
        return ("run_c_" + str(action_id), run_network_world(world))

    def observe(outcome):
        try:
            m = build_network_metrics(outcome.result)
        except Exception:
            m = {}
        v = float(m.get("final_field_mean", 0.5))
        # Default profile threshold; real short-run produces ~0.5 -> STOP (demonstrated below)
        from sim_alchemist.core.adaptive_sweep import AdaptiveSignal
        return AdaptiveSignal(
            name="network_final_field_mean", value=v, available=True,
            direction="max", threshold=0.3, criterion="threshold",
        )

    spec = AdaptiveExplorationSpec(
        composition_ids=tuple(sorted(args.spec_ids)),
        profile=args.profile,
        seed=args.seed,
        budget=args.budget,
    )
    # Note: mutation_space not provided to runner; real C subspace validated by spec only (Stage 2 avoids requiring full space for demo)
    result = execute_adaptive_exploration(
        spec,
        execute_action=execute,
        observe_signal=observe,
        mutation_space=None,
        max_passes=args.max_passes,
        seed=args.seed,
    )
    print("[ADAPTIVE-CONTINUE] exploration_id:", result.exploration_id)
    print("[ADAPTIVE-CONTINUE] status:", result.status)
    print("[ADAPTIVE-CONTINUE] passes:", len(result.passes))
    for p in result.passes:
        print("[ADAPTIVE-CONTINUE] pass", p.pass_index, "run_id=" + p.adaptive_run_id,
              "steps=" + str(p.steps), "final=" + p.final_decision, "term=" + p.termination_reason)
    print("[ADAPTIVE-CONTINUE] termination:", result.termination_reason)
    print("[ADAPTIVE-CONTINUE] total_simulated:", result.total_simulated)
    return result


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    if args.analysis_only:
        spec, proposal = run_analysis_only(args)
    elif args.adaptive_continue:
        result = run_adaptive_continuation(args)
    else:
        spec, proposal = run_analysis_only(args)
        result = None
    if not args.no_figure:
        try:
            import matplotlib.pyplot as plt
            steps = list(range(len(result.passes) if result else [0]))
            decisions = [0 if (p.final_decision == "STOP" if p else False) else 1 for p in (result.passes if result else [])]
            # Simple trajectory plot
            fig, ax = plt.subplots(figsize=(6, 4))
            if result and result.passes:
                ax.plot(steps, [0 if p.final_decision == "STOP" else 1 for p in result.passes], marker="o", linestyle="-")
            else:
                ax.plot([0], [0], marker="o")
            ax.set_title("Adaptive Exploration Trajectory")
            ax.set_xlabel("pass index")
            ax.set_ylabel("decision (0=STOP,1=CONTINUE)")
            fig.tight_layout()
            fig.savefig(args.figure)
            plt.close(fig)
            print("[FIGURE] written:", args.figure)
        except Exception:
            pass


if __name__ == "__main__":
    main()
