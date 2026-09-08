# AGENTS.md

> **Quick recovery:** before substantial work, read `PROJECT_STATE.md` (the
> canonical compact snapshot of task/milestone status) and inspect the actual
> repository state — do NOT trust previous conversation context.

## Project: Simulation Alchemist — Baseline v0.1

A framework for composing multiple independent simulation systems into a
unified simulated world. This repository currently holds **Baseline v0.1**:
the validated chemo-mechanical prototype (Tasks 0.1–0.3) plus the Task 1.2
scheduler, the **Task 1.3 declarative composition layer**, the **Task 1.5
Adaptive Network Morphogenesis experiment (Experiment C)**, the **Task 1.6
generic mutation / lineage / variant-runner layer**, the **Task 1.7
generic sweep / ranking layer**, and the **Task 1.8
behavioral-characterization / interestingness layer**, and the **Task 1.9
guided simulation search / first discovery loop**, and the **Task 2.0
diversity-preserving multi-objective discovery layer**, and the **Task 2.1
cross-composition compatibility & discovery design (PLAN-ONLY)**, the
**Task 2.2 coupling-contract layer + pre-execution composition validation**
(`core/contracts.py`, optional `contracts=` on compose, adapter variant/capability/
grid/payload metadata), the **Task 2.3 Build Stage 1+2 composition
shape/space layer** (`core/composition.py`: `ComponentBinding`/
`CompositionShape`/`CompositionSpace` + static capability filter
CAPABILITY_VALID/CAPABILITY_INVALID, deterministic bounded enumeration with
variant exclusivity), and the **Task 2.3 Build Stage 3+4+5 composition
layer** (`core/templates.py`: `CouplingTemplate`/`CouplingTemplateRegistry` +
the COUPLING_UNAVAILABLE/COUPLING_INVALID/SCHEDULE_INVALID/CLOCK_INVALID/
EXECUTABLE taxonomy, `generate_world`, `composition_id`; `core/catalog.py`:
`CompositionCatalog`/`CatalogCandidate`; `world.py` `ComponentSpec.variant`
stamping), the **Task 2.4 Build Stage 1 cross-composition discovery
result layer** (`core/composition_search.py`: `CompositionEvaluation`/
`composition_discovery_id_of`/`evaluate_composition_baseline`, additive
`RunRecord.composition_id` lineage stamp with pre-2.4 `_migrate()`, plus the
conforming A/B executors in `chemomech/experiment.py` and
`experiments/field_guided_movers/experiment.py` and the experiments-owned
`repository_executors()` composition→executor map), and the **Task 2.4 Build
Stage 2 thin `CompositionSearcher` orchestrator** (`core/composition_search.py`:
`CompositionSearcher`/`CompositionSearchSpec`/`CompositionSearchResult`/
`CompositionSearchTiming`/`CompositionSearchError`; enumerate `catalog.executable()`
in canonical order, evaluate one baseline per EXECUTABLE composition through the
Stage 1 result layer via the opaque id→executor map, compact *unranked* result
with deterministic replay; no ranking/behavior/frontier/visualization) — the
verified starting
point for the framework. Three
experiments (A: chemo-morphogenesis, B: field-guided movers, C: adaptive network
morphogenesis) execute through the generic `AlchemistEngine` + core `StepScheduler`
against declaratively-described worlds; the science, scheduling, and declared
coupling contracts live in experiment coupling modules, not in engine subclasses.
**Next milestone: Task 2.4 Build Stage 4 (cross-composition ranking / discovery
frontier over the common-observable layer), not
started. Robot do NOT start Task 2.4 Build Stage 4 until it is issued.**

## Current Repository State (validated prototype — do not paper over)

Three independent simulation subsystems are wired into one deterministic
closed loop:

- **Mesa** — agent subsystem. `WallBuildingAgent` senses the morphogen field,
  decides where to deposit/dissolve walls. Owned by `chemomech/agents.py`.
- **py-pde** — continuous reaction-diffusion subsystem. Schnakenberg field on
  a masked grid where wall cells are frozen. Owned by `chemomech/reaction_diffusion.py`.
- **Pymunk** — rigid-body/wall subsystem. Dynamic rod bodies driven by
  field-gradient forces, with damping and bounds clamping. Owned by
  `chemomech/physics.py`.
- **chemomech/simulation.py** — the Experiment A facade entry point (slim).
  It now composes its world through the generic core composer; the science and
  the coupling rules live in `chemomech/coupling.py`.
- **chemomech/coupling.py** — Experiment A coupling: the declared macro-step
  order (`MORPHOGENESIS_SCHEDULE`), the field-gradient force rule, the agent
  wall-intention translation, observable recording, and the declarative world
  builder.
- **experiments/field_guided_movers/coupling.py** — Experiment B coupling:
  `FIELD_GUIDED_MOVERS_SCHEDULE`, gradient→force and mover→source rules, the
  world builder, and the registry override that swaps the experiment's
  point-mover adapter under the `pymunk` component id.
- **NDlib** — network subsystem (Experiment C). `AdaptiveNetworkAdapter`
  (`experiments/network_morphogenesis/adapter.py`, `engine_id="network"`)
  wraps NDlib's `ContinuousModel` for continuous node *loads* that diffuse
  over a grid graph via a custom weighted-averaging / transport rule; it
  provides the `network_diffusion` capability (and `agent_intentions`, so the
  wall `pymunk` adapter's requirement is met without Mesa). Integer node
  labels are mandatory (NDlib/AGraph limitation).
- **experiments/network_morphogenesis/coupling.py** — Experiment C coupling:
  the declared macro-step order (`NETWORK_MORPHOGENESIS_SCHEDULE`: geometry
  sync → field step → physics force/step → wall growth → network step →
  route → field source → record), the gradient/force and load/source rules,
  the world builder, and the registry that adds the `network` component id on
  top of the core `default_registry()`.
- **src/sim_alchemist/core/** — Task 1.3 composition core:
  `world.py` (typed `WorldDefinition`/`ComponentSpec`, YAML load/save),
  `registry.py` (`ComponentRegistry` + `default_registry()`), `composer.py`
  (`compose`/`compose_into`/`build_components`/`resolve_capabilities`),
  `engine.py` (generic `AlchemistEngine` that installs a composed world and
  dispatches it through the core scheduler).
- **src/sim_alchemist/core/mutation.py** — Task 1.6 generic, deterministic
  world mutation: `Mutation`/`MutationRecord`/`ParameterSpec`, immutable
  `apply_mutation`/`apply_mutations` (deep-clone + rebuild, parent never
  edited), `clone_world`, `range_validator`/`one_of`. Path grammar is
  dot-separated data navigation only (no `eval`); structural fields are
  immovable.
- **src/sim_alchemist/core/lineage.py** — Task 1.6 SQLite-backed lineage:
  `LineageStore` (metadata + compact metrics only, never trajectories),
  `RunRecord`, deterministic `run_id_of` (sha256 of world content + seed).
- **src/sim_alchemist/core/runner.py** — Task 1.6 `VariantRunner` (executor:
  any `WorldDefinition` → `ExecOutcome`), `compare_metrics`/`compare_runs`
  (generic per-metric `MetricDelta`), `MissingParentRunError`.
- **src/sim_alchemist/core/sweep.py** — Task 1.7 generic, deterministic variant
  **sweeps + ranking**: `ParameterSweep`/`MutationSpace` (Cartesian products,
  documented `itertools.product` ordering — right-most dimension fastest),
  `sweep_id_of` (deterministic from world hash + space), `SweepRunner`
  (validates the whole space against the declared specs before any simulation,
  runs the **baseline control first**, skips+counts no-ops, records everything
  into the lineage store, `SweepTiming` instrumentation), `rank_results`/
  `RankingEntry` (metric by name, direction, deterministic tie-break by run id).
- **src/sim_alchemist/core/behavior.py** — Task 1.8 generic, deterministic
  **behavioral characterization + interestingness**: `ObservableSeries`
  (validated, `resample_to`), 18 per-observable features (temporal / trend /
  oscillation / stability / divergence) with documented stdlib formulas
  (counts-only sign changes, `|lag1 autocorr of detrended residual|`, can't
  claim oscillation for a single step; divergence compares variants resampled
  onto the baseline's time axis; baseline divergence is `None` — never 0),
  `InterestingnessProfile` (explicit weights + max/min directions — 
  "interesting ≠ largest value"), `rank_by_profile` (min-max normalization
  across the population, `run_id` tie-break), `RankedRow.explanation()`,
  `BehavioralAnalysisRunner` (Task 1.6/1.7 machinery reused),
  `behavior_analysis_id_of`. Only compact feature snapshots and analysis
  records are persisted (never trajectories). Task 2.0 adds the behavioral-
  distance primitives for diversity-aware selection: `behavior_vector`,
  `behavior_distance` (Euclidean, missing/non-finite -> 0.0),
  `select_diverse_frontier`, `compute_frontier_diagnostics`,
  `FrontierDiagnostics`.
- **src/sim_alchemist/core/templates.py** — Task 2.3 (Stage 3+4) coupling
  templates + world generation: `CouplingTemplate` (frozen authoring surface:
  bindings/world_id/contracts/schedule/operations/requires/executor_ref/
  component_configs/clock), `CouplingTemplateRegistry` (register-only,
  `DuplicateTemplateError`, lookup by canonical shape), `classify_composition`
  (the ordered 6-status funnel: capability → template → contracts → schedule →
  clock → EXECUTABLE; contracts never inferred; adapters only *constructed* for
  template-matched shapes), `composition_id` (content-addressed 24-hex),
  `generate_world(template)` (deterministic, immutable, adapter-free
  `WorldDefinition` with `ComponentSpec.variant` stamped per binding).
- **src/sim_alchemist/core/catalog.py** — Task 2.3 (Stage 5) composition
  catalog: `CompositionCatalog` pre-classifies the whole enumerated space
  (constructor-only builds for matched shapes; nothing simulated/persisted/
  searched), `CatalogCandidate` (shape/status/reason/composition_id/generated_
  world) with `generated_world_available` for EXECUTABLE rows; query APIs
  `all/executable/invalid/by_status/by_shape_id/status_counts/explain`.
- **src/sim_alchemist/core/composition_search.py** — Task 2.4 Build Stage 1
  cross-composition evaluation result layer: `CompositionEvaluation` (one immutable
  evaluated-composition-baseline snapshot reusing `run_id_of`/`world_hash`),
  `CompositionEvaluationError`, `composition_discovery_id_of` (deterministic
  content-addressed 24-hex discovery-pass identity over the catalog's composition
  universe + profile + seed + evaluation config, no transient data),
  `evaluate_composition_baseline` (EXECUTABLE-only, `generated_world`-required;
  records a root run `parent_run_id=None` with its `composition_id`; idempotent on
  the deterministic run id), plus the **Task 2.4 Build Stage 2 thin
  `CompositionSearcher` orchestrator** (`CompositionSearcher`/`CompositionSearchSpec`/
  `CompositionSearchResult`/`CompositionSearchTiming`/`CompositionSearchError`;
  enumerate `catalog.executable()` in canonical order, evaluate one baseline per
  EXECUTABLE composition through the Stage 1 result layer via the opaque id→executor
map, compact *unranked* result with deterministic replay — no ranking/behavior/
   frontier/visualization), plus the **Task 2.4 Build Stage 3 common-observable
   chapter** (`search` attaches one deterministic `CommonObservableSet` per evaluated
   composition in catalog order — sorted union of executor metric names, missing =
   explicit `available=False`/`None`; pure O(n) extraction reusing the in-memory
   evaluations, no re-run, no persistence, world immutable; evaluation/extraction
   timing split; no ranking/behavior/frontier/visualization), and the additive
   `RunRecord.composition_id` stamp on
   the lineage store with pre-2.4 `_migrate()`.
- **src/sim_alchemist/core/observables.py** — Task 2.4 Build Stage 3 common
   cross-composition observables: `CommonObservable` (frozen name/`value`/`available`
   triple; `available⇔non-None`, verbatim floats), `CommonObservableSet` (per
   evaluated composition — composition_id/shape_id/world_hash/run_id/world_id/
   status/seed/horizon + observables sorted by name; `names`/`available_names`/
   `missing_names`, `observable(name)`, `as_dict`), `CommonObservableError`,
   `common_observable_names` (deterministic sorted union of executor metric names
   across the evaluated pool), `extract_common_observables` (pure projection of one
   evaluated baseline onto the common vocabulary; composition-specific names
   elsewhere become explicit missing rows; horizon from the generated world with
   id/hash validation; structural/type-checked errors; nothing simulated/persisted).
- **src/sim_alchemist/core/search.py** — Task 1.9 **guided beam search over `SearchSpec` (frozen, validated config: name,
  generations, beam_width, children_per_parent, mutation_space, profile,
  seed, optional selection_profile), `child_mutations` (dimension-major,
  value-minor, no-op skip, single-param children, truncation), `SearchRunner`
  (sequential beam search: gen 0 = root control, each generation mutates beam
  via `child_mutations`, runs unique children, ranks pool via
  `rank_by_profile`, keeps `beam_width` best — or, with a **`SelectionProfile`
  (quality_weight, diversity_weight)**, keeps a greedy diversity-aware frontier:
  `qw × normalized quality + dw × min normalized behavioral distance to the
  selected frontier`; first slot = highest quality; `diversity_weight=0`
  reproduces Task 1.9 exactly), `SearchCandidate` / `SearchGeneration` /
  `SearchResult` (full in-memory outcome with `best()`, `lineage_path()`,
  `mutation_path()`, `explain_best()`, `explain_selection()`,
  `explain_frontier()`, per-generation + final `FrontierDiagnostics`,
  selection_* score metadata), `SearchTiming` (incl. `n_distance_calcs`),
  `search_id_of` (deterministic 24-hex id). Diversity = **behavioral, not
  parameter-based**: distances are computed over Task 1.8 behavior vectors
  (`behavior_vector` / `behavior_distance` / `select_diverse_frontier` /
  `compute_frontier_diagnostics` in behavior.py; min-max normalization,
  None/non-finite -> 0.0, constant dims -> 0.0). No GA/evolutionary/Bayesian/
  ML/RL/clustering; deterministic and sequential. Reuses existing Task
  1.6/1.7/1.8 machinery; no new simulation concept.
- **src/sim_alchemist/core/lineage.py** — Task 1.6/1.7/1.8/1.9 SQLite-backed
  lineage: `LineageStore` (metadata + compact metrics only, never
  trajectories), `RunRecord`, deterministic `run_id_of` (sha256 of world
  content + seed), plus the Task 1.7 `SweepRecord` and `sweeps` table, plus
  the Task 1.8 per-run `feature_snapshot` and `behavior_analyses` table
  (idempotent metadata; pre-1.8 stores migrate on open), plus the Task 1.9
  `SearchRecord` and `searches` table (compact search metadata, no trajectories;
  pre-1.9 stores migrate on open).
- **experiments/network_morphogenesis/experiment.py** — Task 1.6
  experiment-facing side: `PARAMETER_SPECS` (the three meaningful mutable
  parameters), `build_network_metrics`, `run_network_world` executor; Task 1.8
  adds `build_network_observables` (9 compact per-step series on `t_field`).
- **worlds/** — declarative YAML worlds for Experiments A, B, and C
  (`chemo_morphogenesis.yaml`, `field_guided_movers.yaml`,
  `adaptive_network.yaml`). `component_configs` for the templates are copied
  from these worlds, so generated worlds stay config-identical.
- **experiments/catalog.py** — Task 2.3 (Stage 3+4+5) repository-side
  composition layer: `repository_surfaces()` (five-binding unified universe:
  mesa / py-pde / network / pymunk/walls / pymunk/movers, keyed by
  `(component, variant)` across default + C + B registries),
  `repository_templates()` (the three experiment coupling templates),
  `build_repository_adapters` (constructor-only dispatch), and
  `build_repository_catalog()`. Demo: `run_catalog_demo.py`.

All three experiments are ALSO runnable without their facades: a plain
`AlchemistEngine` composed via `compose(world, registry, operations)` —
proved bitwise identical to the facade path.

This is a **validated scientific prototype**: `run_validation.py`
(checks A–G) and `run_stability.py` (checks S1–S6) pass, and the figures in
`figures/` are baseline evidence. The pytest suite in `tests/` wraps these
same checks.

There is **no** capability discovery, plugin architecture, adapter registry
beyond the in-process `default_registry()`, generalized world composition
beyond `compose()`, or experiment database. Do not document or
implement those as if they existed here.

## What Simulation Alchemist Will Become (NOT yet implemented)

- Capability discovery, plugin architecture, generalized world composition
  beyond `compose()`, and an experiment database
- External-engine adapters beyond the in-process `default_registry()`
  factories
- Shared world model, simulation clock, event bus (already: clock, event bus,
  world state, adapter `SimulationEngine` protocol exist in the validated core)
- Deterministic replay system (partially here: same-runtime replay)

The next phase is extracting reusable Alchemist abstractions (clock, event bus,
world state, adapter protocol, capability model) from this validated prototype.
Do not start building that until the extraction task is issued.

## Key Architecture (as-built)

| Layer | Technology | Module |
|-------|-----------|--------|
| Reaction-diffusion field | py-pde | `chemomech/reaction_diffusion.py` |
| Rigid-body wall physics | Pymunk | `chemomech/physics.py` |
| Agent sensing/decision | Mesa | `chemomech/agents.py` |
| Macro-step scheduler | core (extracted Task 1.2) | `src/sim_alchemist/core/scheduler.py` |
| Network diffusion | NDlib `ContinuousModel` | `experiments/network_morphogenesis/adapter.py` |
| Composition / orchestration | schedules + coupling loop | `chemomech/engine.py`, `experiments/field_guided_movers/model.py`, `experiments/network_morphogenesis/model.py` |
| Task 1.3 composition core | generic core | `src/sim_alchemist/core/{world,registry,composer,engine}.py` |
| Mutation / lineage / variant runner | generic core | `src/sim_alchemist/core/{mutation,lineage,runner}.py` |
| Sweep / ranking layer | generic core | `src/sim_alchemist/core/sweep.py`, `run_sweep.py` |
| Behavior / interestingness | generic core | `src/sim_alchemist/core/behavior.py`, `run_behavior_demo.py` |
| Guided search / discovery | generic core | `src/sim_alchemist/core/search.py`, `run_search.py` |
| Task 2.3 composition (templates/catalog) | generic core | `src/sim_alchemist/core/{templates,catalog}.py`, `experiments/catalog.py`, `run_catalog_demo.py` |
| Task 2.4 Stage 1 composition evaluation | generic core + experiment executors | `src/sim_alchemist/core/composition_search.py`, `chemomech/experiment.py`, `experiments/field_guided_movers/experiment.py`, `experiments/catalog.py` |
| Task 2.4 Stage 2 composition search | generic core | `src/sim_alchemist/core/composition_search.py`, `tests/test_composition_search_stage2.py` |
| Task 2.4 Stage 3 common observables | generic core | `src/sim_alchemist/core/observables.py`, `src/sim_alchemist/core/composition_search.py`, `tests/test_common_observables_stage3.py` |
| Experiment coupling + worlds | YAML + closures | `chemomech/coupling.py`, `experiments/field_guided_movers/coupling.py`, `experiments/network_morphogenesis/coupling.py`, `worlds/*.yaml` |
| Validation A–G + figures | numpy / matplotlib | `chemomech/validate.py` |
| Stability checks S1–S6 | numpy | `run_stability.py` |
| Experiment C mutation layer | generic core + executor | `experiments/network_morphogenesis/experiment.py`, `run_variant_demo.py` |

Each experiment declares its macro-step ordering as a plain ordered tuple of
operation names (`ChemomechanicalEngine.SCHEDULE`, `FieldGuidedMoversEngine.
SCHEDULE`) resolved through that engine's op registry and executed by the
core `StepScheduler`. The scheduler owns ordering, validation, time
progression, and tracing; the science stays in the experiments.

Since Task 1.3 the world, schedule, and component list are *data*: a
`WorldDefinition` (PYAML-loadable) lists the components and their configs, the
declared macro-step order, and the required capabilities. `compose()` resolves
capabilities, builds adapters from the `default_registry()` (Experiments B and
C override / extend it via their own registries), installs them in a plain
`AlchemistEngine`, and dispatches the schedule through the core `StepScheduler`.
The science and the per-operation coupling rules live in the experiment
coupling modules, not in engine subclasses.

## Running the Project (reproducible)

The environment is managed by uv against Python 3.13:

- `uv sync` — install the locked environment into `.venv`
- `uv run python run_validation.py` — full Task 0.3 validation (A–G) + figures
- `uv run python run_stability.py` — stability/boundedness checks (S1–S6)
- `uv run python run_variant_demo.py` — Task 1.6 base/variant/lineage demo
- `uv run python run_sweep.py --dim <path>:v1,v2,... [--dim ...] [--rank-by <metric>]` — Task 1.7 deterministic sweep + ranking demo
- `uv run python run_behavior_demo.py --dim <path>:v1,v2,... --feature <obs>:<feature>:<weight>[:max|min] ...` — Task 1.8 behavioral characterization + interestingness demo
- `uv run python run_search.py --dim <path>:v1,v2,... --feature <obs>:<feature>:<weight>[:max|min] ... [--generations N] [--beam-width N]` — Task 1.9 guided beam search + discovery loop
- `uv run python run_catalog_demo.py [--generate-worlds [--worlds-dir DIR]]` — Task 2.3 composition catalog demo (23 shapes, 16/4/3) + writes the 3 EXECUTABLE worlds
- `uv run pytest` — test suite wrapping the same scientific checks

## Key Development Commands

- `uv run pytest tests/` — run all tests (includes the slow 160-step canonical regression, ~14 min)
- `uv run pytest tests/ -m "not slow"` — fast suite only (~1 min)
- `uv run python -m ruff check .` — lint
- `uv run pyright` — type checking

## Scientific Limitations (must be preserved, not hidden)

- The clamped-obstacle PDE approximation (wall cells frozen) is **not** a true
  no-flux boundary.
- Parameters are hand-tuned for the validated runs.
- The wall model is simplified (thin frictionless rods, walls pass through
  walls).
- The Pymunk/PDE coupling is an experimental model, not a calibrated
  physics/simulation claim.
- The network update is a custom continuous weighted-averaging / transport
  rule over node loads — **not** a physically calibrated nutrient transport
  model; reservoir nodes are recharged to sustain the load gradient.
- Claims of sustained non-equilibrium behaviour remain hypotheses to be tested.
- Deterministic replay is same-runtime/environment; it is not universal
  cross-platform bitwise equivalence.

## Adapter Protocol (future target)

Adapters will implement `SimulationEngine` from `src/sim_alchemist/adapters/base.py`:

```python
def initialize(self, config: dict) -> WorldState: ...
def step(self, dt: float) -> StepResult: ...
def get_state(self) -> dict: ...
def apply_event(self, event: Event) -> bool: ...
def shutdown(self) -> None: ...
```

Full roadmap: see IMPLEMENTATION_PLAN.md.