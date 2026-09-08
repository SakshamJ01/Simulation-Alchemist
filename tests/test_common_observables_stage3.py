"""Task 2.4 Stage 3: common cross-composition observables.

Stage 3 sits between the Stage 2 orchestration pass and any later
summary/selection layer.  After ``CompositionSearcher.search`` evaluates
every ``EXECUTABLE`` composition once, the result is reduced -- in the same
deterministic catalog order -- to one ``CommonObservableSet`` per composition:
the composition's lineage identity plus one ``CommonObservable`` per
recognized metric name, with ``available=False`` / ``value=None`` where a
composition does not produce that name (missing stays explicit, never
imputed).  The horizon (``max_steps`` / ``macro_timestep``) is captured from
the already-generated ``WorldDefinition``.

The mandated properties proven here:

  * A: extraction from real evaluation snapshots (union vocabulary, values,
    availability vs composition-specific names);
  * B: captured horizon matches the generated world (and is explicit None
    when no world is supplied -- never guessed);
  * C: determinism and replay (identical sets across runs and fresh stores);
  * D: lineage is untouched (no new runs, no observable/discovery tables,
    run-record parity);
  * E: one observable set per evaluated composition, aligned in catalog
    order, with ``observable_set()`` lookup;
  * F: world immutability (the generated world is never mutated);
  * G: no ranking surfaces anywhere (result model + source scans);
  * H: no behavior-analysis API and no visualization leaks into this layer;
  * I: canonical serialization is stable and carries only deterministic data
    (no timing, no ephemeral values; values verbatim);
  * J: Stage 2 result-model and timing contracts remain intact;
  * K: timing is split (evaluation vs extraction vs whole pass);
  * L: store idempotency -- a repeated search leaves ``run_count`` unchanged
    and produces identical observable sets;
  * M: empty and invalid inputs reduce to empty deterministically or fail
    loudly with typed errors.

Plus one slow test over the canonical full-length repository catalog.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

import pytest
from test_composition_search import (
    CORE_DIR,
    FORBIDDEN_CORE_TOKENS,
    build_fast_repository_catalog,
)
from test_composition_search_stage2 import (
    STAGE2_FORBIDDEN_TOKENS,
    _fast_registry,
    _spec,
)

from experiments.catalog import (
    build_repository_adapters,
    build_repository_catalog,
    repository_bindings,
    repository_executors,
    repository_surfaces,
)
from sim_alchemist.core import (
    EXECUTABLE,
    CommonObservable,
    CommonObservableError,
    CommonObservableSet,
    CompositionCatalog,
    CompositionEvaluation,
    CompositionSearcher,
    CompositionSearchResult,
    CompositionSearchTiming,
    CompositionSpace,
    LineageStore,
    common_observable_names,
    extract_common_observables,
)

# Identifiers that must never appear in this stage's core sources (Stage 2
# vocabulary kept verbatim).
NOGO_IDENTIFIERS = (
    "rank_by_profile",
    "select_diverse_frontier",
    "compute_frontier_diagnostics",
    "BehaviorAnalyzer",
    "BehaviorFeatures",
    "ObservableSeries",
    "InterestingnessProfile",
    "behavior_vector",
    "score",
    "final_ranking",
)

VISUALIZATION_TOKENS = ("matplotlib", "plot", "chart", "dashboard")


@dataclass
class _SearchFixture:
    catalog: CompositionCatalog
    searcher: CompositionSearcher
    result: CompositionSearchResult
    store: LineageStore


@pytest.fixture(scope="module")
def search_fixture():
    catalog = build_fast_repository_catalog(generate_worlds=True)
    store = LineageStore(":memory:")
    searcher = CompositionSearcher(catalog, repository_executors(), store)
    result = searcher.search(_spec())
    fixture = _SearchFixture(catalog=catalog, searcher=searcher, result=result, store=store)
    yield fixture
    store.close()


# ----------------------------------------------------------------------
# A. Extraction from real evaluation snapshots
# ----------------------------------------------------------------------
class TestExtraction:
    def test_a_union_vocabulary_is_sorted_and_shared(self, search_fixture: _SearchFixture) -> None:
        common = common_observable_names(search_fixture.result.evaluations)
        assert common == tuple(sorted(common))
        assert common == tuple(sorted(common_observable_names(search_fixture.result.evaluations)))
        assert len(common) == 16  # the deterministic A/B/C union
        assert common_observable_names([]) == ()
        for name in ("final_field_mean", "final_field_std", "field_entropy"):
            assert name in common  # genuinely common across all three

    def test_a_each_set_covers_the_sorted_vocabulary(self, search_fixture: _SearchFixture) -> None:
        common = common_observable_names(search_fixture.result.evaluations)
        for observable_set in search_fixture.result.observable_sets:
            assert observable_set.names == common
            assert observable_set.names == tuple(sorted(observable_set.names))
            assert set(observable_set.available_names) | set(observable_set.missing_names) == set(common)
            assert set(observable_set.available_names).isdisjoint(observable_set.missing_names)

    def test_a_availability_matches_composition_specificity(self, search_fixture: _SearchFixture) -> None:
        by_available: dict[tuple[str, ...], CommonObservableSet] = {}
        for observable_set in search_fixture.result.observable_sets:
            by_available[tuple(sorted(observable_set.available_names))] = observable_set

        a_keys = tuple(sorted(("final_field_mean", "final_field_std", "field_entropy",
                               "wall_count", "wall_movement", "dissolved_total",
                               "mean_wall_speed", "mean_force")))
        b_keys = tuple(sorted(("final_field_mean", "final_field_std", "field_entropy",
                               "n_movers", "total_displacement", "mean_speed",
                               "mean_force", "mean_gradient")))
        c_keys = tuple(sorted(("final_field_mean", "final_field_std", "field_entropy",
                               "wall_count", "wall_movement", "network_load_mean",
                               "network_load_max", "n_sources", "growth_edges")))
        a = by_available[a_keys]
        b = by_available[b_keys]
        c = by_available[c_keys]

        # a composition-specific name is real on its composition and explicit
        # None (never imputed) on the others.
        a_ev = search_fixture.result.evaluation(a.composition_id)
        assert a_ev is not None
        a_dissolved = a.observable("dissolved_total")
        b_dissolved = b.observable("dissolved_total")
        b_movers = b.observable("n_movers")
        c_movers = c.observable("n_movers")
        c_growth = c.observable("growth_edges")
        a_growth = a.observable("growth_edges")
        a_movers = a.observable("n_movers")
        assert a_dissolved is not None
        assert b_dissolved is not None
        assert b_movers is not None
        assert c_movers is not None
        assert c_growth is not None
        assert a_growth is not None
        assert a_movers is not None
        assert a_dissolved.available
        assert a_dissolved.value == a_ev.metrics["dissolved_total"]
        assert b_dissolved.available is False
        assert b_dissolved.value is None
        assert b_movers.available
        assert c_movers.available is False
        assert c_growth.available
        assert a_growth.available is False
        assert a_movers.available is False

    def test_a_extraction_matches_the_search_time_reduction(self, search_fixture: _SearchFixture) -> None:
        common = common_observable_names(search_fixture.result.evaluations)
        by_id = {c.composition_id: c for c in search_fixture.catalog.executable()}
        for observable_set in search_fixture.result.observable_sets:
            world = by_id[observable_set.composition_id].generated_world
            evaluation = search_fixture.result.evaluation(observable_set.composition_id)
            assert evaluation is not None
            assert extract_common_observables(evaluation, common, world=world) == observable_set


# ----------------------------------------------------------------------
# B. Captured horizon
# ----------------------------------------------------------------------
class TestCapturedHorizon:
    def test_b_horizon_matches_generated_world(self, search_fixture: _SearchFixture) -> None:
        by_id = {c.composition_id: c for c in search_fixture.catalog.executable()}
        for observable_set in search_fixture.result.observable_sets:
            world = by_id[observable_set.composition_id].generated_world
            assert world is not None
            assert observable_set.max_steps == world.max_steps
            assert observable_set.macro_timestep == world.macro_timestep

    def test_b_without_world_horizon_is_explicit_none(self, search_fixture: _SearchFixture) -> None:
        evaluation = search_fixture.result.evaluations[0]
        observable_set = extract_common_observables(evaluation, ("final_field_mean",))
        assert observable_set.max_steps is None
        assert observable_set.macro_timestep is None


# ----------------------------------------------------------------------
# C. Determinism and replay
# ----------------------------------------------------------------------
class TestDeterminism:
    def test_c_same_store_replay(self, search_fixture: _SearchFixture) -> None:
        before = search_fixture.result.as_dict(canonical=True)
        replay = search_fixture.searcher.search(_spec())
        assert replay.discovery_id == search_fixture.result.discovery_id
        assert replay.as_dict(canonical=True) == before
        assert replay.observable_sets == search_fixture.result.observable_sets
        assert search_fixture.store.run_count == 3

    def test_c_fresh_store_bitwise_exact(self) -> None:
        def _run() -> dict:
            catalog = build_fast_repository_catalog(generate_worlds=True)
            store = LineageStore(":memory:")
            result = CompositionSearcher(catalog, repository_executors(), store).search(_spec())
            store.close()
            return result.as_dict(canonical=True)

        assert _run() == _run()


# ----------------------------------------------------------------------
# D. Lineage is untouched
# ----------------------------------------------------------------------
class TestLineagePreserved:
    def test_d_no_new_runs_and_no_observable_tables(self, search_fixture: _SearchFixture) -> None:
        assert search_fixture.store.run_count == 3
        tables = [
            row[0]
            for row in search_fixture.store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        assert "composition_discoveries" not in tables
        assert not any("observable" in t for t in tables)

    def test_d_observable_sets_trace_to_recorded_runs(self, search_fixture: _SearchFixture) -> None:
        for observable_set in search_fixture.result.observable_sets:
            record = search_fixture.store.get_run(observable_set.run_id)
            assert record is not None
            assert record.composition_id == observable_set.composition_id
            assert record.world_hash == observable_set.world_hash
            assert record.seed == observable_set.seed


# ----------------------------------------------------------------------
# E. One set per evaluation, aligned in catalog order
# ----------------------------------------------------------------------
class TestOneSetPerEvaluation:
    def test_e_aligned_with_evaluations(self, search_fixture: _SearchFixture) -> None:
        evaluations = search_fixture.result.evaluations
        observable_sets = search_fixture.result.observable_sets
        assert len(observable_sets) == len(evaluations) == 3
        assert [s.composition_id for s in observable_sets] == [
            e.composition_id for e in evaluations
        ]
        assert [s.shape_id for s in observable_sets] == [e.shape_id for e in evaluations]
        assert [s.run_id for s in observable_sets] == [e.run_id for e in evaluations]
        assert [s.status for s in observable_sets] == [EXECUTABLE] * 3

    def test_e_observable_set_lookup(self, search_fixture: _SearchFixture) -> None:
        first = search_fixture.result.evaluations[0]
        assert search_fixture.result.observable_set(first.composition_id) is search_fixture.result.observable_sets[0]
        assert search_fixture.result.observable_set("no-such-composition") is None


# ----------------------------------------------------------------------
# F. World immutability
# ----------------------------------------------------------------------
class TestNoWorldMutation:
    def test_f_world_is_never_mutated(self, search_fixture: _SearchFixture) -> None:
        candidate = search_fixture.catalog.executable()[0]
        assert candidate.composition_id is not None
        world = candidate.generated_world
        assert world is not None
        before = world.as_dict()
        evaluation = search_fixture.result.evaluation(candidate.composition_id)
        assert evaluation is not None
        common = common_observable_names(search_fixture.result.evaluations)
        observable_set = extract_common_observables(evaluation, common, world=world)
        assert observable_set.composition_id == candidate.composition_id
        assert world.as_dict() == before


# ----------------------------------------------------------------------
# G/H. No ranking, no behavior/analysis, no visualization
# ----------------------------------------------------------------------
class TestNoOverreach:
    def test_g_result_model_has_no_ranking(self, search_fixture: _SearchFixture) -> None:
        assert not hasattr(search_fixture.result, "final_ranking")
        blob = json.dumps(search_fixture.result.as_dict(canonical=True))
        assert "final_ranking" not in blob
        for item in search_fixture.result.as_dict(canonical=True)["observable_sets"]:
            assert "score" not in item
            assert "rank" not in item

    def test_h_observables_module_is_clean(self) -> None:
        source = (CORE_DIR / "observables.py").read_text(encoding="utf-8")
        lowered = source.lower()
        tokens = FORBIDDEN_CORE_TOKENS + STAGE2_FORBIDDEN_TOKENS
        hits = [tok for tok in tokens if tok in lowered]
        assert not hits, f"core/observables.py contains experiment identifiers: {hits}"
        id_hits = [ident for ident in NOGO_IDENTIFIERS if ident in source]
        assert not id_hits, f"core/observables.py references ranking/analysis API: {id_hits}"
        viz_hits = [tok for tok in VISUALIZATION_TOKENS if tok in lowered]
        assert not viz_hits, f"core/observables.py contains visualization identifiers: {viz_hits}"

    def test_h_composition_search_still_clean(self) -> None:
        source = (CORE_DIR / "composition_search.py").read_text(encoding="utf-8")
        lowered = source.lower()
        tokens = FORBIDDEN_CORE_TOKENS + STAGE2_FORBIDDEN_TOKENS
        hits = [tok for tok in tokens if tok in lowered]
        assert not hits, f"core/composition_search.py contains experiment identifiers: {hits}"
        id_hits = [ident for ident in NOGO_IDENTIFIERS if ident in source]
        assert not id_hits, f"core/composition_search.py references ranking/analysis API: {id_hits}"
        viz_hits = [tok for tok in VISUALIZATION_TOKENS if tok in lowered]
        assert not viz_hits, f"core/composition_search.py contains visualization identifiers: {viz_hits}"


# ----------------------------------------------------------------------
# I. Canonical serialization
# ----------------------------------------------------------------------
class TestCanonicalSerializationStability:
    def test_i_canonical_form_is_stable_and_clean(self, search_fixture: _SearchFixture) -> None:
        canonical = search_fixture.result.as_dict(canonical=True)
        assert "timing" not in canonical
        assert "observation_seconds" not in json.dumps(canonical)
        assert "evaluation_seconds" not in json.dumps(canonical)
        assert "observable_sets" in canonical
        payload = json.dumps(canonical, sort_keys=True, allow_nan=False)
        assert json.dumps(
            search_fixture.result.as_dict(canonical=True), sort_keys=True, allow_nan=False
        ) == payload
        for item in canonical["observable_sets"]:
            assert set(item) == {
                "composition_id",
                "shape_id",
                "world_hash",
                "run_id",
                "world_id",
                "status",
                "seed",
                "max_steps",
                "macro_timestep",
                "observables",
            }
            for row in item["observables"]:
                assert set(row) == {"name", "value", "available"}
                assert (row["value"] is None) == (not row["available"])

    def test_i_values_are_verbatim_floats(self, search_fixture: _SearchFixture) -> None:
        for evaluation in search_fixture.result.evaluations:
            observable_set = search_fixture.result.observable_set(evaluation.composition_id)
            assert observable_set is not None
            for name, value in evaluation.metrics.items():
                row = observable_set.observable(name)
                assert row is not None
                assert row.available
                assert row.value == value
                assert isinstance(row.value, float)


# ----------------------------------------------------------------------
# J. Stage 2 contract compatibility
# ----------------------------------------------------------------------
class TestStage2Compatibility:
    def test_j_stage2_fields_and_lookup_intact(self, search_fixture: _SearchFixture) -> None:
        result = search_fixture.result
        assert isinstance(result, CompositionSearchResult)
        assert len(result.discovery_id) == 24
        assert result.evaluation(result.composition_ids[0]) is result.evaluations[0]
        assert result.timing.n_executable == result.timing.n_evaluated == 3

    def test_j_stage2_style_construction_without_sets_is_valid(self) -> None:
        timing = CompositionSearchTiming(
            n_executable=0,
            n_evaluated=0,
            evaluation_seconds=0.0,
            observation_seconds=0.0,
            total_seconds=0.0,
            mean_seconds=0.0,
        )
        legacy = CompositionSearchResult(discovery_id="d", spec=_spec(), evaluations=(), timing=timing)
        assert legacy.observable_sets == ()
        assert legacy.as_dict(canonical=True) == {
            "discovery_id": "d",
            "spec": _spec().as_dict(),
            "evaluations": [],
            "observable_sets": [],
        }


# ----------------------------------------------------------------------
# K. Timing split
# ----------------------------------------------------------------------
class TestTimingSplit:
    def test_k_phases_and_totals(self, search_fixture: _SearchFixture) -> None:
        timing = search_fixture.result.timing
        assert timing.n_executable == 3
        assert timing.n_evaluated == 3
        assert timing.evaluation_seconds > 0
        assert timing.observation_seconds >= 0
        assert timing.total_seconds == pytest.approx(
            timing.evaluation_seconds + timing.observation_seconds, abs=1e-3
        )
        assert timing.mean_seconds == pytest.approx(timing.total_seconds / 3)
        assert set(timing.as_dict()) == {
            "n_executable",
            "n_evaluated",
            "evaluation_seconds",
            "observation_seconds",
            "total_seconds",
            "mean_seconds",
        }

    def test_k_zero_evaluation_is_division_safe(self) -> None:
        timing = CompositionSearchTiming(
            n_executable=0,
            n_evaluated=0,
            evaluation_seconds=0.0,
            observation_seconds=0.0,
            total_seconds=0.0,
            mean_seconds=0.0,
        )
        assert timing.mean_seconds == 0.0


# ----------------------------------------------------------------------
# L. Store idempotency
# ----------------------------------------------------------------------
class TestIdempotency:
    def test_l_repeated_search_keeps_run_count(self, search_fixture: _SearchFixture) -> None:
        before = search_fixture.result.as_dict(canonical=True)
        search_fixture.searcher.search(_spec())
        search_fixture.searcher.search(_spec())
        assert search_fixture.store.run_count == 3
        assert search_fixture.result.as_dict(canonical=True) == before


# ----------------------------------------------------------------------
# M. Empty and invalid inputs
# ----------------------------------------------------------------------
class TestEmptyAndInvalid:
    def test_m_empty_pool(self) -> None:
        assert common_observable_names(()) == ()
        with pytest.raises(TypeError):
            common_observable_names(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            common_observable_names(["not-an-evaluation"])  # type: ignore[list-item]

    def test_m_empty_catalog_yields_no_sets(self) -> None:
        catalog = CompositionCatalog(
            CompositionSpace(
                name="repository",
                universe=repository_bindings(),
                min_size=4,
                max_size=4,
            ),
            repository_surfaces(),
            _fast_registry(),
            build_adapters=build_repository_adapters,
            generate_worlds=True,
        )
        assert not catalog.executable()
        store = LineageStore(":memory:")
        result = CompositionSearcher(catalog, {}, store).search(_spec())
        assert result.observable_sets == ()
        assert result.as_dict(canonical=True)["observable_sets"] == []
        store.close()

    def test_m_bad_common_names_rejected(self, search_fixture: _SearchFixture) -> None:
        evaluation = search_fixture.result.evaluations[0]
        with pytest.raises(TypeError):
            extract_common_observables(evaluation, "final_field_mean")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            extract_common_observables(evaluation, [1, 2])  # type: ignore[list-item]

    def test_m_structural_validation(self, search_fixture: _SearchFixture) -> None:
        with pytest.raises(TypeError):
            extract_common_observables(object(), ())  # type: ignore[arg-type]
        bad_metrics = CompositionEvaluation(
            composition_id="c",
            shape_id="s",
            world_hash="h",
            run_id="r",
            world_id="w",
            status=EXECUTABLE,
            seed=0,
            metrics={"x": "not-a-number"},  # type: ignore[arg-type]
        )
        with pytest.raises(TypeError):
            common_observable_names([bad_metrics])
        with pytest.raises(TypeError):
            extract_common_observables(bad_metrics, ("x",))

    def test_m_world_mismatch_rejected(self, search_fixture: _SearchFixture) -> None:
        candidate = search_fixture.catalog.executable()[0]
        assert candidate.composition_id is not None
        world = candidate.generated_world
        assert world is not None
        evaluation = search_fixture.result.evaluation(candidate.composition_id)
        assert evaluation is not None
        common = ("final_field_mean",)

        wrong_id = dataclasses.replace(world, id="wrong")
        with pytest.raises(CommonObservableError):
            extract_common_observables(evaluation, common, world=wrong_id)

        reseeded = dataclasses.replace(world, seed=999)  # same id, different content
        with pytest.raises(CommonObservableError):
            extract_common_observables(evaluation, common, world=reseeded)

    def test_m_set_guards(self) -> None:
        with pytest.raises(ValueError):
            CommonObservable(name="x", value=None, available=True)
        with pytest.raises(ValueError):
            CommonObservable(name="x", value=1.0, available=False)
        with pytest.raises(ValueError):
            CommonObservable(name="", value=1.0, available=True)

        unsorted = (
            CommonObservable(name="b", value=1.0, available=True),
            CommonObservable(name="a", value=1.0, available=True),
        )
        duplicated = (
            CommonObservable(name="a", value=1.0, available=True),
            CommonObservable(name="a", value=2.0, available=True),
        )
        for observables in (unsorted, duplicated):
            with pytest.raises(ValueError):
                CommonObservableSet(
                    composition_id="c",
                    shape_id="s",
                    world_hash="h",
                    run_id="r",
                    world_id="w",
                    status=EXECUTABLE,
                    seed=0,
                    max_steps=None,
                    macro_timestep=None,
                    observables=observables,
                )

    def test_m_as_dict_round_trip(self) -> None:
        observable = CommonObservable(name="m", value=1.5, available=True)
        observable_set = CommonObservableSet(
            composition_id="c",
            shape_id="s",
            world_hash="h",
            run_id="r",
            world_id="w",
            status=EXECUTABLE,
            seed=0,
            max_steps=2,
            macro_timestep=0.2,
            observables=(observable,),
        )
        assert CommonObservable(**observable.as_dict()) == observable
        rebuilt = CommonObservableSet(**observable_set.as_dict())
        assert rebuilt == observable_set


# ----------------------------------------------------------------------
# Slow: real Stage 3 search over the canonical repository catalog
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_slow_real_search_over_repository_catalog() -> None:
    catalog = build_repository_catalog(generate_worlds=True)
    assert len(catalog.executable()) == 3
    store = LineageStore(":memory:")
    searcher = CompositionSearcher(catalog, repository_executors(), store)
    result = searcher.search(_spec())

    assert len(result.observable_sets) == 3
    by_id = {c.composition_id: c for c in catalog.executable()}
    common = common_observable_names(result.evaluations)
    assert len(common) == 16
    for observable_set in result.observable_sets:
        world = by_id[observable_set.composition_id].generated_world
        assert world is not None
        assert observable_set.names == common
        assert observable_set.max_steps == world.max_steps == 160
        assert observable_set.macro_timestep == world.macro_timestep == 0.2
        record = store.get_run(observable_set.run_id)
        assert record is not None
        assert record.parent_run_id is None
        assert record.composition_id == observable_set.composition_id

    timing = result.timing
    assert timing.n_executable == timing.n_evaluated == 3
    assert timing.evaluation_seconds > 0
    assert timing.observation_seconds > 0
    assert timing.total_seconds > timing.evaluation_seconds
    assert store.run_count == 3

    replay = searcher.search(_spec())
    assert replay.discovery_id == result.discovery_id
    assert replay.as_dict(canonical=True) == result.as_dict(canonical=True)
    assert replay.observable_sets == result.observable_sets
    assert store.run_count == 3
    store.close()