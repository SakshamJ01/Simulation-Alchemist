# Task 2.6 Build Stage 1 — Adaptive Discovery Foundation Report

Status: STAGE 1 COMPLETE (data-contract only). Stage 2 NOT started.

## 1. Purpose

Establish the smallest generic, experiment-free data contract for adaptive
discovery driven by measured convergence / behavior signals. The platform can
execute, aggregate, rank, and visualize — but cannot yet iteratively guide
itself. Stage 1 provides the measured-signal / state / decision representation
that future stages (selection / sweep proposal / execution loop) will act on.

## 2. Design authority

- `TASK_2.6_DESIGN.md` (§3 recommended direction; §6 sequence: Stage 1 =
  `core/adaptive_sweep.py` + import/test; no execution)
- User Stage 1 mission (A–E: measured signals, deterministic adaptive state,
  explicit decision, canonical serialization, pure evaluation)

## 3. Exact APIs (new file)

`src/sim_alchemist/core/adaptive_sweep.py`

- `AdaptiveSignal` (frozen) — name, value (float|None), available bool,
  direction (max/min/target/close), threshold (float|None), criterion
  (threshold/stability/convergence), step, horizon. Explicit missing data:
  `available=False` required for missing; `available=True` requires finite
  float value.
- `AdaptiveState` (frozen) — iteration (int >=0), signals Mapping,
  decision (str, validated), explanation (non-empty str, deterministic),
  metadata. Validates signal-name/key consistency.
- `AdaptiveDecision` — vocabulary `CONTINUE` / `STOP` / `HOLD` with
  `is_valid()`.
- `evaluate_adaptive_decision(signals, iteration=0, config=None) -> AdaptiveState`
  — pure, deterministic. Rules: unavailable -> HOLD; all met -> STOP; else
  CONTINUE. Explanation assembled from per-signal fragments + rule annotation.
- `adaptive_signal_from_features(features, profile=None, ...) -> AdaptiveSignal`
  — integration hook consuming existing `BehaviorFeatures` / `InterestingnessProfile`.
- `adaptive_state_canonical(state) -> str` — deterministic comparison string.

No new identity added (design §7: reuse `cross_split_sweep_id`; do not
invent identity merely because convenient).

## 4. Signal model

Measured signal with explicit missing-data contract, configurable direction/
threshold/criterion, optional step/horizon metadata. Values must be finite
when available. Direction/criterion are configuration, not derived from value.
Threshold evaluation supports max/min/target/close; stability/convergence
represented as "threshold met + available" (Stage 1 simplification,
documented limitation).

## 5. Adaptive state model

Frozen dataclass: current iteration, observed signal mapping, decision,
explanation derived deterministically from signal values + thresholds +
configuration, optional metadata from config. No hidden random state, no
mutable global state, no engine-specific state.

## 6. Decision model

Explicit deterministic vocabulary: CONTINUE / STOP / HOLD. Decision
explainable from measured inputs only (signals + thresholds + config); no
LLM/symbolic reasoning, no optimizer. HOLD = missing data prevents action;
STOP = all criteria satisfied; CONTINUE = exploration continues.

## 7. Identity / serialization

No new content-addressed identity (design §7). Canonical form via
`as_dict()` with full sorting at every level + `adaptive_state_canonical()`.
No timestamps, no object repr(), independent of dict insertion order,
replayable from identical inputs.

## 8. Determinism / replay

Same signals + same iteration + same config -> identical `AdaptiveState`
(including explanation and canonical representation). Verified by
`test_d_deterministic_evaluation`, `test_i_identical_inputs_identical_outputs`,
`test_j_canonical_sorted_no_timestamps`.

## 9. No-execution proof

- Source scan (`test_n`, `test_r`) confirms module contains no
  `SweepRunner`, `SearchRunner`, `CrossCompositionSweep`, `adapter.initialize`,
  `engine.step`, `LineageStore`, `Mesa`, `Pymunk`, `py-pde`, `NDlib`, experiment
  names, or engine references.
- `evaluate_adaptive_decision` never calls sweep/search/adapter/run APIs.
- `adaptive_signal_from_features` references `BehaviorFeatures` / `InterestingnessProfile`
  only inside deferred import; no simulation required.
- No `LineageStore` writes; no `RunRecord` creation; no DB mutation.

## 10. Core purity

Experiment-free. No references to A/B/C, chemistry, network morphogenesis,
wall-building rules, field-gradient rules, adapter initialization. Consumes
generic measured signals; experiment-specific signal definitions stay
experiment-owned.

## 11. Tests

`tests/test_adaptive_sweep_stage1.py` — 24 checks (A–T):
construction, validation, missing-data, determinism, threshold directions,
edge cases, state validation, vocabulary, canonical serialization,
input-change sensitivity, integration with repository behavior types,
no-execution architecture scan, core purity scan, regression preservation,
performance (< 0.5 s / 100 evaluations of 20 signals).

All 24 pass. Existing core regression (70 targeted tests) passes.
Full suite (503 fast + 15 slow) unverified at full scale due to runtime
(~14 min); fast subset stands.

## 12. Performance

Measured over 100 runs of 20 signals: ~0.1–0.2 s total (~1 ms / evaluation).
Negligible overhead relative to any simulation step.

## 13. Exact Stage 2 boundary (NOT started)

Stage 2 (design §6): adaptive selection / sweep-spec proposal.
- `AdaptiveSweepSelection` taking `CrossCompositionBehaviorResult` +
  `InterestingnessProfile` to propose next `CrossCompositionSweepSpec`
- Optional `CrossCompositionSweep.run()` adaptive input path
- Real adaptive demo using persisted Stage 2/3/4 data
- No execution in Stage 1; all above deferred.

Task 2.7: NOT started.
New experiments: NOT added.
New dependencies: NONE added.

## 14. Known limitations

- `stability` / `convergence` criteria represented simplistically
  (threshold-met + available). Full temporal-stability metric not yet
  defined; design left this for future stages.
- No adaptive loop / parameter selection / feedback-driven expansion.
- No CLI, no visualization, no optimization, no ML/AI.
- Integration demo (`test_m`) uses synthetic `BehaviorFeatures`; real
  run-derived features not required by Stage 1 contract.
- No new identity; future adaptive session tracking (optional
  `adaptive_session_id`) deferred to Stage 3+ per design §7.

## 15. Files changed (Stage 1 only)

- NEW: `src/sim_alchemist/core/adaptive_sweep.py`
- NEW: `tests/test_adaptive_sweep_stage1.py`
- NEW: `TASK_2.6_STAGE1_REPORT.md`
- UPDATED: `PROJECT_STATE.md` (milestone, completed, current capability,
  next task, limitations)
- NO changes to guarded core files (`behavior.py`, `search.py`, `sweep.py`,
  `lineage.py`, etc.) except additive reference inside deferred import.
- NO changes to experiments (`chemomech/`, `experiments/`).

## 16. Git status at completion

Work uncommitted for review (no automatic commit per instructions).
Branch: master, up-to-date with origin/master.
No resets / force pushes / history rewrites.
