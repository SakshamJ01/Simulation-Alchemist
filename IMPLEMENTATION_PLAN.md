# Simulation Alchemist — Implementation Plan

**Status:** BASELINE v0.1 COMPLETE — Tasks 0.1–0.3 validated, Tasks 1.2–1.3
validated, Task 1.5 (Experiment C: Adaptive Network Morphogenesis) validated,
**Task 1.6 (generic mutation + SQLite experiment lineage) COMPLETE**, **Task 1.7
(deterministic variant sweeps + generic experiment ranking) COMPLETE**, **Task 1.8
(behavioral characterization + generic interestingness engine) COMPLETE**,
**Task 1.9 (guided simulation search — first discovery loop) COMPLETE**,
**Task 2.0 (diversity-preserving multi-objective discovery) COMPLETE**, **Task 2.1
(cross-composition compatibility & discovery design, PLAN-ONLY) COMPLETE**,
**Task 2.2 (coupling-contract layer + pre-execution validation) COMPLETE**,
**Task 2.3 Build Stage 1+2 (CompositionShape/CompositionSpace + static
capability filter) COMPLETE**, **Task 2.3 Build Stage 3+4+5 (CouplingTemplate
registry + executable taxonomy, world generation with variant stamping,
CompositionCatalog) COMPLETE**, **Task 2.4 Build Stage 1 (cross-composition
discovery result layer: `composition_search.py` evaluation record + deterministic
`composition_discovery_id_of` + `evaluate_composition_baseline`, additive
`composition_id` lineage stamp with migration, A/B experiment executors +
`repository_executors()` map) COMPLETE**, **Task 2.4 Build Stage 2 (the thin
`CompositionSearcher` orchestrator: enumerate `catalog.executable()` in canonical
order → resolve experiment-owned executors via an opaque id→executor map →
evaluate one baseline per EXECUTABLE composition through the Stage 1 result layer
→ compact unranked `CompositionSearchResult` with deterministic replay; no
ranking, no behavior analysis, no frontier, no visualization) COMPLETE**,
**Task 2.4 Build Stage 3 (common cross-composition observables: deterministic
`CommonObservableSet` per evaluated composition over the sorted union of the
executors' metric names, missing = explicit `available=False`/`value=None`,
horizon captured from the generated worlds, pure O(n) extraction reusing the
in-memory evaluations with evaluation/extraction timing split, integrated
into `CompositionSearcher.search` with backward-compatible
`CompositionSearchResult` / `CompositionSearchTiming`) COMPLETE.** Next is
**Task 2.4 Build Stage 4 (cross-composition ranking / discovery frontier over
the common observable layer)**, not started; do not start it until it is
issued.
**Date:** 2026-09-05 (updated 2026-09-09)

---

## 0. Task Status

### COMPLETED
- **Task 0.1** — spike: chemo-mechanical feedback idea validated on
  representative engines (Mesa / pymunk / py-pde integration).
- **Task 0.2** — clamped-obstacle wall coupling: static walls block the
  reaction-diffusion field; agents deposit/dissolve walls.
- **Task 0.3** — dynamic chemo-mechanical loop: pymunk walls are driven by
  bounded field-gradient forces; validation A–G and stability S1–S6 pass;
  figures in `figures/` are the baseline evidence.
- **Task 1.2** — core scheduler extraction: `StepScheduler` + `StepSchedule`
  moved to `src/sim_alchemist/core/scheduler.py` with valid-operations
  validation at install time, deterministic time progression, and full trace.
  51 pytest tests passing; both experiments' `SCHEDULE` attributes execute
  through the core scheduler without any experiment-specific scheduling logic.
- **Task 1.3** — declarative composition layer: `WorldDefinition`/`ComponentSpec`
  (PYAML-loadable), `ComponentRegistry` + `default_registry()`, `compose()` /
  `compose_into()` adapter-building + capability-resolution path, plain
  `AlchemistEngine` execution, thin experiment facades, YAML worlds
  (`worlds/*.yaml`), 17 A–M composition tests (`tests/test_composition.py`);
  plain-compose path proved bitwise identical to both facades; full canonical
  regression (A 160 steps, B closed 160 steps) matches baseline hashes.
- **Task 1.5** — THIRD composed experiment (Adaptive Network Morphogenesis,
  Experiment C) proving a genuine A↔B↔C↔A feedback triangle through the same
  generic core: an NDlib `ContinuousModel` network adapter
  (`experiments/network_morphogenesis/adapter.py`, `engine_id="network"`,
  capability `network_diffusion`) whose continuous node loads inject py-pde
  field sources; the field gradient drives Pymunk wall growth; wall geometry
  reweights network edges, rerouting diffusion. `network_morphogenesis/coupling.py`
  declares `NETWORK_MORPHOGENESIS_SCHEDULE` + world/registry builders;
  `worlds/adaptive_network.yaml` is the declarative twin. No change to
  `src/sim_alchemist/core/` (immutability guard holds). 26 C1–C10 tests in
  `tests/test_network_morphogenesis.py` pass (capability resolution, bitwise
  determinism, closed-loop divergence from open/inert controls, sustained
  adaptive growth, boundedness, YAML/plain-compose equivalence, shared core).
- **Task 1.6** — GENERIC MUTATION + EXPERIMENT LINEAGE: first generic
  experiment-facing mutation/lineage capability, fully experiment-free in the
  core. `src/sim_alchemist/core/mutation.py` (declarative `Mutation`/
  `MutationRecord`/`ParameterSpec`, validators, immutable `apply_mutation`/
  `apply_mutations` with deep-clone semantics, dot-path grammar restricted to
  data, no `eval`, structural fields immovable), `lineage.py` (SQLite-backed
  `LineageStore` storing metadata + compact metrics only — never trajectories —
  with deterministic `run_id_of` from world hash + seed, idempotent records),
  `runner.py` (`VariantRunner` over any executor, `compare_metrics`/
  `compare_runs` generic per-metric `MetricDelta`). Experiment C declares its
  three meaningful parameters (`components.network.config.loss`,
  `config.force_fmax`, `config.source_amplitude`) in
  `experiments/network_morphogenesis/experiment.py` plus `build_network_metrics`
  and the `run_network_world` executor; `NetworkMorphogenesisConfig.from_world`
  added to `model.py`. 26 A–L tests (`tests/test_mutation_lineage.py`) pass;
  demo `run_variant_demo.py` shows a real 159-wall base run vs a loss 0.05→0.14
  variant (growth edges 9→6, field std +0.374, wall movement +7.7) with
  deterministic run ids and recorded lineage. Core immutability guard
  re-baselined to the post-1.6 core (adds mutation/lineage/runner.py).
  `pyproject.toml` fixes the packaging gaps found while closing: `ndlib==5.1.1`
  was missing though imported at runtime; added a build-system
  (`[tool.hatch.build.targets.wheel]`) so `uv sync` installs the project
  itself. `uv.lock` regenerated (57 packages).
- **Task 1.7** — DETERMINISTIC VARIANT SWEEPS + GENERIC RANKING: turns Task 1.6's
  singular mutations into the generic batch layer, fully experiment-free in the
  core. `src/sim_alchemist/core/sweep.py` (`ParameterSweep`+`MutationSpace`
  Cartesian products with **documented `itertools.product` ordering** — right-most
  dimension fastest, unit-tested verbatim; deterministic `sweep_id_of` from
  world hash + canonical space; `SweepRunner` with a two-phase `sweep()`
  — (1) generate + validate the **entire** space against `parameter_specs`
  before any simulation, dropping+counting no-ops identical to the baseline,
  (2) run the **baseline control first** then every variant sequentially,
  recording each into the lineage store; `SweepTiming` planned/skipped/executed
  + total/mean seconds; `rank_results`/`RankingEntry` — pick a metric by name,
  choose direction, deterministic tie-break by run id ascending, raw values
  only). `lineage.py` extended with an idempotent `sweeps` table +
  `SweepRecord` (metadata only, never trajectories; run metrics stay in the
  existing `runs` table). 18 A–Q tests (`tests/test_sweep_ranking.py`); CLI
  `run_sweep.py` (`--dim path:v1,v2,...` repeatable, `--rank-by`, `--ascending`,
  `--db`). Real Experiment C sweep: loss[0.05,0.08,0.11,0.14] ×
  force_fmax[0.4,0.8] → 8 planned, 7 executed, 1 no-op skipped; ranking by
  field_entropy puts the loss=0.14 variants on top. Cross-layer determinism:
  the 10-step base run id `08c74954f42c86066b118244` and loss=0.14 variant
  `f3faa9c9d8d344b46271a393` reproduce Task 1.6's run ids exactly. Guard
  re-baselined to the post-1.7 core (adds sweep.py); no prior test weakened.
- **Task 1.8** — BEHAVIORAL CHARACTERIZATION + GENERIC INTERESTINGNESS ENGINE:
  first generic trajectory-characterization layer, fully experiment-free in the
  core, stdlib-only (`math`/`statistics` — **no ML/LLM/embeddings/clustering/
  learned weights, by task constraint**). `src/sim_alchemist/core/behavior.py`
  (`ObservableSeries` with eager validation + deterministic `resample_to`;
  18 features in temporal / trend / oscillation / stability / divergence
  families with documented formulas — oscillation is `sign_change_rate ×
  |lag1 autocorr of detrended residual|`, so a single step scores 0 and no
  false periodicity claim is possible; divergence compares each variant
  resampled onto the baseline's time axis; baseline's own divergence is
  `None`, never silently 0; `InterestingnessProfile` with explicit weights +
  per-feature max/min directions — "interesting ≠ largest value", and `rank_by_profile`
  normalizing min-max **across the analyzed population** with `run_id` tie-break
  (Task 1.7 rule, reused); `Contribution`/`RankedRow.explanation()` giving a
  per-feature "favors/penalizes interest" explanation; `BehavioralAnalysisRunner`
  reusing `apply_mutations`/`run_id_of`/no-op skip-and-count; deterministic
  `behavior_analysis_id_of`). `lineage.py` extended with a per-run compact
  `feature_snapshot` (`runs` column + `_migrate()` ALTER for pre-1.8 stores)
  and an idempotent `behavior_analyses` table — **trajectories are never
  persisted**. Experiment C exposes `build_network_observables` (9 scalar
  series on `t_field`; field mean/std derived in memory only). 18 A–Q tests
  (`tests/test_behavior_analysis.py`); CLI `run_behavior_demo.py` (`--dim`,
  `--feature name:weight[:max|min]`, `--steps`, `--db`). Real Experiment C
  analysis at 160 steps: loss[0.05,0.08,0.11,0.14] → 4 planned, 3 executed,
  1 no-op skipped, 58.96s total / 19.65s mean; baseline ranked #1 under the
  demo profile (field oscillation + flat network-load max) with the "why"
  explanation reproduced verbatim in the report. Guard re-baselined to the
  post-1.8 core (adds behavior.py); no prior test weakened. See
  `TASK_1.8_REPORT.md`.
- **Task 1.9** — GUIDED SIMULATION SEARCH (FIRST DISCOVERY LOOP):
  first *discovery loop* of the framework: a deterministic bounded beam
  search over world variants, experiment-free in the core, reusing existing
  Task 1.6/1.7/1.8 machinery. `src/sim_alchemist/core/search.py`
  (`SearchSpec` — frozen, validated declarative config: name, generations,
  beam_width, children_per_parent, mutation_space, profile, seed;
  `child_mutations` — dimension-major, value-minor, no-op skip, single-param
  children, truncation; `SearchRunner` — sequential beam search: gen 0 = root
  control, each generation mutates beam, runs unique children via
  `apply_mutations`, ranks via `rank_by_profile`, keeps `beam_width` best;
  `SearchCandidate`, `SearchGeneration`, `SearchResult`, `SearchTiming` — full
  in-memory outcome with `best()`, `lineage_path()`, `mutation_path()`,
  `explain_best()`; `search_id_of` — deterministic 24-hex id from world hash
  + spec JSON). `lineage.py` extended with `SearchRecord` + idempotent
  `searches` table (compact metadata only, never trajectories) + `search_count`.
  15 A–O tests (`tests/test_search.py`); CLI `run_search.py` (`--dim`,
  `--feature`, `--generations`, `--beam-width`, `--children`, `--steps`,
  `--db`, `--figure`). Real Experiment C search at 160 steps:
  loss[0.05,0.08,0.11,0.14] × force_fmax[0.4,0.8], gen 3, beam 2,
  children 3 → 5 unique worlds, root control scored best (0.6); figure
  `figures/search_beam_scores.png`. Determinism confirmed (bitwise identical
   canonical output across runs). Guard re-baselined to post-1.9 core
   (adds search.py); no prior test weakened. See `TASK_1.9_REPORT.md`.
- **Task 2.0** — DIVERSITY-PRESERVING MULTI-OBJECTIVE DISCOVERY: extends the
  Task 1.9 beam search so the guide preserves multiple behaviorally distinct
  simulations instead of selecting purely by quality, remaining deterministic,
  explainable, sequential and experiment-free in the core — **no
  GA/evolutionary, Bayesian, RL, ML, embeddings/clustering, or scikit-learn
  (by task constraint; stdlib `math` and numpy only)**. Diversity is
  **behavioral, not parameter-based**: distance is computed over Task 1.8
  behavioral features. `src/sim_alchemist/core/behavior.py` gains the
  distance primitive layer — `behavior_vector` (deterministic flat vector,
  None/non-finite -> 0.0, divergence excluded by default, sorted keys),
  `behavior_distance` (Euclidean, symmetric, key-aware, missing/constant/NaN
  safe), `select_diverse_frontier` (greedy `quality_weight × normalized
  quality + diversity_weight × min normalized Euclidean distance to the kept
  frontier`; first slot = highest quality; deterministic tie-break quality
  desc then run_id asc; validates weights finite, non-negative, positive sum)
  and `compute_frontier_diagnostics` / `FrontierDiagnostics` (mean/min/max
  pairwise distance, unique behavioral signatures, mean quality).
  `src/sim_alchemist/core/search.py` gains `SelectionProfile
  (quality_weight=1.0, diversity_weight=0.0)` (frozen, validated) and extends
  `SearchSpec`/`SearchCandidate`/`SearchGeneration`/`SearchTiming`/
  `SearchResult` with diversity metadata — `selection_quality_score`,
  `selection_diversity_score` (min Euclidean dist to kept frontier),
  `selection_combined_score`, `selection_reason` (only `selection_*` fields
  and the spec `selection_profile` are persisted; the in-memory
  `behavior_vector` is excluded from `as_dict`), per-generation
  `FrontierDiagnostics`, final `frontier_diagnostics`, and a new
  `SearchTiming.n_distance_calcs` (diversity-greedy distance evaluations
  only; quality-only searches report 0). `SearchRunner.search` is
  diversity-aware yet **`SelectionProfile(diversity_weight=0)` reproduces
  Task 1.9 beam behaviour bitwise** (unit-proven). Also fixes a stale
  `by_run_id` lookup in the final ranking and adds `explain_selection()`/
  `explain_frontier()`. **Normalization**: explicit per-feature min-max over
  the candidate pool; constant dimensions -> 0.0; missing keys -> 0.0;
  non-finite (NaN/inf) -> 0.0. 21 tests (`tests/test_diversity.py`,
  checks A–L / A–F profile / A–C [ia/ib/ic] Experiment C integration); CLI
  `run_search.py` adds `--quality-weight`/`--diversity-weight` and
  `--compare`/`--compare-figure` (2-panel figure). Real Experiment C
  comparison at identical budget (loss[0.05,0.08,0.11,0.14] ×
  force_fmax[0.4,0.8], gen 3, beam 4, children 3) with weights 0.2/0.8: 5
  unique worlds each, 3/4 beam overlap; diversity-aware retained a
  low-quality but behaviorally distant 4th signature (mean quality 0.416 vs
  0.4204 quality-only) while raising frontier spread —
  `figures/search_diversity_beam.png`, `figures/frontier_diversity_compare.png`,
  `figures/frontier_diversity_compare_wide.png`. Guard re-baselined to
  post-2.0 core (search.py, behavior.py, __init__.py); no prior test
  weakened. See `TASK_2.0_REPORT.md`.
- **Task 2.1** — CROSS-COMPOSITION COMPATIBILITY & DISCOVERY DESIGN (PLAN-ONLY):
  audit of the capability/coupling/executable gap, the coupling graph, the
  composition matrix, the `CouplingContract` model, `CompositionSpace`/
  `CompositionSearcher` design, resolver stages (capability → contract →
  schedule/clock), science-safety rules, and the exact minimal §14 Build task.
  **No source modified.** See `TASK_2.1_DESIGN.md`.
- **Task 2.2** — COUPLING-CONTRACT LAYER + PRE-EXECUTION COMPOSITION VALIDATION
  (Build mode of Task 2.1 §14): new `src/sim_alchemist/core/contracts.py`
  (`CouplingContract`, `PayloadItem`, `ContractIssue`, `UnresolvedContractError`,
  `resolve_contracts`, `adapter_by_id`, `contracts_key`); optional `contracts=`
  threaded through `compose`/`compose_into` (stage order resolve_capabilities →
  resolve_contracts → _install); adapter `variant`/`state_keys`/`grid`/
  `coordinate_system` metadata on `BaseAdapter` + the five concrete adapters;
  real declared contracts colocated in each coupling module
  (`MORPHOGENESIS_CONTRACTS`, `FIELD_GUIDED_MOVERS_CONTRACTS`,
  `NETWORK_MORPHOGENESIS_CONTRACTS`); facades pass `contracts=`; `run_network_world`
  switched from positional indexing to id+variant `adapter_by_id`. Resolver
  validates presence → capabilities → variant binding → payload (keys/shapes) →
  timing/mechanism → coordinate system → grid → self-edge, **never inventing
  couplings**; gap-proof test: Exp C world with `pymunk`→`MoversAdapter` passes
  `resolve_capabilities` yet `compose(..., contracts=NETWORK_MORPHOGENESIS_CONTRACTS)`
  raises `UnresolvedContractError` before `_install`. `contracts=` vs `None`
bitwise-identical science for A/B/C. Guard re-baselined to post-2.2 core
   (contracts.py, composer.py, __init__.py); no prior test weakened. Full suite
   233 passed; validation A–G / stability S1–S6 / ruff / pyright all clean.
   See `TASK_2.2_REPORT.md`.
- **Task 2.3 Build Stage 3+4+5** — COUPLING TEMPLATES + WORLD GENERATION +
  COMPOSITION CATALOG: new `src/sim_alchemist/core/templates.py`
  (`CouplingTemplate`, `CouplingTemplateRegistry`, `classify_composition`,
  `CompositionVerdict`, `composition_id`/`template_composition_id`,
  `generate_world`) and `catalog.py` (`CompositionCatalog`, `CatalogCandidate`);
  `world.py` gains the optional `ComponentSpec.variant` stamp (world/run
  identity is now variant-aware). Experiment-owned templates co-located in the
  three coupling modules (`build_*_template`), surfaced by
  `experiments/catalog.py` (`repository_surfaces`/`bindings`/`templates`,
  `build_repository_adapters`, `build_repository_catalog`) and demoed by
  `run_catalog_demo.py`. The ordered 6-status funnel
  (CAPABILITY_INVALID → COUPLING_UNAVAILABLE → COUPLING_INVALID →
  SCHEDULE_INVALID → CLOCK_INVALID → EXECUTABLE) is deterministic, static
  (adapters only constructed for template-matched shapes, never
  initialized/stepped), and never infers contracts. Exact classification of
  the 23-shape universe: **16 CAPABILITY_INVALID / 4 COUPLING_UNAVAILABLE /
  3 EXECUTABLE**. Slow bitwise proof: generated worlds reproduce the A/B/C
  facade trajectories exactly. Guard re-baselined (sanctioned extension):
  `__init__.py`, `world.py` re-pinned; `templates.py`, `catalog.py` added;
  no prior test weakened. Full suite **359 passed** (353 fast + 6 slow);
  validation A–G / stability S1–S6 / ruff / pyright all clean.
  See `TASK_2.3_REPORT.md` + `TASK_2.3_CHECKPOINT.md`.

Result: **Baseline v0.1 + Task 1.2–1.3–1.5–1.6–1.7–1.8–1.9–2.0–2.1(design)–2.2(contracts)–2.3(Stage 1+2+3+4+5)** — a reproducible, uv-locked,
pytest-wrapped, validated prototype with a generic composition core in
`src/sim_alchemist/core/` that now drives three independent composed
experiments (A chemo-morphogenesis, B field-guided movers, C adaptive network)
over six generic layers: mutation/lineage/runner, deterministic
sweeps + ranking, behavioral characterization + interestingness ranking,
guided beam search over world variants, diversity-preserving
multi-objective discovery over that search, and the declarative coupling-
template/catalog composition layer.

### NEXT
- **Task 2.4 Build Stage 4** (cross-composition ranking / discovery frontier
  over the Stage 3 common-observable envelope) — see `TASK_2.4_DESIGN.md` §18.
  **Stage 3 (common cross-composition observables) complete; Stage 4 not
  started. Do not start until issued.** (Stage 3 delivered
  `CommonObservable`/`CommonObservableSet`/`common_observable_names`/
  `extract_common_observables` in the new `core/observables.py`, re-exports in
  `__init__.py`, and the 30-fast/1-slow Stage 3 suite — one deterministic
  observable set per evaluated composition over the sorted union of the
  executors' metric names (missing = explicit `available=False`/`value=None`),
  horizon captured from the generated worlds, pure O(n) extraction that
  reuses the in-memory evaluations (no re-run, no persistence, world
  immutable), evaluation/extraction timing split in `CompositionSearchTiming`,
  canonical embedding in `CompositionSearchResult` with Stage 2 contracts
  intact; see `TASK_2.4_STAGE3_REPORT.md`.)
- Plugin/adapter registry (extensible `ComponentRegistry` with external
  adapters and capability discovery).
- Generalized world composition beyond `compose()` (world graph, runtime
  mutation, experiment database).
- Deterministic replay (the foundation is here; cross-platform replay needs
  careful version pinning).
- Phase 0 remaining: CLI.

### DEFERRED
- Plugin marketplace
- FMI integration
- Mosaik integration
- Distributed execution
- FastAPI API layer
- React / PixiJS visualization frontend
- SQLite experiment/lineage database
- Advanced mutation framework (genetic/automated-evolution pipelines)

---

## 1. Project Vision

Simulation Alchemist is a composition engine that discovers, adapts, and orchestrates independent simulation backends into unified worlds. The system does not simulate directly — it composes. A user describes a desired world in structured YAML. The system reasons about capabilities, finds compatible engines, wires them together, and runs the emergent result.

The core insight: a world is not a simulation — it is a graph of simulations with shared state and synchronized time. The magic happens at the composition layer, not in any individual engine.

---

## 2. MVP Definition

The MVP must prove that the composition engine works — that independent simulation systems can be discovered, matched, wired, and run as a unified world.

**MVP scope:**
- A working composition engine with capability/compatibility reasoning
- 3 external simulation adapters (physics, cellular automata, agent-based)
- A shared world model and simulation clock
- An event bus for inter-simulation communication
- A mutation engine for parameter changes
- A deterministic replay system
- Minimal visual output showing emergent behavior

**MVP scope excludes:**
- Natural language understanding (use structured YAML)
- Plugin marketplace
- Distributed execution
- Any custom physics/renderer/engine implementation

---

## 3. Recommended First Simulation Experiment: Fungal Network

**Concept:** An underground ecosystem where:
1. **Cellular automata** grows fungal mycelium patterns through soil
2. **Physics particles** simulate nutrient diffusion through porous soil
3. **Agent-based insects** forage the fungi, modify soil structure, and compete
4. **Weather system** cycles rain/drought affecting growth rates

**Why this works:**
- Visually compelling: glowing fungal networks spreading through soil, insects moving, rain particles
- Emergent behavior is obvious: insects farm fungi → fungi alter soil porosity → water flows differently → weather patterns change insect behavior
- Each component is independently swapable
- Demonstrates the composition thesis perfectly: no single system could produce this behavior

**Alternative rejected:** Cities, disasters, traffic, autonomous driving — too common, misses the novelty of composition.

---

## 4. Recommended External GitHub Repositories

### 4.1 Pymunk (viblo/pymunk) — Physics Adapter (VALIDATED in Baseline v0.1)
| Attribute | Value |
|-----------|-------|
| License | MIT |
| Headless | Yes (no GUI dependencies) |
| Deterministic | Yes — fixed-step `space.step(dt)` with same initial state |
| Step API | space.step(dt) |
| State access | Full — bodies, shapes, forces, velocities |
| Event injection | External forces/moment at body COM; collision handlers |
| Integration | pip install pymunk; pinned at 7.3.0 in uv.lock |
| Status | Baseline v0.1 physics engine — wall rods are dynamic rigid bodies |

**Why Pymunk over PyBullet:** the validated prototype (Task 0.3) already uses
Pymunk. It is a pure-Python/CFFI 2D engine with explicit fixed timesteps, no
PyTorch/GPU requirement, and passes the same-runtime determinism and
bounded-force stability checks (S1–S6). PyBullet remains an option for 3D
rigid-body worlds later, but it is **not** the MVP physics engine.

### 4.2 Mesa (projectmesa/mesa) — Agent-Based Adapter
| Attribute | Value |
|-----------|-------|
| License | Apache 2.0 |
| Headless | Yes (no GUI required) |
| Deterministic | Yes with fixed seed |
| Step API | model.step() |
| State access | Full — agents, grid, schedule |
| Event injection | Yes — place agents, modify parameters |
| Integration | pip install mesa |

### 4.3 py-pde (zwicker-group/py-pde) — Continuous Field Adapter (VALIDATED)
| Attribute | Value |
|-----------|-------|
| License | Apache 2.0 |
| Headless | Yes (numpy backend, no GUI) |
| Deterministic | Yes — explicit time stepping on a fixed grid/seed |
| Step API | eq.solve(state, t_range, dt, backend="numpy") |
| State access | Full — scalar/vector field data |
| Event injection | Yes — domain mask field mutated in place per macro step |
| Integration | pip install py-pde; pinned at 0.58.0 in uv.lock |
| Status | Baseline v0.1 continuous field engine — Schnakenberg reaction-diffusion |

**Why py-pde over gridlife:** the validated prototype (Tasks 0.2/0.3) uses
py-pde for the morphogen field. It exposes compiled symbolic RHS equations
(SymPy lambdify), a numpy backend, and in-place mask mutation that maps
directly onto the clamped-obstacle wall model. gridlife (Lenia, Gray-Scott,
SmoothLife) remains an option for cellular-automata worlds later, but it is
**not** part of the validated baseline.

---

## 5. License Considerations

All selected dependencies are permissive license (Apache 2.0 or MIT). No copyleft concerns. No GPL contamination risk.

| Component | License | Redistribution Risk |
|-----------|---------|-------------------|
| PyBullet | Apache 2.0 | None |
| Mesa | Apache 2.0 | None |
| gridlife | MIT | None |
| FastAPI | MIT | None |
| SQLite | Public Domain | None |

---

## 6. Proposed System Architecture

The composition engine is the only system that knows about external simulators. External simulators know nothing about Simulation Alchemist. All communication flows through adapters.

Composition Engine → Capability Registry → Compatibility Engine → World Composer → Simulation Clock → Event Bus → World State → Mutation Engine → Experiment Runner

Adapters: PhysicsAdapter → Pymunk, FieldAdapter → py-pde, AgentAdapter → Mesa

---

## 7. Adapter Architecture

### 7.1 Base Interface

class SimulationEngine(Protocol):
    id: str
    name: str
    version: str
    capabilities: list[Capability]
    requirements: list[Requirement]
    deterministic: bool
    timestep: float
    license: str

    def initialize(self, config: dict) -> WorldState: ...
    def step(self, dt: float) -> StepResult: ...
    def get_state(self) -> dict: ...
    def apply_event(self, event: Event) -> bool: ...
    def shutdown(self) -> None: ...

### 7.2 Adapter Responsibilities

Each adapter wraps an external simulation engine, translates between its API and the internal SimulationEngine protocol, exposes provides/requires capabilities, translates events, and maintains a local seed for determinism.

### 7.3 Adapter Discovery

Adapters are discovered via Python entry points (setuptools).

---

## 8. Capability/Compatibility Model

Components declare what they provide and require:

component:
  id:  pybullet-rigid-001
  adapter: pybullet
  provides:
    - id: rigid_body
      schema: physics/rigid/v1
  requires:
    - id: world_geometry
      min_version: 1.0.0
  timestep: 1/240.0
  deterministic: true

The compatibility resolver matches requirements to providers. MVP uses greedy algorithm; production could use SAT solver.

---

## 9. Event Model

**MVP:** In-process asyncio.Queue-based event bus. Zero external dependencies.
**Phase 2:** Redis Streams for persistence, replay, and multi-process support.

Event types: ENTITY_SPAWNED, STATE_CHANGED, PARAMETER_MUTATED, COMPONENT_ADDED, SIMULATION_ERROR, TIME_STEP.

Three consumer groups: state subscribers, mutation subscribers, telemetry subscribers.

---

## 10. Time Synchronization Model

External simulators have different timestep rates:
- PyBullet: 1/240s per step
- Mesa: configurable (typically 1.0s per step)
- gridlife: configurable

**Solution:** Master clock advances at fixed dt. Each adapter maps global timestep to native timestep by integer multiples. Divisibility validated at composition time.

**Deterministic Time:** Time is purely numeric — no wall-clock dependency. The seed initializes all RNG sources.

---

## 11. World State Model

Unified WorldState contains: time, seed, entities (dict across all components), channels (inter-component state), and metadata. All adapters declare their coordinate system. The world state normalizes to a canonical system (right-handed, Y-up, meters).

---

## 12. Mutation Architecture

**Mutation Targets:** PARAMETER, ENVIRONMENT, AGENT_BEHAVIOR, RESOURCE_RULE, INTERACTION_RULE, PROBABILITY, TOPOLOGY, COMPONENT.

Every run records: run_id, parent_run_id, seed, mutation_set, configuration, metrics, result_state, duration. The lineage graph is stored in SQLite as a directed acyclic graph.

**Mutation Engine:** Three modes: Manual (YAML), Automated (random within bounds), Genetic (crossover + selection). MVP: Manual + automated random mutation.

---

## 13. Experiment Lineage Model

Each Experiment has an experiment_id, root_config, generation, population of RunRecords. Each RunRecord has: run_id, parent_run_id, seed, mutation_set, configuration, metrics, result_state, duration.

**Evolution Pipeline:**
- generate_worlds: 100
- execute_parallel: true
- collect_metrics → rank top 20% → mutate → next_generation

---

## 14. Repository Structure

**Current repository (Baseline v0.1, as-built):**

`
simulation project/
├── AGENTS.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── pyproject.toml           # uv project, Python 3.13, exact validated deps
├── uv.lock                  # reproducible environment
├── .gitignore
├── chemomech/               # validated prototype
│   ├── simulation.py        # composition / orchestration loop (un-refactored)
│   ├── reaction_diffusion.py
│   ├── physics.py
│   ├── agents.py
│   └── validate.py
├── tests/                   # pytest wrappers over the same scientific checks
│   ├── test_feedback.py
│   ├── test_determinism.py
│   └── test_stability.py
├── figures/                 # baseline evidence (task-mandated filenames)
├── run_validation.py
├── run_stability.py
└── simulation_projects_report.txt
`

**Planned structure (Simulation Alchemist core, to be extracted):**

`
simulation-alchemist/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── IMPLEMENTATION_PLAN.md
├── LICENSE
├── docs/
├── src/sim_alchemist/
│   ├── core/engine.py, clock.py, world_state.py, event_bus.py, compatibility.py
│   ├── adapters/base.py, pybullet_adapter.py, mesa_adapter.py, gridlife_adapter.py, registry.py
│   ├── world/composer.py, definition.py, validator.py
│   ├── mutation/engine.py, lineage.py, tracker.py
│   ├── experiment/runner.py, metrics.py, scheduler.py
│   ├── persistence/database.py, replay.py
│   ├── telemetry/metrics_collector.py, event_logger.py
│   └── cli/main.py
├── tests/
├── examples/fungal_network.yaml
└── configs/default.yaml
`

---

## 15. Technology Choices with Reasoning

**Baseline v0.1 (VALIDATED, as-built):**

| Layer | Choice | Evidence |
|-------|--------|----------|
| Composition / orchestration | generic core composer | `src/sim_alchemist/core/{world,registry,composer,engine}.py` + `worlds/*.yaml` |
| Continuous field engine | py-pde 0.58.0 | Schnakenberg RD, maskable walls, clamped obstacles |
| Rigid-body physics engine | Pymunk 7.3.0 | dynamic wall rods, bounded forces, bounds clamping |
| Agent engine | Mesa 3.5.1 | deterministic sensing/decision agents |
| Vision / figures | numpy / matplotlib 3.11.1 | checks A–G + figures in `figures/` |
| Build / env | uv + pyproject.toml + uv.lock | reproducible, Python 3.13 |
| Validation | pytest + hypothesis + ruff + pyright | wraps A–G and S1–S6 |

**Planned (after extraction):**

| Layer | Choice | Why |
|-------|--------|-----|
| Core engine | Python 3.12+ | Fastest path to MVP, largest simulation library ecosystem |
| API | FastAPI | Async-native, excellent simulation APIs, auto OpenAPI docs |
| Frontend | React Three Fiber | R3F provides React integration for 3D visualization |
| Messaging | asyncio.Queue (MVP) | Zero external dependencies, simplest |
| Persistence | SQLite | Zero server, file-based, Python stdlib |
| Determinism | random.Random(seed) | Both Python and NumPy support explicit seeding |
| Build | uv + pyproject.toml | Fast, modern, entry points enable adapter discovery |
| Visualization | matplotlib server-side | MVP: 2D top-down view. 3D comes later. |

**What can wait:** Distributed execution, NLP, plugin marketplace, advanced visualization, custom renderers, multi-machine parallelism, production auth, Docker deployment, CI/CD pipeline.

---

## 16. Development Phases

**Baseline context:** Tasks 0.1–0.3 produced the validated chemo-mechanical
prototype; Tasks 1.2–1.3 extracted the reusable core (scheduler, composition
layer, world model, adapter protocol, capability schema, YAML worlds) and
validates both experiments through the generic `AlchemistEngine` + core
`StepScheduler`.  The remainder of Phase 0 (plugin registry, mutation engine,
SQLite persistence) and Phase 1+ now proceed on the extracted foundation.

### Phase 0: Foundation (Week 1-2)
Project scaffolding, SimulationEngine protocol, in-process event bus, simulation clock, SQLite persistence, basic CLI.

### Phase 1: First Composition (Week 3-4)
PyBullet adapter, Mesa adapter, gridlife adapter, capability schema, composition engine, world YAML parser, state exchange.

### Phase 2: MVP Experiment — Fungal Network (Week 5-6)
Define fungal_network.yaml, wire all 3 adapters, nutrient diffusion channel, foraging behavior, clock synchronization, visual output.

### Phase 3: Mutation & Replay (Week 7-8)
Mutation engine, experiment lineage graph, deterministic replay, metrics collection, CLI commands.

### Phase 4: Automation & Scale (Week 9-10)
Parallel experiment runner, automated mutation pipeline, experiment ranking, web visualization.

### Phase 5: Polish & Harden (Week 11-12)
Comprehensive test suite, documentation, performance profiling, plugin system formalization, Redis Streams.

---

## 17. Testing Strategy

**Unit Tests:** Each adapter in isolation, capability resolver, event bus, mutation engine.
**Integration Tests:** Full composition of 3+ adapters, deterministic replay, event propagation, state exchange validation.
**Property Tests (Hypothesis):** Valid world definition → clear success/failure, same seed → identical state, mutation → measurable difference.
**Determinism Tests:** 100 runs with same seed → identical world_state bytes, replay from seed → identical output.

---

## 18. Biggest Technical Risks

1. **Timestep synchronization** — Different engines have different native timesteps. Finding a common tick is non-trivial. **Mitigation:** Use a master dt that is a common multiple of all adapter timesteps. Validate at composition time.

2. **State serialization between heterogeneous engines** — PyBullet state, Mesa state, and gridlife state have completely different structures. **Mitigation:** Define a minimal shared protocol. Adapters translate. Share only what's necessary.

3. **Determinism across external engines** — Each engine has its own determinism model. **Mitigation:** Each adapter wraps the engine's seeding mechanism. Test determinism explicitly.

4. **Dependency conflicts** — PyBullet, Mesa, gridlife have different transitive dependencies. **Mitigation:** Use uv for strict dependency resolution.

---

## 19. What Should Explicitly NOT Be Built Yet

Custom physics engine, custom renderer, natural language interface, plugin marketplace, Kubernetes/distributed infrastructure, authentication/authorization, multi-tenant support, LLM integration, agent orchestration frameworks (LangChain, AutoGen), WebSocket server, Docker deployment, CI/CD pipeline, mobile app, VR/AR visualization.

---

## 20. First 10 Implementation Tasks (In Order)

1. **Initialize project scaffolding** — DONE in Baseline v0.1: uv project, pyproject.toml with validated deps, uv.lock, git repo with AGENTS.md, reproducible `.venv`
2. **Define SimulationEngine protocol and Capability schema** — Create the base interface in src/sim_alchemist/adapters/base.py
3. **Build the in-process event bus** — src/sim_alchemist/core/event_bus.py using asyncio.Queue
4. **Build the simulation clock** — src/sim_alchemist/core/clock.py with tick(), time, speed, adapter timestep mapping
5. **Build the SQLite persistence layer** — src/sim_alchemist/persistence/database.py for runs, mutations, lineage
6. **Implement PyBullet adapter** — Wrap pybullet.DIRECT mode, register capabilities (rigid_body, gravity, collision)
7. **Implement Mesa adapter** — Wrap a Mesa Model, register capabilities (agent, spatial_grid, scheduler)
8. **Implement gridlife adapter** — Wrap a gridlife simulation, register capabilities (cellular_automata, reaction_diffusion)
9. **Build the composition engine and capability resolver** — src/sim_alchemist/core/engine.py with greedy resolver
10. **Create the first composed world: Fungal Network** — Write examples/fungal_network.yaml, wire all 3 adapters, run full simulation cycle

---

## Appendix: AGENTS.md Context

This repository contains the Simulation Alchemist project. Key references:
- Core protocol: src/sim_alchemist/adapters/base.py
- World definitions: examples/*.yaml
- Tests: tests/
- This plan: IMPLEMENTATION_PLAN.md
