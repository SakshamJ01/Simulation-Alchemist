"""Unit tests for Phase 3 Slice 3.3: Transparent Ranking, Diversity Frontier, and Persistence."""

from __future__ import annotations

from sim_alchemist.core.behavior import InterestingnessProfile
from sim_alchemist.core.sweep import ParameterSweep
from workbench.discovery import (
    characterize_and_rank_candidates,
    get_default_interestingness_profile,
    run_bounded_discovery_exploration,
    run_discovery_pass,
)
from workbench.store import WorkbenchStore


def test_characterize_and_rank_transparency() -> None:
    """Verify transparent ranking scoring and per-feature contribution breakdown."""
    exploration = run_bounded_discovery_exploration(
        "gated_movers",
        [ParameterSweep("config.gate_threshold", (0.25, 0.75))],
        max_steps=3,
        seed=42,
        retain_all_trajectories=True,
    )

    profile = InterestingnessProfile(
        name="speed_and_gates",
        description="Speed and gates profile",
        weights={"speed:mean": 1.0, "active_gates:mean": 0.5},
        directions={"speed:mean": True, "active_gates:mean": True},
    )

    enriched, ranking_result, _frontier = characterize_and_rank_candidates(
        exploration,
        profile,
        beam_width=2,
        quality_weight=0.7,
        diversity_weight=0.3,
    )

    assert len(enriched) >= 2
    assert len(ranking_result.rows) == len(enriched)

    # Verify rank ordering: rank 1 has highest score
    assert enriched[0]["rank"] == 1
    assert enriched[0]["score"] >= enriched[1]["score"]

    # Verify contribution explainability
    for cand in enriched:
        assert "speed:mean" in cand["contributions"]
        contrib = cand["contributions"]["speed:mean"]
        assert "weight" in contrib
        assert "raw" in contrib
        assert "normalized" in contrib
        assert "contribution" in contrib
        assert contrib["weight"] == 1.0
        # Check that contribution equals weight * normalized (or close within float precision)
        if contrib["normalized"] is not None:
            expected = contrib["weight"] * contrib["normalized"]
            assert abs(contrib["contribution"] - expected) < 1e-6


def test_diversity_frontier_selection() -> None:
    """Verify diversity frontier selection logic and rationale."""
    exploration = run_bounded_discovery_exploration(
        "gated_movers",
        [ParameterSweep("config.gate_threshold", (0.2, 0.5, 0.8))],
        max_steps=3,
        seed=42,
        retain_all_trajectories=True,
    )

    profile = get_default_interestingness_profile("gated_movers")

    enriched, _, frontier_tuples = characterize_and_rank_candidates(
        exploration,
        profile,
        beam_width=2,
        quality_weight=0.5,
        diversity_weight=0.5,
    )

    assert len(frontier_tuples) == 2
    # Slot 1 is always highest_quality
    assert frontier_tuples[0][5] == "highest_quality"
    # Slot 2 is diversity_balanced
    assert frontier_tuples[1][5] == "diversity_balanced"

    frontier_candidates = [c for c in enriched if c["is_frontier"]]
    assert len(frontier_candidates) == 2


def test_run_discovery_pass_end_to_end_persistence() -> None:
    """Verify end-to-end discovery pass with WorkbenchStore and trajectory retention policy."""
    store = WorkbenchStore(":memory:")

    sweeps = [ParameterSweep("config.gate_threshold", (0.25, 0.75))]
    pass_result = run_discovery_pass(
        "gated_movers",
        sweeps,
        max_steps=3,
        seed=42,
        session_name="Test Gating Exploration",
        store=store,
        beam_width=1,  # Keep 1 on frontier to test non-frontier trajectory omission
    )

    assert pass_result.session_id.startswith("disc_")
    assert pass_result.name == "Test Gating Exploration"
    assert len(pass_result.candidates) >= 2

    # Verify session is persisted in WorkbenchStore
    saved_session = store.get_discovery_session(pass_result.session_id)
    assert saved_session is not None
    assert saved_session.name == "Test Gating Exploration"
    assert len(saved_session.candidate_record_ids) == len(pass_result.candidates)

    # Verify each candidate is persisted as an ExperimentRecord
    baseline_cand = next(c for c in pass_result.candidates if c.is_baseline)
    non_frontier_cands = [c for c in pass_result.candidates if not c.is_frontier and not c.is_baseline]

    # Trajectory Retention Policy:
    # Baseline candidate ALWAYS has trajectory in SQLite
    base_rec = store.get_record(baseline_cand.record_id)
    assert base_rec is not None
    assert store.get_trajectory(baseline_cand.record_id) is not None

    # Non-frontier candidate has record in SQLite, but NO stored trajectory (saves database space)
    if non_frontier_cands:
        nf_cand = non_frontier_cands[0]
        nf_rec = store.get_record(nf_cand.record_id)
        assert nf_rec is not None
        assert nf_rec.run_id == nf_cand.run_id
        assert store.get_trajectory(nf_cand.record_id) is None
