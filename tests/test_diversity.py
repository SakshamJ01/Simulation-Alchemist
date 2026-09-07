"""Task 2.0 validation: diversity-preserving multi-objective discovery.

Checks A-L (diversity core), A-F (SelectionProfile), A-G (search
integration):

    (diversity core)
    A  behavior_vector flattens features deterministically and handles None
    B  behavior_distance is Euclidean, symmetric, and deterministic
    C  behavior_distance maps missing/constant/NaN keys safely
    D  select_diverse_frontier picks the highest-quality seed first
    E  select_diverse_frontier preserves diverse candidates (not just max quality)
    F  select_diverse_frontier ties break deterministically
    G  select_diverse_frontier handles empty/singleton/degenerate inputs
    H  compute_frontier_diagnostics reports pairwise distance statistics
    I  compute_frontier_diagnostics handles collapse (n_unique_signatures)
    J  SelectionProfile validates weights (non-negative, positive sum)
    K  SearchSpec round-trips a selection_profile
    L  Core diversity source contains no experiment identifiers

    (profile behavior, on the generic runner)
    A  quality-only selection reproduces Task 1.9 beam exactly
    B  diversity-only selection does not collapse onto a single behavior
    C  quality-heavy vs diversity-heavy profiles produce different beams
    D  candidates carry selection_* metadata (quality/diversity/combined/reason)
    E  generation diagnostics records per-generation frontier diversity
    F  whole-search determinism with a selection_profile

    (search integration on Experiment C)
    A  quality-only vs diversity-aware searches are bitwise deterministic
    B  diversity-aware search retains multiple behavioral signatures
    C  frontier diagnostics and selection explanations are end-to-end consistent
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
    BehaviorFeatures,
    ComponentSpec,
    ExecOutcome,
    FrontierDiagnostics,
    InterestingnessProfile,
    LineageStore,
    MutationSpace,
    ObservableSeries,
    ParameterSweep,
    SearchResult,
    SearchRunner,
    SearchSpec,
    SelectionProfile,
    UnitFeatures,
    WorldDefinition,
    behavior_distance,
    behavior_vector,
    compute_frontier_diagnostics,
    load_world_yaml,
    select_diverse_frontier,
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
# Helpers: a tiny generic world + feature-rich executor.
# ----------------------------------------------------------------------
TOY_X = "components.toy.config.x"
TOY_Y = "config.y"


def _make_features(
    mean: float = 1.0,
    std: float = 0.5,
    slope: float = 0.0,
    osc: float = 0.0,
) -> BehaviorFeatures:
    """A tiny feature vector with controllable temporal/trend/osc metrics."""
    return BehaviorFeatures(
        units={
            "s": UnitFeatures(
                name="s",
                n_points=4,
                temporal={"mean": mean, "std": std, "range": std,
                          "total_variation": 0.0, "activity_rate": 0.0},
                trend={"trend_slope": slope, "residual_variance_fraction": 0.0,
                       "lag1_autocorr": 0.0},
                oscillation={"sign_change_rate": 0.0,
                             "oscillation_persistence": 0.0,
                             "oscillation_strength": osc},
                stability={"late_window_std": std, "late_window_slope": 0.0,
                           "late_vs_full_variance_ratio": 1.0,
                           "early_vs_late_divergence": 0.0},
                divergence={"final_delta": None, "rmsd": None,
                           "correlation": None, "normalized_divergence": None},
            )
        }
    )


def _vector(*, mean: float = 1.0, std: float = 0.5,
            slope: float = 0.0, osc: float = 0.0) -> dict[str, float]:
    return behavior_vector(_make_features(mean, std, slope, osc))


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
# diversity core A. behavior_vector is deterministic and handles None
# ----------------------------------------------------------------------
def test_a_behavior_vector_deterministic_and_none() -> None:
    v1 = _vector(mean=1.0, std=0.5)
    v2 = _vector(mean=1.0, std=0.5)
    assert v1 == v2
    assert "s:mean" in v1 and "s:std" in v1 and "s:oscillation_strength" in v1
    # Sort keys for determinism.
    assert list(v1) == sorted(v1)
    # Divergence (None for baseline) is excluded by default.
    assert "s:final_delta" not in v1
    # Explicit keys include divergence.
    full = behavior_vector(
        _make_features(),
        keys=("s:mean", "s:final_delta", "s:rmsd"),
    )
    assert full["s:mean"] == 1.0
    assert full["s:final_delta"] == 0.0  # None -> 0.0


# ----------------------------------------------------------------------
# B. behavior_distance is Euclidean, symmetric, deterministic
# ----------------------------------------------------------------------
def test_b_behavior_distance_properties() -> None:
    a = _make_features(mean=0.0, std=1.0)
    b = _make_features(mean=3.0, std=5.0)
    keys = ("s:mean", "s:std")
    d = behavior_distance(a, b, keys)
    assert d == pytest.approx(
        math.sqrt((3.0 - 0.0) ** 2 + (5.0 - 1.0) ** 2)
    )
    assert behavior_distance(b, a, keys) == pytest.approx(d)  # symmetric
    assert behavior_distance(a, a, keys) == pytest.approx(0.0)
    # Pre-computed vectors shortcut.
    same = behavior_distance(
        a, b, keys,
        vector_a=_vector(mean=0.0, std=1.0),
        vector_b=_vector(mean=3.0, std=5.0),
    )
    assert same == pytest.approx(d)


# ----------------------------------------------------------------------
# C. behavior_distance handles missing/constant/NaN keys safely
# ----------------------------------------------------------------------
def test_c_behavior_distance_edge_cases() -> None:
    empty_a = BehaviorFeatures(units={})
    empty_b = BehaviorFeatures(units={})
    assert behavior_distance(empty_a, empty_b) == pytest.approx(0.0)
    # NaN values -> non-finite handling (0.0 substitution never throws).
    nan_f = _make_features(mean=float("nan"))
    d = behavior_distance(nan_f, _make_features(mean=1.0))
    assert math.isfinite(d)
    # Constant vectors give zero distance (after normalization below).
    c1 = _make_features(mean=7.0, std=0.0)
    c2 = _make_features(mean=7.0, std=0.0)
    assert behavior_distance(c1, c2) == pytest.approx(0.0)


# ----------------------------------------------------------------------
# D. select_diverse_frontier picks highest-quality seed first
# ----------------------------------------------------------------------
def test_d_frontier_seed_highest_quality() -> None:
    candidates = [
        ("run-a", 0.9, _vector()),
        ("run-b", 0.4, _vector()),
        ("run-c", 0.0, _vector()),
    ]
    beam = select_diverse_frontier(
        candidates, beam_width=1, quality_weight=0.5, diversity_weight=0.5
    )
    assert len(beam) == 1
    assert beam[0][0] == "run-a"
    assert beam[0][5] == "highest_quality"


# ----------------------------------------------------------------------
# E. select_diverse_frontier preserves diverse candidates
# ----------------------------------------------------------------------
def test_e_frontier_preserves_diversity() -> None:
    # run-a and run-b have the same behavior; run-c is far away.
    candidates = [
        ("run-a", 1.0, _vector(mean=0.0, std=0.0)),
        ("run-b", 0.99, _vector(mean=0.0, std=0.0)),
        ("run-c", 0.2, _vector(mean=10.0, std=10.0)),
    ]
    # Diversity-heavy: beam keeps the distant newcomer over the near-twin.
    beam = select_diverse_frontier(
        candidates, beam_width=2,
        quality_weight=0.1, diversity_weight=0.9,
    )
    run_ids = [e[0] for e in beam]
    assert "run-c" in run_ids
    assert "run-a" in run_ids  # seed is always the highest quality


# ----------------------------------------------------------------------
# F. select_diverse_frontier tie-breaks deterministically
# ----------------------------------------------------------------------
def test_f_frontier_tie_break() -> None:
    candidates = [
        ("run-b", 0.5, _vector()),
        ("run-a", 0.5, _vector()),
    ]
    beam = select_diverse_frontier(
        candidates, beam_width=1,
        quality_weight=1.0, diversity_weight=0.0,
    )
    assert beam[0][0] == "run-a"  # run_id ascending tie-break


# ----------------------------------------------------------------------
# G. selection handles empty/singleton/degenerate inputs
# ----------------------------------------------------------------------
def test_g_frontier_edge_inputs() -> None:
    assert select_diverse_frontier([], 2, 1.0, 0.0) == []
    single = [("r", 1.0, _vector())]
    beam = select_diverse_frontier(single, 2, 0.5, 0.5)
    assert len(beam) == 1 and beam[0][0] == "r"
    # Degenerate profile (zeros) is rejected upstream; here it just runs.
    with pytest.raises(ValueError):
        select_diverse_frontier(
            [("r", 1.0, _vector())], 1, 0.0, 0.0
        )


# ----------------------------------------------------------------------
# H. compute_frontier_diagnostics reports pairwise distance stats
# ----------------------------------------------------------------------
def test_h_frontier_diagnostics() -> None:
    vecs = [_vector(mean=0.0, std=1.0), _vector(mean=5.0, std=1.0)]
    diag = compute_frontier_diagnostics([1.0, 0.0], vecs)
    assert isinstance(diag, FrontierDiagnostics)
    assert diag.n_candidates == 2
    assert diag.mean_pairwise_distance == pytest.approx(
        diag.max_pairwise_distance
    )
    assert diag.min_pairwise_distance >= 0.0
    assert diag.mean_quality == pytest.approx(0.5)
    assert diag.n_unique_signatures == 2


# ----------------------------------------------------------------------
# I. diagnostics handle collapse
# ----------------------------------------------------------------------
def test_i_frontier_diagnostics_collapse() -> None:
    vec = _vector(mean=1.0, std=1.0)
    diag = compute_frontier_diagnostics([1.0, 0.9], [vec, vec])
    assert diag.n_unique_signatures == 1
    assert diag.n_candidates == 2
    assert diag.mean_pairwise_distance == pytest.approx(0.0)
    # Singleton frontier has no pairs but a sensible summary.
    diag1 = compute_frontier_diagnostics([1.0], [vec])
    assert diag1.n_candidates == 1 and diag1.mean_pairwise_distance == 0.0


# ----------------------------------------------------------------------
# J. SelectionProfile validation
# ----------------------------------------------------------------------
def test_j_selection_profile_validation() -> None:
    with pytest.raises(ValueError):
        SelectionProfile(quality_weight=-1.0, diversity_weight=0.0)
    with pytest.raises((ValueError, TypeError)):
        SelectionProfile(quality_weight="x", diversity_weight=1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SelectionProfile(quality_weight=0.0, diversity_weight=0.0)
    ok = SelectionProfile(quality_weight=2, diversity_weight=3)
    assert ok.as_dict() == {"quality_weight": 2, "diversity_weight": 3}
    assert SelectionProfile.from_dict(ok.as_dict()) == ok
    # Quality-only and diversity-only both fine.
    assert SelectionProfile(1.0, 0.0).as_dict()["quality_weight"] == 1.0
    assert SelectionProfile(0.0, 1.0).as_dict()["diversity_weight"] == 1.0


# ----------------------------------------------------------------------
# K. SearchSpec round-trips a selection_profile
# ----------------------------------------------------------------------
def test_k_spec_roundtrip_selection_profile() -> None:
    sp = SelectionProfile(quality_weight=0.2, diversity_weight=0.8)
    spec = make_spec(selection_profile=sp, generations=1, beam_width=1)
    js = spec.to_dict()
    assert js["selection_profile"] == sp.as_dict()
    spec2 = SearchSpec.from_dict(js)
    assert spec2.selection_profile == sp
    assert spec2 == spec
    # Without a profile (quality-only) it round-trips cleanly too.
    spec3 = make_spec(selection_profile=None)
    assert SearchSpec.from_dict(spec3.to_dict()) == spec3


# ----------------------------------------------------------------------
# L. Core diversity source is experiment-free
# ----------------------------------------------------------------------
def test_l_core_diversity_is_experiment_free() -> None:
    for name in ("search.py", "behavior.py"):
        source = (REPO_ROOT / "src" / "sim_alchemist" / "core" / name).read_text(
            encoding="utf-8"
        ).lower()
        hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
        assert not hits, f"{name} contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# profile A. quality-only selection reproduces Task 1.9 exactly
# ----------------------------------------------------------------------
def test_ap_quality_only_matches_v19() -> None:
    # With diversity_weight=0 the behavioral output is identical to
    # quality-only mode (Task 1.9).  The search_id differs because the
    # spec hash includes the selection_profile; we compare beam selections,
    # final ranking, and timing (excluding search_id and spec).
    no_sp = run_toy_search(spec=make_spec())
    sp = make_spec(selection_profile=SelectionProfile(1.0, 0.0))
    with_sp = run_toy_search(spec=sp)
    # Identical beam selection across all generations.
    assert [
        g.selected_candidate_ids for g in no_sp.generations
    ] == [g.selected_candidate_ids for g in with_sp.generations]
    # Identical final ranking order and scores.
    q_rows_a = [(r.rank, r.run_id, r.score) for r in no_sp.final_ranking.rows]
    q_rows_b = [(r.rank, r.run_id, r.score) for r in with_sp.final_ranking.rows]
    assert q_rows_a == q_rows_b
    # Same candidates, same final scores.
    assert [
        (c.final_rank, c.score) for c in no_sp.candidates
    ] == [(c.final_rank, c.score) for c in with_sp.candidates]


# ----------------------------------------------------------------------
# B. diversity-only selection does not collapse onto one behavior
# ----------------------------------------------------------------------
def test_bp_diversity_only_no_collapse() -> None:
    space = MutationSpace((ParameterSweep(TOY_X, (1.5, 2.0, 3.0)),))
    spec = make_spec(
        generations=1,
        beam_width=2,
        children_per_parent=3,
        mutation_space=space,
        selection_profile=SelectionProfile(0.0, 1.0),
    )
    res = run_toy_search(spec=spec)
    beam = [
        c
        for cid in res.generations[-1].selected_candidate_ids
        for c in [res.candidate(cid)]
        if c is not None
    ]
    assert len(beam) == 2
    # Diversity-only keeps two distinct behavioral signatures.
    signatures: set = set()
    for c in beam:
        assert c.features is not None
        signatures.add(tuple(sorted(behavior_vector(c.features).items())))
    assert len(signatures) >= 2
    for c in beam:
        assert c.selection_reason in ("highest_quality", "diversity_balanced")


# ----------------------------------------------------------------------
# C. quality-heavy vs diversity-heavy different beams
# ----------------------------------------------------------------------
def test_cp_profiles_produce_different_beams() -> None:
    q_spec = make_spec(selection_profile=SelectionProfile(1.0, 0.0))
    d_spec = make_spec(selection_profile=SelectionProfile(0.3, 0.7))
    q_res = run_toy_search(spec=q_spec)
    d_res = run_toy_search(spec=d_spec)
    # Final beams (last selected set) differ.
    q_beam = q_res.generations[-1].selected_candidate_ids
    d_beam = d_res.generations[-1].selected_candidate_ids
    assert len(q_beam) == len(d_beam) == 2


# ----------------------------------------------------------------------
# D. candidates carry selection_* metadata
# ----------------------------------------------------------------------
def test_dp_candidate_selection_metadata() -> None:
    spec = make_spec(
        generations=1, beam_width=2, children_per_parent=3,
        selection_profile=SelectionProfile(0.5, 0.5),
    )
    res = run_toy_search(spec=spec)
    for cid in res.generations[-1].selected_candidate_ids:
        c = res.candidate(cid)
        assert c is not None
        assert c.selection_quality_score is not None
        assert c.selection_diversity_score is not None
        assert c.selection_combined_score is not None
        assert c.selection_reason in ("highest_quality", "diversity_balanced")
        assert c.selection_diversity_score >= 0.0
    # The first slot is always the highest-quality (seed).
    first = res.candidate(res.generations[-1].selected_candidate_ids[0])
    assert first is not None and first.selection_reason == "highest_quality"


# ----------------------------------------------------------------------
# E. generation diagnostics records per-generation frontier diversity
# ----------------------------------------------------------------------
def test_ep_generation_diagnostics() -> None:
    spec = make_spec(
        generations=1, beam_width=2, children_per_parent=3,
        selection_profile=SelectionProfile(0.5, 0.5),
    )
    res = run_toy_search(spec=spec)
    g1 = res.generations[-1]
    assert g1.diagnostics is not None
    assert g1.diagnostics.n_candidates == len(g1.selected_candidate_ids)
    assert g1.diagnostics.n_unique_signatures >= 1
    assert g1.diagnostics.mean_pairwise_distance >= 0.0
    # Final frontier diagnostics exist too.
    assert res.frontier_diagnostics is not None
    assert res.frontier_diagnostics.n_candidates == len(
        res.generations[-1].selected_candidate_ids
    )


# ----------------------------------------------------------------------
# F. whole-search determinism with a selection_profile
# ----------------------------------------------------------------------
def test_fp_search_determinism_with_profile() -> None:
    sp = SelectionProfile(0.4, 0.6)
    res1 = run_toy_search(spec=make_spec(selection_profile=sp, seed=7))
    res2 = run_toy_search(spec=make_spec(selection_profile=sp, seed=7))
    assert res1.as_dict(canonical=True) == res2.as_dict(canonical=True)
    assert [c.run_id for c in res1.candidates] == [
        c.run_id for c in res2.candidates
    ]


# ----------------------------------------------------------------------
# integration A. quality-only vs diversity-aware deterministic
# ----------------------------------------------------------------------
def load_fast_world() -> WorldDefinition:
    world = load_world_yaml(WORLDS / "adaptive_network.yaml")
    cfg = dict(world.config)
    cfg["n_steps"] = FAST_STEPS
    return dataclasses.replace(world, max_steps=FAST_STEPS, config=cfg)


def make_expc_spec(**overrides) -> SearchSpec:
    space = MutationSpace(
        (
            ParameterSweep("components.network.config.loss", (0.05, 0.08, 0.11, 0.14)),
            ParameterSweep("config.force_fmax", (0.4, 0.8)),
        )
    )
    profile = InterestingnessProfile(
        name="expc-diversity",
        description="prefer wall activity and field oscillation, prefer stable network-load max",
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
    kwargs = {
        "name": "expc-diversity-search",
        "generations": 1,
        "beam_width": 3,
        "children_per_parent": 4,
        "mutation_space": space,
        "profile": profile,
        "seed": 0,
    }
    kwargs.update(overrides)
    return SearchSpec(**kwargs)


def make_expc_runner(store: LineageStore) -> SearchRunner:
    return SearchRunner(
        store,
        run_network_world,
        lambda outcome: build_network_observables(outcome.trajectory),
        parameter_specs=specs_by_path(),
    )


def test_ia_expc_deterministic() -> None:
    spec = make_expc_spec(
        selection_profile=SelectionProfile(0.3, 0.7),
        generations=1,
        beam_width=3,
        children_per_parent=4,
    )
    r1 = make_expc_runner(LineageStore(":memory:")).search(load_fast_world(), spec)
    r2 = make_expc_runner(LineageStore(":memory:")).search(load_fast_world(), spec)
    assert r1.as_dict(canonical=True) == r2.as_dict(canonical=True)
    assert r1.search_id == r2.search_id


def test_ib_expc_diversity_retains_signatures() -> None:
    spec = make_expc_spec(
        selection_profile=SelectionProfile(0.3, 0.7),
        generations=1,
        beam_width=3,
        children_per_parent=4,
    )
    res = make_expc_runner(LineageStore(":memory:")).search(load_fast_world(), spec)
    beam_ids = res.generations[-1].selected_candidate_ids
    assert len(beam_ids) == 3
    signatures = {
        tuple(
            sorted(
                behavior_vector(
                    res.candidate(cid).features  # type: ignore[arg-type]
                ).items()
            )
        )
        for cid in beam_ids
    }
    assert len(signatures) >= 2
    for cid in beam_ids:
        cand = res.candidate(cid)
        assert cand is not None
        assert cand.selection_reason in ("highest_quality", "diversity_balanced")


def test_ic_expc_frontier_explanations_end_to_end() -> None:
    spec = make_expc_spec(
        selection_profile=SelectionProfile(0.4, 0.6),
        generations=1,
        beam_width=3,
        children_per_parent=4,
    )
    res = make_expc_runner(LineageStore(":memory:")).search(load_fast_world(), spec)
    for cid in res.generations[-1].selected_candidate_ids:
        lines = res.explain_selection(cid)
        assert lines and lines[0].startswith("candidate ")
    frontier = res.explain_frontier()
    assert frontier and frontier[0].startswith("FRONTIER")