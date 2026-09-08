"""Cross-composition evaluation identity + orchestration (Task 2.4).

Stage 1 builds the *result layer* the Stage 2 ``CompositionSearcher``
drives: a deterministic, content-addressed identity for a discovery pass and a
single generic function that evaluates one ``EXECUTABLE`` composition of a
``CompositionCatalog`` as a *baseline* (root lineage run) and records it.

Stage 2 adds the thin *orchestration layer* on top of that result layer: a
generic ``CompositionSearcher`` that enumerates ``catalog.executable()`` in
catalog (canonical) order, resolves each candidate's experiment-owned executor
from an opaque composition-id -> executor map, evaluates each candidate once
through ``evaluate_composition_baseline``, and collects the
``CompositionEvaluation`` snapshots in the same deterministic order.

Stage 3 adds the *common-observable envelope* on top of the Stage 2
orchestration: after evaluation the searcher reduces the pool to one
``CommonObservableSet`` per composition (same catalog order), over the sorted
union of the metric names the executors actually produced.  Extraction is a
pure, idempotent projection over the in-memory evaluations and the already-
generated worlds -- it never re-runs a composition, never fabricates a value
(missing = ``available=False`` / ``value=None``), and never persists anything.

Scope (deliberately minimal):

* ``CompositionEvaluation`` -- the compact, immutable outcome of evaluating
  one composition baseline.  It reuses the existing deterministic lineage
  identity (``run_id_of`` / ``world_hash``); it never duplicates ``RunRecord``.
* ``composition_discovery_id_of`` -- the identity of a discovery pass: the
  catalog's composition universe (space, bindings, templates, executable
  compositions) plus the profile, seed, and evaluation config that guide it.
  Content-addressed, deterministic, and free of any transient runtime data.
* ``evaluate_composition_baseline`` -- runs one ``EXECUTABLE`` candidate's
  generated world through the caller-supplied experiment executor and records
  the run with its composition stamp.  Non-executable candidates are never
  simulated: the caller must not evaluate them, and this function refuses to
  if asked.  Composition evaluation is root evaluation -- ``parent_run_id``
  is ``None``; there is no synthetic A/B/C parent-child relation here.
* ``CompositionSearchSpec`` -- the declarative config of one discovery pass
  (profile + seed + evaluation config), exactly the inputs the discovery
  identity is derived from.  Adds no ranking or analysis concept.
* ``CompositionSearcher`` -- a thin orchestrator over the result layer.  It
  never ranks, never analyzes behavior, and never selects a frontier: it
  evaluates, preserves deterministic catalog order, and returns a compact
  ``CompositionSearchResult`` holding the discovery id, the spec, and the
  ordered evaluations.
* ``CompositionSearchResult`` / ``CompositionSearchTiming`` -- the compact
  in-memory outcome and instrumentation (counts + wall/mean seconds measured,
  never part of the canonical identity).  Stage 3 splits the wall time into
  evaluation vs common-observable extraction; the canonical form carries the
  observable sets (deterministic) but never the timing.

Execution reuses the existing executor path (``core.runner.Executor``); this
module holds no executor of its own, no ranking, no frontier selection, no
search loop.  ``EXECUTABLE``-only: catalog statuses other than ``EXECUTABLE``
remain catalog metadata and are simply not evaluated.  The generic core never
dispatches on a composition's name or identity -- the experiment-owned executor
map is opaque and keyed by content-addressed composition id.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.catalog import CatalogCandidate, CompositionCatalog
from sim_alchemist.core.lineage import LineageStore, RunRecord, run_id_of
from sim_alchemist.core.observables import (
    CommonObservableSet,
    common_observable_names,
    extract_common_observables,
)
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.templates import EXECUTABLE
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "CompositionEvaluation",
    "CompositionEvaluationError",
    "CompositionSearchError",
    "CompositionSearchResult",
    "CompositionSearchSpec",
    "CompositionSearchTiming",
    "CompositionSearcher",
    "composition_discovery_id_of",
    "evaluate_composition_baseline",
]

Executor = Callable[[WorldDefinition], ExecOutcome]


class CompositionEvaluationError(ValueError):
    """A composition could not be evaluated (non-executable or no world)."""


@dataclass(frozen=True)
class CompositionEvaluation:
    """One evaluated composition baseline (compact, immutable outcome).

    ``composition_id`` is the composition's content-addressed identity,
    ``run_id`` / ``world_hash`` / ``world_id`` the deterministic lineage keys
    of the executed world, and ``metrics`` the executor's compact summary.
    """

    composition_id: str
    shape_id: str
    world_hash: str
    run_id: str
    world_id: str
    status: str
    seed: int
    metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", dict(self.metrics))

    def as_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "shape_id": self.shape_id,
            "world_hash": self.world_hash,
            "run_id": self.run_id,
            "world_id": self.world_id,
            "status": self.status,
            "seed": self.seed,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_run_record(
        cls,
        record: RunRecord,
        *,
        shape_id: str,
        status: str = EXECUTABLE,
    ) -> CompositionEvaluation:
        """Build the evaluation snapshot from an already-recorded run."""
        return cls(
            composition_id=record.composition_id or "",
            shape_id=shape_id,
            world_hash=record.world_hash,
            run_id=record.run_id,
            world_id=record.world_id,
            status=status,
            seed=record.seed,
            metrics=dict(record.metrics),
        )


def composition_discovery_id_of(
    catalog: CompositionCatalog,
    profile: Any,
    *,
    seed: int = 0,
    evaluation_config: Mapping[str, Any] | None = None,
) -> str:
    """Deterministic, content-addressed identity of a discovery pass.

    The identity covers everything that defines an evaluation pass:

    * the catalog's composition universe (space name, the ordered bindings,
      the registered template names, and the executable composition ids);
    * the guiding profile (weights/directions) and its seed;
    * the evaluation config (e.g. step budget).

    It contains no transient runtime data (timestamps, object identities,
    measurement results).  The same inputs always produce the same 24-hex id;
    any difference in the universe, profile, seed, or evaluation config
    produces a different one.
    """
    profile_data = profile.as_dict() if hasattr(profile, "as_dict") else dict(profile)
    universe = tuple(
        (binding.component, binding.variant or "")
        for binding in catalog.space.universe
    )
    templates = tuple(name for name in sorted(t.name for t in catalog.templates.templates()))
    executables = tuple(
        candidate.composition_id
        for candidate in catalog.executable()
        if candidate.composition_id is not None
    )
    payload = json.dumps(
        {
            "space": catalog.space.name,
            "universe": universe,
            "templates": templates,
            "executables": executables,
            "profile": profile_data,
            "seed": seed,
            "evaluation_config": evaluation_config,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def evaluate_composition_baseline(
    store: Any,
    executor: Executor,
    candidate: CatalogCandidate,
) -> CompositionEvaluation:
    """Evaluate one EXECUTABLE composition baseline and record its root run.

    ``store`` is any ``LineageStore``; ``executor`` is the experiment-owned
    ``WorldDefinition -> ExecOutcome`` callable that runs the candidate's
    generated world.  Only ``EXECUTABLE`` candidates with a generated world
    are evaluated; everything else raises ``CompositionEvaluationError`` and
    is never simulated.

    Re-running the same candidate is idempotent: the run id follows the world
    content + seed, so the same world is recorded once (deterministic
    overwrite) and the same ``CompositionEvaluation`` is returned.
    """
    if candidate.status != EXECUTABLE:
        raise CompositionEvaluationError(
            f"candidate {candidate.shape_id} has status {candidate.status}; "
            "only EXECUTABLE compositions are evaluated"
        )
    if candidate.composition_id is None:
        raise CompositionEvaluationError(
            f"candidate {candidate.shape_id} carries no composition id"
        )
    world = candidate.generated_world
    if world is None:
        raise CompositionEvaluationError(
            f"candidate {candidate.shape_id} has no generated world; "
            "build the catalog with generate_worlds=True"
        )
    outcome = executor(world)
    record = RunRecord(
        run_id=run_id_of(world),
        world=world,
        parent_run_id=None,
        metrics=dict(outcome.metrics),
        composition_id=candidate.composition_id,
    )
    store.record_run(record)
    return CompositionEvaluation.from_run_record(
        record,
        shape_id=candidate.shape_id,
        status=candidate.status,
    )


class CompositionSearchError(ValueError):
    """A composition search could not run (missing executor or identity)."""


@dataclass(frozen=True)
class CompositionSearchSpec:
    """The declarative configuration of one composition discovery pass.

    Fields mirror exactly the inputs the discovery identity is derived from
    (``composition_discovery_id_of``): the guiding ``profile``, a ``seed``
    replay key, and an opaque ``evaluation_config`` (e.g. a step budget).
    Nothing here drives ranking, analysis, or selection -- this stage only
    evaluates.

    ``profile`` may be any object exposing ``weights`` and ``as_dict()``
    (the framework's declarative profile); this module does not import or
    name the behavior layer here.
    """

    profile: Any
    seed: int = 0
    evaluation_config: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError(f"seed must be an int, got {self.seed!r}")
        if not callable(getattr(self.profile, "as_dict", None)):
            raise TypeError(
                "profile must expose as_dict(); got "
                f"{type(self.profile).__name__}"
            )
        if self.evaluation_config is None:
            return
        if not isinstance(self.evaluation_config, Mapping):
            raise TypeError(
                "evaluation_config must be a mapping or None, got "
                f"{type(self.evaluation_config).__name__}"
            )
        object.__setattr__(
            self, "evaluation_config", dict(self.evaluation_config)
        )

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "profile": self.profile.as_dict(),
            "seed": self.seed,
        }
        if self.evaluation_config is not None:
            out["evaluation_config"] = dict(self.evaluation_config)
        return out


@dataclass(frozen=True)
class CompositionSearchTiming:
    """Compact instrumentation of one discovery pass (no per-run data).

    ``n_executable`` is the number of EXECUTABLE candidates in the catalog;
    ``n_evaluated`` the number actually evaluated (equal, unless a candidate
    aborts the pass).  ``evaluation_seconds`` measures the baseline runs,
    ``observation_seconds`` the Stage 3 common-observable extraction that
    follows them (the sorted-vocabulary reduction of that same pool), and
    ``total_seconds`` the whole pass -- so the evaluation/extraction split is
    explicit and wall-clock stays out of the canonical form.  ``mean_seconds``
    divides the whole-pass wall time by evaluated count, so it is comparable
    across catalogs.
    """

    n_executable: int
    n_evaluated: int
    evaluation_seconds: float
    observation_seconds: float
    total_seconds: float
    mean_seconds: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_executable": self.n_executable,
            "n_evaluated": self.n_evaluated,
            "evaluation_seconds": self.evaluation_seconds,
            "observation_seconds": self.observation_seconds,
            "total_seconds": self.total_seconds,
            "mean_seconds": self.mean_seconds,
        }


class CompositionSearcher:
    """Thin orchestrator that evaluates every EXECUTABLE composition once.

    The searcher owns *nothing* scientific: ``catalog`` is the pre-classified
    composition catalog, ``executors`` an opaque ``composition_id -> Executor``
    map supplied by the experiment layer, and ``store`` the ``LineageStore``
    baselines are recorded into.  ``search`` walks ``catalog.executable()`` in
    catalog order, resolves each candidate's executor, and evaluates it via the
    Stage 1 ``evaluate_composition_baseline`` (idempotent on the deterministic
    run id -- re-running the same searcher never creates duplicate roots).

    No ranking, no behavior features, no frontier selection: the returned
    ``CompositionSearchResult`` is an ordered list of immutable evaluation
    snapshots whose semantic order is simply the catalog's canonical order.
    Stage 3 additionally attaches one deterministic ``CommonObservableSet``
    per evaluated composition, extracted in that same order from the
    recorded metrics and the generated worlds.
    """

    def __init__(
        self,
        catalog: CompositionCatalog,
        executors: Mapping[str, Executor],
        store: LineageStore,
    ) -> None:
        if not isinstance(catalog, CompositionCatalog):
            raise TypeError(
                f"catalog must be a CompositionCatalog, got {type(catalog).__name__}"
            )
        if not isinstance(executors, Mapping):
            raise TypeError(
                f"executors must be a mapping, got {type(executors).__name__}"
            )
        for key in executors:
            if not isinstance(key, str):
                raise TypeError(f"executor keys must be str, got {key!r}")
        self._catalog = catalog
        self._executors = dict(executors)
        self._store = store

    @property
    def catalog(self) -> CompositionCatalog:
        return self._catalog

    @property
    def store(self) -> LineageStore:
        return self._store

    def search(
        self,
        spec: CompositionSearchSpec,
        *,
        discovery_id: str | None = None,
    ) -> CompositionSearchResult:
        """Evaluate every EXECUTABLE composition once, in catalog order.

        The discovery identity defaults to ``composition_discovery_id_of``
        over this catalog + the spec's profile/seed/config; a caller-supplied
        ``discovery_id`` is trusted as-is (mirrors ``SearchRunner.search``).
        """
        if not isinstance(spec, CompositionSearchSpec):
            raise TypeError(
                f"spec must be a CompositionSearchSpec, got {type(spec).__name__}"
            )
        if discovery_id is None:
            discovery_id = composition_discovery_id_of(
                self._catalog,
                spec.profile,
                seed=spec.seed,
                evaluation_config=spec.evaluation_config,
            )
        executables = self._catalog.executable()
        start = time.monotonic()
        evaluations: list[CompositionEvaluation] = []
        for candidate in executables:
            composition_id = candidate.composition_id
            if composition_id is None:
                raise CompositionSearchError(
                    f"candidate {candidate.shape_id} is EXECUTABLE but carries "
                    "no composition id"
                )
            executor = self._executors.get(composition_id)
            if executor is None:
                raise CompositionSearchError(
                    f"no executor registered for composition {composition_id} "
                    f"(candidate {candidate.shape_id}); the experiment layer "
                    "must supply a composition_id -> executor entry"
                )
            evaluations.append(
                evaluate_composition_baseline(
                    self._store, executor, candidate
                )
            )
        evaluation_seconds = time.monotonic() - start
        observation_start = time.monotonic()
        common_names = common_observable_names(evaluations)
        observable_sets = tuple(
            extract_common_observables(
                evaluation, common_names, world=candidate.generated_world
            )
            for candidate, evaluation in zip(executables, evaluations)
        )
        observation_seconds = time.monotonic() - observation_start
        total_seconds = time.monotonic() - start
        timing = CompositionSearchTiming(
            n_executable=len(executables),
            n_evaluated=len(evaluations),
            evaluation_seconds=evaluation_seconds,
            observation_seconds=observation_seconds,
            total_seconds=total_seconds,
            mean_seconds=total_seconds / max(1, len(evaluations)),
        )
        return CompositionSearchResult(
            discovery_id=discovery_id,
            spec=spec,
            evaluations=tuple(evaluations),
            timing=timing,
            observable_sets=observable_sets,
        )


@dataclass(frozen=True)
class CompositionSearchResult:
    """The in-memory outcome of one composition discovery pass.

    ``evaluations`` preserves catalog executable order -- the result is
    intentionally not ranked or summarized (later stages consume this list).
    ``observable_sets`` holds the Stage 3 common-observable envelope of each
    evaluated composition, aligned with ``evaluations`` in the same order;
    it is derived only from the recorded metrics and generated worlds (never
    re-runs or re-records anything) and is part of the canonical form.
    ``timing`` is instrumentation only and is excluded from the canonical
    form.
    """

    discovery_id: str
    spec: CompositionSearchSpec
    evaluations: tuple[CompositionEvaluation, ...]
    timing: CompositionSearchTiming
    observable_sets: tuple[CommonObservableSet, ...] = ()

    @property
    def composition_ids(self) -> tuple[str, ...]:
        """Ordered executable composition ids (catalog order)."""
        return tuple(ev.composition_id for ev in self.evaluations)

    def evaluation(self, composition_id: str) -> CompositionEvaluation | None:
        return next(
            (
                ev
                for ev in self.evaluations
                if ev.composition_id == composition_id
            ),
            None,
        )

    def observable_set(self, composition_id: str) -> CommonObservableSet | None:
        return next(
            (
                observable
                for observable in self.observable_sets
                if observable.composition_id == composition_id
            ),
            None,
        )

    def as_dict(self, *, canonical: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "discovery_id": self.discovery_id,
            "spec": self.spec.as_dict(),
            "evaluations": [ev.as_dict() for ev in self.evaluations],
            "observable_sets": [
                observable.as_dict() for observable in self.observable_sets
            ],
        }
        if not canonical:
            data["timing"] = self.timing.as_dict()
        return data