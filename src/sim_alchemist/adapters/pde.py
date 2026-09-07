"""Py-pde adapter for reaction-diffusion fields."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.events import Event, EventType


class PyPDEAdapter(BaseAdapter):
    """Adapter wrapping py-pde reaction-diffusion field."""

    def __init__(
        self,
        n: int = 32,
        du: float = 0.005,
        dv: float = 0.2,
        a: float = 0.1,
        b: float = 0.9,
        dt: float = 5.0e-4,
        seed: int = 0,
        field_step: float = 0.2,
    ) -> None:
        provides = CapabilitySet()
        provides.add(Capability.from_dict("scalar_field", "1.0"))
        provides.add(Capability.from_dict("reaction_diffusion", "1.0"))
        provides.add(Capability.from_dict("spatial_sampling", "1.0"))
        provides.add(Capability.from_dict("field_masking", "1.0"))
        provides.add(Capability.from_dict("field_gradient", "1.0"))
        provides.add(Capability.from_dict("field_sources", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("geometry_provider", "1.0"))

        super().__init__(
            engine_id="py-pde",
            provides=provides,
            requires=requires,
            native_timestep=field_step,
        )
        self._state_keys = ("u", "v", "blocked", "gradient", "sources")
        self._grid = n

        self._config = {
            "n": n,
            "du": du,
            "dv": dv,
            "a": a,
            "b": b,
            "dt": dt,
            "seed": seed,
            "field_step": field_step,
        }
        self._field: Any | None = None
        self._blocked_mask: np.ndarray | None = None

    def initialize(self, config: dict[str, Any]) -> None:
        from chemomech.reaction_diffusion import RDField
        super().initialize(config)
        self._field = RDField(
            n=self._config["n"],
            du=self._config["du"],
            dv=self._config["dv"],
            a=self._config["a"],
            b=self._config["b"],
            dt=self._config["dt"],
            seed=self._config["seed"],
        )
        n = self._config["n"]
        self._blocked_mask = np.zeros((n, n), dtype=bool)

    def step(self, dt: float) -> None:
        """Advance the field by one macro step."""
        if self._field is None:
            return
        self._field.advance(dt)
        self._publish_field_state()

    def set_blocked(self, blocked: np.ndarray) -> None:
        """Set the wall mask from geometry."""
        if self._field is None or self._blocked_mask is None:
            return
        self._field.set_blocked(blocked)
        self._blocked_mask[:] = blocked

    def get_field(self):
        return self._field

    def get_state(self) -> dict[str, Any]:
        if self._field is None or self._blocked_mask is None:
            return {}
        return {
            "t": self._field.t,
            "u": self._field.u.copy(),
            "v": self._field.v.copy(),
            "blocked": self._blocked_mask.copy(),
        }

    def _publish_field_state(self) -> None:
        if self._field is None or self._blocked_mask is None:
            return
        event = Event.field_state(
            self.engine_id,
            self._field.t,
            {
                "u": self._field.u.copy(),
                "v": self._field.v.copy(),
                "blocked": self._blocked_mask.copy(),
            },
        )
        self.publish(event)

    def sample(self, x: float, y: float, field_name: str = "u") -> float:
        if self._field is None:
            return 0.0
        return self._field.sample(x, y, field_name)

    def gradient(self, x: float, y: float, field_name: str = "u") -> np.ndarray:
        if self._field is None:
            return np.array([0.0, 0.0])
        return self._field.gradient(x, y, field_name)

    def apply_sources(self, sources: list[dict[str, Any]]) -> None:
        """Inject source/sink contributions into the field.

        Each entry is a generic source specification, e.g.
        ``{"x": x, "y": y, "u": du, "v": dv, "radius": r}`` where ``du``/``dv``
        are concentration deltas applied on the grid cells within ``radius``
        of ``(x, y)``.  This is a *field-level* mutation so any engine that
        provides the ``field_sources`` capability can consume chemical.
        """
        if self._field is None:
            return
        n = self._config["n"]
        u = self._field.u.copy()
        v = self._field.v.copy()
        for src in sources:
            x, y = src["x"], src["y"]
            du, dv = src.get("u", 0.0), src.get("v", 0.0)
            if du == 0.0 and dv == 0.0:
                continue
            radius = src.get("radius", 1.0 / n)
            r_frac = max(1.0, radius * n)
            colc = (n * float(np.clip(x, 0.0, 1.0))) - 0.5
            rowc = (n * float(np.clip(y, 0.0, 1.0))) - 0.5
            r0 = max(0, int(np.floor(rowc - r_frac)))
            r1 = min(n, int(np.ceil(rowc + r_frac)) + 1)
            c0 = max(0, int(np.floor(colc - r_frac)))
            c1 = min(n, int(np.ceil(colc + r_frac)) + 1)
            for i in range(r0, r1):
                for j in range(c0, c1):
                    d = math.hypot(i - rowc, j - colc)
                    w = max(0.0, 1.0 - d / r_frac)
                    u[i, j] += du * w
                    v[i, j] += dv * w
        self._field.u[:] = u
        self._field.v[:] = v

    def apply_event(self, event: Event) -> bool:
        if event.type == EventType.GEOMETRY_UPDATE:
            blocked = event.payload.get("blocked")
            if blocked is not None:
                self.set_blocked(np.asarray(blocked, dtype=bool))
                return True
        return False

    def shutdown(self) -> None:
        self._field = None
        self._blocked_mask = None