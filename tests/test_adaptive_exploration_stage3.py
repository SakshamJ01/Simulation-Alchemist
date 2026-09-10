"""Task 2.7 Build Stage 3 — Durable exploration-session lineage (additive)."""
from __future__ import annotations

import sys
sys.path.insert(0, "src")

from sim_alchemist.core.lineage import LineageStore
from sim_alchemist.core.adaptive_exploration import AdaptiveExplorationSpec, adaptive_exploration_id_of


def test_stage3_lineage_schema_exists():
    store = LineageStore(":memory:")
    # Migration / initialization creates table
    count = store.count_exploration_sessions()
    assert isinstance(count, int)
    assert count == 0


def test_stage3_record_and_get():
    store = LineageStore(":memory:")
    spec = AdaptiveExplorationSpec(composition_ids=("C",), seed=0, budget=2)
    sid = adaptive_exploration_id_of(spec, seed=0)
    store.record_exploration_session(
        session_id=sid,
        spec_dict=spec.as_dict(),
        eligible_compositions=["C"],
        profile_text="default",
        seed=0,
        budget=2,
        pass_adaptive_run_ids=["run_c_baseline_1"],
        final_decision="STOP",
        termination_reason="BUDGET_EXHAUSTED",
        total_simulated=2,
        status="VALID",
        created_at="2026-09-10T00:00:00+00:00",
    )
    row = store.get_exploration_session(sid)
    assert row is not None
    assert row["adaptive_exploration_id"] == sid
    assert row["status"] == "VALID"


def test_stage3_idempotent_duplicate():
    store = LineageStore(":memory:")
    spec = AdaptiveExplorationSpec(composition_ids=("C",), seed=1, budget=3)
    sid = adaptive_exploration_id_of(spec, seed=1)
    store.record_exploration_session(session_id=sid, spec_dict=spec.as_dict(), eligible_compositions=["C"], profile_text="quality", seed=1, budget=3, pass_adaptive_run_ids=["r1"], final_decision="STOP", termination_reason="STOP", total_simulated=1, status="VALID", created_at="2026-09-10T00:00:00+00:00")
    store.record_exploration_session(session_id=sid, spec_dict=spec.as_dict(), eligible_compositions=["C"], profile_text="quality", seed=1, budget=3, pass_adaptive_run_ids=["r1"], final_decision="STOP", termination_reason="STOP", total_simulated=1, status="VALID", created_at="2026-09-10T00:00:00+00:00")
    assert store.count_exploration_sessions() == 1


def test_stage3_iteration_and_count():
    store = LineageStore(":memory:")
    store.record_exploration_session(
        session_id="test123", spec_dict={}, eligible_compositions=["C"],
        profile_text="default", seed=0, budget=1, pass_adaptive_run_ids=["r"],
        final_decision="STOP", termination_reason="STOP", total_simulated=0,
        status="VALID", created_at="2026-09-10T00:00:00+00:00",
    )
    assert store.count_exploration_sessions() == 1
    rows = list(store.iter_exploration_sessions())
    assert len(rows) == 1
    assert rows[0]["adaptive_exploration_id"] == "test123"


def test_stage3_round_trip_identity():
    spec = AdaptiveExplorationSpec(composition_ids=("C",), seed=7, budget=2)
    sid = adaptive_exploration_id_of(spec, seed=7)
    store = LineageStore(":memory:")
    store.record_exploration_session(
        session_id=sid, spec_dict=spec.as_dict(), eligible_compositions=["C"],
        profile_text="default", seed=7, budget=2, pass_adaptive_run_ids=["run_c_baseline"],
        final_decision="STOP", termination_reason="STOP", total_simulated=1,
        status="VALID", created_at="2026-09-10T00:00:00+00:00",
    )
    loaded = store.get_exploration_session(sid)
    assert loaded is not None
    assert loaded["adaptive_exploration_id"] == sid
    import json
    loaded_dict = json.loads(loaded["spec_dict"])
    assert loaded_dict["composition_ids"] == ["C"]
    assert loaded["status"] == "VALID"


def test_stage3_no_duplicate_logical_exploration():
    store = LineageStore(":memory:")
    spec = AdaptiveExplorationSpec(composition_ids=("C",), seed=0)
    sid = adaptive_exploration_id_of(spec, seed=0)
    store.record_exploration_session(session_id=sid, spec_dict=spec.as_dict(), eligible_compositions=["C"], profile_text="default", seed=0, budget=3, pass_adaptive_run_ids=["r1"], final_decision="STOP", termination_reason="STOP", total_simulated=1, status="VALID", created_at="2026-09-10T00:00:00+00:00")
    # Replay same session -> idempotent, no duplicate logical row
    store.record_exploration_session(session_id=sid, spec_dict=spec.as_dict(), eligible_compositions=["C"], profile_text="default", seed=0, budget=3, pass_adaptive_run_ids=["r1"], final_decision="STOP", termination_reason="STOP", total_simulated=1, status="VALID", created_at="2026-09-10T00:00:00+00:00")
    assert store.count_exploration_sessions() == 1


def test_stage3_existing_lineage_preserved():
    """I. RunRecord / sweep / composition IDs preserved; no overload."""
    from sim_alchemist.core.lineage import RunRecord, LineageStore
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        store = LineageStore(str(tf.name))
        # Existing functionality preserved
        assert store.get_run("nonexistent") is None
        # New table present
        assert store.count_exploration_sessions() == 0
