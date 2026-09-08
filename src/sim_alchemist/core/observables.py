"""Cross-composition common observables (Task 2.4 Build Stage 3).

Stage 3 sits between the Stage 2 evaluation pass and any later
summary/selection layer: after ``CompositionSearcher.search`` has evaluated
every ``EXECUTABLE`` composition once, this module reduces the pool to a
*single deterministic common-observable envelope*.

Each evaluated composition is reduced to one ``CommonObservableSet``: the
composition's lineage identity plus one ``CommonObservable`` per *recognized*
metric name.  Recognition is the sorted union of the metric names the
executors actually produced across the pool (``common_observable_names``), so:

* a name that appears in *every* composition is present and available in
  every set (the genuinely common subspace);
* a name that only some compositions produce is still listed for the others,
  with ``available=False`` and ``value=None`` -- missing stays explicit and
  is never fabricated or imputed.

Nothing here ranks, selects, or summarizes; extraction only reads
already-recorded evaluation snapshots and (optionally) the already-generated
``WorldDefinition`` for the horizon (``max_steps`` / ``macro_timestep``).
It never re-runs a composition and never writes to the lineage store: a
``CommonObservableSet`` is a pure, deterministic projection of data the
evaluation pass already produced and persisted, so repeated searches cannot
duplicate runs or detach analytical records.

All ordering is deterministic: names are sorted, and the per-composition
sets follow the evaluation order of the pool.  Values are carried verbatim
(no rounding, no normalization).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sim_alchemist.core.lineage import world_hash
from sim_alchemist.core.world import WorldDefinition

if TYPE_CHECKING:
    from sim_alchemist.core.composition_search import CompositionEvaluation

__all__ = [
    "CommonObservable",
    "CommonObservableError",
    "CommonObservableSet",
    "common_observable_names",
    "extract_common_observables",
]

# The structural surface of one evaluation snapshot this layer reads.  It is
# checked with hasattr (no runtime import of the composition-search module),
# so this module and the orchestrator module cannot form an import cycle.
_EVALUATION_FIELDS = (
    "composition_id",
    "shape_id",
    "world_hash",
    "run_id",
    "world_id",
    "status",
    "seed",
    "metrics",
)


class CommonObservableError(ValueError):
    """An observable set could not be built (world/evaluation mismatch)."""


def _coerce_number(value: Any) -> float | None:
    """Verbatim ``float`` of a numeric value; ``None`` passes through."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"observable values must be numeric, got {type(value).__name__}"
        )
    return float(value)


def _metrics_of(evaluation: Any) -> dict[str, float]:
    """Structurally validate an evaluation snapshot and copy its metrics."""
    for field_name in _EVALUATION_FIELDS:
        if not hasattr(evaluation, field_name):
            raise TypeError(
                "expected a composition evaluation snapshot; missing "
                f"{field_name!r} on {type(evaluation).__name__}"
            )
    metrics = evaluation.metrics
    if not isinstance(metrics, Mapping):
        raise TypeError(
            "evaluation metrics must be a mapping, got "
            f"{type(metrics).__name__}"
        )
    out: dict[str, float] = {}
    for key, value in metrics.items():
        if not isinstance(key, str):
            raise TypeError(f"metric keys must be str, got {type(key).__name__}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"metric value for {key!r} must be numeric, got "
                f"{type(value).__name__}"
            )
        out[key] = float(value)
    return out


@dataclass(frozen=True)
class CommonObservable:
    """One recognized observable of one evaluated composition.

    ``available`` is ``True`` exactly when the composition's executor
    produced a numeric ``value``; a composition that does not produce a
    recognized name is explicit with ``available=False`` and ``value=None``
    (never imputed).
    """

    name: str
    value: float | None
    available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("observable name must be a non-empty string")
        if self.available and self.value is None:
            raise ValueError(
                f"available observable {self.name!r} requires a numeric value"
            )
        if not self.available and self.value is not None:
            raise ValueError(
                f"unavailable observable {self.name!r} must carry value None"
            )
        object.__setattr__(self, "value", _coerce_number(self.value))

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "available": self.available}


@dataclass(frozen=True)
class CommonObservableSet:
    """The common-observable envelope of one evaluated composition.

    ``max_steps`` / ``macro_timestep`` are the horizon of the composition's
    *generated* world (captured from it, never guessed); both are ``None``
    when the caller supplied no world (explicit insufficient data).
    ``observables`` is sorted by ``name``, and names are unique.
    """

    composition_id: str
    shape_id: str
    world_hash: str
    run_id: str
    world_id: str
    status: str
    seed: int
    max_steps: int | None
    macro_timestep: float | None
    observables: tuple[CommonObservable, ...]

    def __post_init__(self) -> None:
        rows: list[CommonObservable] = []
        for row in self.observables:
            if isinstance(row, CommonObservable):
                rows.append(row)
            elif isinstance(row, Mapping):
                rows.append(CommonObservable(**dict(row)))
            else:
                raise TypeError(
                    "observables must be CommonObservable rows or mappings, "
                    f"got {type(row).__name__}"
                )
        object.__setattr__(self, "observables", tuple(rows))
        names = tuple(row.name for row in self.observables)
        if len(set(names)) != len(names):
            raise ValueError("observable names must be unique")
        if names != tuple(sorted(names)):
            raise ValueError("observables must be sorted by name")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.observables)

    @property
    def available_names(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.observables if row.available)

    @property
    def missing_names(self) -> tuple[str, ...]:
        return tuple(row.name for row in self.observables if not row.available)

    def observable(self, name: str) -> CommonObservable | None:
        for row in self.observables:
            if row.name == name:
                return row
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "shape_id": self.shape_id,
            "world_hash": self.world_hash,
            "run_id": self.run_id,
            "world_id": self.world_id,
            "status": self.status,
            "seed": self.seed,
            "max_steps": self.max_steps,
            "macro_timestep": self.macro_timestep,
            "observables": [row.as_dict() for row in self.observables],
        }


def common_observable_names(evaluations: Sequence[Any]) -> tuple[str, ...]:
    """The sorted union of metric names across an evaluated pool.

    ``evaluations`` is any sequence of composition evaluation snapshots
    (structural duck typing; an empty pool yields the empty vocabulary).
    Each snapshot is validated, so a non-evaluation raises ``TypeError``.
    """
    if isinstance(evaluations, str) or not isinstance(evaluations, Sequence):
        raise TypeError(
            "evaluations must be a Sequence of evaluated compositions, got "
            f"{type(evaluations).__name__}"
        )
    names: set[str] = set()
    for evaluation in evaluations:
        names.update(_metrics_of(evaluation).keys())
    return tuple(sorted(names))


def extract_common_observables(
    evaluation: CompositionEvaluation,
    common_names: Sequence[str],
    *,
    world: WorldDefinition | None = None,
) -> CommonObservableSet:
    """Reduce one evaluation snapshot to its common-observable envelope.

    ``common_names`` is the recognized vocabulary (normally the output of
    ``common_observable_names``).  Every recognized name is materialized: a
    name the composition produced becomes an available observable with its
    verbatim value; a name it did not becomes ``available=False`` /
    ``value=None``.

    The optional ``world`` is the composition's *generated* world; when given
    it must match the snapshot's ``world_id`` and ``world_hash`` exactly (a
    mismatch raises ``CommonObservableError``) and supplies the captured
    horizon.  When omitted, the horizon fields are ``None``.  Nothing here
    mutates the world or the snapshot, and nothing is persisted.
    """
    if isinstance(common_names, str) or not isinstance(common_names, Sequence):
        raise TypeError(
            "common_names must be a Sequence of str, got "
            f"{type(common_names).__name__}"
        )
    names: list[str] = []
    for name in common_names:
        if not isinstance(name, str):
            raise TypeError(
                f"common_names entries must be str, got {type(name).__name__}"
            )
        names.append(name)

    metrics = _metrics_of(evaluation)
    seed = evaluation.seed
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"evaluation seed must be an int, got {type(seed).__name__}")

    max_steps: int | None = None
    macro_timestep: float | None = None
    if world is not None:
        for attr in ("id", "seed", "max_steps", "macro_timestep"):
            if not hasattr(world, attr):
                raise TypeError(
                    f"world must expose {attr!r}, got {type(world).__name__}"
                )
        if world.id != evaluation.world_id:
            raise CommonObservableError(
                f"world id {world.id!r} does not match the evaluation "
                f"snapshot's world id {evaluation.world_id!r}"
            )
        if world_hash(world) != evaluation.world_hash:
            raise CommonObservableError(
                "world content does not match the evaluation snapshot "
                "(world hash mismatch)"
            )
        max_steps = int(world.max_steps)
        macro_timestep = float(world.macro_timestep)

    rows = tuple(
        CommonObservable(
            name=name,
            value=_coerce_number(metrics[name]) if name in metrics else None,
            available=name in metrics,
        )
        for name in sorted(names)
    )
    return CommonObservableSet(
        composition_id=evaluation.composition_id,
        shape_id=evaluation.shape_id,
        world_hash=evaluation.world_hash,
        run_id=evaluation.run_id,
        world_id=evaluation.world_id,
        status=evaluation.status,
        seed=seed,
        max_steps=max_steps,
        macro_timestep=macro_timestep,
        observables=rows,
    )