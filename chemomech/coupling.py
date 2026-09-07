"""Experiment A coupling: morphogenesis schedule operations and world.

This module owns everything *experiment-specific* about the chemo-mechanical
morphogenesis world: the declared macro-step ordering (``MORPHOGENESIS_SCHEDULE``),
the per-operation coupling rules (field-gradient forces, agent-intention
translation, observable recording), and the declarative ``WorldDefinition``
builder.  The core composer turns that definition into a plain
``AlchemistEngine``; nothing here reaches into ``src/sim_alchemist/core/
engine.py``.

The operation handlers are plain closures built by ``build_morphogenesis_operations``.
Each receives the macro timestep ``dt`` and is dispatched by the core
``StepScheduler``.  Anything the operations must share across a macro step
(total force, wall count, mean speed) or persist across the run (cumulative
dissolved count) lives in ``MorphogenesisState``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from chemomech.reaction_diffusion import RDField
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.contracts import CouplingContract
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

if TYPE_CHECKING:
    from chemomech.simulation import Trajectory, WorldConfig


MORPHOGENESIS_SCHEDULE: tuple[str, ...] = (
    "geometry.sync",
    "field.step",
    "physics.force",
    "physics.step",
    "agents.step",
    "agents.apply",
    "observables.record",
)


MORPHOGENESIS_CONTRACTS: tuple[CouplingContract, ...] = (
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
        name="wall-intentions",
        producer="mesa",
        producer_capability="agent_intentions",
        consumer="pymunk",
        consumer_capability="rigid_body",
        payload=(("intentions", "array_1d"),),
        transform="wall-intentions",
        variant="walls",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="field-sensing",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("u", "array_1d"), ("v", "array_1d")),
        transform="field-sensing",
        coordinate_system="unit-square-2d",
    ),
)


@dataclass
class MorphogenesisState:
    """Scratch + persistent state shared across the schedule operations.

    ``total_force`` / ``n_walls`` / ``speed_sum`` are per-macro-step scratch
    values written by earlier operations and read by ``observables.record``.
    ``dissolved_total`` persists across the whole run (cumulative dissolve
    counter, matching the validated baseline).
    """

    total_force: float = 0.0
    n_walls: int = 0
    speed_sum: float = 0.0
    dissolved_total: int = 0


def morphogenesis_force(
    field: RDField,
    wall: Any,
    force_fmax: float,
    force_gsat: float,
) -> tuple[float, float]:
    """Mechanochemical force on a wall: F = Fmax * tanh(|grad u|/g_sat) * u_hat."""
    gx, gy = field.gradient(wall.center[0], wall.center[1], "u")
    gmag = math.hypot(gx, gy)
    if gmag == 0.0:
        return 0.0, 0.0
    magnitude = force_fmax * math.tanh(gmag / force_gsat)
    return magnitude * gx / gmag, magnitude * gy / gmag


def build_morphogenesis_world(config: WorldConfig) -> WorldDefinition:
    """The declarative world definition reproducing Experiment A exactly."""
    agent_configs = [
        {"x": ac.x, "y": ac.y, "build_threshold": ac.build_threshold,
         "wall_length": ac.wall_length, "wall_radius": ac.wall_radius,
         "wall_offset": ac.wall_offset, "min_separation": ac.min_separation,
         "cooldown": ac.cooldown, "dissolve_threshold": ac.dissolve_threshold,
         "dissolve_min_age": ac.dissolve_min_age}
        for ac in config.default_agents()
    ]
    return WorldDefinition(
        id="chemo_morphogenesis",
        components=(
            ComponentSpec("py-pde", {
                "n": config.n, "du": config.du, "dv": config.dv,
                "a": config.a, "b": config.b, "dt": config.pde_dt,
                "seed": config.seed, "field_step": config.field_step,
            }),
            ComponentSpec("pymunk", {
                "n": config.n, "mass": config.wall_mass,
                "damping": config.wall_damping, "dt_phys": config.phys_dt,
                "phys_substeps": config.phys_substeps,
            }),
            ComponentSpec("mesa", {
                "agent_configs": agent_configs, "seed": config.seed,
                "macro_timestep": config.field_step,
            }),
        ),
        requires=("agent_population", "reaction_diffusion", "rigid_body", "field_gradient"),
        schedule=MORPHOGENESIS_SCHEDULE,
        macro_timestep=config.field_step,
        max_steps=config.n_steps,
        seed=config.seed,
        config={
            "n": config.n,
            "seed": config.seed,
            "pde_dt": config.pde_dt,
            "du": config.du,
            "dv": config.dv,
            "a": config.a,
            "b": config.b,
            "field_step": config.field_step,
            "n_steps": config.n_steps,
            "feedback": config.feedback,
            "build_walls": config.build_walls,
            "apply_forces": config.apply_forces,
            "force_fmax": config.force_fmax,
            "force_gsat": config.force_gsat,
            "wall_mass": config.wall_mass,
            "wall_damping": config.wall_damping,
            "phys_dt": config.phys_dt,
            "phys_substeps": config.phys_substeps,
        },
    )


def build_morphogenesis_operations(
    pde: PyPDEAdapter,
    pymunk: PymunkAdapter,
    mesa: MesaAdapter,
    config: WorldConfig,
    trajectory: Trajectory,
    state: MorphogenesisState,
) -> dict[str, Callable[[float], None]]:
    """Build the ordered coupling-operation handlers for the morphogenesis world.

    The returned mapping resolves every name in ``MORPHOGENESIS_SCHEDULE``.
    Handler bodies reproduce the validated baseline exactly (same order, same
    formulas, same observable bookkeeping).
    """

    def run_geometry_sync(dt: float) -> None:
        blocked = pymunk.get_geometry()["blocked"]
        if config.feedback and config.build_walls:
            pde.set_blocked(blocked)
        else:
            pde.set_blocked(np.zeros_like(blocked))

    def run_field_step(dt: float) -> None:
        pde.step(config.field_step)

    def run_physics_force(dt: float) -> None:
        total_force = 0.0
        if config.apply_forces and pymunk._wallspace:
            for w in pymunk._wallspace.walls:
                fx, fy = morphogenesis_force(
                    cast(RDField, pde.get_field()), w, config.force_fmax, config.force_gsat
                )
                pymunk.apply_force(w.id, fx, fy)
                total_force += math.hypot(fx, fy)
        state.total_force = total_force

    def run_physics_step(dt: float) -> None:
        pymunk.step(config.field_step)
        pymunk_state = pymunk.get_state()
        n_walls = len(pymunk_state.get("walls", []))
        speed_sum = 0.0
        if pymunk._wallspace:
            speed_sum = sum(
                math.hypot(w.body.velocity.x, w.body.velocity.y) / pymunk._wallspace.scale
                for w in pymunk._wallspace.walls
            )
        state.n_walls = n_walls
        state.speed_sum = speed_sum

    def run_agents_step(dt: float) -> None:
        mesa.step(config.field_step)

    def run_agents_apply(dt: float) -> None:
        _translate_agent_actions()

    def run_observables_record(dt: float) -> None:
        _record_observables()

    def _translate_agent_actions() -> None:
        if mesa._model is None:
            return
        for agent in mesa._model.agents:
            for w in agent.pending_dissolve:
                if w in agent.own_walls:
                    agent.own_walls.remove(w)
                pymunk.remove_wall(w.id)
                state.dissolved_total += 1
            if config.build_walls and agent.pending_wall is not None and pymunk._wallspace is not None:
                p1, p2, radius, _angle = agent.pending_wall
                wall = pymunk._wallspace.add_wall(
                    p1, p2, radius, t=cast(RDField, pde.get_field()).t, owner=agent.unique_id
                )
                agent.own_walls.append(wall)

    def _record_observables() -> None:
        s = state
        field = cast(RDField, pde.get_field())
        blocked = pymunk.get_geometry()["blocked"]

        trajectory.t_field.append(field.t)
        trajectory.u_snaps.append(field.u.copy())
        trajectory.blocked_snaps.append(blocked.copy())
        trajectory.walls_per_step.append(s.n_walls)
        trajectory.wall_geometry_snaps.append(pymunk.get_geometry()["segments"])
        trajectory.force_mags.append(s.total_force / max(1, s.n_walls))
        trajectory.wall_speeds.append(s.speed_sum / max(1, s.n_walls))
        trajectory.dissolved_count.append(s.dissolved_total)

        if pymunk._wallspace:
            for w in pymunk._wallspace.walls:
                trajectory.wall_tracks.setdefault(w.id, []).append(
                    (field.t, w.center[0], w.center[1], w.angle)
                )

        if mesa._model:
            for i, agent in enumerate(mesa._model.agents):
                if agent.history:
                    trajectory.agent_histories.setdefault(i, []).append(agent.history[-1])

    return {
        "geometry.sync": run_geometry_sync,
        "field.step": run_field_step,
        "physics.force": run_physics_force,
        "physics.step": run_physics_step,
        "agents.step": run_agents_step,
        "agents.apply": run_agents_apply,
        "observables.record": run_observables_record,
    }