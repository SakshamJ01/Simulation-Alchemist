"""Pymunk wall physics: dynamic wall bodies integrated by pymunk.

Task 0.3 upgrade: walls are now *dynamic rigid bodies* that pymunk actually
steps.  The alchemist layer computes an external force from the morphogen
field; pymunk integrates the resulting motion through ``space.step``.  We do
NOT move walls by writing x/y/angle directly.

Coordinate scaling
------------------
The PDE lives on [0,1]^2.  Pymunk coordinates are the PDE coordinates scaled
by ``SF = 100`` (1 > 0.1 > 1e-2 are awkward for pymunk's tolerances).  All
public API in this module accepts/returns PDE coordinates; the scaling is
applied only at the pymunk boundary.

Wall body model
---------------
Each wall is a thin rod (a pymunk Seg shape) attached to a dynamic
``pymunk.Body`` of mass ``m`` and moment ``I = (1/12) m L^2`` about its centre
of mass.  The segment endpoints live in body-local coordinates
``(-L/2, 0)``..``(+L/2, 0)`` and rotate with the body angle.  Wall bodies are
given the same pymunk collision ``filter group`` so they pass through each
other (no wall-wall collisions) -- the only constraints are the world bounds.

Units (arbitrary but self-consistent toy model)
-----------------------------------------------
    length L        domain units DU  (1 = whole domain)
    time   t        model time units MT (dimensionless)
    mass   m        mass units MU  (m = wall_mass, default 1)
    force  F        MU*DU/MT^2
    damping D       fraction of velocity lost per MT (pymunk body.damping)

Stability limits
----------------
The physical timestep ``dt_phys`` is split into ``phys_substeps`` substeps per
macro step.  The field force is bounded by a tanh saturator (|F| <= F_max), so
acceleration is bounded; damping bounds the terminal velocity to
``v_ss ~ F_max / (m (1 - D))``; and wall positions are clamped to the world
bounds each substep with the outward velocity component zeroed.  Wall
trajectories therefore cannot leave the domain or accumulate unbounded energy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pymunk


@dataclass
class Wall:
    """A dynamic pymunk wall body (thin rod segment)."""

    id: int
    length: float
    radius: float
    mass: float
    t_built: float
    owner: int | None
    body: Any = field(default=None, init=False, repr=False)
    shape: Any = field(default=None, init=False, repr=False)
    scale: float = field(default=100.0, init=False)

    @property
    def center(self) -> tuple[float, float]:
        """Wall centre of mass in PDE coordinates."""
        return (float(self.body.position.x) / self.scale,
                float(self.body.position.y) / self.scale)

    @property
    def angle(self) -> float:
        return float(self.body.angle)

    def _end_local(self, sign: float) -> tuple[float, float]:
        v = self.body.local_to_world(pymunk.Vec2d(sign * 0.5 * self.length, 0.0))
        return (float(v.x) / self.scale, float(v.y) / self.scale)

    def endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Global endpoints of the wall segment in PDE coordinates."""
        return self._end_local(-1.0), self._end_local(+1.0)

    def distance_to(self, point: tuple[float, float]) -> float:
        """Shortest distance from a point to the current wall segment."""
        p1, p2 = self.endpoints()
        a = np.asarray(p1, dtype=float)
        b = np.asarray(p2, dtype=float)
        p = np.asarray(point, dtype=float)
        ab = b - a
        ab2 = float(np.dot(ab, ab))
        t = 0.0 if ab2 == 0 else float(np.clip(np.dot(p - a, ab) / ab2, 0.0, 1.0))
        return float(np.linalg.norm(p - (a + t * ab)))


@dataclass
class WallSpace:
    """Pymunk space owning dynamic wall rigid bodies."""

    n: int = 32
    scale: float = 100.0             # pymunk units per domain unit
    mass: float = 1.0                # default wall mass (MU)
    damping: float = 0.05            # wall velocity damping per MT (1.0 = none)
    dt_phys: float = 0.05            # physical substep interval (MT)
    phys_substeps: int = 4           # substeps per macro step

    space: pymunk.Space = field(default=None, init=False)  # type: ignore[reportAssignmentType]
    walls: list[Wall] = field(default_factory=list, init=False)
    _next_id: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)
        self.space.damping = 1.0

    # ------------------------------------------------------------------
    # wall lifecycle
    # ------------------------------------------------------------------
    def add_wall(
        self, p1: tuple[float, float], p2: tuple[float, float],
        radius: float, t: float = 0.0, owner: int | None = None,
        mass: float | None = None,
    ) -> Wall:
        """Create a dynamic wall body from segment endpoints (PDE coords)."""
        a1 = np.asarray(p1, dtype=float)
        a2 = np.asarray(p2, dtype=float)
        length = float(np.linalg.norm(a2 - a1))
        center = 0.5 * (a1 + a2)
        angle = math.atan2(a2[1] - a1[1], a2[0] - a1[0])
        mass = self.mass if mass is None else mass

        length_p = length * self.scale
        moment = (1.0 / 12.0) * mass * length_p * length_p
        body = pymunk.Body(mass, moment)
        body.position = pymunk.Vec2d(float(center[0]) * self.scale,
                                     float(center[1]) * self.scale)
        body.angle = angle
        body.damping = self.damping
        shape = pymunk.Segment(
            body, pymunk.Vec2d(-0.5 * length_p, 0.0),
            pymunk.Vec2d(+0.5 * length_p, 0.0), radius * self.scale,
        )
        shape.filter = pymunk.ShapeFilter(group=1)  # walls pass through walls
        shape.friction = 0.0
        self.space.add(body, shape)

        wall = Wall(id=self._next_id, length=length, radius=radius, mass=mass,
                    t_built=t, owner=owner)
        self._next_id += 1
        wall.body = body
        wall.shape = shape
        wall.scale = self.scale
        self.walls.append(wall)
        return wall

    def remove_wall(self, wall: Wall) -> None:
        """Dissolve a wall: remove its body and shape from the pymunk space."""
        if wall not in self.walls:
            return
        self.space.remove(wall.shape, wall.body)
        self.walls.remove(wall)

    # ------------------------------------------------------------------
    # forces and integration
    # ------------------------------------------------------------------
    def apply_force(self, wall: Wall, fx: float, fy: float, torque: float = 0.0) -> None:
        """Apply an external force (PDE units) at the wall centre of mass."""
        if wall.body.body_type == pymunk.Body.DYNAMIC:
            f = pymunk.Vec2d(float(fx) * self.scale, float(fy) * self.scale)
            wall.body.apply_force_at_world_point(f, wall.body.position)
            if torque:
                wall.body.torque += torque

    def step(self, dt: float | None = None, substeps: int | None = None,
             world_bounds: tuple[float, float] = (0.0, 1.0)) -> None:
        """Advance pymunk dynamics with world-bound clamping each substep."""
        dt = self.dt_phys if dt is None else dt
        sub = self.phys_substeps if substeps is None else substeps
        s = self.scale
        lo, hi = world_bounds
        for _ in range(max(1, sub)):
            self.space.step(dt)
            for w in self.walls:
                b = w.body
                # clamp to world bounds (PDE coords -> scaled)
                r = w.radius
                x = float(np.clip(b.position.x / s, lo + r, hi - r))
                y = float(np.clip(b.position.y / s, lo + r, hi - r))
                b.position = pymunk.Vec2d(x * s, y * s)
                # cancel the outward velocity component
                if x <= lo + r and b.velocity.x < 0:
                    b.velocity = pymunk.Vec2d(0.0, b.velocity.y)
                if x >= hi - r and b.velocity.x > 0:
                    b.velocity = pymunk.Vec2d(0.0, b.velocity.y)
                if y <= lo + r and b.velocity.y < 0:
                    b.velocity = pymunk.Vec2d(b.velocity.x, 0.0)
                if y >= hi - r and b.velocity.y > 0:
                    b.velocity = pymunk.Vec2d(b.velocity.x, 0.0)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def nearest_wall_distance(
        self, point: tuple[float, float], exclude_ids: set[int] | None = None
    ) -> float:
        """Distance from a point to the nearest wall (inf if no walls)."""
        if not self.walls:
            return float("inf")
        exclude = exclude_ids or set()
        distances = [w.distance_to(point) for w in self.walls if w.id not in exclude]
        if not distances:
            return float("inf")
        return min(distances)

    def wall_count(self) -> int:
        return len(self.walls)

    def segments_world(self) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
        """Current global wall segments (PDE coords) from live pymunk bodies."""
        return [(w.endpoints()[0], w.endpoints()[1], w.radius) for w in self.walls]

    def blocked(self) -> np.ndarray:
        """Rasterize current wall geometry onto the n x n grid (bool mask)."""
        blocked = np.zeros((self.n, self.n), dtype=bool)
        segments = self.segments_world()
        if not segments:
            return blocked
        cell = np.meshgrid(
            (np.arange(self.n) + 0.5) / self.n,
            (np.arange(self.n) + 0.5) / self.n,
            indexing="ij",
        )
        points = np.stack(cell, axis=-1).reshape(-1, 2)  # (n*n, 2)
        dist = np.full(points.shape[0], np.inf)
        for (p1, p2, _radius) in segments:
            d = self._segment_distance(points, p1, p2)
            dist = np.minimum(dist, d)
        threshold = segments[0][2] + 0.5 / self.n
        return (dist <= threshold).reshape(self.n, self.n)

    @staticmethod
    def _segment_distance(points: np.ndarray, p1, p2) -> np.ndarray:
        """Vectorized point-to-segment distance for a batch of points."""
        a = np.asarray(p1, dtype=float)
        b = np.asarray(p2, dtype=float)
        ab = b - a
        ab2 = float(np.dot(ab, ab))
        t = np.nan_to_num(np.dot(points - a, ab) / ab2) if ab2 else np.zeros(len(points))
        t = np.clip(t, 0.0, 1.0)
        proj = a + t[:, None] * ab
        return np.linalg.norm(points - proj, axis=1)