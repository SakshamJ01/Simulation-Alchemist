"""Experiment B coupling: field-guided movers schedule operations and world.

The Field-Guided Movers experiment (py-pde field + point-mover Pymunk bodies,
no Mesa) owns two coupling rules here, outside the core:
    * ``gradient_force``  -- field gradient -> bounded physical force,
    * ``mover_source``    -- mover position -> chemical source/sink deposit.

The declared macro-step order lives in ``FIELD_GUIDED_MOVERS_SCHEDULE`` and the
operation handlers are closures built by ``build_field_guided_movers_operations``,
dispatched by the core ``StepScheduler``.  The declarative ``WorldDefinition``
builder plus a registry builder make this world composable by the generic core
composer.

This module deliberately imports nothing from ``experiments.field_guided_movers.
model`` at runtime (TYPE_CHECKING only), so ``model`` may re-export the coupling
rules without import cycles.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.registry import ComponentRegistry, default_registry
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

if TYPE_CHECKING:
    from experiments.field_guided_movers.model import (
        Mover,
        MoversAdapter,
        MoversConfig,
        MoversTrajectory,
    )


FIELD_GUIDED_MOVERS_SCHEDULE: tuple[str, ...] = (
    "field.step",
    "movers.force",
    "movers.step",
    "field.source",
    "observables.record",
)


@dataclass
class MoversState:
    """Per-macro-step scratch shared across the schedule operations."""

    total_force: float = 0.0
    total_grad: float = 0.0
    sources_present: int = 0


def gradient_force(
    pde: PyPDEAdapter,
    position: tuple[float, float],
    force_fmax: float,
    force_gsat: float,
    field_name: str = "u",
) -> tuple[float, float]:
    """Experiment rule: field gradient -> bounded physical force.

    F = Fmax * tanh(|grad u| / g_sat) * grad u / |grad u|.
    """
    x, y = position
    gx, gy = pde.gradient(x, y, field_name)
    gmag = float(np.hypot(gx, gy))
    if gmag == 0.0:
        return 0.0, 0.0
    magnitude = force_fmax * math.tanh(gmag / force_gsat)
    return magnitude * float(gx) / gmag, magnitude * float(gy) / gmag


def mover_source(
    mover: Mover,
    config: MoversConfig,
    field_name: str = "u",
) -> dict[str, float]:
    """Experiment rule: mover position -> chemical source/sink.

    The mover deposits activator ``u`` and consumes inhibitor ``v`` at its
    current position.  The effect is computed here (experiment-owned) and
    handed to the PDE adapter's generic source injection.
    """
    _ = field_name  # reserved: species field name is u for both channels
    return {
        "x": mover.position[0],
        "y": mover.position[1],
        "u": config.source_u,
        "v": config.source_v,
        "radius": config.source_radius,
    }


def build_field_guided_movers_world(config: MoversConfig) -> WorldDefinition:
    """The declarative world definition reproducing Experiment B exactly."""
    return WorldDefinition(
        id="field_guided_movers",
        components=(
            ComponentSpec("py-pde", {
                "n": config.n, "du": config.du, "dv": config.dv,
                "a": config.a, "b": config.b, "dt": config.pde_dt,
                "seed": config.seed, "field_step": config.macro_timestep,
            }),
            ComponentSpec("pymunk", config.as_dict()),
        ),
        requires=("reaction_diffusion", "rigid_body", "field_gradient"),
        schedule=FIELD_GUIDED_MOVERS_SCHEDULE,
        macro_timestep=config.macro_timestep,
        max_steps=config.n_steps,
        seed=config.seed,
        config=config.as_dict(),
    )


def build_field_guided_movers_registry() -> ComponentRegistry:
    """Core registry with the point-mover ``pymunk`` variant overridden.

    The ``pymunk`` component id is dual-variant: Experiment A uses the walls
    adapter, Experiment B the probe-body (Movers) adapter.  The experiment
    overrides the core entry so experiment-specific names stay out of the core.
    """
    registry = default_registry()

    def _mover_factory(cfg: dict[str, Any]) -> MoversAdapter:
        from experiments.field_guided_movers.model import MoversAdapter, MoversConfig

        return MoversAdapter(config=MoversConfig(**cfg))

    registry.register("pymunk", _mover_factory)
    return registry


def build_field_guided_movers_operations(
    pde: PyPDEAdapter,
    movers: MoversAdapter,
    config: MoversConfig,
    trajectory: MoversTrajectory,
    state: MoversState,
) -> dict[str, Callable[[float], None]]:
    """Build the ordered coupling-operation handlers for the movers world."""

    def run_field_step(dt: float) -> None:
        pde.step(config.macro_timestep)

    def run_movers_force(dt: float) -> None:
        total_force = 0.0
        total_grad = 0.0
        if config.apply_forces:
            space = movers._space
            if space is not None:
                for m in space.movers:
                    fx, fy = gradient_force(
                        pde, m.position,
                        config.force_fmax, config.force_gsat,
                    )
                    movers.apply_force(m.id, fx, fy)
                    total_force += math.hypot(fx, fy)
                    gx, gy = pde.gradient(m.position[0], m.position[1], "u")
                    total_grad += math.hypot(gx, gy)
        state.total_force = total_force
        state.total_grad = total_grad

    def run_movers_step(dt: float) -> None:
        movers.step(config.macro_timestep)

    def run_field_source(dt: float) -> None:
        sources_present = 0
        if config.apply_sources:
            space = movers._space
            if space is not None:
                sources = [mover_source(m, config) for m in space.movers]
                pde.apply_sources(sources)
                sources_present = len(sources)
        state.sources_present = sources_present

    def run_observables_record(dt: float) -> None:
        field = pde.get_field()
        if field is None:
            return
        mover_positions = movers.get_positions()
        n = max(1, len(mover_positions))
        trajectory.t_field.append(field.t)
        trajectory.u_snaps.append(field.u.copy())

        for mover_id, pos in mover_positions.items():
            trajectory.positions.setdefault(mover_id, []).append(pos)

        speed_sum = 0.0
        state_snap = movers.get_state()
        for vel in state_snap["velocities"].values():
            speed_sum += float(np.hypot(vel[0], vel[1]))
        trajectory.speeds.append(speed_sum / n)
        trajectory.force_mags.append(state.total_force / n)
        trajectory.gradient_mags.append(state.total_grad / n)

    return {
        "field.step": run_field_step,
        "movers.force": run_movers_force,
        "movers.step": run_movers_step,
        "field.source": run_field_source,
        "observables.record": run_observables_record,
    }