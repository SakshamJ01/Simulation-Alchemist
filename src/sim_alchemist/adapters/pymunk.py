"""Pymunk adapter for rigid-body wall physics."""

from __future__ import annotations

from typing import Any

import numpy as np

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.events import Event, EventType


class PymunkAdapter(BaseAdapter):
    """Adapter wrapping Pymunk wall physics."""

    def __init__(
        self,
        n: int = 32,
        mass: float = 1.0,
        damping: float = 0.05,
        dt_phys: float = 0.05,
        phys_substeps: int = 4,
        scale: float = 100.0,
    ) -> None:
        provides = CapabilitySet()
        provides.add(Capability.from_dict("rigid_body", "1.0"))
        provides.add(Capability.from_dict("collision_geometry", "1.0"))
        provides.add(Capability.from_dict("force_integration", "1.0"))
        provides.add(Capability.from_dict("geometry_provider", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("field_gradient", "1.0"))
        requires.add(Capability.from_dict("agent_intentions", "1.0"))

        super().__init__(
            engine_id="pymunk",
            provides=provides,
            requires=requires,
            native_timestep=dt_phys,
        )

        self._config = {
            "n": n,
            "mass": mass,
            "damping": damping,
            "dt_phys": dt_phys,
            "phys_substeps": phys_substeps,
            "scale": scale,
        }
        self._wallspace = None
        self._pending_forces: dict[int, tuple[float, float]] = {}
        self._pending_wall_adds: list[dict[str, Any]] = []
        self._pending_wall_removes: list[int] = []

    def initialize(self, config: dict[str, Any]) -> None:
        from chemomech.physics import WallSpace
        super().initialize(config)
        self._wallspace = WallSpace(
            n=self._config["n"],
            mass=self._config["mass"],
            damping=self._config["damping"],
            dt_phys=self._config["dt_phys"],
            phys_substeps=self._config["phys_substeps"],
        )

    def step(self, dt: float) -> None:
        """Apply pending forces, step physics, then publish geometry."""
        if self._wallspace is None:
            return

        # Apply pending forces
        for wall_id, (fx, fy) in self._pending_forces.items():
            wall = next((w for w in self._wallspace.walls if w.id == wall_id), None)
            if wall:
                self._wallspace.apply_force(wall, fx, fy, torque=0.0)
        self._pending_forces.clear()

        # Apply pending wall adds/removes
        for wall_data in self._pending_wall_adds:
            self._wallspace.add_wall(
                wall_data["p1"], wall_data["p2"],
                wall_data["radius"], wall_data.get("t", 0.0),
                wall_data.get("owner"), wall_data.get("mass")
            )
        self._pending_wall_adds.clear()

        for wall_id in self._pending_wall_removes:
            wall = next((w for w in self._wallspace.walls if w.id == wall_id), None)
            if wall:
                self._wallspace.remove_wall(wall)
        self._pending_wall_removes.clear()

        # Step physics
        substeps = self._config["phys_substeps"]
        self._wallspace.step(dt=self._config["dt_phys"], substeps=substeps)

        # Publish geometry update
        self._publish_geometry()

    def apply_force(self, wall_id: int, fx: float, fy: float) -> None:
        self._pending_forces[wall_id] = (fx, fy)

    def add_wall(self, p1: tuple[float, float], p2: tuple[float, float],
                 radius: float, t: float = 0.0, owner: int | None = None,
                 mass: float | None = None) -> None:
        self._pending_wall_adds.append({
            "p1": p1, "p2": p2, "radius": radius,
            "t": t, "owner": owner, "mass": mass
        })

    def remove_wall(self, wall_id: int) -> None:
        self._pending_wall_removes.append(wall_id)

    def get_state(self) -> dict[str, Any]:
        if self._wallspace is None:
            return {}
        return {
            "walls": [w.id for w in self._wallspace.walls],
            "geometry": self._wallspace.segments_world(),
            "blocked": self._wallspace.blocked().tolist(),
            "wall_tracks": {
                w.id: (w.center[0], w.center[1], w.angle)
                for w in self._wallspace.walls
            },
        }

    def _publish_geometry(self) -> None:
        if self._wallspace is None:
            return
        blocked = self._wallspace.blocked()
        event = Event.geometry_update(
            self.engine_id,
            self._config.get("t", 0.0),
            {
                "blocked": blocked.tolist(),
                "segments": self._wallspace.segments_world(),
                "wall_count": self._wallspace.wall_count(),
            },
        )
        self.publish(event)

    def get_geometry(self) -> dict[str, Any]:
        if self._wallspace is None:
            return {"blocked": np.zeros((self._config["n"], self._config["n"]), dtype=bool),
                    "segments": [], "wall_count": 0}
        return {
            "blocked": self._wallspace.blocked(),
            "segments": self._wallspace.segments_world(),
            "wall_count": self._wallspace.wall_count(),
        }

    def get_wall_centers(self) -> dict[int, tuple[float, float]]:
        if self._wallspace is None:
            return {}
        return {w.id: w.center for w in self._wallspace.walls}

    def apply_event(self, event: Event) -> bool:
        if event.type == EventType.FIELD_FORCE:
            forces = event.payload.get("forces", {})
            for wall_id, (fx, fy) in forces.items():
                self.apply_force(wall_id, fx, fy)
            return True
        elif event.type == EventType.WALL_ADD:
            wall_data = event.payload
            self.add_wall(
                wall_data["p1"], wall_data["p2"],
                wall_data["radius"], wall_data.get("t", 0.0),
                wall_data.get("owner")
            )
            return True
        elif event.type == EventType.WALL_REMOVE:
            wall_ids = event.payload.get("wall_ids", [])
            for wall_id in wall_ids:
                self.remove_wall(wall_id)
            return True
        elif event.type == EventType.AGENT_DECISION:
            # Agent decisions are handled by the orchestrator
            return True
        return False

    def shutdown(self) -> None:
        self._wallspace = None
        self._pending_forces.clear()
        self._pending_wall_adds.clear()
        self._pending_wall_removes.clear()