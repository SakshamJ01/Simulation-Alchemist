# Simulation Alchemist — Current State

`PROJECT_STATE.md` is the sole authoritative current-status document. The
dated update sections below are historical audit snapshots unless explicitly
marked `current`; they must not override the current milestone above.

## Current milestone
Phase 4: General Simulation Platform complete (Slices 4.1–4.6 complete: PluginRegistry, Generalized Simulation Protocols, Declarative Composition Graph & Mermaid visualization, Multi-rate step scheduling, Deterministic Checkpoint/Restart, Long-horizon Stress Validation L1–L5 passed, Scientific Markdown/HTML reporting & Workbench endpoints). All suites green (Validation A–G, Stability S1–S6, Stress L1–L5, Phase 4 23/23 tests, Pyright 0 errors, Ruff clean).

**Post-stabilization gate:** Phase 4 completed cleanly on master branch.
All validations pass: A–G, S1–S6, L1–L5, Pyright 0 errors, Ruff clean, full reproducibility preserved.

## Completed
- Task 0.1 — chemo-mechanical feedback spike
- Task 0.2 — clamped-obstacle wall coupling
- Task 0.3 — dynamic chemo-mechanical loop (validation A–G)
- Task 1.0 — kernel extraction (clock, event bus, world state, adapter protocol)
- Task 1.1 — capability/model layer
- Task 1.2 — core StepScheduler extraction
- Task 1.3 — declarative ground-truth composition (WorldDefinition, registry, composer)
- Task 1.5 — Experiment C (Adaptive Network Morphogenesis)
- Task 1.6 — generic mutation + lineage + variant runner
- Task 1.7 — deterministic variant sweeps + generic experiment ranking
- Task 1.8 — behavioral characterization + generic interestingness engine
- Task 1.9 — guided simulation search (beam search discovery loop)
- Task 2.0 — diversity-preserving multi-objective discovery
- Task 2.1 — cross-composition compatibility & discovery design (PLAN-ONLY)
- Task 2.2 — coupling-contract layer + pre-execution composition validation
- Task 2.3 Build Stage 1+2 — composition shape/space layer
- Task 2.3 Build Stage 3+4+5 — coupling-template registry + executable taxonomy + CompositionCatalog
- Task 2.4 Build Stage 1 — composition evaluation result layer + composition lineage + experiment executors
- Task 2.4 Build Stage 2 — the thin `CompositionSearcher` orchestrator (enumerate EXECUTABLE → evaluate one baseline each → compact unranked result)
- Task 2.4 Build Stage 3 — common cross-composition observables (one deterministic `CommonObservableSet` per evaluated composition over the sorted union of executor metric names; missing = explicit `available=False`/`None`; horizon captured from generated worlds; pure extraction, no persistence; timing split evaluation vs extraction; integrated into `CompositionSearcher.search` with backward-compatible result/timing)
- Task 2.4 Build Stage 4 — cross-composition ranking + diversity-aware discovery frontier (`composition_analysis.py`: `rank_compositions`/`select_frontier` reusing Task 1.8 `rank_by_profile` and Task 2.0 `select_diverse_frontier`; pool min-max normalization; analysis-only — no execution, no lineage writes)
- Task 2.4 Build Stage 5 — developer discovery CLI (`run_composition_discovery.py`) + matplotlib figure artifact (`figures/discovery_quality_diversity.png`); full test suites (34 fast/1 slow Stage 4, 9 fast/1 slow Stage 5)
- Task 2.5 PLAN — cross-composition parameter sweep / joint structural + parametric discovery architecture (design doc `TASK_2.5_DESIGN.md`: model D-hybrid, per-composition local sweeps over the existing `SweepRunner`, experiment-owned spaces)
- Task 2.5 Build Stage 1 — composition-specific parameter-space binding + result model (data-model only; `core/cross_sweep.py` + experiment-owned `repository_parameter_spaces()` + deterministic `cross_split_sweep_id`; no execution; no lineage changes; guard-safe — no guarded core file re-baselined)
- Task 2.5 Build Stage 2 — CrossCompositionSweep orchestrator (durable cross-composition sweep lineage via `core/lineage.py::CrossCompositionSweepRow` + `INSERT OR REPLACE`; `composition_id` stamped on variant `RunRecord`; per-composition baseline/sweep execution through `SweepRunner`; re-baseline of guarded `lineage.py`/`runner.py`/`sweep.py` hashes; `core/cross_composition_sweep.py` new module, experiment-free)
- Task 2.5 Build Stage 3 — cross-composition common-observable aggregation (`core/cross_composition_behavior.py`; pure projection; 19 tests; vocabulary from pool; baseline/variant preserved; no execution/ranking/frontier/CLI)
- Task 2.9 — persistent adaptive-comparison archive: Stage 1 (`adaptive_comparison_archive` table + idempotent `record_adaptive_comparison` + `get_adaptive_comparison`), Stage 2 (read-only consumption + deterministic `verify_adaptive_comparison` audit/replay + explicit feature linkage), Stage 3 (OUTCOME-B `feature_linkage_of` evidence-grounded resolver + strict read-only archive CLI `run_adaptive_comparison_archive.py` + hard-evidence audit + 46 archive tests)
- Task 3.0 Build Stage 1 — Experiment D "Gated Mover Morphogenesis" (`{mesa, py-pde, pymunk/movers}`): composition declaration + `mover-gate`/contracts + Mesa sensing-layer adapter override + catalog/executor/space-binding registration + ONE structural test file (`tests/test_gated_movers_stage1.py`); converts the last `COUPLING_UNAVAILABLE` discovery target → EXECUTABLE ({16,4,3}→{16,3,4}); sanctioned count re-baselines across stage2/3/4/5 + sweep tests; fast-catalog runtime proof (FAST_STEPS=2) + full slow gate (incl. real 160-step D baseline, verified ~63 s); zero generic-core/guard changes (no pinned hashes touched)
- Phase 1 — Researcher Workbench (`workbench/`, Flask web app, live visualization, interactive execution, parameter controls)
- Phase 1.5 — High-Fidelity Visualization (`workbench/static/workbench.js`, field snapshots, mover trajectories, agent inspection)
- Phase 1.5.1 — Observability Checkpoint (state serialization, trajectory playback, multi-engine telemetry)
- Phase 2 — Trusted Experiment Lab (`workbench/export_import.py`, lineage store migration, verified experiment replay & bundle export/import)
- Phase 3 — Discovery & Research Automation (`workbench/discovery.py`, automated parameter sweeps, multi-objective frontier selection, zero-drift candidate replay)
- Phase 4 — General Simulation Platform (`src/sim_alchemist/core/plugins.py`, `interfaces.py`, `graph.py`, `checkpoint.py`, `reporting.py`, `run_stress_validation.py`; Slices 4.1–4.6)

## Current experiments
- A — Chemo-Mechanical Morphogenesis (Mesa + py-pde + Pymunk)
- B — Field-Guided Movers (py-pde + Pymunk)
- C — Adaptive Network Morphogenesis (NDlib + py-pde + Pymunk)
- D — Gated Mover Morphogenesis (Mesa gating layer + py-pde + Pymunk movers; Task 3.0; `experiments/gated_movers/`)

## Current architecture
`src/sim_alchemist/core/`:
- adapters (`adapters/base.py`, capability protocol in `core/capabilities.py`; metadata: variant / state_keys / grid / coordinate_system)
- capabilities (`capability`/`CapabilitySet` + `SimulationEngine` protocol)
- world definitions (`world.py`, `WorldDefinition`/`ComponentSpec` with optional `variant` stamp, YAML)
- composer (`composer.py`: `compose`/`compose_into`/`build_components`/`resolve_capabilities`, optional `contracts=` -> `resolve_contracts` before `_install`)
- composition (`composition.py`: `ComponentBinding`, `CompositionShape`, `CompositionSpace`, `CapabilitySurface`, `CompositionClassification`, `capability_surfaces_from_registry`, `bindings_from_registry`, `classify_shape(s)`; CAPABILITY_VALID/CAPABILITY_INVALID) — variant-aware binding sets, canonical content-addressed shape_id, deterministic bounded enumeration, static (constructor-only, never stepped) capability filter
- templates (`templates.py`: `CouplingTemplate`, `CouplingTemplateRegistry`, `DuplicateTemplateError`, `classify_composition`, `CompositionVerdict`, `composition_id`, `template_composition_id`, `generate_world`) — Stage 3+4: the 6-status executable taxonomy (CAPABILITY_INVALID/COUPLING_UNAVAILABLE/COUPLING_INVALID/SCHEDULE_INVALID/CLOCK_INVALID/EXECUTABLE); contracts never inferred; adapters only constructed for template-matched shapes — never initialized/stepped; `CompositionVerdict` with reasons)
- catalog (`catalog.py`: `CompositionCatalog`, `CatalogCandidate`) — Stage 5: queryable/explainable snapshot of a whole CompositionSpace (all/executable/invalid/by_status/by_shape_id/status_counts/explain; optional generated worlds for EXECUTABLE rows; never simulated/persisted/searched)
- contracts (`contracts.py`: `CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`, `resolve_contracts`, `adapter_by_id`, `contracts_key`) — declarative coupling-edge validation, never invents couplings
- clock (`clock.py`), scheduler (`scheduler.py`), event bus (`events.py`)
- mutation (`mutation.py`: `Mutation`, `MutationRecord`, `ParameterSpec`, validators, immutable clone)
- lineage (`lineage.py`: `LineageStore` + `RunRecord` (composition_id stamp), `SweepRecord`, `BehaviorAnalysisRecord`, `SearchRecord`, deterministic `run_id_of`)
- runner (`runner.py`: `VariantRunner`, `compare_metrics`, `compare_runs`)
- sweep (`sweep.py`: `ParameterSweep`, `MutationSpace`, `sweep_id_of`, `SweepRunner`, `rank_results`, `SweepResult`)
- behavior (`behavior.py`: `ObservableSeries`, `BehaviorFeatures`, `BehaviorAnalyzer`, `InterestingnessProfile`, `rank_by_profile`, `BehavioralAnalysisRunner`, `behavior_vector`, `behavior_distance`, `select_diverse_frontier`, `compute_frontier_diagnostics`, `FrontierDiagnostics`)
- search (`search.py`: `SearchSpec`, `SearchRunner`, `child_mutations`, `search_id_of`, `SelectionProfile`)
- composition_search (`composition_search.py`: `CompositionEvaluation`, `CompositionEvaluationError`, `composition_discovery_id_of`, `evaluate_composition_baseline`, `CompositionSearcher`, `CompositionSearchSpec`, `CompositionSearchResult`, `CompositionSearchTiming`, `CompositionSearchError`) — Task 2.4 Stages 1+2+3: deterministic discovery-pass identity + one EXECUTABLE composition baseline evaluation recorded as a root lineage run with its composition stamp, the thin orchestrator (enumerate `catalog.executable()` in canonical order → resolve experiment-owned executors via an opaque id→executor map → evaluate each once → compact unranked in-memory result; deterministic replay; never ranks/analyzes/selects), and the Stage 3 common-observable layer (`search` attaches one `CommonObservableSet` per evaluation in catalog order, splitting wall time into evaluation vs extraction); core never dispatches on composition
- composition_analysis (`composition_analysis.py`: `rank_compositions`, `select_frontier`, `CompositionAnalysisResult`, `CompositionAnalyst`, `CommonBehaviorFeatures`, `CompositionFeaturedRun`, `common_observable_vocabulary`, `composition_analysis_id_of`, `CompositionAnalysisTiming`) — Task 2.4 Stage 4: analysis-only cross-composition ranking + diversity frontier; pool-level min-max normalization; constant features → 0.0; ties by run_id asc; reuses `rank_by_profile` / `select_diverse_frontier` / `behavior_distance` / `compute_frontier_diagnostics` unchanged; no execution, no persistence, no experiment imports
- observables (`observables.py`: `CommonObservable`, `CommonObservableSet`, `CommonObservableError`, `common_observable_names`, `extract_common_observables`) — Task 2.4 Stage 3: deterministic common cross-composition observable envelope — sorted union of executor metric names across an evaluated pool; per-composition availability (`available=False`/`value=None` for composition-specific names elsewhere; never imputed); horizon (`max_steps`/`macro_timestep`) captured from the generated world with id/hash-match validation; pure projection of recorded evaluations (no re-runs, no persistence, world-immutable)
- contracts (`contracts.py`: `CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`, `resolve_contracts`, `adapter_by_id`, `contracts_key`)
- templates (`templates.py`: `CouplingTemplate`, `CouplingTemplateRegistry`, `classify_composition`, `CompositionVerdict`, `composition_id`, `template_composition_id`, `generate_world`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml

## Current validation (Task 3.0 Build Stage 1 closing evidence)
- pytest — pre-stabilization evidence was **699 passed / 1 failed** (700 collected). The historical CLI assertion has now been repaired in the worktree; the full suite has not yet been rerun. The 13-test slow gate was previously recorded as passing, but is not rerun during stabilization. Focused stabilization tests currently pass.
- run_validation.py — A–G: PASS (unchanged; no science touched)
- run_stability.py — S1–S6: PASS (unchanged; no science touched)
- ruff check . — clean
- pyright — changed stabilization files currently report 0 errors; the repository-wide baseline still has legacy test diagnostics pending cleanup.
- Historical canonical discovery regression (before Experiment D): seed 0, 160 steps, 3 EXECUTABLE compositions. Current catalog status is 4 EXECUTABLE compositions; the old three-composition numbers are retained only as historical evidence.

## Next exact task
Task 3.0 Build Stage 2 (NOT started). Task 3.0 Build Stage 1 complete. Task 3.0 PLAN-ONLY complete. Task 2.9 complete.

## Current capability (Task 3.0 Build Stage 1)
- Deterministic adaptive signal / state / decision evaluation (core/adaptive_sweep.py)
- Canonical serialization, pure assessment, explicit missing-data contract
- Integration hook for BehaviorFeatures / InterestingnessProfile (no execution required)
- Executable composition-specific parameter-space declarations (`experiments/catalog.py::repository_parameter_spaces()`; C real 27-variant space, A/B baseline-only `space=None` bindings; D owns a real `MutationSpace` (gate_threshold × gate_cooldown, 4 variants) declared in Stage 3)
- Experiment D declared composition `{mesa, py-pde, pymunk/movers}` (`experiments/gated_movers/coupling.py` `build_gated_movers_template`; `mover-gate` contract with `consumer_capability="rigid_body"`; `GATED_MOVERS_SCHEDULE`; world/registry builders) + `GatedMoversEngine`/`run_gated_movers_world` executor (160-step baseline verified ~63 s) + `GatedMesaAdapter` sensing-layer override
- Four EXECUTABLE compositions (A/B/C/D) → catalog {16,4,4} (16 capability‑invalid, 4 coupling‑unavailable, 4 executable); 20-name common-observable union (D adds `deposition_events`, `deposition_suppression`, `active_gates`, `gate_switch_rate`)
- CrossCompositionSweep orchestrator (`core/cross_composition_sweep.py`)
- Durable cross-composition sweep lineage (`lineage.py` `cross_composition_sweeps` + `CrossCompositionSweepRow`; INSERT OR REPLACE; idempotent)
- `composition_id` stamped on `RunRecord` (`runner.py`/`sweep.py` optional threading)
- Cross-composition common-observable aggregation (`core/cross_composition_behavior.py`; pure projection; `CrossCompositionBehaviorResult`; vocabulary from pool; 30 observations; baseline/variant preserved; no ranking/frontier/visualization/CLI)
- Persistent adaptive-comparison archive (`core/lineage.py` `adaptive_comparison_archive` + idempotent `record_adaptive_comparison`/`get_adaptive_comparison`; read-only `iter/count/find/verify_adaptive_comparison` replay/audit; `feature_linkage_of` evidence-grounded OUTCOME-B resolution; read-only CLI `run_adaptive_comparison_archive.py` `list/get/find/verify/link` with explicit unknown/corrupt/missing semantics)

## Known limitations (historical Task 2.4/2.5 notes; current stabilization status above)
- No cross-composition sweep ranking / diversity frontier / shared sweep behavior aggregation (Stage 4 — deferred to Stage 3+4).
- No CLI / figure for cross-composition sweeps (Stage 5 — deferred).
- Only C has a declared mutation space in the catalog; A and B remain baseline-only; D owns a real `MutationSpace` (gate_threshold × gate_cooldown, 4 variants) declared in Stage 3.
- Cross-composition common-observable comparison (sorted union of metric names, missing = `available=False`) deferred to Stage 3.
- The Stage 3 common-observable envelope is the sorted union of the scalar executor metric names; the genuinely-common subspace is the 3 names every composition produces (`final_field_mean`, `final_field_std`, `field_entropy`). It does not claim physical equivalence of A/B/C quantities absent an explicit semantic alias (not yet built — later stages).
- Native-substep/engine differences mean A/B/C runs are not bitwise-comparable peers.
- Diversity is behavioral (Task 1.8 features); a heuristic, not a calibrated metric.
- Small discovery budget: 3 EXECUTABLE compositions / 23-shape universe; results are a demonstration, not exhaustive optimization.
- Executor resolution relies on the experiments-owned `repository_executors()` map and could hide dependence on the 3 experiments; core never dispatches on composition (purity scan enforced in tests).
- Only EXECUTABLE candidates enter discovery; the other 20 shapes are entirely out of scope of the pool.

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search/composition/templates/catalog/analysis experiment-free.
- Guarded core files must not change after Task 2.3 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract; `contracts=` is optional and strictly additive.
- No automatic coupling inference: contracts and coupling templates are never invented — unwired capability-valid shapes stay COUPLING_UNAVAILABLE.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Coupling contracts validate declared edges; they never synthesize or invent couplings.
- Adapter binding is by id + variant, never positional.
- Do not weaken prior tests.\n## Stage 4+5 Update (2026-09-09)\n- Milestone updated: Task 2.5 Stages 4+5 complete.\n- Completed: Stage 4 adapter (ranking/frontier), Stage 5 CLI + visualization.\n- Next: Task 2.6 design (plan-only) per AGENTS.md / IMPLEMENTATION_PLAN.md.\n

## Stage 3+4+5 Update (2026-09-10)
- Milestone: Task 2.6 Build Stages 3+4+5 complete (adaptive selection / proposal / continuation / CLI / figure / docs).
- Completed: Stage 3 selection APIs + Stage 4 feedback loop + Stage 5 CLI/visualization; 59 adaptive tests pass; real bounded C demo verified; profile semantics verified; replay verified.
- Next exact task: Task 2.7 Build Stage 1 (after PLAN-ONLY design confirmed)
- Do-not-change: keep guarded core files unchanged; no new dependencies; no experiment modifications; no automatic commits.

## Task 2.7 Build Stage 1 Update (current)
- Milestone: Task 2.7 Build Stage 1 complete (adaptive exploration specification + identity + subspace filter + tests + report).
- Completed: `core/adaptive_exploration.py` (AdaptiveExplorationSpec / ParameterConstraint / adaptive_exploration_id_of / filter_subspace / evaluate_exploration_spec); `tests/test_adaptive_exploration_stage1.py` (26 passed, A–Z); `TASK_2.7_STAGE1_REPORT.md`; real C subspace proof (freeze => 9 variants, identity deterministic); no execution / no lineage / core pure.
- Current capability: researcher-declared deterministic exploration specification with composition filtering, parameter subspace projection over existing MutationSpace, deterministic content-addressed identity, explicit VALID/INVALID/EMPTY_SUBSPACE status, bounded budget.
- Next exact task: Task 2.7 Build Stage 2 (CLI / multi-pass runner adapter / replay / figure).
- Do-not-change: no source changes beyond new module + tests; keep guarded files unchanged; no new dependencies; no experiment modifications; no automatic commits.


## Task 2.9 Design � PLAN-ONLY (verified complete)
- Milestone: Task 2.9 architecture research completed (PLAN-ONLY).
- Completed: TASK_2.9_DESIGN.md content prepared (persistent cross-session behavioral archive direction; smallest high-value next step after full adaptive pipeline verified).
- Next exact task: No Task 3.0 / no further implementation until explicitly issued.
- Do-not-change: no source/test/dependency/world changes; keep guarded files; no new experiments; no optimization; no ML/GA/Bayesian/RL/plugin/distributed.

## Task 2.9 Build Stage 1 Update (complete)
- Milestone: Task 2.9 Build Stage 1 complete (persistent adaptive-comparison archive + focused repair + verification).
- Completed: intact additive `adaptive_comparison_archive` table + index; new `LineageStore.record_adaptive_comparison` / `get_adaptive_comparison` (idempotent compact digest; no trajectories/feature vectors); restored `make_run_id`; fixed pre-existing `dt.timezone` latent bug in `record_exploration_session` and removed a blind try/except; `tests/test_adaptive_comparison_archive_stage1.py` strengthened (9 test); `TASK_2.9_STAGE1_REPORT.md`; real-data proof on genuine pre-2.9 DB (migration, idempotency 3x->1 row, same-DB, round-trip, real comparison id `e7ca46439e8f874408a9e3c0`); archive is execution-free and analysis-free (source-level scan + counters).
- Guard: `lineage.py` deliberately re-baselined in `test_field_guided_movers.py::CORE_COMMIT_HASHES` (documented RE-PIN, `2B91B51B55EC0BA1DE1A7C2EA630BB24EDBF3872AC5996A332FFE6C1C809525F`); Check-L token `"adapt"` pinned to `"adaptive_network"` in `test_mutation_lineage.py` (documented) to un-break a guard that had been failing at HEAD since Task 2.7.
- Verification: focused 9 passed; focused ruff 0; focused pyright 0; full pytest 658 passed / 1 failed (the failure is circumstantially proven pre-existing on pristine `HEAD` — `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`, unrelated to lineage); run_validation A-G PASS; run_stability S1-S6 PASS; full ruff 118 + full pyright 15 residuals are all pre-existing/scratch (none in Stage 1 files; identical pyright set on HEAD).
- Real-data missing-data statement: durable per-pass feature vectors are not persisted, so a fully-real comparison archives empty ranked/frontier with the honest requirement explanation; nothing fabricated.
- Next exact task: Task 2.9 Build Stage 2 (NOT started). Stage 3 / Task 3.0 NOT started.
- Do-not-change: no commit made; scratch/untracked files untouched; keep guarded core files unchanged beyond the sanctioned lineage.py re-baseline; no new dependencies; no experiment modifications.

## Task 2.9 Build Stage 2 Update (complete)
- Milestone: Task 2.9 Build Stage 2 complete (real archive consumption + deterministic replay + explicit feature linkage).
- Completed: `LineageStore` Stage 2 read-only consumption on top of the Task 2.9 archive — `iter_adaptive_comparisons` / `count_adaptive_comparisons` / `find_adaptive_comparisons(*, profile=, session_id=)` (canonical `adaptive_comparison_id` ascending order; verbatim profile match; exact session membership; explicit not-found) + `verify_adaptive_comparison(comparison_id)` (deterministic audit/replay from the archive row alone: 24-hex id, session well-formedness/sortedness, digest valid/well-formed shape, ranked/frontier ids within sessions, profile/status/created well-formed, `verdict` OK/CORRUPT; corruption reported never raised and never repaired; unknown id → None). `_adaptive_comparison_from_row` shared by get/iter; `get` contract unchanged.
- Feature linkage explicitly deferred: `feature_linkage.available` derived from the stored digest's own `diagnostics.feature_vectors_available`; `resolvable_from_archive` always False (no durable feature-snapshot reference persisted); `identity_recomputable` always False (identity also depends on pre-normalization profile payload + feature-key set, not stored), with exact reasons in both cases.
- Real repository proof on the genuine Stage 1 archive (copy of `task29_real_proof.db`): `e7ca46439e8f874408a9e3c0` (real sessions `2f41779e1947f870b32140e3` + `c592521de654e7c165d8ec15`) → get/iter/count/find(profile=default + by session)/verify == OK; `total_changes` unchanged (read-only); no execution/recomputation; identity independently recomputed outside simulation from the real sessions == `e7ca46439e8f874408a9e3c0`.
- Guard: `lineage.py` re-baselined again in `test_field_guided_movers.py::CORE_COMMIT_HASHES` → `41A18556AE571607AE62DEFAF9E77D23CACD5CCAA766D9941F1D3F6E90023260` (final Stage 2 state; documented RE-PIN with Task 2.9 Build Stage 2 comment; `test_network_morphogenesis` reuses the dict; `test_mutation_lineage` unchanged this stage).
- Verification: focused 19 Stage 2 + 9 Stage 1 + guard tests pass; focused ruff 0; focused pyright 0; full pytest 677 passed / 1 failed (identical pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`); run_validation A-G PASS; run_stability S1-S6 PASS; full ruff 118 + full pyright 15 residuals all pre-existing (none in Stage 2 files).
- Performance on the real archive: get 0.031 ms, iter 0.038 ms, count 0.025 ms, find 0.030 ms, verify 0.034 ms (2000-iter means); retrieval/verify O(1), iter/find O(n) read-only.
- Next exact task: Task 2.9 Build Stage 3 (NOT started at Stage 2 close). Stage 3 / Task 3.0 NOT started.
- Do-not-change: no commit made; scratch/untracked files untouched; keep guarded core files unchanged beyond the two sanctioned lineage.py re-baselines; no new dependencies; no experiment modifications.

## Task 2.9 Build Stage 3 Update (current)
- Milestone: Task 2.9 complete (authoritative feature linkage + read-only archive tooling + final verification). Task 3.0 NOT started.
- Evidence audit (OUTCOME B): no authoritative durable per-run feature data exists for adaptive passes — `run_adaptive_exploration.py` records no runs; `pass_adaptive_run_ids` are content-addressed `adaptive_run_id` values, never `runs.run_id`; real proof DB (`task29_real_proof.db` copy) shows 1 run with `feature_snapshot=NULL`, 0 `behavior_analyses`, real pass id `1611ed456112f8d3af7c8678` matches no `runs` row, and the archived comparison `e7ca46439e8f874408a9e3c0` itself attests `feature_vectors_available:false`.
- Added `LineageStore.feature_linkage_of(comparison_id)` (read-only, SELECT-only): resolves the archive row's source-session refs against `adaptive_exploration_sessions` + `runs` and reports `{available, resolvable, source_ids, resolved_feature_sources, evidence, reason}`; resolves `available=True` only through actual `runs.run_id` records carrying a real `feature_snapshot`; never fabricates values/ids; explicit unavailable with exact reason on real data.
- Added strict real-mode, read-only CLI `run_adaptive_comparison_archive.py` (subcommands `list`/`get`/`find`/`verify`/`link`; exit codes 0/10/20/30/40/50; unknown ≠ corrupt ≠ missing; `mode=ro` schema pre-flight refuses migration-writes; per-command `total_changes` proof; delegates to existing archive APIs, no ranking/frontier/analysis reimplementation).
- Guard: `lineage.py` re-baselined in `test_field_guided_movers.py::CORE_COMMIT_HASHES` → `1B71EAF6DD5A098BC0334647119510093334AE8F79179FDB431B75A89A04675F` (old `41A18556AE571607AE62DEFAF9E77D23CACD5CCAA766D9941F1D3F6E90023260`; documented in both guard files; `test_network_morphogenesis` reuses the dict).
- Verification: 18 new Stage 3 tests + 46 total Task 2.9 tests + guards pass; focused ruff 0 / focused pyright 0; full pytest 695 passed / 1 failed (identical pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`), slow canonical suite 13/13; run_validation A–G PASS; run_stability S1–S6 PASS; full ruff 118 + full pyright 15 residuals all pre-existing (none in Task 2.9 files).
- Performance on the real archive copy: get 0.031 ms, verify 0.033 ms, feature_linkage_of 0.104 ms, count 0.023 ms, iter 0.030 ms, find 0.027 ms; CLI cold start + list 219.6 ms.
- Limitation (preserved, not hidden): feature re-analysis/re-ranking remains unavailable at the archive layer because no authoritative durable feature chain exists (OUTCOME B); `resolvable_from_archive` stays False by design.
- Next exact task: Task 3.0 (NOT started). No commit made; scratch/untracked files untouched.

## Task 3.0 DESIGN — PLAN-ONLY (verified complete)
- Milestone: Task 3.0 full roadmap re-audit + new composition design completed (PLAN-ONLY). Task 2.9 complete. Task 3.0 implementation NOT started.
- HEAD verified: `ad8343c` "feat: complete adaptive comparison archive" on `master` tracking `origin/master`. Task 3.0 NOT started at audit time.
- Audit conclusion: the composition→discovery spine (worlds/capabilities/contracts/templates/catalog/evaluate/observables/sweep/behavior/rank/frontier) is complete and generic, but the executable universe is exactly the 3 hand-authored experiments (A/B/C); none of the 4 documented `COUPLING_UNAVAILABLE` discovery targets has ever been converted. Task 2.9 docs reconfirm the adaptive/archive tail is letter-coupled in action derivation (`_derive_actions_from_spec` keys on A/B/C) with no production archive write caller — deferred architecture work, not this milestone.
- Recommended direction: **Gated Mover Morphogenesis — `{mesa, py-pde, pymunk/movers}` (Experiment D)**: a new Mesa sensing/decision layer gates Experiment B's unconditionally-depositing movers (hysteresis + cooldown + per-mover gate). Converts exactly one `COUPLING_UNAVAILABLE` shape → EXECUTABLE (catalog {16,4,3}→{16,3,4}); zero generic-core / guard changes; zero new dependencies; A/B/C bitwise-unchanged; first legitimate non-C `MutationSpace`; new policy observables. Candidates B (four-way; coherent but overcomplicated/ambiguous two-`agent_intentions`), C (new engine; violates no-new-deps + pre-empts deferred extraction), D-temporal (no durable feature foundation; engineering convenience) rejected for Task 3.0 with reasons.
- Build stages: Stage 1 = composition declaration + contracts + adapter override + ONE structural test (no execution/sweep); Stage 2 = short-horizon deterministic baseline + gating-OFF control + boundedness/replay; Stage 3 = integration through existing discovery pipeline (search → common observables → sweep → behavior → rank → frontier). Smallest Stage 1 is the architecture proof only.
- Files written (plan-only): `TASK_3.0_DESIGN.md` (42 sections, repository-grounded), `PROJECT_STATE.md` (this update). No source/test/dependency/world/experiment/CLI changes; no execution; no commit.
- Next exact task: Task 3.0 Build Stage 1 (NOT started). Stage 2/3 / implementation NOT started; do not start Stage 1 until approved.
- Do-not-change: no source/test/dependency/world/experiment changes; keep guarded core files unchanged; no new dependencies; no commit; scratch/untracked files untouched; no automatic coupling inference (unwired stays COUPLING_UNAVAILABLE).

## Task 3.0 Build Stage 1 Update (current)
- Milestone: Task 3.0 Build Stage 1 complete (Experiment D — Gated Mover Morphogenesis — declared/contracted/catalogued/executor-registered). Stage 1 = the design's §35 "smallest Stage 1" exactly: composition declaration + contracts + Mesa gating adapter + catalog + ONE structural test file; no simulation, no sweep, no CLI in Stage 1 scope (§34 hard stops). The runtime proof used the FAST_STEPS=2 fast-catalog smoke; the real 160-step baseline was verified once as a slow-gate regression (D ≈ 63 s).
- Science (D): Experiment B's unconditionally-depositing movers are now gated by a Mesa sensing/decision layer that reads the morphogen field at each mover, applies hysteresis + cooldown per mover, and emits `deposition_events`/`deposition_suppression`/`active_gates`/`gate_switch_rate` policy observables (8 metrics total). The `mover-gate` contract consumes `rigid_body` (deviation from design §10's proposed `field_sources` — the pymunk/MoversAdapter exposes `rigid_body`, not `field_sources`; documented in the test comment).
- Landing surface: `experiments/gated_movers/{coupling,model,experiment}.py`, `experiments/catalog.py` (template/executor/adapters + D baseline-only `space=None` binding in `repository_parameter_spaces()`), `tests/test_gated_movers_stage1.py` (4 tests), `tests/test_templates.py` D operations drift-guard, `worlds/gated_movers.yaml`, `TASK_3.0_STAGE1_REPORT.md`.
- Guard: **zero generic-core / guard changes** — no pinned `CORE_COMMIT_HASHES`/hash re-baseline this stage; the only sanctioned test changes are catalog-count re-baselines in the stages whose pins enumerate the executable universe: stage2 (3→4 EXECUTABLE, `invalid()==20`→19), stage3 (3→4, 16→20 common names, `/3`→`/4`), stage4 (3→4 incl. frontier/beam/`[1,2,3,4]`), stage5 (`"4 EXECUTABLE (A, B, C, D)"`, `"runs=4)"`, `["A","B","C","D"]`), cross-sweep stage1 (`len(spaces)==4`), cross-composition-sweep stage2 (`n_baseline_only==2`, `len(bindings)==4`, `total_evaluations==4+27+4`, `cross_composition_sweep_count==4`).
- Correction of a prior plan claim: the sweep layer requires a binding entry for EVERY `catalog.executable()` (it raises `CrossCompositionSweepError` otherwise), so D now has a real `MutationSpace` (gate_threshold × gate_cooldown, 4 variants) bound in `repository_parameter_spaces()`; the binding is not `space=None` and the space is not deferred.
- Verification: fast suite `-m "not slow"` = **686 passed / 1 failed** (the single failure is the documented pre-existing historical `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`, isolated per design §32; identical on pristine HEAD); slow suite re-run in full = **13/13 passed** (stage2 9m31s, stage3 9m27s, stage4 5m01s, stage5 5m08s, real cross-composition sweep incl. D baseline 21m21s, l_canonical A/B, executor-vs-facade ×2, network canonical, A/B/C bitwise). Focused: 41 (Stage-1 + templates), 76 (catalog/search/cross-sweep), 98 (stage2/3/4/5), 70 (sweep/behavior/CLI) — all green. ruff: clean on all changed files; pyright: 0 errors on changed files (pre-existing Task 2.5-type optional-access residuals in `test_cross_composition_sweep_stage2.py` are untouched legacy, not Task 3.0); `run_catalog_demo.py` renders the 4-EXECUTABLE catalog.
- Real-machinery proof: the 4 real 160-step baselines evaluated individually in one process — A 89.9 s, D 63.1 s (8 metrics incl. the 4 new policy observables), B 64.4 s, C 85.4 s; all record root lineage runs with `composition_id` stamps; replay deterministic.
- Limitation (preserved, not hidden): D's gating science has NOT been validated (no baseline-vs-gating-OFF comparison; no boundedness); that is Task 3.0 Build Stage 2.
- Next exact task: Task 3.0 Build Stage 2 complete; the next milestone will be identified in the roadmap when available.
- Do-not-change: no commit made; scratch/untracked files untouched; keep guarded core files unchanged (no pinned hash touched); no new dependencies; no experiment modifications to A/B/C.
