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
    "CrossCompositionSweepRow",
    "LineageStore",
    "RunRecord",
    "SearchRecord",
    "SweepRecord",
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


def _loads(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


class RunRecord:
    """Immutable metadata record of one executed world.

    ``world`` carries the snapshot in memory; persistence serializes it as
    JSON.  ``metrics`` is the compact summary dict supplied by the executor.
    ``feature_snapshot`` (Task 1.8) optionally holds the compact behavioral
    feature vector of the run as a dict of floats -- never raw trajectories.
    ``composition_id`` (Task 2.4) optionally stamps the run with the
    content-addressed identity of the composition that produced this world.
    """

    __slots__ = (
        "composition_id",
        "created_at",
        "feature_snapshot",
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
        feature_snapshot: dict[str, Any] | None = None,
        composition_id: str | None = None,
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
        self.feature_snapshot = feature_snapshot
        self.composition_id = composition_id
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
            "feature_snapshot": self.feature_snapshot,
            "composition_id": self.composition_id,
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
            feature_snapshot=(
                json.loads(row["feature_snapshot"]) if row["feature_snapshot"] else None
            ),
            composition_id=row.get("composition_id"),
            created_at=row["created_at"],
            world_id_override=row["world_id"],
        )


class SweepRecord:
    """Immutable metadata record of one executed variant sweep.

    Persists only compact descriptions: the sweep's defining mutation space,
    the ordered run ids of the executed variants, and the timing summary.
    It carries no trajectories and no per-step data (same policy as run
    records).
    """

    __slots__ = (
        "base_run_id",
        "created_at",
        "mean_seconds",
        "mutation_space",
        "n_executed",
        "n_planned",
        "n_skipped",
        "sweep_id",
        "total_seconds",
        "variant_run_ids",
        "world_hash",
        "world_id",
    )

    def __init__(
        self,
        sweep_id: str,
        *,
        world_id: str,
        world_hash: str,
        base_run_id: str,
        mutation_space: list[dict[str, Any]],
        variant_run_ids: list[str] | tuple[str, ...],
        n_planned: int,
        n_skipped: int,
        n_executed: int,
        total_seconds: float,
        mean_seconds: float,
        created_at: str | None = None,
    ) -> None:
        self.sweep_id = sweep_id
        self.world_id = world_id
        self.world_hash = world_hash
        self.base_run_id = base_run_id
        self.mutation_space = mutation_space
        self.variant_run_ids = tuple(variant_run_ids)
        self.n_planned = n_planned
        self.n_skipped = n_skipped
        self.n_executed = n_executed
        self.total_seconds = total_seconds
        self.mean_seconds = mean_seconds
        self.created_at = created_at or _now_iso()

    def as_dict(self) -> dict[str, Any]:
        return {
            "sweep_id": self.sweep_id,
            "world_id": self.world_id,
            "world_hash": self.world_hash,
            "base_run_id": self.base_run_id,
            "mutation_space": self.mutation_space,
            "variant_run_ids": list(self.variant_run_ids),
            "n_planned": self.n_planned,
            "n_skipped": self.n_skipped,
            "n_executed": self.n_executed,
            "total_seconds": self.total_seconds,
            "mean_seconds": self.mean_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SweepRecord:
        return cls(
            sweep_id=row["sweep_id"],
            world_id=row["world_id"],
            world_hash=row["world_hash"],
            base_run_id=row["base_run_id"],
            mutation_space=json.loads(row["mutation_space"]),
            variant_run_ids=json.loads(row["variant_run_ids"]),
            n_planned=int(row["n_planned"]),
            n_skipped=int(row["n_skipped"]),
            n_executed=int(row["n_executed"]),
            total_seconds=float(row["total_seconds"]),
            mean_seconds=float(row["mean_seconds"]),
            created_at=row["created_at"],
        )


class SearchRecord:
    """Immutable metadata record of one executed guided search.

    Persists only compact descriptions: the search spec (mutation space +
    interestingness profile + beam parameters), the per-candidate identity and
    rank records (uniquely keyed by their deterministic run ids, whose full
    worlds/feature snapshots already live in the ``runs`` table), the per-
    generation beam structure, and the timing summary.  It carries no
    trajectories, no per-step data, and no feature vectors (same policy as run
    and sweep records).
    """

    __slots__ = (
        "analysis_seconds",
        "base_run_id",
        "candidates",
        "created_at",
        "execution_seconds",
        "final_ranking",
        "generation_order",
        "mean_seconds",
        "n_executed",
        "n_generated",
        "n_skipped",
        "search_id",
        "spec",
        "total_seconds",
        "world_hash",
        "world_id",
    )

    def __init__(
        self,
        search_id: str,
        *,
        world_id: str,
        world_hash: str,
        base_run_id: str,
        spec: dict[str, Any],
        generation_order: list[Any],
        candidates: list[dict[str, Any]],
        final_ranking: dict[str, Any],
        n_generated: int,
        n_skipped: int,
        n_executed: int,
        total_seconds: float,
        execution_seconds: float,
        analysis_seconds: float,
        mean_seconds: float,
        created_at: str | None = None,
    ) -> None:
        self.search_id = search_id
        self.world_id = world_id
        self.world_hash = world_hash
        self.base_run_id = base_run_id
        self.spec = spec
        self.generation_order = generation_order
        self.candidates = candidates
        self.final_ranking = final_ranking
        self.n_generated = n_generated
        self.n_skipped = n_skipped
        self.n_executed = n_executed
        self.total_seconds = total_seconds
        self.execution_seconds = execution_seconds
        self.analysis_seconds = analysis_seconds
        self.mean_seconds = mean_seconds
        self.created_at = created_at or _now_iso()

    @classmethod
    def from_result(cls, result: Any, *, created_at: str | None = None) -> SearchRecord:
        """Build the compact record from an in-memory ``SearchResult``."""
        payload = result.as_dict(canonical=True)
        timing = result.timing.as_dict()
        return cls(
            search_id=payload["search_id"],
            world_id=payload["world_id"],
            world_hash=payload["world_hash"],
            base_run_id=payload["root_run_id"],
            spec=payload["spec"],
            generation_order=[
                list(g["selected_candidate_ids"]) for g in payload["generations"]
            ],
            candidates=payload["candidates"],
            final_ranking=payload["final_ranking"],
            n_generated=int(timing["n_generated"]),
            n_skipped=int(timing["n_skipped"]),
            n_executed=int(timing["n_executed"]),
            total_seconds=float(timing["total_seconds"]),
            execution_seconds=float(timing["execution_seconds"]),
            analysis_seconds=float(timing["analysis_seconds"]),
            mean_seconds=float(timing["mean_seconds"]),
            created_at=created_at,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "search_id": self.search_id,
            "world_id": self.world_id,
            "world_hash": self.world_hash,
            "base_run_id": self.base_run_id,
            "spec": self.spec,
            "generation_order": self.generation_order,
            "candidates": self.candidates,
            "final_ranking": self.final_ranking,
            "timing": {
                "n_generated": self.n_generated,
                "n_skipped": self.n_skipped,
                "n_executed": self.n_executed,
                "total_seconds": self.total_seconds,
                "execution_seconds": self.execution_seconds,
                "analysis_seconds": self.analysis_seconds,
                "mean_seconds": self.mean_seconds,
            },
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SearchRecord:
        return cls(
            search_id=row["search_id"],
            world_id=row["world_id"],
            world_hash=row["world_hash"],
            base_run_id=row["base_run_id"],
            spec=json.loads(row["spec_json"]),
            generation_order=json.loads(row["generation_order"]),
            candidates=json.loads(row["candidates"]),
            final_ranking=json.loads(row["final_ranking"]),
            n_generated=int(row["n_generated"]),
            n_skipped=int(row["n_skipped"]),
            n_executed=int(row["n_executed"]),
            total_seconds=float(row["total_seconds"]),
            execution_seconds=float(row["execution_seconds"]),
            analysis_seconds=float(row["analysis_seconds"]),
            mean_seconds=float(row["mean_seconds"]),
            created_at=row["created_at"],
        )


class CrossCompositionSweepRow:
    """Immutable durable row of one composition's participation in a sweep.

    Task 2.5 stores a cross-composition sweep pass as **one row per
    participating composition** (compact, columnar).  The row preserves all the
    identities the viewer needs to answer "which cross sweep, which
    composition, which per-composition sweep, which baseline, which variants":
    ``cross_split_sweep_id`` is the whole-pass content address shared by every
    row of the pass, ``composition_id``/``shape_id`` the concrete composition,
    ``parameter_space_ref`` the (opaque) reference to a declared space (``None``
    if the composition declared none), ``sweep_id`` the per-composition sweep
    identity, ``baseline_run_id`` the composition's baseline control run, and
    ``variant_run_ids`` the executed parameter variants in generation order.
    ``status`` is ``"planned"`` or ``"executed"``.  No trajectories, no per-step
    data, no transient timestamps beyond the single ``created_at`` (consistent
    with the compact-only lineage policy).
    """

    __slots__ = (
        "baseline_run_id",
        "composition_id",
        "created_at",
        "cross_split_sweep_id",
        "parameter_space_ref",
        "shape_id",
        "status",
        "sweep_id",
        "variant_run_ids",
    )

    def __init__(
        self,
        cross_split_sweep_id: str,
        composition_id: str,
        *,
        shape_id: str,
        parameter_space_ref: str | None = None,
        sweep_id: str | None = None,
        baseline_run_id: str,
        variant_run_ids: list[str] | tuple[str, ...] = (),
        status: str = "executed",
        created_at: str | None = None,
    ) -> None:
        self.cross_split_sweep_id = cross_split_sweep_id
        self.composition_id = composition_id
        self.shape_id = shape_id
        self.parameter_space_ref = parameter_space_ref
        self.sweep_id = sweep_id
        self.baseline_run_id = baseline_run_id
        self.variant_run_ids = tuple(variant_run_ids)
        self.status = status
        self.created_at = created_at or _now_iso()

    def as_dict(self) -> dict[str, Any]:
        return {
            "cross_split_sweep_id": self.cross_split_sweep_id,
            "composition_id": self.composition_id,
            "shape_id": self.shape_id,
            "parameter_space_ref": self.parameter_space_ref,
            "sweep_id": self.sweep_id,
            "baseline_run_id": self.baseline_run_id,
            "variant_run_ids": list(self.variant_run_ids),
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> CrossCompositionSweepRow:
        return cls(
            cross_split_sweep_id=row["cross_split_sweep_id"],
            composition_id=row["composition_id"],
            shape_id=row["shape_id"],
            parameter_space_ref=row["parameter_space_ref"],
            sweep_id=row["sweep_id"],
            baseline_run_id=row["baseline_run_id"],
            variant_run_ids=json.loads(row["variant_run_ids"]),
            status=row["status"],
            created_at=row["created_at"],
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
    CREATE TABLE IF NOT EXISTS adaptive_comparison_archive (adaptive_comparison_id TEXT PRIMARY KEY, session_ids_json TEXT NOT NULL, profile_text TEXT, comparison_result_digest TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_adapt_comp_archive ON adaptive_comparison_archive(adaptive_comparison_id);
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

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path: str | Path = path
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Migrate stores created before the Task 1.8/2.4 runs schema.

        Pre-1.8 stores lack the per-run ``feature_snapshot`` column;
        pre-2.4 stores lack the per-run ``composition_id`` column.  Both are
        added additively so every existing store keeps loading untouched.
        """
        cols = [str(r["name"]) for r in self._conn.execute("PRAGMA table_info(runs)")]
        if "feature_snapshot" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN feature_snapshot TEXT")
        if "composition_id" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN composition_id TEXT")
        # Additive adaptive exploration session table (Task 2.7 Stage 3)
        self._ensure_adaptive_exploration_sessions_table()

    def _ensure_adaptive_exploration_sessions_table(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS adaptive_exploration_sessions (adaptive_exploration_id TEXT PRIMARY KEY, spec_dict TEXT NOT NULL, composition_ids TEXT NOT NULL, profile_text TEXT, seed INTEGER NOT NULL, budget INTEGER NOT NULL, pass_adaptive_run_ids TEXT NOT NULL, final_decision TEXT NOT NULL, termination_reason TEXT NOT NULL, total_simulated INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_adapt_exp_id ON adaptive_exploration_sessions(adaptive_exploration_id)"
        )
        self._conn.commit()

    def record_run(self, record: RunRecord) -> None:
        """Insert or overwrite the record for ``record.run_id`` (idempotent)."""
        payload = record.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO runs
                (run_id, parent_run_id, world_id, world_hash, seed,
                 mutations, world_json, metrics, feature_snapshot,
                 composition_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                (
                    None
                    if payload["feature_snapshot"] is None
                    else json.dumps(payload["feature_snapshot"], **json_kwargs)
                ),
                payload["composition_id"],
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

    def record_sweep(self, record: SweepRecord) -> None:
        """Insert or overwrite the record for ``record.sweep_id`` (idempotent)."""
        payload = record.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO sweeps
                (sweep_id, world_id, world_hash, base_run_id, mutation_space,
                 variant_run_ids, n_planned, n_skipped, n_executed,
                 total_seconds, mean_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["sweep_id"],
                payload["world_id"],
                payload["world_hash"],
                payload["base_run_id"],
                json.dumps(payload["mutation_space"], **json_kwargs),
                json.dumps(payload["variant_run_ids"], **json_kwargs),
                payload["n_planned"],
                payload["n_skipped"],
                payload["n_executed"],
                payload["total_seconds"],
                payload["mean_seconds"],
                payload["created_at"],
            ),
        )
        self._conn.commit()

    def get_sweep(self, sweep_id: str) -> SweepRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sweeps WHERE sweep_id = ?", (sweep_id,)
        ).fetchone()
        return SweepRecord.from_row(dict(row)) if row is not None else None

    def iter_sweeps(self) -> Iterator[SweepRecord]:
        rows = self._conn.execute(
            "SELECT * FROM sweeps ORDER BY sweep_id"
        ).fetchall()
        for row in rows:
            yield SweepRecord.from_row(dict(row))

    @property
    def sweep_count(self) -> int:
        (count,) = self._conn.execute("SELECT COUNT(*) FROM sweeps").fetchone()
        return int(count)

    def record_behavior_analysis(
        self, record: Any, *, profile_json: str | None = None
    ) -> None:
        """Idempotently persist one compact behavioral-analysis record.

        ``record`` is duck-typed (``as_dict()``); the profile is stored as its
        own JSON column, the ranked rows + timing as JSON.  Only compact
        summaries are stored -- never series or trajectories.
        """
        payload = record.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO behavior_analyses
                (analysis_id, world_id, world_hash, base_run_id, profile_json,
                 run_order, ranked, timing, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["analysis_id"],
                payload["world_id"],
                payload["world_hash"],
                payload["base_run_id"],
                json.dumps(payload["profile"], **json_kwargs),
                json.dumps(list(payload["run_order"]), **json_kwargs),
                json.dumps(payload["ranked"], **json_kwargs),
                json.dumps(payload["timing"], **json_kwargs),
                payload["created_at"],
            ),
        )
        self._conn.commit()

    def get_behavior_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM behavior_analyses WHERE analysis_id = ?", (analysis_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["profile"] = _loads(data.pop("profile_json"))
        data["run_order"] = _loads(data.pop("run_order"))
        data["ranked"] = _loads(data.pop("ranked"))
        data["timing"] = _loads(data.pop("timing"))
        return data

    def iter_behavior_analyses(self) -> Iterator[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM behavior_analyses ORDER BY analysis_id"
        ).fetchall()
        for row in rows:
            data = dict(row)
            data["profile"] = _loads(data.pop("profile_json"))
            data["run_order"] = _loads(data.pop("run_order"))
            data["ranked"] = _loads(data.pop("ranked"))
            data["timing"] = _loads(data.pop("timing"))
            yield data

    @property
    def behavior_analysis_count(self) -> int:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM behavior_analyses"
        ).fetchone()
        return int(count)

    @property
    def run_count(self) -> int:
        (count,) = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(count)

    def record_search(self, record: SearchRecord) -> None:
        """Insert or overwrite the record for ``record.search_id`` (idempotent)."""
        payload = record.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        timing = payload["timing"]
        self._conn.execute(
            """
            INSERT OR REPLACE INTO searches
                (search_id, world_id, world_hash, base_run_id, spec_json,
                 generation_order, candidates, final_ranking,
                 n_generated, n_skipped, n_executed,
                 total_seconds, execution_seconds, analysis_seconds,
                 mean_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["search_id"],
                payload["world_id"],
                payload["world_hash"],
                payload["base_run_id"],
                json.dumps(payload["spec"], **json_kwargs),
                json.dumps(payload["generation_order"], **json_kwargs),
                json.dumps(payload["candidates"], **json_kwargs),
                json.dumps(payload["final_ranking"], **json_kwargs),
                timing["n_generated"],
                timing["n_skipped"],
                timing["n_executed"],
                timing["total_seconds"],
                timing["execution_seconds"],
                timing["analysis_seconds"],
                timing["mean_seconds"],
                payload["created_at"],
            ),
        )
        self._conn.commit()

    def get_search(self, search_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM searches WHERE search_id = ?", (search_id,)
        ).fetchone()
        if row is None:
            return None
        return self._search_from_row(dict(row))

    def iter_searches(self) -> Iterator[SearchRecord]:
        rows = self._conn.execute(
            "SELECT * FROM searches ORDER BY search_id"
        ).fetchall()
        for row in rows:
            yield SearchRecord.from_row(dict(row))

    @staticmethod
    def _search_from_row(data: dict[str, Any]) -> dict[str, Any]:
        data["spec"] = json.loads(data.pop("spec_json"))
        data["generation_order"] = json.loads(data.pop("generation_order"))
        data["candidates"] = json.loads(data.pop("candidates"))
        data["final_ranking"] = json.loads(data.pop("final_ranking"))
        data["timing"] = {
            "n_generated": data.pop("n_generated"),
            "n_skipped": data.pop("n_skipped"),
            "n_executed": data.pop("n_executed"),
            "total_seconds": data.pop("total_seconds"),
            "execution_seconds": data.pop("execution_seconds"),
            "analysis_seconds": data.pop("analysis_seconds"),
            "mean_seconds": data.pop("mean_seconds"),
        }
        return data

    @property
    def search_count(self) -> int:
        (count,) = self._conn.execute("SELECT COUNT(*) FROM searches").fetchone()
        return int(count)

    def record_cross_composition_sweep(
        self, row: CrossCompositionSweepRow
    ) -> None:
        """Insert or overwrite one composition's participation row (idempotent).

        The row's primary key is ``(cross_split_sweep_id, composition_id)``, so
        re-persisting the same pass + composition converges to a single row --
        repeated execution never accumulates duplicate cross-sweep lineage.
        """
        payload = row.as_dict()
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO cross_composition_sweeps
                (cross_split_sweep_id, composition_id, shape_id,
                 parameter_space_ref, sweep_id, baseline_run_id,
                 variant_run_ids, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["cross_split_sweep_id"],
                payload["composition_id"],
                payload["shape_id"],
                payload["parameter_space_ref"],
                payload["sweep_id"],
                payload["baseline_run_id"],
                json.dumps(payload["variant_run_ids"], **json_kwargs),
                payload["status"],
                payload["created_at"],
            ),
        )
        self._conn.commit()

    def get_cross_composition_sweeps(
        self, cross_split_sweep_id: str
    ) -> list[CrossCompositionSweepRow]:
        """All participation rows of one cross-composition sweep, in canonical
        (composition id ascending) order."""
        rows = self._conn.execute(
            "SELECT * FROM cross_composition_sweeps "
            "WHERE cross_split_sweep_id = ? ORDER BY composition_id",
            (cross_split_sweep_id,),
        ).fetchall()
        return [CrossCompositionSweepRow.from_row(dict(r)) for r in rows]

    def iter_cross_composition_sweeps(self) -> Iterator[CrossCompositionSweepRow]:
        rows = self._conn.execute(
            "SELECT * FROM cross_composition_sweeps "
            "ORDER BY cross_split_sweep_id, composition_id"
        ).fetchall()
        for row in rows:
            yield CrossCompositionSweepRow.from_row(dict(row))

    # ---------------------------------------------------------------
    # Task 2.7 Stage 3 — adaptive exploration session lineage (additive)
    # ---------------------------------------------------------------

    def record_exploration_session(self, session_id: str, spec_dict: dict, eligible_compositions: list[str],
                                   profile_text: str, seed: int, budget: int,
                                   pass_adaptive_run_ids: list[str], final_decision: str,
                                   termination_reason: str, total_simulated: int,
                                   status: str, created_at: str | None = None) -> None:
        """Idempotent record of a bounded adaptive exploration session."""
        at = created_at or _now_iso()
        payload_json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        self._conn.execute(
            """
            INSERT OR REPLACE INTO adaptive_exploration_sessions
                (adaptive_exploration_id, spec_dict, composition_ids, profile_text, seed,
                 budget, pass_adaptive_run_ids, final_decision, termination_reason,
                 total_simulated, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                json.dumps(spec_dict, **payload_json_kwargs),
                json.dumps(sorted(eligible_compositions), **payload_json_kwargs),
                profile_text,
                seed,
                budget,
                json.dumps(sorted(pass_adaptive_run_ids), **payload_json_kwargs),
                final_decision,
                termination_reason,
                total_simulated,
                status,
                at,
            ),
        )
        self._conn.commit()

    def get_exploration_session(self, adaptive_exploration_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM adaptive_exploration_sessions WHERE adaptive_exploration_id = ?",
            (adaptive_exploration_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def iter_exploration_sessions(self) -> Iterator[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM adaptive_exploration_sessions ORDER BY adaptive_exploration_id"
        ).fetchall()
        for row in rows:
            yield dict(row)

    def count_exploration_sessions(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM adaptive_exploration_sessions"
        ).fetchone()
        return int(row[0]) if row else 0

    # ---------------------------------------------------------------
    # Task 2.9 Stage 1 — adaptive comparison archive (additive)
    # ---------------------------------------------------------------

    def record_adaptive_comparison(
        self,
        result: Any,
        *,
        status: str = "VALID",
        created_at: str | None = None,
    ) -> None:
        """Idempotently persist one compact adaptive-comparison record.

        ``result`` is duck-typed from the analysis-only task 2.8
        ``AdaptiveComparisonResult``: its content-addressed identity, the
        source session references, the comparison profile, and a compact
        content digest of the analysis outputs (ranked order / frontier /
        diagnostics / explanation) are stored.  No trajectories and no
        feature vectors are persisted (compact-only lineage policy).
        Re-recording the same ``comparison_id`` overwrites, so replay
        converges on exactly one logical archive row.
        """
        if not isinstance(getattr(result, "comparison_id", None), str):
            raise TypeError("adaptive comparison result must expose comparison_id")
        json_kwargs: dict[str, Any] = {"sort_keys": True, "separators": (",", ":")}
        digest = json.dumps(
            {
                "ranked_order": list(result.ranked_order),
                "frontend_ids": list(result.frontend_ids),
                "diagnostics": result.diagnostics,
                "explanation": result.explanation,
            },
            **json_kwargs,
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO adaptive_comparison_archive
                (adaptive_comparison_id, session_ids_json, profile_text,
                 comparison_result_digest, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.comparison_id,
                json.dumps(sorted(result.source_session_ids), **json_kwargs),
                result.profile,
                digest,
                status,
                created_at or _now_iso(),
            ),
        )
        self._conn.commit()

    def get_adaptive_comparison(self, comparison_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM adaptive_comparison_archive WHERE adaptive_comparison_id = ?",
            (comparison_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["session_ids"] = json.loads(data.pop("session_ids_json"))
        data["result_digest"] = _loads(data.pop("comparison_result_digest"))
        return data

    @property
    def cross_composition_sweep_count(self) -> int:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM cross_composition_sweeps"
        ).fetchone()
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
