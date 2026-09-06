"""Adaptive Network Morphogenesis model: NDlib + py-pde + Pymunk.

Experiment C: a network of nodes carrying continuous scalar loads diffuses
via a custom weighted-averaging / transport rule.  Each node injects a
chemical source into the py-pde field; the field gradient drives Pymunk
walls; the wall geometry feeds back to network edge weights.

All coupling lives in ``experiments.network_morphogenesis.coupling``.
The facade contains no scheduling logic: it composes through the generic
core composer and is driven by the core ``StepScheduler``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np

from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    NETWORK_MORPHOGENESIS_SCHEDULE,
    NetworkMorphogenesisState,
    build_network_morphogenesis_operations,
    build_network_morphogenesis_registry,
    build_network_morphogenesis_world,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "NETWORK_MORPHOGENESIS_SCHEDULE",
    "NetworkMorphogenesisConfig",
]


@dataclass
class NetworkMorphogenesisConfig:
    n: int = 32
    seed: int = 0
    pde_dt: float = 5.0e-4
    du: float = 0.005
    dv: float = 0.2
    a: float = 0.1
    b: float = 0.9
    field_step: float = 0.2
    n_steps: int = 160

    mass: float = 1.0
    wall_damping: float = 0.05
    phys_dt: float = 0.05
    phys_substeps: int = 4

    grid_rows: int = 4
    grid_cols: int = 6
    network_beta: float = 0.3
    network_loss: float = 0.05

    force_fmax: float = 0.8
    force_gsat: float = 2.0
    source_amplitude: float = 0.01
    source_radius: float = 0.08
    wall_radius: float = 0.02
    wall_mass: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n, "seed": self.seed,
            "pde_dt": self.pde_dt, "du": self.du, "dv": self.dv,
            "a": self.a, "b": self.b,
            "field_step": self.field_step, "n_steps": self.n_steps,
            "mass": self.mass, "wall_damping": self.wall_damping,
            "phys_dt": self.phys_dt, "phys_substeps": self.phys_substeps,
            "grid_rows": self.grid_rows, "grid_cols": self.grid_cols,
            "network_beta": self.network_beta, "network_loss": self.network_loss,
            "force_fmax": self.force_fmax, "force_gsat": self.force_gsat,
            "source_amplitude": self.source_amplitude,
            "source_radius": self.source_radius,
            "wall_radius": self.wall_radius, "wall_mass": self.wall_mass,
        }

    @classmethod
    def from_world(cls, world: WorldDefinition) -> NetworkMorphogenesisConfig:
        """Reconstruct the facade-equivalent config from a world snapshot.

        ``build_network_morphogenesis_world`` mirrors every config field into
        the world's shared ``config`` dict, so this is an exact inverse for
        world-driven (incl. mutated) execution.
        """
        field_names = set(cls.__dataclass_fields__)
        kwargs: dict[str, Any] = {
            k: v for k, v in world.config.items() if k in field_names
        }
        if "n_steps" not in kwargs:
            kwargs["n_steps"] = int(world.max_steps)
        return cls(**kwargs)


@dataclass
class NetworkMorphogenesisTrajectory:
    config: NetworkMorphogenesisConfig
    t_field: list[float] = field(default_factory=list)
    u_snaps: list[np.ndarray] = field(default_factory=list)
    blocked_snaps: list[np.ndarray] = field(default_factory=list)
    walls_per_step: list[int] = field(default_factory=list)
    force_mags: list[float] = field(default_factory=list)
    wall_speeds: list[float] = field(default_factory=list)
    wall_geometry_snaps: list[Any] = field(default_factory=list)
    wall_tracks: dict[int, list[tuple[float, float, float, float]]] = field(default_factory=dict)
    dissolved_count: list[int] = field(default_factory=list)
    mean_load: list[float] = field(default_factory=list)
    max_load: list[float] = field(default_factory=list)
    n_sources: list[int] = field(default_factory=list)
    edge_grown: list[tuple[int, int] | None] = field(default_factory=list)
    start_u: np.ndarray = field(default_factory=lambda: np.empty(0))
    trace: Any = field(default=None, init=False, repr=False)

    @property
    def final_u(self) -> np.ndarray:
        return self.u_snaps[-1]

    def engine_trace(self) -> Any:
        return self.trace


def run_network_morphogenesis(config: NetworkMorphogenesisConfig) -> NetworkMorphogenesisTrajectory:
    engine = NetworkMorphogenesisEngine(config=config)
    return engine.run()


class NetworkMorphogenesisEngine(AlchemistEngine):
    SCHEDULE: tuple[str, ...] = NETWORK_MORPHOGENESIS_SCHEDULE

    def __init__(self, config: NetworkMorphogenesisConfig) -> None:
        super().__init__()
        self._config = config
        self.trajectory = NetworkMorphogenesisTrajectory(config=config)

        world = build_network_morphogenesis_world(
            n=config.n, du=config.du, dv=config.dv,
            a=config.a, b=config.b, pde_dt=config.pde_dt,
            field_step=config.field_step, mass=config.mass,
            wall_damping=config.wall_damping, phys_dt=config.phys_dt,
            phys_substeps=config.phys_substeps,
            grid_rows=config.grid_rows, grid_cols=config.grid_cols,
            network_beta=config.network_beta, network_loss=config.network_loss,
            force_fmax=config.force_fmax, force_gsat=config.force_gsat,
            source_amplitude=config.source_amplitude,
            source_radius=config.source_radius,
            wall_radius=config.wall_radius, wall_mass=config.wall_mass,
            seed=config.seed, n_steps=config.n_steps,
        )
        registry = build_network_morphogenesis_registry()
        adapters = build_components(registry, world)
        self._pde_adapter = cast(PyPDEAdapter, adapters[0])
        self._pymunk_adapter = cast(PymunkAdapter, adapters[1])
        self._network_adapter = cast(AdaptiveNetworkAdapter, adapters[2])

        state = NetworkMorphogenesisState()
        operations = build_network_morphogenesis_operations(
            self._pde_adapter,
            self._pymunk_adapter,
            self._network_adapter,
            config.as_dict(),
            self.trajectory,
            state,
        )

        def _initialize() -> None:
            self._pde_adapter.set_event_bus(self.event_bus)
            self._pymunk_adapter.set_event_bus(self.event_bus)
            self._network_adapter.set_event_bus(self.event_bus)
            field = self._pde_adapter.get_field()
            if field is not None and self.trajectory.start_u.size == 0:
                self.trajectory.start_u = field.u.copy()

        def _on_step(time: float, dt: float, step: int) -> None:
            pass

        compose_into(
            self, world, adapters, operations,
            on_step=_on_step, on_initialize=_initialize,
        )

    def run(self) -> NetworkMorphogenesisTrajectory:  # type: ignore[override]
        super().run()
        assert self._scheduler is not None
        self.trajectory.trace = self._scheduler.trace
        return self.trajectory
