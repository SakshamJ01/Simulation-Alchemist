"""Declarative composition graph and coupling dataflow representation (Phase 4 Slice 4.3).

Represents a multi-engine simulation world as an explicit directed graph where:
- Nodes represent participating simulation engines / components.
- Edges represent coupling dataflows / contracts transferring state, forces, or decisions.

Provides graph-theoretic validation, cycle detection, topological execution sorting,
and visual diagram generation (Mermaid/DOT).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.contracts import CouplingContract


class GraphCycleError(ValueError):
    """Raised when an unresolvable directed cycle is detected in a composition graph."""


@dataclass(frozen=True)
class CouplingChannel:
    """A dataflow channel defining state transmission across a coupling edge."""

    name: str
    data_type: str  # e.g. "field_gradient", "agent_intention", "particle_positions", "control_gate"
    payload_keys: tuple[str, ...]
    rate_ratio: int = 1  # Multi-rate stepping ratio (consumer steps per producer step)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "payload_keys": list(self.payload_keys),
            "rate_ratio": self.rate_ratio,
        }


@dataclass(frozen=True)
class CouplingEdge:
    """A directed coupling edge from a producer component to a consumer component."""

    source: str
    target: str
    channel: CouplingChannel
    contract_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "channel": self.channel.as_dict(),
            "contract_name": self.contract_name,
        }


@dataclass
class CompositionGraph:
    """Directed composition graph of simulation components and coupling edges."""

    nodes: set[str] = field(default_factory=set)
    edges: list[CouplingEdge] = field(default_factory=list)

    def add_node(self, node: str) -> None:
        """Add a component node to the graph."""
        if not node or not isinstance(node, str):
            raise ValueError("Node name must be a non-empty string")
        self.nodes.add(node)

    def add_edge(self, edge: CouplingEdge) -> None:
        """Add a directed coupling edge between two nodes."""
        self.nodes.add(edge.source)
        self.nodes.add(edge.target)
        self.edges.append(edge)

    def incoming_edges(self, node: str) -> list[CouplingEdge]:
        """Return all incoming edges targeting node."""
        return [e for e in self.edges if e.target == node]

    def outgoing_edges(self, node: str) -> list[CouplingEdge]:
        """Return all outgoing edges originating from node."""
        return [e for e in self.edges if e.source == node]

    def adjacency_list(self) -> dict[str, list[str]]:
        """Return adjacency list mapping source -> list of targets."""
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}
        for e in self.edges:
            adj[e.source].append(e.target)
        return adj

    def has_cycles(self) -> bool:
        """Return True if the directed graph contains at least one cycle."""
        # Standard Kahn's algorithm or DFS 3-color
        adj = self.adjacency_list()
        in_degree: dict[str, int] = {n: 0 for n in self.nodes}
        for e in self.edges:
            in_degree[e.target] += 1

        queue: deque[str] = deque([n for n in self.nodes if in_degree[n] == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited_count < len(self.nodes)

    def topological_order(self) -> list[str]:
        """Compute a deterministic topological sort of the graph nodes.

        Raises:
            GraphCycleError: If the graph contains a cycle.
        """
        adj = self.adjacency_list()
        # Sort targets deterministically
        for k in adj:
            adj[k].sort()

        in_degree: dict[str, int] = {n: 0 for n in self.nodes}
        for e in self.edges:
            in_degree[e.target] += 1

        # Deterministic queue ordering (sorted node names)
        initial = sorted([n for n in self.nodes if in_degree[n] == 0])
        queue: deque[str] = deque(initial)
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            # Re-sort remaining queue items for strict determinism
            sorted_remaining = sorted(queue)
            queue = deque(sorted_remaining)

        if len(result) < len(self.nodes):
            raise GraphCycleError("Composition graph has cycles; cannot compute topological order.")
        return result

    @classmethod
    def from_contracts(
        cls,
        components: Sequence[str],
        contracts: Sequence[CouplingContract],
    ) -> CompositionGraph:
        """Construct a CompositionGraph directly from component names and declared CouplingContracts."""
        graph = cls()
        for comp in sorted(components):
            graph.add_node(comp)

        for contract in contracts:
            keys = tuple(p.key for p in contract.payload)
            channel = CouplingChannel(
                name=f"{contract.producer}->{contract.consumer}:{contract.name}",
                data_type=contract.producer_capability,
                payload_keys=keys,
                rate_ratio=1,
            )
            edge = CouplingEdge(
                source=contract.producer,
                target=contract.consumer,
                channel=channel,
                contract_name=contract.name,
            )
            graph.add_edge(edge)

        return graph

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart representation of the composition graph."""
        lines = ["graph TD"]
        for node in sorted(self.nodes):
            lines.append(f"    {node}[{node}]")
        for edge in self.edges:
            label = edge.channel.data_type
            if edge.contract_name:
                label = f"{edge.contract_name} ({label})"
            lines.append(f"    {edge.source} -->|{label}| {edge.target}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Serialize the composition graph to a JSON-compatible dictionary."""
        return {
            "nodes": sorted(self.nodes),
            "edges": [e.as_dict() for e in self.edges],
            "has_cycles": self.has_cycles(),
        }
