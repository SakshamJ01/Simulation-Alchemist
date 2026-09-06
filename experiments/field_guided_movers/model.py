"""Field-Guided Movers model: py-pde field + Pymunk probe bodies.

This is Experiment B in the Task 1.1 capability-composition proof.

    AlchemistCore
    Folder: src/sim_alchemist/core/  (UNCHANGED)
    Engines:
        py-pde   -> PyPDEAdapter       (field, gradient, source injection)
        pymunk   -> MoversAdapter      (point bodies, force integration)

The experiment itself owns only the *coupling rules*: how the field
gradient becomes a physical force and how a mover deposits/consumes
chemical.  Those rules live here, outside the core.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pymunk

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event, EventType

DEFAULT_START_POSITIONS: tuple[tuple[float, float], ...] = (
    (0.25, 0.25),
    (0.25, 0.75),
    (0.75, 0.25),
    (0.75, 0.75),
    (0.30, 0.50),
    (0.70, 0.50),
)


@dataclass
class MoversConfig:
    """All parameters of one Field-Guided Movers world.

    Defaults mirror the validated chemo-mechanical baseline where sensible
    (n=32, Schnakenberg parameters, pde_dt) so only the composition differs.
    """

    n: int = 32
    seed: int = 0
    pde_dt: float = 5.0e-4
    du: float = 0.005
    dv: float = 0.2
    a: float = 0.1
    b: float = 0.9
    macro_timestep: float = 0.2
    n_steps: int = 160

    # --- Pymunk mover bodies -------------------------------------------
    n_movers: int = 6
    start_positions: tuple[tuple[float, float], ...] = ()
    mover_mass: float = 1.0
    mover_damping: float = 0.2
    mover_radius: float = 0.05
    phys_dt: float = 0.05
    phys_substeps: int = 4

    # --- Coupling rules (experiment-owned) -----------------------------
    apply_forces: bool = True        # False -> movers do not react to field
    apply_sources: bool = True       # False -> open-loop control (no field feedback)
    force_fmax: float = 0.8          # force cap (MU*DU/MT^2)
    force_gsat: float = 2.0          # gradient scale where force saturates
    source_u: float = 0.03           # activator deposited per macro step
    source_v: float = -0.04          # inhibitor consumed per macro step
    source_radius: float = 0.04

    def positions(self) -> list[tuple[float, float]]:
        if self.start_positions:
            return list(self.start_positions[: self.n_movers])
        return list(DEFAULT_START_POSITIONS[: self.n_movers])

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "seed": self.seed,
            "pde_dt": self.pde_dt,
            "du": self.du,
            "dv": self.dv,
            "a": self.a,
            "b": self.b,
            "macro_timestep": self.macro_timestep,
            "n_steps": self.n_steps,
            "n_movers": self.n_movers,
            "mover_mass": self.mover_mass,
            "mover_damping": self.mover_damping,
            "mover_radius": self.mover_radius,
            "phys_dt": self.phys_dt,
            "phys_substeps": self.phys_substeps,
            "apply_forces": self.apply_forces,
            "apply_sources": self.apply_sources,
            "force_fmax": self.force_fmax,
            "force_gsat": self.force_gsat,
            "source_u": self.source_u,
            "source_v": self.source_v,
            "source_radius": self.source_radius,
        }


@dataclass
class Mover:
    """A single Pymunk probe/disc body in PDE coordinates."""

    id: int
    mass: float
    radius: float
    scale: float = field(default=100.0, init=False)
    start: tuple[float, float] = field(default=(0.0, 0.0), init=False)
    body: Any = field(default=None, init=False, repr=False)

    @property
    def position(self) -> tuple[float, float]:
        return (float(self.body.position.x) / self.scale,
                float(self.body.position.y) / self.scale)

    @property
    def velocity(self) -> tuple[float, float]:
        return (float(self.body.velocity.x) / self.scale,
                float(self.body.velocity.y) / self.scale)

    def displacement(self) -> float:
        sx, sy = self.start
        px, py = self.position
        return float(math.hypot(px - sx, py - sy))


@dataclass
class MoverSpace:
    """Pymunk space owning several dynamic probe bodies."""

    n: int = 32
    scale: float = 100.0
    mass: float = 1.0
    damping: float = 0.2
    dt_phys: float = 0.05
    phys_substeps: int = 4
    radius: float = 0.05
    positions: list[tuple[float, float]] = field(default_factory=list)
    start_positions: list[tuple[float, float]] = field(default_factory=list)

    space: pymunk.Space = field(default=None, init=False)  # type: ignore[reportAssignmentType]
    movers: list[Mover] = field(default_factory=list, init=False)
    _next_id: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)
        self.space.damping = 1.0
        for x, y in self.positions:
            self.add_mover(x, y)
        self.start_positions = list(self.positions)

    def add_mover(self, x: float, y: float) -> Mover:
        """Create a dynamic disc body at PDE coordinates (x, y)."""
        body = pymunk.Body(self.mass, pymunk.moment_for_circle(self.mass, 0, self.radius * self.scale))
        body.position = pymunk.Vec2d(float(x) * self.scale, float(y) * self.scale)
        body.damping = self.damping
        shape = pymunk.Circle(body, self.radius * self.scale)
        shape.friction = 0.0
        self.space.add(body, shape)

        mover = Mover(id=self._next_id, mass=self.mass, radius=self.radius)
        self._next_id += 1
        mover.body = body
        mover.scale = self.scale
        mover.start = (float(x), float(y))
        self.movers.append(mover)
        return mover

    def apply_force(self, mover: Mover, fx: float, fy: float) -> None:
        """Apply an external force (PDE units) at the mover centre."""
        if mover.body.body_type == pymunk.Body.DYNAMIC:
            f = pymunk.Vec2d(float(fx) * self.scale, float(fy) * self.scale)
            mover.body.apply_force_at_world_point(f, mover.body.position)

    def step(self, dt: float | None = None, substeps: int | None = None,
             world_bounds: tuple[float, float] = (0.0, 1.0)) -> None:
        """Advance pymunk dynamics with per-substep bounds clamping."""
        dt = self.dt_phys if dt is None else dt
        sub = self.phys_substeps if substeps is None else substeps
        s = self.scale
        lo, hi = world_bounds
        for _ in range(max(1, sub)):
            self.space.step(dt)
            for m in self.movers:
                b = m.body
                r = m.radius
                x = float(np.clip(b.position.x / s, lo + r, hi - r))
                y = float(np.clip(b.position.y / s, lo + r, hi - r))
                b.position = pymunk.Vec2d(x * s, y * s)
                if x <= lo + r and b.velocity.x < 0:
                    b.velocity = pymunk.Vec2d(0.0, b.velocity.y)
                if x >= hi - r and b.velocity.x > 0:
                    b.velocity = pymunk.Vec2d(0.0, b.velocity.y)
                if y <= lo + r and b.velocity.y < 0:
                    b.velocity = pymunk.Vec2d(b.velocity.x, 0.0)
                if y >= hi - r and b.velocity.y > 0:
                    b.velocity = pymunk.Vec2d(b.velocity.x, 0.0)


class MoversAdapter(BaseAdapter):
    """Pymunk adapter for the Field-Guided Movers probe bodies."""

    def __init__(self, config: MoversConfig) -> None:
        provides = CapabilitySet()
        provides.add(Capability.from_dict("rigid_body", "1.0"))
        provides.add(Capability.from_dict("force_integration", "1.0"))
        provides.add(Capability.from_dict("geometry_provider", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("scalar_field", "1.0"))
        requires.add(Capability.from_dict("field_gradient", "1.0"))
        requires.add(Capability.from_dict("field_sources", "1.0"))

        super().__init__(
            engine_id="pymunk",
            provides=provides,
            requires=requires,
            native_timestep=config.phys_dt,
        )

        self._config = config
        self._space: MoverSpace | None = None
        self._pending_forces: dict[int, tuple[float, float]] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        super().initialize(config)
        self._space = MoverSpace(
            n=self._config.n,
            mass=self._config.mover_mass,
            damping=self._config.mover_damping,
            dt_phys=self._config.phys_dt,
            phys_substeps=self._config.phys_substeps,
            radius=self._config.mover_radius,
            positions=self._config.positions(),
        )

    def step(self, dt: float) -> None:
        """Apply pending forces, integrate physics, publish body states."""
        if self._space is None:
            return
        for mover_id, (fx, fy) in self._pending_forces.items():
            mover = next((m for m in self._space.movers if m.id == mover_id), None)
            if mover is not None:
                self._space.apply_force(mover, fx, fy)
        self._pending_forces.clear()
        self._space.step()
        self._publish_body_state(dt)

    def apply_force(self, mover_id: int, fx: float, fy: float) -> None:
        self._pending_forces[mover_id] = (fx, fy)

    def get_state(self) -> dict[str, Any]:
        if self._space is None:
            return {"positions": {}, "velocities": {}, "count": 0}
        return {
            "positions": {m.id: m.position for m in self._space.movers},
            "velocities": {m.id: m.velocity for m in self._space.movers},
            "count": len(self._space.movers),
        }

    def get_positions(self) -> dict[int, tuple[float, float]]:
        state = self.get_state()
        return state["positions"]

    def _publish_body_state(self, dt: float) -> None:
        if self._space is None:
            return
        event = Event(
            EventType.GEOMETRY_UPDATE,
            self.engine_id,
            0.0,
            {"bodies": {m.id: m.position for m in self._space.movers},
             "count": len(self._space.movers)},
        )
        self.publish(event)

    def apply_event(self, event: Event) -> bool:
        return event.type == EventType.FIELD_STATE

    def shutdown(self) -> None:
        self._space = None
        self._pending_forces.clear()


def gradient_force(
    pde: PyPDEAdapter,
    position: tuple[float, float],
    force_fmax: float,
    force_gsat: float,
    field_name: str = "u",
) -> tuple[float, float]:
    """Experiment rule: field gradient -> bounded physical force.

    F = Fmax * tanh(|grad u| / g_sat) * grad u / |grad u|.
    """
    x, y = position
    gx, gy = pde.gradient(x, y, field_name)
    gmag = float(np.hypot(gx, gy))
    if gmag == 0.0:
        return 0.0, 0.0
    magnitude = force_fmax * math.tanh(gmag / force_gsat)
    return magnitude * float(gx) / gmag, magnitude * float(gy) / gmag


def mover_source(
    mover: Mover,
    config: MoversConfig,
    field_name: str = "u",
) -> dict[str, Any]:
    """Experiment rule: mover position -> chemical source/sink.

    The mover deposits activator ``u`` and consumes inhibitor ``v`` at its
    current position.  The effect is computed here (experiment-owned) and
    handed to the PDE adapter's generic source injection.
    """
    return {
        "x": mover.position[0],
        "y": mover.position[1],
        "u": config.source_u,
        "v": config.source_v,
        "radius": config.source_radius,
    }


def run_field_guided_movers(config: MoversConfig) -> MoversTrajectory:
    """Run one composed Field-Guided Movers world."""
    engine = FieldGuidedMoversEngine(config=config)
    return engine.run()


@dataclass
class MoversTrajectory:
    """Full recorded outcome of one Field-Guided Movers run."""

    config: MoversConfig
    t_field: list[float] = field(default_factory=list)
    u_snaps: list[np.ndarray] = field(default_factory=list)
    positions: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    speeds: list[float] = field(default_factory=list)
    force_mags: list[float] = field(default_factory=list)
    gradient_mags: list[float] = field(default_factory=list)
    start_u: np.ndarray = field(default_factory=lambda: np.empty(0))

    @property
    def final_u(self) -> np.ndarray:
        return self.u_snaps[-1]

    @property
    def n_movers(self) -> int:
        return len(self.positions)

    def net_displacements(self) -> dict[int, float]:
        disp: dict[int, float] = {}
        for mover_id, pts in self.positions.items():
            sx, sy = pts[0]
            ex, ey = pts[-1]
            disp[mover_id] = float(np.hypot(ex - sx, ey - sy))
        return disp

    def total_paths(self) -> dict[int, float]:
        paths: dict[int, float] = {}
        for mover_id, pts in self.positions.items():
            total = 0.0
            for (x0, y0), (x1, y1) in itertools.pairwise(pts):
                total += float(np.hypot(x1 - x0, y1 - y0))
            paths[mover_id] = total
        return paths


class FieldGuidedMoversEngine(AlchemistEngine):
    """Experiment B engine: py-pde field driven by Pymunk movers.

    Macro-step ordering (deterministic):
        1. read body geometry (mover positions) from Pymunk
        2. evolve the reaction-diffusion field (sources from last step feed RHS)
        3. sample field gradient at each mover COM -> bounded force
        4. integrate Pymunk dynamics (force, damping, bounds clamp)
        5. inject source/sink at the *new* body positions (reverse coupling)
        6. record observables
    """

    def __init__(self, config: MoversConfig) -> None:
        pde_adapter = PyPDEAdapter(
            n=config.n,
            du=config.du,
            dv=config.dv,
            a=config.a,
            b=config.b,
            dt=config.pde_dt,
            seed=config.seed,
            field_step=config.macro_timestep,
        )
        movers_adapter = MoversAdapter(config=config)

        super().__init__(
            engines=[pde_adapter, movers_adapter],
            macro_timestep=config.macro_timestep,
            max_steps=config.n_steps,
            seed=config.seed,
            config=config.as_dict(),
        )

        self._pde_adapter = pde_adapter
        self._movers_adapter = movers_adapter
        self._config = config
        self.trajectory = MoversTrajectory(config=config)

    def initialize(self) -> None:
        super().initialize()
        # Route adapter-published events onto the shared bus (Alchemist owns
        # event routing).  The core wires TIME_STEP subscribers already; this
        # makes adapter->bus publication available to the experiment.
        self._pde_adapter.set_event_bus(self.event_bus)
        self._movers_adapter.set_event_bus(self.event_bus)
        field = self._pde_adapter.get_field()
        if field is not None and self.trajectory.start_u.size == 0:
            self.trajectory.start_u = field.u.copy()

    def _macro_step(self) -> None:
        _dt = self.clock.next_macro_step()
        self.world_state.time = self.clock.current_time
        self.world_state.step = self.clock.step_count

        # Alchemist owns event routing on the shared bus.
        time_event = Event.time_step("alchemist", self.clock.current_time, _dt)
        self.event_bus.publish(time_event)

        # 1. geometry: mover positions from Pymunk (read via adapter state)

        # 2. evolve the field one macro step
        self._pde_adapter.step(self._config.macro_timestep)

        # 3+4. sample gradients -> bounded forces -> integrate dynamics
        total_force = 0.0
        total_grad = 0.0
        if self._config.apply_forces:
            space = self._movers_adapter._space  # type: ignore[attr-defined]
            if space is not None:
                for m in space.movers:
                    fx, fy = gradient_force(
                        self._pde_adapter, m.position,
                        self._config.force_fmax, self._config.force_gsat,
                    )
                    self._movers_adapter.apply_force(m.id, fx, fy)
                    total_force += math.hypot(fx, fy)
                    gx, gy = self._pde_adapter.gradient(m.position[0], m.position[1], "u")
                    total_grad += math.hypot(gx, gy)

        self._movers_adapter.step(self._config.macro_timestep)

        # 5. reverse coupling: sources at the NEW body positions
        sources_present = 0
        if self._config.apply_sources:
            space = self._movers_adapter._space  # type: ignore[attr-defined]
            if space is not None:
                sources = [mover_source(m, self._config) for m in space.movers]
                self._pde_adapter.apply_sources(sources)
                sources_present = len(sources)

        # 6. record observables
        self._record_observables(total_force, total_grad, sources_present)

    def _record_observables(
        self,
        total_force: float,
        total_grad: float,
        n_sources: int,
    ) -> None:
        field = self._pde_adapter.get_field()
        if field is None:
            return
        mover_positions = self._movers_adapter.get_positions()
        n = max(1, len(mover_positions))
        self.trajectory.t_field.append(field.t)
        self.trajectory.u_snaps.append(field.u.copy())

        for mover_id, pos in mover_positions.items():
            self.trajectory.positions.setdefault(mover_id, []).append(pos)

        speed_sum = 0.0
        state = self._movers_adapter.get_state()
        for vel in state["velocities"].values():
            speed_sum += float(np.hypot(vel[0], vel[1]))
        self.trajectory.speeds.append(speed_sum / n)
        self.trajectory.force_mags.append(total_force / n)
        self.trajectory.gradient_mags.append(total_grad / n)

    def run(self) -> MoversTrajectory:  # type: ignore[override]
        """Run the full composed world and return its trajectory."""
        if not self._initialized:
            self.initialize()

        composition = self.validate_composition()
        if not composition.valid:
            raise RuntimeError(f"Invalid composition: {composition.missing}")

        while not self.clock.is_finished:
            self._macro_step()

        return self.trajectory