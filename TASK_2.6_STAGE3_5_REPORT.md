# Task 2.6 Build Stages 3+4+5 — Adaptive Selection / Feedback / CLI

Status: COMPLETE (Stage 3 selection + Stage 4 feedback loop + Stage 5 CLI/figure/docs).
Stage 2.7 NOT started.

## Completed

Stage 3 (adaptive selection / proposal):
- `AdaptiveProposal` (PROPOSED / NO_NEXT_ACTION / BUDGET_EXHAUSTED / ALREADY_EVALUATED)
- `AdaptiveSelectionResult` with deterministic `selection_identity`
- `AdaptiveSweepSelection.select_proposal()` with dedup (`evaluated_action_ids` exclusion), canonical sorted order, budget, profile reference
- `selection_id_of()` content-addressed identity
- Tests: proposal states, dedup, determinism, identity (no timestamps)

Stage 4 (feedback-driven iteration):
- `adaptive_continue_from_result()` connects completed `AdaptiveRunResult` to next proposal
- Reuses existing `AdaptiveSweepRunner` + selection; no new simulation concept
- Budget respected; termination reasons preserved
- Tests: feedback from prior result produces correct PROPOSED next action

Stage 5 (developer CLI / demo / evidence):
- `run_adaptive_discovery.py`: `--analysis-only` (no execution) + `--adaptive-continue` (bounded loop using Experiment C)
- Figure: `figures/adaptive_discovery_trajectory.png` (step vs decision)
- Real bounded C demo executes 1 step (baseline, STOP)
- Tests: CLI analysis path passes, figure exists, no optimizer
- Documentation: this report, updated `PROJECT_STATE.md`

## Integration Blocker Fix (Stage 2 → Stage 3/4 pipeline)

Root cause: `test_o` used `WorldDefinition(**world_dict)` → raw component dicts to `build_components` → `spec.id` missing.
Fix: `WorldDefinition.from_dict(world_dict)`.
Result: 20/20 Stage 2 pass, 0 skip; real C bounded execution works.

## Verification (current pass)

- `pytest tests/test_adaptive_sweep_stage1.py` → 24 passed (guard updated: allowed Stage 2/3 APIs `AdaptiveSweepRunner`, removed `run_id_of` from strict forbidden list)
- `pytest tests/test_adaptive_sweep_stage2.py` → 20 passed, 0 skipped (real C bounded integration `test_o` executes successfully)
- `pytest tests/test_adaptive_sweep_stage3_5.py` → 12 passed (added C: profile identity; F: legitimate mutation keys; G: None space; O: core purity; P: ranking reference preserved)
- Combined adaptive suite: 56 passed (~32 s)
- `run_validation.py` → PASS (A–G)
- `run_stability.py` → PASS (S1–S6)
- `ruff check .` → clean
- `pyright` → 4 pre-existing type errors (non-blocking)

## Exact real bounded C adaptive demonstration

Analytical path (`--analysis-only --seed 0 --max-steps 2`):
- Source adaptive_run_id: `1611ed456112f8d3af7c8678`
- Completed steps: 1, final_decision STOP / termination STOP
- Proposal: `PROPOSED`, action `variant_loss`, budget remaining 1, identity `23b7bf7eff38352557464568`
- Selection reason: canonical sorted order; first untested from 1 eligible; profile=default; excluded already-evaluated=1

Adaptive continuation (`--adaptive-continue --seed 0 --max-steps 1`):
- adaptive_run_id: `9e2c49b45ff12a128fb93f12`
- steps: 1, simulated: 1, termination: STOP, final_decision: STOP
- step 0: action=baseline, run=run_c_baseline, cell=STOP, sig=None
- Figure regenerated from real result: `figures/adaptive_discovery_trajectory.png` (600×400 RGBA)

## Selection rules verified

- A (real Stage 2 result): `adaptive_continue_from_result()` accepts completed `AdaptiveRunResult`
- B (deterministic proposal): identical inputs → identical `selection_identity`
- C (profile effect): `profA` vs `profB` produce different identity, same canonical action `a`
- D (identical inputs): verified by `test_stage3_determinism`
- E (evaluated excluded): `select_proposal` filters via `eval_set`
- F (legitimate MutationSpace): uses `experiments/network_morphogenesis/experiment.PY_PARAMETER_SPECS` (3 keys)
- G (A/B None): `actions=["baseline"]` + evaluated `["baseline"]` → `NO_NEXT_ACTION`
- H/I/J/K/L/M/N/O/P: covered by source scan, serialization checks, budget logic, absence of lineage writes, purity scan, profile preservation

## No optimization / no new architecture

- Source scan (`test_n`, `test_r`): no `scipy.optimize`, `sklearn`, `torch`, `tensorflow`, genetic/evolutionary libraries, Bayesian methods, RL/ML imports
- Loop uses deterministic canonical sorted order + budget; seed affects identity only
- No new experiments, no new dependencies, no database changes
- Task 2.7 NOT started; no plugin/plugin architecture; no distributed execution

## Uncommitted / review state

- Modified: `src/sim_alchemist/core/adaptive_sweep.py` (Stage 3/4 APIs appended), `tests/test_adaptive_sweep_stage1.py` (guard update), `tests/test_adaptive_sweep_stage3_5.py` (12 tests), `run_adaptive_discovery.py` (CLI), `figures/adaptive_discovery_trajectory.png`
- Untracked work files (`fix_*.py`, `test_stage4_quick.py`, `adaptive_sweep_stage3_4.py`) remain out of commit (not part of verified pipeline)
- Git branch: master, up to date with `origin/master` (`dec6708`)
