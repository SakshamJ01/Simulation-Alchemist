"""Intelligent Multi-Objective Search & Surrogate Optimization Engine (Phase 4I).

Provides deterministic Gaussian/RBF surrogate modeling, Expected Improvement & UCB
acquisition functions, and NSGA-II Pareto multi-objective search to guide parameter
exploration over coupled simulations without black-box opacity or external ML dependencies.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class SearchParameterRange:
    """Bounded parameter range for surrogate optimization."""

    name: str
    min_val: float
    max_val: float

    def __post_init__(self) -> None:
        if self.min_val >= self.max_val:
            raise ValueError(f"min_val ({self.min_val}) must be < max_val ({self.max_val}) for {self.name}")


@runtime_checkable
class SurrogateModel(Protocol):
    """Protocol for deterministic predictive surrogates."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit surrogate model to observed parameter matrix X and scalar target y."""
        ...

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (mean_predictions, uncertainty_stds) for test points X."""
        ...


class RBFGaussianSurrogate:
    """Deterministic Gaussian Radial Basis Function (RBF) surrogate with ridge regularization."""

    def __init__(self, gamma: float = 1.0, ridge_lambda: float = 1e-4) -> None:
        self.gamma = gamma
        self.ridge_lambda = ridge_lambda
        self._X_train: np.ndarray | None = None
        self._weights: np.ndarray | None = None
        self._K_inv: np.ndarray | None = None
        self._y_mean: float = 0.0
        self._y_std: float = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        if len(X) != len(y):
            raise ValueError("X and y must have the same number of samples.")
        if len(X) == 0:
            raise ValueError("Cannot fit surrogate on empty dataset.")

        self._X_train = np.copy(X)
        self._y_mean = float(np.mean(y))
        self._y_std = float(np.std(y)) if float(np.std(y)) > 1e-8 else 1.0
        y_norm = (y - self._y_mean) / self._y_std

        # Pairwise squared Euclidean distances
        dists_sq = np.sum((self._X_train[:, np.newaxis, :] - self._X_train[np.newaxis, :, :]) ** 2, axis=-1)
        K = np.exp(-self.gamma * dists_sq)
        K_reg = K + self.ridge_lambda * np.eye(len(X))

        self._K_inv = np.linalg.pinv(K_reg)
        self._weights = self._K_inv @ y_norm

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self._X_train is None or self._weights is None or self._K_inv is None:
            raise RuntimeError("Surrogate model must be fit before predict().")

        dists_sq = np.sum((X[:, np.newaxis, :] - self._X_train[np.newaxis, :, :]) ** 2, axis=-1)
        K_cross = np.exp(-self.gamma * dists_sq)

        # Mean prediction
        y_norm_pred = K_cross @ self._weights
        mu = y_norm_pred * self._y_std + self._y_mean

        # Epistemic uncertainty estimation
        var_norm = 1.0 - np.sum(K_cross @ self._K_inv * K_cross, axis=1)
        var_norm = np.maximum(1e-6, var_norm)
        sigma = np.sqrt(var_norm) * self._y_std

        return mu, sigma


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * (x**2))


@dataclass(frozen=True)
class AcquisitionScorer:
    """Computes exploration/exploitation acquisition scores."""

    strategy: str = "UCB"  # "UCB" or "EI"
    kappa: float = 2.0  # UCB exploration parameter
    xi: float = 0.01  # EI exploration parameter

    def score(self, mu: float, sigma: float, best_y: float, direction: str = "maximize") -> float:
        if direction == "minimize":
            mu = -mu
            best_y = -best_y

        if self.strategy == "UCB":
            return mu + self.kappa * sigma

        # Expected Improvement (EI)
        if sigma <= 1e-8:
            return max(0.0, mu - best_y)
        improvement = mu - best_y - self.xi
        z = improvement / sigma
        ei = improvement * normal_cdf(z) + sigma * normal_pdf(z)
        return max(0.0, float(ei))


@dataclass(frozen=True)
class IntelligentCandidate:
    """Individual candidate sampled or predicted during intelligent search."""

    candidate_id: str
    iteration: int
    parameters: dict[str, float]
    actual_metrics: dict[str, float]
    predicted_metrics: dict[str, float] = field(default_factory=dict)
    predicted_uncertainty: dict[str, float] = field(default_factory=dict)
    acquisition_score: float = 0.0
    pareto_rank: int = 1
    crowding_distance: float = 0.0
    surrogate_predicted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "iteration": self.iteration,
            "parameters": self.parameters,
            "actual_metrics": self.actual_metrics,
            "predicted_metrics": self.predicted_metrics,
            "predicted_uncertainty": self.predicted_uncertainty,
            "acquisition_score": float(self.acquisition_score),
            "pareto_rank": self.pareto_rank,
            "crowding_distance": float(self.crowding_distance),
            "surrogate_predicted": self.surrogate_predicted,
        }


@dataclass(frozen=True)
class IntelligentSearchSpec:
    """Specification for running surrogate-guided multi-objective optimization."""

    name: str
    parameter_ranges: Sequence[SearchParameterRange]
    target_objectives: tuple[tuple[str, str], ...] = (("metric", "maximize"),)
    n_initial_samples: int = 4
    n_iterations: int = 3
    candidates_per_iter: int = 2
    grid_resolution_per_dim: int = 5
    acquisition_strategy: str = "UCB"
    exploration_weight: float = 2.0
    seed: int = 0

    def __post_init__(self) -> None:
        if not self.parameter_ranges:
            raise ValueError("IntelligentSearchSpec requires at least one SearchParameterRange.")
        if not self.target_objectives:
            raise ValueError("IntelligentSearchSpec requires at least one target objective.")


@dataclass(frozen=True)
class IntelligentSearchResult:
    """Complete outcome of intelligent multi-objective search."""

    spec: IntelligentSearchSpec
    all_evaluated: tuple[IntelligentCandidate, ...]
    pareto_frontier: tuple[IntelligentCandidate, ...]
    surrogate_models: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec_name": self.spec.name,
            "total_evaluated": len(self.all_evaluated),
            "pareto_frontier_count": len(self.pareto_frontier),
            "all_evaluated": [c.as_dict() for c in self.all_evaluated],
            "pareto_frontier": [c.as_dict() for c in self.pareto_frontier],
        }


class NSGA2FrontierSelector:
    """Deterministic Non-Dominated Sorting & Crowding Distance ranking."""

    @staticmethod
    def dominates(
        c1: IntelligentCandidate, c2: IntelligentCandidate, objectives: Sequence[tuple[str, str]]
    ) -> bool:
        """Return True if c1 dominates c2 across all objectives."""
        at_least_as_good = True
        strictly_better = False

        for metric_name, direction in objectives:
            val1 = c1.actual_metrics.get(metric_name, 0.0)
            val2 = c2.actual_metrics.get(metric_name, 0.0)

            if direction == "maximize":
                if val1 < val2:
                    at_least_as_good = False
                elif val1 > val2:
                    strictly_better = True
            else:  # minimize
                if val1 > val2:
                    at_least_as_good = False
                elif val1 < val2:
                    strictly_better = True

        return at_least_as_good and strictly_better

    @classmethod
    def rank_frontier(
        cls,
        candidates: Sequence[IntelligentCandidate],
        objectives: Sequence[tuple[str, str]],
    ) -> tuple[tuple[IntelligentCandidate, ...], tuple[IntelligentCandidate, ...]]:
        """Compute Pareto ranks and return (all_ranked_candidates, pareto_rank_1_frontier)."""
        if not candidates:
            return (), ()

        n = len(candidates)
        domination_counts = [0] * n
        dominated_indices: list[list[int]] = [[] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                if cls.dominates(candidates[i], candidates[j], objectives):
                    dominated_indices[i].append(j)
                    domination_counts[j] += 1
                elif cls.dominates(candidates[j], candidates[i], objectives):
                    dominated_indices[j].append(i)
                    domination_counts[i] += 1

        frontiers: list[list[int]] = [[]]
        for i in range(n):
            if domination_counts[i] == 0:
                frontiers[0].append(i)

        current_rank = 0
        ranked_candidates: list[IntelligentCandidate] = []

        while current_rank < len(frontiers) and frontiers[current_rank]:
            next_frontier = []
            for i in frontiers[current_rank]:
                for j in dominated_indices[i]:
                    domination_counts[j] -= 1
                    if domination_counts[j] == 0:
                        next_frontier.append(j)
            if next_frontier:
                frontiers.append(next_frontier)
            current_rank += 1

        # Build candidate objects with assigned pareto_rank
        for rank_idx, frontier_idxs in enumerate(frontiers):
            for idx in frontier_idxs:
                cand = candidates[idx]
                ranked_cand = IntelligentCandidate(
                    candidate_id=cand.candidate_id,
                    iteration=cand.iteration,
                    parameters=cand.parameters,
                    actual_metrics=cand.actual_metrics,
                    predicted_metrics=cand.predicted_metrics,
                    predicted_uncertainty=cand.predicted_uncertainty,
                    acquisition_score=cand.acquisition_score,
                    pareto_rank=rank_idx + 1,
                    surrogate_predicted=cand.surrogate_predicted,
                )
                ranked_candidates.append(ranked_cand)

        pareto_front = tuple(c for c in ranked_candidates if c.pareto_rank == 1)
        return tuple(ranked_candidates), pareto_front


class IntelligentSearchRunner:
    """Orchestrates surrogate-assisted multi-objective optimization."""

    @classmethod
    def run(
        cls,
        evaluate_fn: Callable[[dict[str, float]], dict[str, float]],
        spec: IntelligentSearchSpec,
    ) -> IntelligentSearchResult:
        rng = np.random.RandomState(spec.seed)
        all_evaluated: list[IntelligentCandidate] = []

        # 1. Initial Latin-Hypercube / Uniform Sampling
        initial_points = []
        for i in range(spec.n_initial_samples):
            point = {}
            for p in spec.parameter_ranges:
                # Deterministic stratified sample
                frac = (i + rng.uniform(0.1, 0.9)) / max(1, spec.n_initial_samples)
                point[p.name] = p.min_val + frac * (p.max_val - p.min_val)
            initial_points.append(point)

        for i, pt in enumerate(initial_points):
            metrics = evaluate_fn(pt)
            cand = IntelligentCandidate(
                candidate_id=f"init_{i}",
                iteration=0,
                parameters=pt,
                actual_metrics=metrics,
                surrogate_predicted=False,
            )
            all_evaluated.append(cand)

        # 2. Surrogate-Guided Active Optimization Loop
        scorer = AcquisitionScorer(
            strategy=spec.acquisition_strategy,
            kappa=spec.exploration_weight,
        )

        for iteration in range(1, spec.n_iterations + 1):
            # Fit one RBF surrogate per objective metric
            surrogates: dict[str, RBFGaussianSurrogate] = {}
            X_train = np.array(
                [[cand.parameters[p.name] for p in spec.parameter_ranges] for cand in all_evaluated]
            )

            for metric_name, _ in spec.target_objectives:
                y_train = np.array([cand.actual_metrics.get(metric_name, 0.0) for cand in all_evaluated])
                surrogate = RBFGaussianSurrogate(gamma=1.0)
                surrogate.fit(X_train, y_train)
                surrogates[metric_name] = surrogate

            # Generate candidate evaluation grid
            dim_values = [
                np.linspace(p.min_val, p.max_val, spec.grid_resolution_per_dim) for p in spec.parameter_ranges
            ]
            mesh = np.meshgrid(*dim_values)
            grid_points = np.column_stack([m.flatten() for m in mesh])

            # Score each grid candidate with surrogate acquisition function
            scored_proposals = []
            for pt_arr in grid_points:
                pt_dict = {p.name: float(pt_arr[j]) for j, p in enumerate(spec.parameter_ranges)}
                pred_metrics = {}
                pred_unc = {}
                total_acq = 0.0

                for metric_name, direction in spec.target_objectives:
                    mu_arr, sigma_arr = surrogates[metric_name].predict(pt_arr[np.newaxis, :])
                    mu = float(mu_arr[0])
                    sigma = float(sigma_arr[0])
                    pred_metrics[metric_name] = mu
                    pred_unc[metric_name] = sigma

                    best_val = max(c.actual_metrics.get(metric_name, 0.0) for c in all_evaluated)
                    acq = scorer.score(mu, sigma, best_val, direction=direction)
                    total_acq += acq

                scored_proposals.append((total_acq, pt_dict, pred_metrics, pred_unc))

            # Select top candidate proposals
            scored_proposals.sort(key=lambda item: item[0], reverse=True)
            selected = scored_proposals[: spec.candidates_per_iter]

            for sel_idx, (acq_score, pt_dict, pred_m, pred_u) in enumerate(selected):
                actual_m = evaluate_fn(pt_dict)
                cand = IntelligentCandidate(
                    candidate_id=f"iter{iteration}_cand{sel_idx}",
                    iteration=iteration,
                    parameters=pt_dict,
                    actual_metrics=actual_m,
                    predicted_metrics=pred_m,
                    predicted_uncertainty=pred_u,
                    acquisition_score=acq_score,
                    surrogate_predicted=False,
                )
                all_evaluated.append(cand)

        # 3. Final NSGA-II Pareto Ranking
        ranked_all, pareto_front = NSGA2FrontierSelector.rank_frontier(all_evaluated, spec.target_objectives)

        return IntelligentSearchResult(
            spec=spec,
            all_evaluated=ranked_all,
            pareto_frontier=pareto_front,
        )
