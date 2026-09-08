# TASK 2.4 STAGE 2 REPORT — Cross-Composition Discovery: `CompositionSearcher` Orchestrator

**Status:** COMPLETE (Build Stage 2 only)
**Date:** 2026-09-09
**Milestone:** Task 2.4 Build Stage 2 (per `TASK_2.4_DESIGN.md` §19)
**Scope:** the thin `CompositionSearcher` orchestrator appended to
`src/sim_alchemist/core/composition_search.py` on top of the Stage 1 result layer
(enumerate `catalog.executable()` → resolve experiment-owned executors → evaluate
one baseline per EXECUTABLE composition via `evaluate_composition_baseline` →
return a compact ranked-free `CompositionSearchResult`). **Stage 3 (common
cross-composition observables), Stage 4 (ranking/frontier), Stage 5
(visualization), and Task 2.5 were NOT implemented.** No new dependencies, no
`rank_by_profile`/`select_diverse_frontier` call, no behavior analysis, no
discovery CLI, no commit made.

---

## 1. Objective

Stage 1 delivered the identity + baseline-evaluation result layer. Stage 2 is the
"thinnest possible" orchestrator that proves a discovery pass over the whole
repository composition universe works end-to-end through the generic core:

- enumerate the catalog's **EXECUTABLE** compositions in canonical catalog order;
- resolve each composition to its experiment-owned `Executor` through an **opaque
  composition_id → executor map** (core never dispatches on composition);
- evaluate each baseline exactly once through the Stage 1 result layer, recording
  a root lineage run per composition (idempotent on the deterministic run id);
- preserve the deterministic discovery-pass identity
  (`composition_discovery_id_of`);
- return a compact in-memory `CompositionSearchResult` — **not ranked**, not
  summarized, no behavioral features, no frontier selection (those are Stage 3+).

## 2. Deliverables (all in `src/sim_alchemist/core/composition_search.py`)

- `CompositionSearchError(ValueError)` — raised when the caller-supplied executor
  map has no entry for an EXECUTABLE composition (message includes the 24-hex
  composition id).
- `CompositionSearchSpec` — frozen, validated config (like `SearchSpec`):
  `profile` (any object exposing `as_dict()` and non-empty `weights`, so the
  framework's profile object satisfies it by duck type), `seed: int = 0`,
  `evaluation_config: Mapping | None = None` (copied in `__post_init__`);
  `as_dict()`. Invalid seed / missing `as_dict` / non-mapping
  `evaluation_config` raise `TypeError`.
- `CompositionSearchTiming` — frozen instrumentation
  (`n_executable`, `n_evaluated`, `total_seconds`, `mean_seconds`) with
  `as_dict()`; the slow test asserts `n_executable == n_evaluated == 3` and
  positive timing. Excluded from the canonical result form.
- `CompositionSearcher(catalog, executors, store)` — constructor-only (no
  simulation at construction); `search(spec, *, discovery_id=None)` defaults the
  pass identity to `composition_discovery_id_of(...)` and evaluates only
  `catalog.executable()` candidates in catalog order, requiring each candidate's
  `generated_world`. Never mutates the `WorldDefinition`; exact two-pass
  deterministic replay of the same search produces bitwise-identical canonical
  results and does **not** duplicate logical runs.
- `CompositionSearchResult` — frozen outcome holding `discovery_id`, `spec`,
  the ordered `evaluations` tuple, and `timing`; helper `composition_ids` and
  `evaluation(composition_id)`; `as_dict(*, canonical=False)` (canonical form
  carries only deterministic identity + evaluations, no timing).
- `__init__.py` re-exports all five names (+ `__all__`); core guard re-pinned
  (sanctioned extension, Task 2.4 Stage 2 comment added to the re-pin history).

## 3. Execution flow (A/B/C)

The one search over the canonical repository catalog evaluates the three
EXECUTABLE compositions — A (chemo-morphogenesis), B (field-guided movers),
C (adaptive network morphogenesis) — sequentially in catalog order through
`experiments/catalog.py::repository_executors()`, each for 160 macro steps at
default config. Measured on this machine (Windows, Python 3.13, uv):

- EXECUTABLE compositions: **3** (invalid: 20; the 23-shape universe)
- Evaluations performed: **3** (one baseline per composition, roots in lineage)
- Total wall time: **56.05 s**; mean per evaluation: **18.68 s**
- Replay: a second identical `search` over the **same** store leaves
  `store.run_count == 3` (evaluations are idempotent on the deterministic
  `run_id_of(world)`); a fresh store produces bitwise-identical canonical results.

## 4. Verification

- `tests/test_composition_search_stage2.py` (new, 26 tests: 25 fast + 1 slow):
  - spec validation (seed/config/profile guards);
  - **empty** catalog: `build_repository_catalog` space with `min_size=max_size=4`
    yields **0 executables**, a clean zero-evaluation result (zero-division-safe);
  - **single-executable** catalog (B-only universe) — one evaluation, one root;
  - **three-executable** catalog via the fast `max_steps=2` trick —
    exact `composition_ids`, 3 root runs;
  - invalid candidates are **never** simulated (counting executors observe only
    the 3 executable world ids);
  - each executor is invoked exactly once per search (call counters);
  - ordering matches catalog executable order exactly;
  - discovery identity: deterministic, equals `composition_discovery_id_of`,
    and — via the fast-catalog trick — **budget-independent** from the canonical
    catalog, seed-sensitive, evaluation-config-sensitive, profile-sensitive;
  - deterministic replay: same store + fresh store, canonical forms equal,
    `run_count == 3` after replay;
  - clear errors: unknown executor composition → `CompositionSearchError`
    naming the id; `build_repository_catalog()` without `generate_worlds=True`
    → `CompositionEvaluationError`; spec violations → `TypeError`;
  - evaluated snapshot fields match the candidate + stored `RunRecord`;
  - no-overreach: result model exposes no `final_ranking`/score/rank; the source
    is scanned for ranking/analysis identifiers and experiment tokens
    (`ndlib/mesa/pymunk/chemomech/morphogen/network/adapt` plus
    `pde/movers/field_guided/chemistry/agent_`) with **zero** hits;
  - **slow** canonical full-horizon search + in-place replay (3 baselines × 2).
- Full suite: **412 passed** (403 fast + 9 slow), including the re-pinned
  core-guard tests and the Stage 1 suite unchanged.
- `run_validation.py` A–G PASS; `run_stability.py` S1–S6 PASS.
- `ruff check .` clean; `pyright` 0 errors.

## 5. Deliberate design decisions (documented, smallest-first)

1. **No `composition_discoveries` persistence table yet.** Stage 1 deferred it
   ("meaningful only with the orchestrator"); Stage 2 keeps the same discipline —
   discovery-pass metadata like timing/frontier belongs to the stage that
   produces ranking/frontier content. Lineage persistence stays exactly as
   Stage 1: one root `RunRecord` per composition in `runs`.
2. **`CompositionSearchSpec.profile` is duck-typed (any `as_dict()` object), not
   bound to the behavior module.** The core module must stay behavior-free
   (forbidden-token + purity scans); reuse of the framework's profile object is
   achieved at the *call site* with zero core dependency, exactly like Stage 1.
3. **Timing lives on the immutable result but never in the canonical form.**
   Deterministic replay comparison uses `as_dict(canonical=True)`; wall-clock
   only appears in the non-canonical/instrumentation view.
4. **The orchestrator evaluates only consumers of Stage 1's evaluator.** No metric
   merging, no observables, no normalization is introduced — staged squarely for
   Stage 3.

## 6. Files touched

| File | Change |
|------|--------|
| `src/sim_alchemist/core/composition_search.py` | + `CompositionSearchSpec/Searcher/Result/Timing/Error` (Stage 2 chapter) |
| `src/sim_alchemist/core/__init__.py` | re-exports the new API |
| `tests/test_composition_search_stage2.py` | **new** — Stage 2 suite (25 fast + 1 slow) |
| `tests/test_field_guided_movers.py` | core-guard hashes re-pinned (sanctioned extension) |
| `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` | status tracking |

No changes to lineage, catalog, templates, the experiment executores, or the
facade paths.

## 7. Confirmed NOT implemented (Stage 3+)

- Stage 3 — common cross-composition observables / A/B/C `build_*_observables` /
  behavior schema / `BehavioralAnalysisRunner` integration.
- Stage 4 — `rank_by_profile` / `select_diverse_frontier` application to the
  evaluated pool (the design's frontier/ranking choreography).
- Stage 5 — discovery visualization / demo CLI.
- Task 2.5 and any new experiment / new dependency / parallel execution.

## 8. Next exact task

Task 2.4 Build Stage 3 — common cross-composition observables (A/B observable
builders, shared behavior schema, behavioral characterization of composition
baselines). Not started.