"""Experiment-facing runner and metric characterization for Experiment E (Fluid-Structure Active Matter)."""

from __future__ import annotations

from typing import cast

import numpy as np

from experiments.fluid_active_matter.coupling import (
    FLUID_ACTIVE_MATTER_CONTRACTS,
    FluidActiveMatterState,
    build_fluid_active_matter_operations,
    build_fluid_active_matter_registry,
)
from experiments.fluid_active_matter.model import (
    FluidActiveMatterConfig,
    FluidActiveMatterTrajectory,
    FluidEngineAdapter,
    SwimmersAdapter,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.behavior import ObservableSeries
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event
from sim_alchemist.core.mutation import ParameterSpec
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        path="config.viscosity",
        description="Kinematic viscosity of the fluid medium.",
        minimum=0.005,
        maximum=0.5,
    ),
    ParameterSpec(
        path="config.buoyancy_coef",
        description="Coupling coefficient converting chemical gradient into fluid buoyancy torque.",
        minimum=0.0,
        maximum=3.0,
    ),
    ParameterSpec(
        path="config.swimmer_speed",
        description="Self-propulsion speed of micro-swimmer particles.",
        minimum=0.005,
        maximum=0.3,
    ),
)


def specs_by_path() -> dict[str, ParameterSpec]:
    return {s.path: s for s in PARAMETER_SPECS}


def build_fluid_active_matter_metrics(trajectory: FluidActiveMatterTrajectory) -> dict[str, float]:
    """Calculate aggregated physical and emergent metrics from Experiment E trajectory."""
    if not trajectory.fluid_energies:
        return {
            "fluid_kinetic_energy:mean": 0.0,
            "fluid_vorticity:max": 0.0,
            "swimmer_speed:mean": 0.0,
            "u_field:mean": 0.0,
            "u_field:variance": 0.0,
        }

    mean_ke = float(np.mean(trajectory.fluid_energies))
    max_vort = float(np.max(trajectory.vorticities)) if trajectory.vorticities else 0.0
    mean_speed = float(np.mean(trajectory.speeds)) if trajectory.speeds else 0.0

    u_means: list[float] = []
    u_vars: list[float] = []
    for snap in trajectory.u_snaps:
        u_means.append(float(np.mean(snap)))
        u_vars.append(float(np.var(snap)))

    return {
        "fluid_kinetic_energy:mean": mean_ke,
        "fluid_vorticity:max": max_vort,
        "swimmer_speed:mean": mean_speed,
        "u_field:mean": float(np.mean(u_means)) if u_means else 0.0,
        "u_field:variance": float(np.mean(u_vars)) if u_vars else 0.0,
    }


def build_fluid_active_matter_observables(trajectory: FluidActiveMatterTrajectory) -> dict[str, ObservableSeries]:
    """Construct validated ObservableSeries across macro-step time points."""
    t = trajectory.time_points
    if not t:
        return {}

    u_mean_vals = [float(np.mean(snap)) for snap in trajectory.u_snaps]
    u_var_vals = [float(np.var(snap)) for snap in trajectory.u_snaps]

    return {
        "fluid_kinetic_energy": ObservableSeries(times=tuple(t), values=tuple(trajectory.fluid_energies), name="fluid_kinetic_energy"),
        "fluid_vorticity_max": ObservableSeries(times=tuple(t), values=tuple(trajectory.vorticities), name="fluid_vorticity_max"),
        "swimmer_speed_mean": ObservableSeries(times=tuple(t), values=tuple(trajectory.speeds), name="swimmer_speed_mean"),
        "u_field_mean": ObservableSeries(times=tuple(t), values=tuple(u_mean_vals), name="u_field_mean"),
        "u_field_variance": ObservableSeries(times=tuple(t), values=tuple(u_var_vals), name="u_field_variance"),
    }


def run_fluid_active_matter_world(world: WorldDefinition) -> ExecOutcome:
    """Conforming executor executing a fluid-structure active matter world."""
    cfg_data = dict(world.config)
    n = int(cfg_data.get("n", 32))
    seed = int(world.seed)
    max_steps = int(world.max_steps)
    macro_dt = float(world.macro_timestep)

    config = FluidActiveMatterConfig(
        n=n,
        seed=seed,
        pde_dt=float(cfg_data.get("pde_dt", 5.0e-4)),
        du=float(cfg_data.get("du", 0.005)),
        dv=float(cfg_data.get("dv", 0.2)),
        a=float(cfg_data.get("a", 0.1)),
        b=float(cfg_data.get("b", 0.9)),
        macro_timestep=macro_dt,
        n_steps=max_steps,
        viscosity=float(cfg_data.get("viscosity", 0.05)),
        buoyancy_coef=float(cfg_data.get("buoyancy_coef", 0.8)),
        fluid_damping=float(cfg_data.get("fluid_damping", 0.02)),
        n_swimmers=int(cfg_data.get("n_swimmers", 8)),
        swimmer_speed=float(cfg_data.get("swimmer_speed", 0.08)),
        swimmer_radius=float(cfg_data.get("swimmer_radius", 0.04)),
        advection_drag=float(cfg_data.get("advection_drag", 1.2)),
        chemotaxis_strength=float(cfg_data.get("chemotaxis_strength", 0.6)),
        rotational_diffusion=float(cfg_data.get("rotational_diffusion", 0.1)),
        source_u=float(cfg_data.get("source_u", 0.02)),
        source_v=float(cfg_data.get("source_v", -0.03)),
        source_radius=float(cfg_data.get("source_radius", 0.04)),
    )

    registry = build_fluid_active_matter_registry()
    adapters = build_components(registry, world)
    pde_adapter = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde"))
    fluid_adapter = cast(FluidEngineAdapter, adapter_by_id(adapters, "fluid"))
    swimmers_adapter = cast(SwimmersAdapter, adapter_by_id(adapters, "pymunk"))

    trajectory = FluidActiveMatterTrajectory()
    state = FluidActiveMatterState()

    ops = build_fluid_active_matter_operations(
        pde=pde_adapter,
        fluid=fluid_adapter,
        swimmers=swimmers_adapter,
        config=config,
        trajectory=trajectory,
        state=state,
    )

    engine = AlchemistEngine()

    def _initialize() -> None:
        pde_adapter.set_event_bus(engine.event_bus)
        fluid_adapter.set_event_bus(engine.event_bus)
        swimmers_adapter.set_event_bus(engine.event_bus)

    def _on_step(time: float, dt: float, step: int) -> None:
        engine.event_bus.publish(Event.time_step("alchemist", time, dt))

    compose_into(
        engine,
        world,
        adapters,
        ops,
        on_step=_on_step,
        on_initialize=_initialize,
        contracts=FLUID_ACTIVE_MATTER_CONTRACTS,
    )
    engine.run()

    metrics = build_fluid_active_matter_metrics(trajectory)
    return ExecOutcome(
        world=world,
        metrics=metrics,
        trajectory=trajectory,
    )
