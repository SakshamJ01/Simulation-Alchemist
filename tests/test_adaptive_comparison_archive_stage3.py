"""Task 2.9 Stage 3 — Authoritative feature linkage + real archive tooling.

Stage 3 completes the archive capability under **OUTCOME B**: the evidence
audit shows the real repository stores no authoritative durable per-run
feature chain for adaptive passes (adaptive pass run ids are content-addressed
adaptive-run identities, not ``runs.run_id`` values; ``runs.feature_snapshot``
is never populated for them; ``behavior_analyses`` is empty).  Stage 3
therefore:

  * preserves explicit *unavailable* semantics (no feature fabrication)
  * adds ``LineageStore.feature_linkage_of`` — a deterministic, read-only,
    evidence-grounded resolver that walks the archive row's authoritative
    source-session references into the durable exploration-session / run
    records and reports exactly what exists (reusing ``runs.run_id`` as the
    resolved identity; never inventing a feature id, values, or a chain)
  * adds a strict real-mode, read-only archive CLI
    (``run_adaptive_comparison_archive.py``) with explicit error semantics:
    unknown != corrupt != missing database != invalid filter, and no silent
    fallback data

The feature-linkage *available* path is exercised with synthetic-but-real
schema records (as permitted): an archived comparison whose source sessions
exist and whose pass run ids resolve to ``runs`` rows carrying a real
``feature_snapshot`` must resolve ``available=True`` through those actual
authoritative ids.

Tests below use only temporary or in-memory stores; the genuine repository
proof (comparison ``e7ca46439e8f874408a9e3c0``) is exercised by the temp real-
data script, and the identity is locked by the Stage 2 suite.
"""
from __future__ import annotations

import ast
import sqlite3
import subprocess
import sys
from pathlib import Path

from test_adaptive_comparison_archive_stage1 import PRE_29_SCHEMA
from test_adaptive_comparison_archive_stage2 import (
    _genuine_comparison,
)

from sim_alchemist.core.lineage import LineageStore, RunRecord
from sim_alchemist.core.world import WorldDefinition

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = "run_adaptive_comparison_archive.py"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _world() -> WorldDefinition:
    return WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1)


def _record_session(
    store: LineageStore,
    session_id: str,
    pass_run_ids: list[str],
    *,
    status: str = "VALID",
    created_at: str = "2026-09-11T00:00:00+00:00",
) -> None:
    store.record_exploration_session(
        session_id=session_id,
        spec_dict={"composition_ids": ["C"], "profile": "default", "seed": 0, "budget": 2},
        eligible_compositions=["C"],
        profile_text="default",
        seed=0,
        budget=2,
        pass_adaptive_run_ids=pass_run_ids,
        final_decision="STOP",
        termination_reason="BUDGET_EXHAUSTED",
        total_simulated=len(pass_run_ids),
        status=status,
        created_at=created_at,
    )


def _record_run_with_features(
    store: LineageStore,
    run_id: str,
    *,
    features: bool,
    created_at: str = "2026-09-11T00:00:00+00:00",
) -> None:
    store.record_run(
        RunRecord(
            run_id=run_id,
            world=_world(),
            metrics={"final_field_mean": 0.5},
            feature_snapshot={"features": {"x": 1.0}} if features else None,
            created_at=created_at,
        )
    )


def _run_cli(db: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, CLI, str(db), *argv],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


# ----------------------------------------------------------------------
# A — legacy archive rows remain readable with explicit linkage state
# ----------------------------------------------------------------------
def test_pre_29_store_reads_and_reports_unavailable_linkage(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_stage3.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(PRE_29_SCHEMA)
    conn.commit()
    conn.close()

    store = LineageStore(str(db_path))
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    cid = result.comparison_id

    assert store.get_adaptive_comparison(cid) is not None
    audit = store.verify_adaptive_comparison(cid)
    assert audit is not None and audit["verdict"] == "OK"
    linkage = store.feature_linkage_of(cid)
    assert linkage is not None
    assert linkage["available"] is False
    assert linkage["resolvable"] is False
    assert linkage["source_ids"] == list(result.source_session_ids)
    assert linkage["resolved_feature_sources"] == []
    assert store.feature_linkage_of("00000000000000000000ffff") is None
    store.close()

    reopened = LineageStore(str(db_path))
    assert reopened.get_adaptive_comparison(cid) is not None
    reopened.close()


def test_archive_only_row_without_sessions_is_explicitly_unavailable() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    assert linkage["available"] is False
    assert linkage["resolvable"] is False
    assert linkage["resolved_feature_sources"] == []
    assert all(not item["session_present"] for item in linkage["evidence"])
    store.close()


# ----------------------------------------------------------------------
# B — available path resolves through authoritative run ids (anti-false-pass)
# ----------------------------------------------------------------------
def test_feature_linkage_resolves_through_authoritative_run_ids() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=True)
    assert result.ranked_order and result.frontend_ids
    store.record_adaptive_comparison(result)
    sids = list(result.source_session_ids)
    pass_ids = ["aaaa00000000000000000001", "aaaa00000000000000000002"]
    _record_session(store, sids[0], [pass_ids[0]])
    _record_session(store, sids[1], [pass_ids[1]])
    # Only sids[0]'s pass run carries a durable feature snapshot; the other
    # pass run id exists but has no feature snapshot.
    _record_run_with_features(store, pass_ids[0], features=True)
    _record_run_with_features(store, pass_ids[1], features=False)

    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    assert linkage["available"] is True
    assert linkage["resolvable"] is True
    # The resolved identity is the authoritative runs.run_id — reused, never invented.
    assert linkage["resolved_feature_sources"] == [pass_ids[0]]
    assert pass_ids[0] in [
        f["pass_run_id"]
        for item in linkage["evidence"]
        if item["session_present"]
        for f in item["pass_run_ids"]
        if f["run_present"]
    ]
    code = store._conn.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()
    assert [r[0] for r in code] == sorted(pass_ids)
    store.close()


def test_feature_linkage_available_is_deterministic() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=True)
    store.record_adaptive_comparison(result)
    for sid in result.source_session_ids:
        _record_session(store, sid, ["bbbb00000000000000000001"])
        _record_run_with_features(store, "bbbb00000000000000000001", features=True)
    first = store.feature_linkage_of(result.comparison_id)
    second = store.feature_linkage_of(result.comparison_id)
    assert first is not None and second is not None
    assert first == second
    assert first["available"] is True
    assert first["resolved_feature_sources"] == ["bbbb00000000000000000001"]
    store.close()


# ----------------------------------------------------------------------
# C — unavailable stays unavailable, with evidence, never fabricated
# ----------------------------------------------------------------------
def test_sessions_present_but_no_run_chain_stays_unavailable() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    for sid in result.source_session_ids:
        _record_session(store, sid, ["cccc00000000000000000001"])
    # The pass run id does not reference any runs row.
    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    assert linkage["available"] is False
    assert linkage["resolvable"] is False
    assert linkage["resolved_feature_sources"] == []
    for item in linkage["evidence"]:
        assert item["session_present"] is True
        assert item["pass_run_ids"][0]["run_present"] is False
    assert "runs.feature_snapshot" in linkage["reason"]
    store.close()


def test_partially_missing_sessions_reported_explicitly() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    sids = list(result.source_session_ids)
    _record_session(store, sids[0], ["dddd00000000000000000001"])
    # sids[1] is deliberately absent from adaptive_exploration_sessions.
    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    assert linkage["available"] is False
    assert sids[1] not in [
        item["session_id"] for item in linkage["evidence"] if item["session_present"]
    ]
    assert any(item["session_id"] == sids[1] and not item["session_present"] for item in linkage["evidence"])
    assert "absent from adaptive_exploration_sessions" in linkage["reason"]
    store.close()


def test_no_feature_values_are_fabricated_when_unavailable() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    for sid in result.source_session_ids:
        _record_session(store, sid, ["eeee00000000000000000001"])
    _record_run_with_features(store, "eeee00000000000000000001", features=False)
    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    # The run exists but carries no durable feature snapshot: the resolver
    # reports absence explicitly and invents nothing.
    assert linkage["available"] is False
    assert linkage["resolved_feature_sources"] == []
    for item in linkage["evidence"]:
        for f in item["pass_run_ids"]:
            assert f["run_present"] is True
            assert f["feature_snapshot_present"] is False
    for key in linkage:
        assert key not in ("feature_values", "features", "feature_vectors"), (
            "linkage must never carry or synthesize feature values"
        )
    store.close()


def test_linkage_reports_source_identity_not_values() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    for sid in result.source_session_ids:
        _record_session(store, sid, ["efef00000000000000000001"])
    _record_run_with_features(store, "efef00000000000000000001", features=True)
    linkage = store.feature_linkage_of(result.comparison_id)
    assert linkage is not None
    assert linkage["available"] is True
    assert linkage["resolvable"] is True
    assert linkage["resolved_feature_sources"] == ["efef00000000000000000001"]
    for key in linkage:
        assert key not in ("feature_values", "features", "feature_vectors"), (
            "linkage must never carry or synthesize feature values"
        )
    store.close()


# ----------------------------------------------------------------------
# E — read-only + no source mutation (zero-write reads)
# ----------------------------------------------------------------------
def test_read_paths_and_linkage_resolution_never_write(tmp_path: Path) -> None:
    db_path = tmp_path / "readonly.db"
    store = LineageStore(str(db_path))
    comps = [_genuine_comparison(seed_a=i, seed_b=100 + i) for i in range(2)]
    for c in comps:
        store.record_adaptive_comparison(c)
    for c in comps:
        _record_session(store, c.source_session_ids[0], ["ffff00000000000000000001"])
        _record_run_with_features(store, "ffff00000000000000000001", features=True)
    store.close()

    store = LineageStore(str(db_path))
    total_before = store._conn.total_changes
    runs_before = [
        tuple(r) for r in store._conn.execute("SELECT * FROM runs ORDER BY run_id")
    ]
    sessions_before = [
        tuple(r)
        for r in store._conn.execute(
            "SELECT * FROM adaptive_exploration_sessions ORDER BY adaptive_exploration_id"
        )
    ]
    archive_before = [
        tuple(r)
        for r in store._conn.execute(
            "SELECT * FROM adaptive_comparison_archive ORDER BY adaptive_comparison_id"
        )
    ]
    for c in comps:
        assert store.get_adaptive_comparison(c.comparison_id) is not None
        assert store.verify_adaptive_comparison(c.comparison_id) is not None
        assert store.feature_linkage_of(c.comparison_id) is not None
    assert len(list(store.iter_adaptive_comparisons())) == 2
    assert store.find_adaptive_comparisons(profile="default") != []
    assert store.count_adaptive_comparisons() == 2
    assert store._conn.total_changes == total_before
    assert [
        tuple(r) for r in store._conn.execute("SELECT * FROM runs ORDER BY run_id")
    ] == runs_before
    assert [
        tuple(r)
        for r in store._conn.execute(
            "SELECT * FROM adaptive_exploration_sessions ORDER BY adaptive_exploration_id"
        )
    ] == sessions_before
    assert [
        tuple(r)
        for r in store._conn.execute(
            "SELECT * FROM adaptive_comparison_archive ORDER BY adaptive_comparison_id"
        )
    ] == archive_before
    store.close()


def test_feature_linkage_of_is_select_only() -> None:
    path = REPO_ROOT / "src/sim_alchemist/core/lineage.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for klass in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LineageStore"):
        for node in klass.body:
            if isinstance(node, ast.FunctionDef) and node.name == "feature_linkage_of":
                body_src = ast.get_source_segment(source, node) or ""
                for tok in ("INSERT ", "UPDATE ", "DELETE ", " OR REPLACE", ".commit()"):
                    assert tok not in body_src, f"feature_linkage_of must be SELECT-only; found {tok!r}"
                for tok in (
                    "AdaptiveDiscoveryAnalyst",
                    "rank_by_profile",
                    "behavior_distance",
                    "select_diverse_frontier",
                    "rank_compositions",
                    "select_frontier",
                ):
                    assert tok not in body_src, f"feature_linkage_of must not analyze; found {tok!r}"


# ----------------------------------------------------------------------
# G/H/I — CLI real-data + error semantics + ordering
# ----------------------------------------------------------------------
def _seed_cli_db(tmp_path: Path, *, with_features: bool = False) -> tuple[Path, str]:
    db_path = tmp_path / "cli.db"
    store = LineageStore(str(db_path))
    result = _genuine_comparison(with_features=with_features)
    store.record_adaptive_comparison(result)
    outcome = result.comparison_id
    store.close()
    return db_path, outcome


def test_cli_get_list_find_verify_link_real_path(tmp_path: Path) -> None:
    db, cid = _seed_cli_db(tmp_path)
    proc = _run_cli(db, "get", cid)
    assert proc.returncode == 0, proc.stderr
    assert f"[ARCHIVE-GET] adaptive_comparison_id: {cid}" in proc.stdout
    assert "[ARCHIVE-READ-ONLY] total_changes unchanged: 0" in proc.stdout

    proc = _run_cli(db, "list")
    assert proc.returncode == 0
    assert f"[ARCHIVE-LIST] {cid} default VALID" in proc.stdout

    proc = _run_cli(db, "find", "--profile", "default")
    assert proc.returncode == 0
    assert f"[ARCHIVE-FIND] {cid} default VALID" in proc.stdout
    assert "[ARCHIVE-FIND] matches: 1" in proc.stdout

    proc = _run_cli(db, "verify", cid)
    assert proc.returncode == 0
    assert "[ARCHIVE-VERIFY] verdict: OK" in proc.stdout
    assert "[ARCHIVE-VERIFY] identity_recomputable: False" in proc.stdout

    proc = _run_cli(db, "link", cid)
    assert proc.returncode == 0
    assert "[ARCHIVE-LINK] available: False" in proc.stdout
    assert "[ARCHIVE-LINK] resolvable: False" in proc.stdout


def test_cli_unknown_comparison_is_distinct_from_corrupt(tmp_path: Path) -> None:
    db, cid = _seed_cli_db(tmp_path)
    unknown = _run_cli(db, "get", "ffffffffffffffffffffffff")
    assert unknown.returncode == 30
    assert "unknown comparison" in unknown.stderr

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE adaptive_comparison_archive SET comparison_result_digest = ? "
        "WHERE adaptive_comparison_id = ?",
        ("{not json", cid),
    )
    conn.commit()
    conn.close()

    corrupt_get = _run_cli(db, "get", cid)
    corrupt_verify = _run_cli(db, "verify", cid)
    corrupt_link = _run_cli(db, "link", cid)
    for proc in (corrupt_get, corrupt_verify, corrupt_link):
        assert proc.returncode == 40, (proc.returncode, proc.stdout, proc.stderr)
        assert "CORRUPT" in proc.stdout + proc.stderr
        assert "unknown comparison" not in proc.stdout + proc.stderr
    # Corruption is never repaired: the raw row keeps the tampered digest.
    conn = sqlite3.connect(db)
    raw = conn.execute(
        "SELECT comparison_result_digest FROM adaptive_comparison_archive "
        "WHERE adaptive_comparison_id = ?",
        (cid,),
    ).fetchone()
    conn.close()
    assert raw[0] == "{not json"


def test_cli_missing_database_and_legacy_schema_are_explicit(tmp_path: Path) -> None:
    missing = _run_cli(tmp_path / "absent.db", "list")
    assert missing.returncode == 20
    assert "database file does not exist" in missing.stderr

    db_path = tmp_path / "schema_less.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    conn.close()
    proc = _run_cli(db_path, "list")
    assert proc.returncode == 50
    assert "missing the required archive tables" in proc.stderr
    # The database file must remain untouched (no schema was created).
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables == {"t"}


def test_cli_invalid_filter_is_explicit(tmp_path: Path) -> None:
    db, _ = _seed_cli_db(tmp_path)
    proc = subprocess.run(
        [sys.executable, CLI, str(db), "find", "--profile", ""],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 10
    assert "must not be empty" in proc.stderr


def test_cli_list_keeps_canonical_api_order(tmp_path: Path) -> None:
    db_path = tmp_path / "order.db"
    store = LineageStore(str(db_path))
    comps = [_genuine_comparison(seed_a=i, seed_b=200 + i) for i in range(3)]
    for c in comps:
        store.record_adaptive_comparison(c)
    store.close()
    api_ids = [
        c["adaptive_comparison_id"]
        for c in LineageStore(str(db_path)).iter_adaptive_comparisons()
    ]
    assert api_ids == sorted(api_ids)
    proc = _run_cli(db_path, "list")
    assert proc.returncode == 0
    cli_ids = [
        line.split(" ")[1]
        for line in proc.stdout.splitlines()
        if line.startswith("[ARCHIVE-LIST] ") and not line.startswith("[ARCHIVE-LIST] count:")
    ]
    assert cli_ids == api_ids


def test_cli_repeated_invocation_is_deterministic(tmp_path: Path) -> None:
    db, cid = _seed_cli_db(tmp_path)
    first = _run_cli(db, "verify", cid)
    second = _run_cli(db, "verify", cid)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr


# ----------------------------------------------------------------------
# J — CLI purity: no analysis/ranking/frontier reimplementation
# ----------------------------------------------------------------------
def test_cli_contains_no_analysis_or_ranking_logic() -> None:
    source = (REPO_ROOT / CLI).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    forbidden_imports = {
        "behavior",
        "composition_analysis",
        "composition_search",
        "adaptive_comparison",
        "adaptive_sweep",
        "adaptive_exploration_runner",
        "search",
        "sweep",
        "runner",
    }
    hits = sorted(m for m in forbidden_imports if m in imported)
    assert not hits, f"CLI must not import analysis/execution modules: {hits}"
    for tok in (
        "rank_by_profile",
        "select_diverse_frontier",
        "behavior_distance",
        "AdaptiveDiscoveryAnalyst",
        "rank_compositions",
        "select_frontier",
    ):
        assert tok not in source, f"CLI must not reimplement analysis; found {tok!r}"
    assert "feature_linkage_of" in source, "CLI must delegate linkage to the store API"


def test_lineage_keeps_core_purity() -> None:
    source = (REPO_ROOT / "src/sim_alchemist/core/lineage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    forbidden_modules = {
        "adaptive_comparison",
        "adaptive_sweep",
        "behavior",
        "composition_analysis",
        "composition_search",
        "composer",
        "engine",
        "runner",
        "search",
        "sweep",
    }
    hits = sorted(m for m in forbidden_modules if m in imported)
    assert not hits, f"lineage.py must stay import-pure: {hits}"