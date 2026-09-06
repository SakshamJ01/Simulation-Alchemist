"""Minimal deterministic step scheduler extracted from the two experiments.

Experiment A (chemo-mechanical morphogenesis) and Experiment B
(field-guided movers) each used to hard-code their own macro-step ordering
inside ``_macro_step``.  This module extracts only the *scheduling*
responsibility -- ordered execution, operation dispatch, macro-step
iteration, time progression, schedule validation, and tracing -- leaving
the science (PDE equations, Mesa behaviour, Pymunk physics, experiment
coupling rules) in the experiments.

What the scheduler OWNS:
    * deterministic, ordered execution
    * operation validation (unknown operations fail loudly)
    * macro-step iteration
    * simulation time progression (through ``SimulationClock``)
    * an in-memory execution trace for tests/debugging

What the scheduler does NOT own:
    * field equations
    * agent behaviour
    * physics formulas
    * wall-building rules / chemistry rules
    * experiment-specific coupling equations

Experiments declare an *explicit registry* mapping operation names to
handlers and an *ordered schedule* of those names.  The scheduler resolves
names through the registry and runs them in order.  No dynamic eval, no
dependency graph, no priority queues, no async.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .clock import SimulationClock


@dataclass(frozen=True)
class StepOperation:
    """A single named, typed, ordered step operation.

    ``name`` is a stable identifier resolved through an explicit registry;
    ``handler`` is the callable invoked, receiving the macro timestep ``dt``.
    """

    name: str
    handler: Callable[[float], None]


class StepSchedule:
    """An ordered, validated list of step operations.

    Declared as an ordered sequence of operation *names* resolved through an
    explicit ``registry`` (name -> handler).  Unknown/unregistered names raise
    a useful ``KeyError`` at construction so ordering mistakes are caught
    before any state is mutated.  Duplicates are allowed (they run in order,
    deterministically); an empty schedule runs nothing per macro step.
    """

    def __init__(
        self,
        operations: list[str],
        registry: dict[str, Callable[[float], None]],
    ) -> None:
        unknown = [name for name in operations if name not in registry]
        if unknown:
            available = ", ".join(sorted(registry)) or "(none registered)"
            raise KeyError(
                f"Unknown schedule operation(s): {', '.join(unknown)}. "
                f"Available operations: {available}"
            )
        self.operations: tuple[StepOperation, ...] = tuple(
            StepOperation(name=name, handler=registry[name]) for name in operations
        )
        self.schedule_names: tuple[str, ...] = tuple(operations)

    def __len__(self) -> int:
        return len(self.operations)

    def names(self) -> list[str]:
        """The declared, ordered operation names (inspectable)."""
        return list(self.schedule_names)


@dataclass(frozen=True)
class TraceEntry:
    """One recorded execution step: time, step index, operation name."""

    time: float
    step: int
    operation: str


class ExecutionTrace:
    """A lightweight, in-memory execution trace for tests and debugging.

    Not a logging framework -- just an ordered list of ``TraceEntry`` objects
    recording which operation ran at which simulated time/step.
    """

    def __init__(self) -> None:
        self._entries: list[TraceEntry] = []

    def record(self, time: float, step: int, operation: str) -> None:
        self._entries.append(TraceEntry(time, step, operation))

    def clear(self) -> None:
        self._entries.clear()

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def operations(self) -> list[str]:
        return [e.operation for e in self._entries]


class StepScheduler:
    """Owns deterministic ordering, dispatch, time progression, and tracing.

    A schedule runs macro step after macro step; each macro step advances the
    shared ``SimulationClock``, then invokes every operation in the declared
    order.  Time/trace semantics match the pre-refactor loops exactly.
    """

    def __init__(
        self,
        schedule: StepSchedule,
        clock: SimulationClock,
        world_state: Any | None = None,
        on_step: Callable[[float, float, int], None] | None = None,
        trace: ExecutionTrace | None = None,
    ) -> None:
        self.schedule = schedule
        self.clock = clock
        self.world_state = world_state
        self.on_step = on_step
        self.trace = trace if trace is not None else ExecutionTrace()

    @property
    def is_finished(self) -> bool:
        return self.clock.is_finished

    def macro_step(self) -> None:
        """Advance time and run every operation in the declared order."""
        dt = self.clock.next_macro_step()
        if self.world_state is not None:
            self.world_state.time = self.clock.current_time
            self.world_state.step = self.clock.step_count
        if self.on_step is not None:
            self.on_step(self.clock.current_time, dt, self.clock.step_count)
        for op in self.schedule.operations:
            self.trace.record(self.clock.current_time, self.clock.step_count, op.name)
            op.handler(dt)

    def run(self) -> ExecutionTrace:
        """Run the full macro-step loop until the clock is finished."""
        while not self.is_finished:
            self.macro_step()
        return self.trace
