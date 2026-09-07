"""Experiment C declarations for the generic mutation/lineage layer (Task 1.6).

This is the experiment-facing side of the Task 1.6 contract: the *generic*
core consumes nothing experiment-specific, so the experiment must expose,
in a generic vocabulary:

- ``PARAMETER_SPECS`` -- the meaningful, mutable parameters as generic
  ``ParameterSpec`` declarations (path + value bounds only);
- ``build_network_metrics`` -- trajectory -> compact metric dict;
- ``run_network_world`` -- an ``Executor`` that runs *any* (base or mutated)
  ``WorldDefinition`` through the generic composition path and returns an
  ``ExecOutcome`` with compact metrics.

The mutable parameters are exactly the ones that already carry experimental
meaning in the coupling layer:

- ``components.network.config.loss``  -- NDlib diffusion loss
  (``new_load = (1-loss)*mine + beta*neighbours``); this is the *effective*
  value (consumed by the network adapter), as opposed to the mirrored
  ``config.network_loss`` shorthand which the coupling never reads.
- ``config.force_fmax``               -- wall force saturation bound.
- ``config.source_amplitude``         -- load-to-chemical-source gain.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any, cast

import numpy as np

from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    NetworkMorphogenesisState,
    build_network_morphogenesis_operations,
    build_network_morphogenesis_registry,
)
from experiments.network_morphogenesis.model import (
    NetworkMorphogenesisConfig,
    NetworkMorphogenesisTrajectory,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.behavior import ObservableSeries
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.mutation import ParameterSpec
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "PARAMETER_SPECS",
    "build_network_metrics",
    "build_network_observables",
    "run_network_world",
    "specs_by_path",
]

PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        path="components.network.config.loss",
        description="network diffusion loss (retention (1-loss) of own load)",
        minimum=0.0,
        maximum=1.0,
    ),
    ParameterSpec(
        path="config.force_fmax",
        description="saturation bound of the field-gradient wall force",
        minimum=0.0,
        maximum=10.0,
    ),
    ParameterSpec(
        path="config.source_amplitude",
        description="chemical source gain per unit network load",
        minimum=0.0,
        maximum=1.0,
    ),
)


def specs_by_path() -> dict[str, ParameterSpec]:
    return {s.path: s for s in PARAMETER_SPECS}


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


def build_network_metrics(trajectory: NetworkMorphogenesisTrajectory) -> dict[str, float]:
    """Collapse a trajectory to the compact metric summary for lineage."""
    final = np.asarray(trajectory.final_u).copy()
    grown = {e for e in trajectory.edge_grown if e is not None}
    return {
        "final_field_mean": float(final.mean()),
        "final_field_std": float(final.std()),
        "field_entropy": _field_entropy(final),
        "wall_count": float(trajectory.walls_per_step[-1]) if trajectory.walls_per_step else 0.0,
        "wall_movement": _total_wall_movement(trajectory.wall_tracks),
        "network_load_mean": float(trajectory.mean_load[-1]) if trajectory.mean_load else 0.0,
        "network_load_max": float(trajectory.max_load[-1]) if trajectory.max_load else 0.0,
        "n_sources": float(trajectory.n_sources[-1]) if trajectory.n_sources else 0.0,
        "growth_edges": float(len(grown)),
    }


def build_network_observables(
    trajectory: NetworkMorphogenesisTrajectory,
) -> dict[str, ObservableSeries]:
    """Task 1.8: expose the compact per-step observables of one run.

    Returns one ``ObservableSeries`` per observable, on the macro-step time
    axis ``t_field``.  Field mean/std are derived in-memory from the field
    snapshots; only the scalar series are returned (never the raw grids).
    These series feed the generic behavior analyzer; nothing here is a metric
    name the core knows about.
    """
    times = tuple(float(t) for t in trajectory.t_field)
    if not times:
        return {}

    def _series(name: str, values: Sequence[float]) -> ObservableSeries:
        return ObservableSeries(name=name, times=times, values=tuple(float(v) for v in values))

    field_means = [float(np.asarray(u).mean()) for u in trajectory.u_snaps]
    field_stds = [float(np.asarray(u).std()) for u in trajectory.u_snaps]

    return {
        "wall_count": _series("wall_count", trajectory.walls_per_step),
        "wall_activity": _series("wall_activity", trajectory.wall_speeds),
        "wall_force": _series("wall_force", trajectory.force_mags),
        "field_mean": _series("field_mean", field_means),
        "field_std": _series("field_std", field_stds),
        "network_load_mean": _series("network_load_mean", trajectory.mean_load),
        "network_load_max": _series("network_load_max", trajectory.max_load),
        "active_sources": _series("active_sources", trajectory.n_sources),
        "growth_event": _series(
            "growth_event",
            [1.0 if e is not None else 0.0 for e in trajectory.edge_grown],
        ),
    }


def run_network_world(world: WorldDefinition) -> ExecOutcome:
    """Executor: run *any* network world through the generic composition path.

    Mirrors the plain ``compose`` path of Task 1.5 (already proven bitwise
    identical to the facade); adapters are rebuilt per call so re-runs are
    independently seeded by the world's own ``seed`` (deterministic replay).
    """
    registry = build_network_morphogenesis_registry()
    adapters = build_components(registry, world)
    pde = cast(PyPDEAdapter, adapters[0])
    pymunk = cast(PymunkAdapter, adapters[1])
    network = cast(AdaptiveNetworkAdapter, adapters[2])

    config = NetworkMorphogenesisConfig.from_world(world)
    trajectory = NetworkMorphogenesisTrajectory(config=config)
    state = NetworkMorphogenesisState()
    operations = build_network_morphogenesis_operations(
        pde, pymunk, network, dict(world.config), trajectory, state
    )

    engine = AlchemistEngine()

    def _initialize() -> None:
        for a in (pde, pymunk, network):
            a.set_event_bus(engine.event_bus)
        field = pde.get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    compose_into(
        engine, world, adapters, operations, on_initialize=_initialize
    )
    engine.run()
    metrics = build_network_metrics(trajectory)
    return ExecOutcome(world=world, metrics=metrics, trajectory=trajectory)