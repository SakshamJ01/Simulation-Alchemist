# TASK 2.4 STAGE 1 REPORT — Cross-Composition Discovery: Result Layer + Composition Lineage

**Status:** COMPLETE (Build Stage 1 only)
**Date:** 2026-09-08
**Milestone:** Task 2.4 Build Stage 1 (per `TASK_2.4_DESIGN.md` §19)
**Scope:** new generic `src/sim_alchemist/core/composition_search.py` (composition
evaluation result + deterministic discovery identity + baseline evaluation), the
additive `composition_id` lineage stamp on `RunRecord`/`runs` with migration, and
two new experiment-side conforming executors (`chemomech/experiment.py`,
`experiments/field_guided_movers/experiment.py`) plus the experiments-owned
`repository_executors()` composition→executor map. **Stage 2 (`CompositionSearcher`
orchestrator) was not implemented.** No cross-composition pool, no `rank_by_profile`
/`select_diverse_frontier` application, no A/B observables builders, no discovery CLI,
no visualization, no new dependencies, no new experiment.

---

## 1. Objective

The design (`TASK_2.4_DESIGN.md`) mandates a staged delivery whose first Build is
*"result/identity/lineage + baseline scaffolding"* (§19): before any orchestrator can
rank compositions, the **identity of a discovery pass** and the **identity of one
evaluated composition baseline** — plus the **lineage stamp that links a recorded run
to its composition** — must exist and be deterministic. Stage 1 delivers exactly that
slice:

- a `CompositionEvaluation` record — one immutable, compact snapshot of a composition
  baseline (composition + shape + deterministic lineage keys + status + seed + metrics);
- `composition_discovery_id_of` — deterministic content-addressed identity of a
  discovery pass from the catalog universe + guiding profile + seed + evaluation config;
- `evaluate_composition_baseline` — runs one **EXECUTABLE** candidate's generated world
  through a caller-supplied experiment executor and records the baseline as a **root
  lineage run** (`parent_run_id=None`) with its composition stamp;
- additive, backwards-compatible `RunRecord.composition_id` (nullable column + `_migrate`)
  so the existing `LineageStore` carries composition provenance without a second DB;
- the two missing conforming executors (A and B) that make all three repository
  compositions evaluable through the same generic `Executor` path, keyed by
  `composition_id` via `experiments/catalog.py::repository_executors()`.

No search concept is introduced and nothing in `core/` dispatches on template name or
composition (validated by the forbidden-token purity scan in the tests).

## 2. Deliverables

### 2.1 `src/sim_alchemist/core/composition_search.py` (new, generic core)

- `CompositionEvaluation` — frozen dataclass (`composition_id`, `shape_id`,
  `world_hash`, `run_id`, `world_id`, `status`, `seed`, `metrics`), `as_dict()`, and
  `from_run_record(record, *, shape_id, status=EXECUTABLE)`. It reuses `run_id_of` /
  `world_hash`; it never duplicates `RunRecord`.
- `CompositionEvaluationError(ValueError)` — raised when a non-**EXECUTABLE** candidate
  or a candidate without a generated world is asked to be evaluated.
- `composition_discovery_id_of(catalog, profile, *, seed=0, evaluation_config=None)`
  — content-addressed 24-hex `sha256` over the catalog's composition universe (space
  name, ordered bindings, registered template names, executable composition ids), the
  profile `as_dict()`, seed, and evaluation config. No transient runtime data; the same
  inputs give the same id.
- `evaluate_composition_baseline(store, executor, candidate)` — EXECUTABLE-only,
  `generated_world`-required, records a root `RunRecord` (`run_id_of(world)`,
  `parent_run_id=None`, `composition_id=candidate.composition_id`) via the existing
  `LineageStore.record_run` (idempotent on the deterministic run id) and returns the
  `CompositionEvaluation` snapshot.

`__init__.py` re-exports all four names (+ `__all__`).

### 2.2 `src/sim_alchemist/core/lineage.py` (additive change)

- `RunRecord.composition_id: str | None = None` in `__slots__` / `__init__` / `as_dict`.
- `runs` CREATE TABLE gains nullable `composition_id TEXT`.
- `_migrate()` now `ALTER TABLE runs ADD COLUMN composition_id TEXT` for pre-2.4 stores
  (idempotent, next to the existing `feature_snapshot` migration) and rewrites
  `RunRecord` defaults so legacy rows load as `None`.
- `record_run` INSERT includes the composition stamp.

Lineage semantics stay exactly as designed (§8): a composition change is a **new root**
(`parent_run_id=None`), a parameter mutation is a **child** (`parent_run_id` set, same
composition). Stage 1 only records composition roots; the parameter-child distinction is
unchanged existing behavior (Task 1.6).

### 2.3 Experiment executors (experiment-side, conforming `Executor`)

- `chemomech/experiment.py` (new): `build_morphogenesis_metrics`, `run_morphogenesis_world`,
  plus `_total_wall_movement` / `_field_entropy` helpers. `run_morphogenesis_world`
  mirrors the facade (`_run_generated_a`): `WorldConfig(**dict(world.config))`,
  `compose_into` with `on_initialize`, `MORPHOGENESIS_CONTRACTS`.
- `experiments/field_guided_movers/experiment.py` (new): `build_movers_metrics`,
  `run_field_guided_movers_world` (mirrors `_run_generated_b`: `MoversConfig(**dict(
  world.config))`, `_ops()`/`_initialize()`/`_on_step` event publish,
  `FIELD_GUIDED_MOVERS_CONTRACTS`).
- Experiment C already conformed (`experiments/network_morphogenesis/experiment.py`).
- `experiments/catalog.py`: `repository_executors() -> dict[str, Executor]` keyed by
  `template_composition_id(build_*_template())` — the "experiments-owned map keyed by
  composition_id" the design mandates (§10); core never dispatches on composition.

### 2.4 Fast catalog trick

`composition_id` is derived from shape/contracts/schedule/requires/macro_timestep —
**not** max_steps/config — so a fast test catalog (templates rebuilt with
`max_steps=2, config={**dict(template.config), "n_steps": 2}`) retains the canonical
executable composition ids. Every fast evaluation test exercises the **real** repo
universe, templates, executors, and ids at a 2-step budget.

## 3. Verification

- `tests/test_composition_search.py` (new, 26 tests: 24 fast + 2 slow):
  - discovery identity (content-addressed, deterministic, universe/profile/config-sensitive);
  - `CompositionEvaluation` result model (`as_dict` round-trip, `from_run_record`);
  - additive lineage — `runs` schema carries `composition_id`; **pre-2.4** store migrates
    (including a legacy `runs` table built without the column) and loads as `None`;
    re-record is idempotent;
  - EXECUTABLE evaluation — the 3 repository compositions evaluate through
    `repository_executors()` on the fast catalog; non-executables **never** simulated
    (the refusing call is asserted, and an executor is passed that would blow up if
    reached); no-world candidates refused;
  - `repository_executors()` keyed by the canonical composition ids;
  - core purity — `composition_search.py` is free of experiment tokens
    (`ndlib/mesa/pymunk/chemomech/morphogen/network/adapt`);
  - **slow** canonical metric parity: for A and B, `run_*_world(generate_world(
    template()))` produces `ExecOutcome.metrics` **bitwise equal** to the facade
    metric builders at the full 160-macro-step horizon.
- Full suite: **386 passed** (378 fast + 8 slow), including the re-pinned core-guard
  tests (Task 2.3/2.4 sanctioned re-baseline), `run_validation.py` A–G PASS,
  `run_stability.py` S1–S6 PASS.
- `ruff check .` clean; `pyright` 0 errors.

## 4. Deliberate design deviations (documented, smallest-first)

1. **No `composition_discoveries` table / `CompositionDiscoveryRecord` yet.** The design
   (§19) listed it; its content (profile, ranking, frontier, timing) is meaningful only
   with the Stage 2 orchestrator and the pool/rank/frontier. Stage 1's persistence
   requirement — record one baseline run per EXECUTABLE composition with its
   composition_id — is fully satisfied by the `runs` table carrying the composition
   stamp. The table will be added in the stage that actually produces its rows.
2. **Single `CompositionEvaluation` instead of the drafter dataclasses.**
   `CompositionCandidateResult` / `CompositionEvaluationResult` were placeholder shapes
   to be superseded by Stage 2's `CompositionDiscoveryResult`; one clean immutable
   evaluation record does the same job (identity + lineage keys + metrics) with no
   throwaway scaffolding.
3. **`composition_discovery_id_of` takes the catalog, not a precomputed `catalog_id`.**
   Its payload is the catalog's *identity components* (space name, ordered bindings,
   template names, executable composition ids) rather than an opaque string — same
   content-addressed determinism, no fragile id plumbing.
4. **Metrics-only baselines this stage.** No observables builders exist for A/B
   (design §19 forbids adding them in Stage 1), so `evaluate_composition_baseline`
   records metrics only. The `feature_snapshot`-when-observables-exists wiring arrives
   with Stage 3's `build_*_observables`; common-schema comparison is explicitly out of
   scope.

## 5. Files touched

| File | Change |
|------|--------|
| `src/sim_alchemist/core/composition_search.py` | **new** — Stage 1 result/identity/baseline-evaluation module |
| `src/sim_alchemist/core/lineage.py` | +`composition_id` column / `RunRecord` / `_migrate` / `record_run` |
| `src/sim_alchemist/core/__init__.py` | re-exports the new API |
| `chemomech/experiment.py` | **new** — A executor + metrics |
| `experiments/field_guided_movers/experiment.py` | **new** — B executor + metrics |
| `experiments/catalog.py` | +`repository_executors()`, docstring/imports |
| `tests/test_composition_search.py` | **new** — Stage 1 suite (24 fast + 2 slow) |
| `tests/test_field_guided_movers.py` | core-guard hashes re-pinned (sanctioned extension) |
| `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` | status tracking |

## 6. Scientific limitations (preserved)

Identical to Task 2.3 §16 + the design §16: PDE approximation, simplified walls,
custom network transport, non-equilibrium claims, and all three experiments' native
limitations remain in force. Metric-parity between executors and facades is a
*reproducibility* guarantee (same paths, bitwise), not a *scientific* endorsement of
the quantities. Cross-composition comparison is explicitly not performed in Stage 1.

## 7. Next exact task

Task 2.4 Build Stage 2 — the thin `CompositionSearcher` orchestrator (enumerate
EXECUTABLE → generate → run per-composition baseline → build the cross-composition
pool → delegate to `rank_by_profile` / `select_diverse_frontier`). Not started.