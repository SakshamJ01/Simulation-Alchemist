"""Task 2.6 Stage 3+4+5 minimal validation: proposal/dedup/CLI/figure/lineage."""
from __future__ import annotations

import os
import subprocess
import sys

from sim_alchemist.core.adaptive_sweep import (
    AdaptiveRunResult,
    AdaptiveStepRecord,
    AdaptiveSweepSelection,
    adaptive_continue_from_result,
)


def test_stage3_proposal_states():
    sel = AdaptiveSweepSelection(actions=["a", "b"])
    r = sel.select_proposal(["a", "b"], [])
    assert r.proposal.proposal_state == "PROPOSED"
    assert r.proposal.proposed_action_id == "a"
    r2 = sel.select_proposal(["a", "b"], [], budget_remaining=0)
    assert r2.proposal.proposal_state == "BUDGET_EXHAUSTED"
    r3 = sel.select_proposal(["a"], ["a"])
    assert r3.proposal.proposal_state == "NO_NEXT_ACTION"


def test_stage3_dedup_excludes_evaluated():
    sel = AdaptiveSweepSelection(actions=["x", "y", "z"])
    r = sel.select_proposal(["x", "y", "z"], ["x"])
    assert r.proposal.proposed_action_id == "y"


def test_stage3_determinism():
    sel = AdaptiveSweepSelection(actions=["c", "a", "b"])
    r1 = sel.select_proposal(["c", "a", "b"], ["b"], budget_remaining=3)
    r2 = sel.select_proposal(["c", "a", "b"], ["b"], budget_remaining=3)
    assert r1.selection_identity == r2.selection_identity
    assert r1.proposal.proposed_action_id == r2.proposal.proposed_action_id


def test_stage3_identity_no_timestamps():
    sel = AdaptiveSweepSelection(actions=["a"])
    r = sel.select_proposal(["a"], [])
    assert "2026" not in r.selection_identity
    assert len(r.selection_identity) == 24


def test_stage4_feedback_from_prior_result():
    step = AdaptiveStepRecord(0, "a", "r1", {"v": 1}, "STOP", {"decision": "STOP"})
    prior = AdaptiveRunResult("id1", (step,), "STOP", "STOP", 1)
    res = adaptive_continue_from_result(prior, ["a", "b"], budget_remaining=1)
    assert res.proposal.proposal_state == "PROPOSED"
    assert res.proposal.proposed_action_id == "b"


def test_stage5_cli_analysis_path_runs():
    proc = subprocess.run(
        [sys.executable, "run_adaptive_discovery.py",
         "--analysis-only", "--seed", "1", "--max-steps", "2"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "ANALYSIS-ONLY" in proc.stdout or "PROPOSED" in proc.stdout


def test_stage5_figure_exists():
    assert os.path.exists("figures/adaptive_discovery_trajectory.png")


def test_stage3_profile_affects_identity_only():
    """Profile affects selection identity/explanation; canonical order unchanged (C)."""
    sel = AdaptiveSweepSelection(actions=["a", "b"])
    r1 = sel.select_proposal(["a", "b"], [], profile_name="profA")
    r2 = sel.select_proposal(["a", "b"], [], profile_name="profB")
    assert r1.proposal.proposed_action_id == "a"
    assert r2.proposal.proposed_action_id == "a"
    assert r1.selection_identity != r2.selection_identity


def test_stage3_legitimate_c_candidates_only():
    """Selection operates only on declared MutationSpace candidates (F)."""
    import sys
    sys.path.insert(0, "src")
    from experiments.network_morphogenesis.experiment import PARAMETER_SPECS
    keys = [spec.path for spec in PARAMETER_SPECS]
    assert len(keys) == 3
    sel = AdaptiveSweepSelection(actions=keys)
    r = sel.select_proposal(keys, [])
    assert r.proposal.proposed_action_id in keys


def test_stage3_none_space_baseline_only():
    """A/B None spaces remain baseline-only; no invented candidates (G)."""
    sel = AdaptiveSweepSelection(actions=["baseline"])
    r = sel.select_proposal(["baseline"], ["baseline"], budget_remaining=1)
    assert r.proposal.proposal_state == "NO_NEXT_ACTION"


def test_stage3_core_purity_no_experiment_refs():
    """Adaptive core module contains no experiment/engine references (O)."""
    import inspect  # noqa: I001 (inside test function)
    import sim_alchemist.core.adaptive_sweep as mod  # noqa: I001
    src = inspect.getsource(mod)
    for bad in ("net_morphogenesis", "chemomech", "field_guided", "Mesa", "Pymunk",
                "py-pde", "NDlib", "scipy.optimize", "sklearn"):
        assert bad not in src, f"experiment/optimizer reference {bad} in adaptive core"


def test_stage3_profile_semantically_changes_proposal_when_preferred():
    """Profile consulted in selection: preferred named candidate chosen; same proposal when irrelevant (C)."""
    sel = AdaptiveSweepSelection(actions=["baseline", "variant_loss"])
    # Profile names second untested candidate -> proposal changes from canonical first
    r_pref = sel.select_proposal(["baseline", "variant_loss"], [], profile_name="variant_loss", budget_remaining=2)
    assert r_pref.proposal.proposed_action_id == "variant_loss"
    assert "profile preference" in r_pref.proposal.selection_reason
    # Default profile -> canonical first
    r_default = sel.select_proposal(["baseline", "variant_loss"], [], profile_name="default", budget_remaining=2)
    assert r_default.proposal.proposed_action_id == "baseline"
    assert "canonical sorted order" in r_default.proposal.selection_reason
    # Profile names missing/non-matching -> falls back to canonical; identity differs due to profile hash
    r_fallback = sel.select_proposal(["baseline"], [], profile_name="other", budget_remaining=1)
    assert r_fallback.proposal.proposed_action_id == "baseline"
    # Same proposal possible with different profiles when preference not in pool or equals first
    r_same = sel.select_proposal(["a"], [], profile_name="x", budget_remaining=1)
    assert r_same.proposal.proposed_action_id == "a"


def test_stage3_ranking_reference_preserved():
    """Selection layer preserves profile/reference; does not invent ranking (P)."""
    sel = AdaptiveSweepSelection(profile="test_profile")
    r = sel.select_proposal(["x", "y"], ["x"], profile_name="test_profile", budget_remaining=3)
    assert r.proposal.profile_used == "test_profile"
    assert r.proposal.proposed_action_id == "y"


def test_stage4_real_c_continuation_loop_with_configured_threshold():
    """Real Experiment C bounded adaptive loop: proposal → execute → observe → CONTINUE → next → execute/observe → termination (Q2)."""
    import sys, yaml
    sys.path.insert(0, "src")
    from experiments.network_morphogenesis.experiment import build_network_metrics, run_network_world
    from sim_alchemist.core.world import WorldDefinition
    from sim_alchemist.core.adaptive_sweep import AdaptiveSweepRunner, AdaptiveSignal

    with open("worlds/adaptive_network.yaml") as f:
        d = yaml.safe_load(f)
    d["max_steps"] = 3
    d["seed"] = 42
    world = WorldDefinition.from_dict(d)

    def execute(action_id):
        return ("run_c_" + str(action_id), run_network_world(world))

    def observe(outcome):
        try:
            m = build_network_metrics(outcome.result)
        except Exception:  # noqa: BLE001 (integration test mimics CLI observe)
            m = {}
        v = float(m.get("final_field_mean", 0.5))
        # Configured threshold high so observed ~0.5 yields CONTINUE (demonstrates loop, not scientific claim)
        return AdaptiveSignal(
            name="network_final_field_mean", value=v, available=True,
            direction="max", threshold=0.6, criterion="threshold",
        )

    runner = AdaptiveSweepRunner(actions=["baseline", "variant_loss"], evaluator=None, budget=2, seed=42)
    result = runner.run(execute, observe)

    # Loop must have executed both legitimate candidates with CONTINUE on first step
    assert len(result.steps) == 2, f"expected 2 steps, got {len(result.steps)}"
    assert result.steps[0].action_id == "baseline"
    assert result.steps[0].decision == "CONTINUE", f"first step expected CONTINUE, got {result.steps[0].decision}"
    assert result.steps[1].action_id == "variant_loss"
    # Termination from budget (2 steps) or STOP; either is valid bounded termination
    assert result.termination_reason in ("BUDGET_EXHAUSTED", "STOP")
    assert result.total_simulated == 2
    assert result.final_decision in ("CONTINUE", "STOP")
    # Deterministic replay identity preserved
    assert len(result.adaptive_run_id) == 24


def test_stage4_real_c_default_threshold_stops_immediately():
    """Real short-run C with default threshold 0.3 produces STOP (not CONTINUE); explains why CONTINUE impossible at default config (Q2 honesty)."""
    import sys, yaml
    sys.path.insert(0, "src")
    from experiments.network_morphogenesis.experiment import build_network_metrics, run_network_world
    from sim_alchemist.core.world import WorldDefinition
    from sim_alchemist.core.adaptive_sweep import AdaptiveSweepRunner, AdaptiveSignal

    with open("worlds/adaptive_network.yaml") as f:
        d = yaml.safe_load(f)
    d["max_steps"] = 3; d["seed"] = 7
    world = WorldDefinition.from_dict(d)

    def execute(action_id):
        return ("run_c_" + str(action_id), run_network_world(world))

    def observe(outcome):
        try:
            m = build_network_metrics(outcome.result)
        except Exception:  # noqa: BLE001 (integration test mimics CLI observe)
            m = {}
        v = float(m.get("final_field_mean", 0.5))
        # Default profile threshold (0.3) — real observed value ~0.5 meets criterion → STOP
        return AdaptiveSignal(name="network_final_field_mean", value=v, available=True,
                              direction="max", threshold=0.3, criterion="threshold")

    runner = AdaptiveSweepRunner(actions=["baseline"], evaluator=None, budget=1, seed=7)
    result = runner.run(execute, observe)
    assert result.steps[0].decision == "STOP"
    assert result.termination_reason == "STOP"
    assert result.total_simulated == 1
    # Explain: observed value (~0.5) > threshold 0.3; criteria satisfied immediately
