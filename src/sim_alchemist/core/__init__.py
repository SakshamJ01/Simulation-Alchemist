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
from .lineage import LineageStore, RunRecord, run_id_of, world_hash
from .mutation import (
    InvalidMutationValueError,
    Mutation,
    MutationError,
    MutationRecord,
    ParameterSpec,
    UnknownMutationPathError,
    apply_mutation,
    apply_mutations,
    clone_world,
    one_of,
    range_validator,
)
from .registry import AdapterFactory, ComponentRegistry, default_registry
from .runner import (
    ExecOutcome,
    MetricDelta,
    MissingParentRunError,
    RunResult,
    VariantRunner,
    compare_metrics,
    compare_runs,
)
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
    "ExecOutcome",
    "ExecutionTrace",
    "InvalidMutationValueError",
    "LineageStore",
    "MetricDelta",
    "MissingParentRunError",
    "Mutation",
    "MutationError",
    "MutationRecord",
    "ParameterSpec",
    "RunRecord",
    "RunResult",
    "SimulationClock",
    "SimulationEngine",
    "StepOperation",
    "StepSchedule",
    "StepScheduler",
    "UnknownComponentError",
    "UnknownMutationPathError",
    "UnresolvedCapabilityError",
    "VariantRunner",
    "WorldDefinition",
    "WorldState",
    "apply_mutation",
    "apply_mutations",
    "build_components",
    "clone_world",
    "compare_metrics",
    "compare_runs",
    "compose",
    "compose_into",
    "default_registry",
    "load_world_yaml",
    "one_of",
    "range_validator",
    "resolve_capabilities",
    "run_id_of",
    "world_hash",
]
