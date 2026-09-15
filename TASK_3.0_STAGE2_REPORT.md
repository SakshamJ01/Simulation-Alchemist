# Task 3.0 Build Stage 2 - Experiment D Execution Validation Report

Status: STAGE 2 COMPLETE as a focused execution-validation layer. Stage 3 remains
removed/not started.

## 1. Stage 2 scope

Stage 2 validates Experiment D's short-horizon runtime behavior without adding
new source code, sweep plumbing, CLI behavior, figures, or generic-core changes.

The retained artifact is:

- `tests/test_gated_movers_stage2.py`

The test exercises the registered `{mesa, py-pde, pymunk/movers}` Experiment D
executor through the repository catalog and executor map. It builds a generated
`gated_movers` world, reduces it to a 12-step deterministic run, and verifies the
scientific claims permitted for Stage 2 only:

- the short baseline emits the complete Experiment D metric vocabulary and
  aligned trajectory series;
- gating ON differs from a gating-OFF control (`gate_threshold=0.0`);
- runs remain finite and bounded over the short horizon;
- same-world replay is bitwise identical within the same runtime.

## 2. What changed

Added one Stage 2 test file:

- `test_stage2_short_baseline_has_complete_metrics_and_series`
- `test_stage2_gating_on_differs_from_gating_off`
- `test_stage2_runs_are_bounded_and_finite`
- `test_stage2_replay_is_bitwise_identical`

No Experiment D source changes are required by Stage 2. No A/B/C experiment
files, generic core files, guarded hashes, dependencies, worlds, CLIs, or
discovery/sweep/reporting surfaces are changed by this report.

## 3. Validation details

The test asserts the exact Experiment D metrics:

- `final_field_mean`
- `final_field_std`
- `field_entropy`
- `n_movers`
- `total_displacement`
- `mean_speed`
- `mean_force`
- `mean_gradient`
- `deposition_events`
- `deposition_suppression`
- `active_gates`
- `gate_switch_rate`

The gating-OFF control is represented by `gate_threshold=0.0`. Under that control,
the test requires:

- `deposition_suppression == 0.0`
- `active_gates == n_movers`
- field snapshots remain non-negative

The gating-ON baseline requires `deposition_suppression > 0.0`, a different
metric dictionary from the control, and at least one differing recorded trajectory
array.

The boundedness test verifies finite field/speed/force/gradient series, mover
positions within `[0.0, 1.0]`, and gate-count observables within `[0, n_movers]`.
The replay test checks exact metric equality, exact trajectory-array equality, and
exact position-history equality across two runs of the same generated world.

## 4. Verification

Focused static gate:

```text
.\.venv\Scripts\pyright.exe tests/test_gated_movers_stage2.py
0 errors, 0 warnings, 0 informations
```

Focused runtime gate:

```text
.\.venv\Scripts\pytest.exe tests/test_gated_movers_stage1.py tests/test_gated_movers_stage2.py -q
8 passed in 13.91s
```

This covers the existing 4 Stage 1 structural tests plus the 4 new Stage 2
execution-validation tests.

## 5. Known limits

Stage 2 is deliberately short-horizon. It proves that the new gated composition
executes deterministically, differs from the uncontrolled gating-OFF control, and
stays bounded/finite in the focused validation window. It does not introduce a
real Experiment D mutation space, cross-composition sweep ranking, discovery
frontier changes, CLI output, or figure generation; those remain outside this
stage.

## 6. Audit notes

- Stage 3 artifacts are not present.
- The only current untracked implementation artifact is the retained Stage 2 test
  file.
- `PROJECT_STATE.md` was not updated by this report.
- No commit was made.
