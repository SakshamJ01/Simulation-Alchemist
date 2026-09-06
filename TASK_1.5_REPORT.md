# Task 1.5 — Adaptive Network Morphogenesis, Experiment C (Final Report)

**Date:** 2026-09-07
**Status:** Complete and validated
**Regression:** pytest now collects **98 tests** (72 pre-existing + 26 new
Experiment C); all fast tests pass, the new Experiment C 160-step canonical
passes, and the two pre-existing slow canonical tests are untouched since
Task 1.3. ruff clean; pyright clean (0 errors); `src/sim_alchemist/core/`
byte-identical (immutability guard holds).

---

## 1. Objective

Compose a THIRD independent simulation system — NDlib network diffusion — into
the existing two-domain chemo-mechanical loop, forming a genuine three-domain
feedback triangle (A↔B↔C↔A) with no change to the validated core:

```
network load ──C→A──► PDE sources ──► field pattern ──A→C─► wall growth/motion
      ▲                                                            │
      └────────────────C←B── edge weighting / topology ────────────┘
```

The science must live in the experiment's coupling module; the macro-step order
must be declared data; the world must be describable declaratively (YAML) and
composable through the generic core `compose()` path like Experiments A and B.

## 2. What Was Built

### New experiment package (`experiments/network_morphogenesis/`)

| File | Role |
|------|------|
| `adapter.py` | `AdaptiveNetworkAdapter` — wraps NDlib `ContinuousModel` on a 4×6 grid graph (integer node labels; NDlib/AGraph cannot handle tuple labels). Node loads diffuse via a custom weighted-averaging / **transport** rule. Provides `network_diffusion` **and** `agent_intentions` (the network's high-throughput-edge decision is the "intention" that drives wall placement, so the wall `pymunk` adapter's requirement is satisfied without Mesa). Reservoir corners are recharged each step to sustain the load gradient. Exposes `get_load/set_load/set_blocked/reweight_from_geometry/get_highest_throughput_edge/nourish_reservoirs/reset`. |
| `coupling.py` | `NETWORK_MORPHOGENESIS_SCHEDULE` (9 ops), `NetworkMorphogenesisState`, `network_morphogenesis_force`, `build_network_morphogenesis_world()`, `build_network_morphogenesis_operations()`, `build_network_morphogenesis_registry()` (adds the `network` component id on top of the core `default_registry()`). |
| `model.py` | Thin facade: `NetworkMorphogenesisConfig`, `NetworkMorphogenesisTrajectory`, `NetworkMorphogenesisEngine` (subclasses the shared `AlchemistEngine`), `run_network_morphogenesis()`. |

### Declarative world

`worlds/adaptive_network.yaml` — declarative twin of the programmatic world
(`load_world_yaml` produces an equal `WorldDefinition`; verified in tests).

### Tests (`tests/test_network_morphogenesis.py`, 26 checks C1–C10)

| Check | What it proves |
|-------|---------------|
| C1 | Capability resolution of the full triangle (py-pde + pymunk + network) without Mesa; world requires `network_diffusion` + `field_gradient`; declared schedule |
| C2 | Incomplete composition fails with a useful capability error |
| C3 | Field gradient → bounded, directional force on walls; walls actually displace |
| C4 | Blocked geometry de-weights edges (1.0 → 0.1) and reroutes growth selection |
| C5 | Node load drives PDE sources; source count grows as load spreads |
| C6 | Closed triangle diverges from open-loop (no source) and inert (no force) controls |
| C7 | Sustained adaptivity: loads stay heterogeneous (reservoirs), walls grow, growth reroutes to additional edges |
| C8 | Bitwise deterministic replay; deterministic reservoir recharge |
| C9 | Boundedness: loads ∈ [0,1], finite forces ≤ fmax, wall positions within [0,1]² |
| C10 | Shared `AlchemistEngine` base class; YAML == programmatic world; YAML runs via plain `compose()`; core-file immutability guard |

Slow canonical (`@pytest.mark.slow`): 160-step regression — walls grow to 159,
across 9 distinct edges (top corridor `(0,6)` ×130 then re-routes to
`(1,2)`, `(5,11)`, `(3,4)`, `(10,16)`, ...), sources 2 → 24, mean force 0.62.

## 3. The Closed Loop (as validated)

1. `geometry.sync` — walls → PDE blocked mask + network edge weights.
2. `field.step` — Schnakenberg field advances with frozen wall cells.
3. `physics.force` — bounded gradient force on each wall COM.
4. `physics.step` — Pymunk integrates (damping + bounds clamp).
5. `physics.grow` — deposit a wall segment along the network's
   highest-throughput edge (network = agent-intention provider).
6. `network.step` — NDlib diffusion iteration (weighted transport) + reservoir recharge.
7. `network.route` — recompute edge weights from wall geometry.
8. `field.source` — inject chemical source proportional to each node's load.
9. `observables.record` — trajectory, wall tracks, geometry snapshots.

Canonical 160-step numbers: **159 walls, 9 distinct growth edges, 24 active
sources, mean load 1.0 (saturated reservoirs), mean force 0.62, final field
std 1.996.**

## 4. Validation Evidence

- **Bitwise determinism**: two identical runs (same seed / same runtime) → identical
  `final_u`, `walls_per_step`, `edge_grown`, `n_sources`, `mean_load`.
- **Genuine feedback**: `rmsd(closed, open) ≈ 7.5e-3` at 10 steps (load-driven
  sources change the field); `rmsd(closed, inert) ≈ 3.5e-4` at 10 steps with
  force×10 (wall motion changes the field) and `≈ 0.118` at 30 steps with
  default forces.
- **Adaptivity**: edge selection deterministically tracks network state and
  re-weights/re-routes when a grown wall blocks the current corridor.
- **Zero core drift**: `tests/...::test_core_files_unchanged` reuses the pinned
  post-1.3 `CORE_COMMIT_HASHES` — all 10 core files byte-identical.
- **Type/lint**: `ruff check` clean; `pyright` clean (0 errors) on all new
  files (adapter made fully pyright-clean with local-graph guards; facade uses
  `cast` to concrete adapter types and the `# type: ignore[override]` pattern
  already used by Experiment B's `run()`).

## 5. NDlib Integration Notes

- **NDlib 5.1.1** (PyPI latest; "6.0" exists only in master-branch docs) works
  on CPython 3.13 / Windows with the pinned dependency set (igraph, dynetx,
  netdispatch, bokeh, scipy).
- `ContinuousModel(graph, constants={...})` + `add_status("loaded")` +
  `add_rule("loaded", fn, NodeStochastic(1.0))` is deterministic per
  `np.random.seed(0)` and state-mutable between steps.
- The internal `fraction_infected` sampling in `set_initial_status` consumes
  RNG draws and warns; the adapter suppresses the warning and re-pins the seed
  so diffusion iterations do not depend on that bookkeeping.
- **Integer node labels are mandatory** — `set_initial_status` fails on tuple
  labels (tuple → NumPy 2-D array in `np.random.choice`).

## 6. Design Rationale

- **`agent_intentions` from the network adapter** — the wall `pymunk` adapter
  requires it (Experiment A gets it from Mesa). Providing it from the network
  keeps the core and the wall adapter untouched and gives a semantically honest
  "the network decides where walls grow" signal.
- **Reservoir recharge** — without it node loads decay/saturate and the loop
  relaxes to uniformity after ~40 steps. Pinning two corner loads preserves a
  persistent gradient so the coupling keeps responding for the whole 160-step
  run. This is the same "sustained input sustains non-equilibrium" stance as
  the validated Experiments A/B.
- **Wall growth is deferred through `PymunkAdapter.add_wall`** — a wall
  requested in `physics.grow` spawns on the following macro step's
  `physics.step`, giving a one-step deterministic latency consistent with the
  adapter's pending-command pattern.
- **`typing.cast` in the facade** — adapters arrive as `SimulationEngine`;
  casting to the concrete adapter types keeps pyright clean at zero runtime
  cost (same pattern as the `RDField` cast in Experiment A coupling).

## 7. Files Created or Modified

**New:**
- `experiments/network_morphogenesis/__init__.py`, `adapter.py`, `coupling.py`, `model.py`
- `worlds/adaptive_network.yaml`
- `tests/test_network_morphogenesis.py`
- `TASK_1.5_REPORT.md`

**Modified:**
- `AGENTS.md` (Experiment C state, architecture table, scientific limitation for the transport rule)
- `IMPLEMENTATION_PLAN.md` (Task 1.5 status + entry)

**Untouched (by design):** `src/sim_alchemist/core/*`, `sim_alchemist/adapters/*`,
`chemomech/*`, `experiments/field_guided_movers/*`, all pre-existing tests.

## 8. What This Proves for the Framework

A third, entirely different simulation backend (a discrete network model on top
of NDlib) now composes through the same generic core: same clock, same event
bus, same scheduler, same capability resolution, same declarative world path.
The experiment contributes only its coupling rules and a registry extension —
the "compose, don't subclass" property of the validated core holds across all
three experiments.