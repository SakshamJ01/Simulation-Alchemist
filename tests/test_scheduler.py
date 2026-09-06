"""Task 1.2 validation: minimal declarative step scheduler (checks A-G).

Proves the scheduling responsibility extracted into ``sim_alchemist/core/
scheduler.py``: ordered, deterministic execution of experiment-declared
operation lists, with time progression, operation validation, tracing, and a
core that knows nothing about any specific experiment's operations.
"""

import pathlib

import numpy as np
import pytest

from chemomech.engine import ChemomechanicalEngine
from chemomech.simulation import WorldConfig
from experiments.field_guided_movers.model import (
    FieldGuidedMoversEngine,
    MoversConfig,
    run_field_guided_movers,
)
from sim_alchemist.core.clock import SimulationClock
from sim_alchemist.core.scheduler import (
    ExecutionTrace,
    StepSchedule,
    StepScheduler,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "src" / "sim_alchemist" / "core"


def make_clock(max_steps: int = 3, macro_timestep: float = 0.2) -> SimulationClock:
    return SimulationClock(macro_timestep=macro_timestep, max_steps=max_steps)


# A. Ordered execution
# ----------------------------------------------------------------------
def test_operations_run_in_declared_order() -> None:
    calls: list[str] = []
    registry = {
        "first": lambda dt: calls.append("first"),
        "second": lambda dt: calls.append("second"),
        "third": lambda dt: calls.append("third"),
    }
    schedule = StepSchedule(["first", "second", "third"], registry)
    trace = StepScheduler(schedule, make_clock(max_steps=1)).run()

    assert calls == ["first", "second", "third"]
    assert trace.operations() == ["first", "second", "third"]


def test_handlers_receive_the_macro_timestep() -> None:
    received: list[float] = []
    registry = {
        "op": lambda dt: received.append(dt),
    }
    schedule = StepSchedule(["op"], registry)
    StepScheduler(schedule, make_clock(max_steps=1, macro_timestep=0.5)).run()
    assert received == [0.5]


# B. Operation validation — unknown operations fail loudly
# ----------------------------------------------------------------------
def test_unknown_operation_raises_helpful_error() -> None:
    with pytest.raises(KeyError) as exc:
        StepSchedule(["geometry.sync", "nope.missing"], {"geometry.sync": lambda dt: None})
    message = str(exc.value)
    assert "nope.missing" in message
    assert "geometry.sync" in message


def test_schedule_construction_never_mutates_state() -> None:
    # Validation happens at construction, before any operation runs.
    calls: list[str] = []
    registry = {"a": lambda dt: calls.append("a")}
    with pytest.raises(KeyError):
        StepSchedule(["a", "b"], registry)
    assert calls == []


# C. Empty schedule
# ----------------------------------------------------------------------
def test_empty_schedule_runs_nothing_but_time_advances() -> None:
    clock = make_clock(max_steps=3)
    schedule = StepSchedule([], {})
    trace = StepScheduler(schedule, clock).run()

    assert len(schedule) == 0
    assert len(trace) == 0
    assert clock.step_count == 3
    assert clock.current_time == pytest.approx(0.6)


# D. Duplicates run in order, deterministically
# ----------------------------------------------------------------------
def test_duplicate_operations_are_allowed_and_run_in_order() -> None:
    calls: list[str] = []
    registry = {
        "draw": lambda dt: calls.append("draw"),
        "record": lambda dt: calls.append("record"),
    }
    schedule = StepSchedule(["draw", "record", "draw", "draw", "record"], registry)
    StepScheduler(schedule, make_clock(max_steps=1)).run()
    assert calls == ["draw", "record", "draw", "draw", "record"]


# E. Time advancement — scheduler drives the clock and world state
# ----------------------------------------------------------------------
def test_scheduler_advances_clock_and_world_state() -> None:
    clock = make_clock(max_steps=2, macro_timestep=0.5)
    seen: list[tuple[float, int]] = []

    class FakeState:
        time = 0.0
        step = 0

    world = FakeState()
    schedule = StepSchedule(
        ["op"],
        {"op": lambda dt: seen.append((clock.current_time, clock.step_count))},
    )
    StepScheduler(schedule, clock, world_state=world).run()

    assert clock.current_time == pytest.approx(1.0)
    assert clock.step_count == 2
    assert world.time == pytest.approx(1.0)
    assert world.step == 2
    # operations observe the *current* (post-advance) time/step
    assert [(t, s) for t, s in seen] == [(0.5, 1), (1.0, 2)]


def test_on_step_hook_receives_time_dt_and_step() -> None:
    hook: list[tuple[float, float, int]] = []
    registry = {"op": lambda dt: None}
    schedule = StepSchedule(["op"], registry)
    clock = make_clock(max_steps=2, macro_timestep=0.5)

    def on_step(time: float, dt: float, step: int) -> None:
        hook.append((time, dt, step))

    StepScheduler(schedule, clock, on_step=on_step).run()
    assert hook == [(0.5, 0.5, 1), (1.0, 0.5, 2)]


# F. Different schedules for A and B
# ----------------------------------------------------------------------
def test_experiments_declare_different_schedules() -> None:
    a_schedule = ChemomechanicalEngine.SCHEDULE
    b_schedule = FieldGuidedMoversEngine.SCHEDULE

    assert a_schedule != b_schedule
    assert a_schedule == (
        "geometry.sync",
        "field.step",
        "physics.force",
        "physics.step",
        "agents.step",
        "agents.apply",
        "observables.record",
    )
    assert b_schedule == (
        "field.step",
        "movers.force",
        "movers.step",
        "field.source",
        "observables.record",
    )


def test_each_engine_runs_exactly_its_declared_order() -> None:
    cfg = MoversConfig(n_steps=2)
    engine_b = FieldGuidedMoversEngine(config=cfg)
    engine_b.run()
    assert engine_b._scheduler is not None
    b_ops = engine_b._scheduler.trace.operations()
    assert b_ops == list(engine_b.SCHEDULE) * cfg.n_steps

    world = WorldConfig(n=16, n_steps=2)
    engine_a = ChemomechanicalEngine(config=world)
    engine_a.run()
    assert engine_a._scheduler is not None
    a_ops = engine_a._scheduler.trace.operations()
    assert a_ops == list(engine_a.SCHEDULE) * world.n_steps


# G. Deterministic replay — same schedule + same seed = same trace
# ----------------------------------------------------------------------
def test_identical_schedules_reproduce_identical_traces() -> None:
    def build() -> ExecutionTrace:
        calls: list[str] = []
        registry = {
            "a": lambda dt: calls.append("a"),
            "b": lambda dt: calls.append("b"),
        }
        schedule = StepSchedule(["a", "b", "a"], registry)
        trace = StepScheduler(schedule, make_clock(max_steps=4)).run()
        return trace

    trace1, trace2 = build(), build()
    assert trace1.operations() == trace2.operations()
    assert [(e.time, e.step, e.operation) for e in trace1] == [
        (e.time, e.step, e.operation) for e in trace2
    ]


def test_experiment_b_replay_produces_identical_trace_and_field() -> None:
    def run() -> tuple[ExecutionTrace, np.ndarray]:
        traj = run_field_guided_movers(MoversConfig(seed=123, n_steps=12))
        return traj.engine_trace(), traj.final_u

    t1, u1 = run()
    t2, u2 = run()
    assert t1.operations() == t2.operations()
    assert np.array_equal(u1, u2)


# Ordering is experiment configuration, not core logic
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "declared_order, expected",
    [
        (["a", "b", "c"], ["a", "b", "c"]),
        (["c", "a", "b"], ["c", "a", "b"]),
        (["b", "b", "a"], ["b", "b", "a"]),
    ],
)
def test_declared_order_is_just_data(declared_order: list[str], expected: list[str]) -> None:
    calls: list[str] = []
    registry = {
        "a": lambda dt: calls.append("a"),
        "b": lambda dt: calls.append("b"),
        "c": lambda dt: calls.append("c"),
    }
    schedule = StepSchedule(declared_order, registry)
    trace = StepScheduler(schedule, make_clock(max_steps=1)).run()
    assert calls == expected
    assert trace.operations() == expected


def test_reordering_experiment_a_ops_changes_observed_order_without_core_change() -> None:
    # Synthetic proof: swapping the experiment's declared order changes which
    # handler runs first/second, with the core scheduler module untouched.
    original = ChemomechanicalEngine.SCHEDULE
    first, *rest, last = original
    reordered = (last,) + tuple(rest[:-1]) + (first,)

    def capture(order: tuple[str, ...]) -> list[str]:
        calls: list[str] = []
        registry = {name: (lambda dt, n=name: calls.append(n)) for name in original}
        schedule = StepSchedule(list(order), registry)
        StepScheduler(schedule, make_clock(max_steps=1)).run()
        return calls

    normal = capture(original)
    swapped = capture(reordered)
    assert normal == list(original)
    assert swapped == list(reordered)
    assert swapped != normal


def test_core_knows_no_experiment_operation_names() -> None:
    experiment_ops = {
        "geometry.sync",
        "field.step",
        "physics.force",
        "physics.step",
        "agents.step",
        "agents.apply",
        "movers.force",
        "movers.step",
        "field.source",
    }
    core_source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(CORE_DIR.glob("*.py"))
        if p.name != "scheduler.py"
    )
    scheduler_source = (CORE_DIR / "scheduler.py").read_text(encoding="utf-8")

    assert "geometry.sync" not in scheduler_source
    assert "movers.force" not in scheduler_source
    assert not any(op in core_source for op in experiment_ops)