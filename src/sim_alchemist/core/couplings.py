"""First-class reusable coupling primitives and nonlinear signal transformers (Phase 4D).

Provides standardized, composable mathematical transformers for inter-component
couplings, including hysteresis thresholds, temporal delay buffers, sigmoid/saturation
transducers, and sequential coupling pipelines.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CouplingTransformer(Protocol):
    """Protocol for stateful/stateless mathematical signal transformers in couplings."""

    def transform(self, value: float) -> float:
        """Transform a scalar signal into a modified coupling input/control value."""
        ...

    def reset(self) -> None:
        """Reset internal history/state back to initial conditions."""
        ...

    def state_dict(self) -> dict[str, Any]:
        """Serialize current internal state for checkpointing/inspection."""
        ...

    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore internal state from checkpoint."""
        ...


@dataclass
class HysteresisFilter:
    """Bistable hysteresis filter with dual thresholds and refractory cooldown.

    State switches to active (1.0) when signal exceeds high_threshold, and switches
    to inactive (0.0) when signal drops below low_threshold. A cooldown timer prevents
    rapid chatter switching.
    """

    low_threshold: float
    high_threshold: float
    cooldown_steps: int = 0
    active_value: float = 1.0
    inactive_value: float = 0.0
    initial_state: bool = False

    _is_active: bool = field(init=False)
    _current_cooldown: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.low_threshold > self.high_threshold:
            raise ValueError(
                f"low_threshold ({self.low_threshold}) must be <= high_threshold ({self.high_threshold})"
            )
        if self.cooldown_steps < 0:
            raise ValueError(f"cooldown_steps ({self.cooldown_steps}) cannot be negative.")
        self._is_active = self.initial_state
        self._current_cooldown = 0

    @property
    def is_active(self) -> bool:
        return self._is_active

    def transform(self, value: float) -> float:
        """Step the hysteresis state machine and return active/inactive value."""
        if self._current_cooldown > 0:
            self._current_cooldown -= 1
        else:
            if not self._is_active and value >= self.high_threshold:
                self._is_active = True
                self._current_cooldown = self.cooldown_steps
            elif self._is_active and value <= self.low_threshold:
                self._is_active = False
                self._current_cooldown = self.cooldown_steps

        return self.active_value if self._is_active else self.inactive_value

    def reset(self) -> None:
        self._is_active = self.initial_state
        self._current_cooldown = 0

    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "HysteresisFilter",
            "is_active": self._is_active,
            "current_cooldown": self._current_cooldown,
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
            "cooldown_steps": self.cooldown_steps,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        self._is_active = bool(state["is_active"])
        self._current_cooldown = int(state["current_cooldown"])


@dataclass
class TemporalDelayBuffer:
    """FIFO circular delay buffer introducing fixed discrete-step time lag.

    Outputs default_value until delay_steps have elapsed.
    """

    delay_steps: int
    default_value: float = 0.0
    _buffer: deque[float] = field(init=False)

    def __post_init__(self) -> None:
        if self.delay_steps < 0:
            raise ValueError(f"delay_steps ({self.delay_steps}) must be non-negative.")
        self._buffer = deque([self.default_value] * self.delay_steps, maxlen=max(1, self.delay_steps + 1))

    def transform(self, value: float) -> float:
        """Push a new value into buffer and return the value delayed by delay_steps."""
        if self.delay_steps == 0:
            return value

        self._buffer.append(value)
        # Oldest value is at index 0 before the most recent append
        delayed_output = self._buffer.popleft()
        return delayed_output

    def reset(self) -> None:
        self._buffer = deque([self.default_value] * self.delay_steps, maxlen=max(1, self.delay_steps + 1))

    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "TemporalDelayBuffer",
            "delay_steps": self.delay_steps,
            "default_value": self.default_value,
            "buffer": list(self._buffer),
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        self.delay_steps = int(state["delay_steps"])
        self.default_value = float(state["default_value"])
        self._buffer = deque(state["buffer"], maxlen=max(1, self.delay_steps + 1))


@dataclass(frozen=True)
class SigmoidTransfer:
    """Smooth sigmoid transduction function: y = lower + (upper - lower) / (1 + exp(-k * (x - midpoint)))."""

    midpoint: float = 0.0
    steepness: float = 1.0
    lower_bound: float = 0.0
    upper_bound: float = 1.0

    def __post_init__(self) -> None:
        if self.lower_bound >= self.upper_bound:
            raise ValueError(f"lower_bound ({self.lower_bound}) must be < upper_bound ({self.upper_bound})")

    def transform(self, value: float) -> float:
        """Compute smooth bounded activation."""
        z = -self.steepness * (value - self.midpoint)
        # Protect against float overflow in exp
        if z > 700.0:
            sig = 0.0
        elif z < -700.0:
            sig = 1.0
        else:
            sig = 1.0 / (1.0 + math.exp(z))
        return self.lower_bound + (self.upper_bound - self.lower_bound) * sig

    def reset(self) -> None:
        pass  # Stateless

    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "SigmoidTransfer",
            "midpoint": self.midpoint,
            "steepness": self.steepness,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        pass


@dataclass(frozen=True)
class SaturationFilter:
    """Clamps signal strictly within [min_val, max_val] with optional linear scaling."""

    min_val: float
    max_val: float
    scale: float = 1.0
    bias: float = 0.0

    def __post_init__(self) -> None:
        if self.min_val > self.max_val:
            raise ValueError(f"min_val ({self.min_val}) must be <= max_val ({self.max_val})")

    def transform(self, value: float) -> float:
        scaled = (value * self.scale) + self.bias
        return max(self.min_val, min(self.max_val, scaled))

    def reset(self) -> None:
        pass

    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "SaturationFilter",
            "min_val": self.min_val,
            "max_val": self.max_val,
            "scale": self.scale,
            "bias": self.bias,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        pass


@dataclass
class CouplingPipeline:
    """Sequential pipeline of multiple CouplingTransformers."""

    transformers: Sequence[CouplingTransformer] = field(default_factory=tuple)

    def transform(self, value: float) -> float:
        """Pass value through each transformer in sequence."""
        current = value
        for t in self.transformers:
            current = t.transform(current)
        return current

    def reset(self) -> None:
        for t in self.transformers:
            t.reset()

    def state_dict(self) -> dict[str, Any]:
        return {
            "type": "CouplingPipeline",
            "transformers": [t.state_dict() for t in self.transformers],
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        for t, s in zip(self.transformers, state["transformers"]):
            t.load_state_dict(s)
