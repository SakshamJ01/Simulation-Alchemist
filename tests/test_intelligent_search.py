"""Unit tests for intelligent multi-objective search & surrogate optimization (Phase 4I)."""

import numpy as np
import pytest

from sim_alchemist.core.intelligent_search import (
    AcquisitionScorer,
    IntelligentCandidate,
    IntelligentSearchRunner,
    IntelligentSearchSpec,
    NSGA2FrontierSelector,
    RBFGaussianSurrogate,
    SearchParameterRange,
    SurrogateModel,
)


def test_rbf_surrogate_exact_fitting_and_uncertainty():
    surrogate = RBFGaussianSurrogate(gamma=1.0, ridge_lambda=1e-6)
    assert isinstance(surrogate, SurrogateModel)

    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0.0, 1.0, 4.0, 9.0])  # y = x^2

    surrogate.fit(X, y)

    # Predict at training points -> should be very close to ground truth
    mu, sigma = surrogate.predict(X)
    assert np.allclose(mu, y, atol=1e-2)
    # Uncertainty at training points should be low
    assert np.all(sigma < 0.2)

    # Predict far away from training data -> uncertainty should increase
    X_far = np.array([[10.0]])
    _, sigma_far = surrogate.predict(X_far)
    assert sigma_far[0] > np.mean(sigma)


def test_acquisition_scoring():
    scorer_ucb = AcquisitionScorer(strategy="UCB", kappa=2.0)
    # High mean, high uncertainty -> high UCB
    score1 = scorer_ucb.score(mu=10.0, sigma=3.0, best_y=8.0, direction="maximize")
    assert pytest.approx(score1) == 16.0  # 10 + 2*3 = 16

    # Minimization
    score_min = scorer_ucb.score(mu=2.0, sigma=1.0, best_y=5.0, direction="minimize")
    assert pytest.approx(score_min) == 0.0  # -2 + 2*1 = 0

    # Expected Improvement
    scorer_ei = AcquisitionScorer(strategy="EI", xi=0.01)
    ei_score = scorer_ei.score(mu=12.0, sigma=2.0, best_y=10.0, direction="maximize")
    assert ei_score > 0.0


def test_nsga2_frontier_ranking():
    # 3 candidates:
    # c1: (10, 2)
    # c2: (8, 8) -> c1 and c2 are mutually non-dominated
    # c3: (5, 1) -> dominated by c1
    c1 = IntelligentCandidate(
        candidate_id="c1",
        iteration=0,
        parameters={"x": 1.0},
        actual_metrics={"m1": 10.0, "m2": 2.0},
    )
    c2 = IntelligentCandidate(
        candidate_id="c2",
        iteration=0,
        parameters={"x": 2.0},
        actual_metrics={"m1": 8.0, "m2": 8.0},
    )
    c3 = IntelligentCandidate(
        candidate_id="c3",
        iteration=0,
        parameters={"x": 0.5},
        actual_metrics={"m1": 5.0, "m2": 1.0},
    )

    objectives = (("m1", "maximize"), ("m2", "maximize"))

    assert NSGA2FrontierSelector.dominates(c1, c3, objectives)
    assert not NSGA2FrontierSelector.dominates(c1, c2, objectives)

    _ranked_all, pareto_front = NSGA2FrontierSelector.rank_frontier([c1, c2, c3], objectives)

    assert len(pareto_front) == 2
    pareto_ids = {c.candidate_id for c in pareto_front}
    assert pareto_ids == {"c1", "c2"}


def test_intelligent_search_runner_end_to_end():
    # Synthetic multi-objective simulation test function:
    # m1 = 10 - (x - 2)^2 - (y - 3)^2 (maximize)
    # m2 = x + y (maximize)
    def evaluate_fn(params: dict[str, float]) -> dict[str, float]:
        x = params["x"]
        y = params["y"]
        m1 = 10.0 - (x - 2.0) ** 2 - (y - 3.0) ** 2
        m2 = x + y
        return {"m1": float(m1), "m2": float(m2)}

    spec = IntelligentSearchSpec(
        name="test_search",
        parameter_ranges=[
            SearchParameterRange("x", 0.0, 5.0),
            SearchParameterRange("y", 0.0, 5.0),
        ],
        target_objectives=(("m1", "maximize"), ("m2", "maximize")),
        n_initial_samples=4,
        n_iterations=2,
        candidates_per_iter=2,
        grid_resolution_per_dim=4,
        acquisition_strategy="UCB",
        exploration_weight=2.0,
        seed=42,
    )

    result = IntelligentSearchRunner.run(evaluate_fn, spec)

    assert result.spec.name == "test_search"
    # 4 initial + 2 iter * 2 candidates = 8 evaluated
    assert len(result.all_evaluated) == 8
    assert len(result.pareto_frontier) >= 1

    d = result.as_dict()
    assert d["total_evaluated"] == 8
    assert d["pareto_frontier_count"] == len(result.pareto_frontier)
