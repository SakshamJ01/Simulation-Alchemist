# Task 2.9 Stage 3 — Authoritative Feature Linkage + Read-Only Archive Tooling + Final Verification Report

Status: **COMPLETE** (Stage 3 acceptance met — total Task 2.9 complete). Task 3.0 NOT started. No commit made.

## 1. Starting state

- HEAD = `2e15f6c` on `master` (tracks `origin/master`, https://github.com/SakshamJ01/Simulation-Alchemist.git): **Stage 2 is committed** (`2e15f6c` "feat: add adaptive comparison archive querying and audit"). `git status` clean of tracked modifications; only untracked scratch files present.
- This reconciles the previous-session note that "no commit was made": the user committed Stage 2 between sessions; the working tree at Stage 3 start exactly matched `2e15f6c`.
- Stage 2 delivered the read-only archive-consumption layer on `LineageStore` (`iter_adaptive_comparisons` / `count_adaptive_comparisons` / `find_adaptive_comparisons` / `verify_adaptive_comparison`) with explicit feature-linkage deferral.
- Stage 2 end-state baselines: full pytest 677 passed / 1 failed (pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`, proven on pristine HEAD); full ruff 118 (HEAD 110 + scratch delta); full pyright 15 (identical set on pristine HEAD); validation A–G PASS; stability S1–S6 PASS.

## 2. Stage 2 reconciliation

The mandatory re-context gate ran before any Stage 3 work:

- `git status` clean of tracked changes; `git log` confirmed `2e15f6c` (Stage 2 achieved); `git branch -vv` / `git remote -v` confirmed `master` tracks `origin/master`.
- Authoritative docs re-read: `PROJECT_STATE.md`, `TASK_2.9_DESIGN.md`, `TASK_2.9_STAGE2_REPORT.md`, `AGENTS.md`.
- Stage 1 + Stage 2 suites re-run: **28/28 passed** before any Stage 3 change.

## 3. Evidence audit — is there authoritative durable feature data? (hard evidence)

The Stage 3 gate required an audit of the *real repository state* before any feature-linkage decision (data, not claims). Findings:

- **`runs.feature_snapshot` exists but is never populated for adaptive passes.** The Task 1.8 per-run snapshot column is present in the schema, but no adaptive-session/pass execution path ever records a `RunRecord` with a non-`None` feature snapshot. `run_adaptive_exploration.py` (the only adaptive-exploration runner demo) never calls `record_run`/`record_exploration_session` at all — it only executes and prints.
- **Pass run ids are content-addressed adaptive-run identities, not `runs.run_id`.** `adaptive_exploration_sessions.pass_adaptive_run_ids` store `adaptive_run_id_of(actions, seed, budget)` values (`adaptive_sweep.py` → 24-hex content id). There is no durable mapping and no code path from a pass id to a `runs` row (verified by grep across `adaptive_exploration.py`, `adaptive_exploration_runner.py`, `adaptive_sweep.py`, `run_adaptive_exploration.py`, `run_adaptive_discovery.py`).
- **Real repository proof data substantiates the schema audit** (copy of `task29_real_proof.db`, complete row dump): `runs` has exactly one row `real00000000000000000001` with `feature_snapshot = NULL`; `behavior_analyses` has **0 rows**; `adaptive_exploration_sessions` has exactly `2f41779e1947f870b32140e3` whose `pass_adaptive_run_ids = ["1611ed456112f8d3af7c8678"]` — and `1611ed456112f8d3af7c8678` does **not** match the sole `runs.run_id`. The archived comparison `e7ca46439e8f874408a9e3c0` is itself feature-less (its stored digest attests `diagnostics.feature_vectors_available: false`).
- **An explicitly-absent session key**: the real archive references two source sessions; `c592521de654e7c165d8ec15` is not present in `adaptive_exploration_sessions` at all.

**Conclusion — OUTCOME B:** authoritative durable feature data does **not** exist. No feature persistence is invented; the archive preserves explicit *unavailable* semantics and gains tooling that explains *why*, grounded in the durable records themselves.

## 4. Feature-linkage decision (OUTCOME B) and representation

- The Stage 2 audit's `feature_linkage.available` / `resolvable_from_archive: False` / `reason` semantics are **preserved unchanged** (`verify_adaptive_comparison` outputs byte-identical for the real row).
- Stage 3 adds one additive, read-only, evidence-grounded resolver — `LineageStore.feature_linkage_of(comparison_id)` — which walks the archive row's *authoritative source references* into the durable records and reports exactly what exists:
  - each source session id is looked up in `adaptive_exploration_sessions` (`session_present`);
  - each session's `pass_adaptive_run_ids` are looked up in `runs` (`run_present`, `feature_snapshot_present`);
  - a pass run id whose `RunRecord.feature_snapshot` is non-`None` is an authoritative durable feature source; its own **`runs.run_id` is reused** as the resolved identity (never a new `feature_archive_id` / `features_snapshot_id`).
- No feature values are fabricated, re-derived, normalized, or inferred; only existence + identity are reported. `available == resolvable` and equals `len(resolved_feature_sources) > 0`. For the real row this resolves `available=False` with hard per-session evidence and an exact reason.

## 5. Schema

- **No schema change**: no new table, no new column, no new index, no migration, no `user_version` bump. Stage 3 is purely additive API + tooling on the existing Stage 1 archive DDL. Stage 1's `PRE_29_SCHEMA`-based test still passes with the Stage 1 table (column list verified unchanged).

## 6. Core API as-built (additive, `src/sim_alchemist/core/lineage.py`)

| Method | Signature → result | Notes |
|--------|-------------------|-------|
| `feature_linkage_of` | `(comparison_id: str) -> dict[str, Any] \| None` | Resolution of authoritative feature evidence for one archived comparison. Unknown id → `None`. Returns `{adaptive_comparison_id, available, resolvable, source_ids, resolved_feature_sources, evidence, reason}`. `source_ids` = the archive row's session refs (sorted); `evidence` = per-session `{session_id, session_present}` + per-pass `{pass_run_id, run_present, feature_snapshot_present}`; `resolved_feature_sources` = unique authoritative `runs.run_id`s carrying a real snapshot; `reason` states precisely why none/some resolved. SELECT-only (AST-verified). |

Complexity: O(1) archive-row PK lookup + O(sessions × passes) evidence resolution over the small durable linkage records, all pure reads.

## 7. CLI as-built (`run_adaptive_comparison_archive.py`, repo-root, argparse)

Strict real-mode, read-only archive tooling. Every command only calls the existing `LineageStore` archive APIs (no ranking/frontier/diversity reimplementation, no own sorting beyond the API's canonical order, no analysis engine).

| Command | Behavior |
|---------|----------|
| `<db> list` | canonical-order catalog lines + `count:`; optional `--profile` / `--session-id` exact filters via `find_adaptive_comparisons`. |
| `<db> get <id>` | one decoded record + deterministic `sort_keys` JSON; gated on the audit verdict. |
| `<db> find --profile P [--session-id S]` | exact-filtered rows + `matches: N`. |
| `<db> verify <id>` | full audit/replay output: verdict, `identity_recomputable: False`, feature_linkage summary, integrity JSON, full JSON. |
| `<db> link <id>` | the evidence-grounded feature-resolution explanation (delegates to `feature_linkage_of`). |

Every command ends with `[ARCHIVE-READ-ONLY] total_changes unchanged: N`.

## 8. Error semantics + exit codes (unknown ≠ corrupt ≠ missing)

| Exit | Meaning | Notes |
|------|---------|-------|
| 0 | success | |
| 10 | invalid filter | empty `--profile` / `--session-id`. |
| 20 | missing database | file does not exist. |
| 30 | unknown comparison | `get` / `verify` / `link` on an id with no archive row. |
| 40 | corrupt archived row | verdict `CORRUPT` (gate via `verify_adaptive_comparison`; single-row commands refuse to decode a row the audit already flags). Corruption is reported, never silently repaired; raw row re-fetch after CLI shows the tampered value still intact. |
| 50 | write / schema violation | database open would require a migration-write (schema missing required archive tables/columns) — refused; or a read command modified the DB. |

Missing features are **not** an error: `link` reports `available: False` with evidence + reason (exit 0). Missing session ids are reported in evidence, never collapsed into "not found".

## 9. Read-only guarantees (three independent layers)

1. **True `mode=ro` pre-flight** — before the store opens, the CLI validates the archive schema with `sqlite3.connect("file:...?mode=ro")`. A database missing `adaptive_comparison_archive` / `adaptive_exploration_sessions` / `runs` (or the required columns) is refused with exit 50 *without ever opening a write-capable connection*, so no `CREATE`/`ALTER` migration ever runs. Proven by test: a schema-less DB yields exit 50 and still contains only the original table afterwards.
2. **SELECT-only API bodies** — `feature_linkage_of` (and all Stage 2 readers) contain no `INSERT`/`UPDATE`/`DELETE`/`OR REPLACE`/`.commit()` tokens (AST-verified).
3. **`total_changes` proof** — the CLI prints and asserts the sqlite write counter is unchanged after every command (verified on the real copy: 0 → 0).

## 10. Real repository proof

On a **copy** of the genuine real-data DB (`task29_real_proof.db`; the source is never opened for writing):

- API on `e7ca46439e8f874408a9e3c0`: `get` OK (status `VALID`); `verify` verdict `OK`, `identity_recomputable` `False`, `feature_linkage.available` `False`; `feature_linkage_of` → `available=False`, `resolvable=False`, `resolved_feature_sources=[]`, evidence = [{`2f41779e1947f870b32140e3`: present, pass run `1611ed456112f8d3af7c8678` = `run_present:false`}, {`c592521de654e7c165d8ec15`: `session_present:false`}], reason = "some archived source sessions are absent from adaptive_exploration_sessions and no durable feature chain resolves". `total_changes` 0 after the whole session.
- CLI on the copy: `list` → `[ARCHIVE-LIST] e7ca46439e8f874408a9e3c0 default VALID ... count: 1`; `get`/`find --profile default`/`verify`/`link` all exit 0 with deterministic output and the read-only proof line.
- **No second real record**: the CLI never writes; row counts (1 archive, 1 session, 1 run) unchanged; profile set unchanged (`default` only — no profiles fabricated).
- Identity reproduction (Stage 2 §11) still holds: the real comparison id recomputes to `e7ca46439e8f874408a9e3c0` from the real sessions + profile `default` + empty feature-key set.

## 11. Performance

Measured on the real one-row archive copy (200 iterations each; mean per op):

| Op | ms/op |
|----|-------|
| `get_adaptive_comparison` | 0.0305 |
| `verify_adaptive_comparison` | 0.0330 |
| `feature_linkage_of` | 0.1038 |
| `count_adaptive_comparisons` | 0.0233 |
| `iter_adaptive_comparisons` (full) | 0.0295 |
| `find_adaptive_comparisons` (profile) | 0.0272 |

CLI process (cold start + `list` on the real archive): 219.6 ms. `feature_linkage_of` is O(1) + O(sessions × passes) read-only resolution; the archive cardinality and per-comparison linkage sets are small by design.

## 12. Backward compatibility

- Pre-2.9 stores (`PRE_29_SCHEMA`) still open, gain the archive table on open (migration preserved), and the Stage 3 resolver reads them (tested).
- Old archive rows (any schema era) load and resolve identically; the Stage 2 `verify` output shape is unchanged (real row byte-compared).
- **Guard re-baseline (sanctioned, documented policy old→new→reason):** `lineage.py` in `test_field_guided_movers.py::CORE_COMMIT_HASHES` re-pinned 41A18556AE571607AE62DEFAF9E77D23CACD5CCAA766D9941F1D3F6E90023260 → 1B71EAF6DD5A098BC0334647119510093334AE8F79179FDB431B75A89A04675F because Stage 3 additively adds `feature_linkage_of`. `test_network_morphogenesis` reuses the same dict (one source of truth) and carries the documented reason in its header comment.
- No behavior change to any existing `LineageStore` method; no new dependency; no `pyproject.toml` / `uv.lock` / `experiments/*` / `worlds/*` changes.

## 13. Tests (`tests/test_adaptive_comparison_archive_stage3.py`, 18 new)

Coverage categories A–T for OUTCOME B plus the anti-false-pass guarantees:

- **A** legacy + archive-only rows readable with explicit unavailable linkage (incl. `PRE_29_SCHEMA` store).
- **B** *available* path: sessions + runs with a real `feature_snapshot` resolve `available=True` through the actual authoritative `runs.run_id`; deterministic across calls.
- **C** unavailable stays unavailable: sessions present but no run chain; partially-missing sessions reported explicitly.
- **D** no fabrication: unavailable → empty resolved sources + absent feature-value keys; availability never faked by a dangling feature row.
- **E** read-only + no source mutation: full read sweep leaves `runs`, sessions, archive, and `total_changes` byte-identical; `feature_linkage_of` body is SELECT-only (AST scan).
- **G/H/I** CLI: real-data path exit 0 + expected output; unknown (30) ≠ corrupt (40) with no collapse; missing DB (20) distinct from legacy/schema refusal (50, DB left untouched); invalid filter (10); list keeps the API's canonical order; filters exact; repeated invocation byte-identical.
- **J** purity: CLI source imports no analysis/execution modules and contains no ranking/frontier/diversity tokens; `lineage.py` retains its import-purity (extended scan).

**10 anti-false-pass correspondences** (1) legacy rows decode without linkage fields; (2) unavailable resolver never fabricates sources/values; (3) real-row resolution stays unavailable; (4) available resolution provably traverses an actual authoritative `runs.run_id`; (5) CLI list order = store canonical order (no re-sort); (6) CLI delegates to `feature_linkage_of` / `verify`, no reimplemented analysis; (7) repeated reads → identical results; (8) zero `total_changes` on all read paths; (9) corrupt row remains corrupt after CLI/verify (raw value re-fetched unchanged); (10) old pre-2.9 archive rows remain fully readable.

## 14. Regression (full order executed)

1. Stage 1 + 2 + 3 suites — **46 passed**. 2. Guard suites (`test_field_guided_movers.py`, `test_network_morphogenesis.py`) — **24 passed** after re-pin. 3. Full suite — **695 passed / 1 failed** = 677 Stage-2 baseline + 18 new; sole failure identical pre-existing `test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path` (Task 2.5 CLI staleness, unrelated; proven on pristine HEAD in earlier stages). This was run as fast suite (682 passed / 1 failed / 13 slow deselected) + slow canonical suite (13/13 passed, incl. 160-step network, bitwise facade, real repository sweep). 4. Focused ruff on all Task 2.9 changed files — 0. 5. Full ruff — 118 (identical pre-existing baseline; zero findings in Task 2.9 files). 6. Focused pyright on Task 2.9 files — 0. 7. Full pyright — 15 (identical pre-existing set on pristine HEAD; the two transient errors in the new test file were fixed). 8. `run_validation.py` A–G — **ALL PASSED**. 9. `run_stability.py` S1–S6 — **ALL PASSED**.

## 15. Guard safety

`lineage.py` was the only guarded core file touched, and only additively (`feature_linkage_of`). The stage guard re-pin is amply documented in both guard files with old→new→reason; `test_mutation_lineage.py` untouched; the rest of `CORE_COMMIT_HASHES` unchanged. No scratch or untracked file was modified or staged.

## 16. Limitations (preserved, not hidden)

- Authoritative durable per-run feature vectors do not exist for adaptive passes (OUTCOME B). `feature_linkage_of` reports availability from real durable records and never manufactures a chain; `verify`'s `resolvable_from_archive` remains `False` by design.
- `identity_recomputable` remains `False` (compact-lineage policy; identity depends on un-stored pieces).
- Only one real profile (`default`) exists; no profiles are fabricated.
- CLI single-row commands gate on the audit verdict before decoding, so a corrupt row is sharply reported; `list`/`find` rely on the store iterators' decode and surface corruption distinctly (exit 40). All existing `LineageStore` read behaviors are unchanged.
- Archive reads are O(n) for iterate/find; O(1) for get/count/verify/link resolution.

## 17. Final Task 2.9 status

Task 2.9 is **complete**: Stage 1 (persistent one-row-per-comparison archive + focused repair + verification), Stage 2 (real archive consumption + deterministic replay/audit + explicit feature linkage), Stage 3 (outcome-B authoritative feature linkage with evidence-grounded resolution, strict read-only archive CLI, hard-evidence audit, final verification). **Task 3.0 is NOT started.** No commit made; all changes un-staged in the working tree.

## 18. Files changed (Stage 3)

- `src/sim_alchemist/core/lineage.py` — additive `feature_linkage_of` (guard re-baselined).
- `tests/test_adaptive_comparison_archive_stage3.py` — new (18 tests).
- `run_adaptive_comparison_archive.py` — new archive CLI.
- `tests/test_field_guided_movers.py`, `tests/test_network_morphogenesis.py` — guard hash re-pin + reason comment.
- `TASK_2.9_STAGE3_REPORT.md`, `PROJECT_STATE.md` — this report and state update.