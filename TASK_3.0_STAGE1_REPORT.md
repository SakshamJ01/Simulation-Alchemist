# Task 3.0 Build Stage 1 — Experiment D (Gated Mover Morphogenesis) Report

Status: STAGE 1 COMPLETE. Task 3.0 PLAN-ONLY design (`TASK_3.0_DESIGN.md`) executed;
Build Stage 2/3 NOT started.

## 1. Stage 1 scope (accepted exactly per design §34/§35)
`coupling.py` (template + contracts + schedule + world/registry builders) + gating
agent model + `GatedMesaAdapter` (Mesa sensing-layer override) + catalog/executor/
space-binding registration + ONE test file

`tests/test_gated_movers_stage1.py` asserting:
- (a) `{mesa, py-pde, pymunk/movers}` is classified **EXECUTABLE** through the
  repository catalog (converting the design's last `COUPLING_UNAVAILABLE` discovery
  target: catalog `{16,4,3}` = CAPABILITY_INVALID 16, COUPLING_UNAVAILABLE 4,
  EXECUTABLE 3 → **{16,3,4}** = CAPABILITY_INVALID 16, COUPLING_UNAVAILABLE 3,
  EXECUTABLE 4);
- (b) deterministic world/identity (`composition_id` content-addressed; generated
  world `ComponentSpec.variant` stamped per binding);
- (c) resolved coupling contracts (the declared `mover-gate` edge resolved against
  the pymunk/MoversAdapter with `consumer_capability="rigid_body"`; adapter-by-id +
  variant, never positional);
- (d) generic-core byte-identity guard (no pinned `CORE_COMMIT_HASHES`/hash touch —
  zero generic-core or guard changes this stage).

Stage 1 hard stops respected: no long simulations, no sweeps, no CLI. The only
runtime check is a FAST_STEPS=2 executor smoke test through the fast-catalog
shortcut; the long-resolution D baseline is exercised once by the (unmodified-in-
scope) slow regression gate — see §7.

## 2. Experiment D science (declared this stage, not yet validated)
Experiment B's movers deposit walls unconditionally (`deposition_events`). D adds a
Mesa sensing/decision layer that reads the morphogen field at each mover, applies a
per-mover gate with **hysteresis + cooldown**, and only then deposits/dissolves.
The coupling exposes 4 policy observables beyond B's (`deposition_events`,
`deposition_suppression`, `active_gates`, `gate_switch_rate`) — 8 metrics total:

`final_field_mean`, `final_field_std`, `field_entropy`, `n_movers`,
`total_displacement`, `mean_speed`, `mean_force`, `mean_gradient`,
`deposition_events`, `deposition_suppression`, `active_gates`, `gate_switch_rate`
(full metric dict from the real 160-step baseline, §7).

The gate science (regulated vs uncontrolled chemotaxis) is Task 3.0 Build Stage 2,
not claimed here.

## 3. Declared coupling contract + schedule
`build_gated_movers_template()` (`experiments/gated_movers/coupling.py`):

- components `{mesa, py-pde, pymunk/movers}` with adapters overridden on top of the
  core/default registries (B's movers adapter + py-pde + Mesa under the gated id,
  plus the default `pymunk/walls` not needed — 3-binding shape).
- contracts: `mover-gate` (`process_sync`, `consumer_capability="rigid_body"`,
  producer = gated Mesa intentions), plus the inherited `force_integration` /
  `field_sources` / `field_sensing` edges that B already declares.
- `GATED_MOVERS_SCHEDULE`: `field step → gating step (Mesa) → mover-gate sync →
  physics force/step → field source → record` (declared macro-step order resolved
  through the core `StepScheduler`).
- `executor_ref="experiments.gated_movers.model.run_gated_movers"`.

### 3.1 Deviation from design §10 (documented, not silent)
Design §10 proposed `consumer_capability="field_sources"` for the gate edge. The
pymunk/MoversAdapter does not expose `field_sources`; it exposes `rigid_body` (the
adapter that resolves `force_integration` and owns the movers). The gate contract
therefore declares `consumer_capability="rigid_body"`. This is the honest minimal
edge the adapters can resolve; leaving the `field_sources` spelling would have
failed `resolve_contracts` (contracts are never inferred or silently rewritten).

## 4. Repository registration
- `experiments/catalog.py::repository_templates()` includes `build_gated_movers_template()`.
- `repository_surfaces()` already produced the five-binding unified universe;
  D binds exactly `{mesa, py-pde, pymunk/movers}`.
- `repository_executors()` adds `run_gated_movers_world` keyed by
  `template_composition_id(build_gated_movers_template())` (conforming `Executor`).
- `build_repository_adapters()` dispatch extended for the gated Mesa adapter.
- `worlds/gated_movers.yaml` mirrors the template's `component_configs` (identical
  configs to keep generated worlds config-identical with the hand-authored world).

### 4.1 Correction of a prior plan claim (binding requirement)
The design deferred D's `repository_parameter_spaces()` entry to Stage 3. During
verification the cross-composition sweep layer (`_binding_for`) was found to
**require a binding entry for EVERY `catalog.executable()` composition**, raising
`CrossCompositionSweepError` for a missing key. So Stage 1 registers D's
**baseline-only** binding now (the same `space=None`/`ref=None` = "no registered
parameter sweep space" semantic that A/B use — Task 2.5 Stage 1, distinct from
error/empty). D's real `MutationSpace` remains deferred exactly as designed.

## 5. Agent model + adapter override
- `experiments/gated_movers/model.py`: `GatedMoversEngine` + Mesa `GatedMesaAdapter`
  (`engine_id="mesa"` under the composition's mesa component id; capability
  `agent_intentions` + `field_sensing` semantics through the D world's mesa config:
  per-mover gate state = field reading → hysteresis band + cooldown timer →
  gate on/off → intention). Scheduler disposal and adapter typing are explicit;
  B's pre-existing optional-scheduler pyright issue does not recur (assert + casts).
- `experiments/gated_movers/experiment.py`: `build_gated_movers_metrics` (8 metrics)
  + `run_gated_movers_world` executor mirroring the conforming contract of
  `run_field_guided_movers_world` (adapters rebuilt per call; reruns independently
  seeded from the world's own seed — deterministic).

## 6. Files landed
- NEW `experiments/gated_movers/{__init__,coupling,model,experiment}.py`
- NEW `worlds/gated_movers.yaml`
- NEW `tests/test_gated_movers_stage1.py` (4 tests)
- MODIFIED `experiments/catalog.py` (template + executor + adapters + D baseline-only
  space binding; docstring updated)
- MODIFIED `tests/test_templates.py` (D operations drift-guard; correct
  `(pde, movers, mesa, config, trajectory, state)` arg order)
- MODIFIED `run_composition_discovery.py` / `experiments/composition_discovery.py`
  / `run_catalog_demo.py` (import-order + 4-EXECUTABLE labels for the demos)
- MODIFIED (re-baselined, see §8) `tests/test_composition_search_stage2.py`,
  `tests/test_common_observables_stage3.py`,
  `tests/test_composition_analysis_stage4.py`,
  `tests/test_composition_discovery_cli_stage5.py`, `tests/test_cross_sweep_stage1.py`,
  `tests/test_cross_composition_sweep_stage2.py`
- NEW `TASK_3.0_STAGE1_REPORT.md` (this file); MODIFIED `PROJECT_STATE.md`

## 7. Verification
Fast suite (`uv run pytest tests/ -m "not slow"`):
**686 passed / 1 failed / 13 deselected**. The single failure is the documented
pre-existing historical `test_cross_composition_sweep_cli_stage5.py::
test_cli_parse_and_analysis_path` (CLI prints `ranking_ids:`/`frontier_members:`,
test asserts `ranking=`/`frontier=`) — untouched by Task 3.0, isolated per design §32,
NB-identical failure on pristine `HEAD` (verified in the Task 2.9 Stage 3 record and
re-confirmed here); never conflated with Task 3.0 failures.

Focused groups observed green:
- 41 = `test_gated_movers_stage1.py` (4) + `test_templates.py`
- 76 = `test_catalog.py` + `test_composition_search.py` + `test_cross_sweep_stage1.py`
- 98 = `test_composition_search_stage2.py` + `test_common_observables_stage3.py` +
  `test_composition_analysis_stage4.py` + `test_composition_discovery_cli_stage5.py`
- 70 = `test_cross_sweep_stage1/2` + `test_cross_composition_behavior_stage3.py` +
  `test_cross_composition_sweep_cli_stage5.py`

Slow suite (`uv run pytest tests/ -m slow`) — re-run in full this stage,
**13/13 PASSED** (durations on this machine):
- stage2 real search over repository catalog (4 evals + replay): 9m31s
- stage3 real search (4 evals + replay): 9m27s
- stage4 canonical analysis + frontiers: 5m01s
- stage5 canonical discovery figure: 5m08s
- real cross-composition sweep incl. D baseline (31 evaluations): 21m21s
- l_canonical A/B, executor-vs-facade ×2, network canonical, A/B/C bitwise: 3m46s
  (8 tests)

Real-machinery proof (§2's metric dicts, one clean process):
- A (morphogenesis) 89.9 s — 8 metrics
- **D (gated movers) 63.1 s — 8 metrics incl. the 4 new policy observables**
- B (field guided movers) 64.4 s — 8 metrics
- C (network) 85.4 s — 8 metrics

All four record root lineage runs (`parent_run_id=None`) with deterministic
`composition_id` stamps; re-evaluation idempotent; replay deterministic.

Static/type gate: `uv run python -m ruff check .` clean on every changed file;
`uv run pyright` 0 errors on changed files. The 9 `reportOptionalMemberAccess`
residuals in `tests/test_cross_composition_sweep_stage2.py` are pre-existing
Task 2.5-era typing (optional `timing`/`bindings` access in that file's own tests) —
none introduced here and none in any file Task 3.0 changed structurally.

Demo: `uv run python run_catalog_demo.py` renders the catalog with
`4 EXECUTABLE` (A, B, C, D) and the same 16 capability-invalid shapes.

## 8. Sanctioned re-baselines (§38-consistent, count-only, no guard/hash touch)
Files whose pins enumerate the executable/observable universe, updated exactly:
| File | old → new |
| --- | --- |
| `test_composition_search_stage2.py` | 3→4 EXECUTABLE; `invalid()==20`→19; class/test names now "FourExecutables" |
| `test_common_observables_stage3.py` | 3→4 evaluated; common names 16→20; `/3`→`/4`; `[EXECUTABLE]*4` |
| `test_composition_analysis_stage4.py` | 3→4 incl. frontier/beam/`[1,2,3,4]`; slow 4 |
| `test_composition_discovery_cli_stage5.py` | `"4 EXECUTABLE (A, B, C, D)"`, `"runs=4)"`, `["A","B","C","D"]` |
| `test_cross_sweep_stage1.py` | `len(spaces)==4` (documents baseline-only D binding) |
| `test_cross_composition_sweep_stage2.py` | `n_baseline_only==3` (A/B/D), `len(bindings)==4`, `total_evaluations==4+27`, `cross_composition_sweep_count==4`, slow same |

No guarded file (`src/sim_alchemist/core/*`) or experiment A/B/C file was modified;
no `CORE_COMMIT_HASHES` re-baseline.

## 9. Pitfalls caught during verification
1. **D binding in `repository_parameter_spaces()`** (see §4.1) — the sweep layer
   hard-requires a per-executable entry; without it the real sweep slow test and
   the stage-1 sweep tests raise `CrossCompositionSweepError`. Registered the
   baseline-only binding; corrected test expectations.
2. **Adapter typing** in `model.py`/`experiment.py` — pyright needs explicit
   `cast(...)` on the pymunk/MoversAdapter handle everywhere it is used (the
   registry returns a shallow adapter handle), and `assert self._scheduler is not None`
   before tracing (B's own optional-scheduler issue pre-dates Task 3.0 and was left
   untouched).
3. **`test_templates.py` drift-guard arg order** — the new D operations test first
   passed `(pde, mesa, movers, ...)`; the builder's signature is
   `(pde, movers, mesa, config, trajectory, state)`. Fixed; the guard now actually
   exercises the declared D operations.
4. **Slow-suite observation** — the real 160-step suite is genuinely long on this
   machine (~54 min in total); the real search tests run 4 evals + a 4-eval replay
   (~9.5 min each) and the real cross-composition sweep runs 31 evaluations
   (~21 min). Full 13/13 passed with unbuffered streaming confirms the earlier
   "hang" observations were output-buffering artifacts, not deadlocks.

## 10. Known limitations (preserved, not hidden)
- D's gating science is UNVALIDATED (no baseline-vs-gating-OFF control, no
  boundedness/replay claims) — explicitly Task 3.0 Build Stage 2.
- D's real `MutationSpace` (first legitimate non-C sweep space) is deferred to
  Task 3.0 Build Stage 3; Stage 1 registers only the baseline-only binding.
- The 9 pyright residuals in `test_cross_composition_sweep_stage2.py` and the
  pre-existing optional-scheduler error in B's `field_guided_movers/model.py` are
  legacy and untouched.
- Run durations above are this machine's real measurements; the pre-Task-3.0
  "~14 min full suite" figure was optimistic for the current suite (re-baselined
  discovery + sweep are ~50 min of slow alone).

## 11. Violations / audit trail
- No commit made. `master` unchanged (HEAD `ad8343c`); changes uncommitted.
- Scratch/untracked files (prior-session `fix_*.py`, `test_*.py`, `*.db` debris)
  left untouched per repository discipline.
- No new dependencies; A/B/C science bitwise-untouched (bitwise world-generation
  slow tests re-verified green); no generic-core changes; no CLI/sweep/figure added
  in Stage 1 scope; the demos' executable-label/import-order updates are
  presentation-only and covered by the stage5 CLI tests.

## 12. Next exact task
Task 3.0 Build Stage 2 (NOT started) — deterministic short-horizon D baseline +
gating-OFF control + boundedness/replay + metrics/series validation; scientific
claim limited to "regulated vs uncontrolled chemotaxis differ in a bounded,
deterministic way". Do not start until issued.

## 13. Post-stabilization gate update

This dated section supersedes only the provisional verification and audit wording
above; the Stage 1 scope and historical measurements remain unchanged.

- Commit `85a8581` (`feat: complete Task 3.0 Stage 1 and stabilize baseline`) is
  pushed to `origin/master`.
- Fast regression: `uv run pytest -m "not slow"` — 687 passed, 13 deselected.
- Slow regression: `uv run pytest -m slow` — 13 passed, 687 deselected.
- Combined applicable regression: 700 passed, 0 failed.
- Repository Pyright: 0 errors. Changed-file Ruff: clean.
- A–G, S1–S6, focused D structural tests, focused stabilization tests, CLI
  regression, and catalog smoke all pass.
- Task 3.0 Build Stage 2 remains not started. D gating science remains
  unvalidated until that stage.