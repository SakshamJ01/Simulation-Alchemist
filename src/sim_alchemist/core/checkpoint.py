"""World checkpoint and zero-drift state restoration (Phase 4 Slice 4.4).

Provides deterministic snapshot serialization and restoration for multi-engine
simulations, enabling pause/resume, mid-run inspection, and checkpoint-restart.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sim_alchemist.core.clock import SimulationClock


@dataclass
class WorldCheckpoint:
    """A point-in-time snapshot of the simulation world and all its components."""

    step: int
    time: float
    seed: int | None
    component_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to a dictionary."""
        return {
            "step": self.step,
            "time": self.time,
            "seed": self.seed,
            "component_states": self.component_states,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorldCheckpoint:
        """Construct a WorldCheckpoint from a dictionary."""
        return cls(
            step=int(data["step"]),
            time=float(data["time"]),
            seed=int(data["seed"]) if data.get("seed") is not None else None,
            component_states=dict(data.get("component_states", {})),
            metadata=dict(data.get("metadata", {})),
        )

    def save(self, filepath: str | Path) -> None:
        """Save the checkpoint to a JSON file on disk."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.as_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str | Path) -> WorldCheckpoint:
        """Load a checkpoint from a JSON file on disk."""
        path = Path(filepath)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def capture_checkpoint(
    clock: SimulationClock,
    engines: Mapping[str, Any] | None = None,
    seed: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorldCheckpoint:
    """Capture a snapshot of the current simulation clock and all engine states."""
    states: dict[str, dict[str, Any]] = {}
    if engines:
        for engine_id, eng in engines.items():
            st = eng.get_state()
            # Deep copy to ensure immutable snapshot
            states[engine_id] = copy.deepcopy(st)

    return WorldCheckpoint(
        step=clock.step_count,
        time=clock.current_time,
        seed=seed,
        component_states=states,
        metadata=metadata or {},
    )


def restore_checkpoint(
    checkpoint: WorldCheckpoint,
    clock: SimulationClock,
    engines: Mapping[str, Any] | None = None,
) -> None:
    """Restore simulation clock and engines from a checkpoint.

    Engines that implement `initialize` or state restoration can be rehydrated.
    """
    clock.current_time = checkpoint.time
    clock.step_count = checkpoint.step

    if engines and checkpoint.component_states:
        for engine_id, st in checkpoint.component_states.items():
            if engine_id in engines:
                eng = engines[engine_id]
                # If engine supports initialize with restored state config:
                eng.initialize(st)

