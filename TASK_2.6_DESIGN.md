# Task 2.6 Design — Architecture Research / Design-Only (PLAN-ONLY)

Status: PLAN-ONLY. No source/test/dependency changes. No Task 2.7.
Verified starting state: Task 2.5 Stage 4+5 complete (adapter + CLI + figure + tests).

## 1. Verified Starting State
- Stage 2 committed (`e59abcd`): canonical 30-run PASSED 2253.87s; durable lineage (`lineage.py` `cross_composition_sweeps`); `composition_id` stamped.
- Stage 3 committed (`d33677f`): `core/cross_composition_behavior.py`; 19 tests; pure projection; 30 observations (A=1/B=1/C=28); vocabulary derived; no execution.
- Stage 4 adapter (uncommitted working tree): `core/cross_composition_analysis.py`; uses `rank_by_profile`, `select_diverse_frontier`, `CompositionRanking`, `CompositionFrontier`; 2 profiles verified.
- Stage 5 CLI + figure (uncommitted): `run_cross_composition_sweep.py`; `figures/cross_composition_sweep_quality_diversity.png`; deterministic CLI output.

## 2. Architecture Gap (from actual repo)

The platform can execute, aggregate, rank, and visualize — but cannot iteratively guide itself. After Phase 2 (ranking/frontier) the only remaining structural gap is adaptive selection based on prior results.

Shared limitation: only 3 EXECUTABLE, A/B baseline-only, C only swept, narrow vocabulary, profile-dependent ranking.

## 3. Recommended Direction: Adaptive / Iterative Discovery (C)

Smallest build that unlocks scientifically meaningful iteration without new experiments/engines.

Build `core/adaptive_sweep.py` (optional Stage 2.6 Build Stage 1):
- `AdaptiveSweepSelection`: takes `CrossCompositionBehaviorResult` + `InterestingnessProfile`; produces new `CrossCompositionSweepSpec` based on frontier/ranking/isolation.
- Optional extension to `CrossCompositionSweep.run()` with `adaptive_result=` for next pass.
- No new simulation concept; uses existing `SweepRunner`, `CompositionCatalog`, `MutationSpace`.
- Budget control via `max_variants` / `max_total_variants`.

## 4. Scientific Justification

Not claiming global optimization. Just: given completed baseline + 27 C variants + ranking + frontier, the system can deterministically propose what to evaluate next based on behavioral diversity and profile alignment. This is defensible exploration.

## 5. Non-Goals (must NOT build)

- No Bayesian / evolutionary / RL / ML.
- No plugin architecture.
- No automatic parameter semantic equivalence.
- No new composition generation.
- No distributed execution.
- No universal parameter model.

## 6. Implementation Sequence (Stage 2.6)

Stage 2.6 Build Stage 1 (smallest):
- `core/adaptive_sweep.py` (adaptation layer)
- Import/test (no execution)

Stage 2.6 Build Stage 2 (optional):
- `CrossCompositionSweep.run()` optional adaptive input
- `run_cross_composition_sweep.py` analysis-only path + optional new-pass path clearly separated

Stage 2.6 Build Stage 3 (optional):
- Real adaptive demo using persisted Stage 2/3/4 data
- Update docs/state

## 7. Identity / Lineage

No new identity required initially. Reuse `cross_split_sweep_id` per pass. If adaptive session tracking needed later, add optional `adaptive_session_id` to `CrossCompositionSweepRow` (additive, idempotent, backward-compatible).

## 8. Tests (design)
- Reuse `test_cross_composition_behavior_stage3.py` patterns.
- Add adaptive determinism/replay test.
- Add no-execution purity test.
- Add profile-A/B consistency test.

## 9. Success Criteria
- [x] Design references actual APIs (`CrossCompositionBehaviorResult`, `CompositionRanking`, `CompositionFrontier`, `CrossCompositionSweep`)
- [x] No source modified (only design doc + state)
- [x] No Task 2.6 implementation started
- [x] Task 2.5 Stages 4+5 verified complete
