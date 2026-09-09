"""Cross-composition sweep orchestrator + durable lineage (Task 2.5 Stage 2).

Stage 2 adds the *first execution stage* of Task 2.5: a thin, deterministic,
experiment-free ``CrossCompositionSweep`` that drives the already-verified
``SweepRunner`` once per EXECUTABLE composition and persists compact per-
composition participation rows to the caller-provided ``LineageStore``.

It is *orchestration over the existing sweep engine*, never a second sweep
engine: Cartesian enumeration, mutation validation, baseline-first semantics,
variant cloning, no-op skipping, deterministic ``run_id``/``sweep_id``, and
``SweepRecord`` persistence are all delegated to ``SweepRunner``.  This module
owns only the composition-aware bookkeeping no single sweep expresses:

    1. iterate ``catalog.executable()`` in canonical catalog order,
    2. resolve each composition's opaque executor and parameter-space binding,
    3. run ``SweepRunner.sweep`` where a legitimate ``MutationSpace`` is
       declared ("swept"), or record the composition's baseline only where no
       space is declared ("baseline-only"),
    4. stamp every recorded run ``composition_id`` so structural and variant
       identities coexist on the same ``RunRecord``,
    5. collect per-composition results and persist one ``CrossCompositionSweepRow``
       per participating composition,
    6. return one deterministic ``CrossCompositionSweepResult(state="executed")``
       with ``CrossCompositionSweepTiming``.

Space semantics stay honest (mirroring Stage 1): ``space=None`` (``ref=None``)
means "no registered parameter sweep" -- never an empty space and never a
fabricated one-value sweep; A/B (which declare none) contribute their baseline
only, while C (which declares a real 27-variant space) is swept.

Failure semantics follow the repository conventions:

* **Fail fast before partial execution.** All configuration is validated up
  front (executor present for every EXECUTABLE composition, a space binding
  present for every composition, and the optional per-composition / pass-level
  variant caps respected) before any world is simulated.
* **Runtime failures are not hidden.** A failure while executing one
  composition re-raises with the offending ``composition_id`` named and the
  cross-sweep record is *not* persisted, so no partial lineage pretends the
  pass completed.  (Individual runs recorded by the sweep before the failure
  remain, but there is no cross-sweep record claiming success.)

Purity: the module is experiment-free.  It knows only opaque composition ids,
the generic ``MutationSpace``, ``SweepRunner``, and the ``LineageStore``; no
experiment name, parameter value, engine, or equation appears here.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.catalog import CatalogCandidate, CompositionCatalog
from sim_alchemist.core.composition_search import evaluate_composition_baseline
from sim_alchemist.core.cross_sweep import (
    CompositionSpaceBinding,
    CrossCompositionSweepResult,
    CrossCompositionSweepSpec,
)
from sim_alchemist.core.cross_sweep import (
    cross_split_sweep_id as _cross_split_sweep_id,
)
from sim_alchemist.core.lineage import CrossCompositionSweepRow, LineageStore
from sim_alchemist.core.runner import Executor
from sim_alchemist.core.sweep import MutationSpace, SweepRunner
from sim_alchemist.core.templates import EXECUTABLE

__all__ = [
    "CrossCompositionSweep",
    "CrossCompositionSweepError",
    "CrossCompositionSweepTiming",
]


class CrossCompositionSweepError(ValueError):
    """A cross-composition sweep could not be planned or executed."""


@dataclass(frozen=True)
class CrossCompositionSweepTiming:
    """Compact instrumentation of one cross-composition sweep pass.

    ``n_executable`` is the number of EXECUTABLE compositions in the catalog;
    ``n_swept`` the number with a declared ``MutationSpace`` that were swept;
    ``n_baseline_only`` the number contributing a baseline without any sweep.
    ``total_runs_executed`` counts every logical run evaluation (baselines +
    executed variants, excluding no-op variants the sweep skipped).
    ``planning_seconds`` measures the upfront validation/plan phase,
    ``execution_seconds`` the sweeps + baseline evaluations, and
    ``persistence_seconds`` the cross-sweep row writes; ``total_seconds`` is the
    whole pass.  Wall-clock timing never enters the canonical identity.
    """

    n_executable: int
    n_swept: int
    n_baseline_only: int
    total_runs_executed: int
    planning_seconds: float
    execution_seconds: float
    persistence_seconds: float
    total_seconds: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "n_executable": self.n_executable,
            "n_swept": self.n_swept,
            "n_baseline_only": self.n_baseline_only,
            "total_runs_executed": self.total_runs_executed,
            "planning_seconds": self.planning_seconds,
            "execution_seconds": self.execution_seconds,
            "persistence_seconds": self.persistence_seconds,
            "total_seconds": self.total_seconds,
        }


class CrossCompositionSweep:
    """Thin orchestrator: sweep every EXECUTABLE composition, once each.

    Owns nothing scientific.  ``catalog`` is the pre-classified composition
    catalog; ``executors`` and ``spaces`` are opaque ``composition_id -> ...``
    maps supplied by the experiment layer (``repository_executors()`` /
    ``repository_parameter_spaces()``); ``store`` is the ``LineageStore`` runs
    and cross-sweep rows are recorded into.

    ``run`` walks ``catalog.executable()`` in catalog order.  For each
    composition with a declared space it runs ``SweepRunner.sweep`` (baseline
    control first, then the deterministic variants, all stamped with the
    composition id); for each composition without a declared space it records
    the baseline only (reusing the Task 2.4 ``evaluate_composition_baseline``
    root-run path -- idempotent on the deterministic run id, so no duplicate
    baseline row is ever created).
    """

    def __init__(
        self,
        catalog: CompositionCatalog,
        executors: Mapping[str, Executor],
        spaces: Mapping[str, CompositionSpaceBinding],
        store: LineageStore,
        *,
        parameter_specs: Mapping[str, Any] | None = None,
        max_variants: int | None = None,
        max_total_variants: int | None = None,
    ) -> None:
        if not isinstance(catalog, CompositionCatalog):
            raise TypeError(
                f"catalog must be a CompositionCatalog, got {type(catalog).__name__}"
            )
        if not isinstance(executors, Mapping):
            raise TypeError(
                f"executors must be a mapping, got {type(executors).__name__}"
            )
        if not isinstance(spaces, Mapping):
            raise TypeError(f"spaces must be a mapping, got {type(spaces).__name__}")
        for key in (*executors, *spaces):
            if not isinstance(key, str):
                raise TypeError(f"composition keys must be str, got {key!r}")
        if max_variants is not None and max_variants < 0:
            raise ValueError("max_variants must be non-negative or None")
        if max_total_variants is not None and max_total_variants < 0:
            raise ValueError("max_total_variants must be non-negative or None")
        self._catalog = catalog
        self._executors = dict(executors)
        self._spaces = dict(spaces)
        self._store = store
        self._parameter_specs = dict(parameter_specs or {})
        self._max_variants = max_variants
        self._max_total_variants = max_total_variants

    @property
    def catalog(self) -> CompositionCatalog:
        return self._catalog

    @property
    def store(self) -> LineageStore:
        return self._store

    def _executor_for(self, candidate: CatalogCandidate) -> Executor:
        composition_id = candidate.composition_id
        if composition_id is None:
            raise CrossCompositionSweepError(
                f"candidate {candidate.shape_id} is EXECUTABLE but carries no "
                "composition id"
            )
        executor = self._executors.get(composition_id)
        if executor is None:
            raise CrossCompositionSweepError(
                f"no executor registered for composition {composition_id} "
                f"(candidate {candidate.shape_id}); the experiment layer must "
                "supply a composition_id -> executor entry"
            )
        return executor

    def _binding_for(self, candidate: CatalogCandidate) -> CompositionSpaceBinding:
        composition_id = candidate.composition_id
        if composition_id is None:
            raise CrossCompositionSweepError(
                f"candidate {candidate.shape_id} is EXECUTABLE but carries no "
                "composition id"
            )
        binding = self._spaces.get(composition_id)
        if binding is None:
            raise CrossCompositionSweepError(
                f"no parameter-space binding registered for composition "
                f"{composition_id} (candidate {candidate.shape_id}); the "
                "experiment layer must supply a composition_id -> binding entry"
            )
        return binding

    def _plan(self, spec: CrossCompositionSweepSpec) -> tuple[CatalogCandidate, ...]:
        """Validate the whole pass up front; return ordered executable candidates.

        Fail-fast before any execution: every EXECUTABLE composition must have
        an executor and a space binding, and the optional variant caps must be
        respected.  Non-EXECUTABLE candidates are never even resolved.
        """
        executables = tuple(
            c for c in self._catalog.executable() if c.status == EXECUTABLE
        )
        total_variants = 0
        for candidate in executables:
            self._executor_for(candidate)
            binding = self._binding_for(candidate)
            if candidate.generated_world is None:
                raise CrossCompositionSweepError(
                    f"candidate {candidate.shape_id} has no generated world; "
                    "build the catalog with generate_worlds=True"
                )
            space = binding.space
            if space is not None:
                if (
                    self._max_variants is not None
                    and space.variant_count > self._max_variants
                ):
                    raise CrossCompositionSweepError(
                        f"composition {binding.composition_id} space has "
                        f"{space.variant_count} variants exceeding max_variants="
                        f"{self._max_variants}"
                    )
                total_variants += space.variant_count
        if self._max_total_variants is not None and total_variants > self._max_total_variants:
            raise CrossCompositionSweepError(
                f"combined variant count {total_variants} exceeds "
                f"max_total_variants={self._max_total_variants}"
            )
        return executables

    def _execute_composition(
        self,
        candidate: CatalogCandidate,
        binding: CompositionSpaceBinding,
    ) -> CompositionSpaceBinding:
        """Execute one composition from its generated world, returning the
        populated (executed) binding."""
        executor = self._executor_for(candidate)
        world = candidate.generated_world
        assert world is not None
        space: MutationSpace | None = binding.space
        if space is None:
            evaluation = evaluate_composition_baseline(self._store, executor, candidate)
            return CompositionSpaceBinding(
                composition_id=binding.composition_id,
                shape_id=binding.shape_id,
                ref=binding.ref,
                space=None,
                sweep_id=None,
                baseline_run_id=evaluation.run_id,
                variant_run_ids=(),
            )
        runner = SweepRunner(
            self._store, executor, parameter_specs=self._parameter_specs
        )
        result = runner.sweep(
            world, space, composition_id=binding.composition_id
        )
        return CompositionSpaceBinding(
            composition_id=binding.composition_id,
            shape_id=binding.shape_id,
            ref=binding.ref,
            space=space,
            sweep_id=result.sweep_id,
            baseline_run_id=result.base.run_id,
            variant_run_ids=tuple(v.run_id for v in result.variants),
        )

    def run(
        self,
        spec: CrossCompositionSweepSpec,
        *,
        cross_split_sweep_id: str | None = None,
    ) -> CrossCompositionSweepResult:
        """Execute every EXECUTABLE composition once, then persist + report.

        The pass identity defaults to ``cross_split_sweep_id`` over ``spec``
        (deterministic content address); a caller-supplied id is trusted as-is
        (mirrors ``CompositionSearcher.search``).  Re-running the same spec on
        the same store is idempotent: run ids / sweep ids are deterministic and
        participation rows are INSERT OR REPLACE on (pass, composition).
        """
        if not isinstance(spec, CrossCompositionSweepSpec):
            raise TypeError(
                "spec must be a CrossCompositionSweepSpec, got "
                f"{type(spec).__name__}"
            )
        if cross_split_sweep_id is None:
            cross_split_sweep_id = _cross_split_sweep_id(spec)

        plan_start = time.monotonic()
        executables = self._plan(spec)
        planning_seconds = time.monotonic() - plan_start

        exec_start = time.monotonic()
        executed_bindings: list[CompositionSpaceBinding] = []
        n_swept = 0
        for candidate in executables:
            binding = self._binding_for(candidate)
            if binding.space is not None:
                n_swept += 1
            try:
                executed_bindings.append(
                    self._execute_composition(candidate, binding)
                )
            except Exception as exc:
                raise CrossCompositionSweepError(
                    f"failed executing composition {binding.composition_id} "
                    f"(candidate {candidate.shape_id}): {exc}"
                ) from exc
        execution_seconds = time.monotonic() - exec_start

        n_baseline_only = len(executed_bindings) - n_swept
        total_runs = sum(1 + len(b.variant_run_ids) for b in executed_bindings)

        persist_start = time.monotonic()
        for b in executed_bindings:
            self._store.record_cross_composition_sweep(
                CrossCompositionSweepRow(
                    cross_split_sweep_id=cross_split_sweep_id,
                    composition_id=b.composition_id,
                    shape_id=b.shape_id,
                    parameter_space_ref=b.ref,
                    sweep_id=b.sweep_id,
                    baseline_run_id=(
                        b.baseline_run_id if b.baseline_run_id is not None else ""
                    ),
                    variant_run_ids=b.variant_run_ids,
                    status="executed",
                )
            )
        persistence_seconds = time.monotonic() - persist_start

        total_seconds = time.monotonic() - plan_start
        timing = CrossCompositionSweepTiming(
            n_executable=len(executables),
            n_swept=n_swept,
            n_baseline_only=n_baseline_only,
            total_runs_executed=total_runs,
            planning_seconds=planning_seconds,
            execution_seconds=execution_seconds,
            persistence_seconds=persistence_seconds,
            total_seconds=total_seconds,
        )
        return CrossCompositionSweepResult(
            cross_split_sweep_id=cross_split_sweep_id,
            spec=spec,
            bindings=tuple(executed_bindings),
            state="executed",
            timing=timing,
        )
