"""Typed event model for cross-engine communication."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    """Event types for the chemo-mechanical loop."""
    FIELD_STATE = "field_state"
    FIELD_GRADIENT = "field_gradient"
    WALL_ADD = "wall_add"
    WALL_REMOVE = "wall_remove"
    FIELD_FORCE = "field_force"
    GEOMETRY_UPDATE = "geometry_update"
    AGENT_DECISION = "agent_decision"
    TIME_STEP = "time_step"


@dataclass(frozen=True)
class Event:
    """Typed event for cross-engine communication."""
    type: EventType
    source: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def field_state(cls, source: str, timestamp: float, field_data: dict[str, Any]) -> Event:
        return cls(EventType.FIELD_STATE, source, timestamp, field_data)

    @classmethod
    def field_gradient(cls, source: str, timestamp: float, gradients: dict[str, Any]) -> Event:
        return cls(EventType.FIELD_GRADIENT, source, timestamp, gradients)

    @classmethod
    def wall_add(cls, source: str, timestamp: float, wall_data: dict[str, Any]) -> Event:
        return cls(EventType.WALL_ADD, source, timestamp, wall_data)

    @classmethod
    def wall_remove(cls, source: str, timestamp: float, wall_ids: list[int]) -> Event:
        return cls(EventType.WALL_REMOVE, source, timestamp, {"wall_ids": wall_ids})

    @classmethod
    def field_force(cls, source: str, timestamp: float, forces: dict[int, tuple[float, float]]) -> Event:
        return cls(EventType.FIELD_FORCE, source, timestamp, {"forces": forces})

    @classmethod
    def geometry_update(cls, source: str, timestamp: float, geometry: dict[str, Any]) -> Event:
        return cls(EventType.GEOMETRY_UPDATE, source, timestamp, geometry)

    @classmethod
    def agent_decision(cls, source: str, timestamp: float, decisions: dict[str, Any]) -> Event:
        return cls(EventType.AGENT_DECISION, source, timestamp, decisions)

    @classmethod
    def time_step(cls, source: str, timestamp: float, dt: float) -> Event:
        return cls(EventType.TIME_STEP, source, timestamp, {"dt": dt})


class EventBus:
    """In-process event bus for engine communication."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[tuple[str, callable]]] = {}

    def subscribe(self, event_type: EventType, handler: callable, engine_id: str) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append((engine_id, handler))

    def publish(self, event: Event) -> list[Any]:
        results = []
        for event_type, handlers in self._subscribers.items():
            if event_type == event.type or event_type == EventType.TIME_STEP:
                for engine_id, handler in handlers:
                    if engine_id != event.source:
                        try:
                            result = handler(event)
                            results.append(result)
                        except Exception:  # noqa: BLE001,S110 - intentional catch-all for event bus
                            pass  # Event handling failures shouldn't break the bus
        return results