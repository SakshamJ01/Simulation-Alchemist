"""Simulation Alchemist — composition kernel."""

from .adapters.base import SimulationEngine
from .adapters.mesa import MesaAdapter
from .adapters.pde import PyPDEAdapter
from .adapters.pymunk import PymunkAdapter
from .core.capabilities import Capability, CapabilitySet
from .core.clock import SimulationClock
from .core.engine import AlchemistEngine
from .core.events import EventBus
from .core.state import WorldState

__all__ = [
    "AlchemistEngine",
    "Capability",
    "CapabilitySet",
    "EventBus",
    "MesaAdapter",
    "PyPDEAdapter",
    "PymunkAdapter",
    "SimulationClock",
    "SimulationEngine",
    "WorldState",
]