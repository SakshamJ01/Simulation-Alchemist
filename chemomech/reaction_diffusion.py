"""Reaction-diffusion field on a py-pde grid with maskable wall obstacles.

The chemo-morphogen field is a two-species Schnakenberg reaction-diffusion
system solved by py-pde's numpy backend:

    du/dt = Du * lap(u) + m(x) * (a - u + u**2 * v)
    dv/dt = Dv * lap(v) + m(x) * (b - u**2 * v)

where m(x) in {0, 1} is a domain mask equal to 1 on open cells and 0 on wall
cells.  The mask multiplies the *entire* evolution rate on wall cells, so wall
cells are frozen at the concentration they had when the wall was placed.  This
is an *embedded clamped-obstacle* approximation:

  * neighbours still see the (constant) wall value in their laplacian stencil,
    so the wall acts as a fixed-concentration boundary;
  * no signal propagates *through* a wall, because wall concentrations never
    change (the wall partitions the domain into compartments).

We deliberately do NOT claim this is a true "no-flux" boundary: the diffusive
flux toward a wall cell is not zeroed, the wall value is clamped instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pde


@dataclass
class RDField:
    """Schnakenberg reaction-diffusion field with embedded wall mask."""

    n: int = 32                     # grid cells per side (dx = 1/n)
    du: float = 0.005               # activator diffusivity
    dv: float = 0.2                 # inhibitor diffusivity
    a: float = 0.1                  # activator production
    b: float = 0.9                  # inhibitor production
    dt: float = 5.0e-4              # explicit Euler time step (stability-limited)
    seed: int = 0

    t: float = field(default=0.0, init=False)
    state: pde.FieldCollection | None = field(default=None, init=False)
    eq: pde.PDE | None = field(default=None, init=False)
    _mask_field: pde.ScalarField | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.grid = pde.CartesianGrid(
            bounds=((0.0, 1.0), (0.0, 1.0)), shape=(self.n, self.n)
        )
        rng = np.random.default_rng(self.seed)
        u0 = 0.5 + 0.01 * (rng.random((self.n, self.n)) - 0.5)
        v0 = 1.0 + 0.01 * (rng.random((self.n, self.n)) - 0.5)
        u = pde.ScalarField(self.grid, u0)
        v = pde.ScalarField(self.grid, v0)
        self.state = pde.FieldCollection([u, v])

        ones = np.ones((self.n, self.n), dtype=float)
        self._mask_field = pde.ScalarField(self.grid, ones)

        # RHS: mask * (D * laplace + reaction). Wall cells -> rate 0 (frozen).
        self.eq = pde.PDE(
            rhs={
                "u": (
                    f"mask * ({self.du} * laplace(u) + {self.a} - u + u * u * v)"
                ),
                "v": f"mask * ({self.dv} * laplace(v) + {self.b} - u * u * v)",
            },
            consts={"mask": self._mask_field},  # type: ignore[reportArgumentType]  # py-pde stub: ScalarField is accepted at runtime
            bc="auto_periodic_neumann",
        )
        # One short solve warm-up: py-pde lazily compiles the RHS (sympy
        # lambdify). Subsequent calls are ~30 ms. Without walls the field is a
        # clean Schnakenberg baseline.
        self.eq.solve(
            self.state, t_range=0.001, dt=self.dt, backend="numpy", tracker=None
        )

    @property
    def u(self) -> np.ndarray:
        return self.state[0].data  # type: ignore[reportOptionalSubscript]

    @property
    def v(self) -> np.ndarray:
        return self.state[1].data  # type: ignore[reportOptionalSubscript]

    def advance(self, d_t: float) -> None:
        """Evolve the field from current time t to t + d_t."""
        self.state = self.eq.solve(  # type: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess, reportAssignmentType, reportArgumentType]
            self.state,  # type: ignore[reportArgumentType]  # py-pde stub: solve() accepts FieldCollection at runtime
            t_range=(self.t, self.t + d_t),
            dt=self.dt,
            backend="numpy",
            tracker=None,
        )
        self.t += d_t

    def set_blocked(self, blocked: np.ndarray) -> None:
        """Translate a boolean wall cell mask into the PDE domain mask.

        `blocked` is the boolean rasterized wall geometry.  The mask mutates in
        place because the compiled RHS holds a reference to the same array.
        """
        blocked = np.asarray(blocked, dtype=bool).reshape(self.n, self.n)
        mask_data = np.where(blocked, 0.0, 1.0)
        self._mask_field.data[:] = mask_data  # type: ignore[reportOptionalMemberAccess]

    def _index(self, x: float, y: float) -> tuple[float, float]:
        """Continuous (x, y) in [0,1]^2 -> fractional cell (row, col)."""
        row = y * self.n - 0.5
        col = x * self.n - 0.5
        row = float(np.clip(row, 0.0, self.n - 1.0))
        col = float(np.clip(col, 0.0, self.n - 1.0))
        return row, col

    def sample(self, x: float, y: float, field_name: str = "u") -> float:
        """Bilinear interpolation of a species field at continuous coords."""
        values = self.u if field_name == "u" else self.v
        row, col = self._index(x, y)
        r0, c0 = int(np.floor(row)), int(np.floor(col))
        r0 = min(r0, self.n - 2)
        c0 = min(c0, self.n - 2)
        dr, dc = row - r0, col - c0
        v00 = values[r0, c0]
        v10 = values[r0 + 1, c0]
        v01 = values[r0, c0 + 1]
        v11 = values[r0 + 1, c0 + 1]
        return float(
            (1 - dr) * ((1 - dc) * v00 + dc * v01)
            + dr * ((1 - dc) * v10 + dc * v11)
        )

    def gradient(self, x: float, y: float, field_name: str = "u") -> np.ndarray:
        """Central finite-difference gradient of a species at (x, y)."""
        h = 1.0 / self.n
        dudx = (self.sample(min(x + h, 1.0), y, field_name)
                - self.sample(max(x - h, 0.0), y, field_name)) / (2.0 * h)
        dudy = (self.sample(x, min(y + h, 1.0), field_name)
                - self.sample(x, max(y - h, 0.0), field_name)) / (2.0 * h)
        return np.array([dudx, dudy])