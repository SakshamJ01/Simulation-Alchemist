"""Unit tests for WorkbenchStore and ExperimentRecord persistence."""

from workbench.store import ExperimentRecord, WorkbenchStore


def test_workbench_store_in_memory_crud():
    store = WorkbenchStore(":memory:")

    record = ExperimentRecord(
        record_id="rec_test_001",
        run_id="run_hash_1234567890abcdef",
        composition_id="comp_1234567890abcdef",
        experiment_template="field_guided_movers",
        experiment_name="Field-guided movers (B)",
        created_at="2026-09-17T20:00:00Z",
        status="completed",
        execution_time_seconds=0.45,
        seed=42,
        max_steps=12,
        parameters={"n_movers": 6},
        canonical_world={"components": ["pde", "physics"]},
        metrics={"mean_speed": 0.005, "total_displacement": 0.12},
        tags=["baseline", "test"],
        notes="Initial baseline run",
    )

    trajectory = {
        "available": True,
        "total_steps": 12,
        "field_frames": [{"step": 0, "min_val": 0.0, "max_val": 1.0}],
    }

    # Save
    store.save_record(record, trajectory=trajectory)

    # Get record
    fetched = store.get_record("rec_test_001")
    assert fetched is not None
    assert fetched.record_id == "rec_test_001"
    assert fetched.run_id == "run_hash_1234567890abcdef"
    assert fetched.metrics["mean_speed"] == 0.005
    assert fetched.tags == ["baseline", "test"]
    assert fetched.notes == "Initial baseline run"

    # Get trajectory
    fetched_traj = store.get_trajectory("rec_test_001")
    assert fetched_traj is not None
    assert fetched_traj["available"] is True
    assert fetched_traj["total_steps"] == 12

    # Get by run_id
    by_run = store.get_record_by_run_id("run_hash_1234567890abcdef")
    assert by_run is not None
    assert by_run.record_id == "rec_test_001"

    # List & Filter
    records = store.list_records(experiment_template="field_guided_movers")
    assert len(records) == 1

    records_none = store.list_records(experiment_template="gated_movers")
    assert len(records_none) == 0

    # Search
    search_res = store.list_records(search_query="baseline")
    assert len(search_res) == 1

    # Update notes and tags
    updated = store.update_notes_and_tags("rec_test_001", notes="Updated notes", tags=["production"])
    assert updated is True
    refetched = store.get_record("rec_test_001")
    assert refetched is not None
    assert refetched.notes == "Updated notes"
    assert refetched.tags == ["production"]

    # Delete
    deleted = store.delete_record("rec_test_001")
    assert deleted is True
    assert store.get_record("rec_test_001") is None
    assert store.get_trajectory("rec_test_001") is None
