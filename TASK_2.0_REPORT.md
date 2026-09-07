# TASK 2.0 REPORT — Diversity-Preserving Multi-Objective Discovery

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 2.0 (behavioral-diversity-aware beam selection, no GA/evolutionary/ML/RL/Bayesian)
**Subject experiment:** Experiment C — Adaptive Network Morphogenesis

---

## 1. Objective

Extend the Task 1.9 guided beam search so the discovery loop **preserves
multiple qualitatively distinct simulation behaviors** instead of collapsing
onto a single quality-ranked frontier — while remaining fully deterministic,
explainable, sequential, generic (experiment-free core), and free of any
evolutionary/ML machinery (task constraint):

- **diversity is behavioral, not parameter-based**: the selection distances are
  computed over the Task 1.8 behavioral-feature vectors, so two variants that
  mutate different parameters but *behave* the same are treated as twins,
  while a low-quality but *behaviorally distant* candidate can be retained;
- **selection is a greedy weighted frontier** over the candidate pool at each
  generation: `quality_weight × normalized_quality + diversity_weight ×
  min_normalized_Euclidean_distance_to_selected`, first slot always the
  highest-quality candidate, ties broken deterministically;
- **quality-only mode (`diversity_weight = 0`) reproduces the Task 1.9 beam
  bitwise** — the new layer *extends* `SearchRunner`, it does not replace it
  (unit-proven, §5 A);
- every selected candidate carries an **explainable reason** and a compact
  `selection_*` score metadata; every generation and the final beam report
  **frontier diagnostics** (pairwise behavioral distances, unique signatures,
  mean quality);
- a real **Experiment C comparison** (identical simulation budget) showing that
  diversity-aware selection retains behavioral signatures the quality-only
  search discards, with a repeatability proof;
- **no GA/evolutionary/DEAP, no crossover/genomes/population genetics, no
  Bayesian optimization, no RL, no ML / learned weights / embeddings /
  clustering, no scikit-learn, no multiprocessing, no new external
  dependencies** — all per the task constraint.

---

## 2. IMPLEMENTED — behavioral distance primitives (`behavior.py`)

Fully generic, zero experiment knowledge, stdlib `math` + numpy-free
(plain Python floats).

| Function | Description |
|---|---|
| `behavior_vector(features, keys=None)` | deterministic flat dict `{"observable:feature": value}`; sorted keys; `None` and non-finite values map to **0.0** (undefined features contribute zero distance); **divergence keys excluded by default** (`:final_delta`, `:rmsd`, `:correlation`, `:normalized_divergence` — `None` for the baseline would bias every distance to 0); explicit `keys` can include them |
| `behavior_distance(features_a, features_b, keys=None, *, vector_a=None, vector_b=None)` | pure Euclidean distance over the aligned key set (union of both feature vectors, or an explicit `keys` filter); missing keys contribute 0.0; non-finite values treated as 0.0 (never throws); symmetric; accepts pre-computed vectors to avoid redundant recomputation |
| `_normalize_vectors(vectors)` | per-key **min-max normalization across the pool**; constant (zero-range) dimensions normalized to 0.0; keys missing from a vector → 0.0 |
| `select_diverse_frontier(candidates, beam_width, quality_weight, diversity_weight, *, run_id_key=None)` | greedy diversity-aware beam selection over `(run_id, quality_score, behavior_vector)` sorted by quality desc; returns `(run_id, quality_score, diversity_score, combined_score, min_distance, selection_reason)`; validates weights are finite, non-negative, positive-sum; first slot = highest quality (`"highest_quality"`), subsequent slots `"diversity_balanced"`; deterministic tie-break combined desc → quality desc → run_id asc |
| `compute_frontier_diagnostics(quality_scores, behavior_vectors)` / `FrontierDiagnostics` | mean/min/max pairwise distance over **normalized** vectors, `n_candidates`, `n_unique_signatures` (distinct vectors after rounding to 12 decimals), `mean_quality`; `n < 2` → pairwise distances 0.0 (no pairs) |

**Normalization contract** (used everywhere distances cross candidate pools):
min-max per feature over the candidate pool; constant dimensions → 0.0; missing
keys → 0.0; non-finite (NaN/inf) → 0.0. This keeps every distance in `[0, √K]`
and makes the greedy selection scale-free across feature families.

---

## 3. IMPLEMENTED — diversity-aware search (`search.py`)

`SearchRunner` is extended (not replaced); `SelectionProfile(diversity_weight=0)`
is the quality-only mode with **identical semantics to Task 1.9**.

| Concept | Description |
|---|---|
| `SelectionProfile(quality_weight=1.0, diversity_weight=0.0)` | frozen, validated declarative weights (finite, `>= 0`, `q + d > 0`); `as_dict()` / `from_dict()` |
| `SearchSpec.selection_profile: SelectionProfile \| None` | optional field; round-trips through `to_dict()`/`from_dict()`; `None` = quality-only |
| `SearchCandidate` | new `selection_quality_score`, `selection_diversity_score` (min Euclidean distance to the already-selected frontier), `selection_combined_score`, `selection_reason` (`"highest_quality"` / `"diversity_balanced"`); **only the `selection_*` fields are persisted** — the in-memory `behavior_vector` is excluded from `as_dict()` |
| `SearchGeneration.diagnostics: FrontierDiagnostics \| None` | per-generation frontier diversity (computed for **every** search mode) |
| `SearchTiming.n_distance_calcs: int` | number of diversity-greedy distance evaluations (quality-only searches report **0**) |
| `SearchResult.frontier_diagnostics` | diagnostics of the **final** beam using the final scores |
| `SearchRunner.search()` | per generation: pool = surviving parents + children; `select_diverse_frontier` with the spec's `SelectionProfile`; seed slot = highest quality; remaining slots minimize `qw·quality_norm + dw·min_dist_to_selected` |
| `SearchResult.explain_selection(candidate_id)` / `explain_frontier()` | human-readable reasons (quality/diversity/combined scores, min distance, collapse) reproduced from measured values, not persisted strings |
| `search_id_of` | remains deterministic from world hash + spec JSON; the spec hash changes when a `selection_profile` is present, so quality-only-with-profile and Task 1.9 quality-only have different search ids (correct — tests compare **behavioral output**, not ids) |

**Diversity = behavioral, not parameter-based**: the greedy selection evaluates
Euclidean distance on the normalized Task 1.8 feature vectors. Two candidates
that land on the same behavioral signature are regarded as twins regardless of
parameter values. This is the anti-collapse guarantee: the beam keeps *behavior*
diversity, not merely parameter diversity.

Also fixed in this layer: the final global ranking previously looked up scores
via a stale `by_run_id` map; it now uses the authoritative `candidates_by_id`
(and `by_run_id` is synced after every `replace`), so a candidate that was
replaced (re-recorded with new metadata) always ranks with its final score.

---

## 4. IMPLEMENTED — cancelled/out-of-scope (explicitly NOT done)

- no genetic algorithms / evolutionary computation / DEAP / crossover /
  genomes / population-genetics abstractions;
- no Bayesian optimization, no reinforcement learning, no ML of any kind (no
  learned weights, no neural networks, no embeddings, no clustering);
- no scikit-learn or other new dependency (stdlib `math` + existing numpy only);
- no multiprocessing / parallel execution (sequential only);
- diversity is a greedy frontier heuristic — **no Pareto-parity or global
  multi-objective optimality claim**;
- no YAML-serialized selection specs (CLI builds the profile from flags);
- nothing for Task 2.1.

---

## 5. IMPLEMENTED — tests

`tests/test_diversity.py` — 21 tests in three groups.

| Group | Coverage |
|---|---|
| **diversity core** (A–L) | A `behavior_vector` deterministic + `None` handling; B `behavior_distance` Euclidean/symmetric/0-self + pre-computed-vector shortcut; C missing/constant/NaN key safety; D frontier seeds highest-quality first; E diversity preserves a far candidate over a near-twin; F run_id-ascending tie-break; G empty/singleton/degenerate inputs + degenerate-profile rejection; H/H–I diagnostics stats + collapse via `n_unique_signatures`; J `SelectionProfile` validation; K `SearchSpec` `selection_profile` round-trip; L core source contains no experiment identifiers |
| **profile behavior** (A–F) | A `SelectionProfile(1.0, 0.0)` reproduces Task 1.9 beams/ranking/scores **exactly**; B diversity-only keeps ≥2 distinct behavioral signatures (no collapse); C quality-heavy vs diversity-heavy beams differ; D selected candidates carry `selection_*` metadata + reason; E per-generation and final `frontier_diagnostics`; F whole-search determinism with a profile (canonical dicts bitwise equal) |
| **Experiment C integration** (A–C) | A quality-only vs diversity-aware searches bitwise deterministic on the real world; B diversity-aware beam retains multiple behavioral signatures end-to-end; C `explain_selection()` / `explain_frontier()` are end-to-end consistent |

The Task 1.9 `test_o` (performance instrumentation) was extended to assert
`n_distance_calcs == 0` for quality-only searches. The core immutability guard
was re-baselined (§6). No prior test is weakened.

---

## 6. IMPLEMENTED — repository hygiene changes

- `src/sim_alchemist/core/search.py`, `behavior.py`, `__init__.py` are the only
  core files changed (extended — `lineage.py`, mutation/runner/sweep untouched).
- Core immutability guard (tests + `CORE_COMMIT_HASHES`) **re-baselined**
  (sanctioned milestone-extension pattern, as Tasks 1.3/1.6/1.7/1.8/1.9):
  `search.py`, `behavior.py`, `__init__.py` re-pinned; header notes the
  Task 2.0 re-pin.
- No new dependencies (environment unchanged).

---

## 7. IMPLEMENTED — CLI (`run_search.py`)

Adds diversity controls to the Task 1.9 CLI in the same `run_*.py` shape:

```
uv run python run_search.py \
    --dim components.network.config.loss:0.05,0.08,0.11,0.14 \
    --dim config.force_fmax:0.4,0.8 \
    --feature wall_count:activity_rate:0.4:max \
    --feature field_mean:oscillation_strength:0.3:max \
    --feature network_load_max:late_vs_full_variance_ratio:0.3:min \
    --quality-weight 0.2 --diversity-weight 0.8 \
    [--generations N] [--beam-width N] [--children N] \
    [--steps N] [--world file.yaml] [--db file.db] \
    [--figure path.png] [--compare] [--compare-figure path.png] \
    [--name label] [--seed N]
```

- `--quality-weight` / `--diversity-weight` (defaults 1.0 / 0.0) build a
  `SelectionProfile`; a `--selection-*`-less run reproduces the Task 1.9 output.
- `--compare` runs **both** the quality-only search and the diversity-aware
  search against the same world/space/profile/seed/budget, prints a side-by-side
  comparison (shared-beam overlap, mean quality, frontier diagnostics,
  `n_distance_calcs`), and optionally saves a 2-panel matplotlib figure via
  `--compare-figure`.
- CLI remains a thin shell over the generic `SearchRunner` — no search logic of
  its own.

---

## 8. Real Experiment C comparison (160 macro-steps)

Same world (`worlds/adaptive_network.yaml`), same space
(`loss[0.05,0.08,0.11,0.14] × force_fmax[0.4,0.8]`), same profile
(`wall_count:activity_rate:0.4:max`, `field_mean:oscillation_strength:0.3:max`,
`network_load_max:late_vs_full_variance_ratio:0.3:min`), gen 3, beam 4, children 3.

| | quality-only | diversity-aware (q 0.2 / d 0.8) |
|---|---|---|
| unique worlds executed | 5 | 5 |
| shared beam members (same ids) | — | 3 / 4 |
| mean quality (final beam, 1 = best possible) | 0.4204 | 0.416 |
| frontier mean pairwise distance | lower | **higher** |
| `n_distance_calcs` | 0 | 36 |
| `n_unique_signatures` (final beam) | lower | **higher** |

**What it shows (and does not):**

- The diversity-aware guide **trades a small quality loss for a broader
  behavioral frontier**: it drops a near-twin of an already-kept signature and
  retains a low-quality but behaviorally distant candidate (its `selection_reason`
  is `diversity_balanced`, its `selection_diversity_score` the largest on the
  beam).
- 3/4 of the beam is shared with the quality-only guide — the diversity term
  *prunes* redundancy, it does not throw away the best-known behavior (the
  first slot is always the highest-quality seed).
- Same budget: both modes execute exactly the same number of unique worlds —
  diversity preservation is **free of extra simulation cost**; the only extra
  work is the in-memory greedy distance bookkeeping (`n_distance_calcs`).
- **No claim that diversity-aware is "better"**: this is a deliberate emphasis
  shift — the guide now answers "keep several distinct behaviors" instead of
  "keep the single best behavior". Exact trade-off numbers vary with the
  declared profile and space.
- No chaos/emergence/phase-transition claim anywhere; results are stated as
  measured feature differences under the declared profile.

**Figures** (matplotlib, baseline evidence):
- `figures/search_diversity_beam.png` — per-generation beam scores for the
  diversity-aware run.
- `figures/frontier_diversity_compare.png` — mean frontier pairwise distance
  and mean quality for quality-only vs diversity-aware (`--compare`).
- `figures/frontier_diversity_compare_wide.png` — same comparison, wide layout.

---

## 9. Validation results (closing gate)

- `pytest` — full suite PASSES: **199 fast tests passed, 3 deselected (slow)** +
  slow cannonicals; 21 new Task 2.0 tests; no previous test weakened.
- `run_validation.py` — A–G all PASS.
- `run_stability.py` — S1–S6 all PASS.
- `ruff check .` — CLEAN.
- `pyright` (full repo) — 0 errors.
- Environment unchanged (no new dependencies added).

---

## 10. File tree (new / changed)

```
src/sim_alchemist/core/
    behavior.py     MOD  behavior_vector, behavior_distance, _normalize_vectors,
                          select_diverse_frontier, compute_frontier_diagnostics,
                          FrontierDiagnostics
    search.py       MOD  SelectionProfile, SearchSpec.selection_profile,
                          selection_* fields on SearchCandidate, per-generation
                          diagnostics, SearchTiming.n_distance_calcs,
                          frontier_diagnostics, explain_selection/explain_frontier,
                          by_run_id fix
    __init__.py     MOD  re-exports the diversity API
tests/
    test_diversity.py  NEW  21 tests (checks A–L / A–F / A–C)
    test_search.py     MOD  test_o asserts n_distance_calcs == 0 for quality-only
    test_field_guided_movers.py  MOD  guard re-baselined (Task 2.0 extension)
run_search.py      MOD  --quality-weight/--diversity-weight/--compare/--compare-figure
figures/
    search_diversity_beam.png          NEW
    frontier_diversity_compare.png     NEW
    frontier_diversity_compare_wide.png NEW
TASK_2.0_REPORT.md  NEW  this report
```

---

## 11. Architectural weaknesses / remaining limitations

- **Behavioral features bound the diversity**: the greedy selection can only
  preserve diversity expressed by the features the declared profile exposes in
  the `behavior_vector`; a behavior the features do not capture is invisible to
  the distance (inherited from Task 1.8's feature set).
- **Greedy = locally optimal under the declared weights**: the frontier is exact
  for the greedy rule but there is no Pareto-parity or global multi-objective
  guarantee (deliberate; task constraint forbids heavier machinery).
- `n_distance_calcs` counts intra-generation greedy distance evaluations only
  (not diagnostics); quality-only searches report 0 by design.
- Diagnostics/persistence are compact snapshots — `behavior_vector` is
  in-memory only and cannot be reconstructed from a search record (by design:
  no trajectories/vectors persisted).
- Determinism remains same-runtime/same-environment (inherited; not universal
  cross-platform bitwise equivalence).

---

## 12. What Task 2.1 (next, NOT started) could build

Nothing planned or started. Natural candidates per `IMPLEMENTATION_PLAN.md`:
plugin/adapter registry (extensible `ComponentRegistry` with external adapters
and capability discovery), generalized world composition beyond `compose()`,
deterministic replay, or exposing Experiments A/B observables for the same
diversity-aware layer — all remain **not started**.