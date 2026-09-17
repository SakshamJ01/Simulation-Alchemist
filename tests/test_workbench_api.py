"""Integration tests for Phase 2 Trusted Experiment Lab REST APIs."""


import pytest

from workbench.app import app, store


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_history_empty_and_populated(client):
    # History initially queries store
    res = client.get("/api/history")
    assert res.status_code == 200
    data = res.get_json()
    assert "records" in data
    assert "total" in data


def test_run_persists_to_store_and_history(client):
    payload = {
        "exp_id": "field_guided_movers",
        "params": {},
        "max_steps": 12,
        "seed": 42,
        "tags": ["phase2_test"],
        "notes": "Automated Phase 2 integration run",
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert "record_id" in data
    assert "run_id" in data
    record_id = data["record_id"]

    # Verify record is in database
    rec = store.get_record(record_id)
    assert rec is not None
    assert rec.seed == 42
    assert "phase2_test" in rec.tags
    assert rec.notes == "Automated Phase 2 integration run"

    # Query via /api/records/<record_id>
    rec_res = client.get(f"/api/records/{record_id}")
    assert rec_res.status_code == 200
    rec_json = rec_res.get_json()
    assert rec_json["record_id"] == record_id
    assert rec_json["status"] == "completed"

    # Query trajectory via /api/records/<record_id>/trajectory
    traj_res = client.get(f"/api/records/{record_id}/trajectory")
    assert traj_res.status_code == 200
    traj_json = traj_res.get_json()
    assert traj_json["available"] is True

    # Update notes/tags via PATCH
    patch_res = client.patch(
        f"/api/records/{record_id}",
        json={"notes": "Updated note", "tags": ["phase2_test", "verified"]},
    )
    assert patch_res.status_code == 200
    updated_rec = store.get_record(record_id)
    assert updated_rec is not None
    assert updated_rec.notes == "Updated note"
    assert "verified" in updated_rec.tags


def test_replay_zero_drift_verification(client):
    # Run an experiment to create a record
    payload = {
        "exp_id": "field_guided_movers",
        "params": {},
        "max_steps": 12,
        "seed": 42,
    }
    run_res = client.post("/run", json=payload)
    assert run_res.status_code == 200
    record_id = run_res.get_json()["record_id"]

    # Trigger deterministic replay
    replay_res = client.post(f"/api/replay/{record_id}")
    assert replay_res.status_code == 200
    replay_json = replay_res.get_json()
    assert replay_json["is_identical"] is True
    assert replay_json["max_metric_delta"] < 1e-7
    assert replay_json["replayed_run_id"] == replay_json["original_run_id"]


def test_compare_two_arbitrary_runs(client):
    # Create Run A
    run_a = client.post(
        "/run",
        json={"exp_id": "gated_movers", "params": {"gate_threshold": 0.5, "gate_cooldown": 4}, "max_steps": 12, "seed": 42},
    ).get_json()

    # Create Run B
    run_b = client.post(
        "/run",
        json={"exp_id": "gated_movers", "params": {"gate_threshold": 0.0, "gate_cooldown": 0}, "max_steps": 12, "seed": 42},
    ).get_json()

    rec_id_a = run_a["record_id"]
    rec_id_b = run_b["record_id"]

    # Compare
    cmp_res = client.post("/api/compare", json={"record_id_a": rec_id_a, "record_id_b": rec_id_b})
    assert cmp_res.status_code == 200
    cmp_json = cmp_res.get_json()
    assert "parameter_diffs" in cmp_json
    assert "metric_diffs" in cmp_json
    assert "trajectory_a" in cmp_json
    assert "trajectory_b" in cmp_json

    # Check parameter diff found the gate_threshold difference
    param_diffs = {p["parameter"]: p for p in cmp_json["parameter_diffs"]}
    assert "gate_threshold" in param_diffs
    assert param_diffs["gate_threshold"]["is_different"] is True


def test_export_tiers(client):
    run_res = client.post(
        "/run",
        json={"exp_id": "field_guided_movers", "params": {}, "max_steps": 12, "seed": 42},
    ).get_json()
    record_id = run_res["record_id"]

    # Level 1
    l1 = client.get(f"/export/{record_id}?level=1")
    assert l1.status_code == 200
    assert "application/json" in l1.content_type
    assert b"LEVEL_1_RESULT_EXPORT" in l1.data

    # Level 2 (.simrec)
    l2 = client.get(f"/export/{record_id}?level=2")
    assert l2.status_code == 200
    assert "application/json" in l2.content_type
    assert b"LEVEL_2_REPRODUCIBLE_RECORD" in l2.data

    # Level 3 (.zip)
    l3 = client.get(f"/export/{record_id}?level=3")
    assert l3.status_code == 200
    assert "application/zip" in l3.content_type
    assert len(l3.data) > 0


def test_import_route(client):
    run_res = client.post(
        "/run",
        json={"exp_id": "field_guided_movers", "params": {}, "max_steps": 12, "seed": 42},
    ).get_json()
    record_id = run_res["record_id"]

    l2_content = client.get(f"/export/{record_id}?level=2").get_data(as_text=True)

    # Import
    imp_res = client.post("/api/import", data=l2_content, content_type="application/json")
    assert imp_res.status_code == 200
    imp_json = imp_res.get_json()
    assert imp_json["valid"] is True
    assert imp_json["record_spec"]["experiment_template"] == "field_guided_movers"
