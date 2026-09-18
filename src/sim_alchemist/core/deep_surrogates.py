"""Deep Neural Network Surrogates & Vectorized MLP Ensembles (Phase 4I).

Provides pure-vectorized deep neural network surrogate models with deterministic
Adam optimization, Xavier initialization, and deep ensembles for epistemic
uncertainty estimation over high-dimensional simulation parameter spaces.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


def relu_grad(x: np.ndarray) -> np.ndarray:
    return (x > 0.0).astype(float)


def gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * (x**3))))


def gelu_grad(x: np.ndarray) -> np.ndarray:
    s = np.sqrt(2.0 / np.pi) * (x + 0.044715 * (x**3))
    tanh_s = np.tanh(s)
    sech_sq = 1.0 - tanh_s**2
    ds_dx = np.sqrt(2.0 / np.pi) * (1.0 + 3.0 * 0.044715 * (x**2))
    return 0.5 * (1.0 + tanh_s) + 0.5 * x * sech_sq * ds_dx


@dataclass
class DenseLayer:
    """Fully connected feedforward dense layer with Adam momentum states."""

    weights: np.ndarray
    biases: np.ndarray
    activation: str = "relu"

    m_w: np.ndarray = field(init=False)
    v_w: np.ndarray = field(init=False)
    m_b: np.ndarray = field(init=False)
    v_b: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.m_w = np.zeros_like(self.weights)
        self.v_w = np.zeros_like(self.weights)
        self.m_b = np.zeros_like(self.biases)
        self.v_b = np.zeros_like(self.biases)


class DeepNeuralSurrogate:
    """Multi-Layer Perceptron (MLP) regressor with deterministic Adam optimization."""

    def __init__(
        self,
        layer_sizes: Sequence[int] = (16, 16),
        activation: str = "relu",
        learning_rate: float = 0.01,
        weight_decay: float = 1e-4,
        seed: int = 42,
    ) -> None:
        self.layer_sizes = tuple(layer_sizes)
        self.activation = activation
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.seed = seed

        self.layers: list[DenseLayer] = []
        self._x_mean: np.ndarray | None = None
        self._x_std: np.ndarray | None = None
        self._y_mean: float = 0.0
        self._y_std: float = 1.0

    def _init_layers(self, input_dim: int, output_dim: int = 1) -> None:
        rng = np.random.RandomState(self.seed)
        dims = [input_dim] + list(self.layer_sizes) + [output_dim]
        self.layers = []

        for i in range(len(dims) - 1):
            fan_in, fan_out = dims[i], dims[i + 1]
            limit = math.sqrt(2.0 / fan_in)  # He initialization
            w = rng.randn(fan_in, fan_out) * limit
            b = np.zeros((1, fan_out))
            act = self.activation if i < len(dims) - 2 else "linear"
            self.layers.append(DenseLayer(weights=w, biases=b, activation=act))

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 200, batch_size: int = 16) -> list[float]:
        """Train deep surrogate on parameter matrix X and target array y."""
        if len(X) == 0:
            raise ValueError("Cannot train on empty dataset.")
        if len(X) != len(y):
            raise ValueError("X and y must have identical lengths.")

        # Normalize features & targets
        self._x_mean = np.mean(X, axis=0, keepdims=True)
        self._x_std = np.std(X, axis=0, keepdims=True)
        self._x_std[self._x_std < 1e-8] = 1.0

        self._y_mean = float(np.mean(y))
        self._y_std = float(np.std(y)) if float(np.std(y)) > 1e-8 else 1.0

        X_norm = (X - self._x_mean) / self._x_std
        y_norm = (y.reshape(-1, 1) - self._y_mean) / self._y_std

        self._init_layers(input_dim=X.shape[1], output_dim=1)

        losses = []
        rng = np.random.RandomState(self.seed)
        n = len(X)
        t = 0
        beta1 = 0.9
        beta2 = 0.999
        eps = 1e-8

        for _ in range(epochs):
            indices = rng.permutation(n)
            X_shuffled = X_norm[indices]
            y_shuffled = y_norm[indices]

            epoch_loss = 0.0
            n_batches = max(1, n // batch_size)

            for b in range(n_batches):
                start = b * batch_size
                end = min(n, start + batch_size)
                xb = X_shuffled[start:end]
                yb = y_shuffled[start:end]

                # Forward pass
                activations = [xb]
                pre_activations = []

                for layer in self.layers:
                    z = activations[-1] @ layer.weights + layer.biases
                    pre_activations.append(z)
                    if layer.activation == "relu":
                        a = relu(z)
                    elif layer.activation == "gelu":
                        a = gelu(z)
                    else:
                        a = z
                    activations.append(a)

                pred = activations[-1]
                loss = float(np.mean((pred - yb) ** 2))
                epoch_loss += loss

                # Backward pass
                t += 1
                grad = 2.0 * (pred - yb) / len(xb)

                for idx in reversed(range(len(self.layers))):
                    layer = self.layers[idx]
                    z = pre_activations[idx]
                    a_prev = activations[idx]

                    if layer.activation == "relu":
                        grad = grad * relu_grad(z)
                    elif layer.activation == "gelu":
                        grad = grad * gelu_grad(z)

                    dw = a_prev.T @ grad + self.weight_decay * layer.weights
                    db = np.sum(grad, axis=0, keepdims=True)

                    # Adam update
                    layer.m_w = beta1 * layer.m_w + (1 - beta1) * dw
                    layer.v_w = beta2 * layer.v_w + (1 - beta2) * (dw**2)
                    m_w_hat = layer.m_w / (1 - beta1**t)
                    v_w_hat = layer.v_w / (1 - beta2**t)
                    layer.weights -= self.learning_rate * m_w_hat / (np.sqrt(v_w_hat) + eps)

                    layer.m_b = beta1 * layer.m_b + (1 - beta1) * db
                    layer.v_b = beta2 * layer.v_b + (1 - beta2) * (db**2)
                    m_b_hat = layer.m_b / (1 - beta1**t)
                    v_b_hat = layer.v_b / (1 - beta2**t)
                    layer.biases -= self.learning_rate * m_b_hat / (np.sqrt(v_b_hat) + eps)

                    grad = grad @ layer.weights.T

            losses.append(epoch_loss / n_batches)

        return losses

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Forward predict normalized inputs and scale back to original metric units."""
        if self._x_mean is None or self._x_std is None or not self.layers:
            raise RuntimeError("Surrogate model must be trained before predict().")

        X_norm = (X - self._x_mean) / self._x_std
        a = X_norm

        for layer in self.layers:
            z = a @ layer.weights + layer.biases
            if layer.activation == "relu":
                a = relu(z)
            elif layer.activation == "gelu":
                a = gelu(z)
            else:
                a = z

        return a.flatten() * self._y_std + self._y_mean


class DeepSurrogateEnsemble:
    """Ensemble of deep neural surrogates providing mean predictions and epistemic uncertainty."""

    def __init__(self, n_models: int = 5, layer_sizes: Sequence[int] = (16, 16), base_seed: int = 42) -> None:
        self.n_models = n_models
        self.models = [
            DeepNeuralSurrogate(layer_sizes=layer_sizes, seed=base_seed + i * 17) for i in range(n_models)
        ]

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 150) -> list[list[float]]:
        history = []
        for model in self.models:
            losses = model.fit(X, y, epochs=epochs)
            history.append(losses)
        return history

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (mean_predictions, epistemic_uncertainty_std)."""
        preds = np.array([m.predict(X) for m in self.models])
        mu = np.mean(preds, axis=0)
        sigma = np.std(preds, axis=0)
        return mu, sigma

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "DeepSurrogateEnsemble",
            "n_models": self.n_models,
            "layer_sizes": list(self.models[0].layer_sizes) if self.models else [],
        }
