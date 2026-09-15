"""Task 3.0 Stage 2: scientific execution and validation for Experiment D."""
from __future__ import annotations

from typing import Any

import numpy as np

from experiments.catalog import build_repository_catalog, repository_executors
from experiments.gated_movers.model import GatedMoversTrajectory
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

EXPECTED_METRICS = {
    "final_field_mean",
    "final_field_std",
    "field_entropy",
    "n_movers",
    "total_displacement",
    "mean_speed",
    "mean_force",
    "mean_gradient",
    "deposition_events",
    "deposition_suppression",
    "active_gates",
    "gate_switch_rate",
}


def _short_world(*, gate_threshold: float = 0.5, steps: int = 12) -> WorldDefinition:
    catalog = build_repository_catalog(generate_worlds=True)
    candidate = next(row for row in catalog.executable() if row.template == "gated_movers")
    assert candidate.generated_world is not None
    data = candidate.generated_world.as_dict()
    data["max_steps"] = steps
    data["config"]["n_steps"] = steps
    data["config"]["gate_threshold"] = gate_threshold
    for component in data["components"]:
        component_config = component["config"]
        if component["id"] == "pymunk":
            component_config["n_steps"] = steps
            component_config["gate_threshold"] = gate_threshold
    return WorldDefinition.from_dict(data)


def _run(world: WorldDefinition) -> ExecOutcome:
    catalog = build_repository_catalog(generate_worlds=True)
    candidate = next(row for row in catalog.executable() if row.template == "gated_movers")
    assert candidate.composition_id is not None
    executor = repository_executors()[candidate.composition_id]
    return executor(world)


def _trajectory_arrays(trajectory: GatedMoversTrajectory) -> tuple[Any, ...]:
    return (
        np.asarray(trajectory.t_field),
        *(np.asarray(snapshot) for snapshot in trajectory.u_snaps),
        np.asarray(trajectory.speeds),
        np.asarray(trajectory.force_mags),
        np.asarray(trajectory.gradient_mags),
        np.asarray(trajectory.active_gates),
        np.asarray(trajectory.suppressed_gates),
        np.asarray(trajectory.gate_switches),
        np.asarray(trajectory.gate_deposits),
    )


def test_stage2_short_baseline_has_complete_metrics_and_series() -> None:
    outcome = _run(_short_world())
    assert set(outcome.metrics) == EXPECTED_METRICS
    trajectory = outcome.trajectory
    assert isinstance(trajectory, GatedMoversTrajectory)
    n_steps = len(trajectory.t_field)
    assert n_steps == 12
    for series in (
        trajectory.u_snaps,
        trajectory.speeds,
        trajectory.force_mags,
        trajectory.gradient_mags,
        trajectory.active_gates,
        trajectory.suppressed_gates,
        trajectory.gate_switches,
        trajectory.gate_deposits,
    ):
        assert len(series) == n_steps


def test_stage2_gating_on_differs_from_gating_off() -> None:
    on = _run(_short_world(gate_threshold=0.5))
    off = _run(_short_world(gate_threshold=0.0))
    on_trajectory = on.trajectory
    off_trajectory = off.trajectory
    assert isinstance(on_trajectory, GatedMoversTrajectory)
    assert isinstance(off_trajectory, GatedMoversTrajectory)
    assert min(float(np.min(snapshot)) for snapshot in off_trajectory.u_snaps) >= 0.0
    assert off.metrics["deposition_suppression"] == 0.0
    assert off.metrics["active_gates"] == off.metrics["n_movers"]
    assert on.metrics["deposition_suppression"] > 0.0
    assert on.metrics != off.metrics
    assert any(
        not np.array_equal(left, right)
        for left, right in zip(_trajectory_arrays(on_trajectory), _trajectory_arrays(off_trajectory))
    )


def test_stage2_runs_are_bounded_and_finite() -> None:
    outcome = _run(_short_world())
    trajectory = outcome.trajectory
    assert isinstance(trajectory, GatedMoversTrajectory)
    assert all(np.isfinite(snapshot).all() for snapshot in trajectory.u_snaps)
    assert all(np.isfinite(value) for value in trajectory.speeds)
    assert all(np.isfinite(value) for value in trajectory.force_mags)
    assert all(np.isfinite(value) for value in trajectory.gradient_mags)
    for positions in trajectory.positions.values():
        for x, y in positions:
            assert 0.0 <= x <= 1.0
            assert 0.0 <= y <= 1.0
    assert all(0 <= value <= trajectory.n_movers for value in trajectory.active_gates)
    assert all(0 <= value <= trajectory.n_movers for value in trajectory.suppressed_gates)


def test_stage2_replay_is_bitwise_identical() -> None:
    world = _short_world()
    first = _run(world)
    second = _run(world)
    assert first.metrics == second.metrics
    assert isinstance(first.trajectory, GatedMoversTrajectory)
    assert isinstance(second.trajectory, GatedMoversTrajectory)
    for left, right in zip(_trajectory_arrays(first.trajectory), _trajectory_arrays(second.trajectory)):
        np.testing.assert_array_equal(left, right)
    assert first.trajectory.positions == second.trajectory.positions
