# Simulation Alchemist — Current State

## Current milestone
Task 1.6 complete (Generic mutation + SQLite experiment lineage).

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

## Current experiments
- A — Chemo-Mechanical Morphogenesis (Mesa + py-pde + Pymunk)
- B — Field-Guided Movers (py-pde + Pymunk)
- C — Adaptive Network Morphogenesis (NDlib + py-pde + Pymunk)

## Current architecture
`src/sim_alchemist/core/`:
- adapters (`adapters/base.py`, capability protocol in `core/capabilities.py`)
- capabilities (`capability`/`CapabilitySet` + `SimulationEngine` protocol)
- world definitions (`world.py`, `WorldDefinition`/`ComponentSpec`, YAML)
- composer (`composer.py`: `compose`/`compose_into`/`build_components`/`resolve_capabilities`)
- clock (`clock.py`), scheduler (`scheduler.py`), event bus (`events.py`)
- mutation (`mutation.py`: `Mutation`, `MutationRecord`, `ParameterSpec`, validators, immutable clone)
- lineage (`lineage.py`: `LineageStore`, `RunRecord`, deterministic `run_id_of`)
- runner (`runner.py`: `VariantRunner`, `compare_metrics`, `compare_runs`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml
- pytest, ruff, pyright, hypothesis (dev)

## Current validation (Task 1.6 closing gate)
- pytest — full suite incl. slow cannonicals: PASS (incl. 26 Task 1.6 tests)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current task
Task 1.6 — Generic Mutation and Experiment Lineage (closing this milestone).

## Completed in current task
- `mutation.py`/`lineage.py`/`runner.py` in core (generic, experiment-free)
- `experiment.py` in Experiment C (parameter specs + metrics + executor)
- `NetworkMorphogenesisConfig.from_world`
- 26 tests (`tests/test_mutation_lineage.py`, checks A–L)
- core immutability guard re-baselined to post-1.6 core
- `ndlib==5.1.1` added to pyproject (was missing); build-system added; uv.lock regenerated
- `run_variant_demo.py` demo (base/variant/difference/lineage; 160-step canonical runs real)
- TASK_1.6_REPORT.md, this file

## Known limitations
- `config.network_loss` mirror is stale/behaviorally neutral; effective value is `components.network.config.loss`.
- No sweeps/ranking/search yet (`run_variants` is explicit batch only).
- Determinism is same-runtime/same-environment (not universal cross-platform bitwise).
- Parameters hand-tuned for validated runs.

## Next exact task
Task 1.7 — Deterministic Variant Sweeps + Generic Experiment Ranking.

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner experiment-free.
- Guarded core files must not change after Task 1.6 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract.
- No AI/optimization/search/discovery in the core.
- Do not weaken prior tests.