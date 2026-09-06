# TASK 1.6 REPORT — Generic Mutation and Experiment Lineage

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 1.6 (stdlib-only, deterministic, local)
**Subject experiment:** Experiment C — Adaptive Network Morphogenesis

---

## 1. Objective

Introduce the first *generic* mutation and lineage capability to the
Simulation Alchemist core:

- declarative **world mutations** (one or many) that never modify their parent,
- a deterministic, SQLite-backed **lineage** linking every variant run to its
  base run,
- a generic **variant runner** plus metric **comparison**, and
- a demonstration on Experiment C where an unmutated **base world** and a
  **single-mutation variant** are both executed through the shared composition
  core and their results compared and recorded.

No experiment-specific logic was added to `src/sim_alchemist/core/`; the
experiment contributes only parameter declarations and an executor, using the
generic vocabulary of the core.

---

## 2. IMPLEMENTED — mutation model

`src/sim_alchemist/core/mutation.py` — fully generic, zero experiment knowledge.

| Concept | Description |
|---|---|
| `Mutation` | `(path, new_value)` — pure serializable data (`to_dict`/`from_dict`/`from_record`). |
| `MutationRecord` | A mutation plus the `old_value` it replaced as actually applied (`display()` for the `a -> b` form, `to_dict`). |
| `apply_mutation` | Clone the world, navigate, type-check, validate, rebuild a new `WorldDefinition`; returns `(child_world, record)`. Never edits the parent. |
| `apply_mutations` | Apply a sequence left-to-right deterministically, returning the final child and ordered records. |
| `clone_world` | Deep, fully independent copy of a `WorldDefinition`. |
| `ParameterSpec` | Declared parameter metadata: path, description, `minimum`/`maximum` and/or `allowed`; produces a value validator. |
| `UnknownMutationPathError` | Unresolvable path; reports the path and the deepest valid prefix reached. |
| `InvalidMutationValueError` | Type/domain violation; reports path, expected constraint, and value. |

### Mutation path grammar

Only declarative data is reachable (no `eval`, no arbitrary code):

```
components.<component-id>.config.<key...>   # inside one component's config dict
config.<key...>                              # the world's shared config dict
seed | max_steps | macro_timestep            # top-level scalars
```

Structural fields (`schedule`, `requires`, component `id`, component set
membership) are **not** mutable: mutating structure would break the scheduler
and composer contracts.

### Value coercion

Exact type match is required, except lossless numeric widening `int -> float`
(`float -> int` is rejected as potentially lossy; booleans require exact
matches). The coerced value is what lands in the child world and in the
record's `new_value`.

### Validators

`ParameterSpec.validator()` returns either a `range_validator(lo, hi)` or
`one_of(*choices)`. `apply_mutation` runs the validator against the coerced
value before any simulation starts and converts `ValueError`/`TypeError`/`False`
into an `InvalidMutationValueError` naming the path.

---

## 3. IMPLEMENTED — world immutability model

Every mutation path starts by `copy.deepcopy`-ing the parent and rebuilds only
the containers on the mutated path. Recorded guarantees (tested by check B):

- the parent world's full `as_dict()` is byte-identical after any mutation;
- a clone shares no mutable objects with the parent (editing one never
  observably changes the other);
- re-running the same mutation sequence on the same parent always yields the
  same child world.

---

## 4. IMPLEMENTED — lineage model

`src/sim_alchemist/core/lineage.py`

- `world_hash(world)` — canonical SHA-256 over the sorted JSON of the world
  content.
- `run_id_of(world)` — deterministic 24-char id: SHA-256 over
  `<world_hash>|seed=<seed>`. Same world + same seed ⇒ same id on replay.
- `RunRecord` — immutable per-run metadata (run id, parent id, world snapshot,
  world hash, seed, ordered mutation records, compact metrics, created-at).
- `LineageStore` — thin, idempotent local SQLite store (`INSERT OR REPLACE` by
  `run_id`); table `runs` holds **metadata and compact metrics only** — never
  trajectories. Memory (`:memory:`) for tests, file path for persistence.
  Queries: `get_run`, `children_of`, `iter_runs`, `run_count`.

Determinism: replaying a recorded lineage converges on exactly one record per
node (record idempotence), so a repeated sweep never forks the tree.

---

## 5. IMPLEMENTED — VariantRunner

`src/sim_alchemist/core/runner.py`

- `ExecOutcome` — `(world, metrics, trajectory?)`; `trajectory` is opaque to
  the core and never persisted.
- `RunResult` — the runner's answer per executed world (run id, world,
  parent id, mutation records, metrics, seed).
- `MetricDelta` — per-metric `(name, base, variant)` with `.absolute` and
  `.relative` (relative is signed w.r.t. the base magnitude, `inf` for a
  non-zero change from an exact-zero base, `0.0` when unchanged).
- `compare_metrics` / `compare_runs` — turn two metric dicts (or two run
  results) into `{metric_name: MetricDelta}`. **Generic:** no metric is named
  or special-cased; non-numeric observables are skipped.
- `VariantRunner(store, executor, parameter_specs=None)`:
  - `run(base_world)` — execute + record the root run;
  - `run_variant(base_world, mutation | mutations)` — clone, validate against
    the declared specs, execute, and record the child linked to the base run.
    Raises `MissingParentRunError` if the base run was never recorded.
  - `run_variants(base_world, mutations)` — ordered batch, results in input
    order.

---

## 6. IMPLEMENTED — Experiment C integration

`experiments/network_morphogenesis/experiment.py`

- `PARAMETER_SPECS` — three *meaningful* existing parameters, declared in the
  generic vocabulary (path + bounds only):

| Path | Meaning | Range |
|---|---|---|
| `components.network.config.loss` | NDlib diffusion loss (`new_load = (1-loss)*mine + beta*avg`) — the *effective* value consumed by the network adapter | 0.0–1.0 |
| `config.force_fmax` | saturation bound of the wall force | 0.0–10.0 |
| `config.source_amplitude` | chemical source gain per unit network load | 0.0–1.0 |

- `build_network_metrics(trajectory)` — collapse a trajectory into the compact
  metric dict: `final_field_mean`, `final_field_std`, `field_entropy`,
  `wall_count`, `wall_movement`, `network_load_mean`, `network_load_max`,
  `n_sources`, `growth_edges`.
- `run_network_world(world) -> ExecOutcome` — the **executor**: rebuilds the
  adapters from the experiment registry, composes via the generic
  `compose_into` path (proven bitwise identical to the facade in Task 1.5),
  runs the engine, and returns compact metrics (+ trajectory for tests).
- `NetworkMorphogenesisConfig.from_world(world)` (added to `model.py`) —
  reconstructs the facade-equivalent config from a world snapshot; the
  inverse of `build_network_morphogenesis_world` for world-driven (incl.
  mutated) execution.

Known architectural wart (documented, not changed): `config.network_loss` is a
stale mirror shorthand that the coupling ops never read; the effective value is
`components.network.config.loss`. Only the canonical component-config path is
declared in `PARAMETER_SPECS`; mutating the mirror is behaviorally neutral.

---

## 7. IMPLEMENTED — baseline / variant / comparison / lineage walkthrough

Demonstration: `run_variant_demo.py` (project-convention `run_*.py` name).

```
$ python run_variant_demo.py --steps 160
```
```
Adaptive Network Morphogenesis mutation demo (160 macro-steps)

BASE (unmutated)
  field mean: 1.35138, field std: 1.99558, field entropy: 2.08949,
  walls: 159, wall movement: 419.425, network load: 1,
  network load max: 1, sources: 24, growth edges: 9

VARIANT
   components.network.config.loss 0.05 -> 0.14
  field mean: 1.56186, field std: 2.36954, field entropy: 2.10118,
  walls: 159, wall movement: 427.156, network load: 1,
  network load max: 1, sources: 24, growth edges: 6

DIFFERENCE
       field_entropy  +2.089492 -> +2.101183  (+0.011691)
    final_field_mean  +1.351379 -> +1.561858  (+0.210479)
    final_field_std   +1.995578 -> +2.369543  (+0.373965)
        growth_edges  +9.000000 -> +6.000000  (-3.000000)
        wall_movement +419.424679 -> +427.156173  (+7.731493)
        (wall_count, n_sources, network_load_* unchanged)

LINEAGE
Base
  6b6d70c8e903116534cb9b9a  (world 'adaptive_network', seed 0)
   +-- Variant-001  dea63e383409d9b548195812
       mutation: components.network.config.loss 0.05 -> 0.14
```

The selected mutation **does** produce a meaningful difference: higher loss
concentrates diffusion, so the adaptive network re-routes fewer distinct
corridors (growth edges 9 → 6), while wall motion and field variance increase
(field std +0.374, wall movement +7.7). Runs are recorded with real,
measured metrics; the numbers above are exact outputs, not estimates.

The fast 10-step form (`--steps 10`) is the developer-focused quick check and
prints the same structure (with walls growing past 9 and `network_load_mean`
dropping from 0.351 to 0.281 under the loss mutation).

---

## 8. IMPLEMENTED — deterministic replay

Proved by check F (and the existing A/B/C determinism/bitwise suites):

- same world + same seed + same mutation set  ⇒ same `run_id`, same metrics,
  and **bitwise-identical** final field (`sha256(final_u)` equal across two
  runs);
- lineage store converges on one record per node (idempotent `run_id`).

---

## 9. IMPLEMENTED — tests

`tests/test_mutation_lineage.py` — 26 tests, checks A–L.

| Check | Coverage |
|---|---|
| A | valid mutation → distinct child world, correct record (path/old/new) |
| B | parent never modified; clone deeply independent |
| C | invalid paths fail clearly with deepest-valid-prefix reporting |
| D | invalid type/domain fails clearly; `int→float` widening; validators |
| E | multiple mutations apply in order; batch ≡ sequential; deterministic |
| F | identical inputs ⇒ identical run_id / metrics / bitwise final field; store converges (run_count 2) |
| G | each meaningful mutation (loss/force/source) yields a meaningful metric delta |
| H | parent/child lineage recorded and linked; missing parent fails loudly |
| I | generic metric comparison (`compare_metrics` / `compare_runs`), delta math |
| J | Experiment C paths resolve, bounds reject out-of-domain values, runner mutates + records |
| K | Experiment A/B/C worlds mutate through the same generic engine |
| L | core mutation/lineage/runner sources contain **no** experiment identifiers |

---

## 10. IMPLEMENTED — repository hygiene changes

- `pyproject.toml`: added the missing runtime dependency **`ndlib==5.1.1`**
  (imported at runtime by `experiments/network_morphogenesis/adapter.py`),
  verified against the installed version; `uv lock` + `uv sync` regenerate a
  reproducible environment. Also added a minimal `[build-system]`
  (hatchling) and `[tool.hatch.build.targets.wheel]` so `uv sync` actually
  installs the project itself (previously the venv was only usable because of
  incidental state).
- Core immutability guard in `tests/test_field_guided_movers.py` was
  **re-baselined** (the sanctioned Task 1.3-style extension) to cover the
  three new core files (`mutation.py`, `lineage.py`, `runner.py`) and the
  updated `__init__.py`. The guard is intentionally kept: it pins the
  post-Task-1.6 core against future drift.

---

## 11. File tree (new / changed)

```
src/sim_alchemist/core/
    mutation.py          NEW  generic mutation engine
    lineage.py           NEW  SQLite-backed lineage store
    runner.py            NEW  VariantRunner + metric comparison
    __init__.py          MOD  re-exports the new API
experiments/network_morphogenesis/
    experiment.py        NEW  PARAMETER_SPECS + metrics + executor
    model.py             MOD  NetworkMorphogenesisConfig.from_world
tests/
    test_mutation_lineage.py  NEW  26 tests (checks A–L)
    test_field_guided_movers.py MOD  core guard re-baselined
    test_network_morphogenesis.py MOD  guard message updated
run_variant_demo.py      NEW  baseline/variant/lineage demonstration
pyproject.toml           MOD  ndlib dependency + build-system
uv.lock                  MOD  regenerated (57 packages, ndlib + transitives)
```

---

## 12. PLANNED (NOT implemented)

The following remain **future work** and were NOT built in Task 1.6 — in
particular, **no sweep/search/ranking exists yet**:

- mutation *spaces* and deterministic variant *sweeps* (Task 1.7);
- generic result *ranking* / "interestingness" (post-1.7);
- evolutionary / Bayesian / AI-driven discovery;
- automatic engine selection; plugin marketplace; distributed execution.

The runner's `run_variants` executes an explicit, pre-built list of variants —
it is batch execution, **not** combinatorial generation.

---

## 13. Architectural weaknesses / remaining limitations

- The `config.network_loss` mirror path is behaviorally neutral (documented
  above); only canonical component-config paths are declared.
- `ndlib` had been missing from `pyproject.toml` (a pre-existing Task 1.5
  packaging gap); now declared and locked by this task.
- Lineage persists metadata/metrics; trajectories never enter SQLite.
- `MutationRecord.new_value` stores the *coerced* (possibly widened) value, so
  `int → float` mutations record the float.
- Determinism is same-runtime/same-environment; it is not universal
  cross-platform bitwise equivalence (inherited from Task 0.3/1.2/1.3/1.5).
- Parameter bounds are hand-tuned for the validated runs.

---

## 14. Validation results

Rerun as part of the closing gate (identical commands as the project baseline):

- `pytest` — full suite (incl. slow cannonicals) PASSES; 26 Task 1.6 tests
  included; no previous tests weakened.
- `run_validation.py` — A–G PASSES.
- `run_stability.py` — S1–S6 PASSES.
- `ruff check .` — CLEAN.
- `pyright` (full repo) — 0 errors.
- `uv sync` / `uv lock` — reproducible; environment builds from lock.

---

## 15. What Task 1.7 will build

Deterministic variant **sweeps** + generic experiment **ranking**: mutation
spaces (one- and multi-dimensional Cartesian products with a documented,
deterministic ordering), batch execution with stable variant identities, the
base run always included as a control, generic metric collection and ranking,
and sweep metadata recorded into the existing Task 1.6 lineage store. No
search/optimization/AI. The material from this report
(consistent run ids, idempotent lineage, generic metric comparison) is reused
directly.