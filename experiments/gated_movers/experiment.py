"""Experiment D executor declarations for the generic evaluation layer (Task 3.0).

Stage 1 scope: this module exposes ``build_gated_movers_metrics`` and
``run_gated_movers_world`` so the composition catalog can evaluate Experiment D
with the generic ``WorldDefinition -> ExecOutcome`` contract.  Nothing else is
changed.

PARAMETER_SPECS declares the three gating dimensions; a future Stage 3 will
bind them to a ``MutationSpace`` inside the cross-composition sweep layer.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from experiments.field_guided_movers.experiment import _field_entropy
from experiments.field_guided_movers.model import MoversAdapter
from experiments.gated_movers.coupling import (
    GATED_MOVERS_CONTRACTS,
    GatedMoversState,
    build_gated_movers_operations,
    build_gated_movers_registry,
)
from experiments.gated_movers.model import (
    GatedMesaAdapter,
    GatedMoversConfig,
    GatedMoversTrajectory,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event
from sim_alchemist.core.mutation import ParameterSpec
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "PARAMETER_SPECS",
    "build_gated_movers_metrics",
    "run_gated_movers_world",
    "specs_by_path",
]

PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        path="config.gate_threshold",
        description="activator u threshold below which a mover's source gate closes",
        minimum=0.0,
        maximum=1.0,
    ),
    ParameterSpec(
        path="config.gate_cooldown",
        description="macro steps a closed gate must wait before it may re-open",
        minimum=0,
        maximum=20,
    ),
    ParameterSpec(
        path="config.source_amplitude",
        description="scale factor multiplied into activator/inhibitor deposit when gate is open",
        minimum=0.0,
        maximum=2.0,
    ),
)


def specs_by_path() -> dict[str, ParameterSpec]:
    return {s.path: s for s in PARAMETER_SPECS}


def build_gated_movers_metrics(trajectory: GatedMoversTrajectory) -> dict[str, float]:
    """Collapse a gated-movers trajectory to the compact metric summary.

    The first eight metrics mirror Experiment B verbatim; the last four are
    new gating-specific quantities.
    """
    final = np.asarray(trajectory.final_u).copy()
    displacements = trajectory.net_displacements()
    n_steps = max(1, len(trajectory.t_field))
    return {
        # --- Experiment B parity ---
        "final_field_mean": float(final.mean()),
        "final_field_std": float(final.std()),
        "field_entropy": _field_entropy(final),
        "n_movers": float(trajectory.n_movers),
        "total_displacement": float(sum(displacements.values())),
        "mean_speed": float(np.mean(trajectory.speeds)) if trajectory.speeds else 0.0,
        "mean_force": float(np.mean(trajectory.force_mags)) if trajectory.force_mags else 0.0,
        "mean_gradient": float(np.mean(trajectory.gradient_mags)) if trajectory.gradient_mags else 0.0,
        # --- Experiment D: gating specifics ---
        "deposition_events": float(sum(trajectory.gate_deposits)),
        "deposition_suppression": float(sum(trajectory.suppressed_gates)),
        "active_gates": float(np.mean(trajectory.active_gates)) if trajectory.active_gates else 0.0,
        "gate_switch_rate": float(sum(trajectory.gate_switches)) / n_steps,
    }


def run_gated_movers_world(world: WorldDefinition) -> ExecOutcome:
    """Executor: run *any* gated-movers world through the generic core path.

    Mirrors the plain ``compose`` path; adapters are rebuilt per call so
    re-runs are independently seeded by the world's own ``seed`` (deterministic
    replay).
    """
    config = GatedMoversConfig(**dict(world.config))
    trajectory = GatedMoversTrajectory(config=config)
    state = GatedMoversState()

    engine = AlchemistEngine()
    registry = build_gated_movers_registry()
    adapters = build_components(registry, world)

    def _ops() -> dict[str, Any]:
        return build_gated_movers_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(MoversAdapter, adapter_by_id(adapters, "pymunk")),
            cast(GatedMesaAdapter, adapter_by_id(adapters, "mesa")),
            config,
            trajectory,
            state,
        )

    def _initialize() -> None:
        cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).set_event_bus(engine.event_bus)
        cast(MoversAdapter, adapter_by_id(adapters, "pymunk")).set_event_bus(engine.event_bus)
        mesa_adapter = cast(GatedMesaAdapter, adapter_by_id(adapters, "mesa"))
        mesa_adapter.set_event_bus(engine.event_bus)
        field = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).get_field()
        mesa_adapter.set_field(field)
        mesa_adapter.set_mover_positions(cast(MoversAdapter, adapter_by_id(adapters, "pymunk")).get_positions())
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    def _on_step(time: float, dt: float, step: int) -> None:
        engine.event_bus.publish(Event.time_step("alchemist", time, dt))

    compose_into(
        engine,
        world,
        adapters,
        _ops(),
        on_step=_on_step,
        on_initialize=_initialize,
        contracts=GATED_MOVERS_CONTRACTS,
    )
    engine.run()
    metrics = build_gated_movers_metrics(trajectory)
    return ExecOutcome(world=world, metrics=metrics, trajectory=trajectory)