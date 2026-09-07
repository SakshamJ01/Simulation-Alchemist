# TASK 1.8 CHECKPOINT — Behavioral Characterization + Interestingness Engine

**State:** COMPLETE (report + regression done). This file is the compaction-safe
snapshot so any future session can resume Task 1.9 (or re-verify 1.8) from
PROJECT_STATE.md / AGENTS.md / this file alone without trusting stale context.

---

## What Task 1.8 added (all present, all green)

- `src/sim_alchemist/core/behavior.py` — NEW generic core module:
  `ObservableSeries` (validated, `resample_to` linear interp),
  `UnitFeatures`, `BehaviorFeatures` (flatten keys `"<obs>:<feature>"`,
  `as_dict/from_dict`), `BehaviorAnalyzer(late_window_fraction=0.3,
  dead_zone_rel=1e-6)`, `InterestingnessProfile` (weights + max/min
  directions), `rank_by_profile` (score = Σ weight·directional; min-max
  across population; ties by run_id asc — Task 1.7 rule), `Contribution` /
  `RankedRow.explanation()` ("favors/penalizes interest"),
  `BehaviorRankingResult`, `BehaviorTiming`, `BehaviorAnalysisRecord` /
  `BehaviorAnalysisResult`, `BehavioralAnalysisRunner`, `behavior_analysis_id_of`.
- `src/sim_alchemist/core/lineage.py` — MOD: `RunRecord.feature_snapshot`
  (nullable), `runs.feature_snapshot TEXT` column + `_migrate()` ALTER for
  pre-1.8 stores, new `behavior_analyses` table + `record/get/iter/
  behavior_analysis_count`, `_loads` helper.
- `src/sim_alchemist/core/__init__.py` — MOD: re-exports behavior API.
- `experiments/network_morphogenesis/experiment.py` — MOD:
  `build_network_observables(trajectory)` → 9 series on `t_field`
  (wall_count, wall_activity, wall_force, field_mean, field_std,
  network_load_mean, network_load_max, active_sources, growth_event).
- `run_behavior_demo.py` — NEW CLI (uses core runner only).
- `tests/test_behavior_analysis.py` — NEW, 18 tests (checks A–Q).
- `tests/test_mutation_lineage.py` — MOD: `test_l` scans behavior.py.
- `tests/test_field_guided_movers.py` + `test_network_morphogenesis.py` —
  MOD: CORE_COMMIT_HASHES re-baselined (added behavior.py, re-pinned
  `__init__.py` = 61ADB2A10B492C67492C56DECDA795466FE0C1C6A320C5160435524C2B2E34D2,
  `lineage.py` = 99657BC7B02E47EAF2205ED0EC181E3BFE03E6278D6004B50F3FDE385D22B5B4,
  `behavior.py` = 1FF90B5921532ADC9ED548EF1E69942D834057896E3BF40EE5332524F419CE16).
- Docs: `TASK_1.8_REPORT.md`, `TASK_1.8_CHECKPOINT.md` (this file),
  `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` all updated.

## Feature formulas (as implemented, canonical reference)

- temporal: `mean`, `std`(pop), `range`, `total_variation = Σ|Δx|`,
  `activity_rate = TV / max(range, 1e-12)`.
- trend: `trend_slope` (LS on τ in [0,1]), `residual_variance_fraction`
  (unexplained variance fraction, clamp [0,1]), `lag1_autocorr` (of the
  detrended residual).
- oscillation: `sign_change_rate` (direction flips of first differences,
  dead zone `dead_zone_rel·(range+1)`, /(n−1)),
  `oscillation_persistence = |lag1 autocorr of detrended residual|`,
  `oscillation_strength = sign_change_rate × oscillation_persistence`.
- stability: late window = last `ceil(fraction·n)`, ≥2 when n≥2; `late_window_std`,
  `late_window_slope`, `late_vs_full_variance_ratio = late_std²/std²`,
  `early_vs_late_divergence = |mean(late)−mean(early)| / max(std, 1e-12)`.
- divergence (variant resampled onto baseline times): `final_delta`, `rmsd`,
  `correlation`(Pearson; None when degenerate), `normalized_divergence =
  rmsd / max(std_baseline, 1e-12)`. Baseline's own divergence = None.

## Key numbers (real run, 160 steps)

- analysis_id `6307e8e16fd737f49822c877`; base world hash
  `0991944ddb9ef1c2fca1cc45febf87cf62b9a322a8fe6e7ddc41e869e5e89502`;
  base run `6b6d70c8e903116534cb9b9a`; loss sweep 0.05/0.08/0.11/0.14;
  planned=4, executed=3 (skipped 1 no-op), total=58.96s, mean=19.65s/run.
  Baseline ranked #1 (field oscillation + flat network-load-max); explanation
  verified in report §7. DB: `C:\Users\Saksham\AppData\Local\Temp\opencode\task18_expc.db`.

## Validation gate (Task 1.8 close)

- `uv run pytest` — 165 passed (162 fast + 3 slow, ~3 min).
- `uv run python run_validation.py` — A–G PASS. `uv run python run_stability.py` — S1–S6 PASS.
- `uv run python -m ruff check .` — CLEAN. `uv run pyright` — 0 errors.
- No new dependencies; stdlib-only analysis layer.

## What is NOT done / out of scope

- Experiments A/B observable adapters not exposed (only C). No ML/learned
  weights anywhere. Trajectories never persisted. No Task 1.9 work started.
- Guard re-baselining is the sanctioned extension path; the guard message now
  says "Task 1.8 must not change the core."

## Resume guidance (for Task 1.9)

Start ONLY with a fresh re-context: read PROJECT_STATE.md, AGENTS.md,
IMPLEMENTATION_PLAN.md, TASK_1.8_REPORT.md, then inspect `git status` /
`git log --oneline -10`. Do not trust this file's prose alone for code state.