"""Composition engine: the closed chemo-mechanical feedback loop.

Macro-step order (deterministic, task-mandated):

    1. geometry        read live wall body transforms from pymunk
    2. rasterize       walls -> PDE blocked-cell mask (fed to the PDE RHS)
    3. evolve          py-pde advances the reaction-diffusion field
    4. sample force    field gradient sampled at each wall centre of mass
    5. apply force     bounded force applied to each wall body at its COM
    6. advance pymunk  wall bodies integrate (force, damping, bounds clamp)
    7. agents decide   Mesa agents sense the *new* field and decide
    8. translate       dissolve then create walls in the pymunk space

Force model (deliberately simple, documented)
---------------------------------------------
A wall is a rigid rod of mass ``m`` pivoting/translating in the plane.  The
morphogen drives it through the *mechanochemical force*

    F = Fmax * tanh( |grad u| / g_sat ) * grad u / |grad u|

sampled at the wall centre of mass.  ``Fmax`` bounds the force magnitude
(no runaway acceleration), ``g_sat`` is the gradient scale at which the force
saturates, and the direction points up the activator gradient.  Units are
arbitrary-but-consistent toy units (DU length, MT time, MU mass).  With mass
``m`` the acceleration is |a| <= Fmax/m.  Each wall has per-time-unit velocity
damping ``D`` (pymunk ``body.damping``), so the terminal speed is bounded by

    v_ss ~ Fmax / ( m * (1 - D) )

and positions are clamped to the world bounds with the outward velocity
component zeroed every physical substep.  The wall therefore cannot leave the
domain or accumulate unbounded kinetic energy, and the algebraic coupling loop
is numerically stable for Fmax/m << (1-D)/dt_phys.

Units
-----
    length  L    domain units DU  (1 = full domain, walls ~0.35 DU long)
    time    t    dimensionless model-time units MT (macro step = field_step MT)
    mass    m    mass units MU (wall_mass, default 1)
    force   F    MU*DU/MT^2
    damping D    fraction of velocity retained per MT (0.05 = strong damping)

The loop is closed: field -> force -> mechanical motion -> geometry -> field
-> agent decisions -> wall placement/dissolution -> geometry -> ...
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from .agents import AgentConfig, ChemoMechanicalModel, WallBuildingAgent
from .physics import WallSpace
from .reaction_diffusion import RDField

if TYPE_CHECKING:
    from .physics import Wall


@dataclass
class WorldConfig:
    """All parameters of one chemo-mechanical world."""

    n: int = 32
    seed: int = 0
    pde_dt: float = 5.0e-4           # PDE solver time step
    du: float = 0.005
    dv: float = 0.2
    a: float = 0.1
    b: float = 0.9
    field_step: float = 0.2          # simulator time between macro steps (MT)
    n_steps: int = 160               # number of macro (decision) steps
    feedback: bool = True            # walls block the field (False = open loop)
    build_walls: bool = True         # agents deposit walls at all (False = baseline)

    # --- mechanical coupling (Task 0.3) --------------------------------
    apply_forces: bool = True        # field-gradient forces move the walls
    force_fmax: float = 0.8          # force cap (MU*DU/MT^2), see module doc
    force_gsat: float = 2.0          # gradient scale where force saturates
    wall_mass: float = 1.0           # wall rod mass (MU)
    wall_damping: float = 0.05       # velocity retained per MT
    phys_dt: float = 0.05            # pymunk substep interval (MT)
    phys_substeps: int = 4           # pymunk substeps per macro step

    agent_configs: list[AgentConfig] = field(default_factory=list)

    def default_agents(self) -> list[AgentConfig]:
        if self.agent_configs:
            return self.agent_configs
        return [
            AgentConfig(x=0.3, y=0.5),
            AgentConfig(x=0.7, y=0.5),
        ]


@dataclass
class Trajectory:
    """Full recorded outcome of one composed run."""

    config: WorldConfig
    t_field: list[float] = field(default_factory=list)
    u_snaps: list[np.ndarray] = field(default_factory=list)
    blocked_snaps: list[np.ndarray] = field(default_factory=list)
    walls_per_step: list[int] = field(default_factory=list)
    wall_geometry_snaps: list[list[tuple]] = field(default_factory=list)
    agent_histories: dict[int, list[dict]] = field(default_factory=dict)

    # Task 0.3 mechanical observables
    wall_tracks: dict[int, list[tuple]] = field(default_factory=dict)
    force_mags: list[float] = field(default_factory=list)   # mean |F| per step
    wall_speeds: list[float] = field(default_factory=list)  # mean speed per step
    dissolved_count: list[int] = field(default_factory=list)  # cumulative

    @property
    def final_u(self) -> np.ndarray:
        return self.u_snaps[-1]

    @property
    def final_blocked(self) -> np.ndarray:
        return self.blocked_snaps[-1]

    def wall_counts(self) -> np.ndarray:
        return np.asarray(self.walls_per_step, dtype=int)

    def decisions(self, agent_index: int) -> list[dict]:
        """Decision log of one agent across macro steps."""
        return self.agent_histories.get(agent_index, [])


def chemomechanical_force(
    field: RDField, wall: Wall, force_fmax: float, force_gsat: float
) -> tuple[float, float]:
    """Mechanochemical force on a wall: F = Fmax * tanh(|grad u|/g_sat) * u_hat.

    The gradient is sampled at the wall centre of mass (bilinear interpolation
    of the current morphogen field).  The tanh saturator guarantees |F| <=
    Fmax, which -- together with damping and bounds clamping in
    ``WallSpace.step`` -- keeps the coupled loop bounded and stable.
    """
    gx, gy = field.gradient(wall.center[0], wall.center[1], "u")
    gmag = math.hypot(gx, gy)
    if gmag == 0.0:
        return 0.0, 0.0
    magnitude = force_fmax * math.tanh(gmag / force_gsat)
    return magnitude * gx / gmag, magnitude * gy / gmag


def run_world(config: WorldConfig) -> Trajectory:
    """Execute one composed world and return its trajectory."""
    field = RDField(
        n=config.n,
        du=config.du,
        dv=config.dv,
        a=config.a,
        b=config.b,
        dt=config.pde_dt,
        seed=config.seed,
    )
    wallspace = WallSpace(
        n=config.n,
        mass=config.wall_mass,
        damping=config.wall_damping,
        dt_phys=config.phys_dt,
        phys_substeps=config.phys_substeps,
    )
    model = ChemoMechanicalModel(
        field=field,
        wallspace=wallspace,
        agent_configs=config.default_agents(),
        seed=config.seed,
    )

    traj = Trajectory(config=config)
    dissolved_total = 0

    for _ in range(config.n_steps):
        # 1+2. geometry -> PDE mask (live pymunk transforms, rasterized).
        blocked = wallspace.blocked()
        if config.feedback and config.build_walls:
            field.set_blocked(blocked)
        else:
            field.set_blocked(np.zeros_like(blocked))

        # 3. evolve the morphogen field forced by the current geometry.
        field.advance(config.field_step)

        # 4+5. sample the gradient at each wall COM and apply the bounded force.
        total_force = 0.0
        if config.apply_forces and wallspace.walls:
            for w in wallspace.walls:
                fx, fy = chemomechanical_force(
                    field, w, config.force_fmax, config.force_gsat
                )
                wallspace.apply_force(w, fx, fy, torque=0.0)
                total_force += math.hypot(fx, fy)

        # 6. integrate wall dynamics (force, damping, world-bounds clamp).
        wallspace.step()
        speed_sum = sum(
            math.hypot(w.body.velocity.x, w.body.velocity.y) / wallspace.scale
            for w in wallspace.walls
        )
        n_walls = len(wallspace.walls)

        # 7. agents sense the *new* field and decide (Mesa, deterministic).
        model.step()

        # 8. translate agent actions: dissolve first, then create.
        for agent in model.agents:
            if not isinstance(agent, WallBuildingAgent):
                continue
            for w in agent.pending_dissolve:
                if w in agent.own_walls:
                    agent.own_walls.remove(w)
                wallspace.remove_wall(w)
                dissolved_total += 1
            pending = agent.pending_wall
            if config.build_walls and pending is not None:
                p1, p2, radius, _angle = pending
                wall = wallspace.add_wall(
                    p1, p2, radius, t=field.t, owner=agent.unique_id
                )
                agent.own_walls.append(wall)

        # Record observables at the end of the macro step.
        traj.t_field.append(field.t)
        traj.u_snaps.append(field.u.copy())
        traj.blocked_snaps.append(blocked.copy())
        traj.walls_per_step.append(wallspace.wall_count())
        traj.wall_geometry_snaps.append(wallspace.segments_world())
        traj.force_mags.append(total_force / max(1, n_walls))
        traj.wall_speeds.append(speed_sum / max(1, n_walls))
        traj.dissolved_count.append(dissolved_total)
        for w in wallspace.walls:
            traj.wall_tracks.setdefault(w.id, []).append(
                (field.t, w.center[0], w.center[1], w.angle)
            )
        for i, agent in enumerate(model.agents):
            traj.agent_histories.setdefault(i, []).append(agent.history[-1])

    return traj