"""Cross-composition discovery orchestration (Task 2.4 Stage 2).

Stage 2 adds the thin ``CompositionSearcher`` orchestrator on top of the Stage
1 result layer: the searcher enumerates ``catalog.executable()`` in catalog
order, resolves each candidate's experiment-owned executor from the opaque
composition-id -> executor map (``repository_executors``), evaluates each one
exactly once through ``evaluate_composition_baseline``, and preserves the
deterministic evaluation order in a compact ``CompositionSearchResult``.

These tests prove the mandated properties A-P:

  * A: valid search configuration (``CompositionSearchSpec``);
  * B: empty executable catalog (zero evaluations, still a valid search);
  * C: one executable candidate;
  * D: all three repository compositions (A/B/C) are evaluated;
  * E: invalid candidates are skipped (never simulated);
  * F: executor lookup per composition id is deterministic;
  * G: result ordering matches catalog executable ordering;
  * H: same inputs produce the same discovery identity (budget-independent);
  * I: repeated searches produce identical canonical results (no duplicate
    logical roots);
  * J: a missing executor raises a clear error;
  * K: a candidate without a generated world raises a clear error;
  * L: ``CompositionEvaluation`` objects are preserved unchanged;
  * M/N/O: no ranking, no behavior analysis, no diversity frontier exists in
    this stage (source scan + result model assertions);
  * P: the core searcher source is experiment-free.

Plus one slow test that runs a real Stage 2 search over the canonical
repository catalog (three full-length baselines) and replays it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from test_composition_search import (
    CORE_DIR,
    FORBIDDEN_CORE_TOKENS,
    _fast_template,
    build_fast_repository_catalog,
)

from chemomech.coupling import build_morphogenesis_template
from experiments.catalog import (
    build_repository_adapters,
    build_repository_catalog,
    repository_bindings,
    repository_executors,
    repository_surfaces,
)
from experiments.field_guided_movers.coupling import (
    build_field_guided_movers_template,
)
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_template,
)
from sim_alchemist.core import (
    EXECUTABLE,
    CompositionCatalog,
    CompositionEvaluation,
    CompositionEvaluationError,
    CompositionSearcher,
    CompositionSearchError,
    CompositionSearchResult,
    CompositionSearchSpec,
    CompositionSpace,
    CouplingTemplateRegistry,
    InterestingnessProfile,
    LineageStore,
    composition_discovery_id_of,
    run_id_of,
    world_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Tokens that must never appear in the Stage 2 orchestrator source (the Stage 1
# base set plus the domain identifiers this task names explicitly).
STAGE2_FORBIDDEN_TOKENS = FORBIDDEN_CORE_TOKENS + (
    "pde",
    "movers",
    "field_guided",
    "chemistry",
    "agent_",
)


def _profile(*, name: str = "stage2") -> InterestingnessProfile:
    return InterestingnessProfile(name=name, description="", weights={"o:f": 1.0})


def _spec(*, seed: int = 0, evaluation_config: dict | None = None) -> CompositionSearchSpec:
    return CompositionSearchSpec(
        profile=_profile(), seed=seed, evaluation_config=evaluation_config
    )


def _fast_registry() -> CouplingTemplateRegistry:
    registry = CouplingTemplateRegistry()
    for build in (
        build_morphogenesis_template,
        build_field_guided_movers_template,
        build_network_morphogenesis_template,
    ):
        registry.register(_fast_template(build()))
    return registry


def _catalog(
    *,
    universe,
    min_size: int,
    max_size: int,
    generate_worlds: bool = True,
) -> CompositionCatalog:
    return CompositionCatalog(
        CompositionSpace(
            name="repository", universe=universe, min_size=min_size, max_size=max_size
        ),
        repository_surfaces(),
        _fast_registry(),
        build_adapters=build_repository_adapters,
        generate_worlds=generate_worlds,
    )


def _b_only_universe() -> tuple:
    """The two bindings Experiment B needs (one executable around them)."""
    return tuple(
        b
        for b in repository_bindings()
        if b.component == "py-pde" or (b.component == "pymunk" and b.variant == "movers")
    )


# ----------------------------------------------------------------------
# A. Valid search configuration
# ----------------------------------------------------------------------
class TestSearchConfiguration:
    def test_a_valid_spec(self) -> None:
        spec = _spec(seed=7, evaluation_config={"max_steps": 99})
        assert spec.seed == 7
        assert spec.as_dict() == {
            "profile": _profile().as_dict(),
            "seed": 7,
            "evaluation_config": {"max_steps": 99},
        }
        assert _spec() == _spec()  # value equality, deterministic

    def test_a_bad_seed_rejected(self) -> None:
        with pytest.raises(TypeError):
            CompositionSearchSpec(profile=_profile(), seed="0")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            CompositionSearchSpec(profile=_profile(), seed=True)  # type: ignore[arg-type]

    def test_a_profile_must_expose_as_dict(self) -> None:
        with pytest.raises(TypeError):
            CompositionSearchSpec(profile=object())

    def test_a_evaluation_config_must_be_mapping(self) -> None:
        with pytest.raises(TypeError):
            CompositionSearchSpec(
                profile=_profile(), evaluation_config=[1, 2]  # type: ignore[arg-type]
            )

    def test_a_evaluation_config_is_copied(self) -> None:
        config = {"max_steps": 2}
        spec = CompositionSearchSpec(profile=_profile(), evaluation_config=config)
        config["max_steps"] = 999
        assert spec.evaluation_config == {"max_steps": 2}


# ----------------------------------------------------------------------
# B. Empty executable catalog
# ----------------------------------------------------------------------
class TestEmptyCatalog:
    def test_b_zero_executables_still_searchable(self) -> None:
        catalog = _catalog(
            universe=repository_bindings(), min_size=4, max_size=4
        )
        assert not catalog.executable()
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, {}, store).search(_spec())
        assert isinstance(result, CompositionSearchResult)
        assert result.evaluations == ()
        assert result.composition_ids == ()
        assert result.timing.n_executable == 0
        assert result.timing.n_evaluated == 0
        assert len(result.discovery_id) == 24
        assert store.run_count == 0
        store.close()


# ----------------------------------------------------------------------
# C. One executable candidate
# ----------------------------------------------------------------------
class TestSingleExecutable:
    def test_c_one_candidate_evaluated(self) -> None:
        universe = _b_only_universe()
        assert len(universe) == 2
        catalog = _catalog(universe=universe, min_size=2, max_size=2)
        executable = catalog.executable()
        assert len(executable) == 1
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        assert len(result.evaluations) == 1
        assert result.timing.n_executable == 1
        assert result.timing.n_evaluated == 1
        assert result.composition_ids == (executable[0].composition_id,)
        assert store.run_count == 1
        store.close()


# ----------------------------------------------------------------------
# D. All three repository compositions evaluated
# ----------------------------------------------------------------------
class TestThreeExecutables:
    def test_d_all_abc_evaluated(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        assert len(catalog.executable()) == 3
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        assert len(result.evaluations) == 3
        assert set(result.composition_ids) == {
            c.composition_id for c in catalog.executable()
        }
        assert store.run_count == 3
        store.close()

    def test_d3_each_is_a_root_baseline(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        for ev in result.evaluations:
            record = store.get_run(ev.run_id)
            assert record is not None
            assert record.parent_run_id is None
            assert record.composition_id == ev.composition_id
        store.close()


# ----------------------------------------------------------------------
# E. Invalid candidates are skipped
# ----------------------------------------------------------------------
class TestInvalidSkipped:
    def test_e_never_simulates_invalid(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        assert len(catalog.invalid()) == 20
        executed_world_ids: list[str] = []

        def _counting(executor):
            def _wrapped(world):
                executed_world_ids.append(world.id)
                return executor(world)

            return _wrapped

        executors = {
            cid: _counting(fn) for cid, fn in repository_executors().items()
        }
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, executors, store).search(_spec())
        assert len(result.evaluations) == 3
        executable_world_ids = {
            c.generated_world.id for c in catalog.executable() if c.generated_world
        }
        assert set(executed_world_ids) == executable_world_ids
        assert len(executed_world_ids) == 3  # the 20 invalid shapes were never run
        assert store.run_count == 3
        store.close()


# ----------------------------------------------------------------------
# F. Executor lookup is deterministic
# ----------------------------------------------------------------------
class TestExecutorLookup:
    def test_f_resolution_by_composition_id(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        executors = repository_executors()
        for candidate in catalog.executable():
            assert candidate.composition_id in executors

    def test_f_each_executor_used_exactly_once_per_search(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        base = repository_executors()
        calls = {cid: 0 for cid in base}

        def _counting(executor, cid):
            def _wrapped(world):
                calls[cid] += 1
                return executor(world)

            return _wrapped

        wrapped = {cid: _counting(fn, cid) for cid, fn in base.items()}
        store = LineageStore(":memory:")
        CompositionSearcher(catalog, wrapped, store).search(_spec())
        assert calls == {cid: 1 for cid in base}
        assert store.run_count == 3
        store.close()


# ----------------------------------------------------------------------
# G. Result ordering matches catalog executable ordering
# ----------------------------------------------------------------------
class TestOrdering:
    def test_g_catalog_order_preserved(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        expected = tuple(c.composition_id for c in catalog.executable())
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        assert result.composition_ids == expected
        assert [ev.shape_id for ev in result.evaluations] == [
            c.shape_id for c in catalog.executable()
        ]
        store.close()


# ----------------------------------------------------------------------
# H. Same inputs -> same discovery identity (reused from Stage 1)
# ----------------------------------------------------------------------
class TestDiscoveryIdentity:
    def test_h_same_inputs_same_id(self) -> None:
        c1 = build_fast_repository_catalog(generate_worlds=True)
        c2 = build_fast_repository_catalog(generate_worlds=True)
        r1 = CompositionSearcher(c1, repository_executors(), LineageStore(":memory:")).search(_spec())
        r2 = CompositionSearcher(c2, repository_executors(), LineageStore(":memory:")).search(_spec())
        assert r1.discovery_id == r2.discovery_id
        assert len(r1.discovery_id) == 24

    def test_h_identity_matches_stage1_function(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        result = CompositionSearcher(catalog, repository_executors(), LineageStore(":memory:")).search(_spec())
        assert result.discovery_id == composition_discovery_id_of(
            catalog, _profile(), seed=0, evaluation_config=None
        )

    def test_h_identity_is_budget_independent(self) -> None:
        fast = build_fast_repository_catalog(generate_worlds=True)
        canonical = build_repository_catalog()
        result = CompositionSearcher(fast, repository_executors(), LineageStore(":memory:")).search(_spec())
        assert result.discovery_id == composition_discovery_id_of(
            canonical, _profile(), seed=0, evaluation_config=None
        )

    def test_h_seed_and_config_change_identity(self) -> None:
        catalog = build_fast_repository_catalog()
        base = composition_discovery_id_of(catalog, _profile(), seed=0)
        assert composition_discovery_id_of(catalog, _profile(), seed=1) != base
        assert (
            composition_discovery_id_of(
                catalog, _profile(), seed=0, evaluation_config={"max_steps": 3}
            )
            != base
        )


# ----------------------------------------------------------------------
# I. Repeated searches are deterministic (replay, no duplicate roots)
# ----------------------------------------------------------------------
class TestDeterministicReplay:
    def test_i_same_store_replay(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        searcher = CompositionSearcher(catalog, repository_executors(), store)
        first = searcher.search(_spec())
        second = searcher.search(_spec())
        assert first.discovery_id == second.discovery_id
        assert first.as_dict(canonical=True) == second.as_dict(canonical=True)
        assert first.composition_ids == second.composition_ids
        assert [ev.world_hash for ev in first.evaluations] == [
            ev.world_hash for ev in second.evaluations
        ]
        assert [ev.run_id for ev in first.evaluations] == [
            ev.run_id for ev in second.evaluations
        ]
        assert [dict(ev.metrics) for ev in first.evaluations] == [
            dict(ev.metrics) for ev in second.evaluations
        ]
        assert store.run_count == 3  # re-evaluation replaces, never duplicates roots
        store.close()

    def test_i_fresh_store_replay(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)

        def _run() -> dict:
            store = LineageStore(":memory:")
            result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
            store.close()
            return result.as_dict(canonical=True)

        assert _run() == _run()


# ----------------------------------------------------------------------
# J/K. Clear errors: missing executor, missing generated world
# ----------------------------------------------------------------------
class TestClearErrors:
    def test_j_missing_executor(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        searcher = CompositionSearcher(catalog, {}, store)
        with pytest.raises(CompositionSearchError) as excinfo:
            searcher.search(_spec())
        first = catalog.executable()[0]
        assert excinfo.value.args[0].startswith("no executor registered for composition")
        assert first.composition_id in excinfo.value.args[0]
        assert store.run_count == 0
        store.close()

    def test_k_missing_generated_world(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=False)
        assert catalog.executable()[0].generated_world is None
        store = LineageStore(":memory:")
        searcher = CompositionSearcher(catalog, repository_executors(), store)
        with pytest.raises(CompositionEvaluationError):
            searcher.search(_spec())
        assert store.run_count == 0
        store.close()


# ----------------------------------------------------------------------
# L. CompositionEvaluation objects are preserved unchanged
# ----------------------------------------------------------------------
class TestEvaluationPreserved:
    def test_l_fields_preserved_unchanged(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        by_candidate = {c.composition_id: c for c in catalog.executable()}
        for ev in result.evaluations:
            assert isinstance(ev, CompositionEvaluation)
            candidate = by_candidate[ev.composition_id]
            world = candidate.generated_world
            assert world is not None
            assert ev.composition_id == candidate.composition_id
            assert ev.shape_id == candidate.shape_id
            assert ev.world_hash == world_hash(world)
            assert ev.run_id == run_id_of(world)
            assert ev.world_id == world.id
            assert ev.status == EXECUTABLE
            assert ev.seed == world.seed
            record = store.get_run(ev.run_id)
            assert record is not None
            assert dict(ev.metrics) == dict(record.metrics)


# ----------------------------------------------------------------------
# M/N/O/P. No ranking, no behavior analysis, no frontier; core purity
# ----------------------------------------------------------------------
class TestNoOverreach:
    NOGO_IDENTIFIERS = (
        "rank_by_profile",
        "select_diverse_frontier",
        "compute_frontier_diagnostics",
        "BehaviorAnalyzer",
        "BehaviorFeatures",
        "ObservableSeries",
        "behavior_vector",
        "InterestingnessProfile",
        "score",
        "final_ranking",
    )

    def test_mn_sources_have_no_ranking_or_analysis_api(self) -> None:
        source = (CORE_DIR / "composition_search.py").read_text(encoding="utf-8")
        hits = [ident for ident in self.NOGO_IDENTIFIERS if ident in source]
        assert not hits, f"Stage 2 source references ranking/analysis API: {hits}"

    def test_mn_result_model_exposes_no_scores_or_ranks(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=True)
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
        assert not hasattr(result, "final_ranking")
        canonical = result.as_dict(canonical=True)
        for ev in canonical["evaluations"]:
            assert "score" not in ev
            assert "rank" not in ev
        store.close()

    def test_p_core_source_is_experiment_free(self) -> None:
        source = (CORE_DIR / "composition_search.py").read_text(encoding="utf-8").lower()
        hits = [tok for tok in STAGE2_FORBIDDEN_TOKENS if tok in source]
        assert not hits, f"core/composition_search.py contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# Real search over the canonical repository catalog (full-length baselines)
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_slow_real_search_over_repository_catalog() -> None:
    catalog = build_repository_catalog(generate_worlds=True)
    assert len(catalog.executable()) == 3
    store = LineageStore(":memory:")
    searcher = CompositionSearcher(catalog, repository_executors(), store)
    result = searcher.search(_spec())
    assert len(result.evaluations) == 3
    assert result.composition_ids == tuple(c.composition_id for c in catalog.executable())
    for ev in result.evaluations:
        assert ev.status == EXECUTABLE
        assert ev.metrics
        record = store.get_run(ev.run_id)
        assert record is not None
        assert record.parent_run_id is None
        assert record.composition_id == ev.composition_id
    assert store.run_count == 3

    replay = searcher.search(_spec())
    assert replay.discovery_id == result.discovery_id
    assert replay.as_dict(canonical=True) == result.as_dict(canonical=True)
    assert replay.composition_ids == result.composition_ids
    assert store.run_count == 3
    store.close()