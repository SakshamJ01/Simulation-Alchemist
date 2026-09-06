"""Minimal experiment lineage with local SQLite persistence (Task 1.6).

One *run record* identifies everything needed to reproduce and relate a run:

- ``run_id`` (deterministic: derived from the canonical world content + seed)
- ``parent_run_id`` (the base run a variant was derived from)
- ``world_id`` / ``world_hash`` / the full world snapshot
- ``seed``
- the ordered mutation set applied to the parent, with old/new values
- the compact metrics summary

Persistence is deliberately small: a local SQLite file holds only metadata and
compact metrics -- never simulation trajectories (arrays stay out of the DB;
only the aggregated float metrics belong there).

The store is a thin, idempotent table: recording the same ``run_id`` twice
overwrites (deterministic replay converges on one record).  It is generic:
no metric name and no experiment concept appears here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from sim_alchemist.core.mutation import MutationRecord
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "LineageStore",
    "RunRecord",
    "world_hash",
]


def world_hash(world: WorldDefinition) -> str:
    """Canonical, deterministic fingerprint of a world's full content."""
    payload = json.dumps(
        world.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_id_of(world: WorldDefinition) -> str:
    """Deterministic run id: the world content plus its seed.

    Identical world + seed => identical ``run_id`` on replay.
    """
    seed = f"seed={world.seed}"
    marker = f"{world_hash(world)}|{seed}"
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RunRecord:
    """Immutable metadata record of one executed world.

    ``world`` carries the snapshot in memory; persistence serializes it as
    JSON.  ``metrics`` is the compact summary dict supplied by the executor.
    """

    __slots__ = (
        "created_at",
        "metrics",
        "mutations",
        "parent_run_id",
        "run_id",
        "seed",
        "world",
        "world_hash",
        "world_id",
    )

    def __init__(
        self,
        run_id: str,
        world: WorldDefinition,
        *,
        parent_run_id: str | None = None,
        mutations: tuple[MutationRecord, ...] = (),
        metrics: dict[str, float] | None = None,
        created_at: str | None = None,
        world_id_override: str | None = None,
    ) -> None:
        self.run_id = run_id
        self.parent_run_id = parent_run_id
        self.world = world
        self.world_id = world_id_override or world.id
        self.world_hash = world_hash(world)
        self.seed = world.seed
        self.mutations = mutations
        self.metrics = dict(metrics or {})
        self.created_at = created_at or _now_iso()

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "world_id": self.world_id,
            "world_hash": self.world_hash,
            "seed": self.seed,
            "mutations": [m.to_dict() for m in self.mutations],
            "metrics": self.metrics,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RunRecord:
        world = WorldDefinition.from_dict(json.loads(row["world_json"]))
        return cls(
            run_id=row["run_id"],
            parent_run_id=row["parent_run_id"],
            world=world,
            mutations=tuple(
                MutationRecord.from_dict(m) for m in json.loads(row["mutations"])
            ),
            metrics={k: float(v) for k, v in json.loads(row["metrics"]).items()},
            created_at=row["created_at"],
            world_id_override=row["world_id"],
        )


class LineageStore:
    """Small local SQLite-backed lineage store.

    ``path`` may be ``":memory:"`` (tests) or a file path (persistence).
    Thread-safety is not required (single-process, deterministic use).
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        parent_run_id TEXT,
        world_id TEXT NOT NULL,
        world_hash TEXT NOT NULL,
        seed INTEGER NOT NULL,
        mutations TEXT NOT NULL,
        world_json TEXT NOT NULL,
        metrics TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path: str | Path = path
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def record_run(self, record: RunRecord) -> None:
        """Insert or overwrite the record for ``record.run_id`` (idempotent)."""
        payload = record.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO runs
                (run_id, parent_run_id, world_id, world_hash, seed,
                 mutations, world_json, metrics, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"],
                payload["parent_run_id"],
                payload["world_id"],
                payload["world_hash"],
                payload["seed"],
                json.dumps(payload["mutations"], **json_kwargs),
                json.dumps(self._world_json(record), **json_kwargs),
                json.dumps(payload["metrics"], **json_kwargs),
                payload["created_at"],
            ),
        )
        self._conn.commit()

    def _world_json(self, record: RunRecord) -> dict[str, Any]:
        return record.world.as_dict()

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return RunRecord.from_row(dict(row)) if row is not None else None

    def children_of(self, parent_run_id: str) -> list[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE parent_run_id = ? ORDER BY run_id",
            (parent_run_id,),
        ).fetchall()
        return [RunRecord.from_row(dict(r)) for r in rows]

    def iter_runs(self) -> Iterator[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY parent_run_id, run_id"
        ).fetchall()
        for row in rows:
            yield RunRecord.from_row(dict(row))

    @property
    def run_count(self) -> int:
        (count,) = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(count)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def make_run_id() -> str:
    """Random run id for explicit, non-deterministic runs (rarely needed)."""
    return uuid.uuid4().hex[:24]