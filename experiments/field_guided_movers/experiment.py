"""Experiment B executor declarations for the generic evaluation layer (Task 2.4).

This is the experiment-facing side of the Task 2.4 Build Stage 1 contract: the
*core* evaluation layer consumes nothing experiment-specific, so Experiment B
must expose, in the generic vocabulary:

- ``build_movers_metrics`` -- trajectory -> compact metric dict;
- ``run_field_guided_movers_world`` -- an ``Executor`` (as in ``core.runner``)
  that runs *any* ``WorldDefinition`` through the generic composition path and
  returns an ``ExecOutcome`` with compact metrics.

This is the conforming ``WorldDefinition -> ExecOutcome`` wrapper whose
existence the composition template's ``executor_ref``
(``experiments.field_guided_movers.model.run_field_guided_movers``, a
``MoversConfig -> MoversTrajectory`` function) did not provide: the repository
composition layer keys its executor map by composition id and uses this
wrapper to run generated worlds.  The science and the coupling operations are
untouched -- this module only adapts the existing validated execution path to
the generic executor contract.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from experiments.field_guided_movers.coupling import (
    FIELD_GUIDED_MOVERS_CONTRACTS,
    MoversState,
    build_field_guided_movers_operations,
    build_field_guided_movers_registry,
)
from experiments.field_guided_movers.model import (
    MoversAdapter,
    MoversConfig,
    MoversTrajectory,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

__all__ = ["build_movers_metrics", "run_field_guided_movers_world"]


def _field_entropy(u: np.ndarray) -> float:
    lo, hi = float(u.min()), float(u.max())
    if not np.isfinite(hi - lo) or (hi - lo) < 1e-12:
        return 0.0
    hist, _ = np.histogram(u, bins=16, range=(lo, hi + (hi - lo) * 1e-9))
    p = hist / max(1, int(hist.sum()))
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def build_movers_metrics(trajectory: MoversTrajectory) -> dict[str, float]:
    """Collapse a movers trajectory to the compact metric summary.

    The metrics are generic scalar collapses of the existing recorded
    observables (final field statistics, mover displacement, mean speed, force
    and gradient magnitudes) -- nothing new is invented here.
    """
    final = np.asarray(trajectory.final_u).copy()
    displacements = trajectory.net_displacements()
    return {
        "final_field_mean": float(final.mean()),
        "final_field_std": float(final.std()),
        "field_entropy": _field_entropy(final),
        "n_movers": float(trajectory.n_movers),
        "total_displacement": float(sum(displacements.values())),
        "mean_speed": float(np.mean(trajectory.speeds)) if trajectory.speeds else 0.0,
        "mean_force": float(np.mean(trajectory.force_mags)) if trajectory.force_mags else 0.0,
        "mean_gradient": float(np.mean(trajectory.gradient_mags)) if trajectory.gradient_mags else 0.0,
    }


def run_field_guided_movers_world(world: WorldDefinition) -> ExecOutcome:
    """Executor: run *any* movers world through the generic core path.

    Mirrors the plain ``compose`` path already proven bitwise identical to the
    ``FieldGuidedMoversEngine`` facade; adapters are rebuilt per call so
    re-runs are independently seeded by the world's own ``seed``
    (deterministic replay).
    """
    config = MoversConfig(**dict(world.config))
    trajectory = MoversTrajectory(config=config)
    state = MoversState()

    engine = AlchemistEngine()
    registry = build_field_guided_movers_registry()
    adapters = build_components(registry, world)

    def _ops() -> dict[str, Any]:
        return build_field_guided_movers_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(MoversAdapter, adapter_by_id(adapters, "pymunk")),
            config,
            trajectory,
            state,
        )

    def _initialize() -> None:
        cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).set_event_bus(engine.event_bus)
        cast(MoversAdapter, adapter_by_id(adapters, "pymunk")).set_event_bus(engine.event_bus)
        field = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    def _on_step(time: float, dt: float, step: int) -> None:
        engine.event_bus.publish(Event.time_step("alchemist", time, dt))

    compose_into(
        engine,
        world,
        adapters,
        _ops(),
        on_step=_on_step,
        on_initialize=_initialize,
        contracts=FIELD_GUIDED_MOVERS_CONTRACTS,
    )
    engine.run()
    metrics = build_movers_metrics(trajectory)
    return ExecOutcome(world=world, metrics=metrics, trajectory=trajectory)