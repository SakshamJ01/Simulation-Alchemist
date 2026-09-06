"""Core type definitions and protocols."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.events import Event


@dataclass(frozen=True)
class Capability:
    """A named capability that an engine provides or requires."""
    name: str
    version: str = "1.0"
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"

    @classmethod
    def from_dict(cls, name: str, version: str = "1.0", metadata: dict[str, Any] | None = None) -> Capability:
        meta = tuple(sorted(metadata.items())) if metadata else ()
        return cls(name=name, version=version, metadata=meta)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "metadata": dict(self.metadata)}


@dataclass
class CapabilitySet:
    """A set of capabilities with set-like operations."""
    capabilities: set[Capability] = field(default_factory=set)

    def add(self, cap: Capability) -> None:
        self.capabilities.add(cap)

    def has(self, name: str) -> bool:
        return any(c.name == name for c in self.capabilities)

    def get(self, name: str) -> Capability | None:
        for c in self.capabilities:
            if c.name == name:
                return c
        return None

    def satisfies(self, required: CapabilitySet) -> bool:
        """Check if this set satisfies all required capabilities."""
        return all(self.has(r.name) for r in required.capabilities)

    def __or__(self, other: CapabilitySet) -> CapabilitySet:
        return CapabilitySet(self.capabilities | other.capabilities)

    def __and__(self, other: CapabilitySet) -> CapabilitySet:
        return CapabilitySet(self.capabilities & other.capabilities)

    def __iter__(self):
        return iter(self.capabilities)

    def __len__(self) -> int:
        return len(self.capabilities)

    def __bool__(self) -> bool:
        return bool(self.capabilities)


class SimulationEngine(ABC):
    """Protocol for simulation engines wrapped by adapters."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Unique identifier for this engine instance."""

    @property
    @abstractmethod
    def provides(self) -> CapabilitySet:
        """Capabilities this engine provides."""

    @property
    @abstractmethod
    def requires(self) -> CapabilitySet:
        """Capabilities this engine requires from others."""

    @property
    @abstractmethod
    def native_timestep(self) -> float:
        """Native timestep of this engine."""

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the engine with configuration."""

    @abstractmethod
    def step(self, dt: float) -> None:
        """Advance the engine by dt."""

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Get current engine state for cross-engine communication."""

    @abstractmethod
    def apply_event(self, event: Event) -> bool:
        """Apply an event from another engine. Returns True if handled."""

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up resources."""