# Task 2.4 Build Stages 4+5 — Checkpoint

**Status: COMPLETE (validated).** Cross-composition ranking + diversity
frontier (Stage 4) and the discovery CLI + figure artifact (Stage 5) are
implemented, tested, and regressed. Task 2.5 has NOT been started.

## What Stage 4 adds

`src/sim_alchemist/core/composition_analysis.py` is a new **generic core**
module (no experiment imports, no matplotlib, no persistence, no simulation)
that ANALYSES the Stage 3 discovery result. It **reuses** the existing,
unchanged Task 1.8/1.9 primitives — `rank_by_profile`,
`select_diverse_frontier`, `behavior_distance`,
`compute_frontier_diagnostics` — and never re-implements a ranking or a
diversity algorithm.

- `CommonBehaviorFeatures` / `CompositionFeaturedRun` — the per-composition
  common-observable feature surface (`isolation` lives on the frontier, and
  `behavior_distance` is called with `BehaviorFeatures(units={})`).
- `common_observable_vocabulary(result)` — sorted names available in **every**
  evaluated `CommonObservableSet` (verified: `final_field_mean`,
  `final_field_std`, `field_entropy`). Missing features stay explicit
  (`available=False` / `None`), never fabricated.
- `rank_compositions(result, profile, features=None)` — deterministic
  weighted rank via `rank_by_profile`; pool min-max normalization per
  feature; constant (zero-range) feature ⇒ 0.0 contribution; ties by run id
  ascending; rows carry raw + normalized values + per-feature contributions +
  explanation with direction and source id.
- `select_frontier(result, profile, ranking=None, *, q=1, d=1, beam=len)`
  — greedy diversity-aware selection via `select_diverse_frontier` over
  pool-normalized feature vectors inside **local min-max isolation**, with a
  `CompositionFrontier` (members + `FrontierDiagnostics` + `isolation` map).
- `composition_analysis_id_of(...)` — deterministic 24-hex content-addressed
  id over discovery_id + profile + selection config (no transient data).
- `CompositionAnalyst` (analysis-only facade), `CompositionAnalysisResult`
  (canonical `as_dict(canonical=True)` for replay-identical hashing),
  `CompositionAnalysisTiming`.

Stage 4 is analysis-only: it performs no world execution, writes nothing to
the lineage store (run_count is untouched), and never mutates its inputs.

## What Stage 5 adds

- `experiments/composition_discovery.py` — `composition_labels()`
  (composition_id → A/B/C) and `make_diversity_scatter(analyses, out_path,
  labels, dpi=130)`: one matplotlib/Agg panel per profile, x = quality score,
  y = isolation, frontier members starred.
- `run_composition_discovery.py` — developer CLI:
  `uv run python run_composition_discovery.py [--steps N] [--seed N]
  [--db PATH] [--quality-weight Q] [--diversity-weight D] [--beam-width B]
  [--profile {all,a,b}] [--no-figure]`. Defaults to the canonical 160-step
  run, both profiles, and writes `figures/discovery_quality_diversity.png`.

## Validation status

- 478 fast tests pass (incl. 34 Stage 4 + 9 Stage 5 fast tests); 12 slow
  tests pass (incl. the new canonical Stage 4 + Stage 5 slow tests).
- `run_validation.py` A–G and `run_stability.py` S1–S6 pass unchanged.
- `ruff check .` clean; `pyright` 0 errors.
- Stage 3/Stage 4 guard `CORE_COMMIT_HASHES` re-pinned (documented sanction).
- Deterministic delivery: two CLI runs are byte-identical apart from the
  wall-clock `TIMING`/persist lines; `CompositionAnalyst` replay is
  canonical-identical (`replay_equal=True`, same analysis ids).

## Remaining

Final report + this checkpoint's promotion into `PROJECT_STATE.md`,
`IMPLEMENTATION_PLAN.md`, `AGENTS.md`.