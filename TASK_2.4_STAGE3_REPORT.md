# TASK 2.4 STAGE 3 REPORT — Common Cross-Composition Observables

**Status:** COMPLETE (Build Stage 3 only)
**Date:** 2026-09-09
**Milestone:** Task 2.4 Build Stage 3 (per `TASK_2.4_DESIGN.md` §19)
**Scope:** the deterministic common-observable envelope that sits *after*
baseline evaluation and *before* any cross-composition ranking/frontier: a new
generic `src/sim_alchemist/core/observables.py` plus a Stage 3 chapter in
`src/sim_alchemist/core/composition_search.py` (`search` attaches one
`CommonObservableSet` per evaluated composition in catalog order and splits
wall-clock into evaluation vs extraction). **Stage 4 (cross-composition ranking
/ discovery frontier), Stage 5 (visualization), and Task 2.5 were NOT
implemented.** No new dependencies, no `rank_by_profile` /
`select_diverse_frontier` / behavior-feature call, no frontier selection, no
visualization, no commit made.

---

## 1. Objective

Stage 2 proved a full discovery pass produces a compact *unranked* result. Stage 3
is the smallest deterministic layer that makes evaluated compositions comparable
across experiments, again without ranking:

- compute the deterministic **common observable vocabulary** for a pool of
  evaluated compositions — the sorted union of the executors' scalar metric
  names (no human curation, no aliases);
- project each evaluated baseline onto that vocabulary: composition-specific
  names from other experiments become **explicit missing rows**
  (`available=False`, `value=None`) — nothing is imputed, interpolated,
  synthesized, or fabricated;
- capture the **horizon** (`max_steps`, `macro_timestep`) that produced each
  evaluation, taken from the generated world under id/hash-match validation;
- keep extraction **pure and O(n)**: it reuses the in-memory evaluations from the
  pass — **no re-run, no persistence, world immutable**;
- keep everything **deterministic and replay-identical** (canonical serialization
  stays wall-clock-free, so timing never leaks into the deterministic form).

## 2. Deliverables

### 2.1 `src/sim_alchemist/core/observables.py` (new, generic core)

- `CommonObservable` — frozen `name` / `value: float | None` / `available`
  triple. `__post_init__` enforces: non-empty name, `available ⇔ value is not
  None`, and a numeric `value` kept **verbatim** as a float (no premature
  rounding).
- `CommonObservableSet` — frozen per-composition snapshot:
  `composition_id`, `shape_id`, `world_hash`, `run_id`, `world_id`, `status`,
  `seed`, `max_steps: int | None`, `macro_timestep: float | None`, and the
  `observables` tuple **sorted by name** with unique names (post-init repairs so
  `as_dict()` round-trips through `as_dict()`). Helpers: `names`,
  `available_names`, `missing_names`, `observable(name)`, `as_dict()`. Dict rows
  are coerced via `CommonObservable(**dict(row))` so the serialized form
  round-trips verbatim.
- `CommonObservableError(ValueError)` — element/type errors with clear
  messages (e.g. world id/hash mismatch during horizon capture).
- `common_observable_names(evaluations)` — deterministic **sorted union** of the
  metric names across a pool of evaluations; empty pool → `()`.
- `extract_common_observables(evaluation, common_names, *, world=None)` — pure
  projection: metric values taken verbatim from the recorded evaluation; names in
  the common vocabulary that the composition does not produce become explicit
  `available=False` / `value=None` rows. `world` is optional — without it the
  horizon is `max_steps=None` / `macro_timestep=None` (explicit "insufficient
  data", never a guess). When given, the world must match the evaluation's
  `world_id` and `world_hash` exactly or `CommonObservableError` is raised.
  Structural violations of the evaluation shape / non-numeric metrics raise
  `TypeError`; this module never silently swallows a malformed input. It imports
  nothing persistent and never invokes an engine.

### 2.2 `src/sim_alchemist/core/composition_search.py` (Stage 3 chapter)

- `CompositionSearchTiming` is now six non-default fields:
  `n_executable`, `n_evaluated`, `evaluation_seconds`, `observation_seconds`,
  `total_seconds`, `mean_seconds`. Construction happens only inside
  `search()`, so the field change is contract-safe.
- `search()` computes the vocabulary once, then builds one `CommonObservableSet`
  per evaluated composition (in catalog order) using the in-memory evaluations
  and each candidate's generated world. Wall time is split: `evaluation_seconds`
  (the evaluation loop) vs `observation_seconds` (vocabulary + extraction, O(n)
  and ~4 orders of magnitude smaller) vs `total_seconds` (the whole pass, so
  `total ≈ evaluation + observation` on a quiet machine).
- `CompositionSearchResult` gains a trailing `observable_sets` tuple (default
  `()`, so Stage 2 constructions stay valid) plus `observable_set(composition_id)`;
  `as_dict(canonical=True)` embeds the observable sets and remains fully timing-
  free, so deterministic replay comparison continues to work unchanged.
- `__init__.py` re-exports `CommonObservable`, `CommonObservableSet`,
  `CommonObservableError`, `common_observable_names`,
  `extract_common_observables` and updates `__all__`; core guard re-pinned
  (sanctioned extension, Task 2.4 Stage 3 comment added to the re-pin history).

## 3. The vocabulary (real, exact)

Sorted union across the three evaluated compositions — **16 names**:

```
dissolved_total, field_entropy, final_field_mean, final_field_std, growth_edges,
mean_force, mean_gradient, mean_speed, mean_wall_speed, n_movers, n_sources,
network_load_max, network_load_mean, total_displacement, wall_count, wall_movement
```

Genuinely common across all three compositions (every one of A/B/C produces
them): `final_field_mean`, `final_field_std`, `field_entropy`. Every other name
is `available=False`/`value=None` for the compositions that do not produce it —
proven by the test suite, not assumed.

## 4. Execution flow (A/B/C)

One canonical full-horizon search over the repository catalog (`generate_worlds=True`),
measured on this machine (Windows, Python 3.13, uv):

- EXECUTABLE compositions: **3** (invalid: 20; unchanged regression)
- Evaluations performed: **3** (one baseline per composition, roots in lineage)
- Evaluation wall time: **41.539 s**; extraction wall time: **0.000231 s**;
  total: **41.539 s**; mean per evaluation: **13.846 s**
- Observatory: **3** `CommonObservableSet`s in catalog order, horizons captured
  from the generated worlds (`max_steps=160`, `macro_timestep=0.2`)
- Replay: a second identical `search` over the **same** store leaves
  `store.run_count == 3` and produces a **bitwise-identical canonical** result.

## 5. Verification

- `tests/test_common_observables_stage3.py` (new, **31 tests: 30 fast + 1 slow**):
  - extraction is pure / identical to the recorded evaluation values; missing
    names are explicit and `available`/`value` are consistent;
  - **vocabulary determinism** — sorted, deduplicated, and provably the union;
    empty pool → empty vocabulary; malformed pools → `TypeError`;
  - horizon captured from the generated worlds and validated (`id`/`hash`
    mismatch → `CommonObservableError`); absent world → `None` horizon (never a
    guess);
  - **determinism & canonical stability** — identical searches (same store, fresh
    store, sub-second-order structural randomization of dict order) produce
    bitwise-identical canonical results; `run_id`/`world_hash` constant;
  - **lineage preserved** — root runs per composition, `run_count == 3`, no
    detached records; idempotent replay;
  - **one set per evaluated composition** in catalog order; composition-specific
    names are missing exactly where expected;
  - generated worlds are **never mutated** by extraction;
  - **no-overreach** — the observables module carries no ranking/score/frontier/
    behavior identifiers, no experiment tokens, no visualization tokens (scans
    over both changed sources); no persistence, no engine invocation;
  - **Stage 2 compatibility** — the existing Stage 2 result contract is intact;
  - timing split: evaluation ≈ total, extraction on the order of 1e-4 s;
  - **slow** canonical full-horizon search `max_steps == 160`,
    `macro_timestep == 0.2`, exactly 3 evaluations, `run_count == 3`, replay
    canonical-identical.
- Full suite: **444 passed** (434 fast + 10 slow), including the Stage 1/2
  suites and the re-pinned core-guard tests.
- `run_validation.py` A–G PASS; `run_stability.py` S1–S6 PASS.
- `ruff check .` clean; `pyright` 0 errors.

## 6. Deliberate design decisions (documented, smallest-first)

1. **Vocabulary = sorted union, nothing else.** No semantic aliases, no custom
   mapping table. "Common" is defined operationally as "produced by the same
   scalar metric name across executors"; everything else is an explicit missing
   row. A genuinely-common subspace of 3 names exists without curation.
2. **Horizon captured from the generated world, `None` when absent.** The
   extraction signature takes the world (already validated as the evaluation's
   world by id/hash) so the per-composition observability window is recorded
   with an input the pass already holds — a separate re-run would violate the
   no-rerun rule.
3. **`available=False`/`value=None`, never imputation.** Compositions are not
   made to look comparable; the envelope records exactly what each composition
   produced.
4. **Pure extraction module with no state.** `observables.py` imports nothing
   from the engines and never touches a store; the orchestrator owns the
   reconciliation and the timing.
5. **Timing split lives on the immutable result, never in the canonical form.**
   Deterministic replay comparison keeps using `as_dict(canonical=True)`;
   wall-clock only appears in the instrumentation view.
6. **Backward-compatible result/timing.** `observable_sets` is a trailing
   defaulted field and the timing fields are only constructed inside `search()`,
   so every existing Stage 2 call site and test is untouched.

## 7. Files touched

| File | Change |
|------|--------|
| `src/sim_alchemist/core/observables.py` | **new** — Stage 3 common-observables module |
| `src/sim_alchemist/core/composition_search.py` | + Stage 3 chapter (`observable_sets`, extraction, timing split) |
| `src/sim_alchemist/core/__init__.py` | re-exports the new API |
| `tests/test_common_observables_stage3.py` | **new** — Stage 3 suite (30 fast + 1 slow) |
| `tests/test_field_guided_movers.py` | core-guard hashes re-pinned + `observables.py` added (sanctioned extension) |
| `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` | status tracking |

No changes to lineage, catalog, templates, the experiment executors, or the
facade paths.

## 8. Confirmed NOT implemented (Stage 4+)

- Stage 4 — cross-composition ranking / discovery frontier over the common
  observable layer (`rank_by_profile` / `select_diverse_frontier` application
  to the Stage 3 envelope; the design's frontier choreography).
- Stage 5 — discovery visualization / demo CLI.
- Task 2.5 and any new experiment / new dependency / parallel execution.

## 9. Next exact task

Task 2.4 Build Stage 4 — cross-composition ranking / discovery frontier over the
common-observable layer (per `TASK_2.4_DESIGN.md` §18). Not started; do not start
until issued.