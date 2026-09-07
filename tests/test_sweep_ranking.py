"""Task 1.7 validation: deterministic variant sweeps + generic ranking (A-Q).

Uses the generic core directly (``MutationSpace`` / ``SweepRunner`` /
``rank_results``) against a fast deterministic executor, plus one real
Experiment C (Adaptive Network Morphogenesis) sweep at small length as the
live subject.

Checks:

    A  One-dimensional sweep: generation order matches the declared order
    B  Multi-dimensional sweep: documented Cartesian product order
    C  Variant identity is deterministic (same world + space => same run ids)
    D  Sweep id is deterministic across stores/runs
    E  Repeated sweep reproduces identical run ids, metrics, and ranking
    F  Baseline control is included, recorded first, and never mutated
    G  The base world object is never mutated in place by a sweep
    H  ParameterSpec bounds are enforced before any variant executes
    I  A repeated value combination is skipped (counted, not re-executed)
    J  Sweep lineage links every variant to the base run in the store
    K  Compact sweep metadata is persisted (no trajectories)
    L  Ranking picks one metric, respects direction, breaks ties by run id
    M  Ranking handles ascending mode deterministically
    N  The core contains no experiment-specific identifiers (incl. sweep.py)
    O  A real Experiment C sweep executes end to end (4-12 variants)
    P  Sweep metrics are stored generically alongside the runs
    Q  Performance instrumentation (variant count, total/mean duration)
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest

from experiments.network_morphogenesis.experiment import (
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    ExecOutcome,
    InvalidMutationValueError,
    LineageStore,
    MutationSpace,
    ParameterSweep,
    SweepResult,
    SweepRunner,
    WorldDefinition,
    load_world_yaml,
)
from sim_alchemist.core.sweep import rank_results

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
# Helpers: a tiny generic world + a deterministic, fast executor.
# ----------------------------------------------------------------------
TOY_PATH = "components.toy.config.x"
TOY_Y = "config.y"


def make_toy_world(x: float = 1.0, y: float = 10.0, seed: int = 0) -> WorldDefinition:
    from sim_alchemist.core import ComponentSpec

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
    return ExecOutcome(world=world, metrics={"x2": 2.0 * x, "s": x + y})


def make_toy_space() -> MutationSpace:
    return MutationSpace((ParameterSweep(TOY_PATH, (1.5, 2.0, 3.0)),))


def sweep_toy(world=None, space=None, store=None) -> SweepResult:
    store = store if store is not None else LineageStore(":memory:")
    runner = SweepRunner(store, toy_executor)
    return runner.sweep(world or make_toy_world(), space or make_toy_space())


# ----------------------------------------------------------------------
# A. 1-D sweep generation order
# ----------------------------------------------------------------------
def test_a_one_dim_generation_order() -> None:
    space = make_toy_space()
    sets = space.variant_mutation_sets()
    assert len(sets) == 3
    assert [m.new_value for (m,) in sets] == [1.5, 2.0, 3.0]
    assert space.variant_count == 3


# ----------------------------------------------------------------------
# B. Multi-D Cartesian product order (documented)
# ----------------------------------------------------------------------
def test_b_multidim_cartesian_order() -> None:
    space = MutationSpace(
        (
            ParameterSweep("config.y", (10.0, 20.0, 30.0)),
            ParameterSweep(TOY_PATH, (1.0, 2.0)),
        )
    )
    sets = space.variant_mutation_sets()
    assert space.variant_count == 6
    order = [(m2.new_value, m1.new_value) for m1, m2 in sets]
    assert order == [
        (1.0, 10.0),
        (2.0, 10.0),
        (1.0, 20.0),
        (2.0, 20.0),
        (1.0, 30.0),
        (2.0, 30.0),
    ]


# ----------------------------------------------------------------------
# C. Deterministic variant identity
# ----------------------------------------------------------------------
def test_c_variant_identity_deterministic() -> None:
    world = make_toy_world()
    space = make_toy_space()
    store_a = LineageStore(":memory:")
    store_b = LineageStore(":memory:")
    res_a = SweepRunner(store_a, toy_executor).sweep(world, space)
    res_b = SweepRunner(store_b, toy_executor).sweep(world, space)
    ids_a = [v.run_id for v in res_a.variants]
    ids_b = [v.run_id for v in res_b.variants]
    assert ids_a == ids_b
    assert len(set(ids_a)) == 3  # no two variants collapse
    assert res_a.base.run_id == res_b.base.run_id


# ----------------------------------------------------------------------
# D. Sweep id deterministic
# ----------------------------------------------------------------------
def test_d_sweep_id_deterministic() -> None:
    from sim_alchemist.core import sweep_id_of

    space = make_toy_space()
    id1 = sweep_id_of(make_toy_world(), space)
    id2 = sweep_id_of(make_toy_world(), space)
    assert id1 == id2
    assert len(id1) == 24
    # A different value set yields a different sweep id.
    other = MutationSpace((ParameterSweep(TOY_PATH, (1.0, 2.0, 3.0, 4.0)),))
    assert sweep_id_of(make_toy_world(), other) != id1
    # Two identical sweeps in one store collapse to one metadata record.
    store = LineageStore(":memory:")
    res = sweep_toy(store=store)
    assert res.sweep_id == id1
    assert store.sweep_count == 1


# ----------------------------------------------------------------------
# E. Repeatability: run twice -> identical ids, metrics, ranking
# ----------------------------------------------------------------------
def test_e_repeat_sweep_identical() -> None:
    world = make_toy_world()
    res_1 = sweep_toy(world)
    res_2 = sweep_toy(world)
    assert [r.run_id for r in res_1.all_runs()] == [r.run_id for r in res_2.all_runs()]
    assert [r.metrics for r in res_1.all_runs()] == [r.metrics for r in res_2.all_runs()]
    assert res_1.ranking("x2") == res_2.ranking("x2")


# ----------------------------------------------------------------------
# F. Baseline control included, recorded first, unmutated
# ----------------------------------------------------------------------
def test_f_baseline_control_included() -> None:
    res = sweep_toy()
    base = res.base
    assert base.parent_run_id is None
    assert base.metrics == {"x2": 2.0, "s": 11.0}
    assert res.n_executed == 3
    # Baseline metrics correspond to the unmutated world.
    assert base.metrics == toy_executor(make_toy_world()).metrics
    # Every variant is a child of the base run.
    assert all(v.parent_run_id == base.run_id for v in res.variants)


# ----------------------------------------------------------------------
# G. Base world object never mutated in place
# ----------------------------------------------------------------------
def test_g_base_world_not_mutated() -> None:
    world = make_toy_world()
    snapshot = world.as_dict()
    res = sweep_toy(world)
    assert world.as_dict() == snapshot
    assert world.components[0].config["x"] == pytest.approx(1.0)
    # Each returned variant world carries its own mutated value.
    for v in res.variants:
        assert v.world.components[0].config["x"] in (1.5, 2.0, 3.0)


def test_g_baseline_child_equals_base_run_id() -> None:
    # Sweeping a value that equals the base value yields no duplicate run.
    world = make_toy_world(x=1.0)
    space = MutationSpace((ParameterSweep(TOY_PATH, (1.0, 2.0)),))
    res = SweepRunner(LineageStore(":memory:"), toy_executor).sweep(world, space)
    assert res.n_executed == 1  # the 1.0 -> 1.0 no-op combination is skipped
    assert res.timing.n_skipped == 1
    assert res.variants[0].metrics == {"x2": 4.0, "s": 12.0}


# ----------------------------------------------------------------------
# H. Bounds enforced before any variant executes
# ----------------------------------------------------------------------
def test_h_parameter_specs_enforced() -> None:
    specs = {"config.y": specs_by_path()["config.force_fmax"]}
    space = MutationSpace((ParameterSweep("config.y", (10.0, 100.0)),))
    runner = SweepRunner(LineageStore(":memory:"), toy_executor, parameter_specs=specs)
    with pytest.raises(InvalidMutationValueError):
        runner.sweep(make_toy_world(), space)
    assert runner.store.run_count == 0  # nothing executed

    # Valid values pass.
    ok_space = MutationSpace((ParameterSweep("config.y", (0.5, 2.0)),))
    ok = SweepRunner(LineageStore(":memory:"), toy_executor, parameter_specs=specs).sweep(
        make_toy_world(y=0.5), ok_space
    )
    assert ok.n_executed == 1


# ----------------------------------------------------------------------
# I. Repeated combination skipped, counted, not re-executed
# ----------------------------------------------------------------------
def test_i_duplicate_combination_skipped() -> None:
    world = make_toy_world(x=1.0, y=10.0)
    space = MutationSpace(
        (
            ParameterSweep(TOY_PATH, (1.0, 2.0)),
            ParameterSweep("config.y", (10.0, 20.0)),
        )
    )
    res = SweepRunner(LineageStore(":memory:"), toy_executor).sweep(world, space)
    # (x=1,y=10) reproduces the base, (x=1,y=20) and (x=2,y=10) run.
    assert res.timing.n_planned == 4
    assert res.timing.n_skipped == 1
    assert res.timing.n_executed == 3
    assert res.n_executed == 3


# ----------------------------------------------------------------------
# J. Sweep lineage links all variants to base
# ----------------------------------------------------------------------
def test_j_sweep_lineage_links_variants() -> None:
    store = LineageStore(":memory:")
    res = sweep_toy(store=store)
    children = store.children_of(res.base.run_id)
    assert len(children) == 3
    assert {c.run_id for c in children} == {v.run_id for v in res.variants}
    assert store.run_count == 4
    assert all(len(c.mutations) == 1 for c in children)


# ----------------------------------------------------------------------
# K. Compact sweep metadata persisted (no trajectories)
# ----------------------------------------------------------------------
def test_k_sweep_metadata_persisted(tmp_path) -> None:
    db_path = tmp_path / "lineage.db"
    store = LineageStore(str(db_path))
    res = sweep_toy(store=store)
    record = store.get_sweep(res.sweep_id)
    assert record is not None
    assert record.base_run_id == res.base.run_id
    assert record.n_executed == 3
    assert record.n_skipped == 0
    assert record.world_id == "toy"
    assert list(record.variant_run_ids) == [v.run_id for v in res.variants]
    assert record.mutation_space == [
        {"path": TOY_PATH, "values": [1.5, 2.0, 3.0]}
    ]
    assert record.total_seconds >= 0.0 and record.mean_seconds >= 0.0
    # Runs persist with full metric summaries.
    for v in res.variants:
        stored = store.get_run(v.run_id)
        assert stored is not None and stored.metrics == v.metrics
    store.close()


# ----------------------------------------------------------------------
# L. Generic ranking: direction + deterministic tie-break
# ----------------------------------------------------------------------
def test_l_ranking_direction_and_tie_break() -> None:
    world = make_toy_world(x=1.0, y=10.0)
    space = MutationSpace(
        (
            ParameterSweep(TOY_PATH, (1.0, 2.0)),
            ParameterSweep("config.y", (10.0, 20.0)),
        )
    )
    res = SweepRunner(LineageStore(":memory:"), toy_executor).sweep(world, space)

    # Descending by "s": (x=2,y=20)=22, (x=1,y=20)=21, (x=2,y=10)=12, base=11.
    by_s = res.ranking("s")
    assert [e.rank for e in by_s] == [1, 2, 3, 4]
    assert [e.kind for e in by_s] == ["variant", "variant", "variant", "baseline"]
    assert by_s[0].value == pytest.approx(22.0)
    assert by_s[-1].value == pytest.approx(11.0)
    assert by_s[-1].run_id == res.base.run_id

    # Ascending (best = smallest).
    by_s_asc = res.ranking("s", descending=False)
    assert by_s_asc[0].value == pytest.approx(11.0)

    # Deterministic tie-break: variants with an equal metric value sort by
    # run id ascending (the ranking is still a pure function of the runs).
    tie_world = make_toy_world(x=1.0, y=10.0)
    tie_space = MutationSpace((ParameterSweep("config.y", (10.0, 20.0, 30.0)),))
    tie_res = SweepRunner(LineageStore(":memory:"), toy_executor).sweep(tie_world, tie_space)
    assert tie_res.n_executed == 2  # the y=10 combination is the no-op control
    ranking = tie_res.ranking("x2")  # x2 = 2*x: identical for every run here
    assert len(ranking) == 3
    assert all(e.value == pytest.approx(2.0) for e in ranking)
    assert [e.run_id for e in ranking] == sorted(e.run_id for e in ranking)
    assert ranking[0].run_id == min(e.run_id for e in ranking)


# ----------------------------------------------------------------------
# M. Ranking with an arbitrary metric name (no special-casing)
# ----------------------------------------------------------------------
def test_m_ranking_generic_metric_selection() -> None:
    res = sweep_toy()
    by_s = res.ranking("s")
    assert len(by_s) == 4
    assert by_s[0].value == pytest.approx(13.0)  # x=3,y=10
    assert rank_results(res.all_runs(), "s")[0].value == pytest.approx(13.0)
    # Unknown metric raises.
    with pytest.raises(ValueError):
        res.ranking("no_such_metric")


# ----------------------------------------------------------------------
# N. Core sweep source is experiment-free
# ----------------------------------------------------------------------
def test_n_core_sweep_is_experiment_free() -> None:
    core_dir = REPO_ROOT / "src" / "sim_alchemist" / "core"
    source = (core_dir / "sweep.py").read_text(encoding="utf-8").lower()
    hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
    assert not hits, f"sweep.py contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# O. Real Experiment C sweep (4-12 variants), end to end
# ----------------------------------------------------------------------
def load_fast_world() -> WorldDefinition:
    world = load_world_yaml(WORLDS / "adaptive_network.yaml")
    cfg = dict(world.config)
    cfg["n_steps"] = FAST_STEPS
    return dataclasses.replace(world, max_steps=FAST_STEPS, config=cfg)


def test_o_experiment_c_sweep_runs() -> None:
    world = load_fast_world()
    space = MutationSpace(
        (
            ParameterSweep("components.network.config.loss", (0.05, 0.08, 0.11, 0.14)),
            ParameterSweep("config.force_fmax", (0.4, 0.8)),
        )
    )
    store = LineageStore(":memory:")
    runner = SweepRunner(store, run_network_world, parameter_specs=specs_by_path())
    res = runner.sweep(world, space)

    assert 4 <= res.n_executed <= 12
    assert res.n_executed == 7  # 4 x 2 minus the (0.05, 0.8) no-op = 7
    base = res.base
    assert base.metrics["wall_count"] > 0
    assert base.parent_run_id is None
    # Every variant is a child of the base and carries real metrics.
    for v in res.variants:
        assert v.parent_run_id == base.run_id
        assert v.mutations
        assert "field_entropy" in v.metrics
    # Ranking is available end to end.
    ranking = res.ranking("field_entropy")
    assert {e.kind for e in ranking} == {"baseline", "variant"}
    assert [e.rank for e in ranking] == list(range(1, len(ranking) + 1))


# ----------------------------------------------------------------------
# P. Sweep metrics stored generically alongside runs
# ----------------------------------------------------------------------
def test_p_metrics_stored_in_lineage(tmp_path) -> None:
    store = LineageStore(str(tmp_path / "lineage.db"))
    res = sweep_toy(store=store)
    all_run_ids = [r.run_id for r in res.all_runs()]
    stored = {r.run_id: r.metrics for r in store.iter_runs()}
    assert set(stored) == set(all_run_ids)
    # The store is idempotent for a replayed sweep.
    sweep_toy(store=store)
    assert store.run_count == 4
    store.close()


# ----------------------------------------------------------------------
# Q. Performance instrumentation
# ----------------------------------------------------------------------
def test_q_timing_instrumentation() -> None:
    res = sweep_toy()
    t = res.timing
    assert t.n_planned == 3
    assert t.n_executed == 3
    assert t.total_seconds >= 0.0
    assert t.mean_seconds == pytest.approx(t.total_seconds / t.n_executed)
    assert t.as_dict()["n_executed"] == 3
    # A larger sweep reports its own count.
    big_space = MutationSpace(
        (
            ParameterSweep(TOY_PATH, (1.0, 2.0, 3.0)),
            ParameterSweep("config.y", (1.0, 2.0, 3.0)),
        )
    )
    big = SweepRunner(LineageStore(":memory:"), toy_executor).sweep(
        make_toy_world(), big_space
    )
    assert big.timing.n_planned == 9
    assert big.timing.n_executed == 9
    assert big.timing.mean_seconds == pytest.approx(
        big.timing.total_seconds / 9.0
    )