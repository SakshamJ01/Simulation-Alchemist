"""Experiment E: Fluid-Structure Active Matter (Navier-Stokes + py-pde + Active Swimmers)."""

from experiments.fluid_active_matter.coupling import (
    FLUID_ACTIVE_MATTER_CONTRACTS,
    FLUID_ACTIVE_MATTER_SCHEDULE,
    build_fluid_active_matter_registry,
    build_fluid_active_matter_template,
    build_fluid_active_matter_world,
)
from experiments.fluid_active_matter.experiment import (
    PARAMETER_SPECS,
    run_fluid_active_matter_world,
)
from experiments.fluid_active_matter.model import (
    FluidActiveMatterConfig,
    FluidActiveMatterTrajectory,
    FluidEngineAdapter,
    SwimmersAdapter,
)

__all__ = [
    "FLUID_ACTIVE_MATTER_CONTRACTS",
    "FLUID_ACTIVE_MATTER_SCHEDULE",
    "PARAMETER_SPECS",
    "FluidActiveMatterConfig",
    "FluidActiveMatterTrajectory",
    "FluidEngineAdapter",
    "SwimmersAdapter",
    "build_fluid_active_matter_registry",
    "build_fluid_active_matter_template",
    "build_fluid_active_matter_world",
    "run_fluid_active_matter_world",
]
