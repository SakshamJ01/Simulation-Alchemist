"""Cross-composition evaluation identity + baseline evaluation (Task 2.4, Stage 1).

Stage 1 builds the *result layer* the Stage 2 ``CompositionSearcher`` will
drive: a deterministic, content-addressed identity for a discovery pass and a
single generic function that evaluates one ``EXECUTABLE`` composition of a
``CompositionCatalog`` as a *baseline* (root lineage run) and records it.

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

Execution reuses the existing executor path (``core.runner.Executor``); this
module holds no executor of its own, no ranking, no frontier selection, no
search loop.  ``EXECUTABLE``-only: catalog statuses other than ``EXECUTABLE``
remain catalog metadata and are simply not evaluated.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.catalog import CatalogCandidate, CompositionCatalog
from sim_alchemist.core.lineage import RunRecord, run_id_of
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.templates import EXECUTABLE
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "CompositionEvaluation",
    "CompositionEvaluationError",
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