"""Focused tests for Simulation Alchemist Flask Workbench."""

import json

import pytest

from workbench.app import _discover_experiments, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_flask_import():
    """Verify send_from_directory is importable from flask."""
    from flask import send_from_directory

    assert send_from_directory is not None


def test_index_route(client):
    """Verify root page loads with 200 status code and Phase 1.5 UI elements."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Simulation Alchemist" in html
    assert "2D Spatial Viewport" in html
    assert "Observable Metrics" in html
    assert "sim-canvas" in html


def test_run_d_gated_movers(client):
    """Verify /run executes D (gated_movers) with gate_threshold and returns real trajectory frames."""
    exps = _discover_experiments()
    d_info = exps.get("gated_movers")
    assert d_info is not None

    payload = {
        "exp_id": d_info["id"],
        "params": {"gate_threshold": 0.5, "gate_cooldown": 4},
        "max_steps": 12,
        "seed": 42,
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    assert "application/json" in res.content_type
    data = res.get_json()
    assert "session_id" in data
    assert "outcome" in data
    assert "metrics" in data["outcome"]
    assert "world_hash" in data["outcome"]
    assert "active_gates" in data["outcome"]["metrics"]

    # Trajectory observability assertions
    assert "trajectory" in data
    traj = data["trajectory"]
    assert traj["available"] is True
    assert traj["total_steps"] == 12
    assert len(traj["field_frames"]) > 0
    assert len(traj["movers"]) == 6
    assert len(traj["active_gates"]) == 12

    # Verify export for this session
    session_id = data["session_id"]
    res_export = client.get(f"/export/{session_id}")
    assert res_export.status_code == 200
    export_data = json.loads(res_export.get_data(as_text=True))
    assert export_data["session_id"] == session_id
    assert "metrics" in export_data
    assert "world_hash" in export_data


def test_run_abc_experiments(client):
    """Verify A, B, and C experiment runs execute successfully with trajectory payloads."""
    exps = _discover_experiments()
    for exp_key in ["morphogenesis", "field_guided_movers", "adaptive_network"]:
        info = exps.get(exp_key)
        assert info is not None
        payload = {"exp_id": info["id"], "max_steps": 12, "seed": 42}
        res = client.post("/run", json=payload)
        assert res.status_code == 200
        assert "application/json" in res.content_type
        data = res.get_json()
        assert "session_id" in data
        assert "outcome" in data
        assert "metrics" in data["outcome"]
        assert "trajectory" in data
        assert data["trajectory"]["available"] is True


def test_run_invalid_requests(client):
    """Verify missing or invalid exp_id returns a JSON error response with HTTP 400."""
    res = client.post("/run", json={})
    assert res.status_code == 400
    assert "application/json" in res.content_type
    data = res.get_json()
    assert "error" in data
    assert data["error"] == "Missing exp_id"

    res_unknown = client.post("/run", json={"exp_id": "non_existent_id_123"})
    assert res_unknown.status_code == 400
    assert "application/json" in res_unknown.content_type
    data_unknown = res_unknown.get_json()
    assert "error" in data_unknown
    assert "Unknown experiment id" in data_unknown["error"]


def test_comparison_route(client):
    """Verify /comparison returns distinct ON vs OFF simulation runs with real deltas and distinct provenance."""
    res = client.get("/comparison")
    assert res.status_code == 200
    assert "application/json" in res.content_type
    data = res.get_json()
    assert "diff" in data
    assert "provenance" in data
    assert data["provenance"]["experiment"] == "gated_movers"

    # Distinct provenance run IDs
    on_id = data["provenance"]["on_run_id"]
    off_id = data["provenance"]["off_run_id"]
    assert on_id != off_id, f"Expected distinct run IDs, got identical {on_id}"

    # Real metric deltas between ON (gating active) and OFF (unconditional)
    diff = data["diff"]
    assert "deposition_events" in diff
    assert "deposition_suppression" in diff
    assert diff["deposition_events"]["on"] != diff["deposition_events"]["off"]
    assert diff["deposition_suppression"]["on"] != diff["deposition_suppression"]["off"]

    # Trajectory payloads for side-by-side visualization
    assert "on_trajectory" in data
    assert "off_trajectory" in data
    assert data["on_trajectory"]["available"] is True
    assert data["off_trajectory"]["available"] is True
