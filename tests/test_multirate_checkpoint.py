"""Tests for Multi-Rate Scheduling and Checkpoint / Restart (Phase 4 Slice 4.4)."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from sim_alchemist.core.checkpoint import (
    WorldCheckpoint,
    capture_checkpoint,
    restore_checkpoint,
)
from sim_alchemist.core.clock import SimulationClock
from sim_alchemist.core.scheduler import StepSchedule, StepScheduler


class MockEngine:
    def __init__(self, engine_id: str) -> None:
        self._engine_id = engine_id
        self.state: dict[str, object] = {"count": 0, "energy": 10.0}

    @property
    def engine_id(self) -> str:
        return self._engine_id

    def get_state(self) -> dict[str, object]:
        return dict(self.state)

    def initialize(self, config: dict[str, object]) -> None:
        self.state.update(config)


def test_multirate_step_scheduler() -> None:
    calls: list[tuple[str, float]] = []

    def op_slow(dt: float) -> None:
        calls.append(("slow", dt))

    def op_fast(dt: float) -> None:
        calls.append(("fast", dt))

    registry = {"slow": op_slow, "fast": op_fast}
    # fast runs 4 subcycles per macro-step
    schedule = StepSchedule(
        operations=[("slow", 1), ("fast", 4)],
        registry=registry,
    )
    clock = SimulationClock(macro_timestep=1.0, max_steps=2)
    scheduler = StepScheduler(schedule=schedule, clock=clock)

    scheduler.run()

    # In 2 macro steps:
    # 2 slow calls (dt=1.0)
    # 8 fast calls (dt=0.25)
    slow_calls = [c for c in calls if c[0] == "slow"]
    fast_calls = [c for c in calls if c[0] == "fast"]

    assert len(slow_calls) == 2
    assert slow_calls[0][1] == 1.0
    assert len(fast_calls) == 8
    assert pytest.approx(fast_calls[0][1]) == 0.25


def test_checkpoint_capture_save_load_restore() -> None:
    clock = SimulationClock(macro_timestep=1.0, max_steps=10)
    clock.next_macro_step()
    clock.next_macro_step()

    engine1 = MockEngine("eng1")
    engine1.state["count"] = 42

    engines = {"eng1": engine1}

    cp = capture_checkpoint(clock=clock, engines=engines, seed=12345, metadata={"tag": "midway"})
    assert cp.step == 2
    assert cp.time == 2.0
    assert cp.seed == 12345
    assert cp.component_states["eng1"]["count"] == 42
    assert cp.metadata["tag"] == "midway"

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir) / "checkpoint.json"
        cp.save(fpath)
        assert fpath.exists()

        loaded_cp = WorldCheckpoint.load(fpath)
        assert loaded_cp.step == 2
        assert loaded_cp.component_states["eng1"]["count"] == 42

        # Restore into fresh engine & clock
        fresh_clock = SimulationClock(macro_timestep=1.0, max_steps=10)
        fresh_engine = MockEngine("eng1")
        restore_checkpoint(loaded_cp, clock=fresh_clock, engines={"eng1": fresh_engine})


        assert fresh_clock.step_count == 2
        assert fresh_clock.current_time == 2.0
        assert fresh_engine.state["count"] == 42
