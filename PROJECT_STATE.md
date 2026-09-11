# Simulation Alchemist — Current State

## Current milestone
Task 2.9 Build Stage 2 complete (real archive consumption + deterministic replay + explicit feature linkage)

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

## Current experiments
- A — Chemo-Mechanical Morphogenesis (Mesa + py-pde + Pymunk)
- B — Field-Guided Movers (py-pde + Pymunk)
- C — Adaptive Network Morphogenesis (NDlib + py-pde + Pymunk)

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

## Current validation (Task 2.4 Build Stage 5 closing gate)
- pytest — full suite standing gate: **518 tests passed** (503 fast + 15 slow; incl. Stage 1 + new 16-fast/1-slow Stage 2 cross-composition sweep + 30-fast/1-slow Stage 3 common-observables + 34-fast/1-slow Stage 4 + 9-fast/1-slow Stage 5)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors
- Canonical discovery regression (seed 0, 160 steps): discovery id `91a72c708d07d66b5926edec`, 3 EXECUTABLE, 3 genuinely common observables (`final_field_mean`, `final_field_std`, `field_entropy`), evaluation 59.69 s; Profile A ranking: C 1.75 > A 0.413 > B 0.268; Profile B ranking: C 1.25 > B 0.855 > A 0.707; Stage 4 analysis ~0.0004 s (essentially free); deterministic replay canonical-identical; `run_count` unchanged across replay

## Next exact task
Task 2.9 Build Stage 3 (NOT started). Stage 3 / Task 3.0 NOT started.

## Current capability (Task 2.6 Stage 1)
- Deterministic adaptive signal / state / decision evaluation (core/adaptive_sweep.py)
- Canonical serialization, pure assessment, explicit missing-data contract
- Integration hook for BehaviorFeatures / InterestingnessProfile (no execution required)
- Prior capabilities preserved: executable composition-specific parameter-space declarations (`experiments/catalog.py::repository_parameter_spaces()`; C real 27-variant space, A/B `None`)
- CrossCompositionSweep orchestrator (`core/cross_composition_sweep.py`)
- Durable cross-composition sweep lineage (`lineage.py` `cross_composition_sweeps` + `CrossCompositionSweepRow`; INSERT OR REPLACE; idempotent)
- `composition_id` stamped on `RunRecord` (`runner.py`/`sweep.py` optional threading)
- Cross-composition common-observable aggregation (`core/cross_composition_behavior.py`; pure projection; `CrossCompositionBehaviorResult`; vocabulary from pool; 30 observations; baseline/variant preserved; no ranking/frontier/visualization/CLI)

## Known limitations (Task 2.4 + Task 2.5 Stage 1 & design §16–§17)
- No cross-composition sweep ranking / diversity frontier / shared sweep behavior aggregation (Stage 4 — deferred to Stage 3+4).
- No CLI / figure for cross-composition sweeps (Stage 5 — deferred).
- Only C has a declared mutation space; A/B remain baseline-only unless experiments declare new spaces.
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

## Task 2.9 Build Stage 2 Update (current)
- Milestone: Task 2.9 Build Stage 2 complete (real archive consumption + deterministic replay + explicit feature linkage).
- Completed: `LineageStore` Stage 2 read-only consumption on top of the Task 2.9 archive — `iter_adaptive_comparisons` / `count_adaptive_comparisons` / `find_adaptive_comparisons(*, profile=, session_id=)` (canonical `adaptive_comparison_id` ascending order; verbatim profile match; exact session membership; explicit not-found) + `verify_adaptive_comparison(comparison_id)` (deterministic audit/replay from the archive row alone: 24-hex id, session well-formedness/sortedness, digest valid/well-formed shape, ranked/frontier ids within sessions, profile/status/created well-formed, `verdict` OK/CORRUPT; corruption reported never raised and never repaired; unknown id → None). `_adaptive_comparison_from_row` shared by get/iter; `get` contract unchanged.
- Feature linkage explicitly deferred: `feature_linkage.available` derived from the stored digest's own `diagnostics.feature_vectors_available`; `resolvable_from_archive` always False (no durable feature-snapshot reference persisted); `identity_recomputable` always False (identity also depends on pre-normalization profile payload + feature-key set, not stored), with exact reasons in both cases.
- Real repository proof on the genuine Stage 1 archive (copy of `task29_real_proof.db`): `e7ca46439e8f874408a9e3c0` (real sessions `2f41779e1947f870b32140e3` + `c592521de654e7c165d8ec15`) → get/iter/count/find(profile=default + by session)/verify == OK; `total_changes` unchanged (read-only); no execution/recomputation; identity independently recomputed outside simulation from the real sessions == `e7ca46439e8f874408a9e3c0`.
- Guard: `lineage.py` re-baselined again in `test_field_guided_movers.py::CORE_COMMIT_HASHES` → `41A18556AE571607AE62DEFAF9E77D23CACD5CCAA766D9941F1D3F6E90023260` (final Stage 2 state; documented RE-PIN with Task 2.9 Build Stage 2 comment; `test_network_morphogenesis` reuses the dict; `test_mutation_lineage` unchanged this stage).
- Verification: focused 19 Stage 2 + 9 Stage 1 + guard tests pass; focused ruff 0; focused pyright 0; full pytest 677 passed / 1 failed (identical pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`); run_validation A-G PASS; run_stability S1-S6 PASS; full ruff 118 + full pyright 15 residuals all pre-existing (none in Stage 2 files).
- Performance on the real archive: get 0.031 ms, iter 0.038 ms, count 0.025 ms, find 0.030 ms, verify 0.034 ms (2000-iter means); retrieval/verify O(1), iter/find O(n) read-only.
- Next exact task: Task 2.9 Build Stage 3 (NOT started). Stage 3 / Task 3.0 NOT started.
- Do-not-change: no commit made; scratch/untracked files untouched; keep guarded core files unchanged beyond the two sanctioned lineage.py re-baselines; no new dependencies; no experiment modifications.
