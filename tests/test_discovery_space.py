"""Unit tests for Phase 3 Slice 3.1: Discovery Space & Exploration Orchestration."""

from __future__ import annotations

import pytest

from sim_alchemist.core.sweep import ParameterSweep
from workbench.discovery import (
    MAX_DISCOVERY_CANDIDATES,
    build_mutation_space,
    estimate_discovery_runtime,
    get_experiment_parameter_specs,
    run_bounded_discovery_exploration,
    validate_discovery_space,
)


def test_get_experiment_parameter_specs() -> None:
    """Verify declared ParameterSpecs for supported templates."""
    d_specs = get_experiment_parameter_specs("gated_movers")
    assert "config.gate_threshold" in d_specs
    assert "config.gate_cooldown" in d_specs
    assert "config.source_amplitude" in d_specs
    assert d_specs["config.gate_threshold"].minimum == 0.0
    assert d_specs["config.gate_threshold"].maximum == 1.0

    c_specs = get_experiment_parameter_specs("network_morphogenesis")
    assert "components.network.config.loss" in c_specs
    assert "config.force_fmax" in c_specs

    # Unsupported template raises ValueError
    with pytest.raises(ValueError, match="does not declare parameter specifications"):
        get_experiment_parameter_specs("morphogenesis")


def test_validate_discovery_space_legal() -> None:
    """Verify validation of legal parameter bounds."""
    sweeps = [
        ParameterSweep("config.gate_threshold", (0.25, 0.75)),
        ParameterSweep("config.gate_cooldown", (0, 4)),
    ]
    validated = validate_discovery_space("gated_movers", sweeps)
    assert len(validated) == 2
    assert validated[0].path == "config.gate_threshold"
    assert validated[1].values == (0, 4)


def test_validate_discovery_space_illegal_path() -> None:
    """Verify rejection of unknown parameter paths."""
    sweeps = [ParameterSweep("config.non_existent_param", (1.0, 2.0))]
    with pytest.raises(ValueError, match="Invalid parameter path"):
        validate_discovery_space("gated_movers", sweeps)


def test_validate_discovery_space_out_of_bounds() -> None:
    """Verify rejection of values outside declared physical bounds."""
    # gate_threshold maximum is 1.0
    with pytest.raises(ValueError, match="above legal maximum"):
        validate_discovery_space(
            "gated_movers",
            [ParameterSweep("config.gate_threshold", (0.5, 1.5))],
        )

    # gate_cooldown minimum is 0
    with pytest.raises(ValueError, match="below legal minimum"):
        validate_discovery_space(
            "gated_movers",
            [ParameterSweep("config.gate_cooldown", (-2, 4))],
        )


def test_validate_discovery_space_budget_cap() -> None:
    """Verify rejection of spaces exceeding MAX_DISCOVERY_CANDIDATES (50)."""
    # 8 * 8 = 64 variants > 50 cap
    sweeps = [
        ParameterSweep("config.gate_threshold", tuple(i * 0.1 for i in range(8))),
        ParameterSweep("config.gate_cooldown", tuple(range(8))),
    ]
    with pytest.raises(ValueError, match=f"exceeds maximum allowed cap of {MAX_DISCOVERY_CANDIDATES}"):
        validate_discovery_space("gated_movers", sweeps)


def test_build_mutation_space_defaults() -> None:
    """Verify default MutationSpace loading from repository registrations."""
    d_space = build_mutation_space("gated_movers")
    assert d_space.variant_count == 4

    c_space = build_mutation_space("network_morphogenesis")
    assert c_space.variant_count == 27


def test_estimate_discovery_runtime() -> None:
    """Verify empirical runtime estimation logic."""
    est_4 = estimate_discovery_runtime("gated_movers", 4, 12)
    assert est_4 > 0.0
    # 4 * (0.2 + 0.75 * 12) = 4 * 9.2 = 36.8s
    assert 30.0 < est_4 < 45.0


def test_run_bounded_discovery_exploration_deterministic() -> None:
    """Verify execution of a small bounded discovery pass on Experiment D."""
    # Use 2 variants at 3 macro steps for quick test execution
    sweeps = [
        ParameterSweep("config.gate_threshold", (0.3, 0.8)),
    ]

    result = run_bounded_discovery_exploration(
        "gated_movers",
        sweeps,
        max_steps=3,
        seed=42,
    )

    assert result.experiment_template == "gated_movers"
    assert result.n_planned == 2
    # At least baseline + variants executed
    assert len(result.candidates) >= 2

    # Baseline is first
    baseline = result.candidates[0]
    assert baseline.is_baseline is True
    assert baseline.candidate_id == "cand_0"
    assert baseline.trajectory is not None
    assert "deposition_suppression" in baseline.metrics

    # Check variant properties
    variant = result.candidates[1]
    assert variant.is_baseline is False
    assert variant.candidate_id == "cand_1"
    assert variant.run_id != baseline.run_id
    assert variant.parameters["config.gate_threshold"] in (0.3, 0.8)

    # Determinism check: re-running with same parameters reproduces identical run IDs
    result2 = run_bounded_discovery_exploration(
        "gated_movers",
        sweeps,
        max_steps=3,
        seed=42,
    )
    assert result.sweep_id == result2.sweep_id
    for c1, c2 in zip(result.candidates, result2.candidates):
        assert c1.run_id == c2.run_id
        assert c1.metrics == c2.metrics
