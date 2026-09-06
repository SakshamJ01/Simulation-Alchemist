"""Typed, declarative world definitions.

Task 1.3 introduces the declarative composition surface of Simulation
Alchemist: a *world* is a plain, serializable data structure -- a component
id list (each with a config), the required capabilities, an ordered macro-step
schedule, clock parameters, a seed, and the shared top-level config passed to
every adapter's ``initialize``.

A world may be expressed programmatically as a ``WorldDefinition`` dataclass
or loaded from a YAML file (``load_world_yaml``).  Both routes produce the
exact same typed object, so a YAML world is guaranteed to behave identically
to its programmatic twin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ComponentSpec:
    """One component (adapter) instance requested by a world.

    ``id`` names a registered adapter factory (see ``registry.py``); ``config``
    is an opaque per-component configuration dict handed to the factory when
    it constructs the adapter.
    """

    id: str
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentSpec:
        cfg = data.get("config", {})
        if not isinstance(cfg, dict):
            raise TypeError(f"Component '{data.get('id')}' config must be a mapping")
        return cls(id=data["id"], config=dict(cfg))


@dataclass(frozen=True)
class WorldDefinition:
    """The complete, declarative description of one composed world.

    This is the single typed object the composer consumes.  It is fully
    serializable (dict round-trips cleanly) and is the canonical source for
    both the programmatic and the YAML-driven composition paths.
    """

    id: str
    components: tuple[ComponentSpec, ...] = field(default_factory=tuple)
    requires: tuple[str, ...] = field(default_factory=tuple)
    schedule: tuple[str, ...] = field(default_factory=tuple)
    macro_timestep: float = 0.2
    max_steps: int = 160
    seed: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "components": [{"id": c.id, "config": c.config} for c in self.components],
            "requires": list(self.requires),
            "schedule": list(self.schedule),
            "macro_timestep": self.macro_timestep,
            "max_steps": self.max_steps,
            "seed": self.seed,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldDefinition:
        components = tuple(
            ComponentSpec.from_dict(c) for c in data.get("components", [])
        )
        return cls(
            id=data["id"],
            components=components,
            requires=tuple(data.get("requires", [])),
            schedule=tuple(data.get("schedule", [])),
            macro_timestep=float(data.get("macro_timestep", 0.2)),
            max_steps=int(data.get("max_steps", 160)),
            seed=int(data.get("seed", 0)),
            config=dict(data.get("config", {})),
        )

    def to_yaml(self, path: str | Path) -> None:
        """Serialize this world definition to a YAML file."""
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(self.as_dict(), fh, sort_keys=False, default_flow_style=False)


def load_world_yaml(path: str | Path) -> WorldDefinition:
    """Load a ``WorldDefinition`` from a YAML file.

    The YAML schema mirrors ``WorldDefinition.as_dict()``.  Booleans, numbers,
    and lists are handled natively by ``yaml.safe_load``.
    """
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"Not a valid world YAML (missing 'id'): {path}")
    return WorldDefinition.from_dict(data)
