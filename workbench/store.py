"""Durable SQLite storage and repository for Experiment Records in the Trusted Experiment Lab."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

__all__ = [
    "DiscoverySessionRecord",
    "ExperimentRecord",
    "WorkbenchStore",
]


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ExperimentRecord:
    """Immutable record representing one simulation execution in the Trusted Experiment Lab."""

    record_id: str
    run_id: str
    composition_id: str
    experiment_template: str
    experiment_name: str
    created_at: str
    status: str
    execution_time_seconds: float
    seed: int
    max_steps: int
    parameters: dict[str, Any] = field(default_factory=dict)
    canonical_world: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    feature_snapshot: dict[str, Any] | None = None
    trajectory_summary: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Convert record to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct an ExperimentRecord from a dictionary."""
        return cls(
            record_id=data["record_id"],
            run_id=data["run_id"],
            composition_id=data["composition_id"],
            experiment_template=data["experiment_template"],
            experiment_name=data["experiment_name"],
            created_at=data.get("created_at") or _now_iso(),
            status=data.get("status", "completed"),
            execution_time_seconds=float(data.get("execution_time_seconds", 0.0)),
            seed=int(data["seed"]),
            max_steps=int(data["max_steps"]),
            parameters=dict(data.get("parameters") or {}),
            canonical_world=dict(data.get("canonical_world") or {}),
            metrics=dict(data.get("metrics") or {}),
            feature_snapshot=data.get("feature_snapshot"),
            trajectory_summary=data.get("trajectory_summary"),
            tags=list(data.get("tags") or []),
            notes=str(data.get("notes") or ""),
            error_message=data.get("error_message"),
        )


@dataclass(frozen=True)
class DiscoverySessionRecord:
    """Immutable record representing one completed discovery pass in the Researcher Workbench."""

    session_id: str
    name: str
    experiment_template: str
    composition_id: str
    created_at: str
    search_spec: dict[str, Any]
    ranking_profile: dict[str, Any]
    candidate_record_ids: list[str]
    frontier_record_ids: list[str]
    summary_metrics: dict[str, Any]
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Convert session record to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct a DiscoverySessionRecord from a dictionary."""
        return cls(
            session_id=data["session_id"],
            name=data["name"],
            experiment_template=data["experiment_template"],
            composition_id=data["composition_id"],
            created_at=data.get("created_at") or _now_iso(),
            search_spec=dict(data.get("search_spec") or {}),
            ranking_profile=dict(data.get("ranking_profile") or {}),
            candidate_record_ids=list(data.get("candidate_record_ids") or []),
            frontier_record_ids=list(data.get("frontier_record_ids") or []),
            summary_metrics=dict(data.get("summary_metrics") or {}),
            notes=str(data.get("notes") or ""),
        )


class WorkbenchStore:
    """Thread-safe SQLite store managing experiment persistence, history, and trajectories."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._mem_conn: sqlite3.Connection | None = None
        if db_path is None:
            base_dir = Path(__file__).parent
            self.db_path = base_dir / "workbench.db"
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys = ON")
        else:
            self.db_path = Path(db_path)

        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextlib.contextmanager
    def _session(self) -> Generator[sqlite3.Connection]:
        """Context manager yielding a transactional SQLite connection."""
        if self._mem_conn is not None:
            with self._mem_conn:
                yield self._mem_conn
        else:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if str(self.db_path) != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def _init_db(self) -> None:
        """Initialize database schema and indexes."""
        with self._session() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_records (
                    record_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    composition_id TEXT NOT NULL,
                    experiment_template TEXT NOT NULL,
                    experiment_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_time_seconds REAL NOT NULL DEFAULT 0.0,
                    seed INTEGER NOT NULL,
                    max_steps INTEGER NOT NULL,
                    parameters_json TEXT NOT NULL,
                    canonical_world_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    feature_snapshot_json TEXT,
                    trajectory_summary_json TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    error_message TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_trajectories (
                    record_id TEXT PRIMARY KEY,
                    trajectory_json TEXT NOT NULL,
                    FOREIGN KEY (record_id) REFERENCES experiment_records(record_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovery_sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    experiment_template TEXT NOT NULL,
                    composition_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    search_spec_json TEXT NOT NULL,
                    ranking_profile_json TEXT NOT NULL,
                    candidate_record_ids_json TEXT NOT NULL,
                    frontier_record_ids_json TEXT NOT NULL,
                    summary_metrics_json TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_records_template ON experiment_records(experiment_template)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_records_run_id ON experiment_records(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_records_created_at ON experiment_records(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exp_records_status ON experiment_records(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_sessions_created ON discovery_sessions(created_at DESC)")

    def save_record(
        self,
        record: ExperimentRecord,
        trajectory: dict[str, Any] | None = None,
    ) -> None:
        """Persist or update an ExperimentRecord and optional trajectory payload."""
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_records (
                    record_id, run_id, composition_id, experiment_template, experiment_name,
                    created_at, status, execution_time_seconds, seed, max_steps,
                    parameters_json, canonical_world_json, metrics_json,
                    feature_snapshot_json, trajectory_summary_json, tags_json, notes, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.run_id,
                    record.composition_id,
                    record.experiment_template,
                    record.experiment_name,
                    record.created_at,
                    record.status,
                    record.execution_time_seconds,
                    record.seed,
                    record.max_steps,
                    json.dumps(record.parameters, sort_keys=True),
                    json.dumps(record.canonical_world, sort_keys=True),
                    json.dumps(record.metrics, sort_keys=True),
                    json.dumps(record.feature_snapshot) if record.feature_snapshot is not None else None,
                    json.dumps(record.trajectory_summary) if record.trajectory_summary is not None else None,
                    json.dumps(record.tags),
                    record.notes,
                    record.error_message,
                ),
            )
            if trajectory is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO experiment_trajectories (record_id, trajectory_json)
                    VALUES (?, ?)
                    """,
                    (record.record_id, json.dumps(trajectory)),
                )

    def get_record(self, record_id: str) -> ExperimentRecord | None:
        """Retrieve an ExperimentRecord by record_id."""
        with self._session() as conn:
            cursor = conn.execute(
                "SELECT * FROM experiment_records WHERE record_id = ?",
                (record_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def get_record_by_run_id(self, run_id: str) -> ExperimentRecord | None:
        """Retrieve the most recent ExperimentRecord matching a deterministic run_id."""
        with self._session() as conn:
            cursor = conn.execute(
                "SELECT * FROM experiment_records WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def get_trajectory(self, record_id: str) -> dict[str, Any] | None:
        """Retrieve the serialized trajectory payload for a given record_id."""
        with self._session() as conn:
            cursor = conn.execute(
                "SELECT trajectory_json FROM experiment_trajectories WHERE record_id = ?",
                (record_id,),
            )
            row = cursor.fetchone()
            if row is None or row["trajectory_json"] is None:
                return None
            return json.loads(row["trajectory_json"])

    def list_records(
        self,
        *,
        experiment_template: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExperimentRecord]:
        """Query experiment records with filtering and pagination."""
        clauses: list[str] = []
        params: list[Any] = []

        if experiment_template and experiment_template != "all":
            clauses.append("experiment_template = ?")
            params.append(experiment_template)

        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)

        if tag:
            clauses.append("tags_json LIKE ?")
            params.append(f"%{tag}%")

        if search_query:
            clauses.append(
                "(run_id LIKE ? OR record_id LIKE ? OR notes LIKE ? OR experiment_name LIKE ?)"
            )
            term = f"%{search_query}%"
            params.extend([term, term, term, term])

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM experiment_records
            {where_str}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._session() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def count_records(
        self,
        *,
        experiment_template: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> int:
        """Count total records matching filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if experiment_template and experiment_template != "all":
            clauses.append("experiment_template = ?")
            params.append(experiment_template)

        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)

        if tag:
            clauses.append("tags_json LIKE ?")
            params.append(f"%{tag}%")

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT COUNT(*) as cnt FROM experiment_records {where_str}"

        with self._session() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0

    def delete_record(self, record_id: str) -> bool:
        """Delete an experiment record and its associated trajectory."""
        with self._session() as conn:
            cursor = conn.execute(
                "DELETE FROM experiment_records WHERE record_id = ?",
                (record_id,),
            )
            return cursor.rowcount > 0

    def update_notes_and_tags(
        self,
        record_id: str,
        *,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update user notes and tags on an existing record."""
        updates: list[str] = []
        params: list[Any] = []

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if tags is not None:
            updates.append("tags_json = ?")
            params.append(json.dumps(tags))

        if not updates:
            return False

        params.append(record_id)
        with self._session() as conn:
            cursor = conn.execute(
                f"UPDATE experiment_records SET {', '.join(updates)} WHERE record_id = ?",
                params,
            )
            return cursor.rowcount > 0

    def _row_to_record(self, row: sqlite3.Row) -> ExperimentRecord:
        """Convert a database row into an ExperimentRecord dataclass."""
        return ExperimentRecord(
            record_id=row["record_id"],
            run_id=row["run_id"],
            composition_id=row["composition_id"],
            experiment_template=row["experiment_template"],
            experiment_name=row["experiment_name"],
            created_at=row["created_at"],
            status=row["status"],
            execution_time_seconds=float(row["execution_time_seconds"]),
            seed=int(row["seed"]),
            max_steps=int(row["max_steps"]),
            parameters=json.loads(row["parameters_json"]),
            canonical_world=json.loads(row["canonical_world_json"]),
            metrics=json.loads(row["metrics_json"]),
            feature_snapshot=json.loads(row["feature_snapshot_json"]) if row["feature_snapshot_json"] else None,
            trajectory_summary=json.loads(row["trajectory_summary_json"]) if row["trajectory_summary_json"] else None,
            tags=json.loads(row["tags_json"]),
            notes=row["notes"] or "",
            error_message=row["error_message"],
        )

    # -----------------------------------------------------------------------
    # Discovery Session Persistence
    # -----------------------------------------------------------------------
    def save_discovery_session(self, session: DiscoverySessionRecord) -> None:
        """Persist a discovery session record to SQLite."""
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discovery_sessions (
                    session_id,
                    name,
                    experiment_template,
                    composition_id,
                    created_at,
                    search_spec_json,
                    ranking_profile_json,
                    candidate_record_ids_json,
                    frontier_record_ids_json,
                    summary_metrics_json,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.name,
                    session.experiment_template,
                    session.composition_id,
                    session.created_at,
                    json.dumps(session.search_spec),
                    json.dumps(session.ranking_profile),
                    json.dumps(session.candidate_record_ids),
                    json.dumps(session.frontier_record_ids),
                    json.dumps(session.summary_metrics),
                    session.notes,
                ),
            )

    def get_discovery_session(self, session_id: str) -> DiscoverySessionRecord | None:
        """Retrieve a discovery session by session_id."""
        with self._session() as conn:
            cursor = conn.execute(
                "SELECT * FROM discovery_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_discovery_session(row)

    def list_discovery_sessions(
        self,
        *,
        experiment_template: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoverySessionRecord]:
        """Query discovery session records with optional template filter and pagination."""
        clauses: list[str] = []
        params: list[Any] = []

        if experiment_template and experiment_template != "all":
            clauses.append("experiment_template = ?")
            params.append(experiment_template)

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM discovery_sessions
            {where_str}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._session() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_discovery_session(row) for row in cursor.fetchall()]

    def delete_discovery_session(self, session_id: str) -> bool:
        """Delete a discovery session record."""
        with self._session() as conn:
            cursor = conn.execute(
                "DELETE FROM discovery_sessions WHERE session_id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0

    def _row_to_discovery_session(self, row: sqlite3.Row) -> DiscoverySessionRecord:
        """Convert a database row into a DiscoverySessionRecord dataclass."""
        return DiscoverySessionRecord(
            session_id=row["session_id"],
            name=row["name"],
            experiment_template=row["experiment_template"],
            composition_id=row["composition_id"],
            created_at=row["created_at"],
            search_spec=json.loads(row["search_spec_json"]),
            ranking_profile=json.loads(row["ranking_profile_json"]),
            candidate_record_ids=json.loads(row["candidate_record_ids_json"]),
            frontier_record_ids=json.loads(row["frontier_record_ids_json"]),
            summary_metrics=json.loads(row["summary_metrics_json"]),
            notes=row["notes"] or "",
        )
