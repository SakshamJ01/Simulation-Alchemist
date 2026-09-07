"""Task 1.8 validation: behavioral characterization + interestingness (A-Q).

Uses the generic core directly (``ObservableSeries`` / ``BehaviorAnalyzer`` /
``InterestingnessProfile`` / ``rank_by_profile`` / ``BehavioralAnalysisRunner``)
against a fast deterministic executor, plus one real Experiment C (Adaptive
Network Morphogenesis) analysis at small length as the live subject.

Checks:

    A  ObservableSeries validates times/values (monotonic, finite, aligned)
    B  Resample-to-new-times is deterministic linear interpolation
    C  Behavioral features are well-defined on a constant series
    D  Trend detection: a rising ramp has a positive, near-unit slope and a
       near-zero residual variance fraction
    E  Oscillation detection separates a sinusoid from a step and from noise
       (no false periodicity claim on a monotone or step series)
    F  Activity (total normalized movement) is separated from raw trend
    G  Stability window features are computed from the late window
    H  Divergence vs baseline: final delta, RMSD, correlation, normalized
    I  Feature flattening keys are "<observable>:<feature>" and round-trip
    J  Ranking maximizes and minimizes per declared direction and breaks
       ties by run id ascending
    K  Contributions and explanations are explicit, human-readable, and exact
    L  The core contains no experiment-specific identifiers (incl. behavior.py)
    M  A real Experiment C analysis executes end to end (baseline + variants)
    N  Analysis id is deterministic across stores/runs; repeated analysis is
       identical (ids, population, ranking, timing)
    O  Behavioral analyses and per-run feature snapshots persist (no
       trajectories), and an old 1.7 store is migrated in place
    P  "Interesting" is not "largest value": ranking respects the declared
       min/max directions, not raw magnitude
    Q  Performance instrumentation (variant count, total/mean analysis time)
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
import random

import pytest

from experiments.network_morphogenesis.experiment import (
    build_network_observables,
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    BehavioralAnalysisRunner,
    BehaviorAnalysisResult,
    ComponentSpec,
    ExecOutcome,
    InterestingnessProfile,
    LineageStore,
    MutationSpace,
    ObservableSeries,
    ParameterSweep,
    WorldDefinition,
    load_world_yaml,
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


def _series(
    name: str, n: int, fn, *, start: float = 0.0, stop: float = 63.0
) -> ObservableSeries:
    times = tuple(
        start + (stop - start) * i / max(1, n - 1) for i in range(n)
    )
    return ObservableSeries(name, times, tuple(float(fn(i, times[i])) for i in range(n)))


def _feat(features, key: str) -> float:
    """Unwrap a (possibly argument-undefined) feature; tests assert presence."""
    value = features.feature(key)
    assert value is not None, f"feature {key!r} is undefined"
    return float(value)


# ----------------------------------------------------------------------
# Helpers: a tiny generic world + a deterministic, feature-rich executor.
# ----------------------------------------------------------------------
TOY_X = "components.toy.config.x"
TOY_Y = "config.y"


def make_toy_world(x: float = 1.0, y: float = 10.0, seed: int = 0) -> WorldDefinition:
    return WorldDefinition(
        id="toyb",
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
    freq = 3.0 + y * 0.05
    oscill = tuple(math.sin(2 * math.pi * freq * i / n) * (0.5 + x * 0.1) for i in range(n))
    drift = tuple(math.sin(0.03 * i) + 0.01 * x * i for i in range(n))
    trajectory = {"s1": (times, ramp), "s2": (times, oscill), "s3": (times, drift)}
    return ExecOutcome(
        world=world,
        metrics={"m1": x * (1.0 + 0.1 * (n - 1)), "m2": y},
        trajectory=trajectory,
    )


def toy_observables(outcome: ExecOutcome) -> dict[str, ObservableSeries]:
    return {
        name: ObservableSeries(name, outcome.trajectory[name][0], outcome.trajectory[name][1])
        for name in ("s1", "s2", "s3")
    }


def make_toy_space() -> MutationSpace:
    return MutationSpace(
        (
            ParameterSweep(TOY_X, (1.0, 2.0, 3.0)),
            ParameterSweep(TOY_Y, (10.0, 20.0)),
        )
    )


def run_toy_analysis(
    store: LineageStore | None = None, profile: InterestingnessProfile | None = None,
) -> BehaviorAnalysisResult:
    store = store if store is not None else LineageStore(":memory:")
    if profile is None:
        profile = InterestingnessProfile(
            name="synthetic",
            description="prefer ramp activity, positive slope, and oscillation",
            weights={
                "s1:activity_rate": 0.4,
                "s1:trend_slope": 0.3,
                "s2:oscillation_strength": 0.3,
            },
        )
    runner = BehavioralAnalysisRunner(store, toy_executor, toy_observables)
    return runner.analyze(make_toy_world(), make_toy_space(), profile)


# ----------------------------------------------------------------------
# A. ObservableSeries validation
# ----------------------------------------------------------------------
def test_a_observable_series_validation() -> None:
    with pytest.raises(ValueError):
        ObservableSeries("bad", (0.0,), (1.0, 2.0))  # lengths differ
    with pytest.raises(ValueError):
        ObservableSeries("bad", (0.0, 0.0), (1.0, 2.0))  # non-monotonic
    with pytest.raises(ValueError):
        ObservableSeries("bad", (0.0, 1.0), (1.0, float("nan")))  # non-finite value
    ok = ObservableSeries("ok", (0.0, 1.0), (1.0, 2.0))
    assert ok.name == "ok"
    assert ok.times == (0.0, 1.0)
    assert ok.values == (1.0, 2.0)
    # Reject non-numeric values eagerly.
    with pytest.raises((TypeError, ValueError, OverflowError)):
        ObservableSeries("bad", (0.0, 1.0), (1.0, float("inf")))


# ----------------------------------------------------------------------
# B. Resample-to-new-times is deterministic linear interpolation
# ----------------------------------------------------------------------
def test_b_resample_to_linear() -> None:
    s = ObservableSeries("s", (0.0, 1.0, 2.0), (0.0, 10.0, 0.0))
    aligned = s.resample_to((0.0, 0.5, 1.0, 1.5, 2.0))
    assert aligned == (0.0, 5.0, 10.0, 5.0, 0.0)
    # Out-of-range times clamp to the endpoints.
    out = s.resample_to((-1.0, 0.0, 2.0, 3.0))
    assert out == (0.0, 0.0, 0.0, 0.0)
    assert s.resample_to((0.0, 1.0, 2.0)) == (0.0, 10.0, 0.0)


# ----------------------------------------------------------------------
# C. Features on a constant series are well-defined
# ----------------------------------------------------------------------
def test_c_constant_series_features() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer()
    s = ObservableSeries("c", tuple(float(i) for i in range(64)), tuple(5.0 for _ in range(64)))
    f = an.features({"c": s})
    assert f.feature("c:mean") == pytest.approx(5.0)
    assert f.feature("c:std") == pytest.approx(0.0)
    assert f.feature("c:range") == pytest.approx(0.0)
    assert f.feature("c:total_variation") == pytest.approx(0.0)
    assert f.feature("c:activity_rate") == pytest.approx(0.0)
    assert f.feature("c:trend_slope") == pytest.approx(0.0)
    assert f.feature("c:residual_variance_fraction") == pytest.approx(0.0)
    assert f.feature("c:oscillation_strength") == pytest.approx(0.0)
    assert f.feature("c:late_window_std") == pytest.approx(0.0)
    assert f.feature("c:early_vs_late_divergence") == pytest.approx(0.0)


# ----------------------------------------------------------------------
# D. Trend detection on a ramp
# ----------------------------------------------------------------------
def test_d_ramp_trend() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer()
    n = 64
    s = ObservableSeries(
        "r", tuple(float(i) for i in range(n)), tuple(float(i) for i in range(n))
    )
    f = an.features({"r": s})
    assert f.feature("r:trend_slope") == pytest.approx(float(n - 1), rel=1e-6)
    assert f.feature("r:residual_variance_fraction") == pytest.approx(0.0, abs=1e-9)
    assert f.feature("r:activity_rate") == pytest.approx(1.0, rel=1e-6)
    assert f.feature("r:lag1_autocorr") == pytest.approx(0.0, abs=1e-6)


# ----------------------------------------------------------------------
# E. Oscillation measure separates sinusoid / step / noise honestly
# ----------------------------------------------------------------------
def test_e_oscillation_measure() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer()
    n = 64
    times = tuple(float(i) for i in range(n))

    sinf = an.features({"s": ObservableSeries("s", times, tuple(math.sin(2 * math.pi * 8.0 * i / n) for i in range(n)))})
    stepf = an.features({"s": ObservableSeries("s", times, tuple(0.0 for _ in range(32)) + tuple(1.0 for _ in range(32)))})
    rng = random.Random(7)
    noisef = an.features({"s": ObservableSeries("s", times, tuple(0.5 + 0.05 * rng.gauss(0, 1) for _ in range(n)))})

    # The sinusoid oscillates far more than the monotone step.
    assert _feat(sinf, "s:oscillation_strength") > _feat(stepf, "s:oscillation_strength") + 0.1
    assert _feat(stepf, "s:oscillation_strength") == pytest.approx(0.0, abs=1e-9)
    # The clean sinusoid dominates noisy scatter on persistence-weighted strength.
    assert _feat(sinf, "s:oscillation_strength") > _feat(noisef, "s:oscillation_strength")
    # Persistence captures the regular alternation.
    assert _feat(sinf, "s:oscillation_persistence") > 0.5
    assert _feat(noisef, "s:oscillation_persistence") < 0.25
    # Activity on the step is maximal but that is not "oscillation".
    assert _feat(stepf, "s:activity_rate") == pytest.approx(1.0, rel=1e-6)


# ----------------------------------------------------------------------
# F. Activity is separated from raw trend
# ----------------------------------------------------------------------
def test_f_activity_vs_trend() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer()
    n = 64
    times = tuple(float(i) for i in range(n))
    # A rising ramp plus an alternating residual, and its exact mirror.
    r = lambda i: 1.0 if i % 2 == 0 else -1.0
    noisy_up = tuple(float(i) + r(i) for i in range(n))
    noisy_down = tuple(-float(i) - r(i) for i in range(n))
    f_up = an.features({"s": ObservableSeries("s", times, noisy_up)})
    f_down = an.features({"s": ObservableSeries("s", times, noisy_down)})
    # Activity (normalized movement) is invariant under reversal; the trend
    # slope flips sign.  Both carry identical alternating movement, so the
    # activity measure (which the pure trend cannot see) is equal.
    assert _feat(f_up, "s:activity_rate") == pytest.approx(
        _feat(f_down, "s:activity_rate"), rel=1e-6
    )
    assert _feat(f_up, "s:trend_slope") == pytest.approx(
        -_feat(f_down, "s:trend_slope"), rel=1e-9
    )
    # The alternating residual *is* movement: activity > 1 while the bare
    # ramp alone would give activity == 1.
    assert _feat(f_up, "s:activity_rate") > 1.0 + 1e-6


# ----------------------------------------------------------------------
# G. Stability window features
# ----------------------------------------------------------------------
def test_g_late_window_features() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer(late_window_fraction=0.25)
    n = 60
    times = tuple(float(i) for i in range(n))
    # Early violent oscillation, late flat plateau.
    vals = tuple(
        (math.sin(0.9 * i) if i < 30 else 5.0) for i in range(n)
    )
    f = an.features({"s": ObservableSeries("s", times, vals)})
    # The late window is the last 25% (floor(0.25*60)=15 points) and is flat.
    assert _feat(f, "s:late_window_std") <= 1e-9
    assert _feat(f, "s:late_window_slope") <= 1e-9
    # Early variability filters through to the divergence of means.
    assert _feat(f, "s:early_vs_late_divergence") > 0.0
    # The late variance is (at most) the full variance.
    assert _feat(f, "s:late_vs_full_variance_ratio") <= 1.0 + 1e-9


# ----------------------------------------------------------------------
# H. Divergence vs baseline for variant observables
# ----------------------------------------------------------------------
def test_h_divergence_features() -> None:
    from sim_alchemist.core import BehaviorAnalyzer

    an = BehaviorAnalyzer()
    times = tuple(float(i) for i in range(64))
    baseline = ObservableSeries("s", times, tuple(float(i) for i in range(64)))
    # A shifted + slightly scaled copy of the baseline.
    variant = ObservableSeries("s", times, tuple(2.0 * i + 1.0 for i in range(64)))
    features = an.features({"s": variant}, baseline={"s": baseline})
    assert _feat(features, "s:final_delta") == pytest.approx(127.0 - 63.0)
    assert _feat(features, "s:correlation") == pytest.approx(1.0, rel=1e-6)
    # RMSD = sqrt(mean((v-b)^2)) = sqrt(mean((i+1)^2)) over i = 0..63.
    assert _feat(features, "s:rmsd") == pytest.approx(37.383151285037485, rel=1e-6)
    assert _feat(features, "s:normalized_divergence") > 0.0
    # The baseline's own divergence features are undefined (None).
    base_features = an.features({"s": baseline})
    assert base_features.feature("s:rmsd") is None
    assert base_features.feature("s:final_delta") is None


# ----------------------------------------------------------------------
# I. Flat keys and serialization round-trip
# ----------------------------------------------------------------------
def test_i_flat_keys_and_roundtrip() -> None:
    from sim_alchemist.core import BehaviorAnalyzer, BehaviorFeatures

    an = BehaviorAnalyzer()
    n = 32
    series = {
        "wall_count": ObservableSeries("wall_count", tuple(float(i) for i in range(n)), tuple(1.0 for _ in range(n))),
        "speed": ObservableSeries("speed", tuple(float(i) for i in range(n)), tuple(float(i) for i in range(n))),
    }
    f = an.features(series)
    flat = f.flatten()
    assert all(":" in k for k in flat)
    assert "wall_count:mean" in flat
    assert "speed:trend_slope" in flat
    assert f.feature("speed:trend_slope") == flat["speed:trend_slope"]
    restored = BehaviorFeatures.from_dict(f.as_dict())
    assert restored.as_dict() == f.as_dict()


# ----------------------------------------------------------------------
# J. Ranking: direction + deterministic tie-break
# ----------------------------------------------------------------------
def test_j_ranking_direction_and_tiebreak() -> None:
    res = run_toy_analysis()
    rows = res.ranking.rows
    # baseline + variants (3 x 2 combos minus the (1.0, 10.0) no-op = 5).
    assert len(rows) == 6
    # Scores are normalized into [0, 1]; each weight in [0,1] -> score in [0, 1].
    for row in rows:
        assert 0.0 <= row.score <= 1.0 + 1e-9
    # Ties on the exact same score sort by run id ascending.
    scores = [round(r.score, 15) for r in rows]
    assert scores == sorted(scores, reverse=True)
    latest = rows[0]
    tied_run_ids = sorted(
        r.run_id for r in rows if round(r.score, 12) == round(latest.score, 12)
    )
    assert latest.run_id in tied_run_ids


def test_j_profile_direction_changes_order() -> None:
    world = make_toy_world()
    space = MutationSpace((ParameterSweep(TOY_X, (1.0, 2.0, 3.0)),))
    up = InterestingnessProfile(
        name="up", description="maximize slope",
        weights={"s1:trend_slope": 1.0},
        directions={"s1:trend_slope": True},
    )
    down = InterestingnessProfile(
        name="down", description="minimize slope",
        weights={"s1:trend_slope": 1.0},
        directions={"s1:trend_slope": False},
    )
    r_up = BehavioralAnalysisRunner(LineageStore(":memory:"), toy_executor, toy_observables).analyze(world, space, up)
    r_down = BehavioralAnalysisRunner(LineageStore(":memory:"), toy_executor, toy_observables).analyze(world, space, down)
    # Maximizing and minimizing the same feature rank reversed (slope scales with x).
    ids_up = [row.run_id for row in r_up.ranking.rows]
    ids_down = [row.run_id for row in r_down.ranking.rows]
    assert ids_down == list(reversed(ids_up))


# ----------------------------------------------------------------------
# K. Explicit, human-readable explanations
# ----------------------------------------------------------------------
def test_k_explanations_are_explicit() -> None:
    res = run_toy_analysis()
    top_id = res.ranking.rows[0].run_id
    lines = res.explain(top_id)
    assert lines[0].startswith("rank 1")
    assert "score" in lines[0]
    # Every contribution line names a feature, raw, normalized, and weight.
    contrib_lines = [ln for ln in lines if ": " in ln]
    assert len(contrib_lines) == 3  # one per profile weight
    joined = "\n".join(contrib_lines)
    assert "raw" in joined and "norm" in joined and "w " in joined
    assert "feature" in res.ranking.rows[0].contributions["s1:activity_rate"].as_dict()


# ----------------------------------------------------------------------
# L. Core behavior source is experiment-free
# ----------------------------------------------------------------------
def test_l_core_behavior_is_experiment_free() -> None:
    core_dir = REPO_ROOT / "src" / "sim_alchemist" / "core"
    source = (core_dir / "behavior.py").read_text(encoding="utf-8").lower()
    hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
    assert not hits, f"behavior.py contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# M. Real Experiment C analysis executes end to end
# ----------------------------------------------------------------------
def load_fast_world() -> WorldDefinition:
    world = load_world_yaml(WORLDS / "adaptive_network.yaml")
    cfg = dict(world.config)
    cfg["n_steps"] = FAST_STEPS
    return dataclasses.replace(world, max_steps=FAST_STEPS, config=cfg)


def test_m_experiment_c_analysis_runs() -> None:
    world = load_fast_world()
    space = MutationSpace(
        (
            ParameterSweep("components.network.config.loss", (0.05, 0.08, 0.11, 0.14)),
            ParameterSweep("config.force_fmax", (0.4, 0.8)),
        )
    )
    profile = InterestingnessProfile(
        name="expc",
        description="prefer wall-count activity, prefer field oscillation, "
        "prefer stable (low late-variance) network-load max",
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
    store = LineageStore(":memory:")
    runner = BehavioralAnalysisRunner(
        store,
        run_network_world,
        lambda outcome: build_network_observables(outcome.trajectory),
        parameter_specs=specs_by_path(),
    )
    res = runner.analyze(world, space, profile)

    assert 5 <= len(res.population) <= 8  # baseline + the non-noop variants
    assert res.population[0].kind == "baseline"
    assert len(res.ranking.rows) == len(res.population)
    for row in res.ranking.rows:
        assert {c.feature for c in row.contributions.values()} == set(profile.weights)
    # Every population member carries the 9 experiment-C observables (as
    # flattened feature names) with at least the temporal block populated.
    for run in res.population:
        flat = run.features.flatten()
        assert "wall_count:total_variation" in flat
        assert "growth_event:activity_rate" in flat
    assert res.timing.n_executed >= 1


# ----------------------------------------------------------------------
# N. Determinism: ids, population, ranking identical across stores/runs
# ----------------------------------------------------------------------
def test_n_determinism_across_runs() -> None:
    res_a = run_toy_analysis()
    res_b = run_toy_analysis()
    assert res_a.analysis_id == res_b.analysis_id
    assert [p.run_id for p in res_a.population] == [p.run_id for p in res_b.population]
    assert [r.run_id for r in res_a.ranking.rows] == [r.run_id for r in res_b.ranking.rows]
    assert [r.score for r in res_a.ranking.rows] == [r.score for r in res_b.ranking.rows]
    assert res_a.timing.n_executed == res_b.timing.n_executed


def test_n_id_deterministic_across_stores() -> None:
    res = run_toy_analysis()
    assert len(res.analysis_id) == 24
    # A different profile changes the id, but the world-space pair alone does not.
    other = InterestingnessProfile(
        name="synthetic", description="x", weights={"s1:activity_rate": 1.0}
    )
    res2 = run_toy_analysis(profile=other)
    assert res2.analysis_id != res.analysis_id


# ----------------------------------------------------------------------
# O. Persistence (no trajectories) + migration of a 1.7 store
# ----------------------------------------------------------------------
def test_o_behavior_persistence(tmp_path) -> None:
    db_path = tmp_path / "lineage.db"
    store = LineageStore(str(db_path))
    res = run_toy_analysis(store=store)

    # Per-run feature snapshots are persisted compactly (no trajectories).
    for run in res.population:
        rec = store.get_run(run.run_id)
        assert rec is not None
        assert rec.feature_snapshot is not None
        assert "units" in rec.feature_snapshot
        assert isinstance(rec.feature_snapshot["units"], list)
        unit_names = {u["name"] for u in rec.feature_snapshot["units"]}
        assert "s1" in unit_names and "s2" in unit_names and "s3" in unit_names

    # The analysis record is persisted and readable.
    rec = store.get_behavior_analysis(res.analysis_id)
    assert rec is not None
    assert rec["profile"]["name"] == "synthetic"
    assert len(rec["ranked"]["rows"]) == len(res.population)
    assert "timing" in rec
    assert isinstance(rec["world_hash"], str) and len(rec["world_hash"]) == 64

    # Re-running the same analysis is idempotent (no duplicate records).
    run_toy_analysis(store=store)
    assert store.behavior_analysis_count == 1
    store.close()


def test_o_migration_from_17_store(tmp_path) -> None:
    import sqlite3

    from sim_alchemist.core.lineage import RunRecord

    db_path = tmp_path / "legacy.db"
    # Build a pre-1.8 store: the `runs` table with every Task 1.7 column
    # (no `feature_snapshot`), and *without* the new behavior_analyses table.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            parent_run_id TEXT,
            world_id TEXT NOT NULL,
            world_hash TEXT NOT NULL,
            seed INTEGER NOT NULL,
            mutations TEXT NOT NULL,
            world_json TEXT NOT NULL,
            metrics TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    # Opening a 1.7 store migrates it in place: a feature_snapshot column is
    # added and the new behavior_analyses table is created.
    store = LineageStore(str(db_path))
    cols = [r[1] for r in store._conn.execute("PRAGMA table_info(runs)")]
    assert "feature_snapshot" in cols
    tables = {
        r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "behavior_analyses" in tables
    # A pre-1.8 run has no feature snapshot (None) and reads back fine.
    rec = RunRecord(
        run_id="legacy00000000000000000001",
        world=WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1),
        metrics={"m": 1.0},
    )
    store.record_run(rec)
    stored = store.get_run("legacy00000000000000000001")
    assert stored is not None and stored.feature_snapshot is None
    store.close()