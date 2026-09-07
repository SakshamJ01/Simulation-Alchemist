"""Base adapter class for simulation engines."""

from __future__ import annotations

from abc import ABC
from typing import Any

from sim_alchemist.core.capabilities import CapabilitySet, SimulationEngine
from sim_alchemist.core.events import Event, EventBus


class BaseAdapter(SimulationEngine, ABC):
    """Base class for all engine adapters."""

    def __init__(
        self,
        engine_id: str,
        provides: CapabilitySet | None = None,
        requires: CapabilitySet | None = None,
        native_timestep: float = 1.0,
    ) -> None:
        self._engine_id = engine_id
        self._provides = provides or CapabilitySet()
        self._requires = requires or CapabilitySet()
        self._native_timestep = native_timestep
        self._event_bus: EventBus | None = None
        self._initialized = False

        # Task 2.2 coupling metadata consumed by `core.contracts.resolve_contracts`.
        self._variant: str | None = None
        self._state_keys: tuple[str, ...] = ()
        self._grid: int | None = None
        self._coordinate_system: str = "unit-square-2d"

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def provides(self) -> CapabilitySet:
        return self._provides

    @property
    def requires(self) -> CapabilitySet:
        return self._requires

    @property
    def native_timestep(self) -> float:
        return self._native_timestep

    @property
    def variant(self) -> str | None:
        """Concrete variant of a dual-variant component id (e.g. walls/movers).

        ``None`` means the component id is unambiguous as composed.
        """
        return self._variant

    @property
    def state_keys(self) -> tuple[str, ...]:
        """State-vocabulary keys this adapter's surface can produce/consume.

        Payload keys of a declared coupling contract must belong to the
        producer's vocabulary (a documented limitation: adapters that declare
        no vocabulary skip the key check).
        """
        return self._state_keys

    @property
    def grid(self) -> int | None:
        """Field/geometry resolution (``None`` when not grid-structured)."""
        return self._grid

    @property
    def coordinate_system(self) -> str:
        """Coordinate system all capability outputs are expressed in."""
        return self._coordinate_system

    def set_event_bus(self, bus: EventBus) -> None:
        self._event_bus = bus

    def publish(self, event: Event) -> None:
        if self._event_bus:
            self._event_bus.publish(event)

    def get_state(self) -> dict[str, Any]:
        return {}

    def apply_event(self, event: Event) -> bool:
        return False

    def initialize(self, config: dict[str, Any]) -> None:
        self._initialized = True

    def step(self, dt: float) -> None:
        pass

    def shutdown(self) -> None:
        pass