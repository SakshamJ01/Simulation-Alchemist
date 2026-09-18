"""Tests for RL Gym Environment and Autonomous Agents (Phase 4I)."""

from __future__ import annotations

import numpy as np

from sim_alchemist.core.rl_agents import (
    PolicyGradientAgent,
    QTableAgent,
    SimulationGymEnvironment,
)


def test_gym_environment_step_and_reset() -> None:
    def dummy_step(action: np.ndarray, step_num: int) -> tuple[np.ndarray, float, bool, dict]:
        obs = np.array([float(step_num), action[0]])
        reward = 1.0 if action[0] > 0 else -1.0
        done = step_num >= 10
        return obs, reward, done, {"step": step_num}

    def dummy_reset(seed: int | None = None) -> np.ndarray:
        return np.array([0.0, 0.0])

    env = SimulationGymEnvironment(
        step_fn=dummy_step,
        reset_fn=dummy_reset,
        observation_dim=2,
        action_dim=2,
        max_steps=10,
    )

    init_obs = env.reset()
    assert np.array_equal(init_obs, np.array([0.0, 0.0]))

    res = env.step(1)
    assert res.observation.shape == (2,)
    assert res.reward == 1.0
    assert not res.terminated

    # Step until truncated/terminated
    for _ in range(9):
        res = env.step(1)
    assert res.terminated or res.truncated


def test_q_table_agent() -> None:
    agent = QTableAgent(n_states=5, n_actions=2, learning_rate=0.1, epsilon=0.0, seed=42)
    action = agent.select_action(state=0)
    assert action in (0, 1)

    td_err = agent.update(state=0, action=0, reward=10.0, next_state=1, done=False)
    assert td_err > 0.0
    assert agent.q_table[0, 0] > 0.0


def test_policy_gradient_agent() -> None:
    agent = PolicyGradientAgent(state_dim=3, action_dim=2, learning_rate=0.05, seed=42)
    s0 = np.array([1.0, 0.5, -0.5])
    a0 = agent.select_action(s0)
    assert a0 in (0, 1)

    agent.store_reward(1.0)
    loss = agent.train_episode()
    assert isinstance(loss, float)
    assert len(agent.saved_states) == 0  # Cleared after training
