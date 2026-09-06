"""Chemo-mechanical spike experiments for Tasks 0.2 and 0.3."""

from .agents import AgentConfig
from .engine import ChemomechanicalEngine
from .physics import WallSpace
from .reaction_diffusion import RDField
from .simulation import Trajectory, WorldConfig, run_world

__all__ = [
    "AgentConfig",
    "ChemomechanicalEngine",
    "RDField",
    "Trajectory",
    "WallSpace",
    "WorldConfig",
    "run_world",
]