"""Mesa adapter for agent-based sensing and decisions."""

from __future__ import annotations

from typing import Any

from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core.capabilities import Capability, CapabilitySet
from sim_alchemist.core.events import Event, EventType


class MesaAdapter(BaseAdapter):
    """Adapter wrapping Mesa agent model."""

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

        self._config = {
            "agent_configs": agent_configs or [],
            "seed": seed,
        }
        self._model = None
        self._field = None

    def initialize(self, config: dict[str, Any]) -> None:
        from chemomech.agents import AgentConfig

        super().initialize(config)

        # The model needs references to field and wallspace
        # These will be set via events or direct injection
        agent_cfgs = [
            AgentConfig(**ac) for ac in self._config["agent_configs"]
        ]
        # Note: model initialization deferred until field/wallspace are available
        self._agent_cfgs = agent_cfgs

    def set_field(self, field) -> None:
        """Inject field reference for agent sensing."""
        self._field = field

    def set_wallspace(self, wallspace) -> None:
        """Inject wallspace reference for agent decisions."""
        self._wallspace = wallspace

    def create_model(self) -> None:
        """Create the Mesa model once field and wallspace are available."""
        from chemomech.agents import ChemoMechanicalModel
        if self._field is not None and hasattr(self, '_wallspace'):
            self._model = ChemoMechanicalModel(
                field=self._field,
                wallspace=self._wallspace,
                agent_configs=self._agent_cfgs,
                seed=self._config["seed"],
            )

    def step(self, dt: float) -> None:
        """Step the agent model and publish decisions."""
        if self._model is None:
            self.create_model()
        if self._model is not None:
            self._model.step()
            self._publish_decisions()

    def get_state(self) -> dict[str, Any]:
        if self._model is None:
            return {}
        return {
            "agents": [
                {
                    "id": agent.unique_id,
                    "position": (agent.x, agent.y),
                    "pending_wall": agent.pending_wall,
                    "pending_dissolve": [w.id for w in agent.pending_dissolve],
                    "history": agent.history[-1] if agent.history else None,
                }
                for agent in self._model.agents
            ],
        }

    def _publish_decisions(self) -> None:
        if self._model is None:
            return
        decisions = {}
        for i, agent in enumerate(self._model.agents):
            if agent.pending_wall is not None:
                decisions[f"agent_{i}"] = {
                    "build": True,
                    "wall": agent.pending_wall,
                }
            if agent.pending_dissolve:
                decisions[f"agent_{i}"] = decisions.get(f"agent_{i}", {})
                decisions[f"agent_{i}"]["dissolve"] = [w.id for w in agent.pending_dissolve]

        if decisions:
            event = Event.agent_decision(
                self.engine_id,
                self._field.t if self._field else 0.0,
                decisions,
            )
            self.publish(event)

    def apply_event(self, event: Event) -> bool:
        return event.type == EventType.FIELD_STATE

    def shutdown(self) -> None:
        self._model = None
        self._field = None