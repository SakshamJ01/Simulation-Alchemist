# Simulation Alchemist — Current State

## Current milestone
Task 1.9 complete (Guided simulation search — first discovery loop)

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
- Task 1.9 — guided simulation search (beam search discovery loop)

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
- lineage (`lineage.py`: `LineageStore`, `RunRecord`, `SweepRecord`, `BehaviorAnalysisRecord`, `SearchRecord`, deterministic `run_id_of`)
- runner (`runner.py`: `VariantRunner`, `compare_metrics`, `compare_runs`)
- sweep (`sweep.py`: `ParameterSweep`, `MutationSpace`, `sweep_id_of`, `SweepRunner`, `rank_results`, `SweepResult`)
- behavior (`behavior.py`: `ObservableSeries`, `BehaviorFeatures`, `BehaviorAnalyzer`, `InterestingnessProfile`, `rank_by_profile`, `BehavioralAnalysisRunner`)
- search (`search.py`: `SearchSpec`, `SearchRunner`, `child_mutations`, `search_id_of`, `SearchCandidate`, `SearchGeneration`, `SearchResult`, `SearchTiming`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml
- pytest, ruff, pyright, hypothesis (dev)

## Current validation (Task 1.9 closing gate)
- pytest — full suite incl. slow cannonicals: **181 tests passed** (178 fast + 3 slow; 15 new Task 1.9 tests)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current task
Task 1.9 — Guided Simulation Search (first discovery loop).

## Completed in current task
- `search.py` in core (generic, experiment-free: SearchSpec/child_mutations/SearchRunner/SearchCandidate/SearchGeneration/SearchResult/SearchTiming/search_id_of)
- Beam search model: generation 0 = root control, beam expansion via dimension-major single-param children, no-op skip, visited-set dedup, profile-driven ranking per generation
- `lineage.py` extended: SearchRecord + searches table (idempotent metadata only, no trajectories) + search_count
- 15 tests (`tests/test_search.py`, checks A-O)
- `run_search.py` CLI with `--dim`/`--feature`/`--generations`/`--beam-width`/`--children`/`--steps`/`--db`/`--figure`/`--name`/`--seed`
- Real Experiment C search (160 steps, loss×force 2-D space, gen 3, beam 2, children 3): root control ranked best under declared profile; determinism confirmed; figure saved to `figures/search_beam_scores.png`
- core immutability guard re-baselined to post-1.9 core (search.py added)
- TASK_1.9_REPORT.md, this file

## Known limitations
- `config.network_loss` mirror is stale/behaviorally neutral; effective value is `components.network.config.loss`.
- Beam search is a bounded heuristic (no global optimality claim); single-parameter children only (no multi-param combinations).
- `oscillation_persistence` is blind to periods ≲ 4 samples (lag-1 quadrature); documented.
- `wall_count` activity and `network_load_max` stability are constant across 160-step loss variants (honest, non-discriminative at these configs).
- Determinism is same-runtime/same-environment (not universal cross-platform bitwise).
- Parameters hand-tuned for validated runs.

## Next exact task
Task 2.0 — (not specified; not started).

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search experiment-free.
- Guarded core files must not change after Task 1.9 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Do not weaken prior tests.