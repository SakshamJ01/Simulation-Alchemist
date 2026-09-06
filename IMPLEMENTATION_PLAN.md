# Simulation Alchemist — Implementation Plan

**Status:** BASELINE v0.1 COMPLETE — Tasks 0.1–0.3 validated, Tasks 1.2–1.3
validated, Task 1.5 (Experiment C: Adaptive Network Morphogenesis) validated.
Next is the plugin/adapter registry and generalized world composition layer;
do not start Phase 1 architecture until that is issued.
**Date:** 2026-09-05 (updated 2026-09-07)

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

Result: **Baseline v0.1 + Task 1.2–1.3–1.5** — a reproducible, uv-locked,
pytest-wrapped, validated prototype with a generic composition core in
`src/sim_alchemist/core/` that now drives three independent composed
experiments (A chemo-morphogenesis, B field-guided movers, C adaptive network).

### NEXT
- Plugin/adapter registry (extensible `ComponentRegistry` with external
  adapters and capability discovery).
- Generalized world composition beyond `compose()` (world graph, runtime
  mutation, experiment database).
- Deterministic replay (the foundation is here; cross-platform replay needs
  careful version pinning).
- Phase 0 remaining: CLI, SQLite persistence, mutation/lineage engine.

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
