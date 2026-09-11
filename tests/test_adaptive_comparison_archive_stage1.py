"""Task 2.9 Stage 1 — Persistent Adaptive Comparison Archive (additive lineage).

Verifies the ``adaptive_comparison_archive`` lineage contract against a
genuine Task 2.8 ``AdaptiveComparisonResult`` (real analyst, real
content-addressed identity; the session inputs are synthetic-but-real
exploration results, as permitted for unit tests by the task gate):

  * schema     — archive table + columns created on any store open
  * round-trip — record -> get preserves comparison_id / session_ids /
                 profile / ranked_order / frontend_ids / diagnostics /
                 explanation / status *semantically* (never a bare
                 "row is not None" check)
  * idempotency — re-recording the same comparison id converges on exactly
                 one logical archive row (INSERT OR REPLACE)
  * same database — lineage runs and archive rows live in one SQLite file
  * migration  — a pre-2.9 store opens, keeps its old tables/data, and
                 gains the archive table
  * missing data — unknown comparison id reads back as ``None`` (explicit,
                 never fabricated)
  * no execution / no analysis — the archive chapter never invokes a
                 sweep / simulation / ranking / frontier primitive

Nothing here executes a simulation and nothing invokes the analyst; the
comparison objects are produced by the analysis-only Task 2.8 layer, which
the archive only persists.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sim_alchemist.core.adaptive_comparison import (
    AdaptiveComparisonResult,
    AdaptiveDiscoveryAnalyst,
)
from sim_alchemist.core.adaptive_exploration import (
    AdaptiveExplorationResult,
    AdaptiveExplorationSpec,
    AdaptiveExplorationStatus,
    adaptive_exploration_id_of,
)
from sim_alchemist.core.lineage import LineageStore, RunRecord
from sim_alchemist.core.world import WorldDefinition

# Tokens that would mean the archive layer executes or re-analyzes instead
# of merely persisting an already-computed comparison result.
ANALYSIS_OR_EXECUTION_TOKENS = (
    "AdaptiveSweepRunner",
    "AdaptiveDiscoveryAnalyst",
    "behavior_distance",
    "compose(",
    "CrossCompositionSweep(",
    "rank_by_profile",
    "select_diverse_frontier",
    "select_frontier",
    "SweepRunner",
    ".step(",
)

# Modules that execute simulations or recompute analysis outputs.  The
# archive chapter lives in lineage.py, whose static import graph must stay
# clear of every one of them.
EXECUTION_OR_ANALYSIS_MODULES = (
    "adaptive_comparison",
    "adaptive_sweep",
    "behavior",
    "composition_analysis",
    "composition_search",
    "composer",
    "cross_composition_sweep",
    "cross_sweep",
    "engine",
    "runner",
    "search",
    "sweep",
)

# Pre-2.9 store schema (identical to the committed pre-Task-2.9 lineage
# schema minus the adaptive_comparison_archive table).
PRE_29_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    parent_run_id TEXT,
    world_id TEXT NOT NULL,
    world_hash TEXT NOT NULL,
    seed INTEGER NOT NULL,
    mutations TEXT NOT NULL,
    world_json TEXT NOT NULL,
    metrics TEXT NOT NULL,
    feature_snapshot TEXT,
    composition_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);
CREATE TABLE IF NOT EXISTS sweeps (
    sweep_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_hash TEXT NOT NULL,
    base_run_id TEXT NOT NULL,
    mutation_space TEXT NOT NULL,
    variant_run_ids TEXT NOT NULL,
    n_planned INTEGER NOT NULL,
    n_skipped INTEGER NOT NULL,
    n_executed INTEGER NOT NULL,
    total_seconds REAL NOT NULL,
    mean_seconds REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sweeps_base ON sweeps(base_run_id);
CREATE TABLE IF NOT EXISTS behavior_analyses (
    analysis_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_hash TEXT NOT NULL,
    base_run_id TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    run_order TEXT NOT NULL,
    ranked TEXT NOT NULL,
    timing TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_behavior_base ON behavior_analyses(base_run_id);
CREATE TABLE IF NOT EXISTS searches (
    search_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_hash TEXT NOT NULL,
    base_run_id TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    generation_order TEXT NOT NULL,
    candidates TEXT NOT NULL,
    final_ranking TEXT NOT NULL,
    n_generated INTEGER NOT NULL,
    n_skipped INTEGER NOT NULL,
    n_executed INTEGER NOT NULL,
    total_seconds REAL NOT NULL,
    execution_seconds REAL NOT NULL,
    analysis_seconds REAL NOT NULL,
    mean_seconds REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_base ON searches(base_run_id);
CREATE TABLE IF NOT EXISTS cross_composition_sweeps (
    cross_split_sweep_id TEXT NOT NULL,
    composition_id TEXT NOT NULL,
    shape_id TEXT NOT NULL,
    parameter_space_ref TEXT,
    sweep_id TEXT,
    baseline_run_id TEXT NOT NULL,
    variant_run_ids TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (cross_split_sweep_id, composition_id)
);
CREATE INDEX IF NOT EXISTS idx_ccs_composition ON cross_composition_sweeps(composition_id);
CREATE INDEX IF NOT EXISTS idx_ccs_pass ON cross_composition_sweeps(cross_split_sweep_id);
CREATE TABLE IF NOT EXISTS adaptive_exploration_sessions (
    adaptive_exploration_id TEXT PRIMARY KEY,
    spec_dict TEXT NOT NULL,
    composition_ids TEXT NOT NULL,
    profile_text TEXT,
    seed INTEGER NOT NULL,
    budget INTEGER NOT NULL,
    pass_adaptive_run_ids TEXT NOT NULL,
    final_decision TEXT NOT NULL,
    termination_reason TEXT NOT NULL,
    total_simulated INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adapt_exp_id ON adaptive_exploration_sessions(adaptive_exploration_id);
"""


def _session_result(seed: int, budget: int) -> AdaptiveExplorationResult:
    spec = AdaptiveExplorationSpec(
        composition_ids=("C",), profile="default", seed=seed, budget=budget
    )
    session_id = adaptive_exploration_id_of(spec, seed=seed)
    return AdaptiveExplorationResult(
        exploration_id=session_id,
        spec_dict=spec.as_dict(),
        status=AdaptiveExplorationStatus(
            status="VALID",
            reason="synthetic unit session",
            eligible_compositions=("C",),
            constrained_subspace_size=1,
            explanation="",
        ),
        eligible_compositions=("C",),
        subspace_size=1,
        explanation="synthetic unit session",
    )


def _genuine_comparison(
    with_features: bool = False,
) -> tuple[LineageStore, AdaptiveComparisonResult, list[str]]:
    """Return (store, result, ordered_session_ids) over two real sessions."""
    store = LineageStore(":memory:")
    res_a = _session_result(seed=0, budget=2)
    res_b = _session_result(seed=1, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    feature_vectors = None
    if with_features:
        sids = sorted([res_a.exploration_id, res_b.exploration_id])
        feature_vectors = {sids[0]: [2.0, 1.0], sids[1]: [5.0, 3.0]}
    result = analyst.compare_adaptive_discovery(
        [res_a, res_b],
        comparison_profile="default",
        feature_vectors=feature_vectors,
    )
    return store, result, list(result.source_session_ids)


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
def test_archive_schema_created_on_open() -> None:
    store = LineageStore(":memory:")
    tables = {
        r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "adaptive_comparison_archive" in tables
    cols = [r[1] for r in store._conn.execute("PRAGMA table_info(adaptive_comparison_archive)")]
    assert set(cols) == {
        "adaptive_comparison_id",
        "session_ids_json",
        "profile_text",
        "comparison_result_digest",
        "status",
        "created_at",
    }
    store.close()


# ----------------------------------------------------------------------
# Record + get round-trip over a genuine comparison (no feature data)
# ----------------------------------------------------------------------
def test_round_trip_genuine_comparison_without_features() -> None:
    store, result, sids = _genuine_comparison(with_features=False)
    store.record_adaptive_comparison(result, status="VALID")

    got = store.get_adaptive_comparison(result.comparison_id)
    assert got is not None
    # Semantic equality over every archived field (never just "not None").
    assert got["adaptive_comparison_id"] == result.comparison_id
    assert got["session_ids"] == sids
    assert got["profile_text"] == result.profile
    digest = got["result_digest"]
    assert digest["ranked_order"] == list(result.ranked_order)
    assert digest["frontend_ids"] == list(result.frontend_ids)
    assert digest["diagnostics"] == dict(result.diagnostics)
    assert digest["explanation"] == result.explanation
    assert got["status"] == "VALID"
    assert isinstance(got["created_at"], str) and got["created_at"]
    # Without durable features the honest result carries empty ranked/frontier
    # and an explanation stating the missing-data requirement (no fabrication).
    assert digest["ranked_order"] == []
    assert digest["frontend_ids"] == []
    assert "Missing durable feature data" in digest["explanation"]
    store.close()


# ----------------------------------------------------------------------
# Round-trip preserves non-empty analysis outputs (ranked/frontier/diagnostics)
# ----------------------------------------------------------------------
def test_round_trip_preserves_nonempty_analysis_outputs() -> None:
    store, result, sids = _genuine_comparison(with_features=True)
    assert result.ranked_order, "analyst must produce a non-empty ranking here"
    assert result.frontend_ids, "analyst must produce a non-empty frontier here"

    store.record_adaptive_comparison(result)
    got = store.get_adaptive_comparison(result.comparison_id)
    assert got is not None
    assert got["adaptive_comparison_id"] == result.comparison_id
    assert got["session_ids"] == sids
    assert got["profile_text"] == result.profile
    digest = got["result_digest"]
    assert digest["ranked_order"] == list(result.ranked_order)
    assert digest["frontend_ids"] == list(result.frontend_ids)
    assert digest["diagnostics"] == dict(result.diagnostics)
    assert digest["diagnostics"]["feature_vectors_available"] is True
    assert digest["explanation"] == result.explanation
    store.close()


# ----------------------------------------------------------------------
# Idempotency — exactly one logical row per comparison_id
# ----------------------------------------------------------------------
def test_idempotency_single_logical_row() -> None:
    store = LineageStore(":memory:")
    result = _session_result(seed=0, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    comparison = analyst.compare_adaptive_discovery([result], comparison_profile="default")
    for _ in range(3):
        store.record_adaptive_comparison(comparison)
    (count,) = store._conn.execute(
        "SELECT COUNT(*) FROM adaptive_comparison_archive WHERE adaptive_comparison_id = ?",
        (comparison.comparison_id,),
    ).fetchone()
    assert count == 1
    (total,) = store._conn.execute(
        "SELECT COUNT(*) FROM adaptive_comparison_archive"
    ).fetchone()
    assert total == 1
    store.close()


# ----------------------------------------------------------------------
# Same database — lineage runs and archive rows in one SQLite file
# ----------------------------------------------------------------------
def test_same_database_lineage_and_archive(tmp_path: Path) -> None:
    db_path = tmp_path / "single_lineage.db"
    store = LineageStore(str(db_path))
    world = WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1)
    store.record_run(
        RunRecord(run_id="sample00000000000000000001", world=world, metrics={"m": 1.0})
    )
    result = _session_result(seed=0, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    comparison = analyst.compare_adaptive_discovery([result], comparison_profile="default")
    store.record_adaptive_comparison(comparison)
    store.close()

    reopened = LineageStore(str(db_path))
    assert reopened.run_count == 1
    run = reopened.get_run("sample00000000000000000001")
    assert run is not None and run.metrics == {"m": 1.0}
    got = reopened.get_adaptive_comparison(comparison.comparison_id)
    assert got is not None and got["adaptive_comparison_id"] == comparison.comparison_id
    tables = {
        r[0]
        for r in reopened._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"runs", "adaptive_comparison_archive"} <= tables
    reopened.close()


# ----------------------------------------------------------------------
# Migration — a pre-2.9 store opens, keeps old data, gains the archive table
# ----------------------------------------------------------------------
def test_migration_from_pre_29_store(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_29.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(PRE_29_SCHEMA)
    # Seed pre-2.9 lineage: one run (with feature_snapshot + composition_id
    # columns, as post-2.4 stores had) and one exploration session.
    legacy_run = RunRecord(
        run_id="legacy00000000000000000001",
        world=WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1),
        metrics={"m": 1.0},
        feature_snapshot={"units": []},
        composition_id="comp_legacy",
    )
    kwargs = {"sort_keys": True, "separators": (",", ":")}
    conn.execute(
        """
        INSERT INTO runs (run_id, parent_run_id, world_id, world_hash, seed,
                          mutations, world_json, metrics, feature_snapshot,
                          composition_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            legacy_run.run_id,
            legacy_run.parent_run_id,
            legacy_run.world_id,
            legacy_run.world_hash,
            legacy_run.seed,
            "[]",
            json.dumps(legacy_run.world.as_dict(), **kwargs),
            json.dumps(legacy_run.metrics, **kwargs),
            json.dumps(legacy_run.feature_snapshot, **kwargs),
            legacy_run.composition_id,
            legacy_run.created_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO adaptive_exploration_sessions
            (adaptive_exploration_id, spec_dict, composition_ids, profile_text, seed,
             budget, pass_adaptive_run_ids, final_decision, termination_reason,
             total_simulated, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2f41779e1947f870b32140e3",
            "{}",
            '["C"]',
            "default",
            0,
            2,
            "[]",
            "STOP",
            "STOP",
            1,
            "VALID",
            "2026-09-10T00:00:00+00:00",
        ),
    )
    before_cols = [r[1] for r in conn.execute("PRAGMA table_info(runs)")]
    conn.commit()
    conn.close()

    store = LineageStore(str(db_path))
    # Archive table appears (schema + index).
    tables = {
        r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "adaptive_comparison_archive" in tables
    # Old lineage data remains readable.
    run = store.get_run("legacy00000000000000000001")
    assert run is not None
    assert run.feature_snapshot == {"units": []}
    assert run.composition_id == "comp_legacy"
    session = store.get_exploration_session("2f41779e1947f870b32140e3")
    assert session is not None
    assert session["adaptive_exploration_id"] == "2f41779e1947f870b32140e3"
    assert store.run_count == 1
    assert store.count_exploration_sessions() == 1
    # Old tables unchanged (no column altered by migration).
    after_cols = [r[1] for r in store._conn.execute("PRAGMA table_info(runs)")]
    assert after_cols == before_cols
    store.close()


# ----------------------------------------------------------------------
# Missing data — explicit None, never fabricated
# ----------------------------------------------------------------------
def test_missing_data_returns_none() -> None:
    store = LineageStore(":memory:")
    assert store.get_adaptive_comparison("00000000000000000000ffff") is None
    result = _session_result(seed=0, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    comparison = analyst.compare_adaptive_discovery([result], comparison_profile="default")
    store.record_adaptive_comparison(comparison)
    assert store.get_adaptive_comparison("00000000000000000000ffff") is None
    assert store.get_adaptive_comparison(comparison.comparison_id) is not None
    store.close()


# ----------------------------------------------------------------------
# No execution / no analysis by the archive layer
# ----------------------------------------------------------------------
def test_archive_layer_never_executes_or_analyzes_source_level() -> None:
    import ast

    path = Path(__file__).parents[1] / "src/sim_alchemist/core/lineage.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    hits = sorted(m for m in EXECUTION_OR_ANALYSIS_MODULES if m in imported)
    assert not hits, f"lineage.py must not import execution/analysis modules: {hits}"
    fine = [tok for tok in ANALYSIS_OR_EXECUTION_TOKENS if tok in source]
    assert not fine, f"lineage.py must not execute/analyze; found {fine}"


def test_archive_record_triggers_no_simulation_or_analysis() -> None:
    store = LineageStore(":memory:")
    result = _session_result(seed=0, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    comparison = analyst.compare_adaptive_discovery([result], comparison_profile="default")
    store.record_adaptive_comparison(comparison)
    # Persisting an already-computed comparison touches no execution/analysis
    # lineage (runs/sweeps/searches/behavior/exploration counters stay zero).
    assert store.run_count == 0
    assert store.sweep_count == 0
    assert store.search_count == 0
    assert store.behavior_analysis_count == 0
    assert store.count_exploration_sessions() == 0
    (archive_count,) = store._conn.execute(
        "SELECT COUNT(*) FROM adaptive_comparison_archive"
    ).fetchone()
    assert archive_count == 1
    store.close()