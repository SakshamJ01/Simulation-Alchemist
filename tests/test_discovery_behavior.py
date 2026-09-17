"""Unit tests for Phase 3 Slice 3.2: Behavioral Feature Extraction & Observables."""

from __future__ import annotations

import numpy as np

from sim_alchemist.core.behavior import BehaviorAnalyzer, ObservableSeries
from sim_alchemist.core.sweep import ParameterSweep
from workbench.discovery import (
    extract_candidate_observables,
    run_bounded_discovery_exploration,
)


def test_extract_candidate_observables_gated_movers() -> None:
    """Verify scalar ObservableSeries extraction from real GatedMoversTrajectory."""
    exploration = run_bounded_discovery_exploration(
        "gated_movers",
        [ParameterSweep("config.gate_threshold", (0.3, 0.7))],
        max_steps=3,
        seed=42,
        retain_all_trajectories=True,
    )

    baseline_cand = exploration.candidates[0]
    assert baseline_cand.trajectory is not None

    obs = extract_candidate_observables("gated_movers", baseline_cand.trajectory)
    assert "speed" in obs
    assert "force" in obs
    assert "gradient" in obs
    assert "field_mean" in obs
    assert "field_std" in obs
    assert "active_gates" in obs
    assert "suppressed_gates" in obs

    # Verify times and values contract
    speed_series = obs["speed"]
    assert isinstance(speed_series, ObservableSeries)
    assert len(speed_series.times) == 3
    assert len(speed_series.values) == 3
    for t in speed_series.times:
        assert np.isfinite(t)
    for v in speed_series.values:
        assert np.isfinite(v)


def test_extract_candidate_observables_empty() -> None:
    """Verify safe handling of None or empty trajectories."""
    obs = extract_candidate_observables("gated_movers", None)
    assert obs == {}


def test_behavior_features_18_features_extraction() -> None:
    """Verify that BehaviorAnalyzer produces full 18-feature vectors per observable."""
    exploration = run_bounded_discovery_exploration(
        "gated_movers",
        [ParameterSweep("config.gate_threshold", (0.3, 0.7))],
        max_steps=3,
        seed=42,
        retain_all_trajectories=True,
    )

    base_cand = exploration.candidates[0]
    var_cand = exploration.candidates[1]

    base_obs = extract_candidate_observables("gated_movers", base_cand.trajectory)
    var_obs = extract_candidate_observables("gated_movers", var_cand.trajectory)

    analyzer = BehaviorAnalyzer()
    base_feats = analyzer.features(base_obs, baseline=None)
    var_feats = analyzer.features(var_obs, baseline=base_obs)

    # Check units exist
    assert "speed" in base_feats.units
    assert "field_std" in base_feats.units

    unit = var_feats.units["speed"]
    # 1. Temporal (5 features)
    assert "mean" in unit.temporal
    assert "std" in unit.temporal
    assert "range" in unit.temporal
    assert "total_variation" in unit.temporal
    assert "activity_rate" in unit.temporal

    # 2. Trend (3 features)
    assert "trend_slope" in unit.trend
    assert "residual_variance_fraction" in unit.trend
    assert "lag1_autocorr" in unit.trend

    # 3. Oscillation (3 features)
    assert "sign_change_rate" in unit.oscillation
    assert "oscillation_persistence" in unit.oscillation
    assert "oscillation_strength" in unit.oscillation

    # 4. Stability (4 features)
    assert "late_window_std" in unit.stability
    assert "late_window_slope" in unit.stability
    assert "late_vs_full_variance_ratio" in unit.stability
    assert "early_vs_late_divergence" in unit.stability

    # 5. Divergence (baseline divergence is None, variant divergence is finite float)
    assert base_feats.units["speed"].divergence["rmsd"] is None
    assert var_feats.units["speed"].divergence["rmsd"] is not None

    # Flattened map format check
    flat_var = var_feats.flatten()
    assert "speed:mean" in flat_var
    assert "speed:trend_slope" in flat_var
    assert "speed:rmsd" in flat_var
