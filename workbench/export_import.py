"""Export and Import engine for the Trusted Experiment Lab.

Supports three explicit export tiers:
1. Level 1: Result Export (.json) - Lightweight summary with metrics and provenance hashes.
2. Level 2: Reproducible Experiment Record (.simrec / .json) - Full canonical world, parameters, seed, and replay manifest.
3. Level 3: Full Trajectory Archive (.json / .zip) - Reproducible specification plus complete multi-step spatial arrays.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from workbench.store import ExperimentRecord

__all__ = [
    "export_reproducible_record",
    "export_result_json",
    "export_trajectory_archive",
    "import_reproducible_record",
]


def export_result_json(record: ExperimentRecord) -> str:
    """Level 1 Export: Summary metrics and provenance metadata as pretty JSON."""
    payload = {
        "export_tier": "LEVEL_1_RESULT_EXPORT",
        "record_id": record.record_id,
        "session_id": record.record_id,
        "run_id": record.run_id,
        "world_hash": record.run_id,
        "composition_id": record.composition_id,
        "experiment_template": record.experiment_template,
        "experiment_name": record.experiment_name,
        "created_at": record.created_at,
        "status": record.status,
        "execution_time_seconds": record.execution_time_seconds,
        "seed": record.seed,
        "max_steps": record.max_steps,
        "parameters": record.parameters,
        "metrics": record.metrics,
        "feature_snapshot": record.feature_snapshot,
        "tags": record.tags,
        "notes": record.notes,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def export_reproducible_record(record: ExperimentRecord) -> str:
    """Level 2 Export: Self-contained reproducible experiment manifest (.simrec)."""
    payload = {
        "export_tier": "LEVEL_2_REPRODUCIBLE_RECORD",
        "format_version": "2.0",
        "record_id": record.record_id,
        "session_id": record.record_id,
        "run_id": record.run_id,
        "world_hash": record.run_id,
        "composition_id": record.composition_id,
        "experiment_template": record.experiment_template,
        "experiment_name": record.experiment_name,
        "created_at": record.created_at,
        "status": record.status,
        "execution_time_seconds": record.execution_time_seconds,
        "seed": record.seed,
        "max_steps": record.max_steps,
        "parameters": record.parameters,
        "canonical_world": record.canonical_world,
        "metrics": record.metrics,
        "expected_metrics": record.metrics,
        "tags": record.tags,
        "notes": record.notes,
        "reproduction_manifest": {
            "deterministic_run_id": record.run_id,
            "target_composition_id": record.composition_id,
            "environment": {
                "framework": "Simulation Alchemist",
                "phase": "Phase 2 Trusted Experiment Lab",
            },
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def export_trajectory_archive(
    record: ExperimentRecord,
    trajectory: dict[str, Any] | None,
) -> bytes:
    """Level 3 Export: Zip bundle containing the reproducible record and trajectory arrays."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include reproducible record JSON
        rec_json = export_reproducible_record(record)
        zf.writestr("experiment_record.simrec", rec_json)

        # Include trajectory data
        traj_data = trajectory or {"available": False, "total_steps": 0}
        zf.writestr("trajectory.json", json.dumps(traj_data, indent=2))

        # Include summary readme
        readme = f"""# Simulation Alchemist - Level 3 Experiment Archive
Record ID: {record.record_id}
Run ID: {record.run_id}
Composition ID: {record.composition_id}
Experiment: {record.experiment_name} ({record.experiment_template})
Created At: {record.created_at}
Seed: {record.seed}
Steps: {record.max_steps}
Status: {record.status}

Files in this archive:
- experiment_record.simrec: Full reproducible configuration manifest.
- trajectory.json: Raw multi-step spatial arrays and coordinates.
"""
        zf.writestr("README.txt", readme)

    return buf.getvalue()


def import_reproducible_record(raw_content: str | bytes) -> dict[str, Any]:
    """Validate and parse a Level 2 .simrec payload for reconstruction and replay.

    Raises:
        ValueError: If the payload is malformed or missing mandatory reproduction keys.
    """
    if isinstance(raw_content, bytes):
        raw_content = raw_content.decode("utf-8")

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON payload in experiment record: {err}") from err

    if not isinstance(data, dict):
        raise TypeError("Experiment record root must be a JSON object")

    mandatory_keys = [
        "composition_id",
        "experiment_template",
        "seed",
        "max_steps",
        "parameters",
    ]
    missing = [k for k in mandatory_keys if k not in data]
    if missing:
        raise ValueError(f"Missing mandatory reproduction fields: {missing}")

    return {
        "valid": True,
        "record_id": data.get("record_id"),
        "run_id": data.get("run_id"),
        "composition_id": data["composition_id"],
        "experiment_template": data["experiment_template"],
        "experiment_name": data.get("experiment_name", data["experiment_template"]),
        "seed": int(data["seed"]),
        "max_steps": int(data["max_steps"]),
        "parameters": dict(data["parameters"]),
        "canonical_world": data.get("canonical_world", {}),
        "expected_metrics": dict(data.get("expected_metrics", {})),
        "tags": list(data.get("tags", [])),
        "notes": str(data.get("notes", "")),
    }
