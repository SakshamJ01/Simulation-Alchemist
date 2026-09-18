"""Experiment E coupling: fluid-structure active matter schedule, contracts, world, and operations.

Coupling Family:
    * Continuous Reaction-Diffusion PDE (py-pde)
    * Incompressible Navier-Stokes Fluid Convection (fluid)
    * Active Swimmer Micro-Particles (pymunk/swimmers)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.composition import ComponentBinding
from sim_alchemist.core.contracts import CouplingContract
from sim_alchemist.core.registry import ComponentRegistry, default_registry
from sim_alchemist.core.templates import CouplingTemplate
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

if TYPE_CHECKING:
    from experiments.fluid_active_matter.model import (
        FluidActiveMatterConfig,
        FluidActiveMatterTrajectory,
        FluidEngineAdapter,
        SwimmersAdapter,
    )


FLUID_ACTIVE_MATTER_SCHEDULE: tuple[str, ...] = (
    "field.step",
    "fluid.buoyancy",
    "fluid.step",
    "swimmers.advect",
    "swimmers.steer",
    "swimmers.step",
    "field.source",
    "observables.record",
)

FLUID_ACTIVE_MATTER_OPERATIONS: tuple[str, ...] = FLUID_ACTIVE_MATTER_SCHEDULE

FLUID_ACTIVE_MATTER_CONTRACTS: tuple[CouplingContract, ...] = (
    CouplingContract(
        name="field-buoyancy",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="fluid",
        consumer_capability="fluid_state",
        payload=(("u", "array_1d"), ("v", "array_1d")),
        transform="chemical-buoyancy",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="fluid-advection",
        producer="fluid",
        producer_capability="velocity_field",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("velocity", "vec2_list"),),
        transform="fluid-drag",
        variant="swimmers",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="gradient-steering",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="chemotactic-steering",
        variant="swimmers",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="swimmer-source",
        producer="pymunk",
        producer_capability="geometry_provider",
        consumer="py-pde",
        consumer_capability="field_sources",
        payload=(("positions", "vec2_list"),),
        transform="swimmer-excretion",
        variant="swimmers",
        coordinate_system="unit-square-2d",
    ),
)


@dataclass
class FluidActiveMatterState:
    """Transient state carried across macro-step coupling operations."""

    step_index: int = 0
    time: float = 0.0
    mean_fluid_energy: float = 0.0
    max_vorticity: float = 0.0
    mean_swimmer_speed: float = 0.0


def build_fluid_active_matter_world(config: FluidActiveMatterConfig | None = None) -> WorldDefinition:
    """Build a declarative WorldDefinition for Experiment E."""
    from experiments.fluid_active_matter.model import FluidActiveMatterConfig

    cfg = config if config is not None else FluidActiveMatterConfig()
    cfg_dict = {
        "n": cfg.n,
        "seed": cfg.seed,
        "pde_dt": cfg.pde_dt,
        "du": cfg.du,
        "dv": cfg.dv,
        "a": cfg.a,
        "b": cfg.b,
        "macro_timestep": cfg.macro_timestep,
        "n_steps": cfg.n_steps,
        "viscosity": cfg.viscosity,
        "buoyancy_coef": cfg.buoyancy_coef,
        "fluid_damping": cfg.fluid_damping,
        "n_swimmers": cfg.n_swimmers,
        "swimmer_speed": cfg.swimmer_speed,
        "swimmer_radius": cfg.swimmer_radius,
        "advection_drag": cfg.advection_drag,
        "chemotaxis_strength": cfg.chemotaxis_strength,
        "rotational_diffusion": cfg.rotational_diffusion,
        "source_u": cfg.source_u,
        "source_v": cfg.source_v,
        "source_radius": cfg.source_radius,
    }

    return WorldDefinition(
        id="fluid_active_matter",
        components=(
            ComponentSpec("py-pde", {
                "n": cfg.n,
                "du": cfg.du,
                "dv": cfg.dv,
                "a": cfg.a,
                "b": cfg.b,
                "dt": cfg.pde_dt,
                "seed": cfg.seed,
                "field_step": cfg.macro_timestep,
            }),
            ComponentSpec("fluid", {
                "n": cfg.n,
                "viscosity": cfg.viscosity,
                "buoyancy_coef": cfg.buoyancy_coef,
                "fluid_damping": cfg.fluid_damping,
            }),
            ComponentSpec("pymunk", {
                "n_swimmers": cfg.n_swimmers,
                "swimmer_speed": cfg.swimmer_speed,
                "swimmer_radius": cfg.swimmer_radius,
                "advection_drag": cfg.advection_drag,
                "chemotaxis_strength": cfg.chemotaxis_strength,
                "rotational_diffusion": cfg.rotational_diffusion,
                "seed": cfg.seed,
            }),
        ),
        requires=("reaction_diffusion", "velocity_field", "particle_positions", "field_gradient"),
        schedule=FLUID_ACTIVE_MATTER_SCHEDULE,
        macro_timestep=cfg.macro_timestep,
        max_steps=cfg.n_steps,
        seed=cfg.seed,
        config=cfg_dict,
    )


def build_fluid_active_matter_template() -> CouplingTemplate:
    """The declared coupling template of the fluid-structure active matter composition."""
    from experiments.fluid_active_matter.model import FluidActiveMatterConfig

    world = build_fluid_active_matter_world(FluidActiveMatterConfig())
    return CouplingTemplate(
        name="fluid_active_matter",
        bindings=(
            ComponentBinding("fluid"),
            ComponentBinding("py-pde"),
            ComponentBinding("pymunk", "swimmers"),
        ),
        world_id=world.id,
        contracts=FLUID_ACTIVE_MATTER_CONTRACTS,
        schedule=FLUID_ACTIVE_MATTER_SCHEDULE,
        operations=FLUID_ACTIVE_MATTER_OPERATIONS,
        requires=world.requires,
        executor_ref="experiments.fluid_active_matter.experiment.run_fluid_active_matter_world",
        component_configs={spec.id: dict(spec.config) for spec in world.components},
        macro_timestep=world.macro_timestep,
        max_steps=world.max_steps,
        seed=world.seed,
        config=dict(world.config),
    )


def build_fluid_active_matter_registry() -> ComponentRegistry:
    """Component registry providing the fluid solver and swimmers physics adapters."""
    from experiments.fluid_active_matter.model import (
        FluidEngineAdapter,
        SwimmersAdapter,
    )

    registry = default_registry()

    def _fluid_factory(cfg: dict[str, Any]) -> FluidEngineAdapter:
        return FluidEngineAdapter(config=cfg)

    def _swimmers_factory(cfg: dict[str, Any]) -> SwimmersAdapter:
        return SwimmersAdapter(config=cfg)

    registry.register("fluid", _fluid_factory)
    registry.register("pymunk", _swimmers_factory)
    return registry


def build_fluid_active_matter_operations(
    pde: PyPDEAdapter,
    fluid: FluidEngineAdapter,
    swimmers: SwimmersAdapter,
    config: FluidActiveMatterConfig,
    trajectory: FluidActiveMatterTrajectory,
    state: FluidActiveMatterState,
) -> dict[str, Callable[[float], None]]:
    """Build the ordered coupling-operation handlers for Experiment E."""

    def run_field_step(dt: float) -> None:
        pde.step(config.macro_timestep)

    def run_fluid_buoyancy(dt: float) -> None:
        # Chemical concentration u exerts buoyancy torque driving fluid circulation
        field = pde.get_field()
        if field is not None:
            fluid.apply_buoyancy_torque(field.u, beta=config.buoyancy_coef)

    def run_fluid_step(dt: float) -> None:
        fluid.step(config.macro_timestep)

    def run_swimmers_advect(dt: float) -> None:
        # Background fluid drag advects swimmer particles
        swimmers.apply_fluid_advection(fluid)

    def run_swimmers_steer(dt: float) -> None:
        # Chemotactic gradient steering function
        field = pde.get_field()
        if field is None:
            return
        u_arr = field.u
        n_grid = field.n
        dx = 1.0 / float(n_grid)

        def sample_grad(x: float, y: float) -> tuple[float, float]:
            gx = max(0.0, min(0.999, x)) * n_grid
            gy = max(0.0, min(0.999, y)) * n_grid
            ix = int(gx) % n_grid
            iy = int(gy) % n_grid
            ix_next = (ix + 1) % n_grid
            ix_prev = (ix - 1) % n_grid
            iy_next = (iy + 1) % n_grid
            iy_prev = (iy - 1) % n_grid

            du_dx = float((u_arr[ix_next, iy] - u_arr[ix_prev, iy]) / (2.0 * dx))
            du_dy = float((u_arr[ix, iy_next] - u_arr[ix, iy_prev]) / (2.0 * dx))
            return du_dx, du_dy

        swimmers.apply_chemotactic_steering_and_propulsion(sample_grad, config.macro_timestep)

    def run_swimmers_step(dt: float) -> None:
        swimmers.step(config.macro_timestep)

    def run_field_source(dt: float) -> None:
        # Swimmer particles excrete chemical source into PDE field
        pos_map = swimmers.get_positions()
        pts = list(pos_map.values())
        if pts and abs(config.source_u) > 1e-7:
            sources = [
                {
                    "x": pt[0],
                    "y": pt[1],
                    "u": config.source_u * config.macro_timestep,
                    "v": config.source_v * config.macro_timestep,
                    "radius": config.source_radius,
                }
                for pt in pts
            ]
            pde.apply_sources(sources)

    def run_observables_record(dt: float) -> None:
        state.step_index += 1
        state.time += config.macro_timestep

        field = pde.get_field()
        if field is not None:
            u_snap = np.copy(field.u)
            v_snap = np.copy(field.v)
            trajectory.u_snaps.append(u_snap)
            trajectory.v_snaps.append(v_snap)

        omega_snap = np.copy(fluid.omega)
        ux_snap = np.copy(fluid.u_x)
        uy_snap = np.copy(fluid.u_y)

        trajectory.omega_snaps.append(omega_snap)
        trajectory.ux_snaps.append(ux_snap)
        trajectory.uy_snaps.append(uy_snap)

        cur_positions = swimmers.get_positions()
        cur_velocities = swimmers.get_velocities()
        cur_orientations = swimmers.get_orientations()

        for s_id, pt in cur_positions.items():
            trajectory.positions.setdefault(s_id, []).append(pt)
        for s_id, vel in cur_velocities.items():
            trajectory.velocities.setdefault(s_id, []).append(vel)
        for s_id, ori in cur_orientations.items():
            trajectory.orientations.setdefault(s_id, []).append(ori)

        ke = fluid.kinetic_energy()
        vort = fluid.max_vorticity()
        speed = swimmers.mean_swimmer_speed()

        trajectory.fluid_energies.append(ke)
        trajectory.vorticities.append(vort)
        trajectory.speeds.append(speed)
        trajectory.time_points.append(state.time)

        state.mean_fluid_energy = ke
        state.max_vorticity = vort
        state.mean_swimmer_speed = speed

    return {
        "field.step": run_field_step,
        "fluid.buoyancy": run_fluid_buoyancy,
        "fluid.step": run_fluid_step,
        "swimmers.advect": run_swimmers_advect,
        "swimmers.steer": run_swimmers_steer,
        "swimmers.step": run_swimmers_step,
        "field.source": run_field_source,
        "observables.record": run_observables_record,
    }
