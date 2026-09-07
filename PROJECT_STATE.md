# Simulation Alchemist — Current State

## Current milestone
Task 2.3 Build Stage 1+2 complete (CompositionShape/CompositionSpace + static capability filter)

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
- Task 2.0 — diversity-preserving multi-objective discovery (behavioral-diversity-aware beam selection)
- Task 2.1 — cross-composition compatibility and discovery design (PLAN-ONLY; TASK_2.1_DESIGN.md)
- Task 2.2 — coupling-contract layer + pre-execution composition validation (contracts.py, optional contracts=, adapters metadata, id lookup, gap-proof test)
- Task 2.3 Build Stage 1+2 — composition shape/space layer (composition.py: ComponentBinding, CompositionShape, CompositionSpace, static capability filter)

## Current experiments
- A — Chemo-Mechanical Morphogenesis (Mesa + py-pde + Pymunk)
- B — Field-Guided Movers (py-pde + Pymunk)
- C — Adaptive Network Morphogenesis (NDlib + py-pde + Pymunk)

## Current architecture
`src/sim_alchemist/core/`:
- adapters (`adapters/base.py`, capability protocol in `core/capabilities.py`; metadata: variant / state_keys / grid / coordinate_system)
- capabilities (`capability`/`CapabilitySet` + `SimulationEngine` protocol)
- world definitions (`world.py`, `WorldDefinition`/`ComponentSpec`, YAML)
- composer (`composer.py`: `compose`/`compose_into`/`build_components`/`resolve_capabilities`, optional `contracts=` -> `resolve_contracts` before `_install`)
- composition (`composition.py`: `ComponentBinding`, `CompositionShape`, `CompositionSpace`, `CapabilitySurface`, `CompositionClassification`, `capability_surfaces_from_registry`, `bindings_from_registry`, `classify_shape(s)`; CAPABILITY_VALID/CAPABILITY_INVALID) — variant-aware binding sets, canonical content-addressed shape_id, deterministic bounded enumeration, static (constructor-only, never stepped) capability filter
- contracts (`contracts.py`: `CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`, `resolve_contracts`, `adapter_by_id`, `contracts_key`) — declarative coupling-edge validation, never invents couplings
- clock (`clock.py`), scheduler (`scheduler.py`), event bus (`events.py`)
- mutation (`mutation.py`: `Mutation`, `MutationRecord`, `ParameterSpec`, validators, immutable clone)
- lineage (`lineage.py`: `LineageStore`, `RunRecord`, `SweepRecord`, `BehaviorAnalysisRecord`, `SearchRecord`, deterministic `run_id_of`)
- runner (`runner.py`: `VariantRunner`, `compare_metrics`, `compare_runs`)
- sweep (`sweep.py`: `ParameterSweep`, `MutationSpace`, `sweep_id_of`, `SweepRunner`, `rank_results`, `SweepResult`)
- behavior (`behavior.py`: `ObservableSeries`, `BehaviorFeatures`, `BehaviorAnalyzer`, `InterestingnessProfile`, `rank_by_profile`, `BehavioralAnalysisRunner`, `behavior_vector`, `behavior_distance`, `select_diverse_frontier`, `compute_frontier_diagnostics`, `FrontierDiagnostics`)
- search (`search.py`: `SearchSpec`, `SearchRunner`, `child_mutations`, `search_id_of`, `SearchCandidate`, `SearchGeneration`, `SearchResult`, `SearchTiming`, `SelectionProfile`)
- contracts (`contracts.py`: `CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`, `resolve_contracts`, `adapter_by_id`, `contracts_key`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml
- pytest, ruff, pyright, hypothesis (dev)

## Current validation (Task 2.3 Build Stage 1+2 closing gate)
- pytest — full suite standing gate: **274 tests passed** (incl. 40 new Task 2.3 Stage 1+2 composition tests + slow canonicals)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current activity
Task 2.3 Build Stage 1+2 complete (per `TASK_2.3_DESIGN.md` §22/§23).
- `src/sim_alchemist/core/composition.py` — the composition shape/space layer:
  `ComponentBinding` (identity = component id + variant; empty variant
  normalizes to None), `CompositionShape` (unordered variant-distinct binding
  set; canonical sort by (component, variant-or-""); 24-hex content-addressed
  `shape_id`; input-order-independent; rejects duplicates and same-component
  variants), `CompositionSpace` (name + universe + min/max bounds; size-first
  deterministic enumeration, right-most element fastest, variant exclusivity;
  min_size=0 allowed but the empty shape is never enumerated), `CapabilitySurface`
  + `capability_surfaces_from_registry` (constructor-only, cached per binding,
  never initialize/step), `bindings_from_registry`, `classify_shape(s)`
  (provides/requires union vs adapter needs + world-level required;
  CAPABILITY_VALID or CAPABILITY_INVALID with deterministic sorted
  `missing_capabilities`; capability-valid does NOT imply executable).
- The 5-binding universe (mesa, py-pde, network, pymunk/walls, pymunk/movers)
  comes from the real registries: default + Experiment C + Experiment B; exact
  variant-exclusive counts 5/9/7/2, 23 non-empty shapes for min=1/max=4.
- No CouplingTemplate registry, no world generation, no CompositionCatalog/
  Searcher, no search integration, no ComponentSpec variant stamping (all later
  stages). DELETE NOTHING; no scientific baseline parameter changed.
- Guard re-baselined (sanctioned extension): `composition.py` + `__init__.py`
  pinned in `CORE_COMMIT_HASHES`; new architectural test proves
  `composition.py` is experiment-free.
- `tests/test_composition_space.py` (40 tests: ComponentBinding A–F,
  CompositionShape A–H, CompositionSpace A–H, registry-derived bindings,
  capability filter A–G, static-only proof, core-purity architectural test).
- `TASK_2.3_STAGE1_2_REPORT.md`, `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`
  updated; `AGENTS.md` next-milestone line updated.

## Completed in previous task (Task 2.2) — history retained
- `src/sim_alchemist/core/contracts.py` — the coupling-contract layer: `CouplingContract` (frozen; payload normalized to `PayloadItem`; variant/timing/mechanism/coordinate_system/grid defaults), `PayloadItem`, `ContractIssue`, `UnresolvedContractError` (deterministic, actionable), `resolve_contracts` (identity -> capability -> variant -> payload -> timing/mechanism -> coord -> grid -> self-edge; never invents couplings), `adapter_by_id` (id + variant based, never positional), `contracts_key`
- optional `contracts=` threaded through `compose`/`compose_into`; stage order resolve_capabilities -> resolve_contracts -> _install
- adapter metadata: `_variant`/`_state_keys`/`_grid`/`_coordinate_system` on `BaseAdapter`; pde/pymunk/mesa/movers/network set them (pymunk dual-variant walls/movers)
- declared contracts colocated: `MORPHOGENESIS_CONTRACTS` (A, 4 edges), `FIELD_GUIDED_MOVERS_CONTRACTS` (B, 2), `NETWORK_MORPHOGENESIS_CONTRACTS` (C, 5)
- facades pass `contracts=`; `run_network_world` now uses `adapter_by_id` (positional indexing removed)
- tests (`tests/test_contracts.py`, A–R): incl. the gap proof — Exp C world with pymunk->MoversAdapter passes `resolve_capabilities` yet `compose(..., contracts=NETWORK_MORPHOGENESIS_CONTRACTS)` raises `UnresolvedContractError` before `_install`; `contracts=` vs `None` bitwise-identical science for A/B/C
- core immutability guard re-baselined (sanctioned Task 2.2 extension): contracts.py, composer.py, __init__.py
- TASK_2.2_REPORT.md, PROJECT_STATE.md, IMPLEMENTATION_PLAN.md updated

## Known limitations
- Composition analysis today is *static capability* filtering only (CAPABILITY_VALID/CAPABILITY_INVALID). There is no coupling-template classification (COUPLING_UNAVAILABLE/COUPLING_INVALID), no schedule/clock validation, and no EXECUTABLE verdict — capability-valid does not mean executable (Stage 3+).
- There is no world generation from compositions yet, and no automatic/guided composition search (no CompositionCatalog/CompositionSearcher) — those are later stages.
- `ComponentSpec`/`WorldDefinition` do not yet carry a variant field, so a declared world cannot yet *stamp* which variant its components must be (Stage 4).
- `config.network_loss` mirror is stale/behaviorally neutral; effective value is `components.network.config.loss`.
- Beam search is a bounded heuristic (no global optimality claim); single-parameter children only (no multi-param combinations).
- Diversity is evaluated on the discrete behavioral-feature snapshot of the beam pool; it cannot discover behavior outside the features the profile exposes.
- Greedy frontier selection is exact under the declared weights but is a heuristic for global multi-objective optimality (no Pareto-parity guarantee).
- `oscillation_persistence` is blind to periods ≲ 4 samples (lag-1 quadrature); documented.
- Determinism is same-runtime/same-environment (not universal cross-platform bitwise).
- Parameters hand-tuned for validated runs.
- Contract payload keys are validated only against a producer that declares `state_keys` (all wired producers do); a producer exposing no state vocabulary skips the key check (documented).
- The contract layer validates *declared* edges only; it cannot invent couplings, and an undeclared-but-capability-valid edge is rejected only when composed with a contract set that needs it (empty contract set = today's unchecked behavior).

## Next exact task
Task 2.3 Build Stage 3 — CouplingTemplate Registry (experiment-owned templates,
COUPLING_UNAVAILABLE/COUPLING_INVALID/SCHEDULE_INVALID/CLOCK_INVALID/EXECUTABLE
classification) — per `TASK_2.3_DESIGN.md` §22/§23. Do not start until issued.

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search/composition experiment-free.
- Guarded core files must not change after Task 2.3 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract; `contracts=` is optional and strictly additive.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Coupling contracts validate declared edges; they never synthesize or invent couplings.
- Adapter binding is by id + variant, never positional.
- Do not weaken prior tests.