# Task 2.9 Stage 2 — Real Archive Consumption + Deterministic Replay + Explicit Feature Linkage Report

Status: **COMPLETE** (Stage 2 acceptance met). Stage 3 / Task 3.0 NOT started. No commit made.

## 1. Starting state

- HEAD = `478157d` on `master` (tracks `origin/master`, https://github.com/SakshamJ01/Simulation-Alchemist.git): Stage 1 committed (`0d5fb5a` archive + `478157d` guard re-baseline). `git status` clean of tracked modifications; only untracked scratch files present.
- Stage 1 delivered one additive `adaptive_comparison_archive` table + index and `LineageStore.record_adaptive_comparison` / `get_adaptive_comparison` (idempotent compact digest; no trajectories / feature vectors). The real persisted entry lives in the Stage 1 proof DB: comparison `e7ca46439e8f874408a9e3c0` (sessions `2f41779e1947f870b32140e3`, `c592521de654e7c165d8ec15`, profile `default`, status `VALID`).
- Stage 1 tests: 9/9 pass. Validation A–G PASS; Stability S1–S6 PASS. Full-suite baseline: 658 passed / 1 failed (pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`, proven on pristine HEAD). Full pyright 15 errors (identical set on HEAD); full ruff 118 (HEAD 110 + untracked scratch delta).

## 2. Stage 1 reconciliation

Re-context gate executed before any Stage 2 work:

- `git status` was clean of tracked changes; `git log` confirmed `478157d` contains the three Stage 1 guard files (`test_field_guided_movers.py`, `test_network_morphogenesis.py`, `test_mutation_lineage.py`) and `0d5fb5a` the archive implementation.
- Authoritative docs re-read: `PROJECT_STATE.md`, `TASK_2.9_DESIGN.md`, `TASK_2.9_STAGE1_REPORT.md`, `TASK_2.8_STAGE2_REPORT` excerpt, `IMPLEMENTATION_PLAN.md`.
- The prior context's "Stage 1 guard files looked uncommitted" contradiction is resolved: they were committed in `478157d`; nothing to restore.

## 3. Exact capability chosen (smallest coherent consumption set)

The Stage 2 scope decision selected a **read-only consumption layer** as the smallest useful capability. It was *not* extended with a CLI (determined not to be the smallest useful step) and *not* extended with durable feature-linkage (no authoritative data exists; see §7).

Delivered on `LineageStore`, all read-only, all deterministic, all in `src/sim_alchemist/core/lineage.py`:

- Deterministic listing / counting of the archived universe.
- Exact lookups and exact profile/session filtering.
- One audit/replay entry that verifies a stored comparison **from the archive row alone**.
- Explicit, honest not-missing semantics (unknown ids → `None`; `find` with no matches → `[]`; absent feature state reported as unavailable, never fabricated).

## 4. APIs (as-built)

| Method | Signature → result | Notes |
|--------|-------------------|-------|
| `iter_adaptive_comparisons` | `() -> Iterator[dict[str, Any]]` | `SELECT * ... ORDER BY adaptive_comparison_id` (canonical ascending; never raw row order). Yields decoded `{adaptive_comparison_id, session_ids, profile_text, result_digest, status, created_at}`. |
| `count_adaptive_comparisons` | `() -> int` | `SELECT COUNT(*)`. |
| `find_adaptive_comparisons` | `(*, profile: str \| None = None, session_id: str \| None = None) -> list[dict[str, Any]]` | Iterates in canonical order, Python-side exact filters: stored `profile_text` matched verbatim (no normalization); `session_id` by membership in the stored (decoded) session list; no matches → `[]`. |
| `verify_adaptive_comparison` | `(comparison_id: str) -> dict[str, Any] \| None` | Audit/replay of one comparison from the stored row alone; unknown id → `None`. See §6. |

Supporting refactor (no contract change): `get_adaptive_comparison` now delegates row decoding to `_adaptive_comparison_from_row`, the same static helper used by `iter_adaptive_comparisons`. Output keys identical to Stage 1.

## 5. Query model

- Canonical order: `adaptive_comparison_id` ascending. Verified by a test that deliberately inserts rows in reversed physical (rowid) order and proves (a) a raw table scan returns the reversed order while (b) the API returns canonical order.
- Filtering is exact and local: `profile=` compares the stored `profile_text` verbatim; `session_id=` tests membership of the decoded session list. There is no fuzzy matching, no normalization, no inference.
- Not-found is explicit: `get_adaptive_comparison` / `verify_adaptive_comparison` → `None`; `find` → `[]`; `count` → `0`.
- All query paths are pure reads: SELECT-only, tested by an AST source scan (no `INSERT`/`UPDATE`/`DELETE`/`OR REPLACE` tokens in the read method bodies), a write-spy test (a raising spy on `record_adaptive_comparison` never fires), and `sqlite3.Connection.total_changes` equality before/after.

## 6. Replay / audit semantics (`verify_adaptive_comparison`)

One comparison is replayed from its single archive row (never re-executed, never re-analyzed, never re-ranked). Every check derives only from the stored row:

- `adaptive_comparison_id_well_formed` — 24-hex content address.
- `session_ids_well_formed` — non-empty list of unique non-empty strings.
- `session_ids_sorted` — canonical sorted order preserved.
- `result_digest_valid` — the digest column survives JSON decoding as a dict.
- `result_digest_well_formed` — the documented shape exists with correct types: `ranked_order`, `frontend_ids`, `diagnostics`, `explanation`.
- `ranked_frontier_within_sessions` — every ranked/frontier id is one of the archived source sessions.
- `profile_well_formed` — `NULL` or non-empty string; `status_well_formed` / `created_at_well_formed` — non-empty strings.
- `consistent` — conjunction; `verdict` ∈ {`OK`, `CORRUPT`}.

**Corruption detection never raises and never repairs.** JSON payloads that fail decoding, a digest referencing unknown sessions, reversed session order, `NULL` digest, or dangling structure each produce `verdict == "CORRUPT"` with the failing flag, proven by tests that re-fetch the raw row after verifying (bit-for-bit unchanged, `total_changes` unchanged).

Result shape (top level): `adaptive_comparison_id`, `session_ids`, `profile`, `status`, `created_at`, `result_digest`, `feature_linkage {available, resolvable_from_archive, reason}`, `identity_recomputable: False` + `identity_recomputable_reason`, `integrity {...}`, `verdict`.

## 7. Feature-linkage decision

Durable feature linkage is **explicitly deferred** (declared in the result, not silently absent):

- Evidence gathered: the exploration-session row stores only `pass_adaptive_run_ids` (reviewed schema); the archive stores only the compact digest; the real archived comparison (`e7ca46439e8f874408a9e3c0`) was feature-less. No authoritative durable record links sessions → feature vectors, so a "resolvable" feature row cannot truthfully be produced.
- `verify_adaptive_comparison` therefore returns `feature_linkage.available` = whether the **stored digest's own `diagnostics.feature_vectors_available` is `True`** (derived, never re-derived, never fabricated) and `resolvable_from_archive` = always `False`, with the exact reason: the archive persists no feature-snapshot reference.
- A real proof likewise returns `available: False` (the genuine digest has no feature use) — consistent with the Stage 1 honest missing-data statement.

## 8. Missing-data semantics

- Unknown ids: `None` (by design, matching `get_adaptive_comparison`). An in-memory store with no archive rows iterates empty / counts 0 / finds `[]`.
- Corrupt rows are reported by the audit API, not hidden and not repaired; read-facing retrieval APIs keep the Stage 1 well-formed-data assumption (identical to the existing `LineageStore` sweep/search iterators).

## 9. Real repository proof

Performed on a **copy** of the Stage 1 real proof DB (`C:\Users\Saksham\AppData\Local\Temp\opencode\task29_real_proof.db` → temp `task29_stage2_proof.db`; original untouched), the genuine persisted Stage 1 archive entry `e7ca46439e8f874408a9e3c0`:

- `get_adaptive_comparison` → `status == "VALID"`, sessions equal the real pair sorted.
- `iter_adaptive_comparisons` / `count_adaptive_comparisons` → exactly 1 row.
- `find_adaptive_comparisons(profile="default")` and `find_adaptive_comparisons(session_id="2f41779e1947f870b32140e3")` → exactly that comparison.
- `verify_adaptive_comparison` → `verdict == "OK"`, `identity_recomputable is False`, `feature_linkage.available is False`, `resolvable_from_archive is False`.
- `total_changes` before == after (read-only proof). Temp copy removed afterwards.

## 10. No execution

`verify_adaptive_comparison` and all Stage 2 query methods contain no `.step(`, no `compose(`, no `SweepRunner`/analyst references, no analysis/ranking/frontier imports — enforced by an AST source scan mirroring the Stage 1 purity scan, plus the write-spy and `total_changes` proofs above.

## 11. No recomputation

- No comparison identity is recomputed at read time: `identity_recomputable` is always `False` with the exact reason (the Task 2.8 identity also depends on the pre-normalization profile payload and the feature-key set, neither durably stored).
- As an independent cross-check, the Stage 2 test suite reproduces the real comparison identity from the real session ids outside any simulation: sha256 of `{"feature_keys":[],"profile":"default","session_ids":["2f41779e1947f870b32140e3","c592521de654e7c165d8ec15"]}` (compact, sorted) == `e7ca46439e8f874408a9e3c0`.

## 12. Migration

- Schema and initialisation are unchanged from Stage 1: same `_SCHEMA` executescript, same `_migrate()`, `CREATE TABLE IF NOT EXISTS` additive.
- A Stage 2 test re-uses the genuine pre-2.9 schema (`PRE_29_SCHEMA`, imported from `test_adaptive_comparison_archive_stage1`) and asserts the Stage 1 schema SHAs are unchanged by Stage 2.
- Existing stores (including the real pre-2.9 `temp_lineage.db`) open, migrate, and stay structurally identical; the real proof DB object was never written.

## 13. Tests

New file `tests/test_adaptive_comparison_archive_stage2.py` — 19 tests:

- Canonical iteration despite deliberately non-canonical physical insertion (with a table-scan proof the physical order really is reversed).
- Empty store, distinct comparisons, unknown id → `None`.
- Exact `profile` / `session_id` filtering incl. combined filters and unknown-session → `[]`.
- Verify OK path: full integrity detail, feature-use derived-honestly from the stored digest, missing-feature honest state.
- Corruption detection with no repair: invalid-JSON digest, digest referencing an unknown session id, `NULL` digest, unsorted session ids — each → `CORRUPT`, row unchanged after audit.
- Repeated replay is read-only (`total_changes` unchanged) and deterministic.
- Read paths never record nor write (raising write-spy + run/sweep/search/behavior counters unchanged).
- Source scan: no forbidden modules imported; read method bodies contain no write or analysis tokens.
- Same-database coexistence of runs + archive + Stage 2 queries; pre-2.9 migration compatibility; Stage 1 schema preserved.
- Real-data identity reproduction (asserts the genuine comparison id `e7ca46439e8f874408a9e3c0`).

Focused gates after the robustness fix: Stage 1 9 + Stage 2 19 = 28 passed; guard tests (`test_field_guided_movers`, `test_network_morphogenesis`, `test_mutation_lineage`) pass.

## 14. Regression

- Focused ruff (4 Task 2.9 files) — All checks passed (0 errors); focused pyright (same files) — 0 errors.
- Full pytest `tests/` — **677 passed / 1 failed** (658 Stage-1 baseline + 19 new Stage 2 = 677; the single failure is the identical pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`, unrelated to Stage 2).
- Full ruff — 118 errors (identical pre-existing baseline: HEAD 110 + untracked scratch without Task 2.9 involvement); full pyright — 15 errors (identical pre-existing set on pristine HEAD). Zero Stage-2-file findings in either.
- Guard re-baseline (sanctioned, documented in `test_field_guided_movers.py::CORE_COMMIT_HASHES`): `lineage.py` hash re-pinned to `41A18556AE571607AE62DEFAF9E77D23CACD5CCAA766D9941F1D3F6E90023260` with the Task 2.9 Build Stage 2 comment (the final Stage 2 lineage.py state; the intermediate pin was superseded by the verification-robustness fix in §6). `test_network_morphogenesis` reuses the same dict; `test_mutation_lineage` unchanged in Stage 2.

## 15. Performance

Measured on the real one-row archive copy (2000 iterations each; mean per op):

| Op | ms/op |
|----|-------|
| `get_adaptive_comparison` | 0.031 |
| `iter_adaptive_comparisons` (full) | 0.038 |
| `count_adaptive_comparisons` | 0.025 |
| `find_adaptive_comparisons` | 0.030 |
| `verify_adaptive_comparison` | 0.034 |

Retrieval is O(1) per id (PK lookup); iteration/filtering is O(n) read-only over the archive. No new index was added — the archive cardinality is small by design (one compact row per comparison) and the reads are never repeated during execution. No execution cost incurred by the archived-consumption layer (Stage 1 §9).

## 16. Stage 3 boundary (NOT started)

- No new schema columns, no CLI, no archive readers/writers beyond `LineageStore`, no figures, no scheduling, no optimization, no new experiment, no new dependency, no world/YAML change.
- `git status` final check: only the allowed changes on `src/sim_alchemist/core/lineage.py`, `tests/test_adaptive_comparison_archive_stage2.py`, `tests/test_field_guided_movers.py`, this report, and `PROJECT_STATE.md`; no commit staged.
- Scratch/untracked files (`fix_*.py`, `lineage.db`, `sim_alchemist.db`, `temp_lineage.db`, `test_*quick.py`, etc.) untouched.

## 17. Limitations (preserved, not hidden)

- Durable feature vectors are not persisted, so `feature_linkage.resolvable_from_archive` remains `False` by design (corresponds to the design's §10 missing-durable-feature-data mitigation).
- `identity_recomputable` remains `False`: a full recomputation from archive-only state is impossible under the compact-lineage policy.
- Read APIs other than `verify_adaptive_comparison` assume well-formed rows (matching existing `LineageStore` iterators); corruption triage is the audit API's job.
- `find`/`iter` are O(n) scans (fine for the small archive); `count`/`get`/`verify` are O(1).