# AGENTS.md

## Project: Simulation Alchemist — Baseline v0.1

A framework for composing multiple independent simulation systems into a
unified simulated world. This repository currently holds **Baseline v0.1**:
the validated chemo-mechanical prototype (Tasks 0.1–0.3) that is the verified
starting point for the framework. The Simulation Alchemist composition core
(excluding the Task 1.2 scheduler) has **not** been extracted yet; the
composition loop lives un-refactored in `chemomech/simulation.py`.

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
- **chemomech/simulation.py** — the composition/orchestration entry point.
  It reads live wall transforms, rasterizes them into the PDE mask, advances
  the field, samples the force, integrates pymunk, steps the Mesa model, and
  translates agent wall intentions into the physics space. The per-step
  ordering is now *declared* (`ChemomechanicalEngine.SCHEDULE`) and dispatched
  by the core `StepScheduler` (Task 1.2).

This is a **validated scientific prototype**: `run_validation.py`
(checks A–G) and `run_stability.py` (checks S1–S6) pass, and the figures in
`figures/` are baseline evidence. The pytest suite in `tests/` wraps these
same checks.

There is **no** capability discovery, plugin architecture, adapter registry,
generalized world composition, or experiment database yet. Do not document or
implement those as if they existed here.

## What Simulation Alchemist Will Become (NOT yet implemented)

- Composition engine with capability/compatibility reasoning
- Adapters (`SimulationEngine` protocol) wrapping external engines
- Shared world model, simulation clock, event bus
- Mutation/lineage engine with SQLite persistence
- Deterministic replay system
- YAML world definitions

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
| Validation A–G + figures | numpy / matplotlib | `chemomech/validate.py` |
| Stability checks S1–S6 | numpy | `run_stability.py` |

Each experiment declares its macro-step ordering as a plain ordered tuple of
operation names (`ChemomechanicalEngine.SCHEDULE`, `FieldGuidedMoversEngine.
SCHEDULE`) resolved through that engine's op registry and executed by the
core `StepScheduler`. The scheduler owns ordering, validation, time
progression, and tracing; the science stays in the experiments.

## Running the Project (reproducible)

The environment is managed by uv against Python 3.13:

- `uv sync` — install the locked environment into `.venv`
- `uv run python run_validation.py` — full Task 0.3 validation (A–G) + figures
- `uv run python run_stability.py` — stability/boundedness checks (S1–S6)
- `uv run pytest` — test suite wrapping the same scientific checks

## Key Development Commands

- `uv run pytest tests/` — run all tests
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