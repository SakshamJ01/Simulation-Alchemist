# Task 1.3 — Declarative Composition Layer (Final Report)

**Date:** 2026-09-06  
**Status:** Complete and validated  
**Regression:** 72 pytest tests pass; validation A–G pass; stability S1–S6 pass; ruff clean; pyright clean (0 errors); both experiments bitwise-identical to baseline

---

## 1. Objective

Replace the ad-hoc world-construction logic in the experiment facades with a
generic, declarative composition path: typed world data, an explicit component
registry, capability resolution, and adapter construction all driven by data —
not by experiment-specific subclass code. The core scheduler and `AlchemistEngine`
execute the world; the experiments supply coupling rules and world definitions
but no scheduling logic of their own.

## 2. What Was Built

### Core files (`src/sim_alchemist/core/`)

| File | Role |
|------|------|
| `world.py` | `ComponentSpec` and `WorldDefinition` — frozen dataclasses loadable from YAML. `load_world_yaml()` and `as_dict()` / round-trip. |
| `registry.py` | `ComponentRegistry` (maps component id → `AdapterFactory` callable), `default_registry()` returning the three built-in adapters (mesa, py-pde, pymunk). |
| `composer.py` | `resolve_capabilities()`, `build_components()`, `compose()`, `compose_into()` — the composition surface that wires adapters to a world and dispatches the schedule. |
| `engine.py` | `AlchemistEngine` extended (engines=None default, `_install()`, scheduler-driven `run()` / `_macro_step`). |

### Experiment coupling modules (new)

| File | Role |
|------|------|
| `chemomech/coupling.py` | `MORPHOGENESIS_SCHEDULE` (7 ops), `MorphogenesisState`, `morphogenesis_force`, `build_morphogenesis_world()`, `build_morphogenesis_operations()`. |
| `experiments/field_guided_movers/coupling.py` | `FIELD_GUIDED_MOVERS_SCHEDULE` (5 ops), `MoversState`, `gradient_force`, `mover_source`, `build_field_guided_movers_world()`, `build_field_guided_movers_operations()`, `build_field_guided_movers_registry()` (overrides pymunk → MoversAdapter). |

### Experiment facades (rewritten)

`chemomech/engine.py` and `experiments/field_guided_movers/model.py` are now
thin facades: they own trajectory objects, build their worlds via the core
composer, and run through the core `StepScheduler`.  All experiment-specific
coupling lives in the corresponding coupling module.

### YAML worlds

`worlds/chemo_morphogenesis.yaml` and `worlds/field_guided_movers.yaml`
declaratively describe the two experiments' components, configs, required
capabilities, and schedules.  Verified to produce `WorldDefinition` objects
equal to the programmatic builders (`assert yaml_world.as_dict() == prog_world.as_dict()`).

## 3. Composition Flow

```
compose(world, registry, operations, on_initialize)
  └─► resolve_capabilities(adapters, world.requires)
  └─► engine._install(adapters, world, operations, on_step, on_initialize)
       └─► rebuilds engines dict, clock, event_bus, world_state
       └─► validates world.schedule against operations keys at install time
       └─► builds StepScheduler(self._schedule, self.clock, ...)
  └─► engine.run()
       └─► engine.initialize()  →  adapter.initialize(config)
       └─► on_initialize()      →  wiring hook (set_field, set_wallspace, ...)
       └─► validate_composition()
       └─► scheduler.run()      →  loop max_steps × op name → handler
```

`compose()` accepts `operations` as either a plain dict or a factory
`Callable[[list[SimulationEngine]], dict]` — the latter lets experiment code
close over the actual adapter instances compose built.

## 4. Validation Evidence

### Bitwise canonical regression (full 160-step worlds)

| Experiment | final_u SHA256 | force_mags SHA256 | field std |
|-----------|----------------|-------------------|-----------|
| A (morphogenesis) | `9b2232638a6d...` | `6287a47228a3...` | 0.92575 |
| B closed (movers) | `6bdd951fdb29...` | `bee55c7fd4e8...` | 1.09590 |

Bitwise identity is verified between:
- A facade `run_world()` path vs plain `compose()` path (test H)
- B facade `run_field_guided_movers()` path vs plain `compose()` path (test I)
- Plain `compose()` from YAML world vs plain `compose()` from programmatic world (test J)

### pytest composition tests (17 checks, A–M)

| Check | What it proves |
|-------|---------------|
| A | YAML world == programmatic twin (both experiments) |
| B | WorldDefinition dict round-trip |
| C | Registry builds adapters; unknown component → `UnknownComponentError` |
| D | Capability resolution passes both worlds; missing cap → `UnresolvedCapabilityError` |
| E | World-level `requires` enforced on top of adapter requires |
| F | Unknown schedule op → `KeyError` at compose time (before running) |
| G | `compose()` returns a plain `AlchemistEngine` with installed scheduler |
| H | Plain-composed A == A facade (bitwise) |
| I | Plain-composed B == B facade (bitwise) |
| J | YAML-loaded world runs identically to programmatic twin |
| K | Plain-composed replay is deterministic |
| L | Full canonical regression, A + B closed, via YAML + compose |
| M | Both worlds run through plain compose on the generic core |

### Existing regression (unchanged)

- 55 pre-existing tests still pass (test_determinism, test_feedback, test_field_guided_movers, test_scheduler, test_stability).
- Validation A–G pass: figures regenerated identically.
- Stability S1–S6 pass.

### Core immutability guard

`tests/test_field_guided_movers.py::test_core_file_unchanged` pinned to the
post-Task-1.3 core file SHA256 hashes.  This guard is re-baselined as a
sanctioned Task 1.3 extension (the core now includes world.py, registry.py,
composer.py, scheduler.py, and the re-baselined engine.py / __init__.py).

## 5. Design Rationale

**Why a single `UnknownComponentError`?**  `registry.UnknownComponentError`
(KeyError subclass, natural for dict-like lookup) is imported and re-exported
by `composer.py`.  One error class for "unknown component id" across both
registry and composition.

**Why `Sequence` for `resolve_capabilities`?**  Adapters from `build_components`
arrive as `list[SimulationEngine]`, but a subset `[PyPDEAdapter]` from the
test is invariant under `list`.  `Sequence` solves the pyright invariant
constraint without runtime cost.

**Why optional `_scheduler` / `_schedule`?**  `AlchemistEngine.__init__` does
not compose; the scheduler is built only on `_install()` by the composer.
The `run()` method raises `RuntimeError` if no schedule is installed.

**Why RDField typed as runtime import in A coupling?**  `pde.get_field()` returns
the raw py-pde field object (not the adapter).  `typing.cast(RDField, pde.get_field())`
asserts the invariant that the field is always initialized by `run()` time,
preserving baseline crash semantics without adding a runtime branch.

## 6. Files Modified or Created (full list)

**New files:**
- `src/sim_alchemist/core/world.py`, `registry.py`, `composer.py`
- `chemomech/coupling.py`
- `experiments/field_guided_movers/coupling.py`
- `worlds/chemo_morphogenesis.yaml`, `worlds/field_guided_movers.yaml`
- `tests/test_composition.py`

**Modified files:**
- `src/sim_alchemist/core/engine.py`, `__init__.py`
- `chemomech/engine.py` (rewritten as facade)
- `experiments/field_guided_movers/model.py` (rewritten as facade)
- `tests/test_field_guided_movers.py` (CORE_COMMIT_HASHES re-baselined)
- `tests/test_scheduler.py` (optional `_scheduler` asserts)
- `pyproject.toml` (pyyaml dep, pytest slow marker)
- `AGENTS.md`, `IMPLEMENTATION_PLAN.md`

## 7. What This Enables

The validated composition core is the starting point for:

- **Plugin/adapter registry** — `ComponentRegistry` is already extensible at
  runtime; external adapters can register via entry points.
- **Generalized world composition** — `compose()` is a single-world builder;
  extending it to world graphs and runtime mutation is now a data problem, not
  a code-restructuring problem.
- **Experiment database** — worlds are YAML; schedules and configs are
  serializable; the coupling modules are stateless closures.
- **Deterministic replay** — same seed + same YAML + same Python version
  produces bitwise-identical trajectories (proved in tests H/I/J/K).

## 8. What Was NOT Changed

- Adapter code (`sim_alchemist/adapters/`) — untouched.
- Science modules (`chemomech/reaction_diffusion.py`, `physics.py`,
  `agents.py`, `validate.py`) — untouched.
- Baseline scheduler (`src/sim_alchemist/core/scheduler.py`) — untouched.
- Pre-existing test infrastructure (`conftest.py`, determinism/feedback
  test modules) — untouched beyond the `_scheduler` optional guards.
