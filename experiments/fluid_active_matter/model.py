"""Experiment E (Fluid-Structure Active Matter) physics models and adapters.

Composes:
1. Reaction-diffusion continuous chemical field (py-pde),
2. 2D Incompressible Navier-Stokes / streamfunction-vorticity fluid solver (fluid),
3. Active swimmer micro-particles with hydrodynamic drag and chemotactic steering (pymunk/swimmers).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pymunk

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet


@dataclass
class FluidActiveMatterConfig:
    """Configuration parameters for Experiment E."""

    n: int = 32
    seed: int = 42
    pde_dt: float = 5.0e-4
    du: float = 0.005
    dv: float = 0.2
    a: float = 0.1
    b: float = 0.9
    macro_timestep: float = 0.2
    n_steps: int = 160

    # Fluid mechanics parameters (Navier-Stokes)
    viscosity: float = 0.05            # Kinematic viscosity (nu)
    buoyancy_coef: float = 0.8         # Solutal Rayleigh-Benard coupling (beta)
    fluid_damping: float = 0.02        # Linear background drag / damping (alpha)

    # Active Swimmer particles (Pymunk variant: swimmers)
    n_swimmers: int = 8
    swimmer_speed: float = 0.08        # Self-propulsion speed (v0)
    swimmer_radius: float = 0.04
    advection_drag: float = 1.2        # Hydrodynamic drag coupling (gamma)
    chemotaxis_strength: float = 0.6   # Chemical gradient steering torque (kappa)
    rotational_diffusion: float = 0.1  # Angular fluctuation noise (Dr)
    source_u: float = 0.02             # Chemical activator excretion rate
    source_v: float = -0.03            # Chemical inhibitor consumption rate
    source_radius: float = 0.04

    def initial_swimmer_positions(self) -> list[tuple[float, float]]:
        rng = np.random.default_rng(self.seed)
        pts: list[tuple[float, float]] = []
        for _ in range(self.n_swimmers):
            x = float(rng.uniform(0.15, 0.85))
            y = float(rng.uniform(0.15, 0.85))
            pts.append((x, y))
        return pts


class FluidEngineAdapter(BaseAdapter):
    """2D Incompressible Navier-Stokes / streamfunction-vorticity fluid engine adapter."""

    CAPABILITIES = (
        Capability("velocity_field"),
        Capability("vorticity_field"),
        Capability("fluid_state"),
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.n: int = int(cfg.get("n", 32))
        self.viscosity: float = float(cfg.get("viscosity", 0.05))
        self.buoyancy_coef: float = float(cfg.get("buoyancy_coef", 0.8))
        self.damping: float = float(cfg.get("fluid_damping", 0.02))
        self.dx: float = 1.0 / float(self.n)

        provides = CapabilitySet()
        provides.add(Capability.from_dict("velocity_field", "1.0"))
        provides.add(Capability.from_dict("vorticity_field", "1.0"))
        provides.add(Capability.from_dict("fluid_state", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("scalar_field", "1.0"))

        super().__init__(
            engine_id="fluid",
            provides=provides,
            requires=requires,
            native_timestep=0.05,
        )
        self._grid = self.n
        self._state_keys = ("u_x", "u_y", "omega", "psi", "velocity", "u", "v")

        self.omega = np.zeros((self.n, self.n), dtype=np.float64)
        self.psi = np.zeros((self.n, self.n), dtype=np.float64)
        self.u_x = np.zeros((self.n, self.n), dtype=np.float64)
        self.u_y = np.zeros((self.n, self.n), dtype=np.float64)

        # Coordinate grid for Semi-Lagrangian advection
        x = (np.arange(self.n) + 0.5) / self.n
        y = (np.arange(self.n) + 0.5) / self.n
        self.X, self.Y = np.meshgrid(x, y, indexing="ij")

        # Precompute Fourier wavevectors for spectral Poisson solver (nabla^2 psi = -omega)
        kx = 2.0 * np.pi * np.fft.fftfreq(self.n, d=self.dx)
        ky = 2.0 * np.pi * np.fft.fftfreq(self.n, d=self.dx)
        self.KX, self.KY = np.meshgrid(kx, ky, indexing="ij")
        self.K_sq = self.KX**2 + self.KY**2
        self.K_sq[0, 0] = 1.0  # Avoid zero-division at DC component

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(set(self.CAPABILITIES))

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        super().initialize(cfg)
        if "viscosity" in cfg:
            self.viscosity = float(cfg["viscosity"])
        if "buoyancy_coef" in cfg:
            self.buoyancy_coef = float(cfg["buoyancy_coef"])
        if "fluid_damping" in cfg:
            self.damping = float(cfg["fluid_damping"])
        self.omega.fill(0.0)
        self.psi.fill(0.0)
        self.u_x.fill(0.0)
        self.u_y.fill(0.0)

    def advect_scalar_field(self, field_arr: np.ndarray, dt: float, blend: float = 0.3) -> np.ndarray:
        """Advect a 2D scalar field (u or v) by the fluid velocity field using Semi-Lagrangian transport."""
        X_back = (self.X - self.u_x * dt) % 1.0
        Y_back = (self.Y - self.u_y * dt) % 1.0
        gx = X_back * self.n - 0.5
        gy = Y_back * self.n - 0.5

        i0 = np.floor(gx).astype(int) % self.n
        j0 = np.floor(gy).astype(int) % self.n
        i1 = (i0 + 1) % self.n
        j1 = (j0 + 1) % self.n

        fx = gx - np.floor(gx)
        fy = gy - np.floor(gy)

        advected = (
            (1.0 - fx) * (1.0 - fy) * field_arr[i0, j0]
            + fx * (1.0 - fy) * field_arr[i1, j0]
            + (1.0 - fx) * fy * field_arr[i0, j1]
            + fx * fy * field_arr[i1, j1]
        )
        result = (1.0 - blend) * field_arr + blend * advected
        return np.clip(result, 0.01, 12.0)

    def solve_streamfunction_and_velocity(self) -> None:
        """Solve Poisson equation nabla^2 psi = -omega and compute velocity u = (d_y psi, -d_x psi)."""
        omega_hat = np.fft.fft2(self.omega)
        psi_hat = omega_hat / self.K_sq
        psi_hat[0, 0] = 0.0  # Zero mean streamfunction
        self.psi = np.real(np.fft.ifft2(psi_hat))

        self.u_x = np.real(np.fft.ifft2(1j * self.KY * psi_hat))
        self.u_y = np.real(np.fft.ifft2(-1j * self.KX * psi_hat))

    def apply_buoyancy_torque(self, u_chem: np.ndarray, beta: float | None = None) -> None:
        """Generate vorticity source from chemical gradient buoyancy torque (curl of body force)."""
        b = self.buoyancy_coef if beta is None else beta
        if abs(b) < 1e-9:
            return

        u_hat = np.fft.fft2(u_chem)
        du_dx = np.real(np.fft.ifft2(1j * self.KX * u_hat))
        du_dy = np.real(np.fft.ifft2(1j * self.KY * u_hat))
        torque = b * (du_dx - du_dy)
        self.omega += torque

    def step(self, dt: float) -> None:
        """Advance vorticity transport: semi-lagrangian advection + spectral diffusion & damping."""
        self.solve_streamfunction_and_velocity()

        # Semi-Lagrangian advection of vorticity
        X_back = (self.X - self.u_x * dt) % 1.0
        Y_back = (self.Y - self.u_y * dt) % 1.0
        gx = X_back * self.n - 0.5
        gy = Y_back * self.n - 0.5
        i0 = np.floor(gx).astype(int) % self.n
        j0 = np.floor(gy).astype(int) % self.n
        i1 = (i0 + 1) % self.n
        j1 = (j0 + 1) % self.n
        fx = gx - np.floor(gx)
        fy = gy - np.floor(gy)

        adv_omega = (
            (1.0 - fx) * (1.0 - fy) * self.omega[i0, j0]
            + fx * (1.0 - fy) * self.omega[i1, j0]
            + (1.0 - fx) * fy * self.omega[i0, j1]
            + fx * fy * self.omega[i1, j1]
        )

        # Spectral viscous diffusion and damping
        omega_hat = np.fft.fft2(adv_omega)
        decay = np.exp(-(self.viscosity * self.K_sq + self.damping) * dt)
        self.omega = np.real(np.fft.ifft2(omega_hat * decay))

        self.solve_streamfunction_and_velocity()

    def sample_velocity_at(self, x: float, y: float) -> tuple[float, float]:
        """Bilinear interpolation of fluid velocity at arbitrary continuous coordinates (x, y) in [0, 1]."""
        x_clamped = max(0.0, min(0.9999, x))
        y_clamped = max(0.0, min(0.9999, y))

        gx = x_clamped * self.n
        gy = y_clamped * self.n

        i0 = math.floor(gx) % self.n
        j0 = math.floor(gy) % self.n
        i1 = (i0 + 1) % self.n
        j1 = (j0 + 1) % self.n

        fx = gx - math.floor(gx)
        fy = gy - math.floor(gy)

        vx = (1.0 - fx) * (1.0 - fy) * self.u_x[i0, j0] + \
             fx * (1.0 - fy) * self.u_x[i1, j0] + \
             (1.0 - fx) * fy * self.u_x[i0, j1] + \
             fx * fy * self.u_x[i1, j1]

        vy = (1.0 - fx) * (1.0 - fy) * self.u_y[i0, j0] + \
             fx * (1.0 - fy) * self.u_y[i1, j0] + \
             (1.0 - fx) * fy * self.u_y[i0, j1] + \
             fx * fy * self.u_y[i1, j1]

        return float(vx), float(vy)

    def kinetic_energy(self) -> float:
        """Mean fluid kinetic energy per unit mass: 0.5 * mean(u_x^2 + u_y^2)."""
        return float(0.5 * np.mean(self.u_x**2 + self.u_y**2))

    def max_vorticity(self) -> float:
        return float(np.max(np.abs(self.omega)))


class Swimmer:
    """Individual active swimmer particle with orientation and propulsion."""

    def __init__(self, swimmer_id: int, body: pymunk.Body, shape: pymunk.Circle, speed: float) -> None:
        self.id = swimmer_id
        self.body = body
        self.shape = shape
        self.speed = speed
        self.orientation: float = 0.0
        self.last_fluid_vel: tuple[float, float] = (0.0, 0.0)


class SwimmersAdapter(BaseAdapter):
    """Pymunk physics adapter for active swimmer particles (engine_id='pymunk', variant='swimmers')."""

    CAPABILITIES = (
        Capability("particle_positions"),
        Capability("particle_velocities"),
        Capability("geometry_provider"),
        Capability("force_integration"),
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.n_swimmers: int = int(cfg.get("n_swimmers", 8))
        self.swimmer_speed: float = float(cfg.get("swimmer_speed", 0.08))
        self.swimmer_radius: float = float(cfg.get("swimmer_radius", 0.04))
        self.drag_coef: float = float(cfg.get("advection_drag", 1.2))
        self.chemotaxis_kappa: float = float(cfg.get("chemotaxis_strength", 0.6))
        self.rot_diff: float = float(cfg.get("rotational_diffusion", 0.1))
        self.seed: int = int(cfg.get("seed", 42))

        provides = CapabilitySet()
        provides.add(Capability.from_dict("rigid_body", "1.0"))
        provides.add(Capability.from_dict("force_integration", "1.0"))
        provides.add(Capability.from_dict("geometry_provider", "1.0"))
        provides.add(Capability.from_dict("particle_positions", "1.0"))
        provides.add(Capability.from_dict("particle_velocities", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("scalar_field", "1.0"))
        requires.add(Capability.from_dict("field_gradient", "1.0"))
        requires.add(Capability.from_dict("velocity_field", "1.0"))

        super().__init__(
            engine_id="pymunk",
            provides=provides,
            requires=requires,
            native_timestep=0.05,
        )
        self._variant = "swimmers"
        self._state_keys = ("positions", "velocities", "count", "gradient", "velocity")

        self.space: pymunk.Space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)
        self.space.damping = 0.6
        self.swimmers: list[Swimmer] = []
        self._rng = np.random.default_rng(self.seed)

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(set(self.CAPABILITIES))

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        super().initialize(cfg)
        if "n_swimmers" in cfg:
            self.n_swimmers = int(cfg["n_swimmers"])
        if "swimmer_speed" in cfg:
            self.swimmer_speed = float(cfg["swimmer_speed"])
        if "swimmer_radius" in cfg:
            self.swimmer_radius = float(cfg["swimmer_radius"])
        if "advection_drag" in cfg:
            self.drag_coef = float(cfg["advection_drag"])
        if "chemotaxis_strength" in cfg:
            self.chemotaxis_kappa = float(cfg["chemotaxis_strength"])
        if "rotational_diffusion" in cfg:
            self.rot_diff = float(cfg["rotational_diffusion"])
        if "seed" in cfg:
            self.seed = int(cfg["seed"])

        self.space = pymunk.Space()
        self.space.gravity = (0.0, 0.0)
        self.space.damping = 0.6
        self.swimmers = []
        self._rng = np.random.default_rng(self.seed)

        walls = [
            pymunk.Segment(self.space.static_body, (0.0, 0.0), (1.0, 0.0), 0.01),
            pymunk.Segment(self.space.static_body, (1.0, 0.0), (1.0, 1.0), 0.01),
            pymunk.Segment(self.space.static_body, (1.0, 1.0), (0.0, 1.0), 0.01),
            pymunk.Segment(self.space.static_body, (0.0, 1.0), (0.0, 0.0), 0.01),
        ]
        for w in walls:
            w.elasticity = 0.8
            self.space.add(w)

        for i in range(self.n_swimmers):
            mass = 1.0
            moment = pymunk.moment_for_circle(mass, 0, self.swimmer_radius)
            body = pymunk.Body(mass, moment)
            x = float(self._rng.uniform(0.15, 0.85))
            y = float(self._rng.uniform(0.15, 0.85))
            body.position = (x, y)

            shape = pymunk.Circle(body, self.swimmer_radius)
            shape.elasticity = 0.5
            shape.friction = 0.2
            self.space.add(body, shape)

            swimmer = Swimmer(swimmer_id=i, body=body, shape=shape, speed=self.swimmer_speed)
            swimmer.orientation = float(self._rng.uniform(-np.pi, np.pi))
            self.swimmers.append(swimmer)

    def apply_fluid_advection(self, fluid: FluidEngineAdapter) -> None:
        """Apply hydrodynamic drag force: F_drag = gamma * (u_fluid - v_swimmer)."""
        for sw in self.swimmers:
            px, py = sw.body.position.x, sw.body.position.y
            uf_x, uf_y = fluid.sample_velocity_at(px, py)
            sw.last_fluid_vel = (uf_x, uf_y)

            vx, vy = sw.body.velocity.x, sw.body.velocity.y
            drag_x = self.drag_coef * (uf_x - vx)
            drag_y = self.drag_coef * (uf_y - vy)
            sw.body.apply_force_at_local_point((drag_x, drag_y), (0, 0))

    def apply_chemotactic_steering_and_propulsion(
        self,
        grad_fn: Callable[[float, float], tuple[float, float]],
        dt: float,
    ) -> None:
        """Apply active self-propulsion and steer orientation towards chemical gradient."""
        for sw in self.swimmers:
            px, py = sw.body.position.x, sw.body.position.y
            gx, gy = grad_fn(px, py)
            grad_mag = math.hypot(gx, gy)

            if grad_mag > 1e-5:
                target_theta = math.atan2(gy, gx)
                angle_diff = (target_theta - sw.orientation + math.pi) % (2.0 * math.pi) - math.pi
                sw.orientation += self.chemotaxis_kappa * angle_diff * dt

            sw.orientation += float(self._rng.normal(0.0, math.sqrt(max(1e-8, 2.0 * self.rot_diff * dt))))

            prop_fx = sw.speed * 8.0 * math.cos(sw.orientation)
            prop_fy = sw.speed * 8.0 * math.sin(sw.orientation)
            sw.body.apply_force_at_local_point((prop_fx, prop_fy), (0, 0))

    def step(self, dt: float) -> None:
        substeps = 4
        sub_dt = dt / float(substeps)
        for _ in range(substeps):
            self.space.step(sub_dt)

        for sw in self.swimmers:
            px = sw.body.position.x
            py = sw.body.position.y
            vx = sw.body.velocity.x
            vy = sw.body.velocity.y
            if px <= 0.03:
                px = 0.03
                vx = abs(vx) * 0.5 + 0.01
            elif px >= 0.97:
                px = 0.97
                vx = -abs(vx) * 0.5 - 0.01
            if py <= 0.03:
                py = 0.03
                vy = abs(vy) * 0.5 + 0.01
            elif py >= 0.97:
                py = 0.97
                vy = -abs(vy) * 0.5 - 0.01
            sw.body.position = (px, py)
            sw.body.velocity = (vx, vy)

    def get_positions(self) -> dict[str, tuple[float, float]]:
        return {f"swimmer_{sw.id}": (float(sw.body.position.x), float(sw.body.position.y)) for sw in self.swimmers}

    def get_velocities(self) -> dict[str, tuple[float, float]]:
        return {f"swimmer_{sw.id}": (float(sw.body.velocity.x), float(sw.body.velocity.y)) for sw in self.swimmers}

    def get_orientations(self) -> dict[str, float]:
        return {f"swimmer_{sw.id}": float(sw.orientation) for sw in self.swimmers}

    def mean_swimmer_speed(self) -> float:
        if not self.swimmers:
            return 0.0
        speeds = [math.hypot(sw.body.velocity.x, sw.body.velocity.y) for sw in self.swimmers]
        return float(np.mean(speeds))


@dataclass
class FluidActiveMatterTrajectory:
    """Multi-channel trajectory capturing chemical, fluid, and swimmer telemetry."""

    u_snaps: list[np.ndarray] = field(default_factory=list)
    v_snaps: list[np.ndarray] = field(default_factory=list)
    omega_snaps: list[np.ndarray] = field(default_factory=list)
    ux_snaps: list[np.ndarray] = field(default_factory=list)
    uy_snaps: list[np.ndarray] = field(default_factory=list)
    positions: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    velocities: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    orientations: dict[str, list[float]] = field(default_factory=dict)
    speeds: list[float] = field(default_factory=list)
    fluid_energies: list[float] = field(default_factory=list)
    vorticities: list[float] = field(default_factory=list)
    time_points: list[float] = field(default_factory=list)
