# Simulation Alchemist — Current State

## Current milestone
Task 2.4 Build Stage 3 — common cross-composition observables (COMPLETE)
Next: Task 2.4 Build Stage 4 — cross-composition ranking / discovery frontier (NOT started)

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
- observables (`observables.py`: `CommonObservable`, `CommonObservableSet`, `CommonObservableError`, `common_observable_names`, `extract_common_observables`) — Task 2.4 Stage 3: deterministic common cross-composition observable envelope — sorted union of executor metric names across an evaluated pool; per-composition availability (`available=False`/`value=None` for composition-specific names elsewhere; never imputed); horizon (`max_steps`/`macro_timestep`) captured from the generated world with id/hash-match validation; pure projection of recorded evaluations (no re-runs, no persistence, world-immutable)
- contracts (`contracts.py`: `CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`, `resolve_contracts`, `adapter_by_id`, `contracts_key`)
- templates (`templates.py`: `CouplingTemplate`, `CouplingTemplateRegistry`, `classify_composition`, `CompositionVerdict`, `composition_id`, `template_composition_id`, `generate_world`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml

## Current validation (Task 2.4 Build Stage 3 closing gate)
- pytest — full suite standing gate: **444 tests passed** (434 fast + 10 slow; incl. the Stage 1 suite, the 25-fast/1-slow Stage 2 orchestrator suite, the new 30-fast/1-slow `tests/test_common_observables_stage3.py` Stage 3 common-observables suite, and the re-pinned core-guard tests)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors
- Canonical repository search regression: EXECUTABLE=3, invalid=20, evaluated=3, `run_count` stays 3 across replay; observable extraction is O(n) (~0.0002 s vs ~41.5 s of evaluation on this machine)

## Next exact task
Task 2.4 Build Stage 4 — cross-composition ranking / discovery frontier over the common observable layer. NOT started.

## Known limitations (Task 2.4, per design §16–§17)
- The Stage 3 common-observable envelope is the sorted union of the scalar executor metric names; the genuinely-common subspace is the 3 names every composition produces (`final_field_mean`, `final_field_std`, `field_entropy`). It does not claim physical equivalence of A/B/C quantities absent an explicit semantic alias (not yet built — later stages).
- Native-substep/engine differences mean A/B/C runs are not bitwise-comparable peers.
- Diversity is behavioral (Task 1.8 features); a heuristic, not a calibrated metric.
- Small discovery budget: 3 EXECUTABLE compositions / 23-shape universe; results are a demonstration, not exhaustive optimization.
- Executor resolution relies on the experiments-owned `repository_executors()` map and could hide dependence on the 3 experiments; core never dispatches on composition (purity scan enforced in tests).
- Only EXECUTABLE candidates enter discovery; the other 20 shapes are entirely out of scope of the pool.

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search/composition/templates/catalog experiment-free.
- Guarded core files must not change after Task 2.3 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract; `contracts=` is optional and strictly additive.
- No automatic coupling inference: contracts and coupling templates are never invented — unwired capability-valid shapes stay COUPLING_UNAVAILABLE.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Coupling contracts validate declared edges; they never synthesize or invent couplings.
- Adapter binding is by id + variant, never positional.
- Do not weaken prior tests.