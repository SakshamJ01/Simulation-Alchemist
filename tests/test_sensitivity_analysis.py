"""Unit tests for global parameter sensitivity analysis (Phase 4H)."""

import pytest

from sim_alchemist.core.sensitivity import (
    MorrisSensitivityAnalyzer,
    ParameterRange,
    SensitivitySpec,
)


def test_sensitivity_spec_validation():
    with pytest.raises(ValueError, match="must be < max_val"):
        ParameterRange(name="p1", min_val=5.0, max_val=2.0)

    with pytest.raises(ValueError, match="requires at least one"):
        SensitivitySpec(parameters=[])

    with pytest.raises(ValueError, match="must be at least 2"):
        SensitivitySpec(parameters=[ParameterRange("p", 0.0, 1.0)], n_trajectories=1)


def test_morris_sensitivity_linear_function():
    # Linear function: y = 10 * x1 + 0.1 * x2
    # x1 should be identified as vastly more influential than x2
    def linear_model(params: dict[str, float]) -> float:
        return 10.0 * params["x1"] + 0.1 * params["x2"]

    spec = SensitivitySpec(
        parameters=[
            ParameterRange("x1", min_val=0.0, max_val=1.0),
            ParameterRange("x2", min_val=0.0, max_val=1.0),
        ],
        target_metric="linear_output",
        n_trajectories=10,
        seed=42,
    )

    result = MorrisSensitivityAnalyzer.analyze(linear_model, spec)

    assert result.target_metric == "linear_output"
    assert len(result.effects) == 2
    assert result.most_influential_parameter == "x1"
    assert result.effects[0].name == "x1"
    assert result.effects[0].rank == 1
    assert result.effects[1].name == "x2"
    assert result.effects[1].rank == 2

    # x1 mu_star should be ~10.0, x2 mu_star should be ~0.1
    assert result.effects[0].mu_star > result.effects[1].mu_star * 20.0
    assert result.total_evaluations == 10 * (2 + 1)

    d = result.as_dict()
    assert d["most_influential_parameter"] == "x1"
    assert "x1" in d["variance_indices"]


def test_morris_sensitivity_non_linear_interaction():
    # Non-linear function with interaction: y = x1 * x2 + x3^2
    def nonlinear_model(params: dict[str, float]) -> float:
        return params["x1"] * params["x2"] + (params["x3"] ** 2)

    spec = SensitivitySpec(
        parameters=[
            ParameterRange("x1", min_val=0.0, max_val=5.0),
            ParameterRange("x2", min_val=0.0, max_val=5.0),
            ParameterRange("x3", min_val=0.0, max_val=5.0),
        ],
        target_metric="nonlinear_output",
        n_trajectories=12,
        seed=123,
    )

    result = MorrisSensitivityAnalyzer.analyze(nonlinear_model, spec)
    assert len(result.effects) == 3
    # Non-linear / interacting parameters should have non-zero sigma
    for effect in result.effects:
        assert effect.mu_star > 0.0
