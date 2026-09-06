"""Feedback-loop validation tests (Tasks 0.2 / 0.3 checks A-F).

Each test reproduces the exact predicate and thresholds used by
``chemomech.validate`` against the shared experiment trajectories, so the
scientific checks are preserved without recomputing the simulations.
"""

from chemomech.validate import (
    decisions_differ,
    field_correlation,
    mask_drift_count,
    normalized_rmsd,
    wall_net_displacements,
    wall_total_path,
)


def test_baseline_pattern_formation(experiments) -> None:
    """E1 baseline: no walls, no forces -> a patterned morphogen develops."""
    base = experiments["baseline"]
    assert base.final_u.std() > 0.2, "no spatial pattern formed in baseline field"
    assert base.final_u.max() > base.final_u.min(), "field is flat"


def test_static_walls_reproduce_0_2(experiments) -> None:
    """Check A: clamped-obstacle behaviour - fixed walls, blocked cells, pattern."""
    stat, base = experiments["static"], experiments["baseline"]
    a_std = float(stat.final_u.std())
    a_walls = int(stat.walls_per_step[-1])
    a_blocked = int(stat.final_blocked.sum())
    a_rmse = normalized_rmsd(stat.final_u, base.final_u)
    assert a_std > 0.2, f"u std={a_std:.3f}"
    assert a_walls > 0, "no walls deposited"
    assert a_blocked > 0, "no blocked cells"
    assert a_rmse > 0.1, f"static field too close to baseline (RMSD={a_rmse:.3f})"


def test_dynamic_wall_movement(experiments, machine_response) -> None:
    """Check B: pymunk integrates wall motion under body forces."""
    moved_micro, _ = machine_response
    dyn = experiments["dynamic"]
    dyn_disp = wall_net_displacements(dyn)
    n_moved = int(sum(1 for d in dyn_disp.values() if d > 1e-3))
    assert moved_micro > 0.01, f"machine wall moved only {moved_micro:.3f}"
    assert n_moved >= 1, "no dynamic-run wall moved"


def test_geometry_field_coupling(experiments, machine_response) -> None:
    """Check C: the PDE mask tracks wall geometry changes."""
    _, mask_changed = machine_response
    drift = mask_drift_count(experiments["dynamic"])
    assert mask_changed, "machine test: mask did not change after motion"
    assert drift > 0, "dynamic run: blocked cells never changed across steps"


def test_field_divergence_walls_vs_no_walls(experiments) -> None:
    """Check D: dynamic forces change the morphogen field vs static."""
    dyn, stat = experiments["dynamic"], experiments["static"]
    d_rmse = normalized_rmsd(dyn.final_u, stat.final_u)
    d_corr = field_correlation(dyn.final_u, stat.final_u)
    assert d_rmse > 0.1, f"norm RMSD={d_rmse:.3f}"
    assert d_corr < 0.999, f"correlation={d_corr:.4f}"


def test_agent_decision_response(experiments) -> None:
    """Check E: agents feel the difference between dynamic and static runs."""
    dyn, stat = experiments["dynamic"], experiments["static"]
    e_diff = decisions_differ(dyn, stat)
    assert e_diff > 0, "agent decision logs identical between runs"


def test_closed_loop_feedback(experiments) -> None:
    """Check F: motion + mask + field + decisions are all coupled and active."""
    dyn = experiments["dynamic"]
    stat = experiments["static"]
    max_disp = max(wall_net_displacements(dyn).values(), default=0.0)
    drift = mask_drift_count(dyn)
    d_rmse = normalized_rmsd(dyn.final_u, stat.final_u)
    e_diff = decisions_differ(dyn, stat)
    path_sum = wall_total_path(dyn)
    assert max_disp > 1e-3, "no wall net motion"
    assert drift > 0, "no blocked-cell drift"
    assert d_rmse > 0.1, "field did not diverge from static"
    assert e_diff > 0, "agent decisions did not differ"
    assert path_sum > 0, "no cumulative wall motion"