"""Main Alchemist orchestration engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .capabilities import CapabilitySet, SimulationEngine
from .clock import SimulationClock
from .events import Event, EventBus, EventType
from .state import WorldState


@dataclass
class CompositionResult:
    """Result of a composition validation."""
    valid: bool
    missing: CapabilitySet = field(default_factory=CapabilitySet)
    conflicts: list[str] = field(default_factory=list)


class CapabilityResolver:
    """Minimal capability resolver for the current experiment."""

    def resolve(self, engines: list[SimulationEngine]) -> CompositionResult:
        """Check if engines can compose for the current experiment."""
        all_provided = CapabilitySet()
        all_required = CapabilitySet()

        for engine in engines:
            all_provided = all_provided | engine.provides
            all_required = all_required | engine.requires

        missing = CapabilitySet()
        for req in all_required:
            if not all_provided.has(req.name):
                missing.add(req)

        return CompositionResult(
            valid=len(missing) == 0,
            missing=missing,
        )


class AlchemistEngine:
    """
    Main orchestration engine.

    Coordinates multiple simulation engines through a deterministic
    macro-step loop with typed event communication.
    """

    def __init__(
        self,
        engines: list[SimulationEngine],
        macro_timestep: float = 0.2,
        max_steps: int = 160,
        seed: int = 0,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.engines = {e.engine_id: e for e in engines}
        self.clock = SimulationClock(
            macro_timestep=macro_timestep,
            native_timesteps={eid: e.native_timestep for eid, e in self.engines.items()},
            max_steps=max_steps,
        )
        self.event_bus = EventBus()
        self.world_state = WorldState(seed=seed, config=config or {})
        self.resolver = CapabilityResolver()
        self._initialized = False

        # Subscribe engines to relevant events
        for engine in self.engines.values():
            self._subscribe_engine(engine)

    def _subscribe_engine(self, engine: SimulationEngine) -> None:
        """Subscribe engine to events it cares about."""
        # All engines get time step events
        self.event_bus.subscribe(EventType.TIME_STEP, engine.apply_event, engine.engine_id)

    def validate_composition(self) -> CompositionResult:
        """Validate that all engines can work together."""
        return self.resolver.resolve(list(self.engines.values()))

    def initialize(self) -> None:
        """Initialize all engines."""
        for engine in self.engines.values():
            engine.initialize(self.world_state.config)
        self._initialized = True

    def run(self) -> WorldState:
        """Run the full simulation loop."""
        if not self._initialized:
            self.initialize()

        composition = self.validate_composition()
        if not composition.valid:
            raise RuntimeError(f"Invalid composition: {composition.missing}")

        while not self.clock.is_finished:
            self._macro_step()

        return self.world_state

    def _macro_step(self) -> None:
        """Execute one macro step with the exact ordering from the baseline."""
        dt = self.clock.next_macro_step()

        # Emit time step event
        time_event = Event.time_step("alchemist", self.clock.current_time, dt)
        self.event_bus.publish(time_event)

        # The ordering is critical and must match the baseline:
        # 1. PDE adapter reads geometry from Pymunk, advances field
        # 2. Pymunk adapter applies forces from field gradients
        # 3. Pymunk adapter steps physics
        # 4. Mesa adapter senses field, emits decisions
        # 5. Alchemist translates decisions to wall operations
        # 6. Geometry updates fed back to PDE

        # This ordering is implemented by the adapters' step() methods
        # being called in the correct sequence by the concrete engine.
        # The base engine provides the clock and event bus; the
        # concrete ChemomechanicalEngine defines the exact ordering.

        self.world_state.time = self.clock.current_time
        self.world_state.step = self.clock.step_count