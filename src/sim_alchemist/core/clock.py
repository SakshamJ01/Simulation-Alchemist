"""Deterministic simulation clock and macro-step coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SimulationClock:
    """
    Deterministic clock for macro-step orchestration.

    The clock manages:
    - Global simulation time
    - Macro-step count
    - Subsystem timestep mapping
    """
    macro_timestep: float = 0.2      # MT per macro step (field_step)
    native_timesteps: dict[str, float] = field(default_factory=dict)  # engine_id -> dt
    current_time: float = 0.0
    step_count: int = 0
    max_steps: int = 160

    def __post_init__(self) -> None:
        # Validate divisibility for deterministic substep alignment
        for engine_id, dt in self.native_timesteps.items():
            if self.macro_timestep % dt > 1e-12:
                raise ValueError(
                    f"Engine {engine_id} timestep {dt} does not evenly divide "
                    f"macro timestep {self.macro_timestep}"
                )

    @property
    def is_finished(self) -> bool:
        return self.step_count >= self.max_steps

    def next_macro_step(self) -> float:
        """Advance to next macro step, return dt."""
        self.current_time += self.macro_timestep
        self.step_count += 1
        return self.macro_timestep

    def substeps_for(self, engine_id: str) -> int:
        """Calculate integer substeps for an engine's native timestep."""
        dt = self.native_timesteps.get(engine_id, self.macro_timestep)
        return max(1, round(self.macro_timestep / dt))

    def state(self) -> dict[str, Any]:
        return {
            "time": self.current_time,
            "step": self.step_count,
            "macro_timestep": self.macro_timestep,
        }