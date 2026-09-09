"""Task 2.4 Stage 4: cross-composition ranking + diversity frontier.

Stage 4 consumes a Stage 3 ``CompositionSearchResult`` (ordered
``CompositionEvaluation`` snapshots + per-composition ``CommonObservableSet``
envelope) and answers, under an explicit common profile, which executable
compositions rank highest and which ones form the behaviorally diverse
frontier.  The ranking reuses ``rank_by_profile`` (pool-level min-max
normalization, weight/direction scoring, per-feature contribution
explanation) and the frontier reuses ``select_diverse_frontier`` /
``behavior_distance`` / ``compute_frontier_diagnostics`` exactly -- nothing
here re-implements a ranking or a diversity algorithm, nothing executes a
world, and nothing writes to the lineage store.

The mandated properties proven here:

  * A: an ordered evaluation ranking for a real search result, under an
    explicit profile with stated weights/directions and a documented
    pool-wide normalization basis;
  * B: a valid profile addressing only genuinely common observables ranks
    every evaluated composition;
  * C: a profile referencing a feature that is not common for every
    composition raises a clear ``CompositionAnalysisError``;
  * D: normalization is pool-level min-max with a documented constant-feature
    rule (zero-range -> 0.0, contribution 0);
  * E: determinism -- repeated analyses produce identical canonical output,
    raw values preserved verbatim;
  * F: direction handling -- maximize vs minimize orderings are honored and
    consistent with the documented ``weight * directional`` score;
  * G: the Task 1.7 tie-break contract survives (score desc, run id asc);
  * H: raw common-observable values are preserved byte-for-byte in every
    ranked row and frontier vector;
  * I: composition lineage metadata (composition_id/shape_id/run_id/
    world_hash/world_id/status) and the discovery_id survive into the
    analysis result, and frontier members retain their source evaluation;
  * J: analysis is pure -- nothing is executed and the lineage store is
    untouched (no new runs, no new tables);
  * K: the existing rank_by_profile / select_diverse_frontier /
    compute_frontier_diagnostics machinery is reused, not rewritten;
  * L: composition identity is never a distance term -- the diversity
    vectors contain only common-observable features, and identical behavior
    vectors score zero distance regardless of composition id;
  * M: two explicit profiles (A: quality-focused, B: alternative defensible)
    over the same search result produce independent, consistent analyses;
  * N: canonical serialization excludes timing and is stable;
  * O: empty and invalid inputs reduce deterministically or fail loudly;
  * P: the frontier is an ordered quality ranking + selected frontier +
    diagnostics + discovery_id + profile identity, in catalog order;
  * Q: the new generic core module stays experiment-free and visualization-
    free, and adds no backward coupling into the Stage 1-3 modules.

Plus one slow test over the canonical full-length repository catalog.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from test_composition_search import (
    CORE_DIR,
    FORBIDDEN_CORE_TOKENS,
    build_fast_repository_catalog,
)
from test_composition_search_stage2 import (
    STAGE2_FORBIDDEN_TOKENS,
    _spec,
)

import sim_alchemist.core.composition_analysis as ca
from experiments.catalog import (
    build_repository_catalog,
    repository_executors,
)
from sim_alchemist.core import (
    EXECUTABLE,
    CommonObservable,
    CommonObservableSet,
    CompositionAnalysisError,
    CompositionAnalysisResult,
    CompositionAnalyst,
    CompositionEvaluation,
    CompositionSearcher,
    CompositionSearchResult,
    CompositionSearchTiming,
    InterestingnessProfile,
    LineageStore,
    common_observable_vocabulary,
    composition_analysis_id_of,
    rank_compositions,
    select_frontier,
)

COMMON_TRIPLE = ("field_entropy", "final_field_mean", "final_field_std")

PROFILE_A = InterestingnessProfile(
    name="structural_quality",
    description="quality-focused: prefer patterned, low-entropy, strong fields",
    weights={
        "final_field_std": 1.0,
        "field_entropy": 0.5,
        "final_field_mean": 0.25,
    },
    directions={
        "final_field_std": True,
        "field_entropy": False,
        "final_field_mean": True,
    },
)

PROFILE_B = InterestingnessProfile(
    name="field_level",
    description="alternative: prefer high overall field level with mild spread",
    weights={
        "final_field_mean": 1.0,
        "final_field_std": 0.5,
        "field_entropy": 0.25,
    },
    directions={
        "final_field_mean": True,
        "final_field_std": False,
        "field_entropy": False,
    },
)

VISUALIZATION_TOKENS = ("matplotlib", "pyplot", "plot", "chart", "dashboard")
PERSISTENCE_TOKENS = ("sqlite", "record_run", "sweep", "searcher", "executor")


@dataclass
class _SearchFixture:
    catalog: object
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


def _empty_case() -> CompositionSearchResult:
    timing = CompositionSearchTiming(
        n_executable=0,
        n_evaluated=0,
        evaluation_seconds=0.0,
        observation_seconds=0.0,
        total_seconds=0.0,
        mean_seconds=0.0,
    )
    return CompositionSearchResult(
        discovery_id="d", spec=_spec(), evaluations=(), timing=timing
    )


def _synthetic_result(specs: list[dict]) -> CompositionSearchResult:
    """Build an aligned evaluation+observable-set result by hand."""
    evaluations: list[CompositionEvaluation] = []
    sets: list[CommonObservableSet] = []
    for spec in specs:
        evaluation = CompositionEvaluation(
            composition_id=spec["composition_id"],
            shape_id=spec["shape_id"],
            world_hash=f"w-{spec['composition_id']}",
            run_id=spec["run_id"],
            world_id=f"wid-{spec['composition_id']}",
            status=EXECUTABLE,
            seed=0,
            metrics={name: float(value) for name, value in spec["values"].items()},
        )
        evaluations.append(evaluation)
        sets.append(
            CommonObservableSet(
                composition_id=spec["composition_id"],
                shape_id=spec["shape_id"],
                world_hash=f"w-{spec['composition_id']}",
                run_id=spec["run_id"],
                world_id=f"wid-{spec['composition_id']}",
                status=EXECUTABLE,
                seed=0,
                max_steps=None,
                macro_timestep=None,
                observables=tuple(
                    CommonObservable(
                        name=name, value=float(value), available=True
                    )
                    for name, value in sorted(spec["values"].items())
                ),
            )
        )
    timing = CompositionSearchTiming(
        n_executable=len(evaluations),
        n_evaluated=len(evaluations),
        evaluation_seconds=0.0,
        observation_seconds=0.0,
        total_seconds=0.0,
        mean_seconds=0.0,
    )
    return CompositionSearchResult(
        discovery_id="synthetic",
        spec=_spec(),
        evaluations=tuple(evaluations),
        observable_sets=tuple(sets),
        timing=timing,
    )


# ----------------------------------------------------------------------
# A/B. Valid ranking from a real search result
# ----------------------------------------------------------------------
class TestRankingValid:
    def test_a_real_result_ranks_every_evaluation(self, search_fixture: _SearchFixture) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        assert ranking.profile == PROFILE_A
        assert ranking.vocabulary == COMMON_TRIPLE
        assert len(ranking.rows) == 3
        assert sorted(r.composition_id for r in ranking.rows) == sorted(
            search_fixture.result.composition_ids
        )
        assert ranking.ranked_ids() == [row.composition_id for row in ranking.rows]
        assert [row.rank for row in ranking.rows] == [1, 2, 3]

    def test_b_ranking_is_score_descending_with_run_id_tiebreak(
        self, search_fixture: _SearchFixture
    ) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        for prev, cur in zip(ranking.rows, ranking.rows[1:]):
            assert (cur.score, prev.run_id) <= (prev.score, cur.run_id)
            assert cur.score <= prev.score

    def test_b_contributions_cover_exactly_the_profile_features(
        self, search_fixture: _SearchFixture
    ) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        expected = set(PROFILE_A.weights)
        for row in ranking.rows:
            assert set(row.contributions) == expected
            assert set(row.raw) == expected
            assert set(row.normalized) == expected
            for c in row.contributions.values():
                assert c.feature in expected
                assert c.weight == PROFILE_A.weights[c.feature]


# ----------------------------------------------------------------------
# C. Unavailable features fail loudly
# ----------------------------------------------------------------------
class TestUnavailableFeature:
    def test_c_composition_specific_feature_rejected(
        self, search_fixture: _SearchFixture
    ) -> None:
        bad = InterestingnessProfile(
            name="leaky",
            description="",
            weights={"dissolved_total": 1.0},
        )
        with pytest.raises(CompositionAnalysisError) as exc:
            rank_compositions(search_fixture.result, bad)
        assert "dissolved_total" in str(exc.value)
        assert COMMON_TRIPLE[0] in str(exc.value)

    def test_c_bogus_feature_rejected(self, search_fixture: _SearchFixture) -> None:
        bad = InterestingnessProfile(name="noisy", description="", weights={"nope": 1.0})
        with pytest.raises(CompositionAnalysisError):
            rank_compositions(search_fixture.result, bad)

    def test_c_error_is_a_value_error(self) -> None:
        assert issubclass(CompositionAnalysisError, ValueError)


# ----------------------------------------------------------------------
# D. Normalization basis
# ----------------------------------------------------------------------
class TestNormalization:
    def test_d_normalized_is_documented_pool_wide_min_max(
        self, search_fixture: _SearchFixture
    ) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        raws = {}
        for row in ranking.rows:
            raws[row.composition_id] = {
                feature: c.raw for feature, c in row.contributions.items()
            }
        for feature in PROFILE_A.weights:
            values = [raws[cid][feature] for cid in raws]
            assert values is not None
            vals = [v for v in values if v is not None]
            lo, hi = min(vals), max(vals)
            for row in ranking.rows:
                norm = row.normalized[feature]
                if hi - lo <= 1e-9:
                    assert norm == 0.0
                else:
                    assert norm == pytest.approx(
                        (raws[row.composition_id][feature] - lo) / (hi - lo)
                    )

    def test_d_constant_feature_yields_zero_contribution(self) -> None:
        result = _synthetic_result(
            [
                {"composition_id": "x1", "shape_id": "s", "run_id": "r1",
                 "values": {"a": 5.0, "b": 1.0}},
                {"composition_id": "x2", "shape_id": "s", "run_id": "r2",
                 "values": {"a": 5.0, "b": 2.0}},
            ]
        )
        profile = InterestingnessProfile(
            name="const", description="", weights={"a": 1.0, "b": 1.0}
        )
        ranking = rank_compositions(result, profile)
        for row in ranking.rows:
            assert row.normalized["a"] == 0.0
            assert row.contributions["a"].normalized == 0.0
            assert row.contributions["a"].contribution == 0.0
            assert row.raw["a"] in (5.0,)

    def test_d_multiple_evaluations_share_one_basis(self) -> None:
        result = _synthetic_result(
            [
                {"composition_id": "x1", "shape_id": "s", "run_id": "r1",
                 "values": {"a": 1.0, "b": 10.0}},
                {"composition_id": "x2", "shape_id": "s", "run_id": "r2",
                 "values": {"a": 3.0, "b": 30.0}},
                {"composition_id": "x3", "shape_id": "s", "run_id": "r3",
                 "values": {"a": 2.0, "b": 20.0}},
            ]
        )
        profile = InterestingnessProfile(
            name="basis", description="", weights={"a": 1.0}
        )
        ranking = rank_compositions(result, profile)
        norm_a = {row.run_id: row.normalized["a"] for row in ranking.rows}
        assert norm_a["r1"] == 0.0
        assert norm_a["r3"] == 0.5
        assert norm_a["r2"] == 1.0


# ----------------------------------------------------------------------
# E/G/F. Determinism, ties, and direction
# ----------------------------------------------------------------------
class TestDeterminismAndDirection:
    def test_e_repeated_ranking_is_canonically_identical(
        self, search_fixture: _SearchFixture
    ) -> None:
        first = rank_compositions(search_fixture.result, PROFILE_A)
        second = rank_compositions(search_fixture.result, PROFILE_A)
        assert first.as_dict() == second.as_dict()
        assert [r.as_dict() for r in first.rows] == [r.as_dict() for r in second.rows]
        assert first.ranked_ids() == second.ranked_ids()

    def test_f_maximize_prefers_high_values(self) -> None:
        result = _synthetic_result(
            [
                {"composition_id": "lo", "shape_id": "s", "run_id": "r-lo",
                 "values": {"a": 1.0}},
                {"composition_id": "hi", "shape_id": "s", "run_id": "r-hi",
                 "values": {"a": 2.0}},
            ]
        )
        up = InterestingnessProfile(name="up", description="", weights={"a": 1.0}, directions={"a": True})
        down = InterestingnessProfile(name="down", description="", weights={"a": 1.0}, directions={"a": False})
        up_rank = rank_compositions(result, up)
        down_rank = rank_compositions(result, down)
        assert up_rank.rows[0].composition_id == "hi"
        assert up_rank.rows[1].composition_id == "lo"
        assert down_rank.rows[0].composition_id == "lo"
        assert down_rank.rows[1].composition_id == "hi"
        hi_max_row = up_rank.row("hi")
        lo_min_row = down_rank.row("lo")
        assert hi_max_row is not None and lo_min_row is not None
        assert hi_max_row.score == pytest.approx(1.0)
        assert lo_min_row.score == pytest.approx(1.0)

    def test_g_equal_scores_tie_break_by_run_id(self) -> None:
        result = _synthetic_result(
            [
                {"composition_id": "z", "shape_id": "s", "run_id": "run-b",
                 "values": {"a": 1.0}},
                {"composition_id": "a", "shape_id": "s", "run_id": "run-a",
                 "values": {"a": 1.0}},
            ]
        )
        profile = InterestingnessProfile(name="tie", description="", weights={"a": 1.0})
        ranking = rank_compositions(result, profile)
        assert [r.run_id for r in ranking.rows] == ["run-a", "run-b"]
        assert ranking.rows[0].score == ranking.rows[1].score


# ----------------------------------------------------------------------
# H/I. Raw values and metadata preservation
# ----------------------------------------------------------------------
class TestDataPreservation:
    def test_h_raw_values_are_verbatim_from_the_observable_sets(
        self, search_fixture: _SearchFixture
    ) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        for row in ranking.rows:
            observable_set = search_fixture.result.observable_set(row.composition_id)
            assert observable_set is not None
            for feature in PROFILE_A.weights:
                observed = observable_set.observable(feature)
                assert observed is not None and observed.available
                assert row.raw[feature] == observed.value
                assert isinstance(row.raw[feature], float)

    def test_i_metadata_survives_into_every_row(self, search_fixture: _SearchFixture) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        by_eval = {e.composition_id: e for e in search_fixture.result.evaluations}
        for row in ranking.rows:
            evaluation = by_eval[row.composition_id]
            assert row.shape_id == evaluation.shape_id
            assert row.run_id == evaluation.run_id
            assert row.world_hash == evaluation.world_hash
            assert row.world_id == evaluation.world_id
            assert row.status == EXECUTABLE
            assert row.evaluation is evaluation
            assert row.observable_set is search_fixture.result.observable_set(
                row.composition_id
            )

    def test_i_frontier_members_keep_their_evaluation(
        self, search_fixture: _SearchFixture
    ) -> None:
        frontier = select_frontier(search_fixture.result, PROFILE_A)
        by_eval = {e.composition_id: e for e in search_fixture.result.evaluations}
        for member in frontier.members:
            assert member.evaluation is by_eval[member.composition_id]
            assert member.evaluation is not None
            assert member.observable_set is search_fixture.result.observable_set(
                member.composition_id
            )


# ----------------------------------------------------------------------
# J. Analysis-only purity
# ----------------------------------------------------------------------
class TestAnalysisOnly:
    def test_j_analysis_writes_nothing_to_the_store(
        self, search_fixture: _SearchFixture
    ) -> None:
        before = search_fixture.store.run_count
        analyst = CompositionAnalyst()
        analyst.analyze(search_fixture.result, PROFILE_A)
        assert search_fixture.store.run_count == before == 3
        tables = [
            row[0]
            for row in search_fixture.store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        assert not any("analysis" in t for t in tables)
        assert not any("frontier" in t for t in tables)

    def test_j_analyst_holds_no_execution_state(self) -> None:
        analyst = CompositionAnalyst()
        assert not hasattr(analyst, "executor")
        assert not hasattr(analyst, "store")
        assert not hasattr(analyst, "catalog")

    def test_j_input_result_is_not_mutated(self, search_fixture: _SearchFixture) -> None:
        before = search_fixture.result.as_dict(canonical=True)
        CompositionAnalyst().analyze(search_fixture.result, PROFILE_A)
        assert search_fixture.result.as_dict(canonical=True) == before


# ----------------------------------------------------------------------
# K. Reuse of the existing generic machinery
# ----------------------------------------------------------------------
class TestReuse:
    def test_k_rank_and_frontier_machinery_is_invoked(self, monkeypatch) -> None:
        calls = {"rank": 0, "frontier": 0, "diag": 0}
        real_rank = ca.rank_by_profile
        real_frontier = ca.select_diverse_frontier
        real_diag = ca.compute_frontier_diagnostics

        def counting_rank(population, profile):
            calls["rank"] += 1
            return real_rank(population, profile)

        def counting_frontier(*args, **kwargs):
            calls["frontier"] += 1
            return real_frontier(*args, **kwargs)

        def counting_diag(*args, **kwargs):
            calls["diag"] += 1
            return real_diag(*args, **kwargs)

        monkeypatch.setattr(ca, "rank_by_profile", counting_rank)
        monkeypatch.setattr(ca, "select_diverse_frontier", counting_frontier)
        monkeypatch.setattr(ca, "compute_frontier_diagnostics", counting_diag)

        result = ca.CompositionAnalyst().analyze(_synthetic_result(
            [
                {"composition_id": "x1", "shape_id": "s", "run_id": "r1",
                 "values": {"a": 1.0, "b": 2.0}},
                {"composition_id": "x2", "shape_id": "s", "run_id": "r2",
                 "values": {"a": 3.0, "b": 4.0}},
            ]
        ), InterestingnessProfile(name="t", description="", weights={"a": 1.0}))
        assert calls["rank"] >= 1
        assert calls["frontier"] >= 1
        assert calls["diag"] >= 1
        assert len(result.ranking.rows) == 2


# ----------------------------------------------------------------------
# L. Identity is not a distance term
# ----------------------------------------------------------------------
class TestIdentityNotDistance:
    def test_l_identical_behavior_vectors_give_zero_distance(self) -> None:
        result = _synthetic_result(
            [
                {"composition_id": "compa", "shape_id": "s", "run_id": "r1",
                 "values": {"a": 1.0, "b": 2.0}},
                {"composition_id": "compb", "shape_id": "t", "run_id": "r2",
                 "values": {"a": 1.0, "b": 2.0}},
            ]
        )
        frontier = select_frontier(result, InterestingnessProfile(
            name="d", description="", weights={"a": 1.0, "b": 1.0}
        ), quality_weight=1.0, diversity_weight=1.0)
        assert "composition_id" not in frontier.vocabulary
        assert frontier.vocabulary == ("a", "b")
        assert set(frontier.isolation) == {"compa", "compb"}
        assert frontier.isolation["compa"] == 0.0
        assert frontier.isolation["compb"] == 0.0
        second = frontier.members[1]
        assert second.selection_reason == "diversity_balanced"
        assert second.diversity_score == 0.0

    def test_l_vocabulary_is_features_only(self, search_fixture: _SearchFixture) -> None:
        frontier = select_frontier(search_fixture.result, PROFILE_A)
        for name in ("composition_id", "run_id", "world_hash"):
            assert name not in frontier.vocabulary


# ----------------------------------------------------------------------
# M. Two explicit profiles over the same result
# ----------------------------------------------------------------------
class TestTwoProfiles:
    def test_m_profiles_a_and_b_are_independent_and_well_formed(
        self, search_fixture: _SearchFixture
    ) -> None:
        analyst = CompositionAnalyst()
        analysis_a = analyst.analyze(search_fixture.result, PROFILE_A)
        analysis_b = analyst.analyze(search_fixture.result, PROFILE_B)
        assert isinstance(analysis_a, CompositionAnalysisResult)
        assert isinstance(analysis_b, CompositionAnalysisResult)
        assert analysis_a.analysis_id != analysis_b.analysis_id
        assert analysis_a.discovery_id == analysis_b.discovery_id == search_fixture.result.discovery_id
        assert analysis_a.vocabulary == analysis_b.vocabulary == COMMON_TRIPLE
        assert analysis_a.ranked_ids() != []
        assert analysis_a.ranked_ids() == list(dict.fromkeys(analysis_a.ranked_ids()))
        assert len(analysis_a.frontier.members) == 3
        assert len(analysis_b.frontier.members) == 3
        assert analysis_a.frontier.member_ids() == list(dict.fromkeys(analysis_a.frontier.member_ids()))

    def test_m_analysis_id_is_content_addressed(self) -> None:
        first = composition_analysis_id_of(
            "disc", PROFILE_A, quality_weight=1.0, diversity_weight=1.0
        )
        second = composition_analysis_id_of(
            "disc", PROFILE_A, quality_weight=1.0, diversity_weight=1.0
        )
        other = composition_analysis_id_of(
            "disc", PROFILE_B, quality_weight=1.0, diversity_weight=1.0
        )
        assert first == second
        assert len(first) == 24
        assert first != other


# ----------------------------------------------------------------------
# N. Canonical serialization
# ----------------------------------------------------------------------
class TestCanonical:
    def test_n_canonical_form_excludes_timing_and_is_stable(
        self, search_fixture: _SearchFixture
    ) -> None:
        analyst = CompositionAnalyst()
        first = analyst.analyze(search_fixture.result, PROFILE_A)
        second = analyst.analyze(search_fixture.result, PROFILE_A)
        canonical = first.as_dict(canonical=True)
        assert "timing" not in canonical
        assert "extraction_seconds" not in str(canonical)
        assert first.as_dict(canonical=True) == second.as_dict(canonical=True)
        assert first.as_dict(canonical=True)["profile"]["name"] == "structural_quality"
        assert first.as_dict(canonical=True)["analysis_id"] == first.analysis_id

    def test_n_timing_is_split_and_totals_are_sensible(
        self, search_fixture: _SearchFixture
    ) -> None:
        analysis = CompositionAnalyst().analyze(search_fixture.result, PROFILE_A)
        timing = analysis.timing
        assert timing.extraction_seconds >= 0
        assert timing.ranking_seconds >= 0
        assert timing.frontier_seconds >= 0
        assert timing.total_seconds == pytest.approx(
            timing.extraction_seconds + timing.ranking_seconds + timing.frontier_seconds,
            abs=1e-3,
        )
        assert set(timing.as_dict()) == {
            "extraction_seconds",
            "ranking_seconds",
            "frontier_seconds",
            "total_seconds",
        }


# ----------------------------------------------------------------------
# O. Empty and invalid inputs
# ----------------------------------------------------------------------
class TestEmptyAndInvalid:
    def test_o_empty_pool_is_deterministic(self) -> None:
        result = _empty_case()
        assert common_observable_vocabulary(result) == ()
        ranking = rank_compositions(result, PROFILE_A)
        assert ranking.rows == ()
        assert ranking.vocabulary == ()
        frontier = select_frontier(result, PROFILE_A, ranking=ranking)
        assert frontier.members == ()
        assert frontier.isolation == {}
        analysis = CompositionAnalyst().analyze(result, PROFILE_A)
        assert analysis.ranking.rows == ()
        assert analysis.frontier.members == ()
        assert analysis.vocabulary == ()

    def test_o_evaluations_without_observable_sets_fail_loudly(self) -> None:
        timing = CompositionSearchTiming(
            n_executable=0,
            n_evaluated=0,
            evaluation_seconds=0.0,
            observation_seconds=0.0,
            total_seconds=0.0,
            mean_seconds=0.0,
        )
        evaluation = CompositionEvaluation(
            composition_id="c", shape_id="s", world_hash="h", run_id="r",
            world_id="w", status=EXECUTABLE, seed=0, metrics={"a": 1.0},
        )
        legacy = CompositionSearchResult(
            discovery_id="d", spec=_spec(), evaluations=(evaluation,), timing=timing
        )
        with pytest.raises(CompositionAnalysisError):
            common_observable_vocabulary(legacy)
        with pytest.raises(CompositionAnalysisError):
            rank_compositions(legacy, PROFILE_A)

    def test_o_type_guards(self, search_fixture: _SearchFixture) -> None:
        with pytest.raises(TypeError):
            rank_compositions(object(), PROFILE_A)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            rank_compositions(search_fixture.result, "not-a-profile")  # type: ignore[arg-type]
        with pytest.raises(CompositionAnalysisError):
            rank_compositions(
                search_fixture.result,
                InterestingnessProfile(name="bad", description="", weights={1: 1.0}),  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# P. Frontier structure
# ----------------------------------------------------------------------
class TestFrontierStructure:
    def test_p_frontier_members_are_ranked_and_reasoned(
        self, search_fixture: _SearchFixture
    ) -> None:
        ranking = rank_compositions(search_fixture.result, PROFILE_A)
        frontier = select_frontier(
            search_fixture.result, PROFILE_A, ranking=ranking,
            quality_weight=1.0, diversity_weight=1.0, beam_width=2,
        )
        assert len(frontier.members) == 2
        assert frontier.members[0].selection_reason == "highest_quality"
        assert frontier.members[0].rank == 1
        assert frontier.members[0].quality_score == ranking.rows[0].score
        for member in frontier.members:
            assert member.quality_score >= 0
            assert member.diversity_score >= 0
            assert member.combined_score >= 0
            assert member.composition_id in frontier.isolation

    def test_p_frontier_default_beam_is_the_whole_pool(
        self, search_fixture: _SearchFixture
    ) -> None:
        frontier = select_frontier(search_fixture.result, PROFILE_A)
        assert frontier.beam_width == 3
        assert len(frontier.members) == 3

    def test_p_diagnostics_are_present(self, search_fixture: _SearchFixture) -> None:
        frontier = select_frontier(search_fixture.result, PROFILE_A)
        diagnostics = frontier.diagnostics
        assert diagnostics.n_candidates == 3
        assert diagnostics.n_unique_signatures >= 1
        assert diagnostics.mean_pairwise_distance >= 0
        assert diagnostics.min_pairwise_distance >= 0


# ----------------------------------------------------------------------
# Q. Generic-core purity + no backward coupling
# ----------------------------------------------------------------------
class TestPurityScans:
    def test_q_analysis_module_is_experiment_free(self) -> None:
        source = (CORE_DIR / "composition_analysis.py").read_text(encoding="utf-8")
        lowered = source.lower()
        tokens = FORBIDDEN_CORE_TOKENS + STAGE2_FORBIDDEN_TOKENS
        hits = [tok for tok in tokens if tok in lowered]
        assert not hits, f"core/composition_analysis.py contains experiment identifiers: {hits}"

    def test_q_analysis_module_has_no_visualization_or_persistence(self) -> None:
        source = (CORE_DIR / "composition_analysis.py").read_text(encoding="utf-8").lower()
        viz = [tok for tok in VISUALIZATION_TOKENS if tok in source]
        assert not viz, f"core/composition_analysis.py contains visualization identifiers: {viz}"
        persist = [tok for tok in PERSISTENCE_TOKENS if tok in source]
        assert not persist, f"core/composition_analysis.py contains persistence identifiers: {persist}"

    def test_q_no_backward_coupling_into_earlier_core_modules(self) -> None:
        for filename in ("composition_search.py", "observables.py"):
            source = (CORE_DIR / filename).read_text(encoding="utf-8")
            hits = [
                ident
                for ident in (
                    "composition_analysis",
                    "rank_compositions",
                    "select_frontier",
                    "CompositionAnalyst",
                    "CompositionRanking",
                )
                if ident in source
            ]
            assert not hits, f"core/{filename} references Stage 4 API: {hits}"


# ----------------------------------------------------------------------
# Slow: real canonical analysis over the full repository catalog
# ----------------------------------------------------------------------
@pytest.mark.slow
def test_slow_canonical_analysis_and_frontiers() -> None:
    catalog = build_repository_catalog(generate_worlds=True)
    assert len(catalog.executable()) == 3
    store = LineageStore(":memory:")
    searcher = CompositionSearcher(catalog, repository_executors(), store)
    result = searcher.search(_spec())
    assert store.run_count == 3

    analyst = CompositionAnalyst()
    analysis_a = analyst.analyze(result, PROFILE_A)
    analysis_b = analyst.analyze(result, PROFILE_B)

    assert analysis_a.vocabulary == COMMON_TRIPLE
    assert analysis_a.discovery_id == result.discovery_id
    assert len(analysis_a.ranking.rows) == 3
    assert len(analysis_a.frontier.members) == 3
    assert len(analysis_b.ranking.rows) == 3
    assert len(analysis_b.frontier.members) == 3
    assert set(analysis_a.frontier.isolation) == set(result.composition_ids)

    for row in analysis_a.ranking.rows:
        evaluation = result.evaluation(row.composition_id)
        assert evaluation is not None
        assert row.world_hash == evaluation.world_hash
        for feature in COMMON_TRIPLE:
            assert row.raw[feature] is not None

    replay = CompositionAnalyst().analyze(result, PROFILE_A)
    assert replay.analysis_id == analysis_a.analysis_id
    assert replay.as_dict(canonical=True) == analysis_a.as_dict(canonical=True)
    assert store.run_count == 3

    store.close()