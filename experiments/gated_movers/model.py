"""Experiment D gated-mover model: field-sensing Mesa agents + Pymunk movers.

The experiment owns:
    * its science (``GatedMoversConfig``, ``GatedMoverAgent``/``GatedMoversModel``,
      ``GatedMesaAdapter``, ``GatedMoversTrajectory``), and
    * its thin engine-style runner (``run_gated_movers``).

All *coupling* -- the declared macro-step order, the contracts, and the
declarative world definition -- lives in
``experiments.gated_movers.coupling``.

The gate rule is a hysteresis switch per mover:

    * while the gate is open and the sensed activator field ``u`` at the
      mover's current position is >= ``gate_threshold``, the gate stays open;
    * when ``u`` drops below the threshold the gate closes and a cooldown of
      ``gate_cooldown`` macro steps begins;
    * the gate may only re-open once the cooldown has elapsed *and* ``u`` is
      back at/above the threshold.

The ``pymunk`` adapter is Experiment B's ``MoversAdapter`` untouched; it is
constructed with the superset ``GatedMoversConfig`` (duck-typed, same field
names) so the move/deposit physics is byte-identical to Experiment B's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from experiments.field_guided_movers.model import (
    MoversAdapter,
    MoversConfig,
    MoversTrajectory,
)
from experiments.gated_movers.coupling import (
    GATED_MOVERS_CONTRACTS,
    GATED_MOVERS_SCHEDULE,
    GatedMoversState,
    build_gated_movers_operations,
    build_gated_movers_registry,
    build_gated_movers_world,
)
from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event, EventType

__all__ = [
    "GATED_MOVERS_SCHEDULE",
    "GatedMesaAdapter",
    "GatedMoversConfig",
    "GatedMoversTrajectory",
    "run_gated_movers",
]


@dataclass
class GatedMoversConfig(MoversConfig):
    """All parameters of one Gated Mover Morphogenesis world.

    Superset of Experiment B's ``MoversConfig``: the mover/field/physics
    defaults are identical, and the three gating dimensions are added.
    """

    gate_threshold: float = 0.5
    gate_cooldown: int = 4
    source_amplitude: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        data = super().as_dict()
        data["gate_threshold"] = self.gate_threshold
        data["gate_cooldown"] = self.gate_cooldown
        data["source_amplitude"] = self.source_amplitude
        return data


@dataclass
class GatedAgentConfig:
    """One gating agent's static configuration (seeded position only)."""

    id: int
    x: float
    y: float


@dataclass
class GatedMoverAgent:
    """A single gate attached to one mover.

    ``gate_open`` starts True (all movers begin with their source armed); the
    hysteresis rule in ``GatedMoversModel.step`` evolves it.  ``switched``
    records whether the gate changed state on the most recent step.
    """

    unique_id: int
    x: float
    y: float
    position: tuple[float, float] = field(default=(0.0, 0.0))
    sensed_u: float = field(default=0.0)
    gate_open: bool = field(default=True)
    cooldown: int = field(default=0)
    switched: bool = field(default=False)


class GatedMoversModel:
    """Mesa-style agent model: one gating agent per mover, no walls.

    The model is fully deterministic (no randomness); the ``seed`` exists for
    adapter parity with the core Mesa adapter.  It senses the field through a
    ``PyPDEAdapter``-provided scalar sampler and applies the threshold-plus-
    cooldown hysteresis rule using the mutable ``config.gate_*`` values, so a
    world whose ``config`` was mutated re-gates accordingly.
    """

    def __init__(
        self,
        field: Any,
        config: GatedMoversConfig,
        agent_configs: list[dict[str, Any]],
        *,
        seed: int = 0,
    ) -> None:
        self.field = field
        self.config = config
        self.seed = seed
        self.agents: list[GatedMoverAgent] = [
            GatedMoverAgent(
                unique_id=int(ac["id"]),
                x=float(ac["x"]),
                y=float(ac["y"]),
            )
            for ac in agent_configs
        ]
        self._mover_positions: dict[int, tuple[float, float]] = {}

    def set_mover_positions(self, positions: dict[int, tuple[float, float]]) -> None:
        self._mover_positions = {int(k): (float(v[0]), float(v[1])) for k, v in positions.items()}

    @property
    def threshold(self) -> float:
        return float(self.config.gate_threshold)

    @property
    def cooldown_steps(self) -> int:
        return int(self.config.gate_cooldown)

    @property
    def active_count(self) -> int:
        return sum(1 for a in self.agents if a.gate_open)

    @property
    def closed_count(self) -> int:
        return sum(1 for a in self.agents if not a.gate_open)

    @property
    def switch_count(self) -> int:
        return sum(1 for a in self.agents if a.switched)

    @switch_count.setter
    def switch_count(self, value: int) -> None:
        for agent in self.agents:
            if value == 0:
                agent.switched = False

    @property
    def open_movers(self) -> set[int]:
        return {a.unique_id for a in self.agents if a.gate_open}

    def step(self) -> None:
        threshold = self.threshold
        cooldown = self.cooldown_steps
        for agent in self.agents:
            px, py = self._mover_positions.get(agent.unique_id, (agent.x, agent.y))
            agent.position = (px, py)
            if self.field is None:
                u = agent.sensed_u
            else:
                u = float(self.field.sample(px, py, "u"))
            agent.sensed_u = u
            agent.switched = False
            if agent.gate_open:
                if u < threshold:
                    agent.gate_open = False
                    agent.cooldown = cooldown
                    agent.switched = True
            else:
                if agent.cooldown > 0:
                    agent.cooldown -= 1
                if agent.cooldown == 0 and u >= threshold:
                    agent.gate_open = True
                    agent.switched = True


class GatedMesaAdapter(BaseAdapter):
    """Mesa adapter for the gating agent model (Experiment D).

    Same capability surface as the core ``MesaAdapter`` (``agent_population``,
    ``agent_step``, ``field_sensing``, ``agent_intentions`` requiring
    ``scalar_field``; variant ``None``), so the repository's ``mesa`` binding
    keeps its capability identity.  The gating science lives in
    ``GatedMoversModel``; this adapter only wires the injected field, mover
    positions, and mutable config into the model on step.
    """

    def __init__(
        self,
        agent_configs: list[dict[str, Any]] | None = None,
        seed: int = 0,
        macro_timestep: float = 0.2,
    ) -> None:
        provides = CapabilitySet()
        provides.add(Capability.from_dict("agent_population", "1.0"))
        provides.add(Capability.from_dict("agent_step", "1.0"))
        provides.add(Capability.from_dict("field_sensing", "1.0"))
        provides.add(Capability.from_dict("agent_intentions", "1.0"))

        requires = CapabilitySet()
        requires.add(Capability.from_dict("scalar_field", "1.0"))

        super().__init__(
            engine_id="mesa",
            provides=provides,
            requires=requires,
            native_timestep=macro_timestep,
        )
        self._state_keys = ("agents", "intentions")

        self._config = {
            "agent_configs": agent_configs or [],
            "seed": seed,
            "macro_timestep": macro_timestep,
        }
        self._model: GatedMoversModel | None = None
        self._field: Any = None
        self._gated_config: GatedMoversConfig | None = None

    def set_config(self, config: GatedMoversConfig) -> None:
        """Inject the mutable run config (reads ``config.gate_*`` each step)."""
        self._gated_config = config

    def set_field(self, field: Any) -> None:
        self._field = field

    def set_mover_positions(self, positions: dict[int, tuple[float, float]]) -> None:
        if self._model is not None:
            self._model.set_mover_positions(positions)

    def create_model(self) -> None:
        if self._model is not None:
            return
        if self._gated_config is None or self._field is None:
            return
        self._model = GatedMoversModel(
            field=self._field,
            config=self._gated_config,
            agent_configs=self._config["agent_configs"],
            seed=self._config["seed"],
        )

    def step(self, dt: float) -> None:
        self.create_model()
        if self._model is not None:
            self._model.step()

    def get_model(self) -> GatedMoversModel | None:
        return self._model

    def get_state(self) -> dict[str, Any]:
        if self._model is None:
            return {"agents": [], "intentions": {}}
        agents = [
            {
                "id": a.unique_id,
                "position": a.position,
                "sensed_u": a.sensed_u,
                "gate_open": a.gate_open,
                "cooldown": a.cooldown,
            }
            for a in self._model.agents
        ]
        scale = self._gated_config.source_amplitude if self._gated_config is not None else 1.0
        intentions = {
            a.unique_id: {
                "open": a.gate_open,
                "amplitude": scale if a.gate_open else 0.0,
            }
            for a in self._model.agents
        }
        return {"agents": agents, "intentions": intentions}

    def apply_event(self, event: Event) -> bool:
        return event.type == EventType.FIELD_STATE

    def shutdown(self) -> None:
        self._model = None
        self._field = None


@dataclass
class GatedMoversTrajectory(MoversTrajectory):
    """Full recorded outcome of one Gated Mover Morphogenesis run.

    Adds the per-macro-step gate bookkeeping to Experiment B's trajectory:
    how many gates were open / suppressed (closed), how many switched state,
    and how many sources were actually deposited in that step.
    """

    active_gates: list[int] = field(default_factory=list)
    suppressed_gates: list[int] = field(default_factory=list)
    gate_switches: list[int] = field(default_factory=list)
    gate_deposits: list[int] = field(default_factory=list)


def run_gated_movers(config: GatedMoversConfig) -> GatedMoversTrajectory:
    """Run one composed Gated Mover Morphogenesis world."""
    engine = GatedMoversEngine(config=config)
    return engine.run()


class GatedMoversEngine(AlchemistEngine):
    """Experiment D facade: field + gating agents + point movers.

    Macro-step ordering (declared, not hard-coded):

        1. evolve the reaction-diffusion field
        2. sense ``u`` at each mover's current position; evolve the gates
        3. translate gate intentions (open/closed) into the source scaling
        4. sample field gradient at each mover COM -> bounded force
        5. integrate Pymunk dynamics (force, damping, bounds clamp)
        6. deposit source/sink only through open gates, scaled by amplitude
        7. record observables

    The ordering is *declared* as ``GATED_MOVERS_SCHEDULE`` and dispatched by
    the core ``StepScheduler``; this experiment owns only the coupling rules.
    """

    SCHEDULE: tuple[str, ...] = GATED_MOVERS_SCHEDULE

    def __init__(self, config: GatedMoversConfig) -> None:
        super().__init__()

        self._config = config
        self.trajectory = GatedMoversTrajectory(config=config)

        world = build_gated_movers_world(config)
        adapters = build_components(build_gated_movers_registry(), world)
        self._pde_adapter = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde"))
        self._movers_adapter = cast(MoversAdapter, adapter_by_id(adapters, "pymunk"))
        self._mesa_adapter = cast(GatedMesaAdapter, adapter_by_id(adapters, "mesa"))

        state = GatedMoversState()
        operations = build_gated_movers_operations(
            self._pde_adapter,
            self._movers_adapter,
            self._mesa_adapter,
            self._config,
            self.trajectory,
            state,
        )

        def _gated_initialize() -> None:
            self._pde_adapter.set_event_bus(self.event_bus)
            self._movers_adapter.set_event_bus(self.event_bus)
            self._mesa_adapter.set_event_bus(self.event_bus)
            field = self._pde_adapter.get_field()
            self._mesa_adapter.set_field(field)
            self._mesa_adapter.set_mover_positions(self._movers_adapter.get_positions())
            if field is not None and self.trajectory.start_u.size == 0:
                self.trajectory.start_u = field.u.copy()

        def _on_step(time: float, dt: float, step: int) -> None:
            time_event = Event.time_step("alchemist", time, dt)
            self.event_bus.publish(time_event)

        compose_into(
            self,
            world,
            adapters,
            operations,
            on_step=_on_step,
            on_initialize=_gated_initialize,
            contracts=GATED_MOVERS_CONTRACTS,
        )

    def run(self) -> GatedMoversTrajectory:  # type: ignore[override]
        """Run the full composed world and return its trajectory."""
        super().run()
        assert self._scheduler is not None
        self.trajectory.trace = self._scheduler.trace
        return self.trajectory