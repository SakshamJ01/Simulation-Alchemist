"""Task 2.4 Stage 5: developer-facing discovery CLI + single figure.

Stage 5 is the thin layer that consumes Stage 4 results: ``run_composition_discovery.py``
runs one deterministic discovery search over the canonical repository catalog
and prints an explicit report (discovery id, executable count, common
observables, Profile A/B ranking, frontier members, scores, composition ids,
ranks, explanations; wall-clock timings labelled separately), and
``experiments/composition_discovery.py`` renders ONE quality-vs-diversity
figure whose quantities come only from the analysis result.

The mandated properties proven here:

  * A: the CLI runs on the real repository infrastructure and reports the
    discovery id, the executable count, the common observables, ranking,
    frontier, and "why" blocks;
  * B: the default CLI analyzes both explicit profiles, and the ``--profile``
    flag selects exactly one;
  * C: CLI determinism -- with identical arguments the printed report is
    identical apart from the explicitly labelled timing and persistence
    lines;
  * D: frontier-selection flags (``--beam-width``, ``--quality-weight``,
    ``--diversity-weight``) are honoured and reflected in the report;
  * E: the figure is produced, non-empty, and renders every evaluated
    composition with no missing labels (no pixel tests anywhere);
  * F: every plotted quantity is consumed from the analysis result -- the
    figure never recalculates and uses deterministic data ordering;
  * G: rendering the figure never re-runs a discovery search.

Plus one slow test that renders the figure from the canonical full-length
discovery analysis.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from pathlib import Path

import pytest
from test_composition_search import build_fast_repository_catalog
from test_composition_search_stage2 import _spec

from experiments.catalog import (
    build_repository_catalog,
    repository_executors,
)
from experiments.composition_discovery import (
    _scatter_data,
    composition_labels,
    make_diversity_scatter,
)
from run_composition_discovery import PROFILE_A, PROFILE_B, main
from sim_alchemist.core import (
    CompositionAnalyst,
    CompositionSearcher,
    LineageStore,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CLI_ARGS = [
    "run_composition_discovery.py",
    "--steps",
    "2",
    "--no-figure",
    "--beam-width",
    "2",
    "--profile",
    "a",
    "--quality-weight",
    "1.5",
    "--diversity-weight",
    "0.5",
]

TIMING_LINE_RE = (
    "discovery:",
    "structural_quality:",
    "field_level: ",
    "Persisted to",
    "FIGURE",
)


def _strip_timing(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(TIMING_LINE_RE)
    )


def _run_cli() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable] + CLI_ARGS,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


# ----------------------------------------------------------------------
# A/D. CLI end-to-end on the real repository infrastructure
# ----------------------------------------------------------------------
class TestCliReport:
    def test_a_cli_reports_discovery_baselines_and_flags(self) -> None:
        proc = _run_cli()
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout
        assert "Cross-composition discovery" in out
        assert "Discovery id     " in out
        for token in (
            "3 EXECUTABLE (A, B, C)",
            "Common observables (genuinely common across every composition)",
            "field_entropy",
            "final_field_mean",
            "final_field_std",
            "RANKING",
            "FRONTIER",
            "WHY",
            "=== PROFILE A: structural_quality",
            "score=",
            "combined=",
            "runs=3)",
            "beam=2",
            "selection q=1.5 d=0.5",
        ):
            assert token in out, f"missing {token!r} in CLI output"
        assert "=== PROFILE B" not in out


# ----------------------------------------------------------------------
# B. Both profiles by default; --profile selects one
# ----------------------------------------------------------------------
class TestProfileSelection:
    def test_b_default_runs_both_profiles(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--steps", "2", "--no-figure"])
        out = buf.getvalue()
        assert "=== PROFILE A: structural_quality" in out
        assert "=== PROFILE B: field_level" in out

    def test_b_profile_flag_selects_exactly_one(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--steps", "2", "--no-figure", "--profile", "b"])
        out = buf.getvalue()
        assert "=== PROFILE B: field_level" in out
        assert "=== PROFILE A" not in out


# ----------------------------------------------------------------------
# C. CLI determinism (timing/persistence lines excluded)
# ----------------------------------------------------------------------
class TestCliDeterminism:
    def test_c_repeated_cli_is_identical_apart_from_timing(self) -> None:
        first = _run_cli()
        second = _run_cli()
        assert first.returncode == second.returncode == 0
        assert _strip_timing(first.stdout) == _strip_timing(second.stdout)


# ----------------------------------------------------------------------
# E/F/G. Figure: consumes Stage 4 results, never re-runs anything
# ----------------------------------------------------------------------
class TestFigure:
    @pytest.fixture(scope="module")
    def analyzed(self):
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        store.close()
        analyst = CompositionAnalyst()
        yield {
            "result": result,
            "a": analyst.analyze(result, PROFILE_A),
            "b": analyst.analyze(result, PROFILE_B),
        }

    def test_e_figure_file_is_produced_and_non_empty(
        self, analyzed, tmp_path: Path
    ) -> None:
        out = tmp_path / "discovery.png"
        make_diversity_scatter(
            [analyzed["a"], analyzed["b"]], out, composition_labels()
        )
        assert out.is_file()
        assert out.stat().st_size > 0

    def test_f_data_ordering_is_deterministic_and_complete(self, analyzed) -> None:
        labels = composition_labels()
        for analysis in (analyzed["a"], analyzed["b"]):
            points, frontier_members = _scatter_data(analysis, labels)
            assert len(points) == len(analysis.ranking.rows) == 3
            assert sorted(p["label"] for p in points) == ["A", "B", "C"]
            assert sorted(p["composition_id"] for p in points) == sorted(
                analysis.ranking.ranked_ids()
            )
            assert len(frontier_members) == len(analysis.frontier.member_ids())
            assert frontier_members == set(analysis.frontier.member_ids())

    def test_f_plotted_values_come_straight_from_the_analysis(self, analyzed) -> None:
        labels = composition_labels()
        for analysis in (analyzed["a"], analyzed["b"]):
            points, frontier_members = _scatter_data(analysis, labels)
            isolation = analysis.frontier.isolation
            for point in points:
                row = analysis.ranking.row(point["composition_id"])
                assert row is not None
                assert point["score"] == row.score
                assert point["isolation"] == isolation[point["composition_id"]]
                assert (point["composition_id"] in frontier_members) == (
                    point["composition_id"] in analysis.frontier.member_ids()
                )

    def test_e_figure_is_deterministic(self, analyzed, tmp_path: Path) -> None:
        first = tmp_path / "a.png"
        second = tmp_path / "b.png"
        make_diversity_scatter([analyzed["a"]], first, composition_labels())
        make_diversity_scatter([analyzed["a"]], second, composition_labels())
        assert first.read_bytes() == second.read_bytes()

    def test_g_rendering_never_reruns_the_search(
        self, analyzed, monkeypatch, tmp_path: Path
    ) -> None:
        calls = {"search": 0}
        real_search = CompositionSearcher.search

        def counting_search(self, *args, **kwargs):
            calls["search"] += 1
            return real_search(self, *args, **kwargs)

        monkeypatch.setattr(CompositionSearcher, "search", counting_search)
        import matplotlib

        matplotlib.use("Agg")
        make_diversity_scatter(
            [analyzed["a"], analyzed["b"]],
            tmp_path / "no_rerun.png",
            composition_labels(),
        )
        assert calls["search"] == 0


# ----------------------------------------------------------------------
# Slow: figure from the canonical discovery analysis
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_slow_canonical_discovery_figure(tmp_path: Path) -> None:
    catalog = build_repository_catalog(generate_worlds=True)
    store = LineageStore(":memory:")
    result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
    store.close()
    analyst = CompositionAnalyst()
    analysis = analyst.analyze(result, PROFILE_A)
    out = tmp_path / "discovery_canonical.png"
    make_diversity_scatter([analysis], out, composition_labels())
    assert out.is_file()
    assert out.stat().st_size > 0