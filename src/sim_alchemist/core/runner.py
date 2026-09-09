"""Variant runner: execute worlds, collect metrics, link lineage (Task 1.6).

A ``VariantRunner`` wraps a single *executor* -- a pure callable the
experiment-facing side supplies that turns any ``WorldDefinition`` into an
``ExecOutcome`` (world + compact metrics + optional trajectory).  The runner
itself is fully generic:

* ``run(base_world)`` -- execute and record the base run.
* ``run_variant(base_world, mutation)`` -- clone, mutate, execute, and record
  the child, linked to the (recorded) base run.

``compare_metrics``/``compare_runs`` turn two metric dicts (or two run
results) into per-metric ``MetricDelta`` records.  The comparison layer never
names or special-cases any metric: it operates on whatever numeric keys the
dicts contain.

Determinism is inherited from the composition layer: the same world + same
seed + same mutation set re-execute bitwise-identically (proved by the
Experiment A/B/C test suites), so ``run_id`` is deterministic and replaying a
recorded lineage is exact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.lineage import LineageStore, RunRecord, run_id_of
from sim_alchemist.core.mutation import (
    Mutation,
    MutationRecord,
    ParameterSpec,
    apply_mutations,
)
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "ExecOutcome",
    "MetricDelta",
    "MissingParentRunError",
    "RunResult",
    "VariantRunner",
    "compare_metrics",
    "compare_runs",
]

Executor = Callable[[WorldDefinition], "ExecOutcome"]


@dataclass(frozen=True)
class ExecOutcome:
    """Result of executing one world: metrics summary + optional trajectory.

    ``trajectory`` is opaque to the core (never persisted; used by tests for
    bitwise checks).
    """

    world: WorldDefinition
    metrics: dict[str, float]
    trajectory: Any = None


@dataclass(frozen=True)
class RunResult:
    """The runner's answer for one executed base or variant world."""

    run_id: str
    world: WorldDefinition
    parent_run_id: str | None
    mutations: tuple[MutationRecord, ...]
    metrics: dict[str, float]
    seed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "world_id": self.world.id,
            "seed": self.seed,
            "mutations": [m.to_dict() for m in self.mutations],
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class MetricDelta:
    """Per-metric difference between a base and a variant run."""

    name: str
    base: float
    variant: float

    @property
    def absolute(self) -> float:
        return float(self.variant - self.base)

    @property
    def relative(self) -> float:
        if abs(self.base) <= 1e-12:
            return float("inf") if abs(self.absolute) > 1e-12 else 0.0
        return float(self.absolute / abs(self.base))


class MissingParentRunError(KeyError):
    """A variant was requested whose base run is not recorded in the store."""


def _as_metric_floats(metrics: Mapping[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, value in metrics.items():
        try:
            out[name] = float(value)
        except (TypeError, ValueError):
            continue  # non-numeric observables are ignored by comparison
    return out


def compare_metrics(
    base: Mapping[str, float], variant: Mapping[str, float]
) -> dict[str, MetricDelta]:
    """Compare two metric dicts generically, keyed by metric name."""
    base_f = _as_metric_floats(base)
    variant_f = _as_metric_floats(variant)
    names = sorted(set(base_f) | set(variant_f))
    return {
        name: MetricDelta(name, base_f.get(name, 0.0), variant_f.get(name, 0.0))
        for name in names
    }


def compare_runs(
    base: RunResult, variant: RunResult
) -> dict[str, MetricDelta]:
    """Compare the compact metrics of a base and a variant run result."""
    return compare_metrics(base.metrics, variant.metrics)


class VariantRunner:
    """Deterministic, lineage-recording variant runner over one executor."""

    def __init__(
        self,
        store: LineageStore,
        executor: Executor,
        *,
        parameter_specs: Mapping[str, ParameterSpec] | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._specs = dict(parameter_specs or {})

    def _record(
        self,
        world: WorldDefinition,
        mutations: tuple[MutationRecord, ...],
        parent: str | None,
        composition_id: str | None = None,
    ) -> RunResult:
        outcome = self._executor(world)
        record = RunRecord(
            run_id=run_id_of(world),
            world=world,
            parent_run_id=parent,
            mutations=mutations,
            metrics=outcome.metrics,
            composition_id=composition_id,
        )
        self._store.record_run(record)
        return RunResult(
            run_id=record.run_id,
            world=world,
            parent_run_id=parent,
            mutations=mutations,
            metrics=outcome.metrics,
            seed=world.seed,
        )

    def _validators(self) -> dict[str, Callable[[Any], bool]]:
        out: dict[str, Callable[[Any], bool]] = {}
        for path, spec in self._specs.items():
            fn = spec.validator()
            if fn is not None:
                out[path] = fn
        return out

    def run(
        self,
        base_world: WorldDefinition,
        *,
        composition_id: str | None = None,
    ) -> RunResult:
        """Execute and record the base world as a root lineage run.

        ``composition_id`` optionally stamps the run with the content-addressed
        identity of the composition that produced this world (default ``None``
        preserves prior behaviour for non-compositional use).
        """
        return self._record(base_world, (), None, composition_id=composition_id)

    def run_variant(
        self,
        base_world: WorldDefinition,
        mutation: Mutation | Sequence[Mutation],
        *,
        composition_id: str | None = None,
    ) -> RunResult:
        """Clone ``base_world``, apply ``mutation``(s), execute and record.

        The parent run must already be recorded (``run`` on the same world);
        otherwise the child lineage link would dangle.  Validation happens
        before any simulation starts.  ``composition_id`` optionally stamps the
        variant with its composing identity.
        """
        mutations = [mutation] if isinstance(mutation, Mutation) else list(mutation)
        child_world, records = apply_mutations(
            base_world, tuple(mutations), validators=self._validators()
        )
        parent_run_id = run_id_of(base_world)
        if self._store.get_run(parent_run_id) is None:
            raise MissingParentRunError(
                f"The base run for world '{base_world.id}' (run_id "
                f"{parent_run_id}) is not recorded. Record it first via "
                "run(base_world)."
            )
        return self._record(
            child_world, records, parent_run_id, composition_id=composition_id
        )

    def run_variants(
        self,
        base_world: WorldDefinition,
        mutations: Sequence[Mutation | Sequence[Mutation]],
        *,
        composition_id: str | None = None,
    ) -> list[RunResult]:
        """Run a batch of variants of one base world (each recorded with its
        own parent link).  Order of results matches order of input."""
        return [
            self.run_variant(base_world, m, composition_id=composition_id)
            for m in mutations
        ]