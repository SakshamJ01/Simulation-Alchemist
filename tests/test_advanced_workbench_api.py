"""Integration tests for advanced Phase 4 Workbench REST endpoints."""

import pytest

from workbench.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_couplings_primitives(client):
    res = client.get("/api/couplings/primitives")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "primitives" in data
    names = [p["name"] for p in data["primitives"]]
    assert "HysteresisFilter" in names
    assert "TemporalDelayBuffer" in names
    assert "SigmoidTransfer" in names
    assert "SaturationFilter" in names


def test_api_sensitivity_analyze(client):
    payload = {
        "template": "gated_movers",
        "target_metric": "final_field_mean",
        "n_trajectories": 2,
        "seed": 42,
    }
    res = client.post("/api/sensitivity/analyze", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["template"] == "gated_movers"
    assert "result" in data
    assert "markdown_report" in data
    assert "most_influential_parameter" in data["result"]


def test_api_intelligent_search_run(client):
    payload = {
        "template": "gated_movers",
        "name": "api_test_search",
        "target_objectives": [["final_field_mean", "maximize"]],
        "n_initial_samples": 2,
        "n_iterations": 1,
        "candidates_per_iter": 1,
        "seed": 42,
    }
    res = client.post("/api/intelligent_search/run", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["template"] == "gated_movers"
    assert "result" in data
    assert "markdown_report" in data
    assert len(data["result"]["all_evaluated"]) == 3  # 2 init + 1 iter
