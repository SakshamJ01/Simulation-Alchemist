"""Task 2.9 Stage 2 — Deterministic archive consumption + audit/replay.

Verifies the read-only archive-consumption layer added on top of the
Stage 1 archive table:

  * iteration/listing — canonical ``adaptive_comparison_id`` ascending order
    regardless of database insertion order (never raw row order)
  * count / get by identity / explicit None for unknown ids
  * profile + session filtering — exact, deterministic, verbatim
  * replay/audit (``verify_adaptive_comparison``) — integrity verdicts
    derived *only* from the stored row; identity recomputation explicitly
    impossible from the archive alone; corruption detected, never repaired
  * feature linkage — deferred: the archive carries explicit
    ``feature_linkage.available`` / ``resolvable_from_archive: False`` state
    and never fabricates features, ranks, or frontier members
  * read-only guarantee — repeated reads leave row counts, contents, and the
    connection's write counter (``total_changes``) unchanged
  * no execution / no recomputation — retrieval never invokes a simulator,
    the analyst, a ranking, or a frontier primitive
  * migration/same-database — pre-2.9 and Stage 1 stores open safely

Synthetic-but-real session inputs are used for unit tests (as permitted);
the genuine real-data path (the Stage 1 persisted archive entry
`e7ca46439e8f874408a9e3c0`) is exercised in the temp proof script, and the
identity-reproduction test below locks the exact real comparison id to the
committed behaviour.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from test_adaptive_comparison_archive_stage1 import PRE_29_SCHEMA

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

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


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
    seed_a: int = 0,
    seed_b: int = 1,
    profile: str = "default",
) -> AdaptiveComparisonResult:
    res_a = _session_result(seed=seed_a, budget=2)
    res_b = _session_result(seed=seed_b, budget=2)
    analyst = AdaptiveDiscoveryAnalyst()
    feature_vectors = None
    if with_features:
        sids = sorted([res_a.exploration_id, res_b.exploration_id])
        feature_vectors = {sids[0]: [2.0, 1.0], sids[1]: [5.0, 3.0]}
    return analyst.compare_adaptive_discovery(
        [res_a, res_b],
        comparison_profile=profile,
        feature_vectors=feature_vectors,
    )


def _raw_insert(
    store: LineageStore,
    result: AdaptiveComparisonResult,
    *,
    status: str = "VALID",
    created_at: str = "2026-09-11T00:00:00+00:00",
) -> None:
    """Direct-SQL insert (bypasses the recording API) so tests can control
    physical insertion order and later tamper with stored fields."""
    kwargs = {"sort_keys": True, "separators": (",", ":")}
    store._conn.execute(
        """
        INSERT INTO adaptive_comparison_archive
            (adaptive_comparison_id, session_ids_json, profile_text,
             comparison_result_digest, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            result.comparison_id,
            json.dumps(sorted(result.source_session_ids), **kwargs),
            result.profile,
            json.dumps(
                {
                    "ranked_order": list(result.ranked_order),
                    "frontend_ids": list(result.frontend_ids),
                    "diagnostics": result.diagnostics,
                    "explanation": result.explanation,
                },
                **kwargs,
            ),
            status,
            created_at,
        ),
    )
    store._conn.commit()


# ----------------------------------------------------------------------
# A/B — iteration + deterministic canonical ordering (anti-false-pass #1)
# ----------------------------------------------------------------------
def test_iteration_canonical_order_despite_noncanonical_insertion() -> None:
    store = LineageStore(":memory:")
    comps = [_genuine_comparison(seed_a=i, seed_b=100 + i) for i in range(3)]
    ids = sorted(c.comparison_id for c in comps)
    assert len(set(ids)) == 3, "comparisons must be distinct"
    # Insert deliberately in reversed-canonical physical order.
    by_id = {c.comparison_id: c for c in comps}
    for cid in reversed(ids):
        _raw_insert(store, by_id[cid])
    # Prove the physical (rowid) order really is non-canonical: rowids were
    # assigned in reversed-id insertion order, so a raw table scan (forced here
    # by selecting a non-indexed column; the covering PK index would mask it)
    # returns the reverse of canonical.
    probe = [
        cid
        for cid, _ in store._conn.execute(
            "SELECT adaptive_comparison_id, session_ids_json "
            "FROM adaptive_comparison_archive"
        )
    ]
    assert probe == list(reversed(ids)), "setup must yield non-canonical physical row order"
    # The query layer must return canonical ascending order.
    got = [c["adaptive_comparison_id"] for c in store.iter_adaptive_comparisons()]
    assert got == ids
    found = [c["adaptive_comparison_id"] for c in store.find_adaptive_comparisons()]
    assert found == ids
    store.close()


def test_iteration_empty_store() -> None:
    store = LineageStore(":memory:")
    assert list(store.iter_adaptive_comparisons()) == []
    assert store.find_adaptive_comparisons() == []
    assert store.count_adaptive_comparisons() == 0
    store.close()


# ----------------------------------------------------------------------
# C/I — get by identity + distinct ids (anti-false-pass #2) + count
# ----------------------------------------------------------------------
def test_distinct_comparisons_remain_distinct() -> None:
    store = LineageStore(":memory:")
    a = _genuine_comparison(seed_a=0, seed_b=100)
    b = _genuine_comparison(seed_a=5, seed_b=200)
    assert a.comparison_id != b.comparison_id
    store.record_adaptive_comparison(a)
    store.record_adaptive_comparison(b)
    assert store.count_adaptive_comparisons() == 2
    ga = store.get_adaptive_comparison(a.comparison_id)
    gb = store.get_adaptive_comparison(b.comparison_id)
    assert ga is not None and ga["adaptive_comparison_id"] == a.comparison_id
    assert gb is not None and gb["adaptive_comparison_id"] == b.comparison_id
    assert ga["adaptive_comparison_id"] != gb["adaptive_comparison_id"]
    assert ga["session_ids"] == list(a.source_session_ids)
    assert gb["session_ids"] == list(b.source_session_ids)
    store.close()


# ----------------------------------------------------------------------
# H — missing archive / unknown id (anti-false-pass #3)
# ----------------------------------------------------------------------
def test_unknown_comparison_explicit_not_found() -> None:
    store = LineageStore(":memory:")
    cid = "00000000000000000000ffff"
    assert store.get_adaptive_comparison(cid) is None
    assert store.verify_adaptive_comparison(cid) is None
    assert store.find_adaptive_comparisons(session_id=cid) == []
    # Recording other rows must not change the not-found behaviour.
    store.record_adaptive_comparison(_genuine_comparison())
    assert store.get_adaptive_comparison(cid) is None
    assert store.verify_adaptive_comparison(cid) is None
    store.close()


# ----------------------------------------------------------------------
# D/E — profile + session filtering (exact, verbatim, deterministic)
# ----------------------------------------------------------------------
def test_find_filters_by_profile_and_session() -> None:
    store = LineageStore(":memory:")
    default_a = _genuine_comparison(seed_a=0, seed_b=100, profile="default")
    default_b = _genuine_comparison(seed_a=1, seed_b=101, profile="default")
    quality = _genuine_comparison(seed_a=2, seed_b=102, profile="quality")
    store.record_adaptive_comparison(default_a)
    store.record_adaptive_comparison(default_b)
    store.record_adaptive_comparison(quality)

    all_ids = sorted([default_a, default_b, quality], key=lambda c: c.comparison_id)
    expected_default_ids = sorted(
        [default_a, default_b], key=lambda c: c.comparison_id
    )
    expected_quality_ids = [quality.comparison_id]

    assert [
        c["adaptive_comparison_id"] for c in store.find_adaptive_comparisons()
    ] == [c.comparison_id for c in all_ids]
    assert [
        c["adaptive_comparison_id"]
        for c in store.find_adaptive_comparisons(profile="default")
    ] == [c.comparison_id for c in expected_default_ids]
    assert [
        c["adaptive_comparison_id"]
        for c in store.find_adaptive_comparisons(profile="quality")
    ] == expected_quality_ids
    # Profile matching is exact and verbatim: no normalization, no case folding.
    assert store.find_adaptive_comparisons(profile="DEFAULT") == []
    assert store.find_adaptive_comparisons(profile="default  ") == []

    # Session membership filtering is exact membership in the archived list;
    # comparisons produced from disjoint seed pairs share no sessions.
    a_sid = default_a.source_session_ids[0]
    assert a_sid not in default_b.source_session_ids
    by_a = [
        c["adaptive_comparison_id"]
        for c in store.find_adaptive_comparisons(session_id=a_sid)
    ]
    assert by_a == [default_a.comparison_id]
    b_sid = default_b.source_session_ids[0]
    by_b = [
        c["adaptive_comparison_id"]
        for c in store.find_adaptive_comparisons(session_id=b_sid)
    ]
    assert by_b == [default_b.comparison_id]
    # Unknown session id matches nothing.
    assert store.find_adaptive_comparisons(session_id="00000000000000000000ffff") == []
    # Combined filters.
    combined = store.find_adaptive_comparisons(profile="quality", session_id=a_sid)
    assert combined == []
    combined2 = store.find_adaptive_comparisons(
        profile="default", session_id=quality.source_session_ids[0]
    )
    assert combined2 == []
    store.close()


# ----------------------------------------------------------------------
# F/G — replay/audit semantics + integrity (no recomputation)
# ----------------------------------------------------------------------
def test_verify_ok_verdict_and_integrity_details() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=False)
    store.record_adaptive_comparison(result)

    audit = store.verify_adaptive_comparison(result.comparison_id)
    assert audit is not None
    assert audit["adaptive_comparison_id"] == result.comparison_id
    assert audit["session_ids"] == list(result.source_session_ids)
    assert audit["profile"] == result.profile
    assert audit["status"] == "VALID"
    assert audit["verdict"] == "OK"
    assert all(
        audit["integrity"][k] is True
        for k in (
            "adaptive_comparison_id_well_formed",
            "session_ids_well_formed",
            "session_ids_sorted",
            "result_digest_valid",
            "result_digest_well_formed",
            "ranked_frontier_within_sessions",
            "profile_well_formed",
            "status_well_formed",
            "created_at_well_formed",
            "consistent",
        )
    )
    # Identity cannot be fully recomputed from the archive alone (documented).
    assert audit["identity_recomputable"] is False
    assert audit["identity_recomputable_reason"]
    # Feature linkage resolvable-at-replay never lies.
    assert audit["feature_linkage"]["resolvable_from_archive"] is False
    assert audit["feature_linkage"]["reason"]
    store.close()


def test_verify_detects_feature_use_from_stored_digest() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=True)
    assert result.ranked_order and result.frontend_ids
    store.record_adaptive_comparison(result)
    audit = store.verify_adaptive_comparison(result.comparison_id)
    assert audit is not None
    assert audit["verdict"] == "OK"
    # Derived from the stored digest diagnostics -- never recomputed.
    assert audit["feature_linkage"]["available"] is True
    assert audit["feature_linkage"]["resolvable_from_archive"] is False
    assert set(audit["result_digest"]["ranked_order"]) <= set(audit["session_ids"])
    assert set(audit["result_digest"]["frontend_ids"]) <= set(audit["session_ids"])
    store.close()


# ----------------------------------------------------------------------
# P — explicit missing-feature evidence (anti-false-pass #6)
# ----------------------------------------------------------------------
def test_verify_reports_missing_feature_state_honestly() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=False)
    store.record_adaptive_comparison(result)
    audit = store.verify_adaptive_comparison(result.comparison_id)
    assert audit is not None
    assert audit["result_digest"]["ranked_order"] == []
    assert audit["result_digest"]["frontend_ids"] == []
    assert "Missing durable feature data" in audit["result_digest"]["explanation"]
    assert audit["feature_linkage"]["available"] is False
    assert audit["feature_linkage"]["resolvable_from_archive"] is False
    assert audit["verdict"] == "OK", "missing features is an honest state, not corruption"
    store.close()


# ----------------------------------------------------------------------
# S — corruption detection (anti-false-pass #5); never repaired
# ----------------------------------------------------------------------
def test_verify_detects_corrupted_digest_and_never_repairs() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    cid = result.comparison_id

    # Corrupt the stored digest to invalid JSON.
    store._conn.execute(
        "UPDATE adaptive_comparison_archive SET comparison_result_digest = ? "
        "WHERE adaptive_comparison_id = ?",
        ("{definitely not json", cid),
    )
    store._conn.commit()
    audit = store.verify_adaptive_comparison(cid)
    assert audit is not None
    assert audit["verdict"] == "CORRUPT"
    assert audit["integrity"]["result_digest_valid"] is False
    assert audit["integrity"]["consistent"] is False
    # No silent repair: the raw row is still corrupt after verify.
    raw = store._conn.execute(
        "SELECT comparison_result_digest FROM adaptive_comparison_archive "
        "WHERE adaptive_comparison_id = ?",
        (cid,),
    ).fetchone()
    assert raw[0] == "{definitely not json"
    second = store.verify_adaptive_comparison(cid)
    assert second is not None
    assert second["verdict"] == "CORRUPT"
    store.close()


def test_verify_detects_digest_referencing_unknown_session() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison(with_features=True)
    store.record_adaptive_comparison(result)
    cid = result.comparison_id

    # Tamper: ranked_order names an id that is not among the archived sessions.
    raw = store.get_adaptive_comparison(cid)
    assert raw is not None
    digest = raw["result_digest"]
    digest["ranked_order"] = ["ffffffffffffffffffffffff"]
    kwargs = {"sort_keys": True, "separators": (",", ":")}
    store._conn.execute(
        "UPDATE adaptive_comparison_archive SET comparison_result_digest = ? "
        "WHERE adaptive_comparison_id = ?",
        (json.dumps(digest, **kwargs), cid),
    )
    store._conn.commit()
    audit = store.verify_adaptive_comparison(cid)
    assert audit is not None
    assert audit["verdict"] == "CORRUPT"
    assert audit["integrity"]["ranked_frontier_within_sessions"] is False
    store.close()


def test_verify_detects_null_digest() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    cid = result.comparison_id
    store._conn.execute(
        "UPDATE adaptive_comparison_archive SET comparison_result_digest = NULL "
        "WHERE adaptive_comparison_id = ?",
        (cid,),
    )
    store._conn.commit()
    audit = store.verify_adaptive_comparison(cid)
    assert audit is not None
    assert audit["verdict"] == "CORRUPT"
    assert audit["integrity"]["result_digest_valid"] is False
    store.close()


def test_verify_detects_unsorted_session_ids() -> None:
    store = LineageStore(":memory:")
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    cid = result.comparison_id
    store._conn.execute(
        "UPDATE adaptive_comparison_archive SET session_ids_json = ? "
        "WHERE adaptive_comparison_id = ?",
        (json.dumps(list(reversed(result.source_session_ids))), cid),
    )
    store._conn.commit()
    audit = store.verify_adaptive_comparison(cid)
    assert audit is not None
    assert audit["verdict"] == "CORRUPT"
    assert audit["integrity"]["session_ids_sorted"] is False
    store.close()


# ----------------------------------------------------------------------
# J/R — read-only guarantee + deterministic repeated reads (anti-false-pass #4)
# ----------------------------------------------------------------------
def test_repeated_replay_is_read_only_and_deterministic() -> None:
    store = LineageStore(":memory:")
    comps = [_genuine_comparison(seed_a=i, seed_b=100 + i, profile=p)
             for i, p in enumerate(["default", "quality", "default"])]
    for c in comps:
        store.record_adaptive_comparison(c)

    (count_before,) = store._conn.execute(
        "SELECT COUNT(*) FROM adaptive_comparison_archive"
    ).fetchone()
    total_changes_before = store._conn.total_changes

    def snapshot() -> tuple:
        return (
            list(store.iter_adaptive_comparisons()),
            store.find_adaptive_comparisons(profile="default"),
            store.find_adaptive_comparisons(session_id=comps[0].source_session_ids[0]),
            [store.verify_adaptive_comparison(c.comparison_id) for c in comps],
        )

    first = snapshot()
    second = snapshot()

    assert first == second, "repeated reads must be deterministic"
    assert store.count_adaptive_comparisons() == count_before
    assert store._conn.total_changes == total_changes_before, (
        "read/replay paths must issue no INSERT/UPDATE/DELETE/REPLACE"
    )
    # Row contents unchanged.
    raw_after = [
        r[0]
        for r in store._conn.execute(
            "SELECT adaptive_comparison_id FROM adaptive_comparison_archive "
            "ORDER BY adaptive_comparison_id"
        )
    ]
    assert raw_after == sorted(c.comparison_id for c in comps)
    store.close()


# ----------------------------------------------------------------------
# K/L — no simulation, no recomputation (anti-false-pass #7)
# ----------------------------------------------------------------------
def test_read_paths_never_record_nor_write() -> None:
    store = LineageStore(":memory:")
    comps = [_genuine_comparison(seed_a=i, seed_b=100 + i) for i in range(3)]
    for c in comps:
        store.record_adaptive_comparison(c)

    # Spy: any write via the recording API during a read is a failure.
    def _spy(*args: object, **kwargs: object) -> None:
        raise AssertionError("record_adaptive_comparison invoked during read path")

    store.record_adaptive_comparison = _spy  # type: ignore[method-assign]

    before = (
        store.run_count,
        store.sweep_count,
        store.search_count,
        store.behavior_analysis_count,
        store.count_exploration_sessions(),
        store._conn.total_changes,
    )
    for c in comps:
        assert store.get_adaptive_comparison(c.comparison_id) is not None
        assert store.verify_adaptive_comparison(c.comparison_id) is not None
    assert len(list(store.iter_adaptive_comparisons())) == 3
    assert store.find_adaptive_comparisons() != []
    assert store.count_adaptive_comparisons() == 3

    after = (
        store.run_count,
        store.sweep_count,
        store.search_count,
        store.behavior_analysis_count,
        store.count_exploration_sessions(),
        store._conn.total_changes,
    )
    assert before == after, "read paths must not write or create analysis/simulation records"
    store.close()


def test_read_paths_contain_no_analysis_imports_or_execution_tokens() -> None:
    import ast as _ast

    path = Path(__file__).parents[1] / "src/sim_alchemist/core/lineage.py"
    source = path.read_text(encoding="utf-8")
    tree = _ast.parse(source)

    imported: list[str] = []
    for node in tree.body:
        if isinstance(node, _ast.Import):
            imported.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    forbidden_modules = {
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
    }
    hits = sorted(m for m in forbidden_modules if m in imported)
    assert not hits, f"lineage.py must not import execution/analysis modules: {hits}"

    # The Stage 2 read methods must be SELECT-only: no write verbs in their bodies.
    read_methods = {
        "iter_adaptive_comparisons",
        "count_adaptive_comparisons",
        "find_adaptive_comparisons",
        "verify_adaptive_comparison",
    }
    write_tokens = ("INSERT ", "UPDATE ", "DELETE ", " OR REPLACE")
    analysis_tokens = (
        "AdaptiveDiscoveryAnalyst",
        "behavior_distance",
        "rank_by_profile",
        "select_diverse_frontier",
        "select_frontier",
        ".step(",
        "SweepRunner",
        "compose(",
    )
    for klass in (n for n in tree.body if isinstance(n, _ast.ClassDef)):
        for node in klass.body:
            if isinstance(node, _ast.FunctionDef) and node.name in read_methods:
                body_src = _ast.get_source_segment(source, node) or ""
                for tok in write_tokens:
                    assert tok not in body_src, (
                        f"{node.name} must be read-only; found write token {tok!r}"
                    )
                for tok in analysis_tokens:
                    assert tok not in body_src, (
                        f"{node.name} must not analyze/execute; found {tok!r}"
                    )


# ----------------------------------------------------------------------
# M — same database
# ----------------------------------------------------------------------
def test_same_database_lineage_archive_and_stage2_queries(tmp_path: Path) -> None:
    db_path = tmp_path / "stage2_single.db"
    store = LineageStore(str(db_path))
    world = WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1)
    store.record_run(
        RunRecord(run_id="stage20000000000000000001", world=world, metrics={"m": 1.0})
    )
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    store.close()

    reopened = LineageStore(str(db_path))
    assert reopened.run_count == 1
    assert reopened.count_adaptive_comparisons() == 1
    assert [c["adaptive_comparison_id"] for c in reopened.iter_adaptive_comparisons()] == [
        result.comparison_id
    ]
    audit = reopened.verify_adaptive_comparison(result.comparison_id)
    assert audit is not None
    assert audit["verdict"] == "OK"
    tables = {
        r[0]
        for r in reopened._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"runs", "adaptive_comparison_archive"} <= tables
    reopened.close()


# ----------------------------------------------------------------------
# N — migration compatibility: pre-2.9 and Stage 1 stores
# ----------------------------------------------------------------------
def test_pre_29_store_opens_and_gains_stage2_query_layer(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_stage2.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(PRE_29_SCHEMA)
    conn.commit()
    conn.close()

    store = LineageStore(str(db_path))
    assert store.count_adaptive_comparisons() == 0
    assert list(store.iter_adaptive_comparisons()) == []
    assert store.verify_adaptive_comparison("00000000000000000000ffff") is None
    result = _genuine_comparison()
    store.record_adaptive_comparison(result)
    audit = store.verify_adaptive_comparison(result.comparison_id)
    assert audit is not None
    assert audit["verdict"] == "OK"
    store.close()

    reopened = LineageStore(str(db_path))
    assert reopened.find_adaptive_comparisons(profile="default") != []
    assert reopened.count_adaptive_comparisons() == 1
    reopened.close()


def test_stage1_store_schema_unchanged_by_stage2() -> None:
    store = LineageStore(":memory:")
    store.record_adaptive_comparison(_genuine_comparison())
    cols_before = [
        r[1]
        for r in store._conn.execute("PRAGMA table_info(adaptive_comparison_archive)")
    ]
    assert len(list(store.iter_adaptive_comparisons())) == 1
    store.record_adaptive_comparison(_genuine_comparison(seed_a=9, seed_b=99))
    cols_after = [
        r[1]
        for r in store._conn.execute("PRAGMA table_info(adaptive_comparison_archive)")
    ]
    assert cols_after == cols_before
    store.close()


# ----------------------------------------------------------------------
# Q — real-data identity reproduction (locks the genuine Stage 1 proof id)
# ----------------------------------------------------------------------
def test_real_session_comparison_identity_reproduced() -> None:
    # The genuine persisted archive entry from the Stage 1 real-data proof:
    # comparison e7ca46439e8f874408a9e3c0 over the real durable session
    # 2f41779e1947f870b32140e3 (temp_lineage.db) + canonical session id
    # c592521de654e7c165d8ec15, profile "default", no feature vectors.
    real_ids = ("2f41779e1947f870b32140e3", "c592521de654e7c165d8ec15")
    sessions = [
        AdaptiveExplorationResult(
            exploration_id=sid,
            spec_dict={"composition_ids": ["C"], "profile": "default", "seed": 0, "budget": 2},
            status=AdaptiveExplorationStatus(
                status="VALID",
                reason="",
                eligible_compositions=("C",),
                constrained_subspace_size=1,
                explanation="",
            ),
            eligible_compositions=("C",),
            subspace_size=1,
            explanation="",
        )
        for sid in real_ids
    ]
    analyst = AdaptiveDiscoveryAnalyst()
    result = analyst.compare_adaptive_discovery(sessions, comparison_profile="default")
    assert result.comparison_id == "e7ca46439e8f874408a9e3c0"
    assert result.source_session_ids == real_ids
    assert result.profile == "default"

    store = LineageStore(":memory:")
    store.record_adaptive_comparison(result)
    got = store.get_adaptive_comparison("e7ca46439e8f874408a9e3c0")
    assert got is not None
    assert got["session_ids"] == list(real_ids)
    audit = store.verify_adaptive_comparison("e7ca46439e8f874408a9e3c0")
    assert audit is not None and audit["verdict"] == "OK"
    assert audit["feature_linkage"]["available"] is False
    assert audit["feature_linkage"]["resolvable_from_archive"] is False
    assert audit["result_digest"]["ranked_order"] == []
    assert audit["result_digest"]["frontend_ids"] == []
    store.close()