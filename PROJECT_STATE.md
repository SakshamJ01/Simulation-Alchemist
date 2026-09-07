# Simulation Alchemist — Current State

## Current milestone
Task 2.0 complete (Diversity-preserving multi-objective discovery)

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
- Task 2.0 — diversity-preserving multi-objective discovery (behavioral-diversity-aware beam selection)

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
- behavior (`behavior.py`: `ObservableSeries`, `BehaviorFeatures`, `BehaviorAnalyzer`, `InterestingnessProfile`, `rank_by_profile`, `BehavioralAnalysisRunner`, `behavior_vector`, `behavior_distance`, `select_diverse_frontier`, `compute_frontier_diagnostics`, `FrontierDiagnostics`)
- search (`search.py`: `SearchSpec`, `SearchRunner`, `child_mutations`, `search_id_of`, `SearchCandidate`, `SearchGeneration`, `SearchResult`, `SearchTiming`, `SelectionProfile`)

## Current technology stack
- Python 3.13 (uv-managed, uv.lock reproducible)
- Mesa, py-pde, Pymunk, NDlib, networkx, numpy, matplotlib, pyyaml
- pytest, ruff, pyright, hypothesis (dev)

## Current validation (Task 2.0 closing gate)
- pytest — full suite standing gate: **~202 tests** (199 fast incl. 21 new Task 2.0 tests + slow cannonicals)
- run_validation.py — A–G: PASS
- run_stability.py — S1–S6: PASS
- ruff check . — clean
- pyright — 0 errors

## Current task
Task 2.0 — Diversity-preserving multi-objective discovery.

## Completed in current task
- `behavior.py` gains the behavioral-distance primitive layer: `behavior_vector` (deterministic flat vector, None/non-finite -> 0.0, divergence excluded by default), `behavior_distance` (Euclidean, symmetric, key-aware, missing/constant/NaN-safe), `select_diverse_frontier` (greedy `qw*quality + dw*min_dist` selection, deterministic tie-break, seed = highest quality), `compute_frontier_diagnostics` / `FrontierDiagnostics` (mean/min/max pairwise distance, unique behavioral signatures, mean quality)
- `search.py` gains `SelectionProfile(quality_weight, diversity_weight)` (validated >=0, sum>0), extends `SearchSpec`/`SearchCandidate`/`SearchGeneration`/`SearchTiming`/`SearchResult` with diversity metadata (selection_quality/diversity/combined scores, selection_reason, per-generation + final frontier diagnostics), and makes `SearchRunner.search` diversity-aware (quality-only `diversity_weight=0` reproduces Task 1.9 semantics exactly)
- `SearchResult.explain_selection()` / `explain_frontier()` report selection reasons and collapse diagnostics from measured values
- 21 tests (`tests/test_diversity.py`, checks A–L / A–F / A–C)
- `run_search.py` CLI adds `--quality-weight`/`--diversity-weight` and `--compare`/`--compare-figure`
- Real Experiment C comparison: identical budget, diversity-weight 0.8 retains a low-quality but behaviorally-distant 4th signature (3/4 beam overlap with quality-only; slightly lower mean quality for higher frontier spread)
- core immutability guard re-baselined post-2.0 (search.py, behavior.py, __init__.py)
- TASK_2.0_REPORT.md, this file

## Known limitations
- `config.network_loss` mirror is stale/behaviorally neutral; effective value is `components.network.config.loss`.
- Beam search is a bounded heuristic (no global optimality claim); single-parameter children only (no multi-param combinations).
- Diversity is evaluated on the discrete behavioral-feature snapshot of the beam pool; it cannot discover behavior outside the features the profile exposes.
- Greedy frontier selection is exact under the declared weights but is a heuristic for global multi-objective optimality (no Pareto-parity guarantee).
- `oscillation_persistence` is blind to periods ≲ 4 samples (lag-1 quadrature); documented.
- Determinism is same-runtime/same-environment (not universal cross-platform bitwise).
- Parameters hand-tuned for validated runs.

## Next exact task
Task 2.1 — (not specified; not started).

## Do-not-change constraints
- Keep `src/sim_alchemist/core/*` mutation/lineage/runner/sweep/behavior/search experiment-free.
- Guarded core files must not change after Task 2.0 (hashes pinned in tests) except via a sanctioned re-baseline.
- Keep the three-composition-paths (A/B/C) bitwise-identical facade/plain-compose contract.
- No GA/evolutionary/Bayesian/ML/RL optimization in the core.
- Do not weaken prior tests.