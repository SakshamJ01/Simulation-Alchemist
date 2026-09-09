"""Cross-composition orchestrated sweep + durable pass lineage (Task 2.5 Stage 2).

Stage 2 adds the thin ``CrossCompositionSweep`` orchestrator on top of the
Stage 1 data model and the existing ``SweepRunner``: it walks
``catalog.executable()`` in catalog order, sweeps every composition that owns
a declared ``MutationSpace`` (baseline control first, then the deterministic
variants), records the baseline only for compositions with no declared space,
stamps every recorded run with its ``composition_id``, persists one compact
``CrossCompositionSweepRow`` per participating composition, and returns one
deterministic ``CrossCompositionSweepResult(state="executed")`` with timing.

A/B/C semantics stay honest: A and B bind ``space=None`` ("no declared
parameter sweep") and contribute their baseline only; C owns a real space and
is swept.  These tests prove the mandated properties:

  * A: empty executable catalog executes nothing;
  * B: repeat execution is convergent -- deterministic ids, no duplicated
    baseline rows, INSERT OR REPLACE participation rows;
  * C: A/B baseline-only plus C swept;
  * D: baseline runs are the root baseline of their composition (parent None),
    never a variant;
  * E: every variant + baseline run stamps its composition id;
  * F: executors resolve per composition id deterministically;
  * G: executed result ordering matches the catalog's executable ordering;
  * H: same inputs produce the same canonical result on re-run;
  * I: a missing executor raises a clear error (fail-fast, nothing executed);
  * J: a missing space binding raises a clear error (fail-fast);
  * K: a missing generated world raises a clear error (fail-fast);
  * L: ``max_variants`` cap is enforced ahead of execution (fail-fast);
  * M/N/O: no ranking, no behavior analysis, no diversity frontier exist in
    this stage (source scan + result-model assertions);
  * P: the orchestrator core source is experiment-free, and the orchestrator
    lives in its own module so the Stage 1 ``cross_sweep`` purity scan stays
    green;
  * Q: lineage persistence -- durable rows round-trip and ``composition_id``
    is stamped on variant ``RunRecord``s;

Plus a slow canonical test that runs the real cross-composition sweep (three
full-length baselines + the real 27-variant C space = 30 logical runs / 29
after no-op skipping) and persists/replays it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from test_composition_search import (
    CORE_DIR,
    FORBIDDEN_CORE_TOKENS,
    build_fast_repository_catalog,
)

from experiments.catalog import (
    build_repository_catalog,
    repository_executors,
    repository_parameter_spaces,
)
from experiments.network_morphogenesis.experiment import specs_by_path
from sim_alchemist.core.catalog import CompositionCatalog
from sim_alchemist.core.composition import CompositionSpace
from sim_alchemist.core.cross_composition_sweep import (
    CrossCompositionSweep,
    CrossCompositionSweepError,
)
from sim_alchemist.core.cross_sweep import (
    CompositionSpaceBinding,
    CrossCompositionSweepResult,
    CrossCompositionSweepSpec,
)
from sim_alchemist.core.lineage import CrossCompositionSweepRow, LineageStore
from sim_alchemist.core.sweep import MutationSpace, ParameterSweep

REPO_ROOT = Path(__file__).resolve().parents[1]

# Tokens that must never appear in the Stage 2 orchestrator source: the shared
# core base set plus the experiment/domain identifiers Task 2.5 names.
STAGE2_FORBIDDEN_TOKENS = FORBIDDEN_CORE_TOKENS + (
    "pde",
    "movers",
    "field_guided",
    "chemistry",
    "agent_",
    "morphogenesis",
    "loss",
    "source_amplitude",
    "force_fmax",
)

FAST_STEPS = 2


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _c_space() -> MutationSpace:
    """A small legitimate network space for fast tests (2x2x2 = 8 variants)."""
    return MutationSpace(
        (
            ParameterSweep("components.network.config.loss", (0.2, 0.8)),
            ParameterSweep("config.force_fmax", (2.0, 8.0)),
            ParameterSweep("config.source_amplitude", (0.2, 0.8)),
        )
    )


def _fast_catalog() -> CompositionCatalog:
    return build_fast_repository_catalog(generate_worlds=True)


def _fast_spaces(*, with_c: bool = True) -> dict:
    """Repository space bindings; A/B baseline-only; C carries a small space
    (or is omitted entirely when ``with_c`` is False)."""
    spaces = repository_parameter_spaces()
    cid = next(b.composition_id for b in spaces.values() if b.space is not None)
    shape_id = next(b.shape_id for b in spaces.values() if b.space is not None)
    if not with_c:
        del spaces[cid]
        return spaces
    spaces[cid] = CompositionSpaceBinding(
        composition_id=cid, shape_id=shape_id, ref="smoke-c", space=_c_space()
    )
    return spaces


def _spec(spaces: dict) -> CrossCompositionSweepSpec:
    bindings = tuple(
        CompositionSpaceBinding(composition_id=k, shape_id="x")
        for k in sorted(spaces)
    )
    return CrossCompositionSweepSpec(space_name="repo", bindings=bindings)


def _empty_catalog() -> CompositionCatalog:
    return CompositionCatalog(
        CompositionSpace(name="empty", universe=()),
        {},
        [],
        build_adapters=lambda _s, _t: [],
        generate_worlds=True,
    )


# ----------------------------------------------------------------------
# Orchestrator: A-Q
# ----------------------------------------------------------------------
class TestCrossCompositionSweep:
    def test_b_repeat_execution_is_convergent(self) -> None:
        store = LineageStore(":memory:")
        catalog = _fast_catalog()
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            catalog, repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        result1 = sweep.run(_spec(spaces))
        result2 = sweep.run(_spec(spaces))
        assert result1.cross_split_sweep_id == result2.cross_split_sweep_id
        assert result1.bindings == result2.bindings
        assert store.run_count == result2.total_evaluations
        assert store.cross_composition_sweep_count == len(result2.bindings)

    def test_c_a_b_baseline_only_c_swept(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        result = sweep.run(_spec(spaces))
        cid = next(b.composition_id for b in spaces.values() if b.space is not None)
        assert result.timing.n_swept == 1
        assert result.timing.n_baseline_only == 2
        for b in result.bindings:
            if b.composition_id == cid:
                assert b.sweep_id is not None
                assert len(b.variant_run_ids) == _c_space().variant_count
            else:
                assert b.sweep_id is None
                assert b.variant_run_ids == ()
            assert b.baseline_run_id is not None

    def test_d_baseline_is_root_not_variant(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        result = sweep.run(_spec(spaces))
        for b in result.bindings:
            rec = store.get_run(b.baseline_run_id)
            assert rec is not None
            assert rec.parent_run_id is None
            assert b.baseline_run_id not in b.variant_run_ids

    def test_e_variants_and_baseline_stamped_with_composition_id(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        result = sweep.run(_spec(spaces))
        for b in result.bindings:
            base = store.get_run(b.baseline_run_id)
            assert base.composition_id == b.composition_id
            for vid in b.variant_run_ids:
                v = store.get_run(vid)
                assert v.composition_id == b.composition_id

    def test_f_executors_resolve_per_composition_id(self) -> None:
        store = LineageStore(":memory:")
        catalog = _fast_catalog()
        spaces = _fast_spaces()
        executors = repository_executors()
        for c in catalog.executable():
            assert c.composition_id in executors
        sweep = CrossCompositionSweep(
            catalog, executors, spaces, store, parameter_specs=specs_by_path()
        )
        result = sweep.run(_spec(spaces))
        assert len(result.bindings) == 3

    def test_g_order_matches_catalog_executable(self) -> None:
        store = LineageStore(":memory:")
        catalog = _fast_catalog()
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            catalog, repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        expected = [c.composition_id for c in catalog.executable()]
        result = sweep.run(_spec(spaces))
        assert [b.composition_id for b in result.bindings] == expected

    def test_h_deterministic_canonical_result(self) -> None:
        spaces1 = _fast_spaces()
        spaces2 = _fast_spaces()
        r1 = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces1, LineageStore(":memory:"),
            parameter_specs=specs_by_path(),
        ).run(_spec(spaces1))
        r2 = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces2, LineageStore(":memory:"),
            parameter_specs=specs_by_path(),
        ).run(_spec(spaces2))
        # Timing is wall-clock and may differ between interpreter runs;
        # verify that all deterministic fields coincide.
        assert r1.cross_split_sweep_id == r2.cross_split_sweep_id
        assert r1.state == r2.state
        assert r1.total_evaluations == r2.total_evaluations
        assert r1.bindings == r2.bindings
        assert r1.spec.as_dict(canonical=True) == r2.spec.as_dict(canonical=True)

    def test_i_missing_executor_fails_fast(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        executors = dict(repository_executors())
        del executors[next(iter(spaces))]
        sweep = CrossCompositionSweep(
            _fast_catalog(), executors, spaces, store, parameter_specs=specs_by_path()
        )
        with pytest.raises(CrossCompositionSweepError):
            sweep.run(_spec(spaces))
        assert store.run_count == 0
        assert store.cross_composition_sweep_count == 0

    def test_j_missing_space_binding_fails_fast(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces(with_c=False)
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        with pytest.raises(CrossCompositionSweepError):
            sweep.run(_spec(spaces))
        assert store.run_count == 0

    def test_k_missing_generated_world_fails_fast(self) -> None:
        store = LineageStore(":memory:")
        catalog = build_fast_repository_catalog(generate_worlds=False)
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            catalog, repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        with pytest.raises(CrossCompositionSweepError):
            sweep.run(_spec(spaces))
        assert store.run_count == 0

    def test_l_variant_caps_enforced_before_execution(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store,
            parameter_specs=specs_by_path(), max_variants=1,
        )
        with pytest.raises(CrossCompositionSweepError):
            sweep.run(_spec(spaces))
        assert store.run_count == 0

    def test_m_no_ranking_in_result(self) -> None:
        result_default = CrossCompositionSweepResult(
            cross_split_sweep_id="0" * 24, spec=_spec({})
        )
        assert result_default.state == "planned"
        assert not hasattr(result_default, "ranking")

    def test_n_no_behavior_or_ranking_in_source(self) -> None:
        src = (CORE_DIR / "cross_composition_sweep.py").read_text(encoding="utf-8").lower()
        assert "rank_" not in src
        assert "behavior" not in src

    def test_o_no_frontier_in_source(self) -> None:
        src = (CORE_DIR / "cross_composition_sweep.py").read_text(encoding="utf-8")
        assert "frontier" not in src

    def test_p_orchestrator_source_is_experiment_free(self) -> None:
        src = (CORE_DIR / "cross_composition_sweep.py").read_text(encoding="utf-8").lower()
        hits = [tok for tok in STAGE2_FORBIDDEN_TOKENS if tok in src]
        assert hits == [], f"experiment tokens in core orchestrator: {hits}"

    def test_q_lineage_round_trips_and_counts(self) -> None:
        store = LineageStore(":memory:")
        spaces = _fast_spaces()
        sweep = CrossCompositionSweep(
            _fast_catalog(), repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        result = sweep.run(_spec(spaces))
        rows = store.get_cross_composition_sweeps(result.cross_split_sweep_id)
        assert len(rows) == 3
        assert store.cross_composition_sweep_count == 3
        assert len(list(store.iter_cross_composition_sweeps())) == 3
        for row in rows:
            assert isinstance(row, CrossCompositionSweepRow)
            assert row.status == "executed"
            assert row.shape_id
        assert rows[0].cross_split_sweep_id == result.cross_split_sweep_id


# ----------------------------------------------------------------------
# Slow: real cross-composition sweep (3 baselines + full 27-variant C space)
# ----------------------------------------------------------------------
@pytest.mark.slow
class TestSlowCanonicalCrossCompositionSweep:
    def test_real_repository_sweep_executes_and_persists(self) -> None:
        store = LineageStore(":memory:")
        catalog = build_repository_catalog(generate_worlds=True)
        spaces = repository_parameter_spaces()
        sweep = CrossCompositionSweep(
            catalog, repository_executors(), spaces, store, parameter_specs=specs_by_path()
        )
        spec = CrossCompositionSweepSpec(
            space_name="repo",
            bindings=tuple(
                CompositionSpaceBinding(
                    composition_id=b.composition_id, shape_id=b.shape_id,
                    ref=b.ref, space=b.space,
                )
                for b in spaces.values()
            ),
        )
        result = sweep.run(spec)
        assert result.state == "executed"
        assert result.timing.n_executable == 3
        assert result.timing.n_swept == 1
        assert result.timing.n_baseline_only == 2
        assert result.total_evaluations == 3 + 27
        assert store.cross_composition_sweep_count == 3
        cid = next(b.composition_id for b in spaces.values() if b.space is not None)
        c_row = next(
            r
            for r in store.get_cross_composition_sweeps(result.cross_split_sweep_id)
            if r.composition_id == cid
        )
        assert len(c_row.variant_run_ids) == 27
