"""Field-Guided Movers experiment (Task 1.1).

A second, smaller composition that proves the Alchemist kernel is reusable
without Mesa: a py-pde reaction-diffusion field coupled to Pymunk probe
movers through the shared core (engine, clock, event bus, capability
resolver, adapter contracts).
"""

from .model import (
    FieldGuidedMoversEngine,
    Mover,
    MoversAdapter,
    MoversConfig,
    MoverSpace,
    MoversTrajectory,
    gradient_force,
    mover_source,
)

__all__ = [
    "FieldGuidedMoversEngine",
    "Mover",
    "MoverSpace",
    "MoversAdapter",
    "MoversConfig",
    "MoversTrajectory",
    "gradient_force",
    "mover_source",
]