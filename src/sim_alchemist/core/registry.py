"""In-process component registry and adapter factories.

The registry is the explicit, discoverable catalog from which the composer
builds adapters.  A ``ComponentRegistry`` maps a stable component id to an
``AdapterFactory`` (a callable that constructs one adapter from a config
dict).  Task 1.3 ships ``default_registry()`` with the three wall-pymunk
component ids (``mesa``, ``py-pde``, ``pymunk``) used by the validated
Experiment A.  Experiment B's point-mover ``pymunk`` variant is provided by
the experiment's coupling layer, which overrides the ``pymunk`` entry with a
``MoversAdapter`` factory -- keeping experiment-specific names out of the core.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.capabilities import SimulationEngine


@dataclass(frozen=True)
class AdapterFactory:
    """A registered constructor for one component id.

    ``builder`` receives a config dict (from the world's ``ComponentSpec``)
    and returns an adapter implementing ``SimulationEngine``.
    """

    component: str
    builder: Callable[[dict[str, Any]], SimulationEngine]

    def build(self, config: dict[str, Any]) -> SimulationEngine:
        return self.builder(config)


class ComponentRegistry:
    """Explicit, in-process catalog of component adapter factories."""

    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, component: str, builder: Callable[[dict[str, Any]], SimulationEngine]) -> None:
        """Register a builder under ``component`` (overwrites any prior entry)."""
        self._factories[component] = AdapterFactory(component=component, builder=builder)

    def has(self, component: str) -> bool:
        return component in self._factories

    def get(self, component: str) -> AdapterFactory:
        try:
            return self._factories[component]
        except KeyError:
            available = ", ".join(sorted(self._factories)) or "(none registered)"
            raise UnknownComponentError(
                f"Unknown component '{component}'. Registered: {available}"
            ) from None

    def build(self, component: str, config: dict[str, Any]) -> SimulationEngine:
        return self.get(component).build(config)

    def components(self) -> list[str]:
        return sorted(self._factories)

    def __iter__(self):
        return iter(self._factories.items())


class UnknownComponentError(KeyError):
    """Raised when a world references a component id with no registered factory."""


def _field_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Extract PyPDEAdapter constructor kwargs from a component config."""
    keys = ("n", "du", "dv", "a", "b", "dt", "seed", "field_step")
    return {k: config[k] for k in keys if k in config}


def _pymunk_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Extract PymunkAdapter constructor kwargs from a component config."""
    keys = ("n", "mass", "damping", "dt_phys", "phys_substeps", "scale")
    return {k: config[k] for k in keys if k in config}


def _mesa_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Extract MesaAdapter constructor kwargs from a component config."""
    keys = ("agent_configs", "seed", "macro_timestep")
    return {k: config[k] for k in keys if k in config}


def default_registry() -> ComponentRegistry:
    """The validated Experiment A component catalog.

    Ships the three wall-based components: ``py-pde`` (reaction-diffusion),
    ``pymunk`` (rigid-body walls), and ``mesa`` (agent sensing/decisions).
    The point-mover ``pymunk`` variant for Experiment B is supplied by that
    experiment's coupling layer (it overrides the ``pymunk`` entry).
    """
    from sim_alchemist.adapters.mesa import MesaAdapter
    from sim_alchemist.adapters.pde import PyPDEAdapter
    from sim_alchemist.adapters.pymunk import PymunkAdapter

    registry = ComponentRegistry()
    registry.register("py-pde", lambda cfg: PyPDEAdapter(**_field_kwargs(cfg)))
    registry.register("pymunk", lambda cfg: PymunkAdapter(**_pymunk_kwargs(cfg)))
    registry.register("mesa", lambda cfg: MesaAdapter(**_mesa_kwargs(cfg)))
    return registry
