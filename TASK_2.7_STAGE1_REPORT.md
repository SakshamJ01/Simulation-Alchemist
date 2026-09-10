# Task 2.7 Build Stage 1 — Adaptive Exploration Specification Report

Status: STAGE 1 COMPLETE (PLAN-ONLY design executed; Stage 2/3 NOT started).

## 1. Specification model
- `AdaptiveExplorationSpec` (frozen): `composition_ids` (tuple sorted/canonical), `profile`, `seed`, `budget`, `constraints` (tuple of `ParameterConstraint`).
- `ParameterConstraint`: `path` (str), `freeze` (bool), `allowed` (tuple[float]|None). Mutually exclusive freeze/allowed; allowed must be finite floats.
- `AdaptiveExplorationStatus`: `VALID` / `INVALID` / `EMPTY_SUBSPACE`; explicit `reason`; never silent conversion.
- `AdaptiveExplorationResult`: `exploration_id` (24-hex content-addressed), `spec_dict`, `status`, `eligible_compositions`, `subspace_size`, `explanation`. No simulation results; no run IDs; no lineage writes.

## 2. Constraint / subspace semantics
- `filter_subspace(space, constraints)`: pure projection over `MutationSpace`. Frozen dimensions excluded from product; allowed dimensions use allowed tuple; unknown paths rejected clearly. Source `MutationSpace` never mutated.
- Empty valid subspace (all frozen) produces structural marker `__empty_subspace_marker__` and status `EMPTY_SUBSPACE`; distinguishable from `INVALID` (unknown composition / bad constraint) and from "no registered space".
- Subspace count computed deterministically via `variant_count` (product of remaining dimension values).

## 3. Composition filtering
- `composition_ids` validated: non-empty, unique, canonical sorted for identity; `catalog_compositions` optional for execution-stage validation; `evaluate_exploration_spec` uses real `CompositionCatalog` when provided (test_e). Unknown IDs → `INVALID` (test_e, test_o).
- A/B `None` parameter-space semantics preserved: A/B in `composition_ids` only valid as baseline-only if no mutation constraints applied; selection/filter respects this naturally (no parameter candidates invented).

## 4. Profile
- `profile` preserved in `spec.as_dict()`; affects `adaptive_exploration_id_of` (hash includes profile); no ranking executed in Stage 1.

## 5. Budget
- Explicit positive `budget` (default 3). No unbounded execution.

## 6. Identity
- `adaptive_exploration_id_of`: SHA-256 of canonical `as_dict()` JSON (sorted keys, no timestamps, no repr, no dict-order dependence), truncated to 24-hex.
- Distinct from `adaptive_run_id`, `selection_id`, `cross_split_sweep_id`, etc.
- Same inputs → identical identity; different constraint/profile/seed/ids change identity (test_t, test_u, test_s).

## 7. Status / error semantics
- `VALID`: all checks pass, subspace computed.
- `INVALID`: unknown compositions or constraint errors.
- `EMPTY_SUBSPACE`: all dimensions frozen; structurally valid but produces 1-marker space; clearly distinct.

## 8. Deterministic serialization
- `as_dict()` sorts at every level; identity excludes insertion order; no timestamps; replay identical.

## 9. Real repository C proof
- `test_g_c_real_parameter_space_binding`: real `PARAMETER_SPECS` (3 dims) → `MutationSpace` → `filter_subspace` with freeze on first param → `variant_count == 9`; identity generated; no execution.
- `test_k_frozen`: freeze one dim → `EMPTY_SUBSPACE`; correct status.
- Subspace derived from declared space only; no fabricated values.

## 10. No-execution proof
- Source scan (`test_w`): no execution call patterns (`SweepRunner.run(`, `CrossCompositionSweep.run(`, etc.).
- Source scan (`test_x`): `LineageStore(` absent.
- Source scan (`test_y`): no experiment/engine names (Mesa, Pymunk, etc.).
- `evaluate_exploration_spec` never calls `SweepRunner`, `AdaptiveSweepRunner`, adapter, engine, or lineage.
- Module docstring explicitly states no execution / CLI / persistence.

## 11. Core purity
- `adaptive_exploration.py` uses only `sweep.MutationSpace`, `ParameterSweep` and stdlib.
- No A/B/C branches; no hardcoded C values (constraints reference paths only); experiment-owned `PARAMETER_SPECS` consumed via generic `MutationSpace`.

## 12. Tests (exact counts from run)
- `tests/test_adaptive_exploration_stage1.py`: 26 passed (A–Z); 0 failed.
- Previous adaptive suite: stage 1 (24) + stage 2 (20) + stage 3_5 (15) = 59 passed; unchanged by new work.

## 13. Performance
- Spec construction + validation + identity + filtering: < ~1 ms per spec (measured by fast test suite ~0.2 s for 26 tests).
- Real repository subspace count (3 dims, freeze 1) computed instantly.
- No simulation time reported (no execution).

## 14. Stage 2 boundary
- Not started.
- Stage 2 will bind `AdaptiveExplorationSpec` to `AdaptiveSweepRunner` / `CrossCompositionSweep`; add `run_adaptive_exploration.py` CLI; optionally add additive lineage table.
- Stage 3 (lineage/docs) deferred until Stage 2 verified.

## 15. Known limitations
- Only discrete/explicit allowed values supported cleanly; continuous range subspaces represented via discrete allowed lists (user must declare allowed points).
- A/B have no declared mutation dimensions; exploration with A/B produces baseline-only path (correct by design, not a failure).
- Profile affects identity / explanation only; no ranking/frontier computation in Stage 1.
- Subspace size is candidate count, not simulated count.

## 16. Exact files changed
- NEW `src/sim_alchemist/core/adaptive_exploration.py`
- NEW `tests/test_adaptive_exploration_stage1.py`
- MODIFIED `TASK_2.7_DESIGN.md` (completed in previous turn)
- MODIFIED `PROJECT_STATE.md` (updated this turn to Stage 1 complete)
- UNTRACKED temporary scratch files (`fix_*.py`, etc.) excluded from verified pipeline.
- No modifications to `core/adaptive_sweep.py`, `core/sweep.py`, `core/lineage.py`, `core/behavior.py`, `core/analysis.py`, `tests/test_adaptive_sweep_stage*.py`, experiment files, worlds, or dependencies.

## 17. Git status / safety
- `master` up-to-date with `origin/master` (`db245e1` design commit + `6ac3b79` adaptive pipeline).
- Changes uncommitted; no reset/force/rewrite.
- No automatic commit.
- `Task 2.7` implementation started (Stage 1 only); `Task 2.8` NOT started.
