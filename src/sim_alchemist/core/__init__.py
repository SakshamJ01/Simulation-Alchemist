"""Core package exports."""

from .capabilities import Capability, CapabilitySet, SimulationEngine
from .clock import SimulationClock
from .composer import (
    CompositionError,
    UnknownComponentError,
    UnresolvedCapabilityError,
    build_components,
    compose,
    compose_into,
    resolve_capabilities,
)
from .engine import AlchemistEngine, CapabilityResolver, CompositionResult
from .events import Event, EventBus, EventType
from .registry import AdapterFactory, ComponentRegistry, default_registry
from .scheduler import ExecutionTrace, StepOperation, StepSchedule, StepScheduler
from .state import WorldState
from .world import ComponentSpec, WorldDefinition, load_world_yaml

__all__ = [
    "AdapterFactory",
    "AlchemistEngine",
    "Capability",
    "CapabilityResolver",
    "CapabilitySet",
    "ComponentRegistry",
    "ComponentSpec",
    "CompositionError",
    "CompositionResult",
    "Event",
    "EventBus",
    "EventType",
    "ExecutionTrace",
    "SimulationClock",
    "SimulationEngine",
    "StepOperation",
    "StepSchedule",
    "StepScheduler",
    "UnknownComponentError",
    "UnresolvedCapabilityError",
    "WorldDefinition",
    "WorldState",
    "build_components",
    "compose",
    "compose_into",
    "default_registry",
    "load_world_yaml",
    "resolve_capabilities",
]
