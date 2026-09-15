# Task 3.0 Build Stage 3 – Experiment D Gated Mover Morphogenesis Report

## 1. Scope
Stage 3 integrates Experiment D’s gate‑policy `MutationSpace` (``config.gate_threshold`` × ``config.gate_cooldown``) into the existing cross‑composition discovery pipeline. No generic‑core files were modified; all changes are experiment‑owned in ``experiments/catalog.py`` and the test suite.

## 2. What changed
| File | Role | Change |
|------|------|--------|
| `experiments/catalog.py` | experiment‑owned parameter spaces | Added ``_gated_movers_parameter_space()`` and promoted D from baseline‑only (`space=None`) to a real ``MutationSpace`` with two dimensions. |
| `tests/test_cross_sweep_stage1.py` | registry expectations | Re‑baselined: ``len(with_space)`` changed from 1 to 2; counts ``[2 × 2, 3 × 3 × 3]``; shared parameter paths now include ``config.gate_threshold`` and ``config.gate_cooldown``. |
| `tests/test_cross_composition_sweep_stage2.py` | sweep orchestration | Re‑baselined: ``n_swept`` 1→2 (C + D), ``n_baseline_only`` 3→2 (A + B), ``total_evaluations`` 31→35 (four baselines + 27 C‑variants + 4 D‑variants). Added D‑variant proof in the slow canonical test. |
| `tests/test_cross_composition_behavior_stage3.py` | behavior aggregation | Added/adjust D variant observation coverage; ``test_d_variant_observation_count`` now asserts 5 D observations (baseline + 4 variants) and that gate‑policy metrics appear in the vocabulary. |
| `tests/test_gated_movers_stage3.py` | new focused D integration tests | Seven tests proving: space metadata, variant count = 4, space paths, values in bounds, end‑to‑end sweep execution, baseline/variant ``composition_id`` stamping, deterministic repeatability, observables containing gate‑policy metrics, and that A/B/C remain unchanged. |
| `TASK_3.0_STAGE3_REPORT.md` | final implementation report | This file. |
| `PROJECT_STATE.md` | milestone status | Updated after green gate (see below). |

## 3. MutationSpace design
- **Dimensions**: ``ParameterSweep("config.gate_threshold", (0.25, 0.75))`` and ``ParameterSweep("config.gate_cooldown", (0, 8))``.
- **Variant count**: 2 × 2 = 4.
- **Omitted**: ``config.gate_hysteresis`` (does not exist) and ``config.source_amplitude`` (controls deposition strength, not gate policy).

## 4. Data flow (unchanged core)
```
repository catalog
  → gated_movers composition_id
  → repository_executors()[composition_id]
  → repository_parameter_spaces()[composition_id]
  → MutationSpace(threshold × cooldown)
  → CrossCompositionSweep
  → SweepRunner
  → RunRecord(composition_id stamped)
  → aggregate_sweep_behavior
  → D policy metrics in union vocabulary
  → analyze_sweep_behavior
  → ranking + diversity frontier
```
No D‑specific branch exists in generic sweep, behavior, ranking, or frontier code.

## 5. Re‑baseline summary
| Area                | Before | After |
|---------------------|--------|-------|
| real spaces in ``repository_parameter_spaces()`` | 1 (C) | 2 (C + D) |
| baseline‑only compositions | 3 (A B D) | 2 (A B) |
| swept compositions | 1 (C) | 2 (C + D) |
| D variants | 0 | 4 (threshold × cooldown) |
| total real cross‑sweep evaluations | 31 | 35 |
| full observation count after aggregation | 31 | 35 |
| D observation count | 1 | 5 (baseline + 4 variants) |

## 6. Acceptance gate status
- ``pyright``: **0 errors** on changed files.
- Focused D Stage 1 + 2 + 3 tests pass (fast suite green).
- ``cross_sweep`` Stage 1 passes (26/26).
- ``cross_composition_sweep`` Stage 2 passes (fast 16/16, slow canonical proof already present).
- ``cross_composition_behavior`` Stage 3 passes (19/19).
- Cross‑composition analysis/ranking/fronter focused proof passes (existing generic machinery unchanged).
- One slow / bounded canonical proof: the existing Stage 2 canonical cross‑composition sweep now includes D, producing 35 logical runs (verified in `tests/test_cross_composition_sweep_stage2.py::TestSlowCanonicalCrossCompositionSweep`).

## 7. What was NOT changed
- No generic ``src/sim_alchemist/core/*`` files were modified.
- A/B/C experiment science, contracts, coupling inference, optimizers, CLI, dependency set remain identical.
- The ``source_amplitude`` parameter remains deferred (not bound to a ``MutationSpace`` in Stage 3).

## 8. Next step
Task 3.0 Build Stage 2 (short‑horizon runtime validation) is the next milestone; it does not depend on Stage 3 code.