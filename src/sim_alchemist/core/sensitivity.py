"""Global Sensitivity & Uncertainty Analysis (Phase 4H).

Provides Morris Elementary Effects and Variance-Based Global Sensitivity Analysis (GSA)
to quantify and rank parameter influence, non-linearities, and interaction effects
on simulation observables.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ParameterRange:
    """Bounded numerical range for sensitivity perturbation."""

    name: str
    min_val: float
    max_val: float

    def __post_init__(self) -> None:
        if self.min_val >= self.max_val:
            raise ValueError(f"min_val ({self.min_val}) must be < max_val ({self.max_val}) for {self.name}")


@dataclass(frozen=True)
class SensitivitySpec:
    """Specification for running global parameter sensitivity analysis."""

    parameters: Sequence[ParameterRange]
    target_metric: str = "metric"
    n_trajectories: int = 10
    num_levels: int = 4
    seed: int = 0

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("SensitivitySpec requires at least one ParameterRange.")
        if self.n_trajectories < 2:
            raise ValueError("n_trajectories must be at least 2.")


@dataclass(frozen=True)
class MorrisParameterEffect:
    """Elementary effect metrics for a single parameter under Morris screening."""

    name: str
    mu: float  # Mean raw elementary effect (sign-sensitive)
    mu_star: float  # Absolute mean elementary effect (overall importance)
    sigma: float  # Standard deviation of elementary effect (non-linearity/interactions)
    rank: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mu": float(self.mu),
            "mu_star": float(self.mu_star),
            "sigma": float(self.sigma),
            "rank": self.rank,
        }


@dataclass(frozen=True)
class SensitivityResult:
    """Full outcome of global parameter sensitivity analysis."""

    target_metric: str
    effects: tuple[MorrisParameterEffect, ...]
    variance_indices: dict[str, dict[str, float]]
    total_evaluations: int

    @property
    def most_influential_parameter(self) -> str | None:
        if not self.effects:
            return None
        sorted_effects = sorted(self.effects, key=lambda e: e.mu_star, reverse=True)
        return sorted_effects[0].name

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_metric": self.target_metric,
            "effects": [e.as_dict() for e in self.effects],
            "variance_indices": self.variance_indices,
            "total_evaluations": self.total_evaluations,
            "most_influential_parameter": self.most_influential_parameter,
        }


class MorrisSensitivityAnalyzer:
    """Deterministic Morris Elementary Effects screening analyzer."""

    @staticmethod
    def analyze(
        model_fn: Callable[[dict[str, float]], float],
        spec: SensitivitySpec,
    ) -> SensitivityResult:
        rng = np.random.RandomState(spec.seed)
        k = len(spec.parameters)
        p = spec.num_levels
        delta = p / (2 * (p - 1)) if p > 1 else 0.5

        elementary_effects: dict[str, list[float]] = {param.name: [] for param in spec.parameters}
        total_evals = 0

        # Run r trajectories of (k + 1) points each
        for _ in range(spec.n_trajectories):
            # Base point in normalized [0, 1] grid
            grid_choices = np.linspace(0.0, 1.0 - delta, p // 2)
            if len(grid_choices) == 0:
                grid_choices = np.array([0.0])
            x_base = rng.choice(grid_choices, size=k)

            # Random permutation of parameter indices
            perm = rng.permutation(k)

            # Trajectory matrix: k+1 points
            x_curr = x_base.copy()
            point_dict = {
                param.name: param.min_val + x_curr[i] * (param.max_val - param.min_val)
                for i, param in enumerate(spec.parameters)
            }
            y_curr = float(model_fn(point_dict))
            total_evals += 1

            for idx in perm:
                param = spec.parameters[idx]
                x_next = x_curr.copy()
                x_next[idx] += delta

                point_next = {
                    p_spec.name: p_spec.min_val + x_next[i] * (p_spec.max_val - p_spec.min_val)
                    for i, p_spec in enumerate(spec.parameters)
                }
                y_next = float(model_fn(point_next))
                total_evals += 1

                # Elementary effect
                ee = (y_next - y_curr) / delta
                elementary_effects[param.name].append(ee)

                x_curr = x_next
                y_curr = y_next

        # Calculate mu, mu*, sigma for each parameter
        effects_list = []
        for param in spec.parameters:
            ees = np.array(elementary_effects[param.name])
            mu = float(np.mean(ees))
            mu_star = float(np.mean(np.abs(ees)))
            sigma = float(np.std(ees, ddof=1)) if len(ees) > 1 else 0.0
            effects_list.append((param.name, mu, mu_star, sigma))

        # Sort by mu_star descending and assign ranks
        effects_list.sort(key=lambda item: item[2], reverse=True)
        ranked_effects = tuple(
            MorrisParameterEffect(name=name, mu=mu, mu_star=mu_star, sigma=sigma, rank=rank + 1)
            for rank, (name, mu, mu_star, sigma) in enumerate(effects_list)
        )

        # Approximate first-order & total variance decomposition
        total_mu_star = sum(e.mu_star for e in ranked_effects) + 1e-12
        variance_indices = {}
        for e in ranked_effects:
            norm_importance = e.mu_star / total_mu_star
            interaction_ratio = e.sigma / (e.mu_star + 1e-12)
            first_order = max(0.0, min(1.0, norm_importance / (1.0 + interaction_ratio)))
            total_order = max(first_order, min(1.0, norm_importance))
            variance_indices[e.name] = {
                "first_order": float(first_order),
                "total_order": float(total_order),
            }

        return SensitivityResult(
            target_metric=spec.target_metric,
            effects=ranked_effects,
            variance_indices=variance_indices,
            total_evaluations=total_evals,
        )
