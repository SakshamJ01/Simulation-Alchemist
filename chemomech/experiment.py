"""Experiment A executor declarations for the generic evaluation layer (Task 2.4).

This is the experiment-facing side of the Task 2.4 Build Stage 1 contract: the
*core* evaluation layer consumes nothing experiment-specific, so Experiment A
must expose, in the generic vocabulary:

- ``build_morphogenesis_metrics`` -- trajectory -> compact metric dict;
- ``run_morphogenesis_world`` -- an ``Executor`` (as in ``core.runner``) that
  runs *any* ``WorldDefinition`` through the generic composition path and
  returns an ``ExecOutcome`` with compact metrics.

This is the conforming ``WorldDefinition -> ExecOutcome`` wrapper whose
existence the composition template's ``executor_ref``
(``chemomech.simulation.run_world``, a ``WorldConfig -> Trajectory`` function)
did not provide: the repository composition layer keys its executor map by
composition id and uses this wrapper to run generated worlds.  The science and
the coupling operations are untouched -- this module only adapts the existing
validated execution path to the generic executor contract.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, cast

import numpy as np

from chemomech.coupling import (
    MORPHOGENESIS_CONTRACTS,
    MorphogenesisState,
    build_morphogenesis_operations,
)
from chemomech.simulation import Trajectory, WorldConfig
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.registry import default_registry
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

__all__ = ["build_morphogenesis_metrics", "run_morphogenesis_world"]


def _total_wall_movement(tracks: dict[int, list[tuple[Any, ...]]]) -> float:
    total = 0.0
    for path in tracks.values():
        points = [(float(x), float(y)) for _, x, y, _ in path]
        for (x0, y0), (x1, y1) in itertools.pairwise(points):
            total += math.hypot(x1 - x0, y1 - y0)
    return total


def _field_entropy(u: np.ndarray) -> float:
    lo, hi = float(u.min()), float(u.max())
    if not np.isfinite(hi - lo) or (hi - lo) < 1e-12:
        return 0.0
    hist, _ = np.histogram(u, bins=16, range=(lo, hi + (hi - lo) * 1e-9))
    p = hist / max(1, int(hist.sum()))
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def build_morphogenesis_metrics(trajectory: Trajectory) -> dict[str, float]:
    """Collapse a morphogenesis trajectory to the compact metric summary.

    The metrics are generic scalar collapses of the existing recorded
    observables (final field statistics, wall population/movement, mean force
    and speed) -- nothing new is invented here.
    """
    final = np.asarray(trajectory.final_u).copy()
    return {
        "final_field_mean": float(final.mean()),
        "final_field_std": float(final.std()),
        "field_entropy": _field_entropy(final),
        "wall_count": float(trajectory.walls_per_step[-1]) if trajectory.walls_per_step else 0.0,
        "wall_movement": _total_wall_movement(trajectory.wall_tracks),
        "dissolved_total": float(trajectory.dissolved_count[-1]) if trajectory.dissolved_count else 0.0,
        "mean_wall_speed": float(np.mean(trajectory.wall_speeds)) if trajectory.wall_speeds else 0.0,
        "mean_force": float(np.mean(trajectory.force_mags)) if trajectory.force_mags else 0.0,
    }


def run_morphogenesis_world(world: WorldDefinition) -> ExecOutcome:
    """Executor: run *any* morphogenesis world through the generic core path.

    Mirrors the plain ``compose`` path already proven bitwise identical to the
    ``ChemomechanicalEngine`` facade; adapters are rebuilt per call so re-runs
    are independently seeded by the world's own ``seed`` (deterministic
    replay).
    """
    config = WorldConfig(**dict(world.config))
    trajectory = Trajectory(config=config)
    state = MorphogenesisState()

    engine = AlchemistEngine()
    adapters = build_components(default_registry(), world)
    pde = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde"))
    pymunk = cast(PymunkAdapter, adapter_by_id(adapters, "pymunk"))
    mesa = cast(MesaAdapter, adapter_by_id(adapters, "mesa"))

    def _initialize() -> None:
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    operations = build_morphogenesis_operations(
        pde, pymunk, mesa, config, trajectory, state
    )
    compose_into(
        engine,
        world,
        adapters,
        operations,
        on_initialize=_initialize,
        contracts=MORPHOGENESIS_CONTRACTS,
    )
    engine.run()
    metrics = build_morphogenesis_metrics(trajectory)
    return ExecOutcome(world=world, metrics=metrics, trajectory=trajectory)