"""Tests for generalized adapter protocols and provider interfaces (Phase 4 Slice 4.2)."""

from __future__ import annotations

import numpy as np
import pytest

from sim_alchemist.core.interfaces import (
    AgentDecisionProvider,
    FieldProvider,
    GatedPhysicsProvider,
    NetworkGraphProvider,
    RigidBodyProvider,
)


class DummyFieldAdapter:
    def get_field_data(self) -> dict[str, np.ndarray]:
        return {"u": np.zeros((32, 32)), "v": np.zeros((32, 32))}

    def get_grid_shape(self) -> tuple[int, ...]:
        return (32, 32)

    def sample_field_at(self, position: tuple[float, float], field_name: str = "u") -> float:
        return 0.5

    def sample_gradient_at(self, position: tuple[float, float], field_name: str = "u") -> tuple[float, float]:
        return (0.1, -0.1)


class DummyPhysicsAdapter:
    def get_body_positions(self) -> list[tuple[float, float]]:
        return [(0.5, 0.5), (0.2, 0.8)]

    def get_body_velocities(self) -> list[tuple[float, float]]:
        return [(0.0, 0.0), (0.01, -0.02)]

    def apply_forces(self, forces: list[tuple[float, float]]) -> None:
        pass


class DummyGatedPhysicsAdapter(DummyPhysicsAdapter):
    def is_gate_open(self) -> bool:
        return True

    def get_compartment_counts(self) -> dict[str, int]:
        return {"left": 1, "right": 1}


class DummyAgentAdapter:
    def get_agent_intentions(self) -> list[dict[str, object]]:
        return [{"action": "build_wall", "target": (10, 10)}]

    def get_agent_positions(self) -> list[tuple[float, float]]:
        return [(0.3, 0.4)]


class DummyNetworkAdapter:
    def get_node_loads(self) -> dict[int, float]:
        return {0: 1.0, 1: 0.5}

    def get_edge_weights(self) -> dict[tuple[int, int], float]:
        return {(0, 1): 0.8}


def test_field_provider_protocol() -> None:
    adapter = DummyFieldAdapter()
    assert isinstance(adapter, FieldProvider)
    assert adapter.get_grid_shape() == (32, 32)
    assert adapter.sample_field_at((0.1, 0.2)) == 0.5


def test_rigid_body_provider_protocol() -> None:
    adapter = DummyPhysicsAdapter()
    assert isinstance(adapter, RigidBodyProvider)
    assert len(adapter.get_body_positions()) == 2


def test_gated_physics_provider_protocol() -> None:
    adapter = DummyGatedPhysicsAdapter()
    assert isinstance(adapter, RigidBodyProvider)
    assert isinstance(adapter, GatedPhysicsProvider)
    assert adapter.is_gate_open() is True
    assert adapter.get_compartment_counts()["left"] == 1


def test_agent_decision_provider_protocol() -> None:
    adapter = DummyAgentAdapter()
    assert isinstance(adapter, AgentDecisionProvider)
    assert len(adapter.get_agent_intentions()) == 1


def test_network_graph_provider_protocol() -> None:
    adapter = DummyNetworkAdapter()
    assert isinstance(adapter, NetworkGraphProvider)
    assert adapter.get_node_loads()[0] == 1.0
