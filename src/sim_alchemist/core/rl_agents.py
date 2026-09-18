"""Reinforcement Learning (RL) Simulation Environment and Policy Agents (Phase 4I).

Provides Gym-like environment wrappers for Alchemist simulations alongside
deterministic Tabular Q-Learning and REINFORCE Policy Gradient agents for
discovering optimal active control policies in multi-physics worlds.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class RLStepResult:
    """Outcome of an environment step."""

    observation: np.ndarray
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)


class SimulationGymEnvironment:
    """Standardized Gym-style environment wrapper for simulation engines."""

    def __init__(
        self,
        step_fn: Callable[[np.ndarray, int], tuple[np.ndarray, float, bool, dict[str, Any]]],
        reset_fn: Callable[[int | None], np.ndarray],
        observation_dim: int,
        action_dim: int,
        max_steps: int = 100,
    ) -> None:
        self.step_fn = step_fn
        self.reset_fn = reset_fn
        self.observation_dim = observation_dim
        self.action_dim = action_dim
        self.max_steps = max_steps
        self._current_step = 0

    def reset(self, seed: int | None = None) -> np.ndarray:
        self._current_step = 0
        return self.reset_fn(seed)

    def step(self, action: np.ndarray | int) -> RLStepResult:
        self._current_step += 1
        if isinstance(action, (int, np.integer)):
            act_arr = np.array([action], dtype=float)
        else:
            act_arr = np.asarray(action, dtype=float)

        obs, reward, done, info = self.step_fn(act_arr, self._current_step)
        truncated = self._current_step >= self.max_steps
        return RLStepResult(
            observation=np.asarray(obs, dtype=float),
            reward=float(reward),
            terminated=bool(done),
            truncated=bool(truncated),
            info=info,
        )


class QTableAgent:
    """Discretized Q-Learning agent with epsilon-greedy exploration."""

    def __init__(
        self,
        n_states: int,
        n_actions: int,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        epsilon: float = 0.2,
        seed: int = 42,
    ) -> None:
        self.n_states = n_states
        self.n_actions = n_actions
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        self.q_table = np.zeros((n_states, n_actions), dtype=float)

    def select_action(self, state: int) -> int:
        if self.rng.rand() < self.epsilon:
            return int(self.rng.randint(0, self.n_actions))
        return int(np.argmax(self.q_table[state]))

    def update(self, state: int, action: int, reward: float, next_state: int, done: bool) -> float:
        target = reward if done else reward + self.discount_factor * np.max(self.q_table[next_state])
        td_error = target - self.q_table[state, action]
        self.q_table[state, action] += self.learning_rate * td_error
        return float(td_error)


class PolicyGradientAgent:
    """REINFORCE Policy Gradient agent with softmax action selection."""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 0.01,
        gamma: float = 0.99,
        seed: int = 42,
    ) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.seed = seed
        self.rng = np.random.RandomState(seed)

        # Vectorized linear softmax policy weights: (state_dim, action_dim)
        self.weights = self.rng.randn(state_dim, action_dim) * 0.1
        self.saved_log_probs: list[np.ndarray] = []
        self.saved_states: list[np.ndarray] = []
        self.saved_actions: list[int] = []
        self.rewards: list[float] = []

    def get_action_probs(self, state: np.ndarray) -> np.ndarray:
        s = state.reshape(1, -1)
        logits = s @ self.weights
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)
        return probs.flatten()

    def select_action(self, state: np.ndarray) -> int:
        probs = self.get_action_probs(state)
        action = int(self.rng.choice(self.action_dim, p=probs))
        self.saved_states.append(state)
        self.saved_actions.append(action)
        return action

    def store_reward(self, reward: float) -> None:
        self.rewards.append(reward)

    def train_episode(self) -> float:
        """Perform REINFORCE policy update on stored trajectory."""
        if not self.rewards:
            return 0.0

        discounted_returns = []
        g = 0.0
        for r in reversed(self.rewards):
            g = r + self.gamma * g
            discounted_returns.insert(0, g)

        returns = np.array(discounted_returns)
        if len(returns) > 1 and np.std(returns) > 1e-8:
            returns = (returns - np.mean(returns)) / (np.std(returns) + 1e-8)

        total_loss = 0.0
        for s, a, ret in zip(self.saved_states, self.saved_actions, returns):
            probs = self.get_action_probs(s)
            grad_log = -probs
            grad_log[a] += 1.0  # d/dz log(softmax)

            # dL/dW = s.T @ grad_log * return
            dW = np.outer(s, grad_log) * ret
            self.weights += self.learning_rate * dW
            total_loss += float(-np.log(max(1e-8, probs[a])) * ret)

        # Clear trajectory
        self.saved_states.clear()
        self.saved_actions.clear()
        self.rewards.clear()
        return total_loss
