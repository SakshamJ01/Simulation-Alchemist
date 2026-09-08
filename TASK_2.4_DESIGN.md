# Task 2.4 — Cross-Composition Discovery Loop: Design (PLAN-ONLY)

> **Deliverable status: PLAN-ONLY design.** No source/test/dependency/world-file
> changes. Only this document (+ `PROJECT_STATE.md`) is part of this task's
> diff. **Stage 1 is the only build stage specified for immediate issue**; the
> remaining stages are sequenced but not to be started until issued.

## 1. Current architecture audit (as-built)

Composition layer (Task 2.3) provides, in `src/sim_alchemist/core/`:

- **`composition.py`** — discrete structural axis. `CompositionShape` (variant-aware
  binding set, canonical content-addressed `shape_id`), `CompositionSpace` (deterministic
  bounded enumeration, variant exclusivity), `CapabilitySurface`, and the
  **static** capability filter (`CAPABILITY_VALID`/`CAPABILITY_INVALID`,
  constructor-only, never stepped).
- **`templates.py`** — `CouplingTemplate` (frozen authoring surface), `CouplingTemplateRegistry`,
  `classify_composition` (the **ordered 6-status funnel**: capability → template → contracts →
  schedule → clock → EXECUTABLE; contracts never inferred; adapters only *constructed* for
  template-matched shapes, never initialized/stepped), `composition_id` (content-addressed
  24-hex), `generate_world(template)` (deterministic, immutable, adapter-free `WorldDefinition`
  with `ComponentSpec.variant` stamped per binding).
- **`catalog.py`** — `CompositionCatalog`: pre-classifies the whole enumerated space
  (23 shapes → **16 CAPABILITY_INVALID, 4 COUPLING_UNAVAILABLE, 3 EXECUTABLE**).
  `CatalogCandidate` carries shape/status/reason/composition_id/generated_world. Query APIs:
  `all/executable/invalid/by_status/by_shape_id/status_counts/explain`.

The 3 EXECUTABLE templates (verified this session) are:

| template | components (mesa/py-pde/network/pymunk) | world | executor_ref |
|----------|------------------------------------------|-------|--------------|
| `morphogenesis` | `{mesa, py-pde, pymunk/walls}` | `chemo_morphogenesis` | `chemomech.simulation.run_world` |
| `field_guided_movers` | `{py-pde, pymunk/movers}` | `field_guided_movers` | `...model.run_field_guided_movers` |
| `adaptive_network` | `{py-pde, pymunk/walls, network}` | `adaptive_network` | `...experiment.run_network_world` |

All share `macro_timestep=0.2`, `max_steps=160`.

### Reusable machinery (do NOT duplicate)

- `BehavioralAnalysisRunner(store, executor, observables, *, parameter_specs, analyzer)`
  (`core/behavior.py:914`), `rank_by_profile` (min-max across population + `run_id`
  tie-break; `_normalize_across` at `behavior.py:715`), `select_diverse_frontier`,
  `behavior_vector`, `behavior_distance`, `compute_frontier_diagnostics`, `FrontierDiagnostics`.
- `BehaviorFeatures.flatten()` → keys `"<observable>:<feature>"`, value `None` when
  undefined (never zeroed).
- `VariantRunner` (executor: any `WorldDefinition` → `ExecOutcome`), `run_id_of`.
- `SearchRunner`/`SearchSpec`/`SearchCandidate`/`SearchResult`/`search_id_of` (Task 1.9/2.0).
- `CompositionCatalog.executable()`, `CatalogCandidate.generated_world`, `generate_world`.
- `experiments/catalog.py`: `repository_surfaces()`, `repository_templates()`,
  `build_repository_adapters`, `build_repository_catalog()`.

### The three architectural gaps (verified)

1. **No `CompositionSearcher`.** `CompositionCatalog` yields EXECUTABLE candidates with
   `composition_id` + `generated_world`, but nothing connects them to unified discovery.
2. **Observables asymmetry.** Only Experiment C exposes
   `experiments/network_morphogenesis/experiment.py:build_network_observables(...) ->
   dict[str, ObservableSeries]`. Experiments A (`chemomech/`) and B
   (`experiments/field_guided_movers/`) record raw trajectory fields only — no
   `build_*_observables` builders.
3. **Lineage gap.** `RunRecord`/`runs` table (plus `sweeps`/`behavior_analyses`/`searches`)
   carry only `world_id`/`world_hash`, no `composition_id` anywhere. `world_hash`/`run_id`
   already distinguish compositions (because `ComponentSpec.variant` stamps fold into
   identity), but composition provenance is not *named*.

## 2. Role of CompositionSearcher

`CompositionSearcher` is a **thin composition-level orchestrator**, not a new engine.
It:

1. Enumerates `catalog.executable()`.
2. `generate_world(template)` per candidate.
3. Evaluates each via the opaque experiment executor/observables map.
4. Collects `BehaviorFeatures` per candidate.
5. Runs **one** cross-composition `rank_by_profile`.
6. Runs **one** `select_diverse_frontier`.

It wraps — never duplicates — `VariantRunner`, `BehavioralAnalysisRunner`,
`rank_by_profile`, `select_diverse_frontier`. It introduces no new search/analysis/
diversity concept. The composition axis is a distinct **root-level axis above** the
parameter-mutation (child) axis.

## 3. Composition-vs-parameter search distinction

**Unified hierarchy (option D).**

- **Composition** = discrete, structural axis. Identity = `composition_id` (content-
  addressed from shape/template) + `shape_id`. Changing composition is a **new root** of
  lineage (`parent_run_id=None`).
- **Parameter** = leaf dimension, `config.*` path mutation (Task 1.6 `Mutation`).
  Identity = `run_id_of(world_hash, seed)`, child edge via `parent_run_id`.

The two are distinct; composition is never collapsed into a leaf parameter and parameter
mutation never changes composition roots. A composition is a discrete grid position;
parameter mutation is a local variation *within* a composition. Both live under one
`LineageStore`, differentiated by `composition_id` (root) vs `parent_run_id` (child).

## 4. Composition evaluation model

**Mechanics of B, hierarchy of D, budgeted to 3 compositions.**

- Baseline: one run per EXECUTABLE composition (metrics + `feature_snapshot` when the
  composition has an observables builder).
- Local parameter note: Experiments A/B declare no `PARAMETER_SPECS`; C declares the three
  meaningful ones. Discovery does an **optional small local parameter search inside each**
  composition only when `PARAMETER_SPECS` exist; otherwise it contributes the baseline only.
  Budget is deliberately small (3 compositions × a few runs each) — this is a discovery
  *demonstration*, not an exhaustive optimizer.
- Evaluator records one baseline run per EXECUTABLE composition with its `composition_id`;
  execution is delegated to an opaque experiments-owned executor map (see §10).

## 5. Cross-composition feature strategy

**Hybrid B+C, principally B.**

- **(B)** All compositions expose a common semantic interface: `BehaviorAnalyzer` yields
  the **same 18+ dimensionless features per series** for any `ObservableSeries` with the
  same semantic meaning (time axis, quantity). The union of common series across the
  compositions forms the cross-composition feature schema.
- **(C)** Where observables share *semantics* but differ in *name*, the profile declares
  explicit **semantic aliases** (e.g. `wall_count` property). Aliases are data-declared in
  the profile, never hard-coded in core.
- **Intersection default:** with no aliases declared, the cross-composition feature schema
  is the intersection of per-composition feature keys.
- **No fake equivalence:** `wall_count` ≠ `network_load_max` unless a semantic alias is
  explicitly declared. Missing features remain **explicit** (`None`), never zeroed.
- Concrete asymmetry: today only C has `build_*_observables`. For a full A/B/C comparison,
  Stage 3 adds A/B `build_*_observables` **in `experiments/`** (experiment-side), so the
  common schema is built from all three. Until then, the common schema is whatever
  observables builders exist.

## 6. Normalization strategy

Cross-composition **pool-level min-max** over *all* candidates (all compositions in the
pool). This is exactly the existing `_normalize_across` behavior (`behavior.py:715`) /
`_normalize_vectors` applied at the higher pool level. **No new normalization layer.**
Per-metric min-max across the population with the documented `None`/non-finite → 0.0
and constant-dim → 0.0 semantics already in `rank_by_profile` / `select_diverse_frontier`.
The pool for normalization is the union of all evaluated candidates across compositions
(not per-composition), so scores are comparable across the composition axis.

## 7. Composition result model

New generic `src/sim_alchemist/core/composition_search.py` (Stage 1):

- `CompositionCandidate` — `composition_id`, `shape_id`, `template`, `run_id`,
  `world_id`, `world_hash`, `mutations`, `features` (`BehaviorFeatures`), `score`,
  `rank`, `explanation` (`RankedRow.explanation()`).
- `CompositionEvaluationResult` / `CompositionCandidateResult` (Stage 1 drafter dataclasses).
- `CompositionDiscoveryResult` — candidates, ranking, frontier, timing;
  `as_dict(canonical=True)` is **bitwise-deterministic**; `timing` excluded from the
  canonical form.

All compose existing `BehaviorFeatures` / `RankedRow` / `FrontierDiagnostics` — no new
feature/ranking types.

## 8. Lineage model

**Additive, backwards-compatible.** One SQLite `LineageStore`; no second DB.

- Add nullable `composition_id` column on `runs` + `RunRecord.composition_id`
  (default/evaluated-only) + `_migrate()` `ALTER TABLE ... ADD COLUMN` for pre-2.4 stores.
- Composition change = **new root** (`parent_run_id=None`, new/composite `composition_id`);
  parameter mutation = **child** (`parent_run_id` set, same `composition_id`).
- New compact **metadata-only** `composition_discoveries` table + `CompositionDiscoveryRecord`
  (id, profile, seed, catalog id, per-composition candidate summary, ranking, frontier,
  timing). Never trajectories.

## 9. Deterministic identity

- `composition_discovery_id_of(catalog_id, profile, seed, evaluator_config)` =
  content-addressed `sha256(...)[:24]`.
- Per-candidate identity: `composition_id` (from the candidate) + `run_id_of(
  world_hash, seed)`.
- `timing` excluded from canonical form so identity is unaffected by runtime.

## 10. Execution model

- `catalog.executable()` → `generate_world(template)` → opaque **experiments/**-owned
  executor/observables map keyed by `composition_id` → `VariantRunner`/`BehavioralAnalysisRunner`.
- **Core never dispatches on template name/composition.** `executor_ref` stays an opaque
  string; the experiments layer maps `composition_id → (executor, observables builder)`.
  There is **no** `if composition == A` branch in generic core.
- Only **EXECUTABLE** catalog candidates may enter discovery. Non-executable statuses
  (CAPABILITY_INVALID/COUPLING_UNAVAILABLE/COUPLING_INVALID/SCHEDULE_INVALID/CLOCK_INVALID)
  are skipped and reported (validation), never evaluated.
- **No automatic coupling inference**: discovery runs only pre-classified EXECUTABLE
  candidates; it never invents couplings or re-classifies.

## 11. Fair-comparison rules

- Same `InterestingnessProfile`, same analyzer config, same macro horizon
  (`0.2 × 160`), same seed where valid.
- Documented native-substep differences (each experiment's scheduler sub-division) are
  acknowledged, not hidden; features are dimensionless/fractional so horizon is comparable.
- Per-composition budget is bounded; the discovery demo is presented as a demonstration,
  not a calibrated head-to-head.

## 12. Diversity strategy

**Behavior space only.** Reuse `select_diverse_frontier` / `behavior_vector` /
`behavior_distance` / `compute_frontier_diagnostics` unchanged, applied over the
**cross-composition pool**. **Composition identity is explicit metadata, never a distance
term** — two compositions are different because they have different ids, but their
dissimilarity is their *behavioral* distance, not their id. Multi-composition frontier
spans behavioral diversity without needing an executor in core.

## 13. Demo design

Single `run_composition_discovery.py` CLI (matching the `run_*.py` convention, e.g.
`run_catalog_demo.py`):
- enumerate EXECUTABLE compositions,
- evaluate baselines (+ local parameter search where `PARAMETER_SPECS` exist),
- build the cross-composition pool,
- rank + frontier,
- print candidates / ranking / explanation / frontier diagnostics.

Demonstration only; small budget.

## 14. Visualization

One **quality/diversity matplotlib scatter**: x = behavioral diversity (min distance to
selected frontier / frontier slot), y = normalized quality score, each point labeled and
colored by `composition_id`. Optional frontier-path / ranking table in the CLI text.

## 15. Validation strategy

Tests A–L (per the plan's §23), wrapping the same scientific checks:
- **A** all EXECUTABLE candidates evaluated / have a candidate result
- **B** non-executable candidates skipped and reported
- **C** determinism: identical inputs → identical decision/identity/order
- **D** distinguishable composition ids across the three compositions
- **E** common-schema compare across compositions
- **F** missing-feature-explicit (and never-fake-equivalence)
- **G** deterministic cross-composition ranking
- **H** multi-composition behavioral frontier
- **I** composition lineage recorded (root) + parameter lineage recorded (child) separately
- **J** no experiment-specific branches in generic core (forbidden-token purity scan on
  `core/composition_search.py`)
- **K** only EXECUTABLE can enter discovery
- **L** canonical repeatability (`as_dict(canonical=True)` bitwise-stable)

Conventions mirror existing tests (`test_catalog.py`, `test_behavior_analysis.py`,
`test_search.py`, `test_diversity.py`, `test_templates.py`).

## 16. Scientific limitations (preserved, not hidden)

- Cross-composition feature comparison is semantic-schema-based; it can only be as fair as
  the declared aliases and the native observables. It does **not** claim physical
  equivalence of A/B/C quantities absent an explicit semantic alias.
- Native-substep and engine differences mean A/B/C runs are not bitwise-comparable peers.
- Diversity is behavioral (Task 1.8 features); it is a heuristic, not a calibrated metric.
- Small discovery budget; results are a demonstration, not exhaustive optimization.
- All Experiment A/B/C scientific limitations (PDE approximation, simplified walls, custom
  network transport, non-equilibrium claims) remain in force; discovery neither calibrates
  nor validates them.

## 17. Architectural risks (severity + mitigation)

1. **Heterogeneous observables** (A/B lack builders). *Medium.* Stage 3 adds A/B
   `build_*_observables`; intersect schema; explicit `None`.
2. **Normalization bias** across compositions. *Medium.* Pool-level min-max over all
   candidates; reuse existing normalization; document.
3. **Unfair runtime comparison.** *Medium.* Same macro horizon/seed; document native
   substeps; dimensionless features.
4. **Executor leakage into core.** *Medium–High.* Opaque `executor_ref` + experiments-owned
   map; no dispatch-on-name in core; purity scan in validation J.
5. **Lineage ambiguity** (composition vs parameter). *Medium.* `composition_id` root vs
   `parent_run_id` child; additive column; tests I.
6. **Catalog drift** (shape set changes). *Low–Medium.* Content-addressed ids; regenerate;
   status_counts guard.
7. **Only-3-executable** limits search breadth. *Low.* Expected; document; demo framing.
8. **Non-equivalent quantities.** *Medium.* Explicit semantic aliases only; no fake
   equivalence; test F.
9. **Combinatorial explosion** if per-composition search grows. *Medium.* Bounded budget,
   small demo, no exhaustive optimizer.
10. **Hidden dependence on the 3 experiments.** *Medium.* Core never references them; the
   experiments-owned map is injected; validation J.

## 18. Exact staged implementation sequence

- **Stage 1 — result/identity/lineage + baseline scaffolding** (smallest first Build; the
  only stage to be issued immediately): `core/composition_search.py` with the drafter
  dataclasses (`CompositionCandidateResult`, `CompositionEvaluationResult`) +
  `composition_discovery_id_of` + additive `composition_id` lineage field (`RunRecord`
  + `_migrate()` ALTER) + compact `composition_discoveries` table +
  `CompositionDiscoveryRecord` + an evaluator that records **one baseline run** (metrics
  only, `feature_snapshot` when an observables builder exists) per EXECUTABLE composition
  with its `composition_id`. **No orchestrator loop, no cross-composition pool/rank/
  frontier, no new experiment observables, no search integration.**
- **Stage 2 — thin `CompositionSearcher`**: enumerate EXECUTABLE → generate → run →
  collect → pool → delegate to `rank_by_profile`/`select_diverse_frontier`.
- **Stage 3 — common feature extraction / cross-composition mapping**: add A/B
  `build_*_observables` in `experiments/` + profile alias map; build the common schema.
- **Stage 4 — cross-composition ranking + reuse diversity frontier**.
- **Stage 5 — discovery CLI + artifact** (`run_composition_discovery.py`, scatter + text).

## 19. Smallest first Build task (exact, to be issued)

> Add `src/sim_alchemist/core/composition_search.py` implementing the **composition
> evaluation result + identity**, and extend `lineage.py` with an **additive** `composition_id`
> column on `runs` (`RunRecord.composition_id` + `_migrate()` `ALTER`) plus the compact
> `composition_discoveries` table and `CompositionDiscoveryRecord`. Provide an evaluator that
> records **one baseline run** (metrics only, `feature_snapshot` when an observables builder
> exists) per EXECUTABLE composition with its `composition_id`, deterministic
> `composition_discovery_id_of`, and the `CompositionCandidateResult` /
> `CompositionEvaluationResult` dataclasses. **Do NOT** add the orchestrator loop, the
> cross-composition pool/rank/frontier, new experiment observables, or any search
> integration yet — identity and lineage first.

## 20. Constraints (non-negotiable)

- CompositionSearcher is a thin composition-level orchestrator.
- Reuse `VariantRunner` / `BehavioralAnalysisRunner` / `rank_by_profile` /
  `select_diverse_frontier`.
- Composition is a discrete structural axis; parameter mutation is a separate config-leaf
  lineage axis.
- Cross-composition comparison uses a common `ObservableSeries` / semantic feature schema.
- Missing features remain explicit; never fake equivalence.
- Cross-composition normalization is pool-level and reuses existing behavior/ranking
  machinery.
- `composition_id` is additive metadata in the existing lineage store.
- Composition identity is never used as a behavioral distance term.
- Only EXECUTABLE catalog candidates can enter discovery.
- No automatic coupling inference.
- No experiment-specific branches in generic core.
- No new dependencies.
- Stage 1 is ONLY result/identity/lineage + baseline evaluation scaffolding; no full search
  orchestrator yet.
- No source/test/dependency/world-file changes in this plan task.
- Do not start Task 2.4 implementation beyond the issued Build stage; do not start Task 2.5.

## 21. Verification of the plan task

- `git diff` contains **only** `TASK_2.4_DESIGN.md` and `PROJECT_STATE.md`.
- No source/test/dependency/world-file modifications.
- `PROJECT_STATE.md`:
  - Current activity: `Task 2.4 — cross-composition discovery architecture design (PLAN-ONLY)`
  - Next exact task: `Task 2.4 Build Stage 1`
- Task 2.4 NOT marked complete. Task 2.5 NOT started. No commits.
