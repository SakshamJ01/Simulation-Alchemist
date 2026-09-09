# Task 2.4 Build Stages 4+5 — Final Report

## Scope

Bounded vertical slice completing Task 2.4: **Stage 4** (cross-composition
ranking + diversity-aware discovery frontier, analysis-only) and **Stage 5**
(developer CLI + one matplotlib quality-vs-diversity artifact). No new world
execution beyond the Stage 1–3 baselines; no lineage writes; Task 2.5 NOT
started.

## Common-observable vocabulary (genuinely common only)

Verified 3 names, available in **every** evaluated composition
(chemomech/field-guided/network): `final_field_mean`, `final_field_std`,
`field_entropy`. The 16-name Stage 3 union is the envelope; only this triple
may enter ranking/variance/diversity vectors. Missing stays explicit
(`available=False`/`None`), never fabricated.

## Normalization rule

- **Pool-level min-max per feature**, computed over the evaluated pool, used
  for BOTH ranking contributions AND diversity-feature vectors.
- Constant (zero-range) feature ⇒ normalized 0.0 and zero contribution.
- Raw numbers preserved verbatim alongside normalized values.
- Ties in ranking broken by run id ascending (Task 1.7 contract).
- Isolation (scatter y) = min normalized Euclidean distance to any other
  pool member, computed under a **local pool-level min-max**
  (`_min_max_vectors`) and passed to `behavior_distance` with
  `vector_a/vector_b` and `BehaviorFeatures(units={})`.
- Composition identity is **never** a distance term; distances use the common
  triple only.

## Profiles (bare common-observable feature keys)

- **Profile A `structural_quality`**: `final_field_std:max:1.0`,
  `field_entropy:min:0.5`, `final_field_mean:max:0.25`.
- **Profile B `field_level`**: `final_field_mean:max:1.0`,
  `final_field_std:min:0.5`, `field_entropy:min:0.25`.

## Canonical results (seed 0, 160 macro-steps)

Discovery id `91a72c708d07d66b5926edec`; 3 EXECUTABLE (A, B, C).

**Profile A** — analysis id `364cb0aadb3b35a02915ff54`
| rank | id | label | score |
|------|----|-------|-------|
| 1 | 3a3768e223681a1734caa32b | C | 1.75 |
| 2 | ccf9b796f63322e7e526363b | A | 0.413028 |
| 3 | 7bdf3877c4b43c0cf792997e | B | 0.267571 |

Frontier (q=1, d=1, beam=3): C [1.75, highest_quality], A [0.413028,
div 1.42487], B [0.267571, div 0.946635]; mean pairwise distance 1.265.

**Profile B** — analysis id `91fef3e4fadcd0bf59525e8d`
| rank | id | label | score |
|------|----|-------|-------|
| 1 | 3a3768e223681a1734caa32b | C | 1.25 |
| 2 | 7bdf3877c4b43c0cf792997e | B | 0.854591 |
| 3 | ccf9b796f63322e7e526363b | A | 0.706514 |

Frontier (q=1, d=1, beam=3): C [1.25, highest_quality], B [0.854591,
div 1.42388], A [0.706514, div 0.946635]; mean pairwise distance 1.265.

Cross-profile interior consistency: isolation map (A 0.946635, B 1.42388,
C 1.42388) is identical across both analyses, and both profiles' frontiers
keep the same three compositions with C highest by combined score — the
frontiers differ only in the secondary ordering, exactly as expected under
the differing profile weights.

## Determinism / replay

`CompositionAnalyst` replay of the canonical discovery is
canonical-identical: `replay_equal=True`, `run_count_after_replay=3`
(no extra runs written). Two independent CLI invocations are byte-identical
apart from the wall-clock `TIMING` lines and the persistence note.

## CLI + figure

```
uv run python run_composition_discovery.py
```
Default: canonical 160-step run, profiles A+B, writes
`figures/discovery_quality_diversity.png` (1404×598 PNG, 57809 bytes; one
Agg panel per profile, x=quality score, y=isolation, frontier starred).
Supported flags: `--steps`, `--seed`, `--db`, `--quality-weight`,
`--diversity-weight`, `--beam-width`, `--profile {all,a,b}`, `--no-figure`.

## Performance (canonical, wall-clock)

- Discovery: evaluation 59.69 s, observation 0.0003 s, per-composition
  19.90 s.
- Profile A analysis: extraction 0.000031 s, ranking 0.00017 s, frontier
  0.00018 s, total 0.00038 s.
- Profile B analysis: extraction 0.000020 s, ranking 0.000086 s, frontier
  0.000075 s, total 0.00018 s.

Stage 4 analysis is effectively free relative to the Stage 1–3 evaluation.

## Test counts

- Fast suite: **478 passed** (~349 s), 12 deselected.
- Slow suite: **12 passed** (~621 s) — includes the new canonical Stage 4
  (exact triple vocabulary, replay-canonical identical, run_count stays 3)
  and the canonical discovery-figure tests.
- Guard `CORE_COMMIT_HASHES` re-pinned (documented Stage 4 sanction):
  added `composition_analysis.py`, refreshed `__init__.py`.
- `run_validation.py` A–G PASS; `run_stability.py` S1–S6 PASS; `ruff`
  clean; `pyright` 0 errors.

## Files changed/added

- `src/sim_alchemist/core/composition_analysis.py` (new, Stage 4 core)
- `src/sim_alchemist/core/__init__.py` (Stage 4 API re-exports)
- `tests/test_field_guided_movers.py` (guard re-pin + sanction comment)
- `experiments/composition_discovery.py` (new, viz + labels)
- `run_composition_discovery.py` (new, developer CLI)
- `tests/test_composition_analysis_stage4.py` (new, 34 fast + 1 slow)
- `tests/test_composition_discovery_cli_stage5.py` (new, 9 fast + 1 slow)
- `figures/discovery_quality_diversity.png` (new, artifact)
- `TASK_2.4_STAGE4_5_CHECKPOINT.md` / `TASK_2.4_STAGE4_5_REPORT.md`
- `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` (status updated)

Unchanged/reused: `behavior.py`, `search.py`, `composition_search.py`,
`observables.py`, `templates.py`, `catalog.py`, all experiment code.

## Next

Task 2.5 NOT started. The common-observable vocabulary identifies C (the
adaptive network) as the highest-quality composition under both profiles,
with a genuinely diverse 3-member frontier spanning all three subsystems —
a clean, well-tested foundation for whatever discovery/visualization phase
follows.