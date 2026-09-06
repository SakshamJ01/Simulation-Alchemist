"""Main Alchemist orchestration engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .capabilities import CapabilitySet, SimulationEngine
from .clock import SimulationClock
from .events import EventBus, EventType
from .scheduler import StepSchedule, StepScheduler
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
        engines: list[SimulationEngine] | None = None,
        macro_timestep: float = 0.2,
        max_steps: int = 160,
        seed: int = 0,
        config: dict[str, Any] | None = None,
    ) -> None:
        engines = engines or []
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

        # Composition state, populated by ``compose``/``compose_into`` via the
        # core composer (Task 1.3).  ``None`` until a world is installed.
        self._schedule: StepSchedule | None = None
        self._scheduler: StepScheduler | None = None
        self._composition_on_step: Callable[[float, float, int], None] | None = None
        self._on_initialize: Callable[[], None] | None = None

        # Subscribe engines to relevant events
        for engine in self.engines.values():
            self._subscribe_engine(engine)

    def _install(
        self,
        adapters: list[SimulationEngine],
        world: Any,
        operations: dict[str, Callable[[float], None]],
        *,
        on_step: Callable[[float, float, int], None] | None = None,
        on_initialize: Callable[[], None] | None = None,
    ) -> None:
        """Install a composed world: engines, clock, bus, scheduler, hooks.

        Called by the core composer (``compose``/``compose_into``) after
        capability resolution.  Rebuilds the clock and event bus from the
        installed adapters and validates the world's declared schedule against
        ``operations`` at install time.
        """
        self.engines = {e.engine_id: e for e in adapters}
        self._initialized = False
        self.clock = SimulationClock(
            macro_timestep=world.macro_timestep,
            native_timesteps={eid: e.native_timestep for eid, e in self.engines.items()},
            max_steps=world.max_steps,
        )
        self.event_bus = EventBus()
        self.world_state.seed = world.seed
        self.world_state.config = dict(world.config)
        for engine in self.engines.values():
            self._subscribe_engine(engine)
        self._composition_on_step = on_step
        self._on_initialize = on_initialize
        self._schedule = StepSchedule(list(world.schedule), operations)
        self._scheduler = StepScheduler(
            self._schedule,
            self.clock,
            world_state=self.world_state,
            on_step=on_step,
        )

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
        """Run the full simulation loop.

        Ordering is: initialize the installed adapters, run any composition
        initialize hook, validate capability resolution, then drive the core
        ``StepScheduler`` for the world's declared schedule.
        """
        if not self._initialized:
            self.initialize()
        if self._on_initialize is not None:
            self._on_initialize()

        composition = self.validate_composition()
        if not composition.valid:
            raise RuntimeError(f"Invalid composition: {composition.missing}")

        if self._scheduler is None:
            raise RuntimeError(
                "No schedule installed; compose this engine with compose()/compose_into() first"
            )
        self._scheduler.run()

        return self.world_state

    def _macro_step(self) -> None:
        """Execute one macro step by delegating to the core scheduler.

        The exact ordering is *declared* as a world schedule (validated at
        compose time) and dispatched by the core ``StepScheduler``; the science
        lives in the coupling operations supplied at composition.
        """
        if self._scheduler is None:  # pragma: no cover - guarded by run()
            raise RuntimeError("No schedule installed")
        self._scheduler.macro_step()

        self.world_state.time = self.clock.current_time
        self.world_state.step = self.clock.step_count