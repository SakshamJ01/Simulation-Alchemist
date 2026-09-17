"""Typed provider protocols and interfaces for generalized engine adapters (Phase 4).

These runtime-checkable Protocols define the standard capability query and
interaction surfaces across physics, field PDEs, agent systems, and network graphs.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class FieldProvider(Protocol):
    """Protocol for continuous spatial field engines (e.g. reaction-diffusion)."""

    def get_field_data(self) -> dict[str, np.ndarray]:
        """Return the current concentration/potential fields keyed by name."""
        ...

    def get_grid_shape(self) -> tuple[int, ...]:
        """Return the spatial resolution/shape of the field grid."""
        ...

    def sample_field_at(self, position: tuple[float, float], field_name: str = "u") -> float:
        """Sample a scalar field value at continuous coordinates."""
        ...

    def sample_gradient_at(self, position: tuple[float, float], field_name: str = "u") -> tuple[float, float]:
        """Sample spatial gradient vector (du/dx, du/dy) at continuous coordinates."""
        ...


@runtime_checkable
class RigidBodyProvider(Protocol):
    """Protocol for mechanical rigid-body / discrete particle physics engines."""

    def get_body_positions(self) -> list[tuple[float, float]]:
        """Return 2D coordinates for all active simulated bodies/particles."""
        ...

    def get_body_velocities(self) -> list[tuple[float, float]]:
        """Return 2D velocities for all active simulated bodies/particles."""
        ...

    def apply_forces(self, forces: list[tuple[float, float]]) -> None:
        """Apply 2D force vectors to bodies in canonical index order."""
        ...


@runtime_checkable
class AgentDecisionProvider(Protocol):
    """Protocol for discrete agent decision engines (e.g. Mesa)."""

    def get_agent_intentions(self) -> list[dict[str, Any]]:
        """Return discrete action intentions generated in the current decision step."""
        ...

    def get_agent_positions(self) -> list[tuple[float, float]]:
        """Return 2D positions of all active decision agents."""
        ...


@runtime_checkable
class NetworkGraphProvider(Protocol):
    """Protocol for dynamical network / graph diffusion engines (e.g. NDlib)."""

    def get_node_loads(self) -> dict[int, float]:
        """Return continuous load/activation values keyed by integer node ID."""
        ...

    def get_edge_weights(self) -> dict[tuple[int, int], float]:
        """Return dynamic edge conductances/weights keyed by (u, v) node pairs."""
        ...


@runtime_checkable
class GatedPhysicsProvider(RigidBodyProvider, Protocol):
    """Protocol for physics engines with dynamic spatial barriers and gates (Experiment D)."""

    def is_gate_open(self) -> bool:
        """Return whether dynamic control gates are currently permeable."""
        ...

    def get_compartment_counts(self) -> dict[str, int]:
        """Return particle/body distribution counts across spatial compartments."""
        ...
