"""Task 1.3 validation: declarative composition (checks A-M).

Proves the composition surface of Simulation Alchemist: typed world
definitions (YAML-readable), an explicit in-process component registry,
capability resolution, adapter construction by a composition layer, and
execution of both Experiments A and B through the *generic* ``AlchemistEngine``
+ core ``StepScheduler`` -- not through experiment-specific scheduling logic
in subclasses.

Checks A-K (plus L/M):

    A  YAML worlds load to typed ``WorldDefinition`` equal to the programmatic twins
    B  ``ComponentSpec`` / ``WorldDefinition`` dict round-trip
    C  ``default_registry`` exposes mesa/py-pde/pymunk; adapters build; unknown id raises
    D  capability resolution passes both worlds and fails loudly when required caps are missing
    E  world-level ``requires`` are enforced on top of adapter ``requires``
    F  unknown schedule operations are rejected at compose time (before running)
    G  ``compose`` returns a *plain* ``AlchemistEngine`` with an installed scheduler
    H  plain-composed Experiment A is bitwise identical to the A facade
    I  plain-composed Experiment B is bitwise identical to the B facade
    J  a YAML-loaded world composes and runs identically to its programmatic twin
    K  plain-composed replay is deterministic (same seed -> identical trace + field)
    L  canonical bitwise regression, Experiment A and B (closed) at full 160 steps
    M  architectural: both worlds run through plain ``compose`` on the generic core
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib

import numpy as np
import pytest

from chemomech.coupling import (
    MORPHOGENESIS_SCHEDULE,
    MorphogenesisState,
    build_morphogenesis_operations,
    build_morphogenesis_world,
)
from chemomech.simulation import Trajectory, WorldConfig
from chemomech.validate import build_agents
from experiments.field_guided_movers.coupling import (
    FIELD_GUIDED_MOVERS_SCHEDULE,
    MoversState,
    build_field_guided_movers_operations,
    build_field_guided_movers_registry,
    build_field_guided_movers_world,
)
from experiments.field_guided_movers.model import (
    FieldGuidedMoversEngine,
    MoversConfig,
    MoversTrajectory,
    run_field_guided_movers,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core import (
    AlchemistEngine,
    UnknownComponentError,
    UnresolvedCapabilityError,
    WorldDefinition,
    build_components,
    compose,
    default_registry,
    load_world_yaml,
    resolve_capabilities,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORLDS = REPO_ROOT / "worlds"


def bytes_of(data) -> bytes:
    return np.asarray(data).tobytes()


def sha(arr) -> str:
    return hashlib.sha256(np.asarray(arr).tobytes()).hexdigest()


def baseline_world_config(n_steps: int = 160) -> WorldConfig:
    return WorldConfig(n=32, seed=0, n_steps=n_steps, agent_configs=build_agents())


def compose_morphogenesis(cfg: WorldConfig) -> tuple[AlchemistEngine, Trajectory]:
    """Plain-compose Experiment A from its programmatic world + default registry."""
    world = build_morphogenesis_world(cfg)
    trajectory = Trajectory(config=cfg)
    state = MorphogenesisState()

    def operations(adapters):
        pde, pymunk, mesa = adapters
        return build_morphogenesis_operations(pde, pymunk, mesa, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, pymunk, mesa = adapters
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    engine = compose(world, default_registry(), operations, on_initialize=on_initialize)
    engine.run()
    return engine, trajectory


def compose_movers(cfg: MoversConfig) -> tuple[AlchemistEngine, MoversTrajectory]:
    """Plain-compose Experiment B from its programmatic world + registry override."""
    world = build_field_guided_movers_world(cfg)
    trajectory = MoversTrajectory(config=cfg)
    state = MoversState()

    def operations(adapters):
        pde, movers = adapters
        return build_field_guided_movers_operations(pde, movers, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, _movers = adapters
        field = pde.get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    engine = compose(
        world, build_field_guided_movers_registry(), operations, on_initialize=on_initialize
    )
    engine.run()
    return engine, trajectory


def assert_trajectories_match_a(got: Trajectory, ref: Trajectory) -> None:
    assert sha(got.final_u) == sha(ref.final_u)
    assert got.force_mags == ref.force_mags
    assert got.wall_speeds == ref.wall_speeds
    assert got.dissolved_count == ref.dissolved_count
    assert got.t_field == ref.t_field
    assert got.wall_counts().tolist() == ref.wall_counts().tolist()


def assert_trajectories_match_b(got: MoversTrajectory, ref: MoversTrajectory) -> None:
    assert sha(got.final_u) == sha(ref.final_u)
    assert got.force_mags == ref.force_mags
    assert got.gradient_mags == ref.gradient_mags
    assert got.speeds == ref.speeds
    assert got.positions == ref.positions


# ----------------------------------------------------------------------
# A. YAML worlds load as typed WorldDefinition == programmatic twins
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("yaml_path", "programmatic", "n_components", "expected_schedule"),
    [
        ("chemo_morphogenesis.yaml", build_morphogenesis_world(baseline_world_config()),
         3, MORPHOGENESIS_SCHEDULE),
        ("field_guided_movers.yaml", build_field_guided_movers_world(MoversConfig(seed=0, n_steps=160)),
         2, FIELD_GUIDED_MOVERS_SCHEDULE),
    ],
)
def test_a_yaml_worlds_equal_programmatic_twins(
    yaml_path, programmatic, n_components, expected_schedule
) -> None:
    world = load_world_yaml(WORLDS / yaml_path)
    assert isinstance(world, WorldDefinition)
    assert world.as_dict() == programmatic.as_dict()
    assert len(world.components) == n_components
    assert world.schedule == expected_schedule
    assert world.macro_timestep == pytest.approx(0.2)
    assert world.max_steps == 160 and world.seed == 0


# ----------------------------------------------------------------------
# B. Dict round-trip of the typed world definition
# ----------------------------------------------------------------------
def test_b_world_definition_dict_round_trip() -> None:
    world = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    rebuilt = WorldDefinition.from_dict(world.as_dict())
    assert rebuilt == world
    assert rebuilt.components[0].id == "py-pde"
    assert rebuilt.requires == world.requires


# ----------------------------------------------------------------------
# C. Registry: component catalog, adapter construction, unknown ids
# ----------------------------------------------------------------------
def test_c_default_registry_builds_adapters() -> None:
    registry = default_registry()
    assert registry.components() == ["mesa", "py-pde", "pymunk"]
    world = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    adapters = build_components(registry, world)
    assert [a.engine_id for a in adapters] == ["py-pde", "pymunk", "mesa"]

    import sim_alchemist.adapters.mesa as mesa_mod
    import sim_alchemist.adapters.pymunk as pymunk_mod
    assert isinstance(adapters[1], pymunk_mod.PymunkAdapter)
    assert isinstance(adapters[2], mesa_mod.MesaAdapter)


def test_c_unknown_component_raises() -> None:
    registry = default_registry()
    with pytest.raises(UnknownComponentError, match="does.not.exist"):
        registry.get("does.not.exist")


# ----------------------------------------------------------------------
# D. Capability resolution
# ----------------------------------------------------------------------
def test_d_both_worlds_resolve() -> None:
    world_a = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    world_b = load_world_yaml(WORLDS / "field_guided_movers.yaml")
    resolve_capabilities(build_components(default_registry(), world_a), list(world_a.requires))
    resolve_capabilities(
        build_components(build_field_guided_movers_registry(), world_b),
        list(world_b.requires),
    )


def test_d_missing_capability_raises() -> None:
    adapters = [PyPDEAdapter(n=16)]
    with pytest.raises(UnresolvedCapabilityError) as exc:
        resolve_capabilities(adapters, ["agent_population"])
    assert "agent_population" in str(exc.value)


# ----------------------------------------------------------------------
# E. World-level requires are enforced on top of adapter requires
# ----------------------------------------------------------------------
def test_e_world_requires_are_enforced() -> None:
    world = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    # The adapters resolve fine on their own, but the world demands an extra cap.
    world_bad = WorldDefinition.from_dict({**world.as_dict(), "requires": list(world.requires) + ["quantum_field"]})

    def ops(_adapters):
        return {"geometry.sync": lambda dt: None, "field.step": lambda dt: None,
                "physics.force": lambda dt: None, "physics.step": lambda dt: None,
                "agents.step": lambda dt: None, "agents.apply": lambda dt: None,
                "observables.record": lambda dt: None}

    def on_init(_adapters):
        pass

    with pytest.raises(UnresolvedCapabilityError, match="quantum_field"):
        compose(world_bad, default_registry(), ops, on_initialize=on_init)


# ----------------------------------------------------------------------
# F. Unknown schedule operations are rejected at compose time
# ----------------------------------------------------------------------
def test_f_unknown_schedule_op_fails_at_compose_time() -> None:
    world = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    world_bad = dataclasses.replace(world, schedule=("geometry.sync", "nope.missing"))
    assert not hasattr(world_bad, "_ran")

    def ops(_adapters):
        return {"geometry.sync": lambda dt: None}

    with pytest.raises(KeyError) as exc:
        compose(world_bad, default_registry(), ops)
    assert "nope.missing" in str(exc.value)


# ----------------------------------------------------------------------
# G. compose() returns a plain AlchemistEngine with an installed scheduler
# ----------------------------------------------------------------------
def test_g_compose_returns_plain_engine() -> None:
    cfg = baseline_world_config(n_steps=4)
    engine, _ = compose_morphogenesis(cfg)
    assert type(engine) is AlchemistEngine
    assert not isinstance(engine, FieldGuidedMoversEngine)
    assert set(engine.engines) == {"py-pde", "pymunk", "mesa"}
    assert engine._scheduler is not None
    assert engine._schedule is not None
    assert engine._schedule.names() == list(MORPHOGENESIS_SCHEDULE)


# ----------------------------------------------------------------------
# H. Plain-composed Experiment A == A facade (bitwise)
# ----------------------------------------------------------------------
def test_h_plain_compose_a_matches_facade() -> None:
    from chemomech.simulation import run_world

    cfg = baseline_world_config(n_steps=12)
    engine, plain = compose_morphogenesis(cfg)
    ref = run_world(cfg)
    assert_trajectories_match_a(plain, ref)
    assert engine._scheduler is not None
    assert engine._scheduler.trace.operations() == list(MORPHOGENESIS_SCHEDULE) * cfg.n_steps


# ----------------------------------------------------------------------
# I. Plain-composed Experiment B == B facade (bitwise)
# ----------------------------------------------------------------------
def test_i_plain_compose_b_matches_facade() -> None:
    cfg = MoversConfig(seed=0, n_steps=12)
    engine, plain = compose_movers(cfg)
    ref = run_field_guided_movers(cfg)
    assert_trajectories_match_b(plain, ref)
    assert engine._scheduler is not None
    assert engine._scheduler.trace.operations() == list(FIELD_GUIDED_MOVERS_SCHEDULE) * cfg.n_steps


# ----------------------------------------------------------------------
# J. A YAML-loaded world composes and runs identically to its twin
# ----------------------------------------------------------------------
def test_j_yaml_worlds_run_equivalently() -> None:
    cfg = baseline_world_config(n_steps=8)
    yaml_world = dataclasses.replace(load_world_yaml(WORLDS / "chemo_morphogenesis.yaml"), max_steps=8)

    prog_traj = Trajectory(config=cfg)
    yaml_traj = Trajectory(config=cfg)
    state_p, state_y = MorphogenesisState(), MorphogenesisState()

    def ops_prog(adapters):
        pde, pymunk, mesa = adapters
        return build_morphogenesis_operations(pde, pymunk, mesa, cfg, prog_traj, state_p)

    def ops_yaml(adapters):
        pde, pymunk, mesa = adapters
        return build_morphogenesis_operations(pde, pymunk, mesa, cfg, yaml_traj, state_y)

    def on_init(adapters):
        pde, pymunk, mesa = adapters
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    compose(build_morphogenesis_world(cfg), default_registry(), ops_prog, on_initialize=on_init).run()
    compose(yaml_world, default_registry(), ops_yaml, on_initialize=on_init).run()

    assert_trajectories_match_a(yaml_traj, prog_traj)
    assert len(yaml_traj.t_field) == 8


# ----------------------------------------------------------------------
# K. Determinism through the plain-composed path
# ----------------------------------------------------------------------
def test_k_plain_compose_replay_is_deterministic() -> None:
    cfg = baseline_world_config(n_steps=6)
    _, t1 = compose_morphogenesis(cfg)
    _, t2 = compose_morphogenesis(cfg)
    assert sha(t1.final_u) == sha(t2.final_u)
    assert t1.force_mags == t2.force_mags


# ----------------------------------------------------------------------
# L. Canonical bitwise regression (full 160-step worlds via YAML + compose)
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_l_canonical_regression_a_full() -> None:
    world = load_world_yaml(WORLDS / "chemo_morphogenesis.yaml")
    cfg = baseline_world_config()
    trajectory = Trajectory(config=cfg)
    state = MorphogenesisState()

    def ops(adapters):
        pde, pymunk, mesa = adapters
        return build_morphogenesis_operations(pde, pymunk, mesa, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, pymunk, mesa = adapters
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    compose(world, default_registry(), ops, on_initialize=on_initialize).run()

    assert sha(trajectory.final_u) == "9b2232638a6dfda3e27f85994606ffea1af66d44a6a50eafb1c4465c23e28b12"
    assert sha(trajectory.force_mags) == "6287a47228a34bd5516c4ed96a99741dd3a96887de27376d0ee0b2e90f67b011"
    assert sha(trajectory.wall_speeds) == "36a0edb0bc1e64ae5fdfb98033d7d883949270f41589ba02cb596a1d418082b9"
    assert float(trajectory.final_u.std()) == pytest.approx(0.9257519710307387, rel=1e-9)


@pytest.mark.slow
def test_l_canonical_regression_b_closed_full() -> None:
    world = load_world_yaml(WORLDS / "field_guided_movers.yaml")
    cfg = MoversConfig(seed=0, n_steps=160)
    trajectory = MoversTrajectory(config=cfg)
    state = MoversState()

    def ops(adapters):
        pde, movers = adapters
        return build_field_guided_movers_operations(pde, movers, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, _movers = adapters
        field = pde.get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    compose(world, build_field_guided_movers_registry(), ops, on_initialize=on_initialize).run()

    assert sha(trajectory.final_u) == "6bdd951fdb293d176cc7c845727cbf78b70139ca8f338b21cb6090cb0ab96033"
    assert sha(trajectory.force_mags) == "bee55c7fd4e892422a9c8dfb10477b4be1dc06172f6d58308649c0905e709571"
    assert sha(trajectory.gradient_mags) == "b88412f28aea9387122d4f1b6f1e4ffe1aaf93f72dcb6ac104235c60ca11857b"
    assert sha(trajectory.speeds) == "eb7ac0e216f2dc57ad0d6154b1e1d65a677e2ef87620800bb45283ca7123779f"
    assert float(trajectory.final_u.std()) == pytest.approx(1.0959005164453761, rel=1e-9)


# ----------------------------------------------------------------------
# M. Architectural: both worlds run through plain compose on the generic core
# ----------------------------------------------------------------------
def test_m_both_worlds_run_through_plain_compose() -> None:
    engine_a, traj_a = compose_morphogenesis(baseline_world_config(n_steps=8))
    engine_b, traj_b = compose_movers(MoversConfig(seed=0, n_steps=8))

    assert type(engine_a) is AlchemistEngine and type(engine_b) is AlchemistEngine
    assert engine_a._scheduler is not None and engine_b._scheduler is not None
    assert engine_a._scheduler.trace.operations() == list(MORPHOGENESIS_SCHEDULE) * 8
    assert engine_b._scheduler.trace.operations() == list(FIELD_GUIDED_MOVERS_SCHEDULE) * 8

    # Both fields genuinely evolved from their initial states.
    assert not np.array_equal(traj_a.final_u, traj_a.u_snaps[0])
    assert not np.array_equal(traj_b.final_u, traj_b.u_snaps[0])
    # Different worlds -> different declared schedules (ordering is data, not code).
    assert MORPHOGENESIS_SCHEDULE != FIELD_GUIDED_MOVERS_SCHEDULE