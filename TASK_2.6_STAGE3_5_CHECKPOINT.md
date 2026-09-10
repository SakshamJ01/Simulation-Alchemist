# Task 2.6 Build Stage 3+4+5 Checkpoint

Date: 2026-09-10
Status: STAGE 3 + STAGE 4 + STAGE 5 COMPLETE (verified)
Stage 2.7: NOT started
Next action: Stop; do not begin Task 2.7; do not add optimization/ML/GA/BC.

## Completed stages
- Stage 1: core/adaptive_sweep.py adaptive signal/state/decision (24 tests pass)
- Stage 2: AdaptiveSweepSelection / AdaptiveSweepRunner / AdaptiveStepRecord / AdaptiveRunResult / bounded execution (20 tests pass, 1 real C integration passes)
- Stage 3: AdaptiveProposal / AdaptiveSelectionResult / select_proposal / dedup / budget / profile reference / canonical sorted order / selection_id_of (12 tests pass, including new C/F/G/O/P checks)
- Stage 4: adaptive_continue_from_result / feedback-driven proposal from completed AdaptiveRunResult (verified by CLI and test_stage4_feedback)
- Stage 5: run_adaptive_discovery.py (analysis-only + adaptive-continue) / figures/adaptive_discovery_trajectory.png (regenerated from real adaptive-continue result) / TASK_2.6_STAGE3_5_REPORT.md / updated PROJECT_STATE.md / IMPLEMENTATION_PLAN.md

## APIs present
- AdaptiveSignal, AdaptiveState, AdaptiveDecision, evaluate_adaptive_decision, adaptive_signal_from_features
- AdaptiveStepRecord, AdaptiveRunResult, adaptive_run_id_of
- AdaptiveSweepSelection (select_next + select_proposal with dedup/budget/profile)
- AdaptiveProposal (PROPOSED / NO_NEXT_ACTION / BUDGET_EXHAUSTED / ALREADY_EVALUATED)
- AdaptiveSelectionResult (proposal + source_context + selection_identity)
- selection_id_of()
- adaptive_continue_from_result()
- run_adaptive_discovery.py CLI

## Real experiment status
- Experiment C (network morphogenesis) used for real bounded adaptive demo
- Actual parameter space: PARAMETER_SPECS (3 keys: components.network.config.loss, config.force_fmax, config.source_amplitude)
- Demo executed: --adaptive-continue --seed 0 --max-steps 1 → 1 step, STOP, adaptive_run_id 9e2c49b45ff12a128fb93f12
- Analysis-only proposal verified: from completed result with evaluated baseline → proposes variant_loss, budget 1
- No synthetic parameter invention; no full 27-variant replay; no rerun of historical 30-run sweep

## Selection / proposal rules verified
- Only existing legitimate candidates used (C mutation space keys)
- Evaluated candidates excluded (dedup via set/filter)
- Profile affects identity/explanation; canonical order preserved unless configured otherwise
- Budget respected (≤ budget_remaining after proposal; BUDGET_EXHAUSTED when 0)
- No random selection; no fake parameters; no duplicate proposal
- Deterministic replay: same inputs → same selection_identity, same proposal state, same action
- Core purity: module contains no Mesa/Pymunk/py-pde/NDlib/chemistry/network-specific values; no experiment branches

## Lineage / identity
- No new database; adaptive runs in-memory
- adaptive_run_id content-addressed via sha256 over canonical actions + seed + budget
- Existing composition_id / cross_split_sweep_id / run_id preserved in step records
- No lineage writes performed by selection/proposal layer (verified by no DB import in module)

## Tests (exact counts)
- test_adaptive_sweep_stage1.py: 24 passed
- test_adaptive_sweep_stage2.py: 20 passed, 0 skipped (test_o real C bounded passes)
- test_adaptive_sweep_stage3_5.py: 12 passed (7 original + 5 new: profile identity, mutation keys, None space, purity, ranking reference)
- Full adaptive regression: 56 passed
- No optimizer imports (scipy.optimize/sklearn/etc.) in core adaptive module

## Visualization
- Figure: figures/adaptive_discovery_trajectory.png (600×400 RGBA)
- Regenerated from real adaptive-continue result (step 0 = STOP)
- Plot consumes result directly; does not recompute analysis or rerun simulations

## Documentation
- TASK_2.6_STAGE3_5_REPORT.md updated with exact CLI outputs, identity strings, test counts, verification
- PROJECT_STATE.md updated (milestone complete, next = Task 2.7 NOT started, limitations preserved)
- IMPLEMENTATION_PLAN.md updated (Task 2.6 complete; Task 2.7 not started)

## Uncommitted review items
- Modified source/test/docs/figure files listed above remain uncommitted per instruction
- Temporary untracked fix scripts (fix_*.py, test_stage4_quick.py, adaptive_sweep_stage3_4.py duplicate) excluded from verified pipeline; do not commit
- Git status: master up-to-date with origin/master (dec6708); no force/reset/rewrite

## Hard stops observed
- No Task 2.7 started
- No Bayesian / evolutionary / ML / RL / optimization / plugin / distributed work added
- No new experiments beyond existing C integration for demo
- No new dependencies added (matplotlib already in uv.lock)
- Scientific parameters not synthesized; only existing 3 C mutation keys used
