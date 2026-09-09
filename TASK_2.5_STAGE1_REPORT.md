# Task 2.5 Build Stage 1 — Composition-Specific Parameter-Space Binding + Result Model

## Status: COMPLETE

Stage 1 of Task 2.5 is the **data-model foundation** of the joint structural +
parametric discovery layer. It is deliberately model-only: it binds a
parameter space to each composition of the executable catalog, defines the
deterministic cross-composition sweep identity, and lays out the result model.
**No simulation executes, no `SweepRunner` runs, no lineage rows are written.**

---

## 1. Parameter-space ownership

Ownership follows the approved Task 2.5 design (model D — hybrid): the
**experiment layer owns the scientific parameter choices**, the **generic core
owns only opaque data types**. The generic core never names an experiment and
never interprets a parameter reference; which composition has which space and
what values are explored is a scientific fact.

The ownership registry mirrors the existing `repository_executors()`
composition→executor map: a parallel experiment-owned
`repository_parameter_spaces()` composition→`CompositionSpaceBinding` map.
Only **Experiment C** declares a real parameter space today.

## 2. `repository_parameter_spaces()`

Added in `experiments/catalog.py`:

```python
repository_parameter_spaces() -> dict[str, CompositionSpaceBinding]
```

Keyed by the content-addressed `template_composition_id` of each experiment
template (the same keys as `repository_executors()`). It returns exactly three
bindings, one per executable composition:

| Composition | space | ref | variant_count |
|-------------|-------|-----|---------------|
| A (morphogenesis) | `None` | `None` | — |
| B (field-guided movers) | `None` | `None` | — |
| C (adaptive network) | real `MutationSpace` | content ref | 27 (3·3·3) |

**Actual parameter spaces found (from repository definitions, not invented):**

- **C** has a legitimate space built from its declared `PARAMETER_SPECS`
  (`experiments/network_morphogenesis/experiment.py`):
  - `components.network.config.loss` (bounds 0…1)
  - `config.force_fmax` (bounds 0…10)
  - `config.source_amplitude` (bounds 0…1)
  A small `MutationSpace` uses modest exploration values strictly inside those
  declared bounds (`_network_parameter_space()` validates every value against
  the spec before building). No existing parameter value is changed.
- **A and B have no declared parameter space** and so bind `space=None`,
  `ref=None`. No space is fabricated for them.

`None` (`ref is None and space is None`) means *"this composition has no
registered parameter sweep space"* — never an error and never an empty space
(`MutationSpace` structurally rejects zero dimensions).

## 3. `parameter_space_ref`

`core/cross_sweep.py::parameter_space_ref(space) -> str` — a **deterministic,
opaque content reference** to a parameter-space definition: a 64-hex sha256 of
the canonical, dictionary-order-independent `MutationSpace.to_dict()`. Changing
the space changes the reference.

Per the guard-safe decision, the reference is carried on the experiment-owned
`CompositionSpaceBinding` and on the core result rows — **not** on the guarded
`CouplingTemplate` (avoids a sanctioned core re-baseline in Stage 1; re-evaluated
in Stage 2 if a template field proves necessary). The core treats the reference
as naming-only metadata and never interprets it.

## 4. `cross_split_sweep_id`

`core/cross_sweep.py::cross_split_sweep_id(spec) -> str` — a deterministic,
content-addressed 24-hex identity over a `CrossCompositionSweepSpec`:

```text
sha256( canonical JSON of {
    space_name,
    ordered bindings (composition_id, shape_id, ref, space dict),
    profile,
    seed,
    evaluation_config,
} )[:24]
```

It mirrors `composition_discovery_id_of` exactly (`sort_keys`,
`separators=(",",":")`, `allow_nan=False`, `.hexdigest()[:24]`). It contains
**no** timestamps, object reprs, random ids, or dictionary-insertion-order
dependence (the canonical `as_dict` builds ordered data; `sort_keys` on the
JSON makes dict order irrelevant). Identical canonical definition ⇒ identical
id; changing the universe, a binding, a space ref, the profile, the seed, or
the evaluation config ⇒ a different id. (Tests L–S prove each case.)

## 5. Result model

`core/cross_sweep.py` (experiment-free) defines:

- **`CompositionSpaceBinding`** — one composition and its own space.
  `composition_id`/`shape_id` identify the composition; `ref`/`space` the
  optional registered space; `has_space ⇔ ref is not None`. The three
  *executed* identities (`sweep_id`, `baseline_run_id`, `variant_run_ids`) are
  present as fields but left at their empty defaults — Stage 2 populates them.
- **`CrossCompositionSweepSpec`** — the complete ordered specification (space
  name, ordered bindings, profile, seed, evaluation config) with a canonical
  `as_dict(canonical=True)`.
- **`CrossCompositionSweepResult`** — `cross_split_sweep_id` + `spec` +
  `bindings` + `state` (`"planned"` | `"executed"`). **Stage 1 only ever
  constructs `planned`.** The model can later hold per-composition sweep/run
  identities without Stage 1 populating them, so a Stage-2 orchestrator can
  fill them without rework.
- **`CrossCompositionSweepRecord`** — an immutable **in-memory** compact
  metadata type (`cross_split_sweep_id`, `space_name`, `seed`, `bindings`) with
  no timestamps/trajectories. This is the intentional Stage 1/Stage 2 boundary:
  see §7.

## 6. Baseline semantics

The baseline is represented **explicitly and separately** from mutated
variants. Each `CompositionSpaceBinding` carries a dedicated
`baseline_run_id` (the composition's Task 2.4 baseline — a root control, never
a mutated variant) alongside `variant_run_ids` (the executed parameter variants
in generation order). Stage 1 does not execute or mint baselines; it simply
structurally guarantees that a baseline can never be a mutation, because it is
a distinct field, not an element of the variant list.

## 7. Lineage changes

**None in Stage 1.** Per the approved decision, `CrossCompositionSweepRecord`
is defined as an in-memory data type only; `lineage.py`, the `LineageStore`,
and the SQLite schema are **not** modified. Durable `cross_composition_sweeps`
persistence (a table + record/get/iter methods) is the **Stage 1/Stage 2
boundary**: Stage 2 adds it together with the orchestrator that actually
creates records (and the required sanctioned re-baseline of the guarded
`lineage.py` hash). No old-lineage records are affected; nothing is migrated.

## 8. Tests

New file `tests/test_cross_sweep_stage1.py` — **26 passed**, checks A–Y:

- **A–G** registry/ownership: covers all executables; valid space where defined
  (C); `None` where not (A/B); unknown composition → `KeyError`; deterministic
  output; no fake shared parameter dimensions (the only space present is the
  network one); experiment spaces stay outside the generic core (purity scan of
  `cross_sweep.py`).
- **H–K** `parameter_space_ref`: deterministic 64-hex; `None` ref works;
  survives serialization round-trip; changing a space changes its ref and the
  cross id.
- **L–S** `cross_split_sweep_id`: same spec ⇒ same id; each of seed / profile /
  evaluation-config / ordered-binding order / space-ref change ⇒ different id;
  no timestamps/random inputs; canonical serialization order-independent.
- **T–X** result model: construction + deterministic equality; serialization
  round-trip; baseline distinct from variants; `None` vs valid space distinct;
  identity hierarchy (`composition_id` / `cross_split_sweep_id` / `sweep_id` /
  `run_id`) kept distinct; in-memory `CrossCompositionSweepRecord`.
- **Y** no-execution architectural proof: scans the `cross_sweep.py` **imports**
  (not prose) for `SweepRunner`/`VariantRunner`/`LineageStore`/`AlchemistEngine`/
  `compose`/`record_*`/`Searcher` primitives and asserts the result is always
  `planned`.

## 9. No-execution proof

- The new core module performs no execution: it only imports the generic
  `MutationSpace` type; its import surface contains no execution/orchestration/
  lineage primitive (test Y).
- `repository_parameter_spaces()` only *declares* spaces; it never runs a
  sweep, never constructs an adapter, never executes a simulation, and never
  writes a lineage row.
- Every `CrossCompositionSweepResult` constructed in Stage 1 is `state="planned"`.
- No `LineageStore` is touched; no run ids are generated; no `world_hash` /
  `run_id_of` is called.

## 10. Limitations

- Stage 1 is model-only: no `CrossCompositionSweep` orchestrator, no
  per-composition sweep execution, no cross-composition ranking, no diversity
  frontier, no CLI/figure.
- A and B have no declared parameter space; they contribute only their
  baselines in any future sweep (Stage 2) and are never swept until an
  experiment declares a space.
- `CrossCompositionSweepRecord` is not yet durable (persistence deferred to
  Stage 2 as the documented boundary).
- `parameter_space_ref` is carried on the experiment binding + result rows, not
  on `CouplingTemplate`; if Stage 2 requires a template field, that is a
  separate, guarded-core change.
- Identity is deterministic content-addressing; no claim of parameter
  equivalence across experiments (only C declares a space).

## 11. Exact Stage 2 scope (NOT started)

Stage 2 will add, over this foundation, the **`CrossCompositionSweep`
orchestrator**:
- per-composition sweeps reusing the existing `SweepRunner` (baseline first,
  validated-before-execution, deterministic `run_id`), in canonical catalog
  order,
- `composition_id` stamping on recorded variant runs (via an optional
  `composition_id=` threaded into the core recording path),
- durable `cross_composition_sweeps` lineage persistence + the sanctioned
  re-baseline of guarded `lineage.py`,
- cross-composition common-observable comparison (reusing the Stage 3/4
  machinery) — ranking/frontier as later stages.

**Task 2.6 is not started.**

---

## Files changed (this stage)

- `src/sim_alchemist/core/cross_sweep.py` — **new** (experiment-free model +
  identity).
- `experiments/catalog.py` — added `repository_parameter_spaces()` +
  `_network_parameter_space()` (experiment-owned).
- `tests/test_cross_sweep_stage1.py` — **new** (26 tests).
- `TASK_2.5_STAGE1_REPORT.md` — this report (new).
- `TASK_2.5_DESIGN.md` — committed earlier (unchanged this stage).
- `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` — status updated.

No other source, test, dependency, or world file was modified; no guarded core
file (templates/lineage/`__init__`/…) was touched, so **no sanctioned core
re-baseline was required**.
