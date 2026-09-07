"""Experiment C coupling: Adaptive Network Morphogenesis schedule operations and world.

Three-domain triangle (NDlib network diffusion + py-pde field + pymunk walls):

    network load
        -->  PDE sources
        -->  field pattern
        -->  physical wall growth / movement
        -->  edge weighting / topology changes
        -->  network diffusion
        (repeat)

The declared macro-step order lives in ``NETWORK_MORPHOGENESIS_SCHEDULE``.
Operation handlers are closures built by
``build_network_morphogenesis_operations``, dispatched by the core
``StepScheduler``.  The declarative ``WorldDefinition`` builder plus a
registry builder make this world composable by the generic core composer.

The custom network update is a weighted-averaging / transport rule over
continuous node loads, **not** a physically calibrated nutrient transport
model.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.contracts import CouplingContract
from sim_alchemist.core.registry import ComponentRegistry, default_registry
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

NETWORK_MORPHOGENESIS_SCHEDULE: tuple[str, ...] = (
    "geometry.sync",
    "field.step",
    "physics.force",
    "physics.step",
    "physics.grow",
    "network.step",
    "network.route",
    "field.source",
    "observables.record",
)


NETWORK_MORPHOGENESIS_CONTRACTS: tuple[CouplingContract, ...] = (
    CouplingContract(
        name="blocked-mask",
        producer="pymunk",
        producer_capability="geometry_provider",
        consumer="py-pde",
        consumer_capability="field_masking",
        payload=(("blocked", "bool_2d"),),
        transform="blocked-mask",
        variant="walls",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="blocked-reweight",
        producer="pymunk",
        producer_capability="geometry_provider",
        consumer="network",
        consumer_capability="network_diffusion",
        payload=(("blocked", "bool_2d"),),
        transform="blocked-reweight",
        variant="walls",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
        variant="walls",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="load-source",
        producer="network",
        producer_capability="network_diffusion",
        consumer="py-pde",
        consumer_capability="field_sources",
        payload=(("load", "array_1d"), ("positions", "vec2_list")),
        transform="load-source",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="throughput-grow",
        producer="network",
        producer_capability="network_diffusion",
        consumer="pymunk",
        consumer_capability="rigid_body",
        payload=(("edge_throughput", "scalar"),),
        transform="throughput-grow",
        variant="walls",
        coordinate_system="unit-square-2d",
    ),
)


@dataclass
class NetworkMorphogenesisState:
    total_force: float = 0.0
    n_walls: int = 0
    speed_sum: float = 0.0
    mean_load: float = 0.0
    max_load: float = 0.0
    n_sources: int = 0
    edge_grown: tuple[int, int] | None = None


def network_morphogenesis_force(
    field: Any,
    wall: Any,
    force_fmax: float,
    force_gsat: float,
) -> tuple[float, float]:
    gx, gy = field.gradient(wall.center[0], wall.center[1], "u")
    gmag = math.hypot(gx, gy)
    if gmag == 0.0:
        return 0.0, 0.0
    magnitude = force_fmax * math.tanh(gmag / force_gsat)
    return magnitude * gx / gmag, magnitude * gy / gmag


def build_network_morphogenesis_world(
    *,
    n: int = 32,
    du: float = 0.005,
    dv: float = 0.2,
    a: float = 0.1,
    b: float = 0.9,
    pde_dt: float = 5.0e-4,
    field_step: float = 0.2,
    mass: float = 1.0,
    wall_damping: float = 0.05,
    phys_dt: float = 0.05,
    phys_substeps: int = 4,
    grid_rows: int = 4,
    grid_cols: int = 6,
    network_beta: float = 0.3,
    network_loss: float = 0.05,
    force_fmax: float = 0.8,
    force_gsat: float = 2.0,
    source_amplitude: float = 0.01,
    source_radius: float = 0.08,
    wall_radius: float = 0.02,
    wall_mass: float = 1.0,
    seed: int = 0,
    n_steps: int = 160,
) -> WorldDefinition:
    return WorldDefinition(
        id="adaptive_network",
        components=(
            ComponentSpec("py-pde", {
                "n": n, "du": du, "dv": dv,
                "a": a, "b": b, "dt": pde_dt,
                "seed": seed, "field_step": field_step,
            }),
            ComponentSpec("pymunk", {
                "n": n, "mass": mass,
                "damping": wall_damping, "dt_phys": phys_dt,
                "phys_substeps": phys_substeps,
            }),
            ComponentSpec("network", {
                "grid_rows": grid_rows,
                "grid_cols": grid_cols,
                "beta": network_beta,
                "loss": network_loss,
                "seed": seed,
            }),
        ),
        requires=(
            "reaction_diffusion",
            "rigid_body",
            "network_diffusion",
            "field_gradient",
        ),
        schedule=NETWORK_MORPHOGENESIS_SCHEDULE,
        macro_timestep=field_step,
        max_steps=n_steps,
        seed=seed,
        config={
            "n": n, "du": du, "dv": dv,
            "a": a, "b": b, "pde_dt": pde_dt,
            "field_step": field_step, "mass": mass,
            "wall_damping": wall_damping, "phys_dt": phys_dt,
            "phys_substeps": phys_substeps,
            "grid_rows": grid_rows, "grid_cols": grid_cols,
            "network_beta": network_beta, "network_loss": network_loss,
            "force_fmax": force_fmax, "force_gsat": force_gsat,
            "source_amplitude": source_amplitude,
            "source_radius": source_radius,
            "wall_radius": wall_radius, "wall_mass": wall_mass,
            "seed": seed, "n_steps": n_steps,
        },
    )


def build_network_morphogenesis_registry() -> ComponentRegistry:
    registry = default_registry()

    def _network_factory(cfg: dict[str, Any]) -> Any:
        from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
        kwargs = {k: cfg[k] for k in ("grid_rows", "grid_cols", "beta", "loss", "seed") if k in cfg}
        return AdaptiveNetworkAdapter(**kwargs)

    registry.register("network", _network_factory)
    return registry


def build_network_morphogenesis_operations(
    pde: PyPDEAdapter,
    pymunk: PymunkAdapter,
    network: Any,
    config: dict[str, Any],
    trajectory: Any,
    state: NetworkMorphogenesisState,
) -> dict[str, Callable[[float], None]]:
    """Build the ordered coupling-operation handlers for the network world."""
    from chemomech.reaction_diffusion import RDField

    force_fmax = config.get("force_fmax", 0.8)
    force_gsat = config.get("force_gsat", 2.0)
    source_amplitude = config.get("source_amplitude", 0.01)
    source_radius = config.get("source_radius", 0.08)
    wall_radius_param = config.get("wall_radius", 0.02)
    n = config.get("n", 32)
    field_step = config.get("field_step", 0.2)

    def run_geometry_sync(dt: float) -> None:
        blocked = _get_blocked()
        pde.set_blocked(blocked)
        network.set_blocked(blocked)
        network.reweight_from_geometry()

    def run_field_step(dt: float) -> None:
        pde.step(field_step)

    def run_physics_force(dt: float) -> None:
        total_force = 0.0
        if pymunk._wallspace:
            for w in pymunk._wallspace.walls:
                fx, fy = network_morphogenesis_force(
                    cast(RDField, pde.get_field()), w, force_fmax, force_gsat
                )
                pymunk.apply_force(w.id, fx, fy)
                total_force += math.hypot(fx, fy)
        state.total_force = total_force

    def run_physics_step(dt: float) -> None:
        pymunk.step(field_step)
        ps = pymunk.get_state()
        state.n_walls = len(ps.get("walls", []))
        speed_sum = 0.0
        if pymunk._wallspace:
            speed_sum = sum(
                math.hypot(w.body.velocity.x, w.body.velocity.y) / pymunk._wallspace.scale
                for w in pymunk._wallspace.walls
            )
        state.speed_sum = speed_sum

    def run_physics_grow(dt: float) -> None:
        state.edge_grown = None
        if pymunk._wallspace is None:
            return
        loads = network.get_load()
        if not loads:
            return
        edge = network.get_highest_throughput_edge(loads)
        if edge is None:
            return
        u_node, v_node = edge
        pos = network.get_node_positions()
        if u_node not in pos or v_node not in pos:
            return
        x1, y1 = pos[u_node]
        x2, y2 = pos[v_node]
        margin = wall_radius_param * 3
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-6:
            return
        dx = (x2 - x1) / length
        dy = (y2 - y1) / length
        px1 = x1 + margin * dx
        py1 = y1 + margin * dy
        px2 = x2 - margin * dx
        py2 = y2 - margin * dy
        pymunk.add_wall(
            (px1, py1), (px2, py2), wall_radius_param,
            t=cast(RDField, pde.get_field()).t,
        )
        state.edge_grown = edge

    def run_network_step(dt: float) -> None:
        network.step(field_step)
        network.nourish_reservoirs()

    def run_network_route(dt: float) -> None:
        network.reweight_from_geometry()

    def run_field_source(dt: float) -> None:
        loads = network.get_load()
        positions = network.get_node_positions()
        sources = []
        for nid, load_val in loads.items():
            if load_val > 1e-6 and nid in positions:
                x, y = positions[nid]
                sources.append({
                    "x": x, "y": y,
                    "u": source_amplitude * load_val,
                    "v": 0.0,
                    "radius": source_radius,
                })
        pde.apply_sources(sources)
        state.n_sources = len(sources)
        load_vals = list(loads.values())
        state.mean_load = sum(load_vals) / max(1, len(load_vals))
        state.max_load = max(load_vals) if load_vals else 0.0

    def run_observables_record(dt: float) -> None:
        field = cast(RDField, pde.get_field())
        blocked = _get_blocked()
        trajectory.t_field.append(field.t)
        trajectory.u_snaps.append(field.u.copy())
        trajectory.blocked_snaps.append(blocked.copy())
        trajectory.walls_per_step.append(state.n_walls)
        trajectory.force_mags.append(
            state.total_force / max(1, state.n_walls)
        )
        trajectory.wall_speeds.append(
            state.speed_sum / max(1, state.n_walls)
        )
        trajectory.mean_load.append(state.mean_load)
        trajectory.max_load.append(state.max_load)
        trajectory.n_sources.append(state.n_sources)
        trajectory.edge_grown.append(state.edge_grown)
        if pymunk._wallspace:
            for w in pymunk._wallspace.walls:
                trajectory.wall_tracks.setdefault(w.id, []).append(
                    (field.t, w.center[0], w.center[1], w.angle)
                )
        trajectory.wall_geometry_snaps.append(
            pymunk._wallspace.segments_world() if pymunk._wallspace else []
        )

    def _get_blocked() -> np.ndarray:
        if pymunk._wallspace is not None:
            return pymunk._wallspace.blocked()
        return np.zeros((n, n), dtype=bool)

    return {
        "geometry.sync": run_geometry_sync,
        "field.step": run_field_step,
        "physics.force": run_physics_force,
        "physics.step": run_physics_step,
        "physics.grow": run_physics_grow,
        "network.step": run_network_step,
        "network.route": run_network_route,
        "field.source": run_field_source,
        "observables.record": run_observables_record,
    }
