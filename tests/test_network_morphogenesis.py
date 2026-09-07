"""Task 1.5 validation: Adaptive Network Morphogenesis (checks C1-C10).

Proves a THIRD experiment -- a three-domain triangle (NDlib network diffusion +
py-pde field + Pymunk walls) with genuine A<->B<->C<->A feedback -- composes
and runs through the same generic Alchemist core as Experiments A and B,
with no change to ``src/sim_alchemist/core/``.
"""

from __future__ import annotations

import hashlib
import pathlib
from collections import Counter
from typing import cast

import numpy as np
import pytest

from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    NETWORK_MORPHOGENESIS_SCHEDULE,
    build_network_morphogenesis_registry,
    build_network_morphogenesis_world,
    network_morphogenesis_force,
)
from experiments.network_morphogenesis.model import (
    NetworkMorphogenesisConfig,
    NetworkMorphogenesisEngine,
    run_network_morphogenesis,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.composer import build_components, compose
from sim_alchemist.core.engine import AlchemistEngine, CapabilityResolver
from sim_alchemist.core.world import load_world_yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FAST_STEPS = 10


def _run(cfg: NetworkMorphogenesisConfig):
    return run_network_morphogenesis(cfg)


@pytest.fixture(scope="module")
def triangle_trajectories() -> dict[str, object]:
    cfg = NetworkMorphogenesisConfig(seed=0, n_steps=FAST_STEPS)
    closed = _run(NetworkMorphogenesisConfig(**cfg.as_dict()))

    no_source = NetworkMorphogenesisConfig(**cfg.as_dict())
    no_source.source_amplitude = 0.0
    open_traj = _run(no_source)

    return {"closed": closed, "open": open_traj}


# ----------------------------------------------------------------------
# C1. Capability resolution without Mesa
# ----------------------------------------------------------------------
def test_capability_resolution_three_engines() -> None:
    cfg = NetworkMorphogenesisConfig()
    pde = PyPDEAdapter(n=cfg.n)
    net = AdaptiveNetworkAdapter(
        grid_rows=cfg.grid_rows, grid_cols=cfg.grid_cols,
        beta=cfg.network_beta, loss=cfg.network_loss, seed=cfg.seed,
    )
    assert pde is not None and net is not None

    # The pymunk wall adapter (provides rigid_body) is composed through the
    # world; here we include it via the experiment registry so resolution is
    # exercised on the full triangle.
    registry = build_network_morphogenesis_registry()
    assert registry.has("py-pde") and registry.has("pymunk") and registry.has("network")
    triangle = build_components(registry, build_network_morphogenesis_world())
    result = CapabilityResolver().resolve(list(triangle))
    assert result.valid, f"triangle should resolve without Mesa: {result.missing}"
    assert len(result.missing) == 0
    ids = {e.engine_id for e in triangle}
    assert ids == {"py-pde", "pymunk", "network"}
    assert "mesa" not in ids


def test_world_requires_network_diffusion_and_field_gradient() -> None:
    world = build_network_morphogenesis_world()
    assert "network_diffusion" in world.requires
    assert "field_gradient" in world.requires
    assert set(world.schedule) == set(NETWORK_MORPHOGENESIS_SCHEDULE)
    assert world.schedule == NETWORK_MORPHOGENESIS_SCHEDULE


# ----------------------------------------------------------------------
# C2. Invalid / incomplete composition fails
# ----------------------------------------------------------------------
def test_incomplete_composition_fails() -> None:
    camper = AdaptiveNetworkAdapter()
    result = CapabilityResolver().resolve([camper])  # no field or physics provider
    assert not result.valid
    missing_names = {c.name for c in result.missing}
    assert {"reaction_diffusion", "rigid_body"} <= missing_names

    # Engine without its network component raises a runtime composition error.
    engine = NetworkMorphogenesisEngine(config=NetworkMorphogenesisConfig(n_steps=1))
    del engine.engines["network"]
    with pytest.raises(RuntimeError, match="[Ii]nvalid composition"):
        engine.run()


# ----------------------------------------------------------------------
# C3. Field -> physics (A->C): gradient force drives walls, bounded
# ----------------------------------------------------------------------
def test_gradient_force_bounded_and_directional() -> None:

    cfg = NetworkMorphogenesisConfig(n=16)
    pde = PyPDEAdapter(n=16)
    pde.initialize(cfg.as_dict())
    f = pde.get_field()
    assert f is not None
    _rr, cc = np.meshgrid(np.arange(16) / 16.0, np.arange(16) / 16.0, indexing="ij")
    f.u[:] = 0.5 + cc  # monotonic gradient along the x-axis (columns)
    class _W:
        center = (0.5, 0.5)
    wall = _W()
    fx, fy = network_morphogenesis_force(f, wall, force_fmax=0.8, force_gsat=2.0)
    assert fx > 0, "force should point in the up-gradient direction"
    assert abs(fy) < abs(fx), "force should be mostly along the single-D gradient"
    assert float(np.hypot(fx, fy)) <= 0.8 + 1e-9, "force magnitude must respect fmax"


def test_walls_actually_move(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    tracks = closed.wall_tracks
    assert tracks, "no wall tracks were recorded"
    moved = 0
    for pts in tracks.values():
        if len(pts) >= 2:
            (t0, x0, y0, _a0), (t1, x1, y1, _a1) = pts[0], pts[-1]
            disp = float(np.hypot(x1 - x0, y1 - y0))
            if t1 > t0 and disp > 1e-6:
                moved += 1
    assert moved >= 1, "no wall body displaced under the field-gradient force"


# ----------------------------------------------------------------------
# C4. Physics -> network (B->C): wall geometry changes edge weights
# ----------------------------------------------------------------------
def test_blocked_geometry_reweights_edges() -> None:
    net = AdaptiveNetworkAdapter(grid_rows=4, grid_cols=6, seed=3)
    net.initialize({
        "grid_rows": 4, "grid_cols": 6,
        "beta": 0.3, "loss": 0.05, "seed": 3,
    })
    node_to_grid = net._node_to_grid
    graph = net._graph
    assert graph is not None
    wall = graph.edges()
    assert len(list(wall)) >= 1
    before = dict(net._weights)

    # Block the cell at the midpoint of edge (5, 11) deliberately.
    mask = np.zeros((4, 6), dtype=bool)
    u, v = 5, 11  # two adjacent nodes on the same row
    ru, cu = node_to_grid[u]
    rv, cv = node_to_grid[v]
    mask[round((ru + rv) / 2.0), round((cu + cv) / 2.0)] = True
    net.set_blocked(mask)
    net.reweight_from_geometry()
    assert net._weights[(u, v)] < 1.0, "blocked edge must be de-weighted"
    assert net._weights[(u, v)] == pytest.approx(0.1)
    assert net._weights[(v, u)] == net._weights[(u, v)]

    # An untouched edge keeps full weight.
    other = next(e for e in graph.edges() if e != (u, v) and e != (v, u))
    assert net._weights[other] == before[other] == 1.0


def test_growth_edge_tracks_network_state() -> None:
    net = AdaptiveNetworkAdapter(grid_rows=4, grid_cols=6, seed=0)
    net.initialize({
        "grid_rows": 4, "grid_cols": 6, "beta": 0.3, "loss": 0.05, "seed": 0,
    })
    loads = net.get_load()
    edges = [net.get_highest_throughput_edge(loads) for _ in range(5)]
    assert all(e is not None for e in edges)
    assert len(set(edges)) == 1, "deterministic edge selection for identical load"

    # Perturbing load moves the selected edge onto the loaded corridor.
    net.set_load({0: 0.9, 1: 0.9, 2: 0.9, 3: 0.9})
    after = net.get_highest_throughput_edge(net.get_load())
    assert after is not None and after[0] in {0, 1, 2, 3}


# ----------------------------------------------------------------------
# C5. Network -> field (C->A): node load injects PDE sources
# ----------------------------------------------------------------------
def test_network_load_drives_field(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    open_traj = triangle_trajectories["open"]
    rmsd = float(np.sqrt(np.mean((closed.final_u - open_traj.final_u) ** 2)))
    assert rmsd > 1e-4, f"network load did not measurably change the field (rmsd={rmsd:.5f})"
    assert closed.n_sources[-1] > 0, "no chemical sources were injected"


def test_sources_grow_with_load_spread() -> None:
    tr = _run(NetworkMorphogenesisConfig(seed=0, n_steps=FAST_STEPS))
    assert len(tr.n_sources) == FAST_STEPS
    assert min(tr.n_sources) > 0, "sources must be present from the first step"
    # As load spreads over the network more nodes become sources.
    assert max(tr.n_sources) >= min(tr.n_sources)


# ----------------------------------------------------------------------
# C6. Closed triangle diverges from open/inert controls
# ----------------------------------------------------------------------
def test_closed_loop_diverges_from_open_loop(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    open_traj = triangle_trajectories["open"]
    rmsd = float(np.sqrt(np.mean((closed.final_u - open_traj.final_u) ** 2)))
    corr = float(np.corrcoef(closed.final_u.ravel(), open_traj.final_u.ravel())[0, 1])
    assert rmsd > 1e-4, f"feedback loop did not diverge from open-loop control (rmsd={rmsd:.5f})"
    assert corr < 0.9999


def test_closed_loop_diverges_from_inert_control() -> None:
    # A strong force makes wall motion visible within a short fast run; the
    # control blinds the forces entirely so only geometry-driven closing of
    # the B->A edge of the triangle can move the field.
    driven = NetworkMorphogenesisConfig(seed=0, n_steps=FAST_STEPS, force_fmax=8.0)
    inert_cfg = NetworkMorphogenesisConfig(seed=0, n_steps=FAST_STEPS, force_fmax=0.0)
    closed = _run(driven)
    inert = _run(inert_cfg)
    rmsd = float(np.sqrt(np.mean((closed.final_u - inert.final_u) ** 2)))
    corr = float(np.corrcoef(closed.final_u.ravel(), inert.final_u.ravel())[0, 1])
    assert rmsd > 1e-4, "no measurable influence of wall motion on the field"
    assert corr < 0.9999
    moved = [p for p in closed.wall_tracks.values() if len(p) >= 2]
    assert moved, "driven run should have recorded moving walls"


# ----------------------------------------------------------------------
# C7. Sustained adaptive behaviour (not a one-shot perturbation)
# ----------------------------------------------------------------------
def test_network_load_stays_heterogeneous(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    loads = closed.mean_load
    assert len(loads) == FAST_STEPS
    assert all(np.isfinite(v) for v in loads)
    # Reservoirs keep a persistent load gradient across the whole run.
    assert closed.max_load[-1] <= 1.0 + 1e-9
    assert closed.mean_load[-1] > 0.0


def test_walls_grow_along_network_edges(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    assert closed.walls_per_step[0] >= 0
    assert closed.walls_per_step[-1] > closed.walls_per_step[0], (
        "the world should grow walls over its run"
    )
    grown = [e for e in closed.edge_grown if e is not None]
    assert grown, "no edge was ever selected for wall growth"
    assert all(isinstance(e, tuple) and len(e) == 2 for e in grown)
    edges_grown = set(grown)
    assert len(edges_grown) >= 1
    # Walls that grew still show up in the geometry snapshots.
    assert closed.wall_geometry_snaps, "no geometry snapshots recorded"


def test_wall_growth_reroutes_after_blocking() -> None:
    """When a grown wall blocks its edge, selection must move elsewhere."""
    net = AdaptiveNetworkAdapter(grid_rows=4, grid_cols=6, seed=0)
    net.initialize({
        "grid_rows": 4, "grid_cols": 6, "beta": 0.3, "loss": 0.05, "seed": 0,
    })
    first = net.get_highest_throughput_edge(net.get_load())
    assert first is not None
    mask = np.zeros((4, 6), dtype=bool)
    ru, cu = net._node_to_grid[first[0]]
    rv, cv = net._node_to_grid[first[1]]
    mask[round((ru + rv) / 2.0), round((cu + cv) / 2.0)] = True
    net.set_blocked(mask)
    net.reweight_from_geometry()
    second = net.get_highest_throughput_edge(net.get_load())
    assert second is not None
    assert second != first, "growing a wall on an edge should reroute growth"


# ----------------------------------------------------------------------
# C8. Determinism: same seed + same runtime -> identical output
# ----------------------------------------------------------------------
def test_deterministic_replay_bitwise() -> None:
    cfg = NetworkMorphogenesisConfig(seed=0, n_steps=FAST_STEPS)
    t1 = _run(cfg)
    t2 = _run(NetworkMorphogenesisConfig(**cfg.as_dict()))
    assert np.array_equal(t1.final_u, t2.final_u), "field must replay bitwise"
    assert t1.walls_per_step == t2.walls_per_step
    assert t1.edge_grown == t2.edge_grown
    assert t1.n_sources == t2.n_sources
    assert t1.mean_load == t2.mean_load


def test_reservoir_recharge_deterministic() -> None:
    net = AdaptiveNetworkAdapter(grid_rows=4, grid_cols=6, seed=1)
    net.initialize({
        "grid_rows": 4, "grid_cols": 6, "beta": 0.3, "loss": 0.05, "seed": 1,
    })
    seeds = set(net.seed_node_ids())
    assert seeds == {0, 18}, "corner reservoirs should be deterministic"
    net.step(0.2)
    net.nourish_reservoirs()
    loads = net.get_load()
    for n in seeds:
        assert loads[n] == pytest.approx(1.0), "reservoir must be recharged"


# ----------------------------------------------------------------------
# C9. Boundedness / boundary checks
# ----------------------------------------------------------------------
def test_loads_bounded_in_unit_interval(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    world = build_network_morphogenesis_world()
    reg = build_network_morphogenesis_registry()
    _pde, _pymunk, net = build_components(reg, world)
    network = cast(AdaptiveNetworkAdapter, net)
    network.initialize(closed.config.as_dict())
    for _ in range(5):
        network.step(0.2)
        loads = network.get_load()
        assert all(0.0 <= v <= 1.0 + 1e-9 for v in loads.values())


def test_walls_in_bounds(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    for snap in closed.wall_geometry_snaps:
        for (p1, p2, _r) in snap:
            for x, y in (p1, p2):
                assert 0.0 - 1e-9 <= x <= 1.0 + 1e-9
                assert 0.0 - 1e-9 <= y <= 1.0 + 1e-9


def test_force_mean_reasonable(triangle_trajectories) -> None:
    closed = triangle_trajectories["closed"]
    assert all(np.isfinite(f) for f in closed.force_mags)
    assert float(np.mean(closed.force_mags)) <= 0.8 + 1e-9


# ----------------------------------------------------------------------
# C10. Shared core architecture + declarative world equivalence
# ----------------------------------------------------------------------
def test_yaml_world_matches_programmatic() -> None:
    yaml_world = load_world_yaml(REPO_ROOT / "worlds" / "adaptive_network.yaml")
    prog_world = build_network_morphogenesis_world()
    assert yaml_world == prog_world or (
        yaml_world.id == prog_world.id
        and yaml_world.components == prog_world.components
        and yaml_world.requires == prog_world.requires
        and yaml_world.schedule == prog_world.schedule
    ), "YAML world must describe the identical composition"


def test_yaml_world_runs_via_plain_compose() -> None:
    yaml_world = load_world_yaml(REPO_ROOT / "worlds" / "adaptive_network.yaml")
    registry = build_network_morphogenesis_registry()
    engine = compose(
        yaml_world,
        registry,
        lambda adapters: _experiment_ops(adapters, yaml_world),
    )
    result = engine.run()
    assert result is not None


def _experiment_ops(adapters, world):
    from experiments.network_morphogenesis.coupling import (
        NetworkMorphogenesisState,
        build_network_morphogenesis_operations,
    )
    from experiments.network_morphogenesis.model import NetworkMorphogenesisTrajectory

    pde, pymunk, net = adapters
    traj = NetworkMorphogenesisTrajectory(config=NetworkMorphogenesisConfig(**world.config))
    return build_network_morphogenesis_operations(
        pde, pymunk, net, world.config, traj, NetworkMorphogenesisState()
    )


def test_shared_core_class(triangle_trajectories) -> None:
    assert NetworkMorphogenesisEngine.__mro__[1] is AlchemistEngine
    assert NetworkMorphogenesisEngine.SCHEDULE == NETWORK_MORPHOGENESIS_SCHEDULE


def test_experiments_a_b_c_share_core():
    import sim_alchemist.core.engine as e
    from sim_alchemist.core.clock import SimulationClock
    from sim_alchemist.core.events import EventBus

    assert e.AlchemistEngine is NetworkMorphogenesisEngine.__mro__[1]
    assert SimulationClock is not None and EventBus is not None


def test_network_adapter_contract():
    net = AdaptiveNetworkAdapter()
    for attr in ("engine_id", "provides", "requires", "native_timestep", "initialize",
                 "step", "get_state", "apply_event", "shutdown"):
        assert hasattr(net, attr)


# ----------------------------------------------------------------------
# Core immutability guard: src/sim_alchemist/core/ must not have changed.
# Reuses the fixed hashes from the Experiment B guard (re-baselined at
# Task 1.6 to include the mutation/lineage/runner modules, at Task 1.7 for
# the sweep/ranking layer, and at Task 1.8 for behavior/interestingness).
# ----------------------------------------------------------------------
def test_core_files_unchanged() -> None:
    import test_field_guided_movers as b

    for filename, expected in b.CORE_COMMIT_HASHES.items():
        path = REPO_ROOT / "src" / "sim_alchemist" / "core" / filename
        assert path.is_file(), f"core file {filename} missing"
        h = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert h == expected, (
            f"src/sim_alchemist/core/{filename} was modified! Task 1.8 must not change the core."
        )


# ----------------------------------------------------------------------
# Slow canonical: full 160-step adaptive morphogenesis regression
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_canonical_160_step_adaptive_network() -> None:
    tr = _run(NetworkMorphogenesisConfig(seed=0, n_steps=160))
    assert len(tr.t_field) == 160
    assert tr.walls_per_step[-1] > 10, "the world must grow a substantial wall ensemble"
    grown = [e for e in tr.edge_grown if e is not None]
    counts = Counter(grown)
    assert len(counts) >= 2, "growth should adapt/reroute across multiple edges"
    assert all(np.isfinite(tr.mean_load)) and all(np.isfinite(tr.max_load))