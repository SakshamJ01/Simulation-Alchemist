# Task 2.9 Design — Persistent Cross-Session Behavioral Archive (PLAN-ONLY)

Status: PLAN-ONLY. No source/test/dependency/world changes started. No implementation.

## 1. Verified Starting State
- Task 2.6 complete; Task 2.7 complete (Stage 1/2/3 verified); Task 2.8 complete (design + build + verification).
- All 38 adaptive tests pass; validation A-G; stability S1-S6.
- Only C has declared MutationSpace (3 dimensions).

## 2. Actual Architecture Gap
Adaptive exploration session results are durable (lineage Stage 3), but adaptive comparison archive is in-memory only. No durable query/replay of comparison identity / ranking / frontier without rerunning analysis pipeline.

## 3. Candidate Directions Evaluated
A. Persistent adaptive comparison archive + optional feature-linkage (RECOMMENDED)
B. Temporal multi-pass divergence tracking (deferred — needs deeper temporal stability)
C. Persistent behavioral snapshot query (subset of A)

## 4. Recommended Direction — Persistent Adaptive Comparison Archive
Smallest high-value addition: additive archive table + optional read-only feature link. No execution; no optimization; reuses existing LineageStore / AdaptiveDiscoveryAnalyst / behavior primitives.

## 5. Scientific Use Case
Compare adaptive profile exploration results (e.g., default vs quality on Experiment C) to observe divergent frontier / diversity without rerunning simulation.

## 6. Core / Experiment / Tool Ownership
- Core (lineage): optional adaptive_comparison_archive table + methods
- Tool (CLI): optional archive read/write when enabled
- Experiment: none required

## 7. Identity / Lineage
- Reuse adaptive_exploration_id; reuse comparison_id (content-addressed 24-hex from AdaptiveDiscoveryAnalyst).
- No new database; additive schema; migration-safe (CREATE IF NOT EXISTS); idempotent (INSERT OR REPLACE).

## 8. Data Flow
AdaptiveExplorationResult (existing) -> AdaptiveDiscoveryAnalyst.compare_adaptive_discovery -> AdaptiveComparisonResult -> (optional) LineageStore.record_adaptive_comparison -> replay by identity.

## 9. Scaling / Performance
- Archive insert O(1) per comparison (<1 KB row)
- Feature linkage O(n) bounded by pass budget (typically < 10)
- No execution cost when disabled

## 10. Failure Modes / Mitigation
- Missing durable feature data: comparison explanation states requirement clearly; does not fabricate lexical ranking.
- Migration failure: IF NOT EXISTS safe; old DB continues.
- Duplicate identity: idempotent overwrite by comparison_id.

## 11. Test Strategy (future Stage 2 build)
- Schema creation / migration test
- Record / replay / idempotency / round-trip
- Real session load + comparison + archive + replay
- Existing regression preserved

## 12. Non-Goals
- No optimization / ML / GA / Bayesian / RL / plugin / distributed
- No automatic parameter synthesis
- No universal metric equivalence
- No new experiment / dependency

## 13. Acceptance Criteria (future)
- [ ] Archive table present (additive, migration-safe)
- [ ] Round-trip replay verified with real session
- [ ] No synthetic fabrication for comparison
- [ ] Task 3.0 NOT started

## 14. Context Recovery / Checkpoint
Read: PROJECT_STATE.md (Task 2.8 complete / Task 2.9 design) + TASK_2.9_DESIGN.md + git log --oneline -5.
