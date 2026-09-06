"""Composition layer: from a declarative world to a running engine.

The composer is the single place where a ``WorldDefinition`` becomes a live
``AlchemistEngine``:

1. ``build_components`` -- construct the adapters requested by the world via
   the explicit ``ComponentRegistry`` (unknown component ids fail loudly).
2. ``resolve_capabilities`` -- check that every adapter's ``requires`` and the
   world's declared ``requires`` are all provided by some adapter in the set.
3. ``compose_into`` / ``compose`` -- install the adapters, validate the world's
   schedule against the supplied operations registry, and build the core
   ``StepScheduler`` that actually drives the run.

Unknown schedule operations are rejected at compose time (before any state is
mutated), which is exactly what the Task 1.2 scheduler contract requires.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sim_alchemist.core.capabilities import CapabilitySet, SimulationEngine
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.registry import ComponentRegistry, UnknownComponentError
from sim_alchemist.core.world import WorldDefinition


class CompositionError(Exception):
    """Base error for any failure during world composition."""


class UnresolvedCapabilityError(CompositionError):
    """At least one required capability is not provided by any adapter."""


def resolve_capabilities(
    adapters: Sequence[SimulationEngine],
    required: list[str] | None = None,
) -> None:
    """Verify every adapter's requires and the world's requires are satisfied.

    Raises ``UnresolvedCapabilityError`` listing the missing capability names.
    """
    provided = CapabilitySet()
    for adapter in adapters:
        provided = provided | adapter.provides

    needed: set[str] = set(required or [])
    for adapter in adapters:
        needed.update(c.name for c in adapter.requires)

    missing = sorted(name for name in needed if not provided.has(name))
    if missing:
        raise UnresolvedCapabilityError(
            f"Unresolved capability(ies): {', '.join(missing)}. "
            "Add a component that provides them or remove the requirement."
        )


def build_components(
    registry: ComponentRegistry,
    world: WorldDefinition,
) -> list[SimulationEngine]:
    """Construct the adapters declared by ``world`` through ``registry``.

    Raises ``UnknownComponentError`` if any component id is not registered.
    """
    adapters: list[SimulationEngine] = []
    for spec in world.components:
        if not registry.has(spec.id):
            available = ", ".join(registry.components()) or "(none registered)"
            raise UnknownComponentError(
                f"Unknown component '{spec.id}'. Registered: {available}"
            )
        adapters.append(registry.build(spec.id, spec.config))
    return adapters


def compose_into(
    engine: AlchemistEngine,
    world: WorldDefinition,
    adapters: list[SimulationEngine],
    operations: dict[str, Callable[[float], None]],
    *,
    on_step: Callable[[float, float, int], None] | None = None,
    on_initialize: Callable[[], None] | None = None,
) -> AlchemistEngine:
    """Fill a pre-created ``AlchemistEngine``/facade with a composed world.

    Constructs the schedule (validating the world's declared order against
    ``operations`` at compose time), installs the adapters, and wires the
    scheduler and optional per-step/initialize hooks.
    """
    resolve_capabilities(adapters, list(world.requires))
    engine._install(  # the composer is the designated installer
        adapters,
        world,
        operations,
        on_step=on_step,
        on_initialize=on_initialize,
    )
    return engine


def compose(
    world: WorldDefinition,
    registry: ComponentRegistry,
    operations: dict[str, Callable[[float], None]] | Callable[[list[SimulationEngine]], dict[str, Callable[[float], None]]],
    *,
    on_step: Callable[[float, float, int], None] | None = None,
    on_initialize: Callable[[list[SimulationEngine]], None] | None = None,
) -> AlchemistEngine:
    """Create, install, and return a plain ``AlchemistEngine`` for ``world``.

    ``operations`` may be a ready-to-use dict of handlers or a factory
    ``(adapters) -> dict`` so the handlers can close over the exact adapter
    instances the composer built.  ``on_initialize`` is adapter-aware: it
    receives the installed adapters (so e.g. a Mesa component can be wired to
    the field/wallspace produced by other components).
    """
    adapters = build_components(registry, world)
    engine = AlchemistEngine()

    ops = operations(adapters) if callable(operations) else operations

    init: Callable[[], None] | None = None
    if on_initialize is not None:
        def init_hook() -> None:
            on_initialize(adapters)

        init = init_hook

    return compose_into(
        engine,
        world,
        adapters,
        ops,
        on_step=on_step,
        on_initialize=init,
    )
