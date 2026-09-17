"""Unit tests for export and import levels in Workbench."""

import json
import zipfile

from workbench.export_import import (
    export_reproducible_record,
    export_result_json,
    export_trajectory_archive,
    import_reproducible_record,
)
from workbench.store import ExperimentRecord


def _sample_record() -> ExperimentRecord:
    return ExperimentRecord(
        record_id="rec_exp_999",
        run_id="run_999_abcdef123456",
        composition_id="comp_gated_123456",
        experiment_template="gated_movers",
        experiment_name="Gated mover morphogenesis (D)",
        created_at="2026-09-17T20:30:00Z",
        status="completed",
        execution_time_seconds=1.23,
        seed=42,
        max_steps=12,
        parameters={"gate_threshold": 0.5, "gate_cooldown": 4},
        canonical_world={"components": ["pde", "physics", "mesa"]},
        metrics={"deposition_events": 0.0, "deposition_suppression": 36.0},
        tags=["gated", "verified"],
        notes="Phase 2 reproducible record test",
    )


def test_export_level_1_result_json():
    record = _sample_record()
    res = export_result_json(record)
    data = json.loads(res)
    assert data["export_tier"] == "LEVEL_1_RESULT_EXPORT"
    assert data["record_id"] == "rec_exp_999"
    assert data["metrics"]["deposition_suppression"] == 36.0


def test_export_and_import_level_2_reproducible_record():
    record = _sample_record()
    simrec = export_reproducible_record(record)
    assert "LEVEL_2_REPRODUCIBLE_RECORD" in simrec

    # Import
    parsed = import_reproducible_record(simrec)
    assert parsed["valid"] is True
    assert parsed["composition_id"] == "comp_gated_123456"
    assert parsed["seed"] == 42
    assert parsed["parameters"]["gate_threshold"] == 0.5
    assert parsed["expected_metrics"]["deposition_events"] == 0.0


def test_export_level_3_trajectory_archive():
    record = _sample_record()
    traj = {"available": True, "total_steps": 12, "field_frames": []}
    zip_bytes = export_trajectory_archive(record, traj)

    import io

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "experiment_record.simrec" in names
        assert "trajectory.json" in names
        assert "README.txt" in names
