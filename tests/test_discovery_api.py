"""Integration tests for Phase 3 Slice 3.4: Discovery REST APIs & Session Lifecycle."""

from __future__ import annotations

import json
from typing import Any

import pytest

from workbench.app import app, store


@pytest.fixture
def client() -> Any:
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_discovery_specs(client: Any) -> None:
    """Verify retrieval of declared parameter specs and defaults."""
    res = client.get("/api/discovery/specs/gated_movers")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    assert data["template"] == "gated_movers"
    assert "config.gate_threshold" in data["specs"]
    assert "config.gate_cooldown" in data["specs"]
    assert data["default_variant_count"] == 4
    assert data["estimated_runtime_seconds"] > 0

    # Unsupported template returns 400
    res_bad = client.get("/api/discovery/specs/morphogenesis")
    assert res_bad.status_code == 400
    data_bad = json.loads(res_bad.data)
    assert data_bad["success"] is False


def test_api_discovery_run_and_session_lifecycle(client: Any) -> None:
    """Verify executing a discovery pass via API, session persistence, and retrieval."""
    payload = {
        "experiment_template": "gated_movers",
        "sweeps": [
            {
                "path": "config.gate_threshold",
                "values": [0.3, 0.7],
            }
        ],
        "max_steps": 3,
        "seed": 42,
        "session_name": "API Test Session",
        "profile_name": "test_profile",
        "profile_weights": {
            "speed:mean": 1.0,
            "active_gates:mean": 0.5,
        },
        "profile_directions": {
            "speed:mean": True,
            "active_gates:mean": True,
        },
        "beam_width": 2,
        "quality_weight": 0.7,
        "diversity_weight": 0.3,
    }

    res = client.post(
        "/api/discovery/run",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    result = data["result"]
    assert "session_id" in result
    session_id = result["session_id"]
    assert len(result["candidates"]) >= 2
    assert len(result["frontier_candidates"]) == 2

    # Verify candidates were saved to WorkbenchStore
    cand0 = result["candidates"][0]
    rec0 = store.get_record(cand0["record_id"])
    assert rec0 is not None
    assert rec0.experiment_template == "gated_movers"

    # Verify session is listed in GET /api/discovery/sessions
    res_list = client.get("/api/discovery/sessions")
    assert res_list.status_code == 200
    list_data = json.loads(res_list.data)
    assert list_data["success"] is True
    session_ids = [s["session_id"] for s in list_data["sessions"]]
    assert session_id in session_ids

    # Verify session detail in GET /api/discovery/sessions/<session_id>
    res_detail = client.get(f"/api/discovery/sessions/{session_id}")
    assert res_detail.status_code == 200
    detail_data = json.loads(res_detail.data)
    assert detail_data["success"] is True
    assert detail_data["session"]["session_id"] == session_id
    assert len(detail_data["candidates"]) >= 2

    # Verify DELETE /api/discovery/sessions/<session_id>
    res_del = client.delete(f"/api/discovery/sessions/{session_id}")
    assert res_del.status_code == 200
    del_data = json.loads(res_del.data)
    assert del_data["success"] is True

    # Confirm 404 after deletion
    res_after = client.get(f"/api/discovery/sessions/{session_id}")
    assert res_after.status_code == 404


def test_api_discovery_run_validation_errors(client: Any) -> None:
    """Verify validation rejections on out-of-bounds or exceeding caps."""
    # Out of bounds value (1.5 > 1.0)
    payload_bad_val = {
        "experiment_template": "gated_movers",
        "sweeps": [
            {
                "path": "config.gate_threshold",
                "values": [0.5, 1.5],
            }
        ],
        "max_steps": 3,
        "seed": 42,
    }
    res = client.post(
        "/api/discovery/run",
        data=json.dumps(payload_bad_val),
        content_type="application/json",
    )
    assert res.status_code == 400
    data = json.loads(res.data)
    assert "above legal maximum" in data["error"]


def test_discovery_candidate_replay_recorded_and_deterministic_rerun(client: Any) -> None:
    """Verify discovery candidate replay workflow for both stored trajectories and deterministic re-runs."""
    payload = {
        "experiment_template": "gated_movers",
        "sweeps": [
            {
                "path": "config.gate_threshold",
                "values": [0.2, 0.5, 0.8],
            }
        ],
        "max_steps": 3,
        "seed": 42,
        "beam_width": 1,
        "quality_weight": 1.0,
        "diversity_weight": 0.0,
    }

    res = client.post(
        "/api/discovery/run",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = json.loads(res.data)
    result = data["result"]
    candidates = result["candidates"]
    frontier = result["frontier_candidates"]

    # 1. Test Frontier Candidate Replay (Option A: Recorded Replay from stored trajectory)
    frontier_cand = frontier[0]
    rec_id_f = frontier_cand["record_id"]
    
    # Verify metadata retrieval
    res_rec = client.get(f"/api/records/{rec_id_f}")
    assert res_rec.status_code == 200
    rec_data = json.loads(res_rec.data)
    assert rec_data["record_id"] == rec_id_f
    assert rec_data["experiment_template"] == "gated_movers"
    assert rec_data["seed"] == 42
    assert rec_data["max_steps"] == 3
    assert rec_data["run_id"] == frontier_cand["run_id"]

    # Verify stored trajectory is available (Option A)
    res_traj = client.get(f"/api/records/{rec_id_f}/trajectory")
    assert res_traj.status_code == 200
    traj_data = json.loads(res_traj.data)
    assert traj_data["available"] is True
    assert len(traj_data["field_frames"]) > 0

    # 2. Test Non-Frontier Non-Baseline Candidate Replay (Option B: Deterministic Re-run)
    # Find a candidate that is neither frontier nor baseline
    non_frontier_non_base = [c for c in candidates if (not c.get("is_frontier")) and (not c.get("is_baseline"))]
    if non_frontier_non_base:
        non_frontier_cand = non_frontier_non_base[0]
        rec_id_nf = non_frontier_cand["record_id"]

        # Verify metadata retrieval
        res_rec_nf = client.get(f"/api/records/{rec_id_nf}")
        assert res_rec_nf.status_code == 200
        rec_data_nf = json.loads(res_rec_nf.data)
        assert rec_data_nf["record_id"] == rec_id_nf
        assert rec_data_nf["seed"] == 42
        assert rec_data_nf["max_steps"] == 3

        # Verify trajectory is not stored (Option B)
        res_traj_nf = client.get(f"/api/records/{rec_id_nf}/trajectory")
        assert res_traj_nf.status_code == 404

        # Execute deterministic re-run endpoint
        res_replay = client.post(f"/api/replay/{rec_id_nf}")
        assert res_replay.status_code == 200
        replay_data = json.loads(res_replay.data)
        assert replay_data["is_identical"] is True
        assert replay_data["max_metric_delta"] < 1e-7
        assert replay_data["replayed_run_id"] == non_frontier_cand["run_id"]
        assert replay_data["trajectory"]["available"] is True
        assert len(replay_data["trajectory"]["field_frames"]) > 0


def test_discovery_replay_arbitrary_templates(client: Any) -> None:
    """Verify discovery replay operates truthfully across arbitrary templates (e.g. adaptive network)."""
    payload = {
        "experiment_template": "adaptive_network",
        "sweeps": [
            {
                "path": "components.network.config.loss",
                "values": [0.3, 0.7],
            }
        ],
        "max_steps": 3,
        "seed": 101,
        "beam_width": 1,
    }

    res = client.post(
        "/api/discovery/run",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200
    data = json.loads(res.data)
    frontier_cand = data["result"]["frontier_candidates"][0]
    rec_id = frontier_cand["record_id"]

    # Verify record and replay
    res_rec = client.get(f"/api/records/{rec_id}")
    assert res_rec.status_code == 200
    rec = json.loads(res_rec.data)
    assert rec["experiment_template"] == "adaptive_network"
    assert rec["seed"] == 101

    # Deterministic replay endpoint returns identical outcome
    res_replay = client.post(f"/api/replay/{rec_id}")
    assert res_replay.status_code == 200
    replay = json.loads(res_replay.data)
    assert replay["is_identical"] is True
    assert replay["replayed_run_id"] == rec["run_id"]


