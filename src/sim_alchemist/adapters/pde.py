"""Py-pde adapter for reaction-diffusion fields."""

from __future__ import annotations

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

        requires = CapabilitySet()
        requires.add(Capability.from_dict("geometry_provider", "1.0"))

        super().__init__(
            engine_id="py-pde",
            provides=provides,
            requires=requires,
            native_timestep=field_step,
        )

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
        self._field = None
        self._blocked_mask = None

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
        if self._field is not None:
            self._field.set_blocked(blocked)
            self._blocked_mask[:] = blocked

    def get_field(self):
        return self._field

    def get_state(self) -> dict[str, Any]:
        if self._field is None:
            return {}
        return {
            "t": self._field.t,
            "u": self._field.u.copy(),
            "v": self._field.v.copy(),
            "blocked": self._blocked_mask.copy(),
        }

    def _publish_field_state(self) -> None:
        if self._field is None:
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