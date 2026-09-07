# TASK 1.9 REPORT — Guided Simulation Search (First Discovery Loop)

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 1.9 (deterministic beam search, no GA/evolutionary/ML/Bayesian)
**Subject experiment:** Experiment C — Adaptive Network Morphogenesis

---

## 1. Objective

Build the framework's **first discovery loop**: an iterative,
deterministic, bounded search over world variants that finds the behavior an
explicit ``InterestingnessProfile`` ranks as most interesting — the
GENERATE → RUN → ANALYZE → SELECT → REPEAT cycle:

- **beam search over world variants**: generation 0 executes the unmutated
  base world as a control; each later generation mutates the current beam
  (the ``beam_width`` most interesting known worlds), runs unique children,
  and keeps the most interesting frontier;
- **reuses existing generic machinery** (``apply_mutations`` / ``ParameterSpec``
  validation, deterministic ``run_id``, ``rank_by_profile``) — no new
  simulation concept is introduced;
- **fully deterministic**: same world + spec + space + seed + profile always
  reproduce identical candidate order, scores, generation structure, and
  ranking; ties break by ``run_id`` ascending (Task 1.7 rule reused);
- **every evaluated candidate is explainable**: per-feature contributions from
  the interestingness ranking; the CLI prints *why* the best candidate won;
- **child generation**: dimension-major, value-minor, skip no-ops (values
  equal to the parent's current leaf), truncate to ``children_per_parent``,
  single-dim mutation per child; duplicate worlds detected via ``world_hash``
  visited set and counted;
- a real **Experiment C search** (declared space → beam search → ranking →
  explanation) with a repeatability proof and measured performance;
- **no GA/evolutionary computation** (no DEAP, no crossover, no genomes, no
  genetic operators, no population-genetics abstractions), no Bayesian
  optimization, no RL, no ML/learned weights, no new external dependencies,
  no multiprocessing — all per the task constraint.

---

## 2. IMPLEMENTED — search model (beam search over world variants)

`src/sim_alchemist/core/search.py` — fully generic, zero experiment knowledge.

| Concept | Description |
|---|---|
| `SearchSpec(name, generations, beam_width, children_per_parent, mutation_space, profile, seed)` | frozen, validated declarative configuration; `generations` >= 1; seed is an `int` replay key (no random component) |
| `SearchRunner(store, executor, observables, parameter_specs=..., analyzer=...)` | sequential beam search; reuses `apply_mutations` (Task 1.6), `rank_by_profile` (Task 1.8), `LineageStore` |
| `SearchCandidate` | one evaluated world: id, run_id, generation, kind ("baseline"/"variant"), parent links, mutations, metrics, features, score, selection/final ranks |
| `SearchGeneration` | one beam step: parents, children, selected beam, best id/score |
| `SearchResult` | full in-memory outcome: candidates, generations, final ranking, timing; `best()`, `lineage_path()`, `mutation_path()`, `explain_best()` |
| `SearchTiming(n_generated, n_skipped, n_executed, total_seconds, execution_seconds, analysis_seconds, mean_seconds)` | compact instrumentation (no per-step data) |
| `child_mutations(world, space, children_per_parent, validators=...)` | deterministic child mutation sets: dimension-major, value-minor, no-op skip, single-param |
| `search_id_of(world, spec)` | deterministic 24-hex id from `sha256(world_hash + spec JSON)` |

**Generation structure**: the `generations` tuple always has length
`spec.generations + 1` (generation 0 = root control record with
`parent=()`, `selected=[root]`, `best_score=None`).

**child_mutations rule**: dimensions in declared `MutationSpace` order,
values in declared order, a value equal to the parent's current leaf
is skipped (a no-op cannot extend the beam), single-parameter children
(one mutation per set), truncated at `children_per_parent`. Duplicates
across the beam are detected via `world_hash` and counted in
`n_skipped` but never re-executed.

**Ranking**: at each generation, the pool is surviving parents + new
children; `rank_by_profile` normalizes across that pool.
`selection_rank` is assigned on first ranking (creation generation).
`score` is overwritten by the final global ranking at the end.
`final_rank` = rank in the final global ranking (1 = best).

---

## 3. IMPLEMENTED — determinism and replay

Everything is a pure function of `(world, mutation_space, profile, search_seed)`:

- candidate ids (`candidate-000`, `candidate-001`, ...) are assigned in
  traversal order (root-first, then depth-first across the beam);
- child mutation sets are produced in documented fixed order;
- no random component in the search itself (seed only disambiguates
  otherwise-identical searches);
- `SearchResult.as_dict(canonical=True)` drops wall-clock timing and
  captures every identity, order, score, and rank — two runs on the same
  world+spec+space+seed+profile produce bitwise-identical canonical dicts.

Proved on real Experiment C (test N): two independent runs with identical
inputs produce identical `search_id`, canonical dicts, candidate ids, and
best candidate.

---

## 4. IMPLEMENTED — lineage persistence (compact only)

`lineage.py` is extended **without weakening** the Task 1.6/1.7/1.8 store:

- new `searches` table — one row per search: `search_id`, `world_id`,
  `world_hash`, `base_run_id`, `spec_json`, `candidates_json`,
  `generation_order_json`, `ranked_json`, `timing_json`, `created_at`;
- `SearchRecord` class with `from_result()` / `from_row()` / `as_dict()`;
- `record_search()` / `get_search()` / `iter_searches()` / `search_count`;
- per-run `RunRecord` rows (with compact `feature_snapshot`) are recorded
  by the existing Task 1.6 lineage layer — no duplication;
- **trajectories and per-step observables are never persisted** — they live
  only on in-memory `SearchCandidate` objects;
- `_migrate()` adds the `searches` table to pre-1.9 stores on open
  (tested implicitly via fresh stores).

---

## 5. IMPLEMENTED — Experiment C integration

No new science code: the search reuses Task 1.6 `PARAMETER_SPECS` /
`run_network_world` / `specs_by_path()` and Task 1.8
`build_network_observables` verbatim. The search CLI wraps the generic
`SearchRunner`.

### Real search (160 macro-steps, canonical regression)

```
$ uv run python run_search.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --dim config.force_fmax:0.4,0.8 \
    --feature wall_count:activity_rate:0.4:max \
    --feature field_mean:oscillation_strength:0.3:max \
    --feature network_load_max:late_vs_full_variance_ratio:0.3:min \
    --generations 3 --beam-width 2 --children 3 --steps 160

Guided simulation search (adaptive_network, 160 macro-steps)
Mutation space: [{path: components.network.config.loss, values: [0.05, 0.08, 0.11, 0.14]}, {path: config.force_fmax, values: [0.4, 0.8]}]
Beam search: 3 generations, beam 2, 3 children per parent
Profile: {'wall_count:activity_rate': 0.4, 'field_mean:oscillation_strength': 0.3, 'network_load_max:late_vs_full_variance_ratio': 0.3}

Search id     <24-hex id>
Base world    <world_hash>

GENERATIONS (parents -> children -> kept beam, best first)
  gen 0  kept=['candidate-000']  children=1  root control
  gen 1  kept=['candidate-000', 'candidate-001']  children=3  best candidate-000 score=0.6
  gen 2  kept=['candidate-000', 'candidate-004']  children=5  best candidate-000 score=0.6
  gen 3  kept=['candidate-000', 'candidate-007']  children=6  best candidate-000 score=0.6

FINAL RANKING (all evaluated candidates, ties by run id ascending)
   1. <run_id>  score=0.6      baseline  (root control) <== best
   2. <run_id>  score=0.499...  variant
   ...

WHY (best candidate)
  candidate-000 (run <run_id>, generation 0)
  lineage path: candidate-000
  rank 1 (baseline, run <run_id>, score 0.6)
    network_load_max:late_vs_full_variance_ratio: raw 0, norm 0, favors interest, w 0.3 -> +0.3
    field_mean:oscillation_strength: raw ..., norm 1, favors interest, w 0.3 -> +0.3
    wall_count:activity_rate: raw 1, norm 0, favors interest, w 0.4 -> +0

TIMING  generated=... executed=... total=... exec=... analysis=... mean=...
Figure     figures/search_beam_scores.png
LINEAGE
  Root    <run_id>  (baseline control)
Persisted to SQLite: ...  (runs=..., searches=1)
```

**What the results support (and what they do not):**

- The root control is the most interesting candidate under the declared
  profile: it has the **highest field oscillation strength** and a
  **constant (flat) network-load max** (`late_vs_full_variance_ratio = 0`);
  `wall_count` activity is a monotone ramp (activity = 1 for every run),
  so this profile feature adds nothing for any candidate — shown honestly
  as `+0`.
- The search explored the declared 2-D space (loss × force) via beam
  expansion; the root remained on top across every generation, indicating
  that the default parameters are locally optimal under this profile for
  the evaluated neighborhood.
- **No chaos/emergence/phase-transition claim is made anywhere.** The
  report only states the measured feature differences and the declared
  profile's ranking.
- This is a bounded heuristic: the beam covers a fraction of the full
  space; global optimality is not claimed.

---

## 6. IMPLEMENTED — tests

`tests/test_search.py` — 15 tests, checks A–O (same letter scheme as
the Task 1.7/1.8 suites).

| Check | Coverage |
|---|---|
| A | `SearchSpec` validation: positive ints, non-empty name, seed type |
| B | `child_mutations` order (dimension-major, value-minor), single-param sets, truncation to `children_per_parent`, parent immutability |
| C | No-op values (equal to parent's current leaf) are skipped |
| D | Duplicate worlds visited once (generated, not re-executed, `n_skipped` counted) |
| E | Base / parent worlds are never mutated in place; children are clones |
| F | Beam structure: generation records, parents feed the next beam, `beam_width` honored |
| G | Generation flow and lineage in the store: candidate ids, parent run links, search count |
| H | Profile-driven selection: two opposite profiles produce clearly divergent rankings ("interesting ≠ largest value") |
| I | Whole-search determinism: same world+spec+space+seed+profile produce identical canonical output (ids, candidates, generations, ranking) |
| J | `search_id_of` is deterministic, 24-hex, sensitive to world/spec/seed |
| K | Final ranking covers every candidate; `best()` / `lineage_path` / `mutation_path` / `explain_best()` consistent |
| L | Compact persistence only (no trajectories, no per-step data in search record); recording is idempotent |
| M | Core `search.py` contains no experiment-specific identifiers (forbidden-token scan) |
| N | Real Experiment C search executes end-to-end (root + children) and is bitwise reproducible across runs/stores |
| O | Performance instrumentation: generated/skipped/executed counts, timing breakdown, `as_dict()` key set |

The Task 1.6 test `test_l` was extended to also scan `search.py`; the core
immutability guard was re-baselined (§7). No prior test is weakened.

---

## 7. IMPLEMENTED — repository hygiene changes

- `src/sim_alchemist/core/` gains `search.py`; `lineage.py` + `__init__.py`
  are extended (search record persistence + searches table + migration +
  re-exports). **No other core file changed.**
- Core immutability guard in `tests/test_field_guided_movers.py` was
  **re-baselined** (the sanctioned milestone-extension pattern, as for Task
  1.3/1.6/1.7/1.8) — adds `search.py`, re-pins `lineage.py` and
  `__init__.py`.
- `tests/test_network_morphogenesis.py` guard reuses the same `CORE_COMMIT_HASHES`
  dict (imported from `test_field_guided_movers`).
- `tests/test_mutation_lineage.py` check L extended to also scan `search.py`.

---

## 8. File tree (new / changed)

```
src/sim_alchemist/core/
    search.py           NEW  beam search engine: SearchSpec, SearchRunner,
                              child_mutations, search_id_of, SearchResult,
                              SearchCandidate, SearchGeneration, SearchTiming
    lineage.py          MOD  + SearchRecord, searches table schema,
                              record_search/get_search/iter_searches/search_count
    __init__.py         MOD  re-exports the search API
tests/
    test_search.py      NEW  15 tests (checks A-O)
    test_mutation_lineage.py  MOD  check L now also scans search.py
    test_field_guided_movers.py MOD  guard re-baselined (Task 1.9 extension)
run_search.py          NEW  CLI: guided beam search + matplotlib figure
figures/
    search_beam_scores.png  NEW  matplotlib artifact (score vs generation)
```

---

## 9. Validation results (closing gate)

- `pytest` — full suite PASSES: **181 tests** (178 fast + 3 slow; 15 new
  Task 1.9 tests); no previous tests weakened.
- `run_validation.py` — A–G all PASS.
- `run_stability.py` — S1–S6 all PASS.
- `ruff check .` — CLEAN.
- `pyright` (full repo) — 0 errors.
- Environment unchanged (no new dependencies added).

---

## 10. IMPLEMENTED — CLI

`run_search.py` (project convention `run_*.py`, same shape as
`run_sweep.py` / `run_behavior_demo.py`):

```
uv run python run_search.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --dim config.force_fmax:0.4,0.8 \
    --feature wall_count:activity_rate:0.4:max \
    --feature field_mean:oscillation_strength:0.3:max \
    --feature network_load_max:late_vs_full_variance_ratio:0.3:min \
    [--generations N] [--beam-width N] [--children N] \
    [--steps N] [--world file.yaml] [--db file.db] \
    [--figure path.png] [--name label] [--seed N]
```

Prints: search id, base world hash, per-generation beam summary, the
final global ranking, the **explanation of why the best candidate won**
(lineage path + per-feature contributions), timing instrumentation, and
saves a matplotlib figure (score vs generation, frontier + best).

CLI is a thin shell over the generic `SearchRunner`; it contains no
search logic of its own.

---

## 11. PLANNED (NOT implemented)

Deliberately out of scope for Task 1.9 (task constraint):

- **no** genetic algorithms, evolutionary computation, DEAP, crossover,
  genomes, or population-genetics abstractions;
- **no** Bayesian optimization, reinforcement learning, or machine learning
  of any kind (no learned weights, no neural networks, no embeddings);
- no multiprocessing or distributed execution;
- no global-optimality claim (beam search is a bounded heuristic);
- no YAML-serialized search specifications (the CLI builds the spec
  from `--dim` / `--feature` flags);
- no UI, no cloud, nothing for Task 2.0.

---

## 12. Architectural weaknesses / remaining limitations

- Beam search is a **bounded heuristic**: it keeps the best-known frontier
  and discards the rest; it does not guarantee global optimality over the
  full mutation space. Wider beams and more generations improve coverage
  at the cost of compute.
- The current `child_mutations` generates **single-parameter children**
  only (one declared parameter per child mutation set); multi-parameter
  combinations in the same child are not explored. This is a deliberate
  MVP simplification.
- `oscillation_persistence` (inherited from Task 1.8) is blind to periods
  ≲ 4 samples — documented, deliberate.
- Determinism remains same-runtime/same-environment (inherited; not universal
  cross-platform bitwise equivalence).
- Persisted search records are compact metadata; they do **not** reconstruct
  the original time series or observable trajectories.

---

## 13. What Task 2.0 (next, NOT started) could build

Nothing has been planned or started beyond Task 1.9. The natural next steps
(per `IMPLEMENTATION_PLAN.md`): plugin/adapter registry (extensible
`ComponentRegistry` with external adapters and capability discovery),
generalized world composition beyond `compose()`, deterministic replay,
or exposing Experiments A/B observables — all remain **not started**.
