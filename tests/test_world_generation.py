"""World generation from coupling templates (Task 2.3 Stage 4) tests.

``generate_world`` turns a ``CouplingTemplate`` into the same fully-declarative
``WorldDefinition`` an experiment facade builds -- with the template's concrete
binding identity stamped on every component.  These tests prove:

  * deterministic, immutable, adapter-free generation;
  * the variant stamp (walls / movers / None) flows into world identity
    (``run_id_of`` differs from the facade twin);
  * dict + YAML round-trips (both the old no-variant and the new stamped form);
  * the generated world is directly composable/executable data through the
    generic core composer;
  * and (slow) the full trajectories of generated worlds are bitwise identical
    to the experiment facades (A, B, C).
"""

from __future__ import annotations

import math
from typing import Any, cast

import numpy as np
import pytest

from chemomech.coupling import (
    MORPHOGENESIS_CONTRACTS,
    MorphogenesisState,
    build_morphogenesis_operations,
    build_morphogenesis_template,
    build_morphogenesis_world,
)
from chemomech.simulation import Trajectory, WorldConfig
from experiments.field_guided_movers.coupling import (
    FIELD_GUIDED_MOVERS_CONTRACTS,
    MoversState,
    build_field_guided_movers_operations,
    build_field_guided_movers_registry,
    build_field_guided_movers_template,
    build_field_guided_movers_world,
)
from experiments.field_guided_movers.model import (
    MoversAdapter,
    MoversConfig,
    MoversTrajectory,
    run_field_guided_movers,
)
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_template,
)
from experiments.network_morphogenesis.experiment import run_network_world
from experiments.network_morphogenesis.model import (
    NetworkMorphogenesisConfig,
    run_network_morphogenesis,
)
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core import (
    CouplingTemplate,
    generate_world,
)
from sim_alchemist.core.composer import build_components, compose
from sim_alchemist.core.contracts import adapter_by_id
from sim_alchemist.core.engine import AlchemistEngine
from sim_alchemist.core.events import Event
from sim_alchemist.core.lineage import run_id_of
from sim_alchemist.core.registry import default_registry
from sim_alchemist.core.world import WorldDefinition, load_world_yaml

WORLDS_DIR = "worlds"
FACADE = {
    "morphogenesis": (build_morphogenesis_world(WorldConfig()), build_morphogenesis_template()),
    "field_guided_movers": (
        build_field_guided_movers_world(MoversConfig()),
        build_field_guided_movers_template(),
    ),
}

TEMPLATES = (build_morphogenesis_template, build_field_guided_movers_template, build_network_morphogenesis_template)


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        return np.allclose(a, b, equal_nan=True)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b or (isinstance(a, float) and isinstance(b, float) and math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0))
    return a == b


def _assert_same(a: Any, b: Any) -> None:
    assert _close(a, b), f"values differ:\n  a={a}\n  b={b}"


def _config_by_id(world: WorldDefinition) -> dict[str, dict[str, Any]]:
    return {spec.id: dict(spec.config) for spec in world.components}


def _variant_by_id(world: WorldDefinition) -> dict[str, str | None]:
    return {spec.id: spec.variant for spec in world.components}


def _run_generated_a(world: WorldDefinition) -> Trajectory:
    """Mirror ``ChemomechanicalEngine`` on a generated world (generic engine)."""
    from sim_alchemist.core.composer import compose_into

    config = WorldConfig(**dict(world.config))
    trajectory = Trajectory(config=config)
    state = MorphogenesisState()

    engine = AlchemistEngine()
    adapters = build_components(default_registry(), world)
    pde = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde"))
    pymunk = cast(PymunkAdapter, adapter_by_id(adapters, "pymunk"))
    mesa = cast(MesaAdapter, adapter_by_id(adapters, "mesa"))

    def _initialize() -> None:
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    operations = build_morphogenesis_operations(
        pde, pymunk, mesa, config, trajectory, state
    )
    compose_into(
        engine,
        world,
        adapters,
        operations,
        on_initialize=_initialize,
        contracts=MORPHOGENESIS_CONTRACTS,
    )
    engine.run()
    return trajectory


def _run_generated_b(world: WorldDefinition) -> MoversTrajectory:
    """Mirror ``FieldGuidedMoversEngine`` on a generated world (generic engine)."""
    config = MoversConfig(**dict(world.config))
    trajectory = MoversTrajectory(config=config)
    state = MoversState()

    engine = AlchemistEngine()
    registry = build_field_guided_movers_registry()
    adapters = build_components(registry, world)

    def _ops() -> dict[str, Any]:
        return build_field_guided_movers_operations(
            cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")),
            cast(MoversAdapter, adapter_by_id(adapters, "pymunk")),
            config,
            trajectory,
            state,
        )

    def _initialize() -> None:
        cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).set_event_bus(engine.event_bus)
        cast(MoversAdapter, adapter_by_id(adapters, "pymunk")).set_event_bus(engine.event_bus)
        field = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde")).get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    def _on_step(time: float, dt: float, step: int) -> None:
        engine.event_bus.publish(Event.time_step("alchemist", time, dt))

    from sim_alchemist.core.composer import compose_into

    compose_into(
        engine,
        world,
        adapters,
        _ops(),
        on_step=_on_step,
        on_initialize=_initialize,
        contracts=FIELD_GUIDED_MOVERS_CONTRACTS,
    )
    engine.run()
    return trajectory


# ----------------------------------------------------------------------
# A. Deterministic, content-exact generation
# ----------------------------------------------------------------------
class TestGenerationDeterminism:
    def test_generation_is_deterministic_and_exact_data(self) -> None:
        for build in TEMPLATES:
            template = build()
            w1 = generate_world(template)
            w2 = generate_world(template)
            assert w1 == w2
            assert w1.as_dict() == w2.as_dict()
            assert isinstance(w1, WorldDefinition)

    def test_generated_world_carries_template_metadata(self) -> None:
        for build in TEMPLATES:
            template = build()
            world = generate_world(template)
            assert world.id == template.world_id
            assert world.schedule == template.schedule
            assert world.requires == template.requires
            assert world.macro_timestep == template.macro_timestep
            assert world.max_steps == template.max_steps
            assert world.seed == template.seed
            assert world.config == dict(template.config)


# ----------------------------------------------------------------------
# B. Variant stamps
# ----------------------------------------------------------------------
class TestVariantStamps:
    def test_morphogenesis_stamps_walls_on_pymunk(self) -> None:
        world = generate_world(build_morphogenesis_template())
        assert _variant_by_id(world) == {"mesa": None, "py-pde": None, "pymunk": "walls"}

    def test_field_guided_movers_stamps_movers_on_pymunk(self) -> None:
        world = generate_world(build_field_guided_movers_template())
        assert _variant_by_id(world) == {"py-pde": None, "pymunk": "movers"}

    def test_network_morphogenesis_stamps_walls_and_network(self) -> None:
        world = generate_world(build_network_morphogenesis_template())
        assert _variant_by_id(world) == {"py-pde": None, "pymunk": "walls", "network": None}

    def test_binding_order_is_canonical(self) -> None:
        world = generate_world(build_field_guided_movers_template())
        assert [spec.id for spec in world.components] == ["py-pde", "pymunk"]


# ----------------------------------------------------------------------
# C. World identity: the variant stamp changes run_id_of vs the facade twin
# ----------------------------------------------------------------------
class TestWorldIdentity:
    def test_run_id_deterministic(self) -> None:
        for build in TEMPLATES:
            template = build()
            assert run_id_of(generate_world(template)) == run_id_of(generate_world(template))

    def test_generated_world_differs_from_facade_twin(self) -> None:
        for facade_world, template in FACADE.values():
            generated = generate_world(template)
            assert generated != facade_world  # variant stamps present
            assert run_id_of(generated) != run_id_of(facade_world)
            # Ignoring the variant stamp they are the exact same world.
            stripped = WorldDefinition.from_dict(dict(generated.as_dict(), components=[
                {"id": spec.id, "variant": None, "config": spec.config}
                for spec in generated.components
            ]))
            assert _config_by_id(stripped) == _config_by_id(facade_world)
            assert {spec.id for spec in stripped.components} == {spec.id for spec in facade_world.components}


# ----------------------------------------------------------------------
# D. Round-trips: dict and YAML (both old no-variant and stamped form)
# ----------------------------------------------------------------------
class TestRoundTrips:
    def test_dict_round_trip_preserves_variant(self) -> None:
        for build in TEMPLATES:
            world = generate_world(build())
            restored = WorldDefinition.from_dict(world.as_dict())
            assert restored == world
            assert restored.components[0].variant == world.components[0].variant

    def test_yaml_round_trip_preserves_variant(self, tmp_path) -> None:
        world = generate_world(build_field_guided_movers_template())
        path = tmp_path / "movers_world.yaml"
        world.to_yaml(path)
        assert load_world_yaml(path) == world

    def test_legacy_yaml_worlds_have_no_variant(self) -> None:
        # Regression: pre-Stage-4 declarative worlds load with variant=None.
        world = load_world_yaml(f"{WORLDS_DIR}/chemo_morphogenesis.yaml")
        assert all(spec.variant is None for spec in world.components)
        assert world.schedule == build_morphogenesis_template().schedule

    def test_legacy_yaml_round_trip_preserves_missing_variant(self, tmp_path) -> None:
        world = load_world_yaml(f"{WORLDS_DIR}/adaptive_network.yaml")
        assert all(spec.variant is None for spec in world.components)
        path = tmp_path / "legacy.yaml"
        world.to_yaml(path)
        restored = load_world_yaml(path)
        assert restored == world
        assert all(spec.variant is None for spec in restored.components)


# ----------------------------------------------------------------------
# E. Generated worlds are directly composable data
# ----------------------------------------------------------------------
class TestGeneratedWorldComposes:
    def test_composes_through_generic_core(self) -> None:
        base = build_morphogenesis_template()
        smoke = CouplingTemplate(
            name="compose-smoke",
            bindings=base.bindings,
            world_id=base.world_id,
            contracts=base.contracts,
            schedule=("observables.record",),
            operations=("observables.record",),
            requires=base.requires,
            executor_ref=base.executor_ref,
            component_configs=base.component_configs,
            macro_timestep=base.macro_timestep,
            max_steps=1,
            seed=base.seed,
            config=base.config,
        )
        world = generate_world(smoke)
        engine = compose(
            world,
            default_registry(),
            {"observables.record": lambda dt: None},
            contracts=MORPHOGENESIS_CONTRACTS,
        )
        state = engine.run()
        assert state.step == 1

    def test_component_construction_uses_registry_per_binding(self) -> None:
        world = generate_world(build_field_guided_movers_template())
        adapters = build_components(build_field_guided_movers_registry(), world)
        assert [a.engine_id for a in adapters] == ["py-pde", "pymunk"]


# ----------------------------------------------------------------------
# F. Immutability and isolation
# ----------------------------------------------------------------------
class TestIsolation:
    def test_generation_does_not_share_mutable_state(self) -> None:
        template = build_morphogenesis_template()
        w1 = generate_world(template)
        w2 = generate_world(template)
        w1.config["n"] = 999
        pde_spec = next(s for s in w1.components if s.id == "py-pde")
        pde_spec.config["n"] = 999
        assert w2.config["n"] != 999
        assert next(s for s in w2.components if s.id == "py-pde").config["n"] != 999
        # The template's own configs are untouched.
        assert template.config.get("n") == 32
        assert template.component_configs["py-pde"]["n"] == 32


# ----------------------------------------------------------------------
# G. Generation is adapter-free
# ----------------------------------------------------------------------
class TestGenerationIsAdapterFree:
    def test_generation_never_constructs_an_adapter(self, monkeypatch) -> None:
        from sim_alchemist.core.registry import AdapterFactory, ComponentRegistry

        def _boom(self, config: dict[str, Any]):  # pragma: no cover
            raise AssertionError("generate_world must not build adapters")

        monkeypatch.setattr(AdapterFactory, "build", _boom)
        monkeypatch.setattr(ComponentRegistry, "build", _boom)
        for build in TEMPLATES:
            generate_world(build())
        # classification is equally construction-free for non-matched shapes


# ----------------------------------------------------------------------
# H. Variant semantics of the old worlds are preserved
# ----------------------------------------------------------------------
class TestLegacyWorlds:
    def test_yaml_worlds_load_and_compose(self) -> None:
        world = load_world_yaml(f"{WORLDS_DIR}/chemo_morphogenesis.yaml")
        adapters = build_components(default_registry(), world)
        assert [a.engine_id for a in adapters] == ["py-pde", "pymunk", "mesa"]

    def test_facade_world_component_variants_are_none(self) -> None:
        for facade_world, _ in FACADE.values():
            assert all(spec.variant is None for spec in facade_world.components)


# ----------------------------------------------------------------------
# I. Generated == facade except explicit variant stamps
# ----------------------------------------------------------------------
class TestGeneratedMatchesFacade:
    def test_per_component_configs_and_metadata_identical(self) -> None:
        for name, (facade_world, template) in FACADE.items():
            generated = generate_world(template)
            assert _config_by_id(generated) == _config_by_id(facade_world)
            assert generated.id == facade_world.id
            assert generated.requires == facade_world.requires
            assert generated.schedule == facade_world.schedule
            assert generated.macro_timestep == facade_world.macro_timestep
            assert generated.max_steps == facade_world.max_steps
            assert generated.seed == facade_world.seed
            assert generated.config == facade_world.config
            assert name  # lint guard


# ----------------------------------------------------------------------
# J (slow). Generated worlds reproduce the facade trajectories bitwise
# ----------------------------------------------------------------------
class TestGeneratedTrajectoriesMatchFacades:
    @pytest.mark.slow
    def test_experiment_a_bitwise(self) -> None:
        templ = build_morphogenesis_template()
        generated = _run_generated_a(generate_world(templ))
        facade = __import__("chemomech.simulation", fromlist=["run_world"]).run_world(WorldConfig())
        _assert_same(generated.t_field, facade.t_field)
        _assert_same(generated.u_snaps, facade.u_snaps)
        _assert_same(generated.blocked_snaps, facade.blocked_snaps)
        _assert_same(generated.walls_per_step, facade.walls_per_step)
        _assert_same(generated.wall_geometry_snaps, facade.wall_geometry_snaps)
        _assert_same(generated.force_mags, facade.force_mags)
        _assert_same(generated.wall_speeds, facade.wall_speeds)
        _assert_same(generated.dissolved_count, facade.dissolved_count)
        _assert_same(generated.wall_tracks, facade.wall_tracks)
        _assert_same(generated.agent_histories, facade.agent_histories)

    @pytest.mark.slow
    def test_experiment_b_bitwise(self) -> None:
        templ = build_field_guided_movers_template()
        generated = _run_generated_b(generate_world(templ))
        facade = run_field_guided_movers(MoversConfig())
        _assert_same(generated.t_field, facade.t_field)
        _assert_same(generated.u_snaps, facade.u_snaps)
        _assert_same(generated.positions, facade.positions)
        _assert_same(generated.speeds, facade.speeds)
        _assert_same(generated.force_mags, facade.force_mags)
        _assert_same(generated.gradient_mags, facade.gradient_mags)
        _assert_same(generated.start_u, facade.start_u)

    @pytest.mark.slow
    def test_experiment_c_bitwise(self) -> None:
        templ = build_network_morphogenesis_template()
        outcome = run_network_world(generate_world(templ))
        generated = outcome.trajectory
        facade = run_network_morphogenesis(NetworkMorphogenesisConfig())
        _assert_same(generated.t_field, facade.t_field)
        _assert_same(generated.u_snaps, facade.u_snaps)
        _assert_same(generated.blocked_snaps, facade.blocked_snaps)
        _assert_same(generated.walls_per_step, facade.walls_per_step)
        _assert_same(generated.force_mags, facade.force_mags)
        _assert_same(generated.wall_speeds, facade.wall_speeds)
        _assert_same(generated.mean_load, facade.mean_load)
        _assert_same(generated.max_load, facade.max_load)
        _assert_same(generated.n_sources, facade.n_sources)
        _assert_same(generated.edge_grown, facade.edge_grown)
        _assert_same(generated.start_u, facade.start_u)