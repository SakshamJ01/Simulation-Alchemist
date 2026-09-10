# Task 2.7 Design — Researcher-Constrained Adaptive Exploration Specification (PLAN-ONLY)

Status: PLAN-ONLY. No source/test/dependency/world changes. Task 2.7 implementation NOT started. Task 2.8 NOT started.

## 1. Verified Starting State
- Task 2.6 Stages 1–5 verified complete (adaptive signal/state/decision + bounded execution + selection/proposal + feedback loop + CLI/figure/docs).
- 59 adaptive tests pass; validation A–G PASS; stability S1–S6 PASS.
- Only C has real MutationSpace (`PARAMETER_SPECS`: `components.network.config.loss`, `config.force_fmax`, `config.source_amplitude`); A/B remain baseline-only.
- 3 EXECUTABLE compositions (A/B/C); 23-shape universe.
- Existing machinery: `CompositionCatalog`, `CompositionSpace`, `CrossCompositionSweep`, `AdaptiveSweepRunner`, `AdaptiveSweepSelection`, `BehaviorAnalyzer`, `rank_by_profile`, `select_diverse_frontier`, `lineage` (compact metadata + additive tables).
- No optimization/ML/GA/Bayesian/RL; no plugin architecture; no distributed execution.

## 2. Current Platform Capability Map
- Composition / catalog / templates / contracts / catalog query
- Cross-composition sweep execution + common-observable aggregation + ranking/frontier
- Adaptive signal evaluation / selection / bounded execution / feedback continuation / CLI
- Mutation / sweep / behavior / search / diversity
- Lineage (RunRecord + SweepRecord + BehaviorAnalysisRecord + SearchRecord + AdaptiveRunResult + CrossCompositionSweepRow)
- Developer CLIs for discovery, sweep, behavior, search, adaptive
- Figure generation (matplotlib) consuming result objects without recomputation

## 3. What Task 2.6 Actually Enabled
Conceptual pipeline (verified): composition → parameter space → sweep → behavior → ranking/frontier → adaptive signal → adaptive selection → adaptive execution → feedback continuation → developer demo.
Still missing: a declared, reproducible way for a researcher to constrain exploration (composition subset + parameter subspace + profile + budget) and run bounded multi-pass adaptive exploration with deterministic replay and compact multi-pass lineage.

## 4. Architecture Gap Audit
| Subsystem | Supports | Limitation | Architectural or missing data? | Solved by existing abstraction? |
|---|---|---|---|---|
| Adaptive execution | Single-completion loop over actions | Starts from completed result; no declared multi-pass spec | Missing spec layer | Yes — `AdaptiveSweepRunner` reusable |
| Cross-composition sweep | Per-composition baseline + variants + common-observable aggregation | Static spec only; no researcher constraint or multi-pass adaptive integration | Missing constraint + multi-pass model | Yes — `CrossCompositionSweep` reusable |
| Parameter space | C real (3 params); A/B None | Only C can adapt; A/B baseline-only | Experiment-owned | Keep experiment-owned |
| Behavior / ranking | Per-run + pool-level + diversity frontier | No temporal multi-pass comparison framework | Missing comparison spec | `BehaviorAnalyzer` reusable |
| Lineage | Compact + deterministic ids | No multi-session adaptive session tracking | Missing additive session table | Additive schema safe |
| CLI / visualization | Single-path CLI + figure | No constrained exploration CLI | Missing CLI wrapper | Additive |

Highest-leverage gap: researcher-constrained multi-pass adaptive exploration specification.

## 5. Candidate Directions (3 evaluated)

A. Richer temporal behavior characterization (multi-pass divergence / convergence tracking)
B. Researcher-constrained adaptive exploration specification (recommended)
C. Richer result persistence / interactive query interface over adaptive/sweep lineage

### Comparison (A vs B vs C)
- Scientific usefulness: B > A (enables cross-composition adaptive study with controls) > C (tooling only)
- Reuse: B uses `AdaptiveSweepRunner`, `CrossCompositionSweep`, `MutationSpace`, `lineage`; A uses `BehaviorAnalyzer`; C uses `lineage` only
- Implementation complexity: B = medium (spec + runner wrapper + CLI + additive schema); A = medium-high (new temporal metrics); C = low (query layer)
- Core purity risk: B = low (spec model + filter only); A = medium (new feature formulas in core); C = low
- Regression risk: B = low (additive only); A = medium (new behavior formulas); C = low
- Determinism / replay: B high (spec id content-addressed); A medium; C high
- Scaling: B bounded by declared budget + existing mutation spaces

## 6. Recommended Direction — B
Researcher-Constrained Adaptive Exploration Specification.

Rationale: smallest architectural capability that unlocks the largest scientifically meaningful next experiment (comparing adaptive trajectories across compositions with researcher-defined subspaces and controls) without corrupting generic core, without optimization, without new experiments, and fully reusing validated Task 2.4–2.6 machinery.

## 7. Scientific Justification
After 2.6, the platform can execute, observe, adapt, and visualize for a single completed adaptive run. To test whether adaptive exploration produces meaningfully different outcomes under researcher-controlled conditions, we need:
- a declared exploration plan (which compositions, which mutation axes, profile, budget)
- bounded multi-pass execution using existing runners
- deterministic replay from plan identity
- compact multi-pass lineage (not full trajectories)
This is exploratory science, not optimization.

## 8. Concrete Experiment Enabled
Experiment: Cross-composition adaptive trajectory comparison (C-focused + baseline controls).
- Independent variables: profile (quality / diversity / balanced); parameter subspace (freeze `force_fmax`, vary `loss`; or freeze `loss`, vary `force_fmax`); budget (2 / 3 passes); composition set (`["C"]` vs `["C","A","B"]` where A/B contribute baseline only).
- Dependent observables: adaptive decision sequence per pass; behavior feature snapshot per pass; final ranking / frontier position per pass; termination reason.
- Controls: identical seed + spec identity produce identical progression; baseline-only runs (no mutation) establish reference trajectory.
- Protocol: declare spec → run Stage 1 (analysis-only from existing completed result) → Stage 2 (bounded adaptive continuation with subspace filter) → record multi-pass result → compare.
- Expected outputs: deterministic adaptive session record (`adaptive_exploration_id`); proposal sequence; stop/budget reasons; feature-snapshot comparison table.
- Interpretation limits: only C has genuine parameter space; A/B provide structural baseline only; profile effects are heuristic; diversity is behavioral, not calibrated.

## 9. Core vs Experiment Ownership
- Generic core (`core/adaptive_exploration.py`): `AdaptiveExplorationSpec`, `AdaptiveExplorationResult`, `adaptive_exploration_id_of`, selection subspace filter (operates on `MutationSpace` / `CompositionCatalog` abstractions), multi-pass runner adapter (optional wrapper around existing `AdaptiveSweepRunner` / `CrossCompositionSweep`). No experiment branches.
- Experiment-owned (`experiments/network_morphogenesis/experiment.py`, `experiments/catalog.py`): parameter-space declarations (`PARAMETER_SPECS`), world builders, execution functions; optional `repository_parameter_spaces()` extended if A/B declare spaces later.
- Developer tooling (`run_adaptive_exploration.py` CLI): analysis-only + adaptive-continue paths; figure from multi-pass result; reads `worlds/*.yaml` and `experiments/catalog.py`.
- Lineage (`core/lineage.py`): additive `adaptive_exploration_sessions` table (id, spec_id, sweep_ids, seed, profile, total_simulated, final_decision, termination_reason, created timestamp optional but excluded from identity).

## 10. API Boundaries
```python
# Generic core (new module)
AdaptiveExplorationSpec  # frozen: composition_ids, mutation_space_ref, profile, budget, seed, constraints
AdaptiveExplorationResult  # frozen: spec_id, steps (sequence of AdaptiveRunResult references), final_decision, termination, total_simulated
adaptive_exploration_id_of(spec_dict, seed=0) -> str  # 24-hex content-addressed
# Optional adaptive selection subspace filter (reuses MutationSpace)
filter_mutation_space(space, constraints) -> MutationSpace  # deterministic, experiment-free
# CLI (new file)
run_adaptive_exploration.py --spec PATH [--analysis-only | --adaptive-continue] [--seed N] [--profile NAME] [--max-passes N] [--figure PATH] [--no-figure]
```
No new adapter initialization, no engine subclass, no new simulation concept.

## 11. Identity Model
- `adaptive_exploration_id`: content-addressed sha256 over canonical `AdaptiveExplorationSpec.as_dict()` (sorted at every level, no timestamps, no repr, no dict-order dependence). 24-hex.
- Distinct from: `composition_id`, `cross_split_sweep_id`, `sweep_id`, `mutation_id`, `run_id`, `adaptive_run_id`, `selection_id`.
- If multi-pass result requires session tracking, session identity = `adaptive_exploration_id`; individual pass identities reuse existing `adaptive_run_id` / `run_id`.
- No second database identity; no UUIDs.

## 12. Lineage Model (additive only)
New table `adaptive_exploration_sessions` (optional, migration-safe, idempotent):
- `session_id` (TEXT, PK, content-addressed 24-hex from spec)
- `spec_dict_json` (compact canonical spec, for replay verification)
- `composition_ids_json` (sorted list)
- `profile_used` (TEXT)
- `seed` (INT)
- `budget` (INT)
- `total_simulated` (INT)
- `final_decision` (TEXT)
- `termination_reason` (TEXT)
- `related_sweep_ids_json` (optional references to existing `cross_composition_sweeps` / `cross_split_sweep_id` rows)
- `related_adaptive_run_ids_json` (optional references to `adaptive_run_id` values)
- No trajectory storage; no world state; no event log.
If the table is absent, the system degrades gracefully (analysis/run from spec identity only, no persistence).

## 13. Data Flow
```
AdaptiveExplorationSpec (researcher-declared, deterministic, immutable)
    ↓
subspace_filter (on MutationSpace / CatalogCandidate / Web of bindings — pure projection)
    ↓
AdaptiveSweepSelection.select_proposal (using filtered pool + profile + budget)
    ↓
AdaptiveSweepRunner.run (existing execution loop)
    ↓
AdaptiveRunResult (existing step records + run_id)
    ↓
AdaptiveExplorationResult (aggregation of pass results; reference-only, no duplication of full RunRecords)
    ↓
write_lineage (additive session table — only if persistence enabled)
    ↓
CLI figure (plots proposal/decision sequence from result; does not recompute analysis or rerun)
```
World remains immutable; adapter construction only for template-matched EXECUTABLE shapes; no automatic coupling inference.

## 14. Deterministic Protocol
- Same `AdaptiveExplorationSpec.as_dict()` + same seed + same profile + same budget + same existing lineage state → identical `adaptive_exploration_id`, identical proposal sequence, identical execution order, identical replay.
- Canonical ordering: `composition_ids` sorted; mutation space enumeration follows existing `itertools.product` right-most-fastest with sorted dimensions; actions sorted.
- No randomness in selection; seed affects identity only (as in Stage 2).
- Replay verification test: construct spec → run → record id + steps → reconstruct identical spec → rerun → assert identical result.

## 15. Computational Scaling (realistic estimate from current base)
- Current: 3 EXECUTABLE; C mutation space 3 params (27 variants); adaptive budget 2–3; evaluation ~60s per pass; total per session ~2–3 min.
- 10 compositions (still 3 EXECUTABLE if others invalid): budget 3 → ~3 passes × ~60s = ~3 min; analysis only ~0.01s.
- 50 compositions: still limited by EXECUTABLE filter (currently 3); if more shaped executable, evaluation scales linearly with EXECUTABLE count.
- Larger mutation spaces (e.g., 4 params × 3 values = 81): budget 3 → same wall time (only 3 passes executed, not full enumeration).
- Multi-pass adaptive does NOT rerun full space; does NOT rerun historical 30-run sweep.
- Bottleneck: real simulation time per step (Experiment C ~30–60s); not selection/analysis overhead.
- Scaling recommendation: keep budget explicit and small; use analysis-only path for rapid exploration planning.

## 16. Failure Modes
| Failure | Detection | Mitigation | Test |
|---|---|---|---|
| Scientific validity: profile/threshold misinterprets real behavior | Compare feature snapshots to baseline; explicit missing-data contract (`available=False`) | Profile is configurable, not fixed; user must interpret | `test_profile_consistency` |
| Determinism failure: spec identity changes with insertion order | Canonical sorted `as_dict()` + `adaptive_exploration_id_of` | Sort at every nesting level | `test_replay_identity` |
| Identity collision: two specs produce same hash | Content-addressed over full canonical dict; 24-hex sufficient for current space | Not solved (accept collision risk < 2^-96) | `test_identity_unique` |
| Lineage failure: session missing / stale | Additive table; absence = graceful degradation | No secondary DB required | `test_lineage_optional` |
| Computational explosion: unbounded passes | Explicit `budget` / `max_passes`; stop on STOP/BUDGET/NO_VALID_ACTION | Budget enforced by `AdaptiveSweepRunner` | `test_budget_exhausted` |
| API misuse: spec includes invalid composition / non-existent mutation | Validation against `CompositionCatalog` / `MutationSpace`; `classify_composition` pre-check | Reject at spec creation; never execute invalid | `test_invalid_spec_rejected` |
| Reproducibility failure: same seed + spec produce different result because adapter state changed | Replay uses same-world / same-adapter initialization; adapter is reconstructed per execution (not persisted with state) | Document that replay requires same environment | `test_replay_same_environment` |
| Stale data: analysis uses old completed result | Analysis-only references existing result by `adaptive_run_id`; never assumes live state | Explicit dependency on completed result | `test_analysis_uses_existing_result` |

## 17. Test Strategy (compact)
- Unit: `AdaptiveExplorationSpec.as_dict()`, `adaptive_exploration_id_of`, subspace filter correctness
- Architectural purity: module contains no experiment names / engine refs / optimizer imports (reuse `test_n` pattern)
- Determinism / replay: identical spec + seed + profile + budget → identical `adaptive_exploration_id` and result
- Integration: CLI `--analysis-only` over completed adaptive result proposes next; `--adaptive-continue` executes bounded 2-pass loop with real C; figure generated; no execution when analysis-only
- Real demo: bounded 2-pass C exploration with subspace constraint; exact steps/decisions recorded; no full sweep replay
- Persistence: optional session table insert / query / idempotency; absence does not break execution
- Regression: existing adaptive + validation + stability must remain green

## 18. Performance / Budget
- Budget: `max_passes` (default 2–3); `budget` per pass (default 2–3); total simulated ≤ ~6 steps.
- Analysis-only: < 0.01 s (pure projection over existing evaluations).
- Execution: ~1–2 min per pass depending on Experiment C horizon + adapter setup.
- Storage: session table row ~500 bytes per session (compact spec reference + metadata); negligible at current scale.
- Acceptable worst case: 3 EXECUTABLE × 3 passes = ~9 simulations; ~5–10 min total; well within current infrastructure.

## 19. Reuse Current Infrastructure
Explicitly reused (no duplication):
- `core/adaptive_sweep.py`: `AdaptiveSignal`, `AdaptiveState`, `AdaptiveDecision`, `evaluate_adaptive_decision`, `AdaptiveSweepSelection`, `AdaptiveSweepRunner`, `AdaptiveRunResult`, `adaptive_run_id_of`
- `core/cross_sweep.py`: `CrossCompositionSweep`, `CrossCompositionSweepSpec`, `cross_split_sweep_id`
- `core/composition_search.py`: `CompositionEvaluation`, `composition_discovery_id_of`
- `core/behavior.py`: `BehaviorFeatures`, `InterestingnessProfile`, `rank_by_profile`, `behavior_vector`
- `core/composition_analysis.py`: `rank_compositions`, `select_frontier`
- `core/sweep.py`: `SweepRunner`, `ParameterSweep`, `MutationSpace`, `sweep_id_of`
- `core/observables.py`: `CommonObservableSet`
- `core/lineage.py`: `LineageStore` (additive table only)
- `experiments/catalog.py`: `repository_parameter_spaces()`, `build_repository_catalog()`
- Existing CLIs: `run_cross_composition_sweep.py`, `run_composition_discovery.py`, `run_adaptive_discovery.py`
- Existing world definitions and experiment executors

Not reused / not needed: new adapter protocol, new engine, new simulation concept, new database.

## 20. Implementation Stages

Stage 1 — Spec + subspace filter + identity (smallest build):
- Files: `src/sim_alchemist/core/adaptive_exploration.py` (new), `tests/test_adaptive_exploration_stage1.py` (new)
- Purpose: establish deterministic exploration spec model + content-addressed identity + pure subspace projection over existing `MutationSpace`
- Acceptance: `AdaptiveExplorationSpec.as_dict()` canonical sorted; `adaptive_exploration_id_of` deterministic; subspace filter excludes non-matching mutation dimensions; no execution; no lineage writes; core purity verified
- Non-goals: execution, CLI, lineage persistence

Stage 2 — CLI + multi-pass runner adapter + replay:
- Files: `run_adaptive_exploration.py` (new), `tests/test_adaptive_exploration_stage2.py` (new)
- Purpose: bind spec to existing `AdaptiveSweepRunner` / `CrossCompositionSweep`; analysis-only path; adaptive-continue bounded loop; deterministic replay; figure from multi-pass result
- Acceptance: `--analysis-only` outputs proposal/identity without simulation; `--adaptive-continue --max-passes 2 --seed N` executes 2 real passes with existing C; replay identical; CLI deterministic; figure written; no optimizer imports; no new dependencies
- Non-goals: new engine, automatic parameter synthesis, global optimization, distributed execution

Stage 3 — Lineage + documentation + final verification:
- Files: `src/sim_alchemist/core/lineage.py` (additive table only), `tests/test_adaptive_exploration_stage3.py` (lineage/test), `TASK_2.7_STAGE3_REPORT.md`, `TASK_2.7_STAGE1_REPORT.md` (additive if needed)
- Purpose: optional durable session table; update `PROJECT_STATE.md`; confirm regression green
- Acceptance: table insert idempotent; session query returns spec/steps/references; missing table does not break execution; full regression (validation/stability/adaptive) passes; `Task 2.7` not marked complete; `Task 2.8` not started
- Non-goals: trajectory storage, second database, automatic scientific interpretation

## 21. Smallest First Build (Stage 1)
Task 2.7 Build Stage 1 should implement `AdaptiveExplorationSpec` + `adaptive_exploration_id_of` + pure subspace filter over `MutationSpace` with no execution.
It establishes the exploration-plan boundary (the specification that everything else executes), is testable without a long simulation, minimizes regression risk, and unlocks Stage 2 (runner binding) and Stage 3 (lineage/docs).

## 22. Non-Goals (explicit, justified by repository)
- No ML / RL / Bayesian / evolutionary / genetic optimization (design §5; repository uses only deterministic search/behavior/ranking/selection)
- No automatic parameter semantic equivalence (contract layer never infers couplings; parameters stay experiment-owned)
- No automatic composition synthesis (templates/catalog stay static; contracts never invented)
- No plugin / marketplace / distributed execution (adapter protocol exists but no plugin infrastructure; core stays experiment-free)
- No universal parameter model (only C has declared space; A/B baseline-only preserved)
- No global optimization claim (adaptive exploration is bounded deterministic exploration over declared candidates; not calibration)
- No new experiment required (uses existing C; A/B can enter as structural baseline-only)
- No new dependencies (matplotlib / numpy / pyyaml already in uv.lock)

## 23. Re-Context Recipe (for future agents)
Every Task 2.7 build session must begin by reading:
1. `PROJECT_STATE.md` (current milestone; verify 2.6 complete / 2.7 plan-only)
2. `AGENTS.md` (architecture; no plugin / no optimization rules)
3. `IMPLEMENTATION_PLAN.md` (confirmed 2.6 complete; 2.7 next; no 2.8)
4. `TASK_2.7_DESIGN.md` (this document; especially §6 recommendation, §8 experiment, §20 stages, §21 smallest build)
5. `TASK_2.6_STAGE3_5_REPORT.md` + `TASK_2.6_STAGE3_5_CHECKPOINT.md` (verified adaptive loop state; identity/selection/test patterns)
6. `git status` (verify uncommitted review state; no unexpected working-tree changes)
7. `git log --oneline -5` (verify master / origin/master alignment; check for unexpected commits)
8. `tests/test_adaptive_sweep_stage3_5.py` (current adaptive selection/metrics patterns)
9. `core/adaptive_sweep.py` (current API surface to extend)
If context compacts, recover from the above + latest `TASK_2.7_*` report/checkpoint without rereading full 2.5/2.6 history.

## 24. Success Criteria
- [ ] `TASK_2.7_DESIGN.md` present with all 25 sections (this document)
- [ ] `TASK_2.7_CHECKPOINT.md` present (if context compacts during build; otherwise optional)
- [ ] `AdaptiveExplorationSpec` / `adaptive_exploration_id_of` exist in `core/adaptive_exploration.py`; pure; experiment-free
- [ ] Subspace filter operates on existing `MutationSpace`; no invented parameters
- [ ] CLI exists (`run_adaptive_exploration.py`) with `--analysis-only` and `--adaptive-continue`; deterministic output
- [ ] Real bounded C demo executes 2-pass loop; exact steps/decisions/termination recorded
- [ ] Replay deterministic from same spec + seed + budget
- [ ] Lineage optional/additive; absence does not break execution
- [ ] Existing regression (adaptive 59, validation A–G, stability S1–S6) preserved
- [ ] No source/test/dependency/world modifications outside approved design scope
- [ ] `Task 2.7` not marked complete; `Task 2.8` not started

## 25. Rationale for Rejecting Alternatives
- A (temporal behavior) rejected: already partially covered by `behavior_vector` / divergence; larger feature-formula change in core; no new experiment unlocked
- C (query/persistence) rejected: low scientific leverage; pure tooling; can be added later as Stage 3 without blocking Stage 1/2
- B (researcher-constrained exploration) selected: smallest spec-layer change; unlocks multi-pass adaptive comparison across compositions using existing machinery; preserves all constraints; deterministic; testable; no optimization

---
Plan-Only Confirmation: No source file modified. No test modified. No world file changed. No dependency added. No experiment added. No commit made. Task 2.7 implementation NOT started. Task 2.8 NOT started.
