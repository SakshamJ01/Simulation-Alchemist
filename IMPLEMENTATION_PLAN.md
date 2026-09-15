# Simulation Alchemist — Implementation Plan

**Status:** Historical roadmap. The early MVP described below has been
implemented and superseded by the current state in `PROJECT_STATE.md`.
**Date:** 2026-09-05 (historical snapshot)

## Current Repository Position

Task 3.0 Build Stage 1 is complete: Experiment D is declared, contracted,
catalogued, and executor-registered. Task 3.0 Build Stage 2 is the next task,
but repository stabilization must reach its explicit GO gate in
`PROJECT_STATE.md` first. This document is retained as historical design and
roadmap context; it is not the current implementation status.

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

### 4.1 PyBullet (bulletphysics/bullet3) — Physics Adapter
| Attribute | Value |
|-----------|-------|
| License | Apache 2.0 |
| Headless | Yes (pybullet.DIRECT mode) |
| Deterministic | Yes, with fixed seed and resetSimulation() |
| Step API | p.stepSimulation() |
| State access | Full — positions, velocities, forces |
| Event injection | Yes — apply forces, create/remove bodies |
| Integration | pip install pybullet |

**Why PyBullet over Genesis:** Genesis requires PyTorch and GPU. PyBullet runs headless on CPU with a single pip install.

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

### 4.3 gridlife (rkv0id/gridlife) — Cellular Automata Adapter
| Attribute | Value |
|-----------|-------|
| License | MIT |
| Headless | Yes (gridlife run --sim ...) |
| Deterministic | Yes (PyTorch CPU) |
| Built-in sims | Game of Life, Gray-Scott, Lenia, SmoothLife |
| Step API | sim.step() |
| Integration | pip install gridlife or source |

**Why gridlife over custom CA:** Provides multiple reaction-diffusion systems out of the box with tensor-based computation. Gray-Scott and Lenia produce visually stunning emergent patterns.

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

Adapters: PhysicsAdapter → PyBullet, CellularAutomataAdapter → gridlife, AgentAdapter → Mesa

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

1. **Initialize project scaffolding** — uv init, pyproject.toml with dependencies, directory structure, git init with AGENTS.md
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
