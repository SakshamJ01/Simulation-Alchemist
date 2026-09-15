"""Experiment D coupling: gated mover morphogenesis schedule, contracts, world.

Experiment D composes the existing single-variant Mesa capability surface
(agent sensing + intentions) with the py-pde field and the point-mover Pymunk
variant from Experiment B.  The science is *new*: the Mesa agent model does not
build walls -- it gates chemical deposition.  Each mover owns a gate that is
open while the sensed activator field ``u`` at the mover's current position
stays at or above ``gate_threshold``; when ``u`` drops below the threshold the
gate closes for ``gate_cooldown`` macro steps (hysteresis) before it may
re-open.  The ``field.source`` operation deposits the mover's source/sink only
when that mover's gate is open, scaled by ``source_amplitude``.

The declared macro-step order lives in ``GATED_MOVERS_SCHEDULE`` and the
operation handlers are closures built by ``build_gated_movers_operations``,
dispatched by the core ``StepScheduler``.  The declarative ``WorldDefinition``
builder plus a registry builder make this world composable by the generic core
composer.

Stage 1 scope (see TASK_3.0_DESIGN.md, Build Stage 1): this module only
*declares* the composition -- the coupling contracts, the schedule, the
template, the world builder, and the registry override.  Nothing is executed
here and no parameter sweep is declared yet (the ``MutationSpace`` binding is
delegated to Task 3.0 Build Stage 3).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.composition import ComponentBinding
from sim_alchemist.core.contracts import CouplingContract
from sim_alchemist.core.registry import ComponentRegistry, default_registry
from sim_alchemist.core.templates import CouplingTemplate
from sim_alchemist.core.world import ComponentSpec, WorldDefinition

if TYPE_CHECKING:
    from experiments.field_guided_movers.model import MoversAdapter


GATED_MOVERS_SCHEDULE: tuple[str, ...] = (
    "field.step",
    "agents.step",
    "agents.apply",
    "movers.force",
    "movers.step",
    "field.source",
    "observables.record",
)

#: The operation names ``build_gated_movers_operations`` registers
#: (co-located with the schedule so the template can verify it).
GATED_MOVERS_OPERATIONS: tuple[str, ...] = GATED_MOVERS_SCHEDULE


GATED_MOVERS_CONTRACTS: tuple[CouplingContract, ...] = (
    CouplingContract(
        name="field-sensing",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("u", "array_1d"), ("v", "array_1d")),
        transform="field-sensing",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
        variant="movers",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="mover-gate",
        producer="mesa",
        producer_capability="agent_intentions",
        consumer="pymunk",
        consumer_capability="rigid_body",
        payload=(("intentions", "array_1d"),),
        transform="gated-source",
        variant="movers",
        coordinate_system="unit-square-2d",
    ),
    CouplingContract(
        name="mover-source",
        producer="pymunk",
        producer_capability="geometry_provider",
        consumer="py-pde",
        consumer_capability="field_sources",
        payload=(("positions", "vec2_list"),),
        transform="mover-source",
        variant="movers",
        coordinate_system="unit-square-2d",
    ),
)


@dataclass
class GatedMoversState:
    """Per-macro-step scratch shared across the schedule operations."""

    total_force: float = 0.0
    total_grad: float = 0.0
    sources_present: int = 0
    active_gates: int = 0
    suppressed_gates: int = 0
    gate_switches: int = 0
    gate_deposits: int = 0
    deposits_total: int = 0


def gated_mover_source(
    mover: Any,
    config: Any,
    *,
    scale: float,
) -> dict[str, float]:
    """Experiment rule: mover position -> gated chemical source/sink.

    ``scale`` is the gate-derived amplitude (``source_amplitude`` when the
    mover's gate is open, ``0.0`` when closed): the activator deposit and the
    inhibitor consumption are both multiplied by the same scale, so a closed
    gate deposits nothing without changing the source geometry.
    """
    return {
        "x": mover.position[0],
        "y": mover.position[1],
        "u": config.source_u * scale,
        "v": config.source_v * scale,
        "radius": config.source_radius,
    }


def build_gated_movers_world(config: Any) -> WorldDefinition:
    """The declarative world definition of the gated movers composition.

    The Mesa component carries one agent per mover (id + seeded position only;
    the gating rule reads the mutable ``config.gate_*`` values at run time so
    parameter mutations of this world's top-level ``config`` are honoured).
    """
    agent_configs = [
        {"id": i, "x": x, "y": y}
        for i, (x, y) in enumerate(config.positions())
    ]
    return WorldDefinition(
        id="gated_movers",
        components=(
            ComponentSpec("py-pde", {
                "n": config.n, "du": config.du, "dv": config.dv,
                "a": config.a, "b": config.b, "dt": config.pde_dt,
                "seed": config.seed, "field_step": config.macro_timestep,
            }),
            ComponentSpec("mesa", {
                "agent_configs": agent_configs, "seed": config.seed,
                "macro_timestep": config.macro_timestep,
            }),
            ComponentSpec("pymunk", config.as_dict()),
        ),
        requires=("agent_population", "reaction_diffusion", "rigid_body", "field_gradient"),
        schedule=GATED_MOVERS_SCHEDULE,
        macro_timestep=config.macro_timestep,
        max_steps=config.n_steps,
        seed=config.seed,
        config=config.as_dict(),
    )


def build_gated_movers_template() -> CouplingTemplate:
    """The declared coupling template of the gated mover composition.

    Derived from the experiment's world builder (default ``GatedMoversConfig``)
    so the template and the world it generates cannot drift.  The config class
    is imported lazily to keep the module import graph acyclic.
    """
    from experiments.gated_movers.model import GatedMoversConfig

    world = build_gated_movers_world(GatedMoversConfig())
    return CouplingTemplate(
        name="gated_movers",
        bindings=(
            ComponentBinding("mesa"),
            ComponentBinding("py-pde"),
            ComponentBinding("pymunk", "movers"),
        ),
        world_id=world.id,
        contracts=GATED_MOVERS_CONTRACTS,
        schedule=GATED_MOVERS_SCHEDULE,
        operations=GATED_MOVERS_OPERATIONS,
        requires=world.requires,
        executor_ref="experiments.gated_movers.model.run_gated_movers",
        component_configs={spec.id: dict(spec.config) for spec in world.components},
        macro_timestep=world.macro_timestep,
        max_steps=world.max_steps,
        seed=world.seed,
        config=dict(world.config),
    )


def build_gated_movers_registry() -> ComponentRegistry:
    """Core registry with the gating ``mesa`` variant and the point-mover
    ``pymunk`` variant.

    The ``pymunk`` component id is reused exactly as Experiment B declares it
    (the point-mover ``MoversAdapter``), but constructed from the superset
    ``GatedMoversConfig`` so the gate parameters ride in the same body config.
    The ``mesa`` component id is overridden with the experiment-owned gating
    agent adapter (same capability surface as the core Mesa adapter, so the
    repository universe is unchanged).
    """
    registry = default_registry()

    def _mesa_factory(cfg: dict[str, Any]) -> Any:
        from experiments.gated_movers.model import GatedMesaAdapter

        kwargs = {k: cfg[k] for k in ("agent_configs", "seed", "macro_timestep") if k in cfg}
        return GatedMesaAdapter(**kwargs)

    def _mover_factory(cfg: dict[str, Any]) -> MoversAdapter:
        from experiments.field_guided_movers.model import MoversAdapter
        from experiments.gated_movers.model import GatedMoversConfig

        return MoversAdapter(config=GatedMoversConfig(**cfg))

    registry.register("mesa", _mesa_factory)
    registry.register("pymunk", _mover_factory)
    return registry


def build_gated_movers_operations(
    pde: PyPDEAdapter,
    movers: MoversAdapter,
    mesa: Any,
    config: Any,
    trajectory: Any,
    state: GatedMoversState,
) -> dict[str, Callable[[float], None]]:
    """Build the ordered coupling-operation handlers for the gated world."""
    from experiments.field_guided_movers.coupling import gradient_force

    mesa.set_config(config)

    def run_field_step(dt: float) -> None:
        pde.step(config.macro_timestep)

    def run_agents_step(dt: float) -> None:
        mesa.set_mover_positions(movers.get_positions())
        mesa.step(config.macro_timestep)

    def run_agents_apply(dt: float) -> None:
        model = mesa.get_model()
        if model is None:
            state.active_gates = 0
            state.suppressed_gates = len(movers.get_positions())
            state.gate_switches = 0
            return
        state.active_gates = model.active_count
        state.suppressed_gates = model.closed_count
        state.gate_switches = model.switch_count
        model.switch_count = 0

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
        gate_deposits = 0
        if config.apply_sources:
            space = movers._space
            model = mesa.get_model()
            if space is not None and model is not None:
                open_ids = model.open_movers
                sources: list[dict[str, float]] = []
                for m in space.movers:
                    if m.id in open_ids:
                        sources.append(
                            gated_mover_source(
                                m, config, scale=config.source_amplitude
                            )
                        )
                        gate_deposits += 1
                pde.apply_sources(sources)
                sources_present = len(sources)
        state.sources_present = sources_present
        state.gate_deposits = gate_deposits
        state.deposits_total += gate_deposits

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
            speed_sum += float(math.hypot(vel[0], vel[1]))
        trajectory.speeds.append(speed_sum / n)
        trajectory.force_mags.append(state.total_force / n)
        trajectory.gradient_mags.append(state.total_grad / n)

        trajectory.active_gates.append(state.active_gates)
        trajectory.suppressed_gates.append(state.suppressed_gates)
        trajectory.gate_switches.append(state.gate_switches)
        trajectory.gate_deposits.append(state.gate_deposits)

    return {
        "field.step": run_field_step,
        "agents.step": run_agents_step,
        "agents.apply": run_agents_apply,
        "movers.force": run_movers_force,
        "movers.step": run_movers_step,
        "field.source": run_field_source,
        "observables.record": run_observables_record,
    }