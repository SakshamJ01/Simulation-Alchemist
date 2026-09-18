"""Focused Stage 3 integration tests for Experiment D (Gated Mover Morphogenesis).

These tests prove that D’s gate‑policy MutationSpace (threshold × cooldown) is
properly bound in the repository, that a sweep executes end‑to‑end, and that the
observed metrics land in the common‑observable vocabulary.
"""

from __future__ import annotations

from experiments.catalog import (
    build_repository_catalog,
    repository_executors,
    repository_parameter_spaces,
)
from experiments.gated_movers.experiment import specs_by_path as gated_specs_by_path
from sim_alchemist.core.catalog import CompositionCatalog
from sim_alchemist.core.cross_composition_sweep import (
    CrossCompositionSweep,
    CrossCompositionSweepSpec,
)
from sim_alchemist.core.lineage import LineageStore
from sim_alchemist.core.sweep import ParameterSweep


def _d_catalog_row(catalog: CompositionCatalog):
    """Return the CatalogCandidate for the gated‑movers composition."""
    return next(c for c in catalog.executable() if c.template == "gated_movers")


# ------------------------------------------------------------------
# A. Parameter‑space metadata
# ------------------------------------------------------------------
def test_d_has_space() -> None:
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(build_repository_catalog())
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    assert d_binding.has_space is True
    assert d_binding.ref is not None
    assert d_binding.space is not None


def test_d_variant_count() -> None:
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(build_repository_catalog())
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    assert d_binding.space.variant_count == 4  # 2 × 2


def test_d_space_paths() -> None:
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(build_repository_catalog())
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    paths = {dim.path for dim in d_binding.space.dimensions}
    assert paths == {"config.gate_threshold", "config.gate_cooldown"}


def test_d_values_in_bounds() -> None:
    """Every value in the declared ParameterSweep lives inside its ParameterSpec bounds."""
    specs = gated_specs_by_path()
    dims = (
        ParameterSweep("config.gate_threshold", (0.25, 0.75)),
        ParameterSweep("config.gate_cooldown", (0, 8)),
    )
    for dim in dims:
        spec = specs[dim.path]
        for value in dim.values:
            assert spec.minimum <= value <= spec.maximum


# ------------------------------------------------------------------
# B. End‑to‑end sweep execution
# ------------------------------------------------------------------
def test_d_sweep_executes() -> None:
    """A D sweep runs through CrossCompositionSweep → SweepRunner → executor."""
    catalog = build_repository_catalog(generate_worlds=True)
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(catalog)
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    store = LineageStore(":memory:")
    spec = CrossCompositionSweepSpec(space_name="repo", bindings=(d_binding,))
    sweep = CrossCompositionSweep(
        catalog, repository_executors(), spaces, store,
        parameter_specs={
            "config.gate_threshold": gated_specs_by_path()["config.gate_threshold"],
            "config.gate_cooldown": gated_specs_by_path()["config.gate_cooldown"],
        },
    )
    result = sweep.run(spec)
    assert result.state == "executed"
    assert result.timing is not None
    # Baseline + 4 variants = 5 logical runs
    assert result.total_evaluations == 5


def test_d_baseline_and_variants_stamp_composition_id() -> None:
    """Every D run (baseline + variants) carries the same composition_id."""
    catalog = build_repository_catalog(generate_worlds=True)
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(catalog)
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    store = LineageStore(":memory:")
    spec = CrossCompositionSweepSpec(space_name="repo", bindings=(d_binding,))
    sweep = CrossCompositionSweep(
        catalog, repository_executors(), spaces, store,
        parameter_specs={
            "config.gate_threshold": gated_specs_by_path()["config.gate_threshold"],
            "config.gate_cooldown": gated_specs_by_path()["config.gate_cooldown"],
        },
    )
    result = sweep.run(spec)
    for b in result.bindings:
        assert b.composition_id == d_binding.composition_id
        # baseline run
        base = store.get_run(b.baseline_run_id)
        assert base is not None
        assert base.composition_id == b.composition_id
        # variants
        for vid in b.variant_run_ids:
            v = store.get_run(vid)
            assert v is not None
            assert v.composition_id == b.composition_id


def test_d_deterministic_repeat() -> None:
    """Re‑running the same D sweep gives identical deterministic IDs."""
    catalog = build_repository_catalog(generate_worlds=True)
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(catalog)
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    spec = CrossCompositionSweepSpec(space_name="repo", bindings=(d_binding,))

    store1 = LineageStore(":memory:")
    sweep1 = CrossCompositionSweep(
        catalog, repository_executors(), spaces, store1,
        parameter_specs={
            "config.gate_threshold": gated_specs_by_path()["config.gate_threshold"],
            "config.gate_cooldown": gated_specs_by_path()["config.gate_cooldown"],
        },
    )
    r1 = sweep1.run(spec)

    store2 = LineageStore(":memory:")
    sweep2 = CrossCompositionSweep(
        catalog, repository_executors(), spaces, store2,
        parameter_specs={
            "config.gate_threshold": gated_specs_by_path()["config.gate_threshold"],
            "config.gate_cooldown": gated_specs_by_path()["config.gate_cooldown"],
        },
    )
    r2 = sweep2.run(spec)

    assert r1.cross_split_sweep_id == r2.cross_split_sweep_id
    assert r1.total_evaluations == r2.total_evaluations


# ------------------------------------------------------------------
# C. Observables from D runs
# ------------------------------------------------------------------
def test_d_observables_contain_gate_metrics() -> None:
    """Aggregated D observations contain the gate‑policy metrics."""
    from sim_alchemist.core.cross_composition_behavior import aggregate_sweep_behavior

    catalog = build_repository_catalog(generate_worlds=True)
    spaces = repository_parameter_spaces()
    row = _d_catalog_row(catalog)
    d_binding = next(b for b in spaces.values() if b.composition_id == row.composition_id)
    store = LineageStore(":memory:")
    spec = CrossCompositionSweepSpec(space_name="repo", bindings=(d_binding,))
    sweep = CrossCompositionSweep(
        catalog, repository_executors(), spaces, store,
        parameter_specs={
            "config.gate_threshold": gated_specs_by_path()["config.gate_threshold"],
            "config.gate_cooldown": gated_specs_by_path()["config.gate_cooldown"],
        },
    )
    result = sweep.run(spec)
    agg = aggregate_sweep_behavior(result, store=store)
    # Find observations belonging to D
    d_obs = [o for o in agg.observations if o.composition_id == d_binding.composition_id]
    assert len(d_obs) == 5  # baseline + 4 variants
    names = set(agg.union_vocabulary)
    # Gate‑policy metrics must appear in the vocabulary
    assert "deposition_events" in names
    assert "deposition_suppression" in names
    assert "active_gates" in names
    assert "gate_switch_rate" in names


# ------------------------------------------------------------------
# D. A/B/C remain unchanged
# ------------------------------------------------------------------
def test_a_b_c_unchanged() -> None:
    """A, B have no space; C keeps its 27‑variant network space."""
    spaces = repository_parameter_spaces()
    catalog = build_repository_catalog(generate_worlds=True)
    with_space = [b for b in spaces.values() if b.has_space]
    # Exactly two compositions have a real space: C and D
    assert len(with_space) == 2
    # C's variant count stays 27
    c_binding = next(b for b in with_space if "components.network.config.loss" in {dim.path for dim in b.space.dimensions})
    assert c_binding.space.variant_count == 27
    # D's variant count is 4 (verified elsewhere)
    d_ids = {b.composition_id for b in with_space}
    assert len(d_ids) == 2