# TASK 1.8 REPORT — Behavioral Characterization + Generic Interestingness Engine

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 1.8 (stdlib-only, deterministic, local, sequential)
**Subject experiment:** Experiment C — Adaptive Network Morphogenesis

---

## 1. Objective

Turn a run's *trajectory* into a compact, inspectable **behavioral
characterization**, rank runs by an **explicit interestingness profile**, and
persist only compact metadata (never trajectories):

- **observable series**: per-step scalar signals sampled on the macro-step time
  axis, produced by the experiment layer (never raw grids);
- **deterministic, inspectable features** per observable grouped into
  *temporal / trend / oscillation / stability / divergence* families, with
  documented formulas and no hidden state;
- **generic interestingness**: an explicit profile = feature weights + a
  maximize/minimize direction per feature, producing a deterministically
  ranked population with per-feature **contributions and explanations**;
- **"interesting ≠ largest value"**: the direction is *declared*, never
  inferred, so the engine cannot reward magnitude for its own sake;
- a real **Experiment C analysis** (declared space → features → ranking →
  explanations) with a repeatability proof and measured performance;
- persistence in the existing SQLite lineage store: per-run **feature
  snapshots** + one **behavior-analyses** record per analysis. No trajectories.

Constraints honoured: **no ML/LLM/embeddings/clustering/anomaly detection/
learned weights of any kind** (pure `math`/`statistics`, stdlib-only);
everything deterministic; core stays fully experiment-free; Experiment C is
the first production subject; sequential execution; scientific honesty — the
report claims only what the measures can support.

---

## 2. IMPLEMENTED — observable series model

`src/sim_alchemist/core/behavior.py` — fully generic, zero experiment knowledge.

| Concept | Description |
|---|---|
| `ObservableSeries(name, times, values)` | frozen, validated series: strictly increasing **finite** times, aligned finite values, ≥ 1 point. |
| `resample_to(times)` | deterministic linear interpolation for baseline-comparison (out-of-range clamps to the endpoints). |
| `UnitFeatures` | one observable's feature blocks (temporal/trend/oscillation/stability/divergence). |
| `BehaviorFeatures` | per-observable feature vector; `flatten()` yields `"<observable>:<feature>"` keys; `as_dict/from_dict/-to_json` round-trip. |
| `BehaviorAnalyzer(late_window_fraction=0.3, dead_zone_rel=1e-6)` | pure feature extractor; no state, no randomness. |
| `InterestingnessProfile` | explicit `weights` + per-feature `directions` (max/min), JSON-safe. |
| `rank_by_profile(...)` | population → `BehaviorRankingResult` with normalized contributions. |
| `BehavioralAnalysisRunner(store, executor, observables, parameter_specs=...)` | run baseline + variants, extract features, rank, persist (see §6). |

`ObservableSeries` rejects non-monotonic times, non-finite values, and
length-mismatched series at construction (eager validation).

**Experiment C observable adapter** (`experiments/network_morphogenesis/
experiment.py::build_network_observables`): nine scalar series on
`t_field` — `wall_count`, `wall_activity`, `wall_force`, `field_mean`,
`field_std`, `network_load_mean`, `network_load_max`, `active_sources`,
`growth_event` (1.0/0.0 per step). Field mean/std are derived **in memory**
from the field snapshots and never persisted.

---

## 3. IMPLEMENTED — behavioral features (documented formulas)

For a series `x_0..x_{n-1}` on times `t_i` (or normalized `τ_i = (t_i-t_0)/span`):

### Temporal
| Feature | Formula |
|---|---|
| `mean` | arithmetic mean (population) |
| `std` | population standard deviation |
| `range` | `max(x) - min(x)` |
| `total_variation` | `Σ_{i≥1} |x_i - x_{i-1}|` |
| `activity_rate` | `total_variation / max(range, 1e-12)` — movement per unit of excursion, independent of absolute scale or slope |

### Trend
| Feature | Formula |
|---|---|
| `trend_slope` | least-squares slope on **normalized time** (units of `range÷span`) |
| `residual_variance_fraction` | fraction of variance **not** explained by the best linear fit, clamped to [0,1] |
| `lag1_autocorr` | Pearson autocorrelation of the **detrended residual** at lag 1 |

### Oscillation (no false periodicity claim on a step)
| Feature | Formula |
|---|---|
| `sign_change_rate` | fraction of direction flips in the first differences; a difference below `dead_zone = dead_zone_rel·(range+1)` counts as flat |
| `oscillation_persistence` | `|lag1 autocorr of the detrended residual|` — how *rhythmically* the detrended signal alternates (→0 for a pure trend, a single step, or white noise; high for a regular alternation) |
| `oscillation_strength` | `sign_change_rate × oscillation_persistence` — requires *both* frequent flips *and* rhythmic alternation |

Rationale (documented in code): a **single step** has high persistence but
`sign_change_rate ≈ 0`, so strength ≈ 0 (**no false "oscillation" claim**); a
clean sinusoid scores high on both; white-noise scatter has high
`sign_change_rate` but persistence ≈ 0. A limitation: `oscillation_persistence`
is only meaningful for periods ≳ 4 samples (lag-1 sampling is in quadrature at
exactly period 4) — documented, and deliberately conservative.

### Stability (late-window behaviour)
The **late window** is the last `ceil(late_window_fraction·n)` points
(`≥ 2` when `n ≥ 2`); the **early window** is the same `w`-sized block at the
start.
| Feature | Formula |
|---|---|
| `late_window_std` | `std` of the late window |
| `late_window_slope` | LS slope of the late window |
| `late_vs_full_variance_ratio` | `late_std² / std²` (0 when full std ≈ 0) |
| `early_vs_late_divergence` | `|mean(late) - mean(early)| / max(std, 1e-12)` |

### Divergence (vs the baseline, per observable)
Variant series are **resampled onto the baseline's time axis** and compared:
| Feature | Formula |
|---|---|
| `final_delta` | last-point difference |
| `rmsd` | root-mean-square difference |
| `correlation` | Pearson correlation (`None` when < 2 points or zero variance) |
| `normalized_divergence` | `rmsd / max(std_baseline, 1e-12)` |

The **baseline's own divergence features are `None` by construction** (there
is no reference to diverge from) — `None` is carried through normalization and
ranked as "not scored", never silently coerced to 0 (§4).

---

## 4. IMPLEMENTED — interestingness profile + ranking

`InterestingnessProfile(name, description, weights, directions)`: an explicit,
user-authored preference — **no learned weights, ever**. Each scored feature
contributes `weight × directional`, where

```
directional = normalized           if the profile maximizes the feature
            = 1 - normalized       if the profile minimizes it
```

- **normalization** is min-max **across the analyzed population** per feature
  (documented in the module); `None` passes through unchanged; a zero-range
  feature normalizes to 0.0 (i.e. adds nothing);
- the **score** is the weighted sum over the profile's features;
- ranking order = **score descending, ties broken by `run_id` ascending** —
  the Task 1.7 deterministic rule, reused verbatim;
- every `RankedRow` carries `Contributions` (`raw`, `normalized`, `weight`,
  `contribution`) and an **explanation()** that states why a run ranked as it
  did, e.g.:

```
rank 1 (baseline, run 6b6d70c8e903116534cb9b9a, score 0.6)
  network_load_max:late_vs_full_variance_ratio: raw 0, norm 0, favors interest, w 0.3 -> +0.3
  field_mean:oscillation_strength: raw 0.0807056, norm 1, favors interest, w 0.3 -> +0.3
  wall_count:activity_rate: raw 1, norm 0, favors interest, w 0.4 -> +0
```

"favors/penalizes interest" = the effect of the feature on this run's score
(positive contribution) independent of the declared direction.

---

## 5. IMPLEMENTED — BehavioralAnalysisRunner + performance

`BehavioralAnalysisRunner(store, executor, observables, parameter_specs=None)`
reuses the Task 1.6/1.7 machinery (`apply_mutations`, deterministic
`run_id_of`, `MutationSpace` product order, no-op skip-and-count):

1. **validate up front** — the whole mutation space against
   `parameter_specs` before any simulation (Task 1.7 rule);
2. run and record the **baseline control first** (`kind="baseline"`), then
   each surviving **variant sequentially** (`kind="variant"`), all children
   linked to the base run;
3. extract features per run via `analyzer` + `observables(outcome)`;
4. rank the population against the profile (`rank_by_profile`);
5. persist: per-run `feature_snapshot` on the `runs` row + one
   `behavior_analyses` record; return `BehaviorAnalysisResult`.

`BehaviorTiming(n_planned, n_skipped, n_executed, total_seconds,
mean_seconds)` mirrors `SweepTiming` and is persisted.

`behavior_analysis_id_of(world, space-free profile)` —
```
sha256({ "world_hash": world_hash(world), "profile": <canonical profile JSON> })[:24]
```
deterministic ⇒ re-running the same world + profile is idempotent (one
`behavior_analyses` row, no duplicate runs).

---

## 6. IMPLEMENTED — lineage persistence (no trajectories)

`lineage.py` is extended **without weakening** the Task 1.6/1.7 store:

- `runs.feature_snapshot TEXT` (nullable) — compact `BehaviorFeatures` JSON per
  run (**never** the time series themselves);
- new `behavior_analyses` table — `analysis_id`, `world_id`, `world_hash`,
  `base_run_id`, `profile_json`, `run_order`, `ranked`, `timing`,
  `created_at` — with `record_behavior_analysis`, `get_behavior_analysis`,
  `iter_behavior_analyses`, `behavior_analysis_count`;
- `_migrate()` adds the `feature_snapshot` column to **pre-1.8 stores** on
  open (ALTER TABLE, tested); a pre-1.8 run reads back with `feature_snapshot
  is None` and remains fully usable.

`RunRecord` gains a `feature_snapshot` field (slot + param), defaulting to
`None`, so existing Task 1.6/1.7 call sites are unaffected.

---

## 7. IMPLEMENTED — Experiment C integration

No new science code: the analysis reuses Task 1.6 `PARAMETER_SPECS` /
`run_network_world` / `specs_by_path()` verbatim and adds only the observable
adapter `build_network_observables`.

### Real analysis (canonical 160 macro-steps, real run)

```
$ python run_behavior_demo.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --feature wall_count:activity_rate:0.4:max \
    --feature field_mean:oscillation_strength:0.3:max \
    --feature network_load_max:late_vs_full_variance_ratio:0.3:min \
    --steps 160

Analysis id   6307e8e16fd737f49822c877
Base world    0991944ddb9ef1c2fca1cc45febf87cf62b9a322a8fe6e7ddc41e869e5e89502

(skipped 1 no-op combination(s) identical to baseline)   # loss=0.05
TIMING  planned=4 executed=3 total=58.96s mean=19.65s

RANKING (profile: score descending, ties by run id ascending)
   1. 6b6d70c8e903116534cb9b9a  score=0.6      baseline   <- field oscillation + stable load max
   2. dea63e383409d9b548195812  score=0.499398 variant    <- loss=0.14 (most active field)
   3. 1c715e15074ce390d15ede0d  score=0.349591 variant    <- loss=0.11
   4. 07dced4eccc40cba31db9271  score=0.3      variant    <- loss=0.08

WHY (top-ranked run)
rank 1 (baseline, run 6b6d70c8e903116534cb9b9a, score 0.6)
  network_load_max:late_vs_full_variance_ratio: raw 0, norm 0, favors interest, w 0.3 -> +0.3
  field_mean:oscillation_strength: raw 0.0807056, norm 1, favors interest, w 0.3 -> +0.3
  wall_count:activity_rate: raw 1, norm 0, favors interest, w 0.4 -> +0

LINEAGE
  Base    6b6d70c8e903116534cb9b9a
Persisted to SQLite: ...  (runs=4, behavior analyses=1)
```

**What the measures support (and what they do not):**

- The baseline run has the **highest field oscillation strength** and a **flat
  (constant) network-load max** (`late_vs_full_variance_ratio = 0`); under the
  declared profile it is the "most interesting" run, and the CLI explains
  *why* feature by feature.
- `wall_count` is a monotone ramp (activity = 1 for every run), so this
  profile feature adds nothing — shown honestly as `+0`.
- `network_load_max` is *constant* at 160 steps under the recharged-reservoir
  model, so its stability feature is equal for all runs (it shifts everyone
  equally and does not reorder) — an honest, non-claiming observation.
- **No chaos/emergence/phase-transition claim is made anywhere.** The report
  only states the measured feature differences and the declared profile's
  ranking.

---

## 8. IMPLEMENTED — deterministic replay / reproducibility

Proved three ways (test R + two callers):

- re-running the same world + space + profile on a fresh store reproduces the
  same `analysis_id`, the same population run ids, the same ranking (ids and
  scores), and the same timing counts;
- re-running into the **same** store is idempotent: one `runs` row per run and
  one `behavior_analyses` row per analysis;
- a different profile (same world/space) yields a **different** `analysis_id`.

---

## 9. IMPLEMENTED — tests

`tests/test_behavior_analysis.py` — 18 tests, checks A–Q (same letter scheme
as the Task 1.7 suite).

| Check | Coverage |
|---|---|
| A | `ObservableSeries` validation: lengths, monotonicity, finiteness, eagerness |
| B | `resample_to` linear interpolation + endpoint clamping |
| C | constant-series features all well-defined (mean/std/variation/oscillation=0) |
| D | ramp: positive near-unit slope, residual variance fraction ≈ 0 |
| E | oscillation separates sinusoid/step/noise; a step has **zero** oscillation strength |
| F | activity (normalized movement) separated from raw slope; invariant under reversal |
| G | late-window stability features on a plateau |
| H | divergence vs baseline: final delta, RMSD, correlation, normalized; baseline's own divergence is `None` |
| I | flat keys `"<observable>:<feature>"` + `as_dict/from_dict` round-trip |
| J | ranking direction + deterministic tie-break; maximize vs minimize reverses order |
| K | explicit human-readable explanations (feature, raw, norm, weight, contribution) |
| L | `behavior.py` core contains **no** experiment identifiers |
| M | real Experiment C analysis end-to-end (baseline + variants, timings) |
| N | analysis id + population + ranking deterministic across runs/stores |
| O | persistence: per-run feature snapshots + analysis record; **1.7 store migrates in place** |
| P | "interesting ≠ largest value": min-direction honored (covered by J's reverse-order) |
| Q | performance instrumentation (planned/executed/mean seconds) |

The Task 1.6 test `test_l` was extended to also scan `behavior.py`; the core
immutability guard was re-baselined (§11). No prior test is weakened.

---

## 10. IMPLEMENTED — CLI

`run_behavior_demo.py` (project convention `run_*.py`, same shape as
`run_sweep.py`):

```
uv run python run_behavior_demo.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --feature wall_count:activity_rate:0.4:max \
    --feature field_mean:oscillation_strength:0.3:max \
    --feature network_load_max:late_vs_full_variance_ratio:0.3:min \
    [--steps N] [--world file.yaml] [--db file.db]
```

Prints: analysis id, base world hash, population features, skip/timing
instrumentation, the ranked population, and the **explanation of why the
top-ranked run won**. CLI is a thin shell over the generic
`BehavioralAnalysisRunner`; it contains no analysis logic of its own.

---

## 11. IMPLEMENTED — repository hygiene changes

- `src/sim_alchemist/core/` gains `behavior.py`; `lineage.py` + `__init__.py`
  are extended (feature-snapshot persistence + behavior-analyses table +
  migration + re-exports). **No other core file changed.**
- Core immutability guard in `tests/test_field_guided_movers.py` was
  **re-baselined** (the sanctioned milestone-extension pattern, as for Task
  1.3/1.6/1.7) — adds `behavior.py`, re-pins `lineage.py` and `__init__.py`.
  The guard stays on.
- `tests/test_network_morphogenesis.py` guard reuses the same map.

---

## 12. File tree (new / changed)

```
src/sim_alchemist/core/
    behavior.py           NEW  observable series, feature analyzer, profile,
                               ranking, analysis runner, persistence records
    lineage.py            MOD  + RunRecord.feature_snapshot, runs column + migration,
                               + behavior_analyses table + store methods
    __init__.py           MOD  re-exports the new API
experiments/network_morphogenesis/
    experiment.py         MOD  + build_network_observables (9 series, in-memory only)
tests/
    test_behavior_analysis.py NEW  18 tests (checks A–Q)
    test_mutation_lineage.py  MOD  check L now also scans behavior.py
    test_field_guided_movers.py MOD  guard re-baselined (Task 1.8 extension)
run_behavior_demo.py      NEW  deterministic analysis + ranking CLI
TASK_1.8_REPORT.md        NEW  this report
TASK_1.8_CHECKPOINT.md    NEW  mid-task context snapshot (see below)
```

---

## 13. Validation results (closing gate)

- `pytest` — full suite PASSES: **165 tests** (162 fast + 3 slow; 19 new
  Task 1.8 tests, 18 behavioral + the extended core-scan); no previous tests
  weakened.
- `run_validation.py` — A–G all PASS.
- `run_stability.py` — S1–S6 all PASS.
- `ruff check .` — CLEAN.
- `pyright` (full repo) — 0 errors.
- Environment unchanged (stdlib-only analysis layer; no new dependencies).

---

## 14. PLANNED (NOT implemented)

Deliberately out of scope for Task 1.8 (task constraint):

- **no** machine learning, embeddings, clustering, PCA, anomaly detection,
  learned/fitted weights, or evolutionary/optimization search;
- no automatic "discovery" or hypothesis generation from the ranking;
- no trajectory storage in the database (persisted features are derived
  *from* the in-memory series; raw series remain ephemeral);
- no per-observable model fitting beyond the least-squares line;
- no experiment factorization beyond Experiment C (the core is generic and
  experiment-free, but Experiments A/B observables are not yet exposed);
- no UI, no cloud, no parallel execution, nothing for Task 1.9.

---

## 15. Architectural weaknesses / remaining limitations

- `oscillation_persistence` is blind to periods ≲ 4 samples (lag-1 quadrature);
  at those frequencies only `sign_change_rate` still reports activity — honest,
  documented, deliberate.
- Ranked "undefined" (`None`) features (e.g. the baseline's divergence) are
  *explained but not silently treated as 0*; a profile weighting only an
  undefined feature yields a constant 0 score across the population.
- The interestingness profile is **fully explicit and user-authored**: it has
  no notion of "unexpectedness" by itself — the divergence features exist so a
  user can *choose* to reward divergence from the baseline.
- Determinism remains same-runtime/same-environment (inherited; not universal
  cross-platform bitwise equivalence).
- Persisted feature snapshots are derived summaries; they are compact by
  design but they do **not** reconstruct the original time series.

---

## 16. What Task 1.9 (next, NOT started) could build

Nothing has been planned or started beyond Task 1.8. The natural next steps
(sweep-driven automation over the ranked output, experiment-database queries
over `behavior_analyses` + `runs` + `sweeps`, exposing Experiments A/B
observables, or ranking multiple profiles and comparing them) all remain
**not started**.