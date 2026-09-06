# AGENTS.md

## Project: Simulation Alchemist — Baseline v0.1

A framework for composing multiple independent simulation systems into a
unified simulated world. This repository currently holds **Baseline v0.1**:
the validated chemo-mechanical prototype (Tasks 0.1–0.3) plus the Task 1.2
scheduler and the **Task 1.3 declarative composition layer** — the verified
starting point for the framework. Both experiments (A: chemo-morphogenesis,
B: field-guided movers) now execute through the generic `AlchemistEngine` +
core `StepScheduler` against declaratively-described worlds; the science and
scheduling live in experiment coupling modules, not in engine subclasses.

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
- **src/sim_alchemist/core/** — Task 1.3 composition core:
  `world.py` (typed `WorldDefinition`/`ComponentSpec`, YAML load/save),
  `registry.py` (`ComponentRegistry` + `default_registry()`), `composer.py`
  (`compose`/`compose_into`/`build_components`/`resolve_capabilities`),
  `engine.py` (generic `AlchemistEngine` that installs a composed world and
  dispatches it through the core scheduler).
- **worlds/** — declarative YAML worlds for Experiments A and B.

Both experiments are ALSO runnable without their facades: a plain
`AlchemistEngine` composed via `compose(world, registry, operations)` —
proved bitwise identical to the facade path.

This is a **validated scientific prototype**: `run_validation.py`
(checks A–G) and `run_stability.py` (checks S1–S6) pass, and the figures in
`figures/` are baseline evidence. The pytest suite in `tests/` wraps these
same checks.

There is **no** capability discovery, plugin architecture, adapter registry
beyond the in-process `default_registry()`, generalized world composition
beyond `compose()`, or experiment database yet. Do not document or implement
those as if they existed here.

## What Simulation Alchemist Will Become (NOT yet implemented)

- Capability discovery, plugin architecture, generalized world composition
  beyond `compose()`, and an experiment database
- External-engine adapters beyond the in-process `default_registry()`
  factories
- Shared world model, simulation clock, event bus (already: clock, event bus,
  world state, adapter `SimulationEngine` protocol exist in the validated core)
- Mutation/lineage engine with SQLite persistence
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
| Composition / orchestration | schedules + coupling loop | `chemomech/engine.py`, `experiments/field_guided_movers/model.py` |
| Task 1.3 composition core | generic core | `src/sim_alchemist/core/{world,registry,composer,engine}.py` |
| Experiment coupling + worlds | YAML + closures | `chemomech/coupling.py`, `experiments/field_guided_movers/coupling.py`, `worlds/*.yaml` |
| Validation A–G + figures | numpy / matplotlib | `chemomech/validate.py` |
| Stability checks S1–S6 | numpy | `run_stability.py` |

Each experiment declares its macro-step ordering as a plain ordered tuple of
operation names (`ChemomechanicalEngine.SCHEDULE`, `FieldGuidedMoversEngine.
SCHEDULE`) resolved through that engine's op registry and executed by the
core `StepScheduler`. The scheduler owns ordering, validation, time
progression, and tracing; the science stays in the experiments.

Since Task 1.3 the world, schedule, and component list are *data*: a
`WorldDefinition` (PYAML-loadable) lists the components and their configs, the
declared macro-step order, and the required capabilities. `compose()` resolves
capabilities, builds adapters from the `default_registry()` (Experiment B
overrides via its own registry), installs them in a plain `AlchemistEngine`,
and dispatches the schedule through the core `StepScheduler`. The science and
the per-operation coupling rules live in the experiment coupling modules, not
in engine subclasses.

## Running the Project (reproducible)

The environment is managed by uv against Python 3.13:

- `uv sync` — install the locked environment into `.venv`
- `uv run python run_validation.py` — full Task 0.3 validation (A–G) + figures
- `uv run python run_stability.py` — stability/boundedness checks (S1–S6)
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