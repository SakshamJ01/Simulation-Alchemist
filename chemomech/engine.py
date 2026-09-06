"""Chemo-mechanical specific engine using Alchemist core."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.engine import AlchemistEngine

if TYPE_CHECKING:
    from chemomech.simulation import Trajectory, WorldConfig


@dataclass
class ChemomechanicalEngine(AlchemistEngine):
    """
    Chemo-mechanical engine with the exact macro-step ordering from baseline.

    Ordering (must match chemomech/simulation.py):
    1. geometry        read live wall body transforms from pymunk
    2. rasterize       walls -> PDE blocked-cell mask (fed to the PDE RHS)
    3. evolve          py-pde advances the reaction-diffusion field
    4. sample force    field gradient sampled at each wall centre of mass
    5. apply force     bounded force applied to each wall body at its COM
    6. advance pymunk  wall bodies integrate (force, damping, bounds clamp)
    7. agents decide   Mesa agents sense the *new* field and decide
    8. translate       dissolve then create walls in the pymunk space
    """

    config: WorldConfig
    trajectory: Trajectory = field(default_factory=lambda: None)  # type: ignore[assignment] # set in __post_init__
    _dissolved_total: int = 0

    def __post_init__(self) -> None:
        from chemomech.simulation import Trajectory

        # Create adapters
        pde_adapter = PyPDEAdapter(
            n=self.config.n,
            du=self.config.du,
            dv=self.config.dv,
            a=self.config.a,
            b=self.config.b,
            dt=self.config.pde_dt,
            seed=self.config.seed,
            field_step=self.config.field_step,
        )

        pymunk_adapter = PymunkAdapter(
            n=self.config.n,
            mass=self.config.wall_mass,
            damping=self.config.wall_damping,
            dt_phys=self.config.phys_dt,
            phys_substeps=self.config.phys_substeps,
        )

        agent_cfgs = [
            {"x": ac.x, "y": ac.y, "build_threshold": ac.build_threshold,
             "wall_length": ac.wall_length, "wall_radius": ac.wall_radius,
             "wall_offset": ac.wall_offset, "min_separation": ac.min_separation,
             "cooldown": ac.cooldown, "dissolve_threshold": ac.dissolve_threshold,
             "dissolve_min_age": ac.dissolve_min_age}
            for ac in self.config.default_agents()
        ]
        mesa_adapter = MesaAdapter(
            agent_configs=agent_cfgs,
            seed=self.config.seed,
            macro_timestep=self.config.field_step,
        )

        # Initialize trajectory
        self.trajectory = Trajectory(config=self.config)

        # Initialize base engine with adapters
        super().__init__(
            engines=[pde_adapter, pymunk_adapter, mesa_adapter],
            macro_timestep=self.config.field_step,
            max_steps=self.config.n_steps,
            seed=self.config.seed,
            config=self._config_to_dict(),
        )

        # Store references
        self._pde_adapter = pde_adapter
        self._pymunk_adapter = pymunk_adapter
        self._mesa_adapter = mesa_adapter

    def _config_to_dict(self) -> dict[str, Any]:
        return {
            "n": self.config.n,
            "seed": self.config.seed,
            "pde_dt": self.config.pde_dt,
            "du": self.config.du,
            "dv": self.config.dv,
            "a": self.config.a,
            "b": self.config.b,
            "field_step": self.config.field_step,
            "n_steps": self.config.n_steps,
            "feedback": self.config.feedback,
            "build_walls": self.config.build_walls,
            "apply_forces": self.config.apply_forces,
            "force_fmax": self.config.force_fmax,
            "force_gsat": self.config.force_gsat,
            "wall_mass": self.config.wall_mass,
            "wall_damping": self.config.wall_damping,
            "phys_dt": self.config.phys_dt,
            "phys_substeps": self.config.phys_substeps,
        }

    def initialize(self) -> None:
        """Initialize adapters and cross-references."""
        # Initialize all adapters
        self._pde_adapter.initialize(self.world_state.config)
        self._pymunk_adapter.initialize(self.world_state.config)
        self._mesa_adapter.initialize(self.world_state.config)

        # Set up cross-references for Mesa adapter
        pde_field = self._pde_adapter.get_field()
        pymunk_wallspace = self._pymunk_adapter._wallspace

        self._mesa_adapter.set_field(pde_field)
        self._mesa_adapter.set_wallspace(pymunk_wallspace)
        self._mesa_adapter.create_model()

        self._initialized = True

    def _macro_step(self) -> None:
        """Execute one macro step with exact baseline ordering."""
        _ = self.clock.next_macro_step()

        # Update world state
        self.world_state.time = self.clock.current_time
        self.world_state.step = self.clock.step_count

        # 1+2. geometry -> PDE mask (live pymunk transforms, rasterized)
        blocked = self._pymunk_adapter.get_geometry()["blocked"]
        if self.config.feedback and self.config.build_walls:
            self._pde_adapter.set_blocked(blocked)
        else:
            self._pde_adapter.set_blocked(np.zeros_like(blocked))

        # 3. evolve the morphogen field forced by the current geometry
        self._pde_adapter.step(self.config.field_step)

        # 4+5. sample the gradient at each wall COM and apply the bounded force
        total_force = 0.0
        if self.config.apply_forces and self._pymunk_adapter._wallspace:
            for w in self._pymunk_adapter._wallspace.walls:
                fx, fy = self._chemomechanical_force(w)
                self._pymunk_adapter.apply_force(w.id, fx, fy)
                total_force += math.hypot(fx, fy)

        # 6. integrate wall dynamics (force, damping, world-bounds clamp)
        self._pymunk_adapter.step(self.config.field_step)

        # Get updated geometry after physics step
        pymunk_state = self._pymunk_adapter.get_state()
        n_walls = len(pymunk_state.get("walls", []))
        speed_sum = 0.0
        if self._pymunk_adapter._wallspace:
            speed_sum = sum(
                math.hypot(w.body.velocity.x, w.body.velocity.y) / self._pymunk_adapter._wallspace.scale
                for w in self._pymunk_adapter._wallspace.walls
            )

        # 7. agents sense the *new* field and decide (Mesa, deterministic)
        self._mesa_adapter.step(self.config.field_step)

        # 8. translate agent actions: dissolve first, then create
        self._translate_agent_actions()

        # Record observables at the end of the macro step
        self._record_observables(total_force, n_walls, speed_sum)

    def _chemomechanical_force(self, wall) -> tuple[float, float]:
        """Mechanochemical force on a wall: F = Fmax * tanh(|grad u|/g_sat) * u_hat."""
        field = self._pde_adapter.get_field()
        gx, gy = field.gradient(wall.center[0], wall.center[1], "u")  # type: ignore[union-attr]
        gmag = math.hypot(gx, gy)
        if gmag == 0.0:
            return 0.0, 0.0
        magnitude = self.config.force_fmax * math.tanh(gmag / self.config.force_gsat)
        return magnitude * gx / gmag, magnitude * gy / gmag

    def _translate_agent_actions(self) -> None:
        """Translate agent decisions to pymunk operations."""
        if self._mesa_adapter._model is None:
            return

        for agent in self._mesa_adapter._model.agents:
            # Dissolve first
            for w in agent.pending_dissolve:
                if w in agent.own_walls:
                    agent.own_walls.remove(w)
                self._pymunk_adapter.remove_wall(w.id)
                self._dissolved_total += 1

            # Then create
            if self.config.build_walls and agent.pending_wall is not None:
                p1, p2, radius, _angle = agent.pending_wall
                wall = self._pymunk_adapter._wallspace.add_wall(  # type: ignore[union-attr]
                    p1, p2, radius, t=self._pde_adapter.get_field().t, owner=agent.unique_id  # type: ignore[union-attr]
                )
                agent.own_walls.append(wall)

    def _record_observables(self, total_force: float, n_walls: int, speed_sum: float) -> None:
        """Record trajectory observables."""
        field = self._pde_adapter.get_field()
        blocked = self._pymunk_adapter.get_geometry()["blocked"]

        self.trajectory.t_field.append(field.t)  # type: ignore[union-attr]
        self.trajectory.u_snaps.append(field.u.copy())  # type: ignore[union-attr]
        self.trajectory.blocked_snaps.append(blocked.copy())
        self.trajectory.walls_per_step.append(n_walls)
        self.trajectory.wall_geometry_snaps.append(
            self._pymunk_adapter.get_geometry()["segments"]
        )
        self.trajectory.force_mags.append(total_force / max(1, n_walls))
        self.trajectory.wall_speeds.append(speed_sum / max(1, n_walls))
        self.trajectory.dissolved_count.append(self._dissolved_total)

        # Wall tracks
        if self._pymunk_adapter._wallspace:
            for w in self._pymunk_adapter._wallspace.walls:
                self.trajectory.wall_tracks.setdefault(w.id, []).append(
                    (field.t, w.center[0], w.center[1], w.angle)  # type: ignore[union-attr]
                )

        # Agent histories
        if self._mesa_adapter._model:
            for i, agent in enumerate(self._mesa_adapter._model.agents):
                if agent.history:
                    self.trajectory.agent_histories.setdefault(i, []).append(agent.history[-1])

    def run(self) -> Trajectory:  # type: ignore[override]
        """Run the full simulation and return trajectory."""
        if not self._initialized:
            self.initialize()

        # Validate composition
        composition = self.validate_composition()
        if not composition.valid:
            raise RuntimeError(f"Invalid composition: {composition.missing}")

        while not self.clock.is_finished:
            self._macro_step()

        return self.trajectory