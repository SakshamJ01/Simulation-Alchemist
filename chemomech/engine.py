"""Chemo-mechanical engine: the Experiment A facade over the composition core.

Task 1.3: this module is a *thin facade*.  The science (PDE equations, wall
physics, Mesa behaviour) stays in the adapters; the coupling rules and the
declared macro-step order live in ``chemomech/coupling.py``; and the actual
composition (adapter construction, capability resolution, schedule
validation, scheduler dispatch) is done by the generic core composer
(``sim_alchemist.core.composer``) against a plain ``AlchemistEngine``.

The facade exists to:
  * own the ``Trajectory`` object (the validated observable record),
  * keep the ``ChemomechanicalEngine`` API stable (``SCHEDULE``, ``config``,
    ``run()`` returning a trajectory) for the existing test suite,
  * remain a true ``AlchemistEngine`` subclass.

There is no experiment-specific scheduling logic in this class: ``run()``
delegates entirely to the generic engine + core ``StepScheduler``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from chemomech.coupling import (
    MORPHOGENESIS_SCHEDULE,
    MorphogenesisState,
    build_morphogenesis_operations,
    build_morphogenesis_world,
)
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.composer import build_components, compose_into
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.registry import default_registry

if TYPE_CHECKING:
    from chemomech.simulation import Trajectory, WorldConfig


@dataclass
class ChemomechanicalEngine(AlchemistEngine):
    """
    Chemo-mechanical engine facade.

    Declared macro-step ordering in ``SCHEDULE`` (Task 1.2).  The ordering
    is data, not code: it is resolved through ``build_morphogenesis_world``
    and dispatched by the core ``StepScheduler``.
    """

    config: WorldConfig
    trajectory: Trajectory = field(default_factory=lambda: None)  # type: ignore[assignment] # set in __post_init__

    # Declared, deterministic macro-step ordering.  Reproduces the exact
    # validated baseline ordering as resolved by the morphogenesis coupling.
    SCHEDULE: tuple[str, ...] = MORPHOGENESIS_SCHEDULE

    def __post_init__(self) -> None:
        from chemomech.simulation import Trajectory

        super().__init__()

        self.trajectory = Trajectory(config=self.config)

        world = build_morphogenesis_world(self.config)
        adapters = build_components(default_registry(), world)
        pde_a, pym_a, mesa_a = cast(
            tuple[PyPDEAdapter, PymunkAdapter, MesaAdapter], adapters
        )
        self._pde_adapter, self._pymunk_adapter, self._mesa_adapter = (
            pde_a,
            pym_a,
            mesa_a,
        )

        state = MorphogenesisState()
        operations = build_morphogenesis_operations(
            self._pde_adapter,
            self._pymunk_adapter,
            self._mesa_adapter,
            self.config,
            self.trajectory,
            state,
        )

        def _morphogenesis_initialize() -> None:
            pde_field = self._pde_adapter.get_field()
            pymunk_wallspace = self._pymunk_adapter._wallspace
            self._mesa_adapter.set_field(pde_field)
            self._mesa_adapter.set_wallspace(pymunk_wallspace)
            self._mesa_adapter.create_model()

        compose_into(
            self,
            world,
            adapters,
            operations,
            on_initialize=_morphogenesis_initialize,
        )

    def run(self) -> Any:  # type: ignore[override]  # returns the materialized Trajectory
        """Run the full simulation and return the recorded trajectory."""
        super().run()
        return self.trajectory