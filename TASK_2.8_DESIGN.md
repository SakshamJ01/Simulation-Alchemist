# Task 2.8 Design — Cross-Composition Adaptive Discovery Analysis (COMPLETED)

Status: COMPLETE (Stage 1 design + Stage 2 build + Stage 3 docs/verification).
Plan-only section completed previously; implementation begun after verified Stage 2.
Next task after this milestone: Task 2.9 (NOT started).

## 1. Verified Starting State
- Task 2.7 Stage 1 (spec/identity/subspace/filter) complete
- Task 2.7 Stage 2 (execution/CLI/replay) complete
- Task 2.7 Stage 3 (lineage/session/persistence) complete
- All 38 adaptive tests pass; validation A–G; stability S1–S6; ruff/pyright clean
- Only C has declared parameter space (3 params, 27 variants); A/B baseline-only
- 3 EXECUTABLE compositions; common-observable vocabulary = 3 genuinely common metrics (`final_field_mean`, `final_field_std`, `field_entropy`)
- Existing analysis layer (`composition_analysis.py`) provides `rank_compositions`, `select_frontier`, `CompositionAnalyst`, `CommonBehaviorFeatures`
- Existing behavioral distance (`behavior_distance`, `behavior_vector`) supports diversity comparison
- No plugin, no optimization, no ML, no distributed execution

## 2. Architecture Gap
Task 2.7 produces adaptive execution results (per-composition, bounded, deterministic, replayable) and durable session lineage. What is missing is a structured way to compare those adaptive results across compositions — using the existing common-observable vocabulary and diversity-aware selection — to understand how adaptive exploration behaves differently per composition / profile / subspace.

The gap is NOT execution (done) or persistence (done); it is comparative analysis of adaptive discovery outcomes.

## 3. Candidate Directions (evaluated)
A. Adaptive session comparative ranking + diversity frontier (chosen)
B. Temporal multi-pass divergence tracking over adaptive trajectory (deferred: needs more temporal-stability metrics not yet fully defined)
C. Interactive query / dashboard over adaptive lineage (deferred: pure tooling, lower scientific leverage)

Chosen: A — uses existing `CompositionAnalysis` / `behavior_distance` / `select_diverse_frontier`; smallest build; no new simulation; unlocks cross-comparison of adaptive results.

## 4. Scientific Justification
After 2.7, the framework can produce adaptive runs for C (and baseline-only for A/B). To evaluate whether adaptive exploration produces composition-specific behavior differences, we need to compare the resulting feature profiles. This is exploratory, not optimization: we compare observed outcomes, not claim universal best parameters.

## 5. Scientific Use Case
Compare adaptive exploration results across compositions (C vs A/B baseline) under the same profile, using common-observable feature vectors (existing vocabulary) and diversity-aware selection (`select_diverse_frontier`). Produces a comparative report + figure; no new experiment required.

## 6. Core vs Experiment Ownership
- Generic core (`core/adaptive_comparison.py`): `AdaptiveDiscoveryAnalyst` / `AdaptiveComparisonResult` / `compare_adaptive_discovery`; uses existing `behavior_distance`, `rank_compositions`, `select_diverse_frontier`; no experiment branches.
- Experiment-owned: execution results come from `run_network_world` / `build_network_metrics` (existing); analysis uses existing feature names; no new parameter semantics.
- CLI (`run_adaptive_comparison.py`): analysis-only; reads existing session/lineage or synthetic results; writes optional figure.
- Lineage: no new schema required (reuses existing session records; analysis is read-only over them).

## 7. Identity / Lineage
- No new content-addressed identity required (analysis is derived from existing `adaptive_exploration_id` and `run_id`).
- Analysis result can use a derived identity (`adaptive_comparison_id`) if persistence needed later, but Stage 1+2 uses in-memory only.
- No lineage writes (analysis-only).

## 8. Implementation (Stage 1 design + Stage 2 build + Stage 3 verification)
Task 2.8 Build Stage 1: `core/adaptive_comparison.py` design (completed in this session via implementation)
Task 2.8 Build Stage 2: implementation + tests + CLI + report + verification (completed in this session)
Task 2.8 Build Stage 3: documentation + final state + regression verification (completed in this session)

Actual implemented APIs:
- `core/adaptive_comparison.py`: `AdaptiveDiscoveryAnalyst` facade; `compare_adaptive_discovery`; `AdaptiveComparisonResult`; reuses `behavior_vector`, `behavior_distance`, `select_diverse_frontier`, `rank_compositions`.
- `tests/test_adaptive_comparison_stage2.py`: unit + replay + real-repo proof + purity + comparison
- `run_adaptive_comparison.py`: CLI (analysis-only over adaptive session / evaluation results)

## 9. Non-Goals
- No optimization / ML / GA / Bayesian
- No automatic parameter synthesis
- No new experiments
- No plugin / distributed
- No universal metric equivalence claims
- No trajectory persistence
- No new database schema

## 10. Verification Completed
- 5 new adaptive-comparison tests pass
- Full regression preserved (existing adaptive + validation + stability)
- Real repository proof: C adaptive session result compared across profile configurations
- Deterministic replay verified
- Core pure (no experiment imports in analysis module)
- No source/test/dependency/world corruption
- Uncommitted intended changes
