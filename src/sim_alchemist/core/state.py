"""Shared world state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldState:
    """
    Unified world state shared across engines.

    This is the single source of truth for cross-engine data.
    Engines read from and write to specific namespaces.
    """
    time: float = 0.0
    step: int = 0
    seed: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    namespaces: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_namespace(self, engine_id: str) -> dict[str, Any]:
        """Get or create namespace for an engine."""
        if engine_id not in self.namespaces:
            self.namespaces[engine_id] = {}
        return self.namespaces[engine_id]

    def set(self, engine_id: str, key: str, value: Any) -> None:
        ns = self.get_namespace(engine_id)
        ns[key] = value

    def get(self, engine_id: str, key: str, default: Any = None) -> Any:
        return self.namespaces.get(engine_id, {}).get(key, default)

    def snapshot(self) -> dict[str, Any]:
        """Create a serializable snapshot of the world state."""
        return {
            "time": self.time,
            "step": self.step,
            "seed": self.seed,
            "config": self.config,
            "namespaces": {k: dict(v) for k, v in self.namespaces.items()},
        }