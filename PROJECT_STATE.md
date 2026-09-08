# Simulation Alchemist — Current State

## Current milestone
Task 2.3 Build Stage 3+4+5 complete (CouplingTemplate registry + executable taxonomy, world generation with variant stamping, CompositionCatalog)

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
- Task 2.3 Build Stage 3+4+5 — experiment-owned CouplingTemplate registry + executable taxonomy (templates.py), declarative world generation with ComponentSpec.variant stamping + composition_id identity, CompositionCatalog over the 23-shape repository space (catalog.py, experiments/catalog.py, run_catalog_demo.py)

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
- templates (`templates.py`: `CouplingTemplate`, `CouplingTemplateRegistry`, `DuplicateTemplateError`, `classify_composition`, `CompositionVerdict`, `composition_id`, `template_composition_id`, `generate_world`) — Stage 3+4: the 6-status executable taxonomy (CAPABILITY_INVALID/COUPLING_UNAVAILABLE/COUPLING_INVALID/SCHEDULE_INVALID/CLOCK_INVALID/EXECUTABLE); contracts never inferred; adapters only constructed (never initialized/stepped) for template-matched shapes; declarative world generation with per-binding variant stamps
- catalog (`catalog.py`: `CompositionCatalog`, `CatalogCandidate`) — Stage 5: queryable/explainable snapshot of a whole CompositionSpace (all/executable/invalid/by_status/by_shape_id/status_counts/explain; optional generated worlds for EXECUTABLE rows; never simulated/persisted/searched)
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

## Current validation (Task 2.3 Build Stage 3+4+5 closing gate)
- pytest — full suite standing gate: **359 tests passed** (353 fast + 6 slow; incl. 123 Task 2.3 composition/template/generation/catalog tests — 40 Stage 1+2 + 37 test_templates + 22 test_world_generation + 24 test_catalog — plus slow canonicals)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current activity
Task 2.3 Build Stage 3+4+5 complete (per `TASK_2.3_DESIGN.md` §22, items 3–5).
- `src/sim_alchemist/core/templates.py` — the coupling-template layer:
  `CouplingTemplate` (frozen authoring surface: name/bindings/world_id/contracts/
  schedule/operations/requires/executor_ref/component_configs/macro_timestep/
  max_steps/seed/config; canonical bindings via CompositionShape; empty
  name/bindings/world_id/contracts/schedule/operations rejected),
  `CouplingTemplateRegistry` (register-only, `DuplicateTemplateError`,
  deterministic `templates()`), `classify_composition` (the ordered 6-status
  funnel: capability → template → contracts → schedule → clock → EXECUTABLE;
  contracts never inferred; adapters only constructed for template-matched
  shapes — never initialized/stepped; `CompositionVerdict` with reasons),
  `composition_id`/`template_composition_id` (content-addressed 24-hex from
  shape + contracts_key + schedule + requires + macro_timestep), and
  `generate_world(template)` (deterministic, immutable, adapter-free
  `WorldDefinition`; `ComponentSpec` gets the concrete binding `variant`
  stamped — walls/movers/None).
- `src/sim_alchemist/core/catalog.py` — `CompositionCatalog` (eager, cheap,
  immutable snapshot of an entire CompositionSpace: every shape classified once
  in deterministic order; query APIs all/executable/invalid/by_status/
  by_shape_id/status_counts/explain; `generate_worlds=True` materializes only
  the EXECUTABLE worlds) + `CatalogCandidate` (shape/status/shape_id/bindings/
  missing_capabilities/template/reason/composition_id/generated_world).
- The 23-shape repository universe (5 bindings: mesa, py-pde, network,
  pymunk/walls, pymunk/movers) classifies **16 CAPABILITY_INVALID /
  4 COUPLING_UNAVAILABLE / 3 EXECUTABLE** (0 COUPLING_INVALID). EXECUTABLE = the
  three experiment templates; the four design §11 unwired capability-valid
  shapes are COUPLING_UNAVAILABLE, never invented.
- `experiments/catalog.py` — repository surfaces/bindings/templates/adapters
  keyed by `(component, variant)` across default + C + B registries;
  `run_catalog_demo.py` — CLI demo (`--generate-worlds` writes the 3 worlds).
- Slow bitwise proof: generated worlds executed through the plain composer
  reproduce the A/B/C facade trajectories exactly.
- Guard re-baselined (sanctioned extension): `__init__.py`, `world.py`
  re-pinned; `templates.py`, `catalog.py` added to `CORE_COMMIT_HASHES`.
- `TASK_2.3_CHECKPOINT.md`, `TASK_2.3_REPORT.md`, `PROJECT_STATE.md`,
  `IMPLEMENTATION_PLAN.md`, `AGENTS.md` updated.

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
- Composition classification is **static**: EXECUTABLE means "statically known to compose" — it says nothing about scientific meaningfulness. Capability/clock metadata is read by *constructing* adapters (constructor-only, never stepped).
- The `CompositionCatalog` is an in-memory snapshot: nothing is persisted, searched, or discovered yet — there is **no CompositionSearcher / search integration**, and `composition_id` is not yet written into the lineage store (composition axis = later stage).
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
Task 2.4 — cross-composition discovery loop (`CompositionSearcher` +
composition lineage + discovery demo) per `TASK_2.3_DESIGN.md` §22/§23 and
`IMPLEMENTATION_PLAN.md`. Not started. Do not start Task 2.4 until it is issued.

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search/composition/templates/catalog experiment-free.
- Guarded core files must not change after Task 2.3 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract; `contracts=` is optional and strictly additive.
- No automatic coupling inference: contracts and coupling templates are never invented — unwired capability-valid shapes stay COUPLING_UNAVAILABLE.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Coupling contracts validate declared edges; they never synthesize or invent couplings.
- Adapter binding is by id + variant, never positional.
- Do not weaken prior tests.