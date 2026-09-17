"""Tests for Scientific Reporting Engine and Export Routes (Phase 4 Slice 4.6)."""

from __future__ import annotations

import pytest

from workbench.app import app, store
from workbench.reporting import (
    generate_experiment_html_report,
    generate_experiment_markdown_report,
)
from workbench.store import ExperimentRecord


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_record() -> ExperimentRecord:
    rec = ExperimentRecord(
        record_id="rec_12345678",
        run_id="test_run_12345678",
        composition_id="comp_123456",
        experiment_template="morphogenesis",
        experiment_name="Test Morphogenesis",
        created_at="2026-09-17T12:00:00Z",
        status="COMPLETED",
        execution_time_seconds=1.23,
        seed=42,
        max_steps=20,
        parameters={"dt": 0.2, "n_agents": 10},
        metrics={"wall_count": 15.0, "mean_u": 0.85, "entropy": 1.234},
    )
    store.save_record(rec)
    return rec



def test_generate_markdown_report(sample_record: ExperimentRecord) -> None:
    md = generate_experiment_markdown_report(sample_record.as_dict())
    assert "# Scientific Experiment Report: Test Morphogenesis" in md
    assert "test_run_12345678" in md
    assert "wall_count" in md
    assert "15.0000" in md
    assert "VERIFIED_DETERMINISTIC" in md


def test_generate_markdown_report_with_comparison(sample_record: ExperimentRecord) -> None:
    baseline_dict = {
        "run_id": "baseline_0001",
        "metrics": {"wall_count": 10.0, "mean_u": 0.80, "entropy": 1.200},
    }
    md = generate_experiment_markdown_report(sample_record.as_dict(), baseline_dict)
    assert "## 4. Differential Comparison" in md
    assert "baseline_0001" in md
    assert "+5.0000" in md  # 15.0 - 10.0


def test_generate_html_report(sample_record: ExperimentRecord) -> None:
    html_doc = generate_experiment_html_report(sample_record.as_dict())
    assert "<!DOCTYPE html>" in html_doc
    assert "Scientific Report - Test Morphogenesis" in html_doc
    assert "REPRODUCIBLE" in html_doc


def test_api_report_endpoints(client, sample_record: ExperimentRecord) -> None:
    res_html = client.get(f"/api/reports/experiment/{sample_record.record_id}")
    assert res_html.status_code == 200
    assert "text/html" in res_html.content_type
    assert b"Test Morphogenesis" in res_html.data

    res_md = client.get(f"/api/reports/markdown/{sample_record.record_id}")
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.content_type
    assert b"Scientific Experiment Report" in res_md.data

