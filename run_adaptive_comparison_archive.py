#!/usr/bin/env python
"""Task 2.9 Build Stage 3 — Adaptive comparison archive CLI.

Strict real-mode, read-only tooling for the persistent adaptive-comparison
archive (``adaptive_comparison_archive`` inside a ``LineageStore`` database).

Contract
--------
- Operates on a real ``LineageStore`` SQLite database file only.  There is no
  demo world, no synthetic archive row, and no *fallback* data: a missing
  database, an unknown comparison, or a corrupt row is an explicit error with
  a distinct exit code.
- Every command is read-only (SELECT-only).  The CLI proves it by checking
  that ``sqlite3`` ``total_changes`` is unchanged after the command, and it
  refuses to run against a database whose schema would need to be *created*
  on open (migration-write).
- All output is deterministic (canonical archive order from the store API,
  ``sort_keys`` JSON).  No ranking/frontier/diversity logic is reimplemented
  here: the CLI only calls the existing ``LineageStore`` archive APIs.
- ``link`` explains *why* feature evidence is or is not available by resolving
  the archived source references against the durable exploration-session and
  per-run feature records (``LineageStore.feature_linkage_of``).  Feature
  values are never fabricated, re-derived, or inferred.

Exit codes: 0 success; 10 invalid filter; 20 missing database; 30 unknown
comparison; 40 corrupt archive row; 50 write detected on a read command.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, "src")

from sim_alchemist.core.lineage import LineageStore

EXIT_OK = 0
EXIT_ERR = 1
EXIT_INVALID_FILTER = 10
EXIT_DB_MISSING = 20
EXIT_UNKNOWN_COMPARISON = 30
EXIT_CORRUPT = 40
EXIT_WRITE_DETECTED = 50

REQUIRED_TABLES = {
    "adaptive_comparison_archive": (
        "adaptive_comparison_id",
        "session_ids_json",
        "profile_text",
        "comparison_result_digest",
        "status",
        "created_at",
    ),
    "adaptive_exploration_sessions": ("adaptive_exploration_id", "pass_adaptive_run_ids"),
    "runs": ("run_id", "feature_snapshot"),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only archive tooling for adaptive comparisons "
        "(strict real mode; explicit errors only)."
    )
    p.add_argument("db", type=str, help="path to the LineageStore SQLite database (real archive)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="list archived comparisons in canonical order")
    sp.add_argument(
        "--profile",
        type=str,
        default=None,
        help="exact profile filter (verbatim match, no normalization)",
    )
    sp.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="exact source-session membership filter",
    )
    sp.set_defaults(handler=_cmd_list)

    sp = sub.add_parser("get", help="print one archived comparison record")
    sp.add_argument("comparison_id", type=str)
    sp.set_defaults(handler=_cmd_get)

    sp = sub.add_parser("find", help="print archived comparisons matching exact filters")
    sp.add_argument("--profile", type=str, default=None)
    sp.add_argument("--session-id", type=str, default=None)
    sp.set_defaults(handler=_cmd_find)

    sp = sub.add_parser("verify", help="deterministic audit/replay of one archived comparison")
    sp.add_argument("comparison_id", type=str)
    sp.set_defaults(handler=_cmd_verify)

    sp = sub.add_parser("link", help="resolve whether authoritative durable feature evidence exists")
    sp.add_argument("comparison_id", type=str)
    sp.set_defaults(handler=_cmd_link)
    return p


def _validate_db_schema_readonly(db_path: str) -> None:
    """Verify the archive schema exists using a true ``mode=ro`` connection.

    This runs *before* the store is opened, so a schema missing the archive
    tables is an explicit error and the database is never mutated by the CLI
    (opening ``LineageStore`` would otherwise create missing tables/columns as
    migration-writes, which a read-only archive must refuse).
    """
    path = Path(db_path)
    uri = "file:" + path.as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        present = {str(r[0]) for r in table_rows}
        missing = [t for t in REQUIRED_TABLES if t not in present]
        if missing:
            raise _CliError(
                "database is missing the required archive tables: "
                + ", ".join(missing),
                EXIT_WRITE_DETECTED,
            )
        for table, columns in REQUIRED_TABLES.items():
            col_rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            present_cols = {str(r[1]) for r in col_rows}
            missing_cols = [c for c in columns if c not in present_cols]
            if missing_cols:
                raise _CliError(
                    f"table {table} is missing the required columns: "
                    + ", ".join(missing_cols)
                    + " (database predates the adaptive archive schema; "
                    + "a read-only archive never migrates)",
                    EXIT_WRITE_DETECTED,
                )
    finally:
        conn.close()


def open_store(db_path: str) -> LineageStore:
    path = Path(db_path)
    if not path.is_file():
        raise _CliError(
            f"database file does not exist: {path}",
            EXIT_DB_MISSING,
        )
    _validate_db_schema_readonly(db_path)
    store = LineageStore(path)
    return store


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class _CliError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _validate_filters(profile: str | None, session_id: str | None) -> None:
    if profile is not None and profile == "":
        raise _CliError("invalid filter: --profile must not be empty", EXIT_INVALID_FILTER)
    if session_id is not None and session_id == "":
        raise _CliError("invalid filter: --session-id must not be empty", EXIT_INVALID_FILTER)


def _row_line(comparison: dict[str, object]) -> str:
    return " ".join(
        [
            str(comparison["adaptive_comparison_id"]),
            str(comparison["profile_text"]),
            str(comparison["status"]),
            str(comparison["created_at"]),
        ]
    )


def _cmd_list(store: LineageStore, args: argparse.Namespace) -> None:
    _validate_filters(args.profile, args.session_id)
    try:
        if args.profile is not None or args.session_id is not None:
            rows = store.find_adaptive_comparisons(
                profile=args.profile,
                session_id=args.session_id,
            )
        else:
            rows = list(store.iter_adaptive_comparisons())
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise _CliError(
            "corrupted archived row encountered during listing "
            "(use 'verify <id>' for detail): " + str(exc),
            EXIT_CORRUPT,
        ) from exc
    for comparison in rows:
        print("[ARCHIVE-LIST] " + _row_line(comparison))
    print(f"[ARCHIVE-LIST] count: {len(rows)}")


def _audit_before_decode(store: LineageStore, command: str, comparison_id: str) -> dict[str, object]:
    """Gate a single-row command on the audit verdict (read-only, no decode).

    Distinguishes unknown (``None``) from corrupt (``CORRUPT`` verdict) so the
    CLI never collapses corruption into "not found" and never decodes a row the
    audit already knows to be corrupt.
    """
    verification = store.verify_adaptive_comparison(comparison_id)
    if verification is None:
        raise _CliError(
            f"unknown comparison: {comparison_id}",
            EXIT_UNKNOWN_COMPARISON,
        )
    if verification["verdict"] != "OK":
        print(f"[ARCHIVE-{command}] verdict: CORRUPT")
        print(f"[ARCHIVE-{command}] integrity_json: " + _json(verification["integrity"]))
        raise _CliError(
            f"archived comparison is corrupt: {comparison_id}",
            EXIT_CORRUPT,
        )
    return verification


def _cmd_get(store: LineageStore, args: argparse.Namespace) -> None:
    _audit_before_decode(store, "GET", args.comparison_id)
    comparison = store.get_adaptive_comparison(args.comparison_id)
    assert comparison is not None
    print("[ARCHIVE-GET] adaptive_comparison_id: " + str(comparison["adaptive_comparison_id"]))
    print("[ARCHIVE-GET] profile: " + str(comparison["profile_text"]))
    print("[ARCHIVE-GET] status: " + str(comparison["status"]))
    print("[ARCHIVE-GET] created_at: " + str(comparison["created_at"]))
    print("[ARCHIVE-GET] session_ids: " + _json(sorted(comparison["session_ids"])))
    print("[ARCHIVE-GET] record_json: " + _json(comparison))


def _cmd_find(store: LineageStore, args: argparse.Namespace) -> None:
    _validate_filters(args.profile, args.session_id)
    try:
        matches = store.find_adaptive_comparisons(
            profile=args.profile,
            session_id=args.session_id,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise _CliError(
            "corrupted archived row encountered during find "
            "(use 'verify <id>' for detail): " + str(exc),
            EXIT_CORRUPT,
        ) from exc
    for comparison in matches:
        print("[ARCHIVE-FIND] " + _row_line(comparison))
    print(f"[ARCHIVE-FIND] matches: {len(matches)}")


def _cmd_verify(store: LineageStore, args: argparse.Namespace) -> None:
    verification = store.verify_adaptive_comparison(args.comparison_id)
    if verification is None:
        raise _CliError(
            f"unknown comparison: {args.comparison_id}",
            EXIT_UNKNOWN_COMPARISON,
        )
    print("[ARCHIVE-VERIFY] adaptive_comparison_id: " + str(verification["adaptive_comparison_id"]))
    print("[ARCHIVE-VERIFY] verdict: " + str(verification["verdict"]))
    print("[ARCHIVE-VERIFY] identity_recomputable: " + str(verification["identity_recomputable"]))
    linkage = verification["feature_linkage"]
    print("[ARCHIVE-VERIFY] feature_linkage.available: " + str(linkage["available"]))
    print("[ARCHIVE-VERIFY] feature_linkage.resolvable_from_archive: " + str(linkage["resolvable_from_archive"]))
    print("[ARCHIVE-VERIFY] feature_linkage.reason: " + str(linkage["reason"]))
    print("[ARCHIVE-VERIFY] integrity_json: " + _json(verification["integrity"]))
    print("[ARCHIVE-VERIFY] full_json: " + _json(verification))
    if verification["verdict"] != "OK":
        raise _CliError(
            f"archived comparison is corrupt: {args.comparison_id}",
            EXIT_CORRUPT,
        )


def _cmd_link(store: LineageStore, args: argparse.Namespace) -> None:
    _audit_before_decode(store, "LINK", args.comparison_id)
    linkage = store.feature_linkage_of(args.comparison_id)
    assert linkage is not None
    print("[ARCHIVE-LINK] adaptive_comparison_id: " + str(linkage["adaptive_comparison_id"]))
    print("[ARCHIVE-LINK] available: " + str(linkage["available"]))
    print("[ARCHIVE-LINK] resolvable: " + str(linkage["resolvable"]))
    print("[ARCHIVE-LINK] reason: " + str(linkage["reason"]))
    print("[ARCHIVE-LINK] source_ids: " + _json(linkage["source_ids"]))
    print("[ARCHIVE-LINK] resolved_feature_sources: " + _json(linkage["resolved_feature_sources"]))
    print("[ARCHIVE-LINK] evidence_json: " + _json(linkage["evidence"]))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.  Returns the process exit code (0 = success)."""
    args = build_parser().parse_args(argv)
    store = None
    try:
        store = open_store(args.db)
        before = store._conn.total_changes
        args.handler(store, args)
        after = store._conn.total_changes
        if after != before:
            raise _CliError(
                f"read command modified the database (total_changes {before} -> {after})",
                EXIT_WRITE_DETECTED,
            )
        print(f"[ARCHIVE-READ-ONLY] total_changes unchanged: {after}")
        return EXIT_OK
    except _CliError as exc:
        print(f"[ARCHIVE-ERROR] {exc.message}", file=sys.stderr)
        return exc.exit_code
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    sys.exit(main())