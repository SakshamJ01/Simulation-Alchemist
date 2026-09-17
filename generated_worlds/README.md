# Generated World Definitions

This directory contains canonical, declarative YAML world configurations deterministically synthesized from registered `CouplingTemplate` instances via `sim_alchemist.core.templates.generate_world()`.

---

## What is a World Definition?

In Simulation Alchemist, a simulated world is **data, not code**. A `WorldDefinition` completely specifies:
1. **Components & Variants:** The set of simulation adapters active in the world (e.g. `py-pde`, `pymunk`, `mesa`, `network`).
2. **Component Configurations:** Initial conditions, domain grid dimensions, physics parameters, and diffusion constants.
3. **Coupling Contracts:** Declaratively validated input/output capabilities ensuring cross-engine compatibility before execution.
4. **Macro-Step Schedule:** The exact sequence of scheduled operations executed each macro timestep by the `StepScheduler`.
5. **Simulation Clock:** Step size ($\Delta t$), total macro-steps ($N_{\text{steps}}$), and sub-step discretization ratios.

---

## Canonical Experiment Worlds

| File | Experiment Name | Composed Subsystems | Schedule Operations |
| :--- | :--- | :--- | :--- |
| `morphogenesis.yaml` | **Experiment A** (Chemo-Mechanical Morphogenesis) | Mesa Agents + py-pde Field + Pymunk Walls | `geometry_sync` $\to$ `field_step` $\to$ `physics_force` $\to$ `physics_step` $\to$ `agent_step` $\to$ `agent_translate` $\to$ `record` |
| `field_guided_movers.yaml` | **Experiment B** (Field-Guided Movers) | py-pde Field + Pymunk Dynamic Movers | `geometry_sync` $\to$ `field_step` $\to$ `physics_force` $\to$ `physics_step` $\to$ `field_source` $\to$ `record` |
| `adaptive_network.yaml` | **Experiment C** (Adaptive Network Morphogenesis) | NDlib Network + py-pde Field + Pymunk Physics | `geometry_sync` $\to$ `field_step` $\to$ `physics_force` $\to$ `physics_step` $\to$ `wall_growth` $\to$ `network_step` $\to$ `route` $\to$ `field_source` $\to$ `record` |

---

## Usage in Python

To load and run any generated world definition directly through the core composition engine:

```python
from sim_alchemist.core.world import WorldDefinition
from sim_alchemist.core.composer import compose
from experiments.catalog import repository_surfaces

# 1. Load world definition
world = WorldDefinition.from_yaml("generated_worlds/morphogenesis.yaml")

# 2. Compose into generic AlchemistEngine
registry = repository_surfaces()
engine = compose(world, registry=registry)

# 3. Step or run simulation
for step in range(world.clock.n_steps):
    engine.step()

print("Final field mean:", engine.get_state("py_pde.u").mean())
```

---

## Immutability & Reproducibility

- World files in this directory serve as standard baseline fixtures.
- Every world is content-addressed via a SHA-256 hash (`world_hash`), guaranteeing bitwise identical experiment replication and lineage tracking across runs.
