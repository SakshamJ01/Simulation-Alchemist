"""Tests for Deep Neural Network Surrogates and Ensembles (Phase 4I)."""

from __future__ import annotations

import numpy as np

from sim_alchemist.core.deep_surrogates import (
    DeepNeuralSurrogate,
    DeepSurrogateEnsemble,
    gelu,
    relu,
)


def test_activations() -> None:
    x = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    r = relu(x)
    assert np.all(r >= 0.0)
    assert r[0] == 0.0
    assert r[-1] == 2.0

    g = gelu(x)
    assert g[0] < 0.0  # GELU dips slightly below 0
    assert g[-1] > 1.9


def test_deep_surrogate_training_and_prediction() -> None:
    rng = np.random.RandomState(42)
    X = rng.uniform(-2.0, 2.0, size=(60, 3))
    # Target non-linear function
    y = np.sin(X[:, 0]) + 0.5 * (X[:, 1] ** 2) - 0.2 * X[:, 2]

    surrogate = DeepNeuralSurrogate(layer_sizes=(16, 16), activation="relu", learning_rate=0.02, seed=42)
    losses = surrogate.fit(X, y, epochs=100, batch_size=16)

    assert len(losses) == 100
    assert losses[-1] < losses[0]  # Loss decreased

    preds = surrogate.predict(X[:5])
    assert preds.shape == (5,)
    assert np.all(np.isfinite(preds))


def test_deep_surrogate_ensemble_uncertainty() -> None:
    rng = np.random.RandomState(42)
    X = rng.uniform(-1.0, 1.0, size=(40, 2))
    y = X[:, 0] * 2.0 + X[:, 1]

    ensemble = DeepSurrogateEnsemble(n_models=3, layer_sizes=(8, 8), base_seed=100)
    history = ensemble.fit(X, y, epochs=50)

    assert len(history) == 3
    mu, sigma = ensemble.predict(X[:4])

    assert mu.shape == (4,)
    assert sigma.shape == (4,)
    assert np.all(sigma >= 0.0)  # Standard deviation is non-negative
