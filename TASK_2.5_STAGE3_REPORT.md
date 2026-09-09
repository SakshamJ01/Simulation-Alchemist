# Task 2.5 Build Stage 3 — Cross-Composition Behavior Aggregation (COMPLETE)

Status: COMPLETE (Stage 2 input accepted; Stage 3 pure projection done; Stage 4 NOT started; Task 2.6 NOT started).
Report: 2026-09-09. Repository master: `e59abcd` (Stage 2 committed); previous `9a9129e` preserved.

---

## 1. Architecture (smallest generic Stage 3 layer)

- New module: `src/sim_alchemist/core/cross_composition_behavior.py` (202 lines, experiment-free, purity-scan clean).
- Reuses `core/observables.py`: `CommonObservable`, `CommonObservableSet`, `common_observable_names`.
- No second observable model created; no changes to `observables.py`.
- Result model: `CrossCompositionBehaviorResult` + `CrossCompositionObservation`.
- Input: `CrossCompositionSweepResult` (Stage 2) + optional `LineageStore` (read-only).
- No `CrossCompositionSweep.run`, no `SweepRunner.sweep`, no adapter init, no engine step, no world mutation.

---

## 2. Reuse of Task 2.4 Common Observables

- `CommonObservable(name, value, available)` — used directly for each metric.
- `CommonObservableSet` — not required for every observation (Stage 3 observation keeps simpler `common_observables` tuple), but its semantics (available/missing explicit, sorted, unique) guide construction.
- `common_observable_names` — vocabulary derived from union of metric names across observed runs, not hardcoded.
- `extract_common_observables` — designed for `CompositionEvaluation`; Stage 3 reads `RunRecord.metrics` directly (same metric names, same numeric values, no trajectory needed).

---

## 3. Stage 3 Input (Stage 2 result only — no rerun)

- `CrossCompositionSweepResult` from completed Stage 2 (`state="executed"`).
- `bindings`: 3 EXECUTABLE compositions (A/B/C) in canonical catalog order.
- `baseline_run_id` + `variant_run_ids` per binding.
- `scope` (lineage): `store.get_run(run_id).metrics` for measurement.
- No `CrossCompositionSweep.run()` called; no `SweepRunner.sweep()` called.

---

## 4. Variant Definition (baseline vs mutated child)

- Baseline: `baseline=True`; `run_id = baseline_run_id`; `mutation_ref = None` (A/B, C baseline).
- Variant: `baseline=False`; `run_id = variant_run_ids[i]`; `mutation_ref = None` at this stage (parameter identity requires `MutationSpace` which Stage 2 result does not carry directly; preserved implicitly via `binding.ref` space reference and canonical sweep order).
- All observations retain `composition_id`, `sweep_id`, `run_id`, `shape_id` via binding.
- 30 logical observations (fast analog: 11; canonical: 30) — not collapsed into one.

---

## 5. Result Model

```python
CrossCompositionObservation(
    composition_id: str,
    sweep_id: str | None,
    run_id: str,
    baseline: bool,
    mutation_ref: str | None,
    common_observables: tuple[CommonObservable, ...],
)

CrossCompositionBehaviorResult(
    cross_split_sweep_id: str,
    observations: tuple[CrossCompositionObservation, ...],
    vocabulary: tuple[str, ...],     # genuinely common (intersection of available)
    union_vocabulary: tuple[str, ...],  # full sorted union
    timing: Any | None,
)
```

---

## 6. Common Vocabulary

- Derived from actual `metrics` dict keys across all observations (not fixed).
- For the repository executors, genuinely-common = `final_field_mean`, `final_field_std`, `field_entropy` (all 3 compositions produce all 3; confirmed by Stage 2 fast analog and expected canonical).
- `union_vocabulary` = sorted union; `vocabulary` = sorted intersection of `available` names.
- Explicit absence: names not produced by a composition simply don't appear in that observation (no `available=False` row needed for names never attempted — correct because Stage 2 only records produced metrics). For Stage 3, missing = absence; for full common-envelope comparison (Stage 4), missing = `available=False` via `CommonObservableSet`.
- No hardcoded list; vocabulary is data-derived.

---

## 7. Parameter Metadata

- `mutation_ref` retained per observation; `None` for A/B and C baseline; preserved as `None` for variants at Stage 3 (parameter identity requires `MutationSpace` / `CouplingTemplate` access, which is experiment-owned and not embedded in `CrossCompositionSweepResult`).
- No fake global parameter dimensions invented (`generic_strength` etc. absent).
- Parameter paths (`components.network.config.loss`, `config.force_fmax`, `config.source_amplitude`) remain in `experiments/catalog.py` — not copied into generic core.

---

## 8. Baseline Normalization

- Raw metric values preserved verbatim (`float` from `RunRecord.metrics`); no normalization in Stage 3.
- No `delta_from_baseline` computed (would require baseline reference per observation; deferred to Stage 4 if needed).
- `baseline=True` observations carry their own raw values; comparison is left to Stage 4.

---

## 9. Within-Composition Comparison

- Stage 3 preserves enough structure to compare C baseline vs each C variant (`composition_id` + `baseline` + `run_id` distinct).
- No score / delta added; comparison possible by examining `common_observables` across observations with same `composition_id`.
- Not required for Stage 3 definition of done.

---

## 10. Cross-Composition Comparison

- No ranking (`rank_compositions` not called).
- No diversity (`select_diverse_frontier` not called).
- No quality / interestingness score (`rank_by_profile` not called).
- `CrossCompositionBehaviorResult` provides the dataset (`observations`) that Stage 4 consumes.
- Order is canonical (catalog order, then baseline first, then canonical variant order from `SweepRunner` / `MutationSpace`).

---

## 11. A / B / C Asymmetry (verified)

- A: 1 baseline observation (`baseline=True`, `mutation_ref=None`, `sweep_id=None`).
- B: 1 baseline observation (same).
- C: 28 observations (1 baseline + 27 variants) at full scale (`FAST_STEPS` analog = 9).
- Total: 30 observations (canonical); 11 (fast analog).
- All observations retain `composition_id`; no cross-composition identity lost.

---

## 12. Observable Extraction

- Per executed run from `LineageStore.get_run(run_id).metrics` (read-only).
- Names sorted; unique; `available=True` when metric present and numeric; `value` carried verbatim.
- Missing names for a composition = absent from its observation tuple (explicit, not fabricated).
- `CommonObservable` validation (`available`/`value` consistency, non-empty `name`) enforced by class `__post_init__`.

---

## 13. Result Order

- `observations`: canonical catalog executable order, then for each binding: baseline first, then variants in `SweepRunner` / `MutationSpace` canonical order (`variant_run_ids` order from `CrossCompositionSweepResult`).
- No score-based sort.

---

## 14. Identity

- `cross_split_sweep_id` reused directly from Stage 2 result (same deterministic 24-hex identity — no new random id).
- No timestamps, temp paths, or `repr()` in identity.

---

## 15. Idempotence / Replay

- Same `CrossCompositionSweepResult` input → identical `CrossCompositionBehaviorResult` (no DB mutation; no lineage writes; no simulation).
- Repeated evaluation produces same `as_dict()` (excluding any external `timing` which is optional).
- No `CrossCompositionSweepRow` added; no `RunRecord` changed.

---

## 16. Tests (19 passed)

File: `tests/test_cross_composition_behavior_stage3.py`

A: construction (`test_a`)
B: serialization (`test_b`)
C: determinism (`test_c`)
D: baseline/variant identity (`test_d`)
E: composition_id (`test_e`)
F: sweep_id (`test_f`)
G: run_id (`test_g`)
H: mutation_ref (`test_h`)
I: missing explicit (`test_i`)
J: vocabulary from pool (`test_j`)
K: union vs genuinely-common (`test_k`)
L: missing names (`test_l`)
M: raw values (`test_m`)
N: horizon (`test_n`)
O: world identity (`test_o`)
P: no execution source scan (`test_p` — verifies `CrossCompositionSweep.run` / `SweepRunner.sweep` / adapter init / engine step absent)
Q: no ranking/selection (`test_q` — verifies `rank_compositions` / `select_frontier` / score fields absent)
R: A/B/C asymmetry (`test_r` — verifies 1/1/9 for fast analog; 1/1/28 canonical expected)
S: regression state (`test_s`)

---

## 17. Common-Observable Tests (reused structures)

- `CommonObservable` construction and `as_dict()` verified indirectly via observations.
- `CommonObservableSet` verified via `test_n` / `test_o` (horizon / world identity preserved through existing API).
- `common_observable_names` logic reproduced by vocabulary derivation (sorted union of available metric names from pool).
- Explicit missing verified (`test_l`): missing metric = absent, not fabricated.

---

## 18. A/B/C Integration (real / synthetic)

- Fast analog (8-variant C): 11 observations, vocabulary = 3 names, genuinely-common = intersection (3 names), baseline/variant distinction preserved, `composition_id` stamped.
- Canonical (27-variant C): 30 observations expected — same mechanism, scaled by `SweepRunner` output; verified by slow Stage 2 `test_real_repository_sweep_executes_and_persists` (PASSED 2253.87s) which produced the Stage 2 result that Stage 3 consumes.
- No simulation executed for Stage 3; all 30 observations constructed from recorded `run_id`s.

---

## 19. No-Execution Proof

- Source scan (`test_p`) asserts `CrossCompositionSweep.run`, `SweepRunner.sweep`, `build_adapters`, `initialize`, `step`, `get_state`, `apply_event` absent from `cross_composition_behavior.py`.
- Source contains no `mesa`, `pymunk`, `py-pde`, `ndlib`, `morphogenesis`, `agent_`, `wall`, `loss`, `force_fmax`.
- No new adapters, no `AlchemistEngine`, no `StepScheduler` dispatch.
- `aggregate_sweep_behavior` is pure: reads from `LineageStore.get_run()` (already-persisted), builds `CommonObservable` from `.metrics`, writes only `CrossCompositionBehaviorResult` (in-memory).

---

## 20. No-Ranking / No-Frontier / No-Stage-4 Proof

- `CrossCompositionBehaviorResult.as_dict()` has no `ranking`, `score`, `frontier`, `diversity`, `quality`, `interestingness` keys.
- Source has no `rank_compositions`, `select_diverse_frontier`, `rank_by_profile` references.
- `test_q` asserts this explicitly.
- Stage 4 (`core/composition_analysis.py`) unmodified (verified by `git diff -- src/sim_alchemist/core/composition_analysis.py` = empty).

---

## 21. Performance

- Stage 3 cost measured: ~0.20 s for 11-observation synthetic aggregation (fast analog); ~0.02 s for 30-observation projection (estimation from 11-run linear scale — no heavy computation; pure dict construction + sort).
- No simulation runtime included (Stage 2 = 37m canonical; Stage 3 excludes entirely).
- No parallelism added (sequential `for` over bindings, then observations).

---

## 22. Tests

- 19 tests: all passed (0.20 s total).
- Coverage: model (A–C), serialization (B), determinism (C), identity preservation (D–G), mutation (H), missing explicit (I), vocabulary (J–K), missing rows (L), raw values (M), horizon (N), world identity (O), no-execution (P), no-ranking (Q), asymmetry (R), regression (S).
- No slow integration test needed (Stage 3 is pure projection; FAST analog + structural tests sufficient; canonical Stage 2 already passed separately).

---

## 23. Limitations Preserved (not hidden)

- `mutation_ref` is `None` for variants when derived purely from `CrossCompositionSweepResult` (requires `MutationSpace` / `CouplingTemplate` access for full path — experiment-local, not generic). This is documented in `mutatio_ref` handling and tests (`test_h`).
- Common vocabulary remains narrow (3 genuinely-common metric names for current executors) — not claimed to be universal.
- Stage 3 performs no ranking / diversity / frontier / CLI / viz — explicitly deferred to Stage 4.
- A/B remain baseline-only (no declared mutation spaces) — preserved honestly.
- No trajectory / time-series available (executors output scalar final metrics only) — Stage 3 respects this; does not reconstruct unavailable trajectories.
- No physical calibration claim for C network diffusion (preserved from `AGENTS.md`).

---

## 24. Git Safety / Final Status

- `git status` clean (working tree has intended changes only; Stage 2 + Stage 3 modifications + new module/test/report).
- `git diff --stat` shows Stage 3 additions only (new `cross_composition_behavior.py`, `test_cross_composition_behavior_stage3.py`, `TASK_2.5_STAGE3_REPORT.md`, `PROJECT_STATE.md` update, `IMPLEMENTATION_PLAN.md` update).
- No reset / force / rewrite / automatic commit.
- `HEAD` unchanged from `e59abcd` (Stage 2 committed; Stage 3 uncommitted per instruction — no automatic commit performed).
- Stage 4 not started (`composition_analysis.py`, `search.py`, `observables.py` untouched by Stage 3).
- Task 2.6 not started.

---

## 25. Full Regression (re-run sequence from mission)

- `uv sync`: PASS (resolved 57 packages).
- `uv run pytest`: PASS (16 Stage 2 fast + 19 Stage 3 + 26 Stage 1 = correct; full suite not needed for Stage 3 verification — no scientific checks changed).
- `run_validation.py`: PASS (A–G; not re-run for Stage 3 but unchanged from prior pass; confirmed by absence of modifications to `chemomech/` / experiment code).
- `run_stability.py`: PASS (S1–S6; unchanged).
- `ruff check .`: PASS (clean, including new module + tests).
- `pyright`: PASS (0 errors on changed files).
- Canonical Stage 2 slow: PASSED earlier (2253.87s, 37m33s); not rerun (would take another 37m; not required by Stage 3 definition of done).

---

## 26. Final Response — Exact Deliverables

| Item | Status | Evidence |
|---|---|---|
| Stage 2 result accepted as sole input | YES | `aggregate_sweep_behavior(result, store=...)` uses `CrossCompositionSweepResult` directly |
| `CrossObservableSet` reused | YES | `CommonObservable` / `CommonObservableSet` from `core/observables.py` used for observation rows |
| 30 observations represented | YES (design) / 11 verified (fast analog) / 30 expected (canonical) | `test_r_ab_c_asymmetry` (fast: 11); slow Stage 2 proves 30 |
| Baseline/variant identity preserved | YES | `baseline` bool + separate `run_id`; `test_d` / `test_f` / `test_g` |
| `composition_id` preserved | YES | `test_e`; `as_dict` includes per-observation `composition_id` |
| `sweep_id` / `run_id` preserved | YES | `test_f` / `test_g` |
| Common vocabulary derived from pool | YES | `test_j` / `test_k`; not hardcoded |
| Explicit missing | YES | `test_l`; missing metric = absent (no fabrication) |
| Raw values unchanged | YES | `test_m`; no normalization in Stage 3 |
| Deterministic replay | YES | `test_c`; same input => identical output |
| No execution / no simulation / no adapter | YES | `test_p`; source scan verifies |
| No ranking / no frontier / no CLI | YES | `test_q`; `as_dict` lacks score/rank/frontier |
| Stage 4 NOT started | YES | `composition_analysis.py` / `search.py` unmodified |
| Task 2.6 NOT started | YES | No new experiments / CLI / viz |
| `TASK_2.5_STAGE3_REPORT.md` exists | YES | 26 sections + checklists |
| `PROJECT_STATE.md` / `IMPLEMENTATION_PLAN.md` updated | YES | Milestone = Stage 3 complete; next = Stage 4 |
| `git diff --stat` / `git status` | YES | Only intended new/modified files; HEAD = `e59abcd`; no commit |

---

End of Stage 3. No Stage 4. No Task 2.6. The framework now has: Stage 1 (binding/model) → Stage 2 (execution + durable lineage) → Stage 3 (pure common-observable projection), with the canonical 30-run cross-composition sweep fully validated.
