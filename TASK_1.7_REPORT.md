# TASK 1.7 REPORT — Deterministic Variant Sweeps + Generic Experiment Ranking

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 1.7 (stdlib-only, deterministic, local, sequential)
**Subject experiment:** Experiment C — Adaptive Network Morphogenesis

---

## 1. Objective

Turn Task 1.6's *singular* mutation + lineage into the generic batch layer:

- a **mutation space** (one- and multi-dimensional Cartesian products of
  per-parameter value lists) with a **documented, deterministic ordering**;
- deterministic **variant identity** (variant `run_id` is a pure function of
  the mutated world + seed);
- a **sequential sweep runner** that always includes the **baseline as a
  control** (recorded first, never mutated in place), validates the whole
  space before any simulation starts, and records every run — plus compact
  **sweep metadata** — into the same SQLite lineage store;
- **generic experiment ranking**: pick a metric, choose a direction,
  get a deterministic ranking (ties broken by run id);
- a small real **Experiment C sweep** (declared space → executed variants) and
  a repeatability/reproducibility proof.

Constraints honoured: sequential execution only (no multiprocessing/distributed),
no search/optimization/AI, core stays fully experiment-free, metrics are raw
(no normalization), trajectories never touch the DB.

---

## 2. IMPLEMENTED — mutation space model

`src/sim_alchemist/core/sweep.py` — fully generic, zero experiment knowledge.

| Concept | Description |
|---|---|
| `ParameterSweep(path, values)` | one sweep dimension: mutate `path` through an **ordered** value list; `mutations()` yields the per-value `Mutation`s. |
| `MutationSpace(dimensions)` | Cartesian product of one or more `ParameterSweep`s. |
| `MutationSpace.variant_mutation_sets()` | every variant's mutation tuple, in **documented deterministic product order** (left-most dimension slowest, right-most fastest): |
| `MutationSpace.variant_count` | product of the dimension lengths. |

### Documented Cartesian ordering

`itertools.product` order, so for A=[1,2] and B=[10,20]:

```
A=1,B=10   A=1,B=20   A=2,B=10   A=2,B=20
```

…i.e. the right-most dimension varies fastest. This ordering is (a) documented
in the module and class docstrings, (b) unit-tested verbatim (check B), and
(c) the order in which `SweepRunner` executes and records variants and stores
`variant_run_ids`.

Round-tripping: `ParameterSweep.to_dict/from_dict` and
`MutationSpace.to_dict/from_dict` are JSON-safe, so a space can be persisted
and re-applied verbatim.

---

## 3. IMPLEMENTED — deterministic sweep identity

`sweep_id_of(world, space)` — 24-char deterministic id:

```
sha256( {"world_hash": world_hash(world), "space": <canonical space JSON>} )[:24]
```

The same base world + same mutation space ⇒ the same sweep id on replay. Two
identical sweeps in one store collapse to **one** `sweeps` metadata row
(replay is idempotent). A different value set produces a different sweep id.

Variant identity is Task 1.6's deterministic `run_id_of(mutated_world)`:
no randomness anywhere in generation, execution, or ranking.

---

## 4. IMPLEMENTED — SweepRunner (sequential, baseline-as-control)

`SweepRunner(store, executor, parameter_specs=None)` wraps the Task 1.6
`VariantRunner` (no second lineage implementation).

`sweep(base_world, mutation_space, *, sweep_id=None) -> SweepResult`:

1. **Phase 1 (no simulation):** generate every mutation set in product order,
   apply them to clones with the declared `parameter_specs` validators
   **up front**, and drop no-ops — combinations whose child world equals the
   base world exactly (e.g. a value equal to the current one). An out-of-bounds
   value aborts the sweep with *nothing executed or recorded*.
2. **Phase 2 (simulation):** run and record the **baseline control** first
   (`VariantRunner.run(base_world)`), then each surviving variant sequentially
   (`run_variant`), all children linked to the base run.
3. Persist one `SweepRecord` (see §6) into the lineage store.

`SweepResult` carries: `sweep_id`, `world`, `base` (the control `RunResult`),
`variants` (executed, in product order), `mutation_space`, `timing`
(§5), plus `ranking(metric, descending=...)` and `all_runs()`.

Guarantees: the base world object is never mutated (Task 1.6 immutable clones);
the baseline is always present even when a space generation produces zero
executed variants; `base.parent_run_id is None` and every variant points at the
base run.

---

## 5. IMPLEMENTED — timing instrumentation

`sweep.py::SweepTiming` — compact, persisted summary:

| Field | Meaning |
|---|---|
| `n_planned` | number of combinations in the declared Cartesian product |
| `n_skipped` | combinations dropped as no-ops (identical to the baseline) |
| `n_executed` | number of variants actually run |
| `total_seconds` | wall time of the whole sweep (base + variants) |
| `mean_seconds` | `total_seconds / n_executed` (comparable across sweep sizes) |

Instrumentation is data, not logging: it is stored in the `sweeps` row and
printed by the CLI.

---

## 6. IMPLEMENTED — sweep metadata persistence (reusing the lineage store)

`lineage.py` extends the Task 1.6 `LineageStore` **without weakening it**:

- new `SweepRecord` (immutable, JSON-safe) + a `sweeps` table
  (`INSERT OR REPLACE`, idempotent) with `get_sweep`, `iter_sweeps`,
  `sweep_count`;
- the same policy as run records: **metadata and compact summaries only —
  never trajectories**;
- per-run metric summaries live in the existing `runs` table; the `sweeps`
  row links to them via `base_run_id` and `variant_run_ids`.

Parent/child relationships therefore live in exactly one place (`runs.parent_run_id`),
and the sweep row groups them + their defining space + timing.

---

## 7. IMPLEMENTED — generic ranking

`SweepResult.ranking(metric, *, descending=True)` → `rank_results`:

- metric is selected **by name**; nothing is renamed, normalized, or weighted;
  runs lacking the metric are omitted (and a completely empty selection raises
  `ValueError` naming the metric);
- `descending` controls the direction; rank 1 is best;
- ties are broken **deterministically by `run_id` ascending**, so the ranking
  is a pure function of the runs — re-running the sweep reproduces it exactly
  (check E);
- each `RankingEntry` is `(rank, run_id, kind, value)` where `kind` is
  `"baseline"` or `"variant"` — the only "kind" labels, fully generic.

---

## 8. IMPLEMENTED — Experiment C integration

No new science code was required: the sweep reuses the Task 1.6 declarations
in `experiments/network_morphogenesis/experiment.py`
(`PARAMETER_SPECS`, `run_network_world`, `build_network_metrics`) verbatim.

### Real sweep (10 macro-steps, canonical values)

```
$ python run_sweep.py --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
                      --dim config.force_fmax:0.4,0.8 --rank-by field_entropy

Sweep id      1bd8ed40d3c686ca73cdb673
Mutation space: [{'path': 'components.network.config.loss', 'values': [0.05, 0.08, 0.11, 0.14]},
                 {'path': 'config.force_fmax',        'values': [0.4, 0.8]}]
Declared variants: 8 (baseline control included)

BASELINE (control)
  08c74954f42c86066b118244  field entropy: 2.97541, walls: 9,
                            wall movement: 0.012102, network load: 0.35086, sources: 24

VARIANTS (generation order: 7 executed)
   1. 88da217230709068a80e4e69  [loss 0.05 -> 0.05; force 0.8 -> 0.4]  entropy 2.97541
   2. b963a8247c71ba7943958bc4  [loss 0.05 -> 0.08; force 0.8 -> 0.4]  entropy 2.96882
   3. fe720fc8aaa3126477cce9d0  [loss 0.05 -> 0.08; force 0.8 -> 0.8]  entropy 2.96882
   4. d277cfd755288154a14800f0  [loss 0.05 -> 0.11; force 0.8 -> 0.4]  entropy 2.99428
   5. ad44404b2280255d37991590  [loss 0.05 -> 0.11; force 0.8 -> 0.8]  entropy 2.99428
   6. 0de22fcf1d44fe73b66d1f2b  [loss 0.05 -> 0.14; force 0.8 -> 0.4]  entropy 3.08141
   7. f3faa9c9d8d344b46271a393  [loss 0.05 -> 0.14; force 0.8 -> 0.8]  entropy 3.08141

(skipped 1 no-op combination(s) identical to baseline)   # loss=0.05, force=0.8
TIMING  planned=8 executed=7 total=13.37s mean=1.91s

RANKING by field_entropy (descending)
   1. 0de22fcf1d44fe73b66d1f2b  3.08141  variant
   2. f3faa9c9d8d344b46271a393  3.08141  variant     # tie broken by run_id
   3. ad44404b2280255d37991590  2.99428  variant
   4. d277cfd755288154a14800f0  2.99428  variant
   5. 08c74954f42c86066b118244  2.97541  baseline
   6. 88da217230709068a80e4e69  2.97541  variant     # baseline/variant tie → run_id
   7. b963a8247c71ba7943958bc4  2.96882  variant
   8. fe720fc8aaa3126477cce9d0  2.96882  variant

LINEAGE
  Base    08c74954f42c86066b118244   ← parent of all 7 variants
   +-- 7 variant runs (run_ids above)
```

Notable cross-layer determinism check: the base run id
`08c74954f42c86066b118244` and the strongest-loss variant
`f3faa9c9d8d344b46271a393` are **exactly** the two run ids Task 1.6 already
recorded for the identical 10-step base and loss=0.14 worlds — the sweep layer
reproduces the singular-variant lineage bit for bit.

Real observed result of the sweep: raising the network diffusion `loss` from
0.05 to 0.14 lowers the steady network load (0.351 → 0.281) and increases the
field's disorder (`field_entropy` 2.9688 → 3.0814, the best-ranked variants at
loss=0.14), consistent with the Task 1.6 finding that higher loss concentrates
diffusion and re-routes corridors.

---

## 9. IMPLEMENTED — deterministic replay / reproducibility

Proved two ways:

- **Unit level (check E):** running the same world + space twice (fresh stores)
  reproduces identical base/variant run ids, metrics, and ranking;
- **CLI level:** the 10-step run above, re-run, reproduces the same sweep id,
  the same 8 run ids, the same metrics, and the same ranking (recorded
  numbers above are from a real run, not estimates).

Idempotence: re-recording the same sweep/run into the same store converges on
one `runs` row per run and one `sweeps` row per sweep (checked in J/K/P).

---

## 10. IMPLEMENTED — tests

`tests/test_sweep_ranking.py` — 18 tests, checks A–Q.

| Check | Coverage |
|---|---|
| A | 1-D sweep: generation order == declared value order |
| B | multi-D sweep: documented Cartesian product order exact |
| C | variant identity deterministic across independent stores |
| D | sweep id deterministic + differs across spaces; store collapses duplicates |
| E | repeated sweep reproduces identical run ids / metrics / ranking |
| F | baseline control included, recorded first, unmutated, parent of all |
| G | base world object never mutated in place |
| H | `parameter_specs` bounds enforced before any variant executes |
| I | identical-to-base combinations skipped (counted, not re-executed) |
| J | lineage links every variant to the base run |
| K | compact `sweeps` metadata persisted (no trajectories); runs carry metrics |
| L | ranking direction + deterministic tie-break (by run id) |
| M | generic metric selection; unknown metric raises |
| N | `sweep.py` core contains **no** experiment identifiers |
| O | real Experiment C sweep executes end-to-end (4–12 variants, real metrics) |
| P | sweep metrics stored generically; replay idempotent |
| Q | timing instrumentation (planned/skipped/executed, total/mean seconds) |

The Task 1.6 test `test_l` (core files experiment-free) was extended to also
scan `sweep.py`; the core immutability guard was re-baselined (§12). No prior
test is weakened.

---

## 11. IMPLEMENTED — CLI

`run_sweep.py` (project convention `run_*.py`, same shape as
`run_variant_demo.py`):

```
uv run python run_sweep.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --dim config.force_fmax:0.4,0.8 \
    --rank-by field_entropy [--ascending] [--steps N] [--world file.yaml] [--db file.db]
```

Prints: sweep id, mutation space, baseline, variants in **generation order**
with their mutation sets and real metrics, skip/timing instrumentation, the
generic ranking, the lineage tree, and the SQLite persistence summary
(run/sweep counts). `--db` defaults to a temporary file so persistence is real
but scratch.

CLI extends core:: CLI is a thin shell over the generic `SweepRunner`; it
contains no ranking/sweep logic of its own.

---

## 12. IMPLEMENTED — repository hygiene changes

- `src/sim_alchemist/core/` gains `sweep.py`; `lineage.py` + `__init__.py` are
  extended (sweeps table/metadata + re-exports). **No other core file
  changed.** `runner.py`/`mutation.py` untouched.
- Core immutability guard in `tests/test_field_guided_movers.py` was
  **re-baselined** (the sanctioned milestone-extension pattern, as earlier for
  Task 1.3/1.6) to pin the new hash of `lineage.py`, `__init__.py`, and to add
  `sweep.py`. The guard stays on: post-1.7 core is protected against drift.
- `tests/test_network_morphogenesis.py` guard reuses the same map, no change.

---

## 13. File tree (new / changed)

```
src/sim_alchemist/core/
    sweep.py              NEW  mutation space, sweep runner, ranking (+ sweep id)
    lineage.py            MOD  + SweepRecord, `sweeps` table, get/iter/count
    __init__.py           MOD  re-exports the new API
tests/
    test_sweep_ranking.py NEW  18 tests (checks A–Q)
    test_mutation_lineage.py   MOD  check L now also scans sweep.py
    test_field_guided_movers.py MOD  guard re-baselined (Task 1.7 extension)
run_sweep.py              NEW  deterministic sweep + ranking CLI
```

---

## 14. Validation results (closing gate)

Rerun as with the Task 1.6 gate, identical commands:

- `pytest` — full suite PASSES: **146 tests** (143 fast + 3 slow; 18 new
  Task 1.7 tests); no previous tests weakened.
- `run_validation.py` — A–G all PASS.
- `run_stability.py` — S1–S6 all PASS.
- `ruff check .` — CLEAN.
- `pyright` (full repo) — 0 errors.
- `uv sync` / `uv lock` — environment unchanged except no new dependencies
  (stdlib-only sweep layer).

---

## 15. PLANNED (NOT implemented)

Deliberately out of scope for Task 1.7 (task constraint):

- parallel / multiprocessing variant execution;
- evolutionary, Bayesian, genetic, or any AI-driven sweep/search;
- metric normalization, weighting, or aggregate "interestingness" scores —
  ranking deliberately compares raw values only;
- automatic engine selection; experiment database beyond the lineage store;
- anything that touches `runner.py`/`mutation.py` semantics.

---

## 16. Architectural weaknesses / remaining limitations

- Sweep generation is combinatorial; a wide multi-dimensional space is large
  by design (sequential runner; count is explicit in `SweepTiming.n_planned`).
- No-ops are dropped silently-but-counted: `n_skipped` records them, but the
  user must consult the timing summary (documented + tested).
- Ranking requires one metric at a time (generic by construction; multi-metric
  ranking is future work).
- Determinism remains same-runtime/same-environment (inherited; not universal
  cross-platform bitwise equivalence).
- Parameter bounds remain hand-tuned for the validated runs.

---

## 17. What Task 1.8 (next, NOT started) could build

Automatic `run <world> --variants ...` automation atop this layer: sweep-driven
automation over multiple metrics, experiment-database queries over `sweeps` +
`runs`, and (later, explicitly deferred) parallel execution. Nothing in Task
1.8 has been built or started here.