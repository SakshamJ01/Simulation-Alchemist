"""Task 1.9 validation: guided simulation search (beam search) (A-O).

Uses the generic core directly (``SearchSpec`` / ``child_mutations`` /
``SearchRunner`` / ``search_id_of``) against a fast deterministic executor,
plus one real Experiment C (Adaptive Network Morphogenesis) search at small
length as the live subject.

Checks:

    A  SearchSpec validation (positive ints, non-empty name/space/profile)
    B  child_mutations: documented dimension-major order, single-param sets,
       truncation to children_per_parent, parents never mutated
    C  child_mutations skips values equal to the parent's current leaf (no-op)
    D  Duplicate worlds are visited once: generated but never re-executed,
       counted in the timing summary
    E  Base / parent worlds are never mutated in place; children are clones
    F  Beam structure: generation records, parents feed the next beam,
       beam_width honored
    G  Generation flow and lineage: candidate ids, parent links in the store,
       deterministic candidate ids, depth-first beam traversal
    H  Profile-driven selection: two opposite profiles clearly diverge
       ("interesting" is what the profile says, not the largest value)
    I  Whole-search determinism: same world+spec+space+seed+profile produce
       identical canonical output (ids, candidates, generations, ranking)
    J  search_id_of is deterministic, 24-hex, and sensitive to world/spec
    K  Final ranking covers every candidate; best()/lineage_path/mutation_path
       and explanations are consistent
    L  Compact search persistence only (no trajectories, no per-step data);
       recording is idempotent
    M  The core search source contains no experiment-specific identifiers
    N  A real Experiment C search executes end to end (root + children) and
       is bitwise reproducible
    O  Performance instrumentation (generated/skipped/executed, timings)
"""

from __future__ import annotations

import dataclasses
import math
import pathlib

import pytest

from experiments.network_morphogenesis.experiment import (
    build_network_observables,
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    ComponentSpec,
    ExecOutcome,
    InterestingnessProfile,
    LineageStore,
    MutationSpace,
    ObservableSeries,
    ParameterSweep,
    SearchResult,
    SearchRunner,
    SearchSpec,
    WorldDefinition,
    child_mutations,
    load_world_yaml,
    search_id_of,
    world_hash,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORLDS = REPO_ROOT / "worlds"
FAST_STEPS = 10

FORBIDDEN_CORE_TOKENS = (
    "ndlib",
    "mesa",
    "pymunk",
    "chemomech",
    "morphogen",
    "network",
    "adapt",
)


# ----------------------------------------------------------------------
# Helpers: a tiny generic world + a deterministic, feature-rich executor.
# ----------------------------------------------------------------------
TOY_X = "components.toy.config.x"
TOY_Y = "config.y"


def make_toy_world(x: float = 1.0, y: float = 10.0, seed: int = 0) -> WorldDefinition:
    return WorldDefinition(
        id="toy",
        components=(ComponentSpec("toy", {"x": float(x)}),),
        config={"y": float(y)},
        seed=seed,
        max_steps=1,
    )


def toy_executor(world: WorldDefinition) -> ExecOutcome:
    x = float(world.components[0].config["x"])
    y = float(world.config["y"])
    n = 48
    times = tuple(float(i) for i in range(n))
    ramp = tuple(x * (1.0 + 0.1 * i) for i in range(n))
    osc = tuple(
        math.sin(2 * math.pi * (3.0 + y * 0.05) * i / n) * (0.5 + x * 0.1)
        for i in range(n)
    )
    trajectory = {"s1": (times, ramp), "s2": (times, osc)}
    return ExecOutcome(world=world, metrics={"m": x * y}, trajectory=trajectory)


def toy_observables(outcome: ExecOutcome) -> dict[str, ObservableSeries]:
    return {
        name: ObservableSeries(name, outcome.trajectory[name][0], outcome.trajectory[name][1])
        for name in ("s1", "s2")
    }


def make_toy_space() -> MutationSpace:
    return MutationSpace(
        (
            ParameterSweep(TOY_X, (1.5, 2.0, 3.0)),
            ParameterSweep(TOY_Y, (20.0, 30.0)),
        )
    )


def make_profile() -> InterestingnessProfile:
    return InterestingnessProfile(
        name="toy-interest",
        description="prefer ramp slope, ramp activity, and oscillation",
        weights={
            "s1:trend_slope": 0.4,
            "s1:activity_rate": 0.3,
            "s2:oscillation_strength": 0.3,
        },
    )


def make_spec(**overrides) -> SearchSpec:
    kwargs = {
        "name": "toy-search",
        "generations": 2,
        "beam_width": 2,
        "children_per_parent": 3,
        "mutation_space": make_toy_space(),
        "profile": make_profile(),
        "seed": 0,
    }
    kwargs.update(overrides)
    return SearchSpec(**kwargs)


def run_toy_search(store=None, spec=None, world=None) -> SearchResult:
    store = store if store is not None else LineageStore(":memory:")
    return SearchRunner(store, toy_executor, toy_observables).search(
        world or make_toy_world(), spec or make_spec()
    )


# ----------------------------------------------------------------------
# A. SearchSpec validation
# ----------------------------------------------------------------------
def test_a_spec_validation() -> None:
    space = make_toy_space()
    profile = make_profile()
    with pytest.raises(ValueError):
        SearchSpec("s", 0, 2, 3, space, profile)  # generations
    with pytest.raises(ValueError):
        SearchSpec("s", 2, 0, 3, space, profile)  # beam width
    with pytest.raises(ValueError):
        SearchSpec("s", 2, 2, 0, space, profile)  # children per parent
    with pytest.raises(ValueError):
        SearchSpec("   ", 2, 2, 3, space, profile)  # empty name
    with pytest.raises((TypeError, ValueError)):
        SearchSpec("s", 2, 2, 3, space, profile, seed=1.5)  # type: ignore[arg-type]
    ok = SearchSpec("s", 2, 2, 3, space, profile, seed=1)
    assert ok.to_dict()["generations"] == 2
    assert SearchSpec.from_dict(ok.to_dict()) == ok


# ----------------------------------------------------------------------
# B. child_mutations: order, single-param sets, truncation, immutability
# ----------------------------------------------------------------------
def test_b_child_mutations_order_and_truncation() -> None:
    world = make_toy_world()  # x=1.0, y=10.0
    sets = child_mutations(world, make_toy_space(), 5)
    assert [m.path for (m,) in sets] == [TOY_X, TOY_X, TOY_X, TOY_Y, TOY_Y]
    assert [m.new_value for (m,) in sets] == [1.5, 2.0, 3.0, 20.0, 30.0]
    assert all(len(s) == 1 for s in sets)  # single-parameter children (MVP)
    truncated = child_mutations(world, make_toy_space(), 2)
    assert [(m.path, m.new_value) for (m,) in truncated] == [
        (TOY_X, 1.5),
        (TOY_X, 2.0),
    ]
    assert len(child_mutations(world, make_toy_space(), 100)) == 5
    # The parent is never mutated by child generation.
    assert world.components[0].config["x"] == pytest.approx(1.0)
    assert world.config["y"] == pytest.approx(10.0)


# ----------------------------------------------------------------------
# C. No-op values (equal to the parent's current leaf) are skipped
# ----------------------------------------------------------------------
def test_c_child_mutations_skip_noops() -> None:
    world = make_toy_world(x=1.5)
    space = MutationSpace((ParameterSweep(TOY_X, (1.5, 2.0, 3.0)),))
    sets = child_mutations(world, space, 3)
    assert [m.new_value for (m,) in sets] == [2.0, 3.0]

    whole_space = MutationSpace(
        (ParameterSweep(TOY_X, (1.0, 2.0)), ParameterSweep(TOY_Y, (10.0, 20.0)))
    )
    over = child_mutations(make_toy_world(x=1.0, y=10.0), whole_space, 10)
    # x=1.0 and y=10.0 are no-ops; x=2.0 and y=20.0 survive.
    assert [(m.path, m.new_value) for (m,) in over] == [(TOY_X, 2.0), (TOY_Y, 20.0)]


# ----------------------------------------------------------------------
# D. Duplicate worlds are visited once (skipped, counted, never re-run)
# ----------------------------------------------------------------------
def test_d_duplicate_world_visited_once() -> None:
    world = make_toy_world()
    space = MutationSpace((ParameterSweep(TOY_X, (1.5, 1.5, 2.0)),))
    spec = SearchSpec("dup", 1, 1, 3, space, make_profile())
    store = LineageStore(":memory:")
    res = SearchRunner(store, toy_executor, toy_observables).search(world, spec)
    assert len(res.candidates) == 3  # root + x=1.5 + x=2.0
    assert res.timing.n_generated == 3
    assert res.timing.n_skipped == 1  # the repeated 1.5
    assert res.timing.n_executed == 3
    assert store.run_count == 3
    # Only the unique children are recorded as generation children.
    assert res.generations[1].child_candidate_ids == (
        res.candidates[1].candidate_id,
        res.candidates[2].candidate_id,
    )


# ----------------------------------------------------------------------
# E. Base / parent worlds are never mutated in place
# ----------------------------------------------------------------------
def test_e_worlds_never_mutated_in_place() -> None:
    world = make_toy_world()
    snapshot = world.as_dict()
    spec = make_spec(generations=2, beam_width=2, children_per_parent=3)
    res = SearchRunner(LineageStore(":memory:"), toy_executor, toy_observables).search(
        world, spec
    )
    assert world.as_dict() == snapshot
    for c in res.candidates:
        if c.parent_candidate_id is not None:
            parent = res.candidate(c.parent_candidate_id)
            assert parent is not None
            assert c.world is not parent.world
            assert c.run_id != parent.run_id


# ----------------------------------------------------------------------
# F. Beam structure: generations feed the next beam, beam_width honored
# ----------------------------------------------------------------------
def test_f_beam_structure() -> None:
    spec = make_spec(generations=2, beam_width=2, children_per_parent=3)
    res = run_toy_search(spec=spec)
    assert len(res.generations) == 3  # generations 0..spec.generations
    g0, g1, g2 = res.generations
    assert g0.parent_candidate_ids == ()
    assert g0.child_candidate_ids == (res.root.candidate_id,)
    assert g0.selected_candidate_ids == (res.root.candidate_id,)
    assert g1.parent_candidate_ids == (res.root.candidate_id,)
    assert len(g1.child_candidate_ids) == 3
    assert len(g1.selected_candidate_ids) == 2
    assert g2.parent_candidate_ids == g1.selected_candidate_ids
    assert all(len(g.selected_candidate_ids) <= 2 for g in res.generations)


# ----------------------------------------------------------------------
# G. Generation flow and lineage in the store
# ----------------------------------------------------------------------
def test_g_generation_lineage() -> None:
    store = LineageStore(":memory:")
    res = run_toy_search(store=store)
    best = res.best()
    assert best is not None
    assert res.lineage_path(best.candidate_id)[0] == res.root.candidate_id
    # Root is a recorded run with no parent; every child links to its parent.
    root_record = store.get_run(res.root.run_id)
    assert root_record is not None and root_record.parent_run_id is None
    for c in res.candidates[1:]:
        record = store.get_run(c.run_id)
        assert record is not None
        assert c.parent_candidate_id is not None
        parent = res.candidate(c.parent_candidate_id)
        assert parent is not None
        assert record.parent_run_id == parent.run_id
        assert c.mutations  # every child carries its mutation record
    assert store.search_count == 1


# ----------------------------------------------------------------------
# H. Profile-driven selection: "interesting" is not "largest value"
# ----------------------------------------------------------------------
def test_h_profile_changes_search() -> None:
    space = MutationSpace((ParameterSweep(TOY_X, (1.5, 2.0, 3.0)),))
    up = InterestingnessProfile(
        name="max-slope",
        description="maximize ramp slope (grows with x)",
        weights={"s1:trend_slope": 1.0},
        directions={"s1:trend_slope": True},
    )
    down = InterestingnessProfile(
        name="min-slope",
        description="minimize ramp slope",
        weights={"s1:trend_slope": 1.0},
        directions={"s1:trend_slope": False},
    )
    res_up = run_toy_search(
        spec=make_spec(name="up", generations=2, beam_width=2, children_per_parent=3, mutation_space=space, profile=up)
    )
    res_down = run_toy_search(
        spec=make_spec(name="down", generations=2, beam_width=2, children_per_parent=3, mutation_space=space, profile=down)
    )
    best_up, best_down = res_up.best(), res_down.best()
    assert best_up is not None and best_down is not None
    assert best_up.candidate_id != best_down.candidate_id
    # Minimizing slope keeps the weakest world (the root control) on top.
    assert best_down.candidate_id == res_down.root.candidate_id
    # Maximizing slope pushes toward the largest x actually reachable.
    assert max(
        m.new_value for m in res_up.mutation_path(best_up.candidate_id)
    ) == pytest.approx(3.0)


# ----------------------------------------------------------------------
# I. Whole-search determinism (canonical output, not just best score)
# ----------------------------------------------------------------------
def test_i_determinism() -> None:
    spec = make_spec(seed=7)
    a = run_toy_search(spec=spec)
    b = run_toy_search(spec=spec)
    assert a.search_id == b.search_id
    assert a.as_dict(canonical=True) == b.as_dict(canonical=True)
    assert [c.run_id for c in a.candidates] == [c.run_id for c in b.candidates]
    best_a, best_b = a.best(), b.best()
    assert best_a is not None and best_b is not None
    assert best_a.candidate_id == best_b.candidate_id

    store = LineageStore(":memory:")
    run_toy_search(store=store, spec=spec, world=make_toy_world())
    run_toy_search(store=store, spec=spec, world=make_toy_world())
    assert store.search_count == 1  # idempotent record


# ----------------------------------------------------------------------
# J. search_id_of is deterministic and sensitive to world/spec
# ----------------------------------------------------------------------
def test_j_search_id() -> None:
    spec = make_spec(seed=3)
    assert search_id_of(make_toy_world(), spec) == search_id_of(make_toy_world(), spec)
    assert len(search_id_of(make_toy_world(), spec)) == 24
    assert search_id_of(make_toy_world(), spec) != search_id_of(
        make_toy_world(), dataclasses.replace(spec, seed=4)
    )
    assert search_id_of(make_toy_world(), spec) != search_id_of(
        make_toy_world(), dataclasses.replace(spec, generations=3)
    )
    assert search_id_of(make_toy_world(), spec) != search_id_of(
        make_toy_world(x=5.0), spec
    )


# ----------------------------------------------------------------------
# K. Final ranking, best(), lineage_path / mutation_path helpers
# ----------------------------------------------------------------------
def test_k_final_ranking_and_paths() -> None:
    res = run_toy_search()
    rows = res.final_ranking.rows
    assert len(rows) == len(res.candidates)
    assert [r.rank for r in rows] == list(range(1, len(rows) + 1))
    best = res.best()
    assert best is not None
    assert rows[0].run_id == best.run_id
    assert best.final_rank == 1
    assert sorted(c.final_rank for c in res.candidates if c.final_rank is not None) == list(
        range(1, len(res.candidates) + 1)
    )
    assert res.lineage_path(res.root.candidate_id) == (res.root.candidate_id,)
    assert res.mutation_path(res.root.candidate_id) == ()
    lines = res.explain_best()
    assert lines and lines[0].startswith("rank 1")
    # Unknown candidate -> empty helpers.
    assert res.lineage_path("candidate-999") == ()
    assert res.mutation_path("candidate-999") == ()


# ----------------------------------------------------------------------
# L. Compact persistence only; idempotent recording
# ----------------------------------------------------------------------
def test_l_persistence_compact(tmp_path) -> None:
    db_path = tmp_path / "search.db"
    store = LineageStore(str(db_path))
    spec = make_spec()
    res = SearchRunner(store, toy_executor, toy_observables).search(
        make_toy_world(), spec
    )
    rec = store.get_search(res.search_id)
    assert rec is not None
    assert rec["spec"]["generations"] == spec.generations
    assert rec["world_hash"] == world_hash(make_toy_world())
    assert rec["base_run_id"] == res.root.run_id
    assert len(rec["candidates"]) == len(res.candidates)
    assert rec["generation_order"][0] == [res.root.candidate_id]
    assert set(rec["timing"]) == {
        "n_generated",
        "n_skipped",
        "n_executed",
        "total_seconds",
        "execution_seconds",
        "analysis_seconds",
        "mean_seconds",
    }
    # No per-step data leaks into the search record.
    assert all("observables" not in c for c in rec["candidates"])
    assert all("features" not in c for c in rec["candidates"])
    # Run records carry compact feature snapshots (never trajectories).
    for c in res.candidates:
        stored = store.get_run(c.run_id)
        assert stored is not None and stored.feature_snapshot is not None
    # Re-running the same search is idempotent.
    SearchRunner(store, toy_executor, toy_observables).search(make_toy_world(), spec)
    assert store.search_count == 1
    store.close()


# ----------------------------------------------------------------------
# M. Core search source is experiment-free
# ----------------------------------------------------------------------
def test_m_core_search_is_experiment_free() -> None:
    core_dir = REPO_ROOT / "src" / "sim_alchemist" / "core"
    for name in ("search.py",):
        source = (core_dir / name).read_text(encoding="utf-8").lower()
        hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
        assert not hits, f"{name} contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# N. Real Experiment C search executes end to end and is reproducible
# ----------------------------------------------------------------------
def load_fast_world() -> WorldDefinition:
    world = load_world_yaml(WORLDS / "adaptive_network.yaml")
    cfg = dict(world.config)
    cfg["n_steps"] = FAST_STEPS
    return dataclasses.replace(world, max_steps=FAST_STEPS, config=cfg)


def test_n_experiment_c_search_runs() -> None:
    world = load_fast_world()
    space = MutationSpace(
        (ParameterSweep("components.network.config.loss", (0.05, 0.08, 0.11, 0.14)),)
    )
    profile = InterestingnessProfile(
        name="expc-search",
        description="prefer wall activity and field oscillation, prefer "
        "stable network-load max",
        weights={
            "wall_count:activity_rate": 0.4,
            "field_mean:oscillation_strength": 0.3,
            "network_load_max:late_vs_full_variance_ratio": 0.3,
        },
        directions={
            "wall_count:activity_rate": True,
            "field_mean:oscillation_strength": True,
            "network_load_max:late_vs_full_variance_ratio": False,
        },
    )
    spec = SearchSpec(
        "expc-search", 1, 1, 3, space, profile, seed=0
    )

    def make_runner(store: LineageStore) -> SearchRunner:
        return SearchRunner(
            store,
            run_network_world,
            lambda outcome: build_network_observables(outcome.trajectory),
            parameter_specs=specs_by_path(),
        )

    res = make_runner(LineageStore(":memory:")).search(world, spec)
    assert len(res.generations) == 2  # gen 0 + one expansion
    assert 2 <= len(res.candidates) <= 4  # root + up to 3 unique loss variants
    assert res.candidates[0].kind == "baseline"
    assert all(c.kind == "variant" for c in res.candidates[1:])
    for c in res.candidates[1:]:
        assert c.features is not None
        flat = c.features.flatten()
        assert "wall_count:total_variation" in flat
        assert "growth_event:activity_rate" in flat
        assert c.parent_candidate_id == res.root.candidate_id
    assert res.root.metrics["wall_count"] >= 0

    res2 = make_runner(LineageStore(":memory:")).search(world, spec)
    assert res.as_dict(canonical=True) == res2.as_dict(canonical=True)
    best1, best2 = res.best(), res2.best()
    assert best1 is not None and best2 is not None
    assert best1.candidate_id == best2.candidate_id


# ----------------------------------------------------------------------
# O. Performance instrumentation
# ----------------------------------------------------------------------
def test_o_timing_instrumentation() -> None:
    res = run_toy_search()
    t = res.timing
    assert t.n_executed == len(res.candidates)
    assert t.n_generated >= t.n_executed - 1
    assert t.total_seconds >= 0.0
    assert t.execution_seconds >= 0.0
    assert t.analysis_seconds == pytest.approx(
        max(0.0, t.total_seconds - t.execution_seconds)
    )
    assert t.mean_seconds == pytest.approx(
        t.execution_seconds / max(1, t.n_executed)
    )
    assert set(t.as_dict()) == {
        "n_generated",
        "n_skipped",
        "n_executed",
        "total_seconds",
        "execution_seconds",
        "analysis_seconds",
        "mean_seconds",
        "n_distance_calcs",
    }
    # Quality-only (default) search performs no diversity distance calcs.
    assert t.n_distance_calcs == 0