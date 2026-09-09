"""Generic deterministic variant sweeps and experiment ranking (Task 1.7).

A *variant sweep* generates a set of mutated worlds from one base world by
taking the Cartesian product of per-parameter value lists (a
``MutationSpace``), executes them sequentially through the same
``VariantRunner`` used for singular mutations, and records every result in
the same ``LineageStore``.  The baseline (the unmutated base world) is always
executed first as a control.

Everything is deterministic:

* the generation order is the standard Cartesian product order, with the
  right-most dimension varying fastest (for A=[1,2], B=[10,20] the order is
  A=1B=10, A=1B=20, A=2B=10, A=2B=20) -- documented in ``MutationSpace``;
* each variant's identity is its deterministic run id (derived from the
  mutated world + seed), so re-running a sweep with the same base world and
  mutation space reproduces the same run ids, metrics, timings, and ranking
  bit for bit;
* variant mutation sets that leave the world unchanged (identical to the
  base) are skipped and counted, never re-executed redundantly.

Ranking is a pure, generic sort over one metric with an explicit direction
and a deterministic tie-break (variant run id): no metric name, no
normalization, and no experiment concept exists in this module.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.lineage import LineageStore, SweepRecord, world_hash
from sim_alchemist.core.mutation import Mutation, apply_mutations
from sim_alchemist.core.runner import RunResult, VariantRunner
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "MutationSpace",
    "ParameterSweep",
    "RankingEntry",
    "SweepResult",
    "SweepRunner",
    "SweepTiming",
    "rank_results",
    "sweep_id_of",
]


@dataclass(frozen=True)
class ParameterSweep:
    """One sweep dimension: mutate ``path`` through an ordered value list.

    ``values`` preserves the caller's order; the sweep space then combines
    dimensions deterministically.
    """

    path: str
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if isinstance(self.values, list):
            object.__setattr__(self, "values", tuple(self.values))
        if not self.values:
            raise ValueError("a ParameterSweep needs at least one value")

    def mutations(self) -> tuple[Mutation, ...]:
        return tuple(Mutation(self.path, v) for v in self.values)

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "values": list(self.values)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParameterSweep:
        return cls(path=str(data["path"]), values=tuple(data["values"]))


@dataclass(frozen=True)
class MutationSpace:
    """A Cartesian product of one or more ``ParameterSweep`` dimensions.

    ``variant_mutation_sets`` returns one tuple of ``Mutation`` per variant,
    in **documented deterministic product order**: the left-most dimension is
    the slowest, the right-most the fastest.  For A=[1,2], B=[10,20] the
    order is (A=1,B=10), (A=1,B=20), (A=2,B=10), (A=2,B=20).
    """

    dimensions: tuple[ParameterSweep, ...]

    def __post_init__(self) -> None:
        if not self.dimensions:
            raise ValueError("a MutationSpace needs at least one dimension")

    @property
    def variant_count(self) -> int:
        return math.prod(len(d.values) for d in self.dimensions)

    def variant_mutation_sets(self) -> tuple[tuple[Mutation, ...], ...]:
        """All mutation-set combinations in deterministic product order."""
        products = itertools.product(*(d.mutations() for d in self.dimensions))
        return tuple(products)

    def to_dict(self) -> dict[str, Any]:
        return {"dimensions": [d.to_dict() for d in self.dimensions]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MutationSpace:
        return cls(
            tuple(ParameterSweep.from_dict(d) for d in data["dimensions"])
        )


def sweep_id_of(world: WorldDefinition, space: MutationSpace) -> str:
    """Deterministic sweep identity: base world content + mutation space.

    The same world + space always yield the same sweep id, so recorded sweep
    metadata is replayable and idempotent.
    """
    payload = json.dumps(
        {"world_hash": world_hash(world), "space": space.to_dict()},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class SweepTiming:
    """Instrumentation summary of one sweep execution (no per-step data).

    ``total_seconds`` is wall time of the whole sweep (baseline control +
    variant runs); ``mean_seconds`` is that total divided by the number of
    executed variants, so it is comparable across sweep sizes.
    """

    n_planned: int
    n_skipped: int
    n_executed: int
    total_seconds: float
    mean_seconds: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_planned": self.n_planned,
            "n_skipped": self.n_skipped,
            "n_executed": self.n_executed,
            "total_seconds": self.total_seconds,
            "mean_seconds": self.mean_seconds,
        }


@dataclass(frozen=True)
class RankingEntry:
    """One row of a generic ranking: position, run identity, and value."""

    rank: int
    run_id: str
    kind: str  # "baseline" | "variant"
    value: float


def rank_results(
    runs: Sequence[RunResult],
    metric: str,
    *,
    descending: bool = True,
    base_run_id: str | None = None,
) -> tuple[RankingEntry, ...]:
    """Rank runs generically by one metric (Task 1.7).

    * metric is selected by name; nothing is normalized or renamed.
    * ``descending`` controls direction; rank 1 is the best.
    * ties are broken deterministically by run id ascending, so the ranking
      is a pure function of the runs.
    * runs lacking the metric are omitted; if no run has the metric a
      ``ValueError`` is raised.
    """
    scored: list[tuple[float, str]] = []
    for run in runs:
        value = run.metrics.get(metric)
        if value is None:
            continue
        scored.append((float(value), run.run_id))
    if not scored:
        raise ValueError(f"metric {metric!r} present in none of the runs")
    scored.sort(key=lambda kv: (kv[0] if not descending else -kv[0], kv[1]))
    return tuple(
        RankingEntry(
            rank=rank,
            run_id=run_id,
            kind="baseline" if run_id == base_run_id else "variant",
            value=value,
        )
        for rank, (value, run_id) in enumerate(scored, start=1)
    )


@dataclass(frozen=True)
class SweepResult:
    """The outcome of one executed sweep.

    ``base`` is the unmutated control run; ``variants`` are the executed
    mutated runs in generation order.  ``timing`` is the compact
    instrumentation summary.
    """

    sweep_id: str
    world: WorldDefinition
    base: RunResult
    variants: tuple[RunResult, ...]
    mutation_space: MutationSpace
    timing: SweepTiming

    @property
    def n_executed(self) -> int:
        return len(self.variants)

    def ranking(self, metric: str, *, descending: bool = True) -> tuple[RankingEntry, ...]:
        return rank_results(
            (self.base, *self.variants),
            metric,
            descending=descending,
            base_run_id=self.base.run_id,
        )

    def all_runs(self) -> tuple[RunResult, ...]:
        return (self.base, *self.variants)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sweep_id": self.sweep_id,
            "world_id": self.world.id,
            "world_hash": world_hash(self.world),
            "base": self.base.as_dict(),
            "variants": [v.as_dict() for v in self.variants],
            "mutation_space": self.mutation_space.to_dict(),
            "timing": self.timing.as_dict(),
        }


class SweepRunner:
    """Sequential, deterministic sweep executor over one experiment executor.

    Reuses ``VariantRunner`` for every base/variant run, so the sweep shares
    the singular-mutation lineage, validation, and run-id semantics.  The
    baseline (unmutated base world) is always recorded first as the control.
    """

    def __init__(
        self,
        store: LineageStore,
        executor: Any,
        *,
        parameter_specs: Mapping[str, Any] | None = None,
    ) -> None:
        self._runner = VariantRunner(store, executor, parameter_specs=parameter_specs)
        self._specs = dict(parameter_specs or {})
        self._store = store

    @property
    def store(self) -> LineageStore:
        return self._store

    def _validators(self) -> dict[str, Callable[[Any], bool]]:
        out: dict[str, Callable[[Any], bool]] = {}
        for path, spec in self._specs.items():
            fn = spec.validator()
            if fn is not None:
                out[path] = fn
        return out

    def sweep(
        self,
        base_world: WorldDefinition,
        mutation_space: MutationSpace,
        *,
        sweep_id: str | None = None,
        composition_id: str | None = None,
    ) -> SweepResult:
        """Execute the baseline control plus every variant, sequentially.

        Every mutation set is validated against the declared ``parameter_specs``
        *and* type-checked before any simulation starts: an invalid value
        aborts the sweep with nothing recorded.  Variant combinations that are
        no-ops (they reproduce the base world exactly) are skipped and counted
        in the timing summary.

        ``composition_id`` optionally stamps the recorded base and variant runs
        with the composing identity (default ``None`` preserves prior behaviour).

        Returns a ``SweepResult`` and records the base run, all variant runs,
        and the sweep metadata in the store.
        """
        if sweep_id is None:
            sweep_id = sweep_id_of(base_world, mutation_space)

        validators = self._validators()
        mutation_sets = mutation_space.variant_mutation_sets()

        # Phase 1 (no simulation): validate every combination up front and
        # drop no-ops (combinations identical to the baseline control).
        planned: list[tuple[Mutation, ...]] = []
        skipped = 0
        for mutations in mutation_sets:
            child, _ = apply_mutations(base_world, mutations, validators=validators)
            if child.as_dict() == base_world.as_dict():
                skipped += 1
                continue
            planned.append(mutations)

        # Phase 2 (simulation): baseline control first, then variants.
        window_start = time.monotonic()
        base = self._runner.run(base_world, composition_id=composition_id)
        base_seconds = time.monotonic() - window_start

        variants: list[RunResult] = []
        variant_start = time.monotonic()
        for mutations in planned:
            variants.append(
                self._runner.run_variant(
                    base_world, mutations, composition_id=composition_id
                )
            )
        variant_seconds = time.monotonic() - variant_start

        total = base_seconds + variant_seconds
        timing = SweepTiming(
            n_planned=len(mutation_sets),
            n_skipped=skipped,
            n_executed=len(variants),
            total_seconds=total,
            mean_seconds=total / max(1, len(variants)),
        )

        result = SweepResult(
            sweep_id=sweep_id,
            world=base_world,
            base=base,
            variants=tuple(variants),
            mutation_space=mutation_space,
            timing=timing,
        )
        self._store.record_sweep(
            SweepRecord(
                sweep_id=sweep_id,
                world_id=base_world.id,
                world_hash=world_hash(base_world),
                base_run_id=base.run_id,
                mutation_space=mutation_space.to_dict()["dimensions"],
                variant_run_ids=[v.run_id for v in variants],
                n_planned=timing.n_planned,
                n_skipped=timing.n_skipped,
                n_executed=timing.n_executed,
                total_seconds=timing.total_seconds,
                mean_seconds=timing.mean_seconds,
            )
        )
        return result