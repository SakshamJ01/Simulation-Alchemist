"""Mesa agents and model for the chemo-mechanical loop.

Mesa owns agent lifecycle, state, stepping and sensing:

  * ``WallBuildingAgent`` (mesa.Agent): senses the reaction-diffusion field at
    its position, decides where to build a mechanical wall, and records its own
    full history (sensed values + decisions) for later validation.
  * ``ChemoMechanicalModel`` (mesa.Model): hosts and steps the agents.

The model does *not* know about py-pde or pymunk details; it only exposes
agents that hold a ``pending_wall`` after each step.  The composition engine
(simulation.py) consumes those intentions, translates them into pymunk wall
segments, and feeds the resulting physics geometry back into the field mask.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from mesa import Agent, Model

if TYPE_CHECKING:
    from .physics import Wall, WallSpace
    from .reaction_diffusion import RDField


@dataclass
class AgentConfig:
    """Parameters controlling how a sensing agent decides to build/dissolve."""

    x: float = 0.3
    y: float = 0.5
    build_threshold: float = 0.15      # |grad u| above which a wall is built
    wall_length: float = 0.35          # wall segment length (PDE units)
    wall_radius: float = 0.02          # pymunk segment radius (PDE units)
    wall_offset: float = 0.2           # settle wall this far up-gradient
    min_separation: float = 0.15       # min distance from *other* agents' walls
    cooldown: int = 4                  # agent steps between wall builds
    dissolve_threshold: float = 0.05   # |grad u| below which an old wall dissolves
    dissolve_min_age: float = 2.5      # wall minimum age (field time) before dissolve


class WallBuildingAgent(Agent):
    """A cell that senses the morphogen field and deposits walls."""

    def __init__(self, model: Model, field: RDField, wallspace: WallSpace,
                 config: AgentConfig) -> None:
        super().__init__(model)
        self.field = field
        self.wallspace = wallspace
        self.cfg = config
        self.x = config.x
        self.y = config.y
        self.cooldown_remaining = 0
        self.own_walls: list = []      # wall ids this agent deposited

        self.history: list[dict] = []
        self.pending_wall: (
            tuple[tuple[float, float], tuple[float, float], float, float] | None
        ) = None
        self.pending_dissolve: list[Wall] = []

    def start(self) -> None:
        super().start()  # type: ignore[reportAttributeAccessIssue]  # mesa.Model.start

    def step(self) -> None:
        """Sense the field and decide on a wall placement (Mesa-owned step)."""
        u = self.field.sample(self.x, self.y, "u")
        g = self.field.gradient(self.x, self.y, "u")
        gmag = float(np.hypot(g[0], g[1]))
        record = {
            "u": u,
            "gx": float(g[0]),
            "gy": float(g[1]),
            "gmag": gmag,
            "built": False,
            "dissolved": False,
            "anchor": None,
            "angle": None,
        }
        self.pending_wall = None
        self.pending_dissolve = []
        self.cooldown_remaining = max(0, self.cooldown_remaining - 1)

        build = gmag >= self.cfg.build_threshold and self.cooldown_remaining == 0
        if build:
            # Wall centre is offset up-gradient so it does not cover the
            # sensing point; orientation is perpendicular to the gradient.
            ux, uy = g[0] / gmag, g[1] / gmag
            cx = self.x + self.cfg.wall_offset * ux
            cy = self.y + self.cfg.wall_offset * uy
            if self.wallspace.nearest_wall_distance(
                (cx, cy), exclude_ids={w.id for w in self.own_walls}
            ) >= self.cfg.min_separation:
                angle = math.atan2(-uy, ux)
                c, s = math.cos(angle), math.sin(angle)
                half = 0.5 * self.cfg.wall_length
                p1 = (cx - half * c, cy - half * s)
                p2 = (cx + half * c, cy + half * s)
                self.pending_wall = (p1, p2, self.cfg.wall_radius, angle)
                record["built"] = True
                record["anchor"] = (self.x, self.y)
                record["angle"] = angle
                self.cooldown_remaining = self.cfg.cooldown

        self.history.append(record)

        # Dissolve: an owned wall is removed once the morphogen gradient at
        # its centre has faded below a threshold (the wall is "dissolved back
        # into the medium").  Executed AFTER the build check so both actions
        # are possible in one step; the simulation engine translates dissolve
        # before create (task-specified action order).
        for w in list(self.own_walls):
            if self.field.t - w.t_built < self.cfg.dissolve_min_age:
                continue
            gw = self.field.gradient(w.center[0], w.center[1], "u")
            if float(np.hypot(gw[0], gw[1])) < self.cfg.dissolve_threshold:
                self.pending_dissolve.append(w)
                self.history[-1]["dissolved"] = True

    def advance(self) -> None:
        super().advance()


class ChemoMechanicalModel(Model):
    """Mesa model hosting the wall-building agents."""

    def __init__(self, field: RDField, wallspace: WallSpace,
                 agent_configs: list[AgentConfig], seed: int = 0) -> None:
        super().__init__(rng=seed)
        self.field = field
        self.wallspace = wallspace
        for cfg in agent_configs:
            WallBuildingAgent(model=self, field=field, wallspace=wallspace, config=cfg)

    def step(self) -> None:
        """Advance all agents (deterministic insertion order).

        No RNG is used inside ``agent.step`` and ``AgentSet.do`` iterates
        agents in registration (insertion) order, so the result is fully
        deterministic for a given field state.
        """
        self.agents.do("step")