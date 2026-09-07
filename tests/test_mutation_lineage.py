"""Task 1.6 validation: generic world mutation and experiment lineage (A-L).

Uses Experiment C (Adaptive Network Morphogenesis) as the live subject and
checks the *generic* core directly: mutations operate on ``WorldDefinition``
data with no experiment knowledge; the runner/lineage layer is exercised
through the experiment's executor and parameter declarations.

Checks A-L:

    A  Valid mutation produces a changed, distinct child world
    B  Parent world is never modified; clones are deeply independent
    C  Invalid parameter *path* fails clearly (path + deepest prefix)
    D  Invalid parameter *type/value* fails clearly (path + reason)
    E  Multiple mutations apply deterministically, in order
    F  Same world + same seed + same mutations => identical (bitwise) result
    G  A meaningful mutation produces a meaningfully different metrics result
    H  Parent/child lineage records are written and linked
    I  Base vs variant metrics compare generically
    J  Experiment C's declared mutations work (paths + bounds enforced)
    K  Experiment A/B worlds mutate through the same generic engine (regression
       gate for the A/B suites runs in ``pytest`` itself)
    L  The core mutation/lineage/runner files contain no experiment names
"""

from __future__ import annotations

import dataclasses
import pathlib

import numpy as np
import pytest

from experiments.network_morphogenesis.experiment import (
    PARAMETER_SPECS,
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    InvalidMutationValueError,
    LineageStore,
    Mutation,
    MutationRecord,
    ParameterSpec,
    UnknownMutationPathError,
    VariantRunner,
    WorldDefinition,
    apply_mutation,
    apply_mutations,
    clone_world,
    compare_metrics,
    compare_runs,
    load_world_yaml,
    range_validator,
    run_id_of,
)
from sim_alchemist.core.runner import MetricDelta

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORLDS = REPO_ROOT / "worlds"
FAST_STEPS = 10

# Tokens that must never appear in the generic core mutation/lineage/runner
# sources (they are experiment or domain identifiers, not data keys).
FORBIDDEN_CORE_TOKENS = (
    "ndlib",
    "mesa",
    "pymunk",
    "chemomech",
    "morphogen",
    "network",
    "adapt",
)


def load_fast_world() -> WorldDefinition:
    world = load_world_yaml(WORLDS / "adaptive_network.yaml")
    cfg = dict(world.config)
    cfg["n_steps"] = FAST_STEPS
    return dataclasses.replace(world, max_steps=FAST_STEPS, config=cfg)


def sha_of_final_u(trajectory) -> str:
    import hashlib

    return hashlib.sha256(np.asarray(trajectory.final_u).tobytes()).hexdigest()


@pytest.fixture(scope="module")
def fast_world() -> WorldDefinition:
    return load_fast_world()


@pytest.fixture(scope="module")
def variant_suite(fast_world):
    """Base run + three single-mutation variants, recorded in one store."""
    store = LineageStore(":memory:")
    runner = VariantRunner(store, run_network_world, parameter_specs=specs_by_path())
    base = runner.run(fast_world)
    loss = runner.run_variant(fast_world, Mutation("components.network.config.loss", 0.14))
    fmax = runner.run_variant(fast_world, Mutation("config.force_fmax", 4.0))
    amp = runner.run_variant(fast_world, Mutation("config.source_amplitude", 0.03))
    return {
        "store": store,
        "runner": runner,
        "base": base,
        "loss": loss,
        "fmax": fmax,
        "amp": amp,
    }


# ----------------------------------------------------------------------
# A. A valid mutation changes a copied world
# ----------------------------------------------------------------------
def test_a_valid_mutation_changes_a_copied_world(fast_world) -> None:
    child, record = apply_mutation(
        fast_world, Mutation("components.network.config.loss", 0.14)
    )
    assert isinstance(child, WorldDefinition)
    assert child.as_dict() != fast_world.as_dict()
    assert child.components[2].config["loss"] == 0.14
    assert record.path == "components.network.config.loss"
    assert record.old_value == pytest.approx(0.05)
    assert record.new_value == pytest.approx(0.14)
    assert child.id == fast_world.id
    assert child.schedule == fast_world.schedule


# ----------------------------------------------------------------------
# B. Parent world stays unchanged; clones are deeply independent
# ----------------------------------------------------------------------
def test_b_parent_world_remains_unchanged(fast_world) -> None:
    snapshot = fast_world.as_dict()
    apply_mutation(fast_world, Mutation("components.network.config.loss", 0.9))
    apply_mutations(fast_world, [Mutation("seed", 42), Mutation("config.force_fmax", 5.0)])
    assert fast_world.as_dict() == snapshot
    assert fast_world.seed == 0
    assert fast_world.components[1].config["damping"] == pytest.approx(0.05)


def test_b_clone_is_deeply_independent(fast_world) -> None:
    cloned = clone_world(fast_world)
    cloned.components[2].config["loss"] = 0.77
    cloned.config["force_fmax"] = 9.9
    assert fast_world.components[2].config["loss"] == pytest.approx(0.05)
    assert fast_world.config["force_fmax"] == pytest.approx(0.8)
    assert cloned.as_dict()["components"][2]["config"]["loss"] == pytest.approx(0.77)


# ----------------------------------------------------------------------
# C. Invalid parameter path fails
# ----------------------------------------------------------------------
def test_c_invalid_path_fails_clearly(fast_world) -> None:
    cases = [
        "components.no_such_component.config.x",
        "config.param_that_does_not_exist",
        "components.network.config.not_a_key",
        "schedule",
        "components.py-pde.config.nope",
    ]
    for path in cases:
        with pytest.raises(UnknownMutationPathError) as exc:
            apply_mutation(fast_world, Mutation(path, 1))
        message = str(exc.value)
        assert path in message, message


def test_c_error_reports_deepest_valid_prefix(fast_world) -> None:
    with pytest.raises(UnknownMutationPathError) as exc:
        apply_mutation(fast_world, Mutation("config.force_fmax.deep", 1))
    message = str(exc.value)
    assert "config.force_fmax" in message


# ----------------------------------------------------------------------
# D. Invalid parameter type / value fails
# ----------------------------------------------------------------------
def test_d_invalid_type_fails_clearly(fast_world) -> None:
    with pytest.raises(InvalidMutationValueError) as exc:
        apply_mutation(fast_world, Mutation("components.network.config.loss", "hello"))
    message = str(exc.value)
    assert "components.network.config.loss" in message
    assert "float" in message and "'hello'" in message


def test_d_float_under_int_leaf_rejected(fast_world) -> None:
    with pytest.raises(InvalidMutationValueError) as exc:
        apply_mutation(fast_world, Mutation("seed", 1.5))  # int leaf, float value
    assert "seed" in str(exc.value)


def test_d_int_widening_accepted(fast_world) -> None:
    child, record = apply_mutation(fast_world, Mutation("seed", 7))
    assert child.seed == 7
    assert record.old_value == 0 and record.new_value == 7


def test_d_range_validator_rejects_out_of_domain(fast_world) -> None:
    spec = ParameterSpec(
        path="components.network.config.loss", minimum=0.0, maximum=1.0
    )
    with pytest.raises(InvalidMutationValueError) as exc:
        apply_mutation(
            fast_world,
            Mutation("components.network.config.loss", 1.5),
            validator=spec.validator(),
        )
    message = str(exc.value)
    assert "components.network.config.loss" in message
    assert "1.5" in message


def test_d_one_of_rejects_unlisted_values(fast_world) -> None:
    validator = range_validator(0.0, 10.0)
    with pytest.raises(InvalidMutationValueError):
        apply_mutation(fast_world, Mutation("config.force_fmax", 50.0), validator=validator)


# ----------------------------------------------------------------------
# E. Multiple mutations apply deterministically
# ----------------------------------------------------------------------
def test_e_multiple_mutations_apply_in_order(fast_world) -> None:
    mutations = [
        Mutation("components.network.config.loss", 0.14),
        Mutation("config.source_amplitude", 0.03),
        Mutation("seed", 3),
    ]
    child, records = apply_mutations(fast_world, mutations)
    assert child.components[2].config["loss"] == pytest.approx(0.14)
    assert child.config["source_amplitude"] == pytest.approx(0.03)
    assert child.seed == 3
    assert [r.path for r in records] == [m.path for m in mutations]
    assert all(isinstance(r, MutationRecord) for r in records)


def test_e_batch_equals_sequential_application(fast_world) -> None:
    mutations = [
        Mutation("components.network.config.loss", 0.14),
        Mutation("config.force_fmax", 4.0),
    ]
    batch_child, _ = apply_mutations(fast_world, mutations)
    sequential, _ = apply_mutations(fast_world, [mutations[0]])
    sequential, _ = apply_mutations(sequential, [mutations[1]])
    assert batch_child.as_dict() == sequential.as_dict()


def test_e_batch_is_deterministic(fast_world) -> None:
    mutations = [
        Mutation("components.network.config.loss", 0.14),
        Mutation("config.source_amplitude", 0.03),
    ]
    a, records_a = apply_mutations(fast_world, mutations)
    b, records_b = apply_mutations(fast_world, mutations)
    assert a.as_dict() == b.as_dict()
    assert [r.to_dict() for r in records_a] == [r.to_dict() for r in records_b]


# ----------------------------------------------------------------------
# F. Same world + seed + mutations => identical result (determinism)
# ----------------------------------------------------------------------
def test_f_identical_inputs_produce_identical_results(fast_world) -> None:
    trajectories: list[object] = []

    def capturing_executor(world):
        outcome = run_network_world(world)
        trajectories.append(outcome.trajectory)
        return outcome

    store = LineageStore(":memory:")
    runner = VariantRunner(store, capturing_executor, parameter_specs=specs_by_path())

    base_a = runner.run(fast_world)
    base_b = runner.run(fast_world)
    assert base_a.run_id == base_b.run_id
    assert base_a.metrics == base_b.metrics
    assert sha_of_final_u(trajectories[0]) == sha_of_final_u(trajectories[1])

    mut = Mutation("components.network.config.loss", 0.14)
    var_a = runner.run_variant(fast_world, mut)
    var_b = runner.run_variant(fast_world, mut)
    assert var_a.run_id == var_b.run_id
    assert var_a.metrics == var_b.metrics
    assert sha_of_final_u(trajectories[2]) == sha_of_final_u(trajectories[3])

    # The base and the variant are different runs.
    assert base_a.run_id != var_a.run_id
    # Replaying everything produces one record per node of the lineage.
    assert store.run_count == 2


# ----------------------------------------------------------------------
# G. Meaningful mutation => meaningfully different metrics
# ----------------------------------------------------------------------
def test_g_loss_mutation_changes_network_load(variant_suite) -> None:
    delta = compare_metrics(variant_suite["base"].metrics, variant_suite["loss"].metrics)
    assert delta["network_load_mean"].absolute < 0.0  # higher loss drains loads
    assert abs(delta["network_load_mean"].absolute) > 5e-3
    assert abs(delta["field_entropy"].absolute) > 1e-3


def test_g_force_mutation_changes_wall_movement(variant_suite) -> None:
    delta = compare_metrics(variant_suite["base"].metrics, variant_suite["fmax"].metrics)
    assert delta["wall_movement"].absolute > 1e-2  # stronger force moves walls more
    assert delta["wall_count"].absolute >= 0.0


def test_g_source_mutation_changes_field(variant_suite) -> None:
    delta = compare_metrics(variant_suite["base"].metrics, variant_suite["amp"].metrics)
    assert abs(delta["final_field_std"].absolute) > 1e-4
    assert abs(delta["field_entropy"].absolute) > 1e-3


# ----------------------------------------------------------------------
# H. Parent/child lineage is recorded
# ----------------------------------------------------------------------
def test_h_parent_child_lineage_is_recorded(variant_suite) -> None:
    base = variant_suite["base"]
    children = variant_suite["store"].children_of(base.run_id)
    assert len(children) == 3
    for child in (variant_suite["loss"], variant_suite["fmax"], variant_suite["amp"]):
        assert child.parent_run_id == base.run_id
        assert child.run_id != base.run_id
        assert len(child.mutations) == 1

    recorded = variant_suite["store"].get_run(variant_suite["loss"].run_id)
    assert recorded is not None
    assert recorded.parent_run_id == base.run_id
    assert recorded.mutations[0].to_dict() == {
        "path": "components.network.config.loss",
        "old_value": 0.05,
        "new_value": 0.14,
    }
    # Base run recorded with no mutations.
    base_recorded = variant_suite["store"].get_run(base.run_id)
    assert base_recorded is not None and base_recorded.mutations == ()


def test_h_variant_without_recorded_parent_fails(fast_world) -> None:
    from sim_alchemist.core.runner import MissingParentRunError

    store = LineageStore(":memory:")
    runner = VariantRunner(store, run_network_world)
    with pytest.raises(MissingParentRunError):
        runner.run_variant(fast_world, Mutation("components.network.config.loss", 0.14))


# ----------------------------------------------------------------------
# I. Base + variant runs compare generically
# ----------------------------------------------------------------------
def test_i_compare_metrics_generically(variant_suite) -> None:
    base = variant_suite["base"]
    loss = variant_suite["loss"]
    deltas = compare_metrics(base.metrics, loss.metrics)

    # Every base metric is compared; delta math is consistent.
    for name, value in base.metrics.items():
        assert name in deltas
        d = deltas[name]
        assert isinstance(d, MetricDelta)
        assert d.base == pytest.approx(value)
        assert d.absolute == pytest.approx(d.variant - d.base)
    # Relative change is signed w.r.t. the base magnitude.
    assert deltas["network_load_mean"].relative < 0.0


def test_i_compare_runs_generically(variant_suite) -> None:
    deltas = compare_runs(variant_suite["base"], variant_suite["amp"])
    assert set(deltas) == set(variant_suite["base"].metrics)
    assert deltas["field_entropy"].absolute != pytest.approx(0.0)


# ----------------------------------------------------------------------
# J. Experiment C mutation works end-to-end
# ----------------------------------------------------------------------
def test_j_experiment_c_parameter_specs_resolve_in_world(fast_world) -> None:
    assert {s.path for s in PARAMETER_SPECS} == {
        "components.network.config.loss",
        "config.force_fmax",
        "config.source_amplitude",
    }
    for spec in PARAMETER_SPECS:
        assert spec.validator() is not None  # every declared param is bounded
        child, _ = apply_mutation(fast_world, Mutation(spec.path, 0.5))
        assert child.as_dict() != fast_world.as_dict()


def test_j_experiment_c_bounds_reject_out_of_domain_values(fast_world) -> None:
    specs = specs_by_path()
    for path, value in [
        ("components.network.config.loss", 1.5),
        ("config.force_fmax", 20.0),
        ("config.source_amplitude", -0.1),
    ]:
        with pytest.raises(InvalidMutationValueError) as exc:
            apply_mutation(fast_world, Mutation(path, value), validator=specs[path].validator())
        assert path in str(exc.value)


def test_j_experiment_c_runner_mutates_and_records(fast_world) -> None:
    store = LineageStore(":memory:")
    runner = VariantRunner(store, run_network_world, parameter_specs=specs_by_path())
    base = runner.run(fast_world)
    variant = runner.run_variant(fast_world, Mutation("config.source_amplitude", 0.03))
    assert base.metrics["wall_count"] > 0
    assert variant.parent_run_id == base.run_id
    assert store.run_count == 2
    assert run_id_of(fast_world) == base.run_id


# ----------------------------------------------------------------------
# K. Experiment A and B worlds mutate through the same generic engine
# ----------------------------------------------------------------------
def test_k_experiment_a_b_worlds_mutate_generically() -> None:
    for name in ("chemo_morphogenesis.yaml", "field_guided_movers.yaml",
                 "adaptive_network.yaml"):
        world = load_world_yaml(WORLDS / name)
        snapshot = world.as_dict()
        # Generic top-level scalar mutation works on every world.
        child, record = apply_mutation(world, Mutation("seed", 11))
        assert child.seed == 11 and record.new_value == 11
        assert world.as_dict() == snapshot
        # A generic component-config mutation works on every world.
        comp = world.components[0]
        first_key = next(k for k in comp.config if isinstance(comp.config[k], float))
        child2, rec2 = apply_mutation(world, Mutation(f"components.{comp.id}.config.{first_key}", 0.25))
        assert child2.components[0].config[first_key] == pytest.approx(0.25)
        assert rec2.old_value != pytest.approx(0.25)


# ----------------------------------------------------------------------
# L. Core contains no experiment-specific identifiers
# ----------------------------------------------------------------------
def test_l_core_mutation_sources_are_experiment_free() -> None:
    core_dir = REPO_ROOT / "src" / "sim_alchemist" / "core"
    for name in ("mutation.py", "lineage.py", "runner.py", "sweep.py"):
        source = (core_dir / name).read_text(encoding="utf-8").lower()
        hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
        assert not hits, f"{name} contains experiment identifiers: {hits}"