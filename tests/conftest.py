"""Shared session-scoped fixtures that run the validated world once for all tests.

The world runs mirror ``chemomech.validate`` exactly (n=32 grid, seed 0,
160 macro steps) so the pytest suite exercises the same scientific checks as
the script-based harnesses without recomputing the simulations per test.
"""

import pytest

from chemomech.simulation import Trajectory, WorldConfig
from chemomech.validate import build_agents, mechanical_response_test, run_experiments


@pytest.fixture(scope="session")
def experiments() -> dict[str, Trajectory]:
    """The four experiment trajectories: baseline, static, dynamic, replay."""
    base = WorldConfig(n=32, seed=0, n_steps=160, agent_configs=build_agents())
    return run_experiments(base)


@pytest.fixture(scope="session")
def machine_response() -> tuple[float, bool]:
    """Single-wall constant-force machine test: (distance moved, mask changed)."""
    return mechanical_response_test()