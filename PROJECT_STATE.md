# Simulation Alchemist — Current State

## Current milestone
Task 1.8 complete (Behavioral characterization + generic interestingness engine)

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
- Task 1.7 — deterministic variant sweeps + generic experiment ranking
- Task 1.8 — behavioral characterization + generic interestingness engine

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
- lineage (`lineage.py`: `LineageStore`, `RunRecord`, `SweepRecord`, `BehaviorAnalysisRecord`, deterministic `run_id_of`)
- runner (`runner.py`: `VariantRunner`, `compare_metrics`, `compare_runs`)
- sweep (`sweep.py`: `ParameterSweep`, `MutationSpace`, `sweep_id_of`, `SweepRunner`, `rank_results`, `SweepResult`)
- behavior (`behavior.py`: `ObservableSeries`, `BehaviorFeatures`, `BehaviorAnalyzer`, `InterestingnessProfile`, `rank_by_profile`, `BehavioralAnalysisRunner`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml
- pytest, ruff, pyright, hypothesis (dev)

## Current validation (Task 1.8 closing gate)
- pytest — full suite incl. slow cannonicals: **165 tests passed** (162 fast + 3 slow; 18 Task 1.7 + 18 Task 1.8 + 26 Task 1.6)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current task
Task 1.8 — Behavioral Characterization + Generic Interestingness Engine (closing this milestone).

## Completed in current task
- `behavior.py` in core (generic, experiment-free: ObservableSeries/resample_to/BehaviorAnalyzer/InterestingnessProfile/rank_by_profile/BehavioralAnalysisRunner/behavior_analysis_id_of)
- 18 features across temporal / trend / oscillation / stability / divergence families; explicit max/min directions ("interesting ≠ largest value")
- `lineage.py` extended: per-run `feature_snapshot` (compact) + `behavior_analyses` table (idempotent) + pre-1.8 store migration; no trajectories
- `experiments/network_morphogenesis/experiment.py`: `build_network_observables` (9 series), `run_network_world`/`PARAMETER_SPECS` reused
- 18 tests (`tests/test_behavior_analysis.py`, checks A–Q)
- `run_behavior_demo.py` CLI (`--dim`/`--feature feature:weight[:max|min]`/`--steps`/`--world`/`--db`) with per-feature explanations ("favors/penalizes interest")
- core immutability guard re-baselined to post-1.8 core (behavior.py added)
- real Experiment C analysis (160 steps, loss sweep): analysis id `6307e8e16fd737f49822c877`, baseline ranked #1, timing 58.96s / 19.65s mean
- TASK_1.8_REPORT.md, TASK_1.8_CHECKPOINT.md, this file

## Known limitations
- `config.network_loss` mirror is stale/behaviorally neutral; effective value is `components.network.config.loss`.
- Sweeps/analyses are sequential/combinatorial; no multiprocessing, no AI/optimization.
- `oscillation_persistence` is blind to periods ≲ 4 samples (lag-1 quadrature); documented.
- `wall_count` activity and `network_load_max` stability are constant across 160-step loss variants (honest, non-discriminative at these configs).
- Determinism is same-runtime/same-environment (not universal cross-platform bitwise).
- Parameters hand-tuned for validated runs.

## Next exact task
Task 1.9 — (not specified; not started).

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior experiment-free.
- Guarded core files must not change after Task 1.8 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract.
- No AI/optimization/search/discovery in the core.
- Do not weaken prior tests.