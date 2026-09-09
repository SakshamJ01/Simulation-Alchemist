# Task 2.5 — Cross-Composition Parameter Sweep / Joint Structural + Parametric Discovery

## Status: PLAN-ONLY (no source code modified)

This document is the authored design for **Task 2.5**. It recommends a single
model, grounds every design decision in the as-built repository APIs, and
organises the work into Build stages. **Nothing here is implemented.** The only
files touched by this task are `TASK_2.5_DESIGN.md` and `PROJECT_STATE.md`.

---

## 1. Architecture gap filled by this task

Task 2.4 introduced the **structural** discovery axis: a catalog of
coupling-valid `EXECUTABLE` compositions, each evaluated exactly once (its
baseline world), reduced to a common-observable envelope, ranked across
compositions, and reduced to a diversity frontier. That axis answers "which
*composition shapes* (bindings of components/variants) are executable and,
under their *default* configuration, produce an interesting common signal."

Task 1.6/1.7/1.8/1.9 introduced the **parametric** discovery axis: within a
*fixed* world, deterministic `MutationSpace` sweeps, behavioral
characterisation, ranking, and guided beam search. That axis answers "for this
*one* world, which parameter variants are behaviourally interesting."

What is **missing** is the joint surface:

> For each EXECUTABLE composition, explore its *own* legitimate parameter
> variants (**sweeps-per-composition**), then compare the resulting common
> behavior *across* compositions — using the Task 2.4 common-observable /
> cross-composition ranking machinery that today only sees one baseline per
> composition.

The gap is therefore a *joint structural + parametric discovery layer*: the
parametric axis (Task 1.6–1.9) is applied **per composition** inside the
structural axis (Task 2.3–2.4), producing one ranked, diversity-aware result
that covers both axes at once. Today these two axes are completely disjoint:
Task 2.4 never varies a parameter; Tasks 1.6–1.9 never vary the composition.

**Concrete evidence of the gap.** Only three compositions are EXECUTABLE in the
catalog (`catalog.executable()`), and Task 2.4 evaluates each one baseline only.
Experiment C (`network_morphogenesis`) declares `PARAMETER_SPECS`
(`components.network.config.loss`, `config.force_fmax`, `config.source_amplitude`);
Experiments A and B declare none today. So a joint discovery pass over all three
compositions is currently impossible: even where parameter spaces *exist* (C),
nothing sweeps them in a composition-aware way, and where they don't (A/B) there
is no declared space to sweep at all.

---

## 2. Task definition

**Task 2.5** provides a deterministic, generic, experiment-agnostic
**CrossCompositionSweep** layer that, for every EXECUTABLE composition,

1. binds that composition's *own* legitimate parameter space (its
   `MutationSpace`, declared per composition and never fabricated),
2. runs a **control-first, seeded** sweep over that space **reusing the
   existing `SweepRunner`** (no new sweep engine),
3. records every variant run in the lineage store with its
   `composition_id` stamped (so the structural identity and the variant
   identity coexist),
4. reduces each *variant* of each composition to the **common-observable
   envelope** (the same `CommonObservableSet` / vocabulary Task 2.4 uses),
5. produces a **ranked + diversity-frontier** cross-composition view over
   the *union of all variants and baselines*, reusing `rank_compositions` /
   `select_frontier`, and
6. reports everything with deterministic content-addressed identities.

The scope is **exploration only**: it asserts deterministic exploration of
parameter variants within multiple executable compositions followed by common
behavioral comparison. It never claims global optimisation, "best
parameters", "best composition", or universal semantic equivalence of
parameters across experiments (see §21).

**Explicitly out of scope for Task 2.5:** any new simulation concept, any
non-deterministic / evolutionary / Bayesian / ML / RL search, any clustering,
any new external-engine adapter, any plugin architecture, any experiment
database. `composition_id`, `shape_id`, `world_hash`, `sweep_id`, and `run_id`
remain distinct concepts (§7).

---

## 3. Composition vs. parameter distinction (and why they must stay separate)

A **composition** is the structural choice: which components (and which
variant of a component) are bound together, in what coupling schedule. Its
identity is `composition_id` — content-addressed over the *shape* and *config
surface* and *contracts/schedule* — **ignoring** `max_steps` and the *values*
of individual tunable parameters. A composition answers "what world is this,
structurally?"

A **parameter** is a *mutable numeric/toggle value inside one component's
config* (or the world-level `seed`/`max_steps`/`macro_timestep`). Its identity
is the **config path within a component/variant** whose value a `Mutation`
changes. A sweep varies parameters *without* changing the composition identity.

The two **must not be collapsed**:

- Varying a parameter must **not** change `composition_id` (it is
  content-addressed over the config *surface*, not the config values). A
  sweep is *within* one composition.
- Conversely, two compositions that share a component still keep their own
  identities; a parameter path is defined *relative to* a component/variant,
  so `components.network.config.loss` in composition-1 is not automatically
  the same parameter as a same-named path in another composition unless an
  explicit semantic mapping states so.

This separation is what makes the Task 2.4 `CommonObservableSet` a valid
comparison surface: every observed baseline/variant is tagged with its
`composition_id` **and** its `run_id` (variant identity), never conflated.

---

## 4. Recommended minimal viable product (MVP)

The MVP is a **Stage 1 (binding + result model) + Stage 2 (sweeps-per-composition
runner)** that produces, for each EXECUTABLE composition that declares a
parameter space, a deterministic per-composition sweep and a cross-composition
ranked/frontier summary. Concretely:

- **Inputs**: the `CompositionSearcher`-style discovered set of EXECUTABLE
  compositions; optics of `worlds/*.yaml` config surfaces; an experiment-owned
  per-composition `MutationSpace` declaration (§5); a common
  `InterestingnessProfile` / selection profile (§14).
- **Actions**: for each EXECUTABLE composition in catalog order,
  `SweepRunner(store, executor, parameter_specs=...).sweep(generated_world,
  mutation_space)` — reusing the existing sweep engine verbatim (§6); then
  `CommonObservableSet`-style extraction over every variant; then
  `rank_compositions` + `select_frontier` over the whole variant+baseline pool.
- **Output**: a single `CrossCompositionSweepResult` (in-memory, compact
  persisted metadata) with per-composition ranking and a cross-composition
  diversity frontier over the union of variants.

The MVP deliberately does **not** attempt a global Cartesian product across
compositions (§12), does **not** invent shared parameter dimensions where the
semantics differ (§5), and does **not** fabricate a parameter space for A/B if
the maintainers do not declare one (§18).

**Smallest first Build task** (see §25) strips this to the *binding + result
model* only: declare a per-composition `MutationSpace` registry surface and the
`CrossCompositionSweepResult` type with a deterministic identity, with **no**
execution yet.

---

## 5. Parameter-space ownership (recommended: D — hybrid, registered per composition)

The core must stay experiment-free; the scientific *meaning* of a parameter
path lives with the experiment. Four candidates, evaluated against the
as-built `repository_executors()` / `repository_templates()` pattern:

- **A — on the `CouplingTemplate`.** Add a `parameter_space` field (or a
  registry key) to `CouplingTemplate`. Pros: the template already carries the
  right experiment coupling semantics and the config surface. Cons: `templates.py`
  is generic-core and must stay experiment-free; a frozen field holding an
  experiment-typed `MutationSpace` would import experiment concerns into the
  core. The template is the **right place to *name/reference* a space**, not to
  *own* the space definition.
- **B — on the experiment-owned executor.** Pass `parameter_specs` to the
  executor. Pros: A/B/C executors already conform. Cons: `parameter_specs`
  (validators) ≠ the full `MutationSpace` (value lists + Cartesian order); the
  executor would have to know both — a conflation of "what values are valid"
  with "what a sweep enumerates."
- **C — separate experiment-owned config module** (e.g. per-experiment
  `parameter_space.py`). Pros: clean separation, mirrors `coupling.py`
  ownership. Cons: no registry; the composition layer would not discover it
  uniformly.
- **D — hybrid: experiment-owned `MutationSpace` keyed by composition_id,
  surfaced through an experiments-owned map.** Mirror the established
  `repository_executors()` composition→executor map with a parallel
  `repository_parameter_spaces()` composition→`MutationSpace|None` map.
  `CouplingTemplate` gains only a **pure identifier** (e.g. an optional
  `parameter_space_ref: str | None`) that stays experiment-agnostic, while the
  actual `MutationSpace` objects live in the experiments layer and are looked
  up by the orchestrator.

**Recommendation: D.** It keeps `templates.py` generic (only a ref, never the
objects), keeps the science in experiment-owned modules (matching the codebase
philosophy that "the science ... lives in experiment coupling modules, not in
engine subclasses"), and gives the generic orchestrator an opaque
composition→space map just like the existing opaque composition→executor map.
There is **no plugin infrastructure** — `repository_parameter_spaces()` is a
plain function, exactly like `repository_executors()`.

The **generic core** exposes an abstract surface only: a `CrossCompositionSweep`
orchestrator that consumes a `Mapping[str, MutationSpace | None]` and never
cares which experiment produced it. This honours the mandate "generic core must
remain experiment-free, science experiment-owned, no plugin infrastructure."

---

## 6. Sweep-reuse strategy (orchestration over `SweepRunner`, no second sweep engine)

**Golden rule (mandate + AGENTS.md):** `CrossCompositionSweep` is
*orchestration over the existing `SweepRunner`*, never a reimplementation of
Cartesian enumeration, mutation validation, variant cloning, run recording, or
ranking.

Concretely, the orchestrator calls, for each EXECUTABLE composition:

```python
runner = SweepRunner(store, executor, parameter_specs=specs)
result = runner.sweep(base_world, mutation_space, sweep_id=sweep_id_of(...))
```

which already provides (verified in `core/sweep.py` and `tests/test_sweep_ranking.py`):

- baseline control **first**, never mutated (check F),
- `MutationSpace.variant_mutation_sets()` Cartesian order, right-most fastest,
- whole-space upfront validation against `parameter_specs` before any execution,
- no-op (world-identical) variants skipped and counted,
- deterministic `run_id_of(world)` identity, `SweepRecord` persisted (compact),
- `rank_results` generic per-metric ranking with deterministic tie-break.

The orchestrator adds **only** the composition-aware bookkeeping that no single
sweep expresses today:

1. *per-composition iteration* in canonical catalog order,
2. `composition_id` stamping on every recorded variant run (§8) — today
   `SweepRunner`/`VariantRunner`/`BehavioralAnalysisRunner` record `RunRecord`s
   **without** `composition_id` (verified in `runner.py`/`behavior.py`); only
   `evaluate_composition_baseline` stamps it. The orchestrator (or a thin
   optional `composition_id=` parameter threaded into the core recording paths)
   must attach it,
3. *cross-composition* common-observable extraction + ranking + frontier (§14),
4. a deterministic identity for the *whole pass* (§7).

Everything else is delegated. No duplication of sweep/ranking/mutation logic.

---

## 7. Identity hierarchy (distinct, never overloaded)

Each identity is a separate concept and maps to a distinct, already-existing or
newly-typed value:

| Concept | Today | Semantics |
|--------|-------|-----------|
| `shape_id` | `core/composition.py` | content-addressed structural shape (bindings) |
| `composition_id` | `core/templates.py::composition_id` | content-addressed composition (shape + config surface + contracts/schedule + variant stamps); ignores `max_steps` and config *values* |
| `world_hash` | `core/lineage.py::world_hash` | sha256 of `world.as_dict()` JSON sort_keys — the concrete config *values* |
| `sweep_id` | `core/sweep.py::sweep_id_of` | deterministic from world hash + mutation space |
| `run_id` | `core/lineage.py::run_id_of` | deterministic from world content + seed — the concrete executed variant |
| mutation lineage | `core/runner.py` (parent_run_id) | parent→child links within one composition's sweep |

**The new concept for Task 2.5** is a **pass-level identity** — the analog of
Task 1.9 `search_id_of` / Task 2.4 `composition_discovery_id_of`:

```text
cross_split_sweep_id = content-address over
  (catalog composition universe, ordered)
  + per-composition parameter spaces (their canonical MutationSpace dicts)
  + profile
  + selection profile
  + seed
  (+ optional evaluation/observation config)
```

It must be **pure content addressing** over the authoritative inputs, contain
**no transient data** (no timestamps, no run ids of *results*), and replay
deterministically. This mirrors `composition_discovery_id_of` exactly (Task 2.4,
`composition_search.py`), which the re-context confirmed is a deterministic
24-hex over the catalog universe + profile + seed + evaluation config.

**No overloading rule:** never put the pass identity where a `composition_id`
or `run_id` belongs, and never let a `sweep_id` stand in for a `composition_id`.
A viewer must be able to answer "which composition, which parameter variant,
which run" from the recorded identity fields alone.

---

## 8. Lineage model (how runs are recorded, stamped, and linked)

The Task 1.6 `LineageStore` and its `RunRecord` are the substrate. Key verified
facts to preserve:

- `run_id` is deterministic from the canonical world content + seed → a variant
  is **idempotent** on re-run (same world ⇒ same `run_id`).
- `RunRecord` already carries a `composition_id` field (added by Task 2.4), but
  the **core sweep/behavior runners do not populate it** — only
  `evaluate_composition_baseline` does.

**Task 2.5 lineage design:**

- Every sweep of a composition records its **baseline as a root run**
  (`parent_run_id=None`) inside that composition's sweep — but the baseline is
  the *same* world as the composition's Task 2.4 root evaluation, so its
  `run_id` coincides (idempotent `record_run` overwrite, no duplicate rows).
  The Task 2.4 evaluation already stamped that baseline's `composition_id`; a
  re-sweep re-records the identical run id (no new row). This keeps the Task 2.4
  baseline **the** canonical baseline for that composition (see §9).
- Each **variant** run is recorded with `parent_run_id` = its composition's
  baseline `run_id`, its `mutations` (the `MutationRecord`s that produced it),
  its `composition_id`, and its compact `metrics` (+ optional
  `feature_snapshot`), exactly as `BehavioralAnalysisRunner` does today — but
  with `composition_id` added.
- A `SweepRecord` per composition persists the compact sweep metadata
  (mutation space, ordered variant run ids, timing) — no trajectories, no
  per-step observables, matching the store's "compact only" policy.
- A new **`CrossCompositionSweepRecord`** (compact, analogous to
  `SearchRecord`/`BehaviorAnalysisRecord`) persists the pass-level metadata:
  `cross_split_sweep_id`, the ordered (composition_id, sweep_id, baseline
  run_id, variant run ids) map, the profile/seed, and timing. No per-step data.

**Stamping requirement:** because the core runners don't stamp `composition_id`,
the Build must either (a) thread an optional `composition_id=` into the core
`SweepRunner`/`VariantRunner`/`BehavioralAnalysisRunner` recording paths
(minimal, backwards-compatible, defaults to `None`), or (b) have the
orchestrator re-stamp recorded runs after the sweep (an upsert by `run_id`).
Recommendation: **(a)**—a small optional parameter is the cleanest, mirrors how
`evaluate_composition_baseline` already builds a `RunRecord` with
`composition_id`, and keeps the store correct on first write. Either way the
scientific contract is the same: **every recorded run created during a Task 2.5
pass carries its `composition_id` unless it is the (already stamped) baseline.**

---

## 9. Baseline semantics

A composition's **baseline** is its generated default world at the discovery
seed, executed once. It is:

- **explicit** (recorded as a root run, `parent_run_id=None`),
- **immutable** (never mutated in place — `apply_mutations` deep-clones; the
  base `WorldDefinition` object is never edited, verified in `sweep.py`),
- **the reference** for divergence/behavior features (baseline divergence is
  `None`, never 0, per Task 1.8),
- **the parent** of every variant in that composition's sweep,
- **the seed for child determinism** (§16).

Task 2.4 already produced and stamped each composition's baseline. Task 2.5
**reuses that same world** (content-identical ⇒ identical `run_id`, idempotent)
rather than minting a new baseline. This is what makes the Task 2.4 evaluation
and the Task 2.5 sweep compose cleanly: **one canonical baseline per
composition, shared across both discovery passes.**

Within a sweep, the baseline is the first executed variant and the ranking
reference — consistent with `SweepRunner` (baseline-control-first, check F) and
`BehavioralAnalysisRunner` (baseline analyzed first as control). The baseline is
always preserved in the cross-composition pool even if a parameter variant
scores higher on the profile; it remains the anchor of the lineage.

---

## 10. Fairness rules

Fairness here means: **a variant is comparable to another variant only when the
comparison is expressed in terms both can meaningfully produce, under
controlled, identical conditions otherwise.**

Concrete, stated rules for the design:

1. **Within a composition:** variants differ only on the *declared* swept
   parameter(s) of their own `MutationSpace`; all other config, the seed
   policy (§16), `max_steps`, `macro_timestep`, and the coupling schedule are
   held identical to the baseline. This is guaranteed by `apply_mutations`
   (single-parameter mutations, no structural mutation, world otherwise
   cloned from baseline).
2. **Across compositions:** comparison happens only on the **common-observable
   vocabulary** — the sorted union of metric names that *every* composition's
   variants actually produce (via `common_observable_names` /
   `extract_common_observables`). A metric only one composition produces does
   not enter the across-composition ranking; it appears as an explicit
   missing row (`available=False`, value `None`) in the others, never imputed.
3. **Seed fairness:** every composition's baseline uses the **same discovery
   seed**, and every variant derives its seed deterministically from the
   baseline seed + composition identity + mutation contents (§16), so no
   composition is favoured by a lucky/different random stream. (Candidate
   seed policies evaluated in §16.)
4. **Same horizon:** all variants use the baseline's `max_steps` /
   `macro_timestep`; horizons are never silently altered to make a variant
   look better.
5. **The common score** (across compositions) is min-max normalized over the
   *whole evaluated pool* (all compositions' variants + baselines), exactly as
   `rank_compositions` / `rank_by_profile` do today — so no composition gets an
   advantage from having a wider range of scores.
6. **No fabrication of parameter equivalence:** a numeric scalar in experiment
   A and a numeric scalar in experiment C are **not** the same dimension unless
   an explicit `ComponentBinding`/config-path semantic alias declares them
   genuinely equivalent (§5, §13, §18). Fair comparison begins from genuinely
   common *observables*, never from assumed-common *parameters*.

---

## 11. Missing dimensions

Two distinct senses of "missing" must be kept apart:

1. **Missing parameter space** — a composition (e.g. A or B, if undeclared)
   has *no* `MutationSpace`. This is a legal, explicit state. The orchestrator
   records that composition's presence with `space=None` and still includes
   its **baseline** in the cross-composition pool, but sweeps nothing for it.
   It is reported as "no parameter space declared", never treated as an empty
   or identity sweep. (This is the direct analog of "missing = explicit
   `available=False`" in the Task 2.4 observables layer.)
2. **Missing common observable** — a metric name that only some compositions
   produce. Following `observables.py` exactly, it stays **explicit and
   explicit-only**: `available=False`, `value=None`, never fabricated, never
   imputed, never unioned into the genuinely-common vocabulary. It simply does
   not participate in across-composition ranking.

Neither kind of missing dimension is ever turned into a fake equality. A
composition with no declared space is *not* swept; a composition with a missing
common observable still appears with the missing row visible. This preserves
the AGENTS.md principle ("missing = explicit `available=False`/`None`") that
Task 2.4 established.

---

## 12. Global vs. local sweep (recommendation: per-composition local sweeps)

The naive design is a **global Cartesian product**: pick one "dimension" per
composition and cross them (e.g. A–config.force_fmax × B–n_movers ×
C–loss). This is both **semantically wrong** and **exponential**:

- Semantically: because parameters are not shared across experiments unless
  explicitly aliased (§5, §13), a "global space" would force an equivalence
  between unrelated scalars, violating §10.6 and §18.
- Combinatorially: the product explodes — 3×4=12, 10×10=100, 50×20=1000 runs
  (§13), and each composition would be run many times for orthogonal axes it
  doesn't own.

**Recommendation: per-composition local sweeps.** Each EXECUTABLE composition
sweeps *its own* `MutationSpace` independently. The cross-composition layer
then ranks/frontiers over the *union* of each composition's variant+baseline
pool on the common-observable vocabulary. This:

- keeps parameter identity honest (each dimension lives in exactly one
  composition's space),
- bounds run count as the *sum* of per-composition `variant_count`s rather than
  their product,
- makes each sweep independently reproducible and independently rankable,
- still yields the joint result the task asks for (parameter variants **and**
  composition identity both visible in one ranked/frontier summary).

A global product is described and rejected unless an explicit semantic alias
makes two dimensions genuinely shared (rare, opt-in, see §18).

---

## 13. Combinatorial growth controls

Run count is the sum of per-composition sweeps. `MutationSpace` already lets the
experiment author fix `variant_count` per composition by choosing value lists.
The design adds **explicit, deterministic bounds** at the orchestrator:

- a **per-composition maximum** `max_variants` (e.g. default from the declared
  space; an orchestrator cap raises a validation error before any execution if
  exceeded — consistent with "validate the whole space before any simulation"
  in `sweep.py`),
- a **pass-level maximum** `max_total_variants` (sum across compositions), to
  keep the joint pass tractable,
- **exhaustive-first, bounded** semantics: the MVP enumerates the full declared
  space (no sampling), governed only by the caps; rejection on exceeding a cap
  happens before any simulation starts.

Growth sanity for the validation example (verified values from
`network_morphogenesis/experiment.py` `PARAMETER_SPECS` with modest lists, e.g.
3 values per dimension): one composition × 3 dimensions × `k` values each ⇒
`k³`; at k=2 ⇒ 8 variants, k=3 ⇒ 27. Across 3 compositions with disjoint,
similarly-sized spaces ⇒ ~3 × `k³`, far smaller than a global `(k³)³`
product — the motive for §12. The caps make this explicit and safe in the
Build-stage test suite.

No sampling, no parallelism required for correctness (deterministic sequential
execution, matching every prior runner); parallelism is a future, optional,
identically-ordered optimisation only.

---

## 14. Behavior integration

The Task 1.8 `BehavioralAnalysisRunner` / `BehaviorAnalyzer` / 18-feature
`ObservableSeries` machinery is per-world and per-observable-series based. It
applies **within** a single composition whose executor also provides a
`build_*_observables` function (Experiment C does; A/B currently do not). So
behavior integration has two tiers:

1. **Within a composition (where per-step observables exist):** reuse
   `BehavioralAnalysisRunner` (or its `analyze` on the composition's baseline +
   `MutationSpace`) to build per-variant feature vectors and rank within that
   composition, when the composition provides an observables builder. This
   stays entirely within the existing Task 1.8 machinery.
2. **Across compositions (the Task 2.5 addition):** where per-step observables
   are not uniformly available, fall back to the **Task 2.4 common-observable
   envelope** — each variant is reduced to its `CommonObservableSet` over the
   genuinely-common metric vocabulary, and the cross-composition ranking /
   frontier uses the *feature-vector projection of those common metrics*
   exactly as `CompositionFeaturedRun` does in `composition_analysis.py`
   (duck-typed `(run_id, kind, features.flatten())` surface feeding
   `rank_compositions` / `select_frontier` / `behavior_distance`).

The crucial rule (mirror of Stage 3 observables, and §10/§11): **only genuinely
common observables may enter the across-composition feature vector.** A
composition-specific metric never leaks into the cross-composition distance/rank;
it stays an explicit missing row. This keeps the diversity frontier honest.

The `InterestingnessProfile` (with explicit max/min directions, weights) is
reused for within-composition ranking; a `SelectionProfile`
(quality/diversity weights) drives the cross-composition frontier, exactly as in
Task 1.9/2.4. Divergence stays task-1.8-defined (baseline divergence is `None`).

---

## 15. Profile scope

Two profiles are at play, and they must be kept distinct:

- **Per-composition profile** (`InterestingnessProfile`): how interesting a
  variant is *within its own composition* — over that composition's
  observables/features (§14 tier 1). Scope: one composition's pool.
- **Cross-composition profile** (`SelectionProfile` quality+diversity weights
  + the profile that defines "quality" over the common-observable vocabulary):
  how interesting/far-apart a variant is *across* compositions. Scope: the
  whole variant+baseline pool, over the genuinely-common metric feature vectors
  only (§14 tier 2).

A tasteful default: the cross-composition *quality* weight is derived from a
single common `InterestingnessProfile` expressed over the common-observable
metric names (e.g. `final_field_entropy` maximizing), so both tiers share one
"what is interesting" statement but apply it at the right scope. The design
defers exact profile fields to the Build stage but fixes the scoping rule: **a
profile is always evaluated against a well-defined pool and vocabulary, and the
pool/vocabulary are recorded with the result** so no ranking is ever ambiguous
about its basis.

Structural identity (`composition_id`/`shape_id`) is **not** a profile input —
profiles score observable/variant features, not composition identity.

---

## 16. Seed policy (recommended: composition-derived deterministic child seeds)

Three candidates were evaluated:

- **A — same seed for all compositions and all variants.** Simplest; maximal
  cross-composition comparability of *baselines* (all at the same seed). But if
  a parameter changes `seed`-sensitive behaviour, all variants sharing one seed
  are not independent draws — a weak form of confounding for any `seed`-sensitive
  path (Experiment A/C use `components.<id>.config.seed` / world seed).
- **B — global fresh random per variant.** Breaks determinism; forbidden (every
  runner is deterministic).
- **C — deterministic child seed derived from the baseline seed + composition
  identity + mutation contents.** Rooted in the same fixed discovery seed
  (fair, §10.3), but each variant gets a *unique, reproducible* seed via a
  stable hash of `(seed, composition_id, world_hash, mutations)`. Independent
  draws per variant *and* fully deterministic.

**Recommendation: C**, with the important caveat that the *baseline* always uses
the untouched discovery seed (so the Task 2.4 baseline and the Task 2.5 baseline
seed coincide). Only variant worlds may receive a derived seed. This preserves
both fairness (common root) and independence (variant-unique), and is fully
deterministic — no dict-ordering-dependent randomness (the derivation hashes
the *canonical* world/mutation serialisation, not a runtime dict). The design
further notes that `world.seed` participates in `run_id_of`, so the derived seed
is part of variant identity — correct and intended.

(NB: this derivation is applied only where a sweep actually mutates a
seed-sensitive path or where the space author opts in; the default in Stage 1
keeps the baseline's seed for a *non-seed-mutating* single-parameter sweep so
variants differ only on the swept dimension — see §10.1. The derived-seed mode is
an explicit option, not the silent default, to keep within-composition fairness
maximal.)

---

## 17. Result model

`CrossCompositionSweepResult` (in-memory, data-only; mirrors
`CompositionSearchResult` / `BehaviorAnalysisResult` style):

- **Identity:** `cross_split_sweep_id` (deterministic 24-hex, §7), `catalog`
  universe, `profile`, `selection_profile`, `seed`.
- **Per composition:** `composition_id`, `shape_id`, `world_hash`,
  **baseline** (`run_id`, seed), `mutation_space` (canonical dict),
  `sweep_id`, ordered `variants` (each `run_id`, mutations, metrics,
  common-observable set, optional feature vector), `n_planned/n_skipped/
  n_executed`, timing.
- **Pool:** the flattened ordered collection of all baselines + variants across
  compositions, each tagged with composition identity + variant identity.
- **Vocabulary:** the sorted genuinely-common observable names
  (`common_observable_names`) that entered the cross-composition pool, plus the
  explicit missing rows for each composition that lacks a name.
- **Cross-composition view:** ranked rows (`rank_compositions`) and the
  diversity frontier (`select_frontier`) with `FrontierDiagnostics`
  (`compute_frontier_diagnostics`) per composition and for the whole pass.
- **Timing:** evaluation/observation split + per-composition and total timing
  (mirrors `CompositionSearchTiming`).
- **Canonical `as_dict()`** for persistence/diffing.

Persistence: only the compact `CrossCompositionSweepRecord` and the underlying
`RunRecord`/`SweepRecord` rows are written to the lineage store. The in-memory
`observables`/per-step series (if any) are never persisted — same compact-only
policy as every prior layer.

---

## 18. Composition-specific parameter spaces (and the no-fabrication rule)

Because only Experiment C declares `PARAMETER_SPECS` today, the design must
explicitly handle spaces that don't exist yet:

- **C** has a real `PARAMETER_SPECS` (`components.network.config.loss`,
  `config.force_fmax`, `config.source_amplitude`) — the natural seed for a
  per-composition `MutationSpace`, with validator-bounds lifted from the same
  specs.
- **A/B** have no declared space. Task 2.5 must **not** invent one from the
  world YAML by brute-force guessing "tunable numerics" (that would fabricate
  semantic equivalence). Instead the design provides the *registry*
  (`repository_parameter_spaces()`) and defines the contract; declaring a space
  for A/B is a follow-on, experiment-owned, opt-in change (a small
  `parameter_space.py` + `MutationSpace` per experiment), out of scope for the
  core Build but fully supported by it. Until then A/B appear with
  `space=None` (§11.1) and contribute only their baselines to the pool.
- **Semantic aliasing** for genuinely-shared dimensions (e.g. if A and B both
  expose a `force_fmax` in a `pymunk` binding with the *same* meaning) is an
  explicit, opt-in declaration only — never inferred from identical path
  strings across different components/variants. The default is
  **no cross-composition parameter alignment**; each dimension lives in one
  composition's space (§5, §12).

This satisfies AGENTS.md/Task-2.4 principle: never fabricate parameter
equivalence — identity of a parameter stays tied to component/variant + config
path unless an explicit semantic mapping exists.

---

## 19. Scientific safety

The safest formulation of what Task 2.5 (and the eventual combined discovery)
claims:

> Given a set of EXECUTABLE compositions, we deterministically enumerate and run
> each composition's own declared parameter variants (baseline control included),
> record them in the lineage store with their composition identity, reduce every
> variant to the common-observable envelope of the genuinely-shared metrics, and
> produce a ranked / diversity-aware cross-composition view of that exploration.

Explicitly **not** claimed (must be documented, never scripted as fact):

- "best parameters" / "best composition" — only ranking within the explored set,
  under a stated profile and vocabulary,
- "global optimum" — exploration, not optimisation; bounded enumerated space,
- "universal semantic equivalence" of parameters across experiments — none is
  assumed,
- a calibrated physics/biology claim — the sweeps explore the *declared*
  hand-tuned parameter envelope; the underlying models remain experimental
  (§"Scientific Limitations" of AGENTS.md),
- sustained non-equilibrium behaviour — still a hypothesis, never asserted.

The existing scientific-limitations statements in AGENTS.md are preserved and
carry over unchanged (clamped-obstacle PDE not a true boundary, hand-tuned
params, simplified wall model, custom network transport rule, same-runtime
determinism).

---

## 20. Tests

New tests mirror the established `tests/test_*_stage*.py` conventions
(`test_sweep_ranking.py`, `test_composition_search_stage2.py`,
`test_common_observables_stage3.py`, `test_composition_analysis_stage4.py`,
`test_composition_discovery_cli_stage5.py`). Required checks (lettered like the
suite):

- **A** Per-composition sweep reuses `SweepRunner` (same variant ids, same order
  as `variant_mutation_sets()`) — no second sweep engine.
- **B** Baseline control is first, never mutated, and shares the Task 2.4
  composition baseline `run_id` (idempotent, no duplicate row).
- **C** Every variant `RunRecord` carries its `composition_id`; the baseline is
  the parent.
- **D** `cross_split_sweep_id` is deterministic (same inputs ⇒ same id) and
  contains no transient data; different space ⇒ different id.
- **E** Missing parameter space (`space=None`, e.g. A/B) is recorded explicitly
  and its baseline still enters the pool; nothing swept.
- **F** Missing common observable stays `available=False`/`None` in compositions
  that lack it; it never enters the cross-composition feature vector.
- **G** No fabrication: a same-named config path across two different
  components/variants is *not* treated as one dimension; explicit alias is
  required and tested.
- **H** Seed policy: same discovery seed for baselines; deterministic derived
  child seed where opted-in; reproducible across two passes.
- **I** Ordering is canonical/deterministic (catalog order, sorted vocabulary,
  right-most-fastest product within each sweep).
- **J** Combinatorial caps validated before any execution (per-composition and
  pass-level maxima reject eagerly).
- **K** Cross-composition `rank_compositions` + `select_frontier` over the
  variant+baseline pool produce a deterministic ranked/frontier view with
  `FrontierDiagnostics`.
- **L** Lineage store persists compact `SweepRecord` + `CrossCompositionSweepRecord`
  (+ `RunRecord`s) with no trajectories; re-run is idempotent.
- **M** A real end-to-end pass over the 3 EXECUTABLE compositions (C with a real
  small space; A/B as `space=None`) runs deterministically.
- **N** Core remains experiment-free (forbidden-token scan, like
  `test_sweep_ranking.py` FORBIDDEN_CORE_TOKENS for the new core module).

Fast suite for the first Build stages; the full end-to-end pass marked
`@pytest.mark.slow` if it approaches the ~14-minute canonical budget.

---

## 21. Purity (determinism / immutability / no side effects beyond lineage)

The new layer honours the project-wide purity contract verified throughout the
codebase:

- **No in-place mutation:** `apply_mutations` deep-clones; the baseline world and
  `WorldDefinition` objects are never edited (§9).
- **Determinism:** all ordering is canonical (catalog order, sorted names,
  documented product order); all identities are content-addressed;
  `run_id`/`sweep_id`/`cross_split_sweep_id` derive from stable inputs, never
  from runtime dict ordering, never from wall-clock except for *timing*
  instrumentation (§16, §17).
- **Side-effect policy:** the only writes are to the caller-provided
  `LineageStore` (compact records), exactly like every prior runner. The
  orchestrator takes `store` and the composition/executor maps as constructor
  deps; it owns no global state, no filesystem, no network.
- **No re-run on replay:** like `extract_common_observables`, the cross-composition
  view is a pure projection of already-recorded runs; a replayed pass re-runs
  sweeps only if asked to, and returns idempotent `run_id`s otherwise.
- **No hidden import of experiment concerns into core:** the core module knows
  only opaque composition→(executor, optional `MutationSpace`) maps and the
  `CommonObservableSet` surface.

---

## 22. Future search integration

Task 1.9 `SearchRunner` (guided beam search) is the natural future consumer of
this layer: its beam would range over *compositions as well as parameters* —
i.e. each step could mutate the composition binding (structural) *and/or* a
parameter within it, and the diversity term would use the cross-composition
behavioral distance this layer produces. Task 2.5 explicitly scopes that out;
it only establishes the per-composition sweep + cross-composition
rank/frontier substrate the future joint search would rest on. The identity
hierarchy (§7), the composition-aware lineage (§8), and the common-observable
vocabulary (§14) are designed to be reusable by that search without change,
matching how Task 1.9 reused Task 1.6/1.7/1.8 machinery.

---

## 23. Performance

- Runtime is the **sum** of per-composition sweeps, each `O(number of declared
  variants × one world execution)` — no product blow-up (§12, §13).
- Common-observable extraction and cross-composition ranking are pure, O(pool)
  projections over already-recorded runs (no re-execution), mirroring
  Task 2.4 Stage 3/4 timing (evaluation/extraction split).
- The Task 2.5 default is sequential and deterministic, matching every prior
  runner; there is **no threading/parallelism required for correctness**.
  Parallel execution, if ever added, must preserve the exact canonical
  execution order and identical `run_id`s.
- Lineage writes are local SQLite, compact metadata only; no trajectory
  storage cost.
- `CrossCompositionSweepTiming` reports per-composition and total
  evaluation/observation/extraction timing, with the recommended slow test
  excluded from the fast `-m "not slow"` suite.

---

## 24. Exact implementation sequence

1. **Stage 1 — binding + result model (smallest first Build task, §25).** Define
   the experiments-owned surface `repository_parameter_spaces()`
   (composition→`MutationSpace|None`) and the core
   `CrossCompositionSweepResult` / `CrossCompositionSweepRecord` /
   `cross_split_sweep_id` with the canonical `as_dict`, **no execution** yet.
   Add the `CouplingTemplate.parameter_space_ref` identifier (naming only).
   Unit-test identity determinism + `as_dict` round-trip (checks C/D/E/F).
2. **Stage 2 — orchestration over `SweepRunner`.** `CrossCompositionSweep`
   iterates EXECUTABLE compositions in catalog order, calls `SweepRunner.sweep`
   per composition (baseline-first, §9), records variants with `composition_id`
   threaded into the core recording path (§8), and handles `space=None`
   compositions (§11). Adds per-composition + pass-level caps (§13) and the
   seed policy (§16) with the from-`PARAMETER_SPECS` validator-binding for C.
   Tests A/B/G/H/I/J/M.
3. **Stage 3 — cross-composition view.** `CommonObservableSet`-style envelope per
   variant + genuinely-common vocabulary + `rank_compositions` +
   `select_frontier` + `FrontierDiagnostics` over the whole pool. Tests F/K/L.
4. **Stage 4 — CLI / figure (optional companion).** A thin
   `run_cross_sweep.py` joining the per-experiment spaces + the discovery
   catalog, mirroring `run_composition_discovery.py`, writing a
   `figures/cross_sweep_rank_diversity.png`. Test N + a `@pytest.mark.slow`
   end-to-end.

Each stage is independently testable and releasable; the Task 2.4 discovery CLI
(`run_composition_discovery.py`) is left **unchanged** (the Task 2.4 pipeline
stays as-is; Task 2.5 is additive).

---

## 25. Smallest first Build task (recommendation)

**Stage 1 — composition-specific mutation-space binding + result model.**

Concrete deliverables, all grounded in existing APIs:

- `experiments/catalog.py` gains a `repository_parameter_spaces()` function
  returning `Mapping[str, MutationSpace | None]` (currently: C → a small
  `MutationSpace` lifted from `PARAMETER_SPECS` value-validators + modest value
  lists; A/B → `None`). This mirrors `repository_executors()` exactly and stays
  experiment-owned.
- `templates.py` adds an optional `parameter_space_ref: str | None = None` on
  `CouplingTemplate` (identifier only; no experiment imports; backward-
  compatible default).
- A new `core/cross_sweep.py` defines `CrossCompositionSweepResult`,
  `CrossCompositionSweepRecord` (compact, persisted), and
  `cross_split_sweep_id` (deterministic 24-hex over the canonical catalog
  universe + ordered per-composition space dicts + profile + selection profile
  + seed). No execution in Stage 1.
- `tests/test_cross_sweep_stage1.py` proves: identity determinism + no transient
  data (C/D), `space=None` handling in the result model (E), no-fabrication of
  parameter equality at the model level (G), and the `as_dict` round-trip (L).

Stage 1 is chosen because it is the smallest change that locks down the
**contract** (ownership §5, identity §7, missing dims §11, result §17, purity
§21) before any execution, and it is the prerequisite every later stage builds
on. Execution (Stage 2+) follows naturally from it without reworking the
binding.

---

## Recommendation summary

- **Model:** D-hybrid, **per-composition local sweeps over the existing
  `SweepRunner`, orchestrated by a thin `CrossCompositionSweep`**, with an
  explicit, experiment-owned `repository_parameter_spaces()` map and an
  optional (naming-only) `parameter_space_ref` on `CouplingTemplate`.
- **Execution:** exact reuse of `SweepRunner` (baseline-first, validated-before-
  execution, Cartesian `MutationSpace`, deterministic `run_id`), plus the only
  genuinely-new bookkeeping: `composition_id` stamping on variant runs, the
  cross-composition common-observable pool, the cross-composition
  rank/frontier, and a content-addressed pass identity.
- **First Build:** Stage 1 (binding + result model, no execution).
- **A/B parameter spaces are declared later, opt-in, by the experiments — never
  fabricated by the core.**
