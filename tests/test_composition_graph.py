"""Tests for CompositionGraph and Coupling Dataflows (Phase 4 Slice 4.3)."""

from __future__ import annotations

import pytest

from sim_alchemist.core.contracts import CouplingContract, PayloadItem
from sim_alchemist.core.graph import (
    CompositionGraph,
    CouplingChannel,
    CouplingEdge,
    GraphCycleError,
)


def test_graph_node_and_edge_creation() -> None:
    graph = CompositionGraph()
    graph.add_node("pde")
    graph.add_node("pymunk")

    channel = CouplingChannel(
        name="field_to_physics",
        data_type="reaction_diffusion",
        payload_keys=("gradient_u", "gradient_v"),
        rate_ratio=1,
    )
    edge = CouplingEdge(
        source="pde",
        target="pymunk",
        channel=channel,
        contract_name="gradient_force",
    )
    graph.add_edge(edge)

    assert "pde" in graph.nodes
    assert "pymunk" in graph.nodes
    assert len(graph.edges) == 1
    assert graph.has_cycles() is False
    assert graph.topological_order() == ["pde", "pymunk"]


def test_graph_cycle_detection() -> None:
    graph = CompositionGraph()
    channel = CouplingChannel(name="c", data_type="test", payload_keys=())
    graph.add_edge(CouplingEdge("A", "B", channel))
    graph.add_edge(CouplingEdge("B", "C", channel))
    graph.add_edge(CouplingEdge("C", "A", channel))

    assert graph.has_cycles() is True
    with pytest.raises(GraphCycleError):
        graph.topological_order()


def test_graph_from_contracts() -> None:
    contracts = [
        CouplingContract(
            name="field_force",
            producer="pde",
            producer_capability="reaction_diffusion",
            consumer="pymunk",
            consumer_capability="rigid_body_physics",
            payload=[PayloadItem("gradient_u", "vec2")],
            transform="grad_force",
        ),
        CouplingContract(
            name="mover_source",
            producer="pymunk",
            producer_capability="rigid_body_physics",
            consumer="pde",
            consumer_capability="reaction_diffusion",
            payload=[PayloadItem("positions", "vec2_list")],
            transform="pos_source",
        ),
    ]

    graph = CompositionGraph.from_contracts(["pde", "pymunk"], contracts)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 2
    # Feedback loop between pde and pymunk
    assert graph.has_cycles() is True

    serialized = graph.as_dict()
    assert serialized["has_cycles"] is True
    assert len(serialized["edges"]) == 2

    mermaid = graph.to_mermaid()
    assert "graph TD" in mermaid
    assert "pde" in mermaid
    assert "pymunk" in mermaid
