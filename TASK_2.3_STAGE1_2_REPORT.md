# TASK 2.3 STAGE 1+2 REPORT — CompositionShape / CompositionSpace + Static Capability Filter

**Status:** COMPLETE (Build Stage 1+2 only)
**Date:** 2026-09-08
**Milestone:** Task 2.3 Build Stage 1+2 (first two stages per `TASK_2.3_DESIGN.md` §22/§23)
**Scope:** new `src/sim_alchemist/core/composition.py` — variant-aware binding identity
(`ComponentBinding`), canonical unordered component sets with content-addressed identity
(`CompositionShape`), deterministic bounded enumeration (`CompositionSpace`), and the
static capability filter (`CAPABILITY_VALID` / `CAPABILITY_INVALID`). **Stage 3/4/5 were
not implemented.** No CouplingTemplate registry, no coupling-template classification, no
world generation, no ComponentSpec variant stamping, no CompositionCatalog /
CompositionSearcher, no search integration, no new dependencies, no new experiment.

---

## 1. Objective

Task 2.1/2.2 established that *capability-compatible ≠ executable* and that the second row
of the discovery flow needs a **declarative, variant-aware, content-addressed model of a
component set**. Stage 1+2 delivers the elementary identity + shape + space + static
capability classification:

- a component set is an **unordered, variant-distinct set of `(component, variant)`
  identities** — a `pymunk` wall world and a `pymunk` mover world are different
  bindings, shapes, and ids;
- a `CompositionShape` is immutable, content-addressed (24-hex `shape_id`), and
  order-independent (the same bindings in any input order give the same shape);
- a `CompositionSpace` enumerates all shapes of bounded size deterministically
  (size-first, canonical universe order, right-most element fastest, variant
  exclusivity enforced);
- a **static capability filter** classifies any shape as `CAPABILITY_VALID` or
  `CAPABILITY_INVALID` using only constructor-level adapter metadata — never
  initializing, stepping, or running a world.

The design (24-section `TASK_2.3_DESIGN.md`) mandated a staged delivery; this is the
smallest generic core-only slice, which is exactly what Stage 3 (CouplingTemplate
Registry) will build on.

---

## 2. IMPLEMENTED — `ComponentBinding`: the elementary identity

```python
@dataclass(frozen=True)
class ComponentBinding:
    component: str
    variant: str | None = None
```

- Identity is the canonical pair `(component, variant)`; `variant=None` is legal.
- The empty / whitespace-only variant string **normalizes to `None`**, so
  `ComponentBinding("py-pde", "") == ComponentBinding("py-pde", None)`.
- Non-string component or variant, or an empty component name, fails loudly
  (`ValueError` / `TypeError`).
- `as_dict()` / `from_dict()` round-trip (structural `{"component": ..., "variant": ...}`),
  consistent with `world.py` / `contracts.py` conventions.
- `pymunk/walls` vs `pymunk/movers` vs `py-pde` are three distinct bindings.

---

## 3. IMPLEMENTED — `CompositionShape`: canonical unordered set semantics

```python
@dataclass(frozen=True)
class CompositionShape:
    bindings: tuple[ComponentBinding, ...]
```

- Holds **at least one** binding; `CompositionShape(())` is rejected.
- Canonical storage: sorted by `(component, variant-or-"")`, so two shapes built from the
  same bindings in different input orders are **equal** and share one `shape_id`.
- **Variant exclusivity** is enforced at construction: two bindings of the same component
  id (including both `pymunk` variants) raise `ValueError` ("variant exclusivity violation");
  exact duplicates raise `ValueError` ("duplicate binding").
- The canonical order is documented as deterministic and is never derived from Python set
  iteration order.
- `components()` returns the unique component ids in canonical order; `__len__` / `__iter__`
  make the shape tuple-like.

---

## 4. IMPLEMENTED — `shape_id`: content-addressed, order-independent, variant-sensitive

```python
@property
def shape_id(self) -> str: ...   # sha256(canonical JSON of sorted bindings)[:24]
```

- Uses the repo's 24-hex convention (`lineage.world_hash`/`run_id_of`,
  `contracts.contracts_key`): `sha256(json.dumps(..., sort_keys=True, separators=(",",":"))).hexdigest()[:24]`.
- `[pymunk/walls, py-pde]` and `[py-pde, pymunk/walls]` → **same** `shape_id`;
  replacing `pymunk/walls` with `pymunk/movers` → **different** `shape_id`.
- `as_dict()` / `from_dict()` round-trip preserves equality and `shape_id`.

---

## 5. IMPLEMENTED — `CompositionSpace`: deterministic bounded enumeration

```python
@dataclass(frozen=True)
class CompositionSpace:
    name: str
    universe: tuple[ComponentBinding, ...]
    min_size: int = 2
    max_size: int = 4
```

- The **universe** is the full set of registered bindings and may legitimately contain two
  variants of one component id (that is exactly the `pymunk/walls` + `pymunk/movers` case).
  It is canonicalized (sorted, exact duplicates rejected) at construction; bounds are
  validated `0 <= min_size <= max_size <= len(universe)`.
- `enumerate_shapes()` returns a **tuple** (eager, immutable) of shapes:
  1. size-first: `k` from `max(min_size, 1)` to `max_size` (an empty shape is never
     enumerated even when `min_size == 0`, since a composition always has ≥ 1 binding);
  2. per size, `itertools.combinations` over the canonical universe — the right-most
     element changes fastest;
  3. combinations that would repeat a component id are **skipped** (variant exclusivity),
     so enumeration never raises.
- All enumeration is reproducible: repeated calls return identical tuples.

---

## 6. IMPLEMENTED — variant exclusivity and the exact counts

For the five variant-distinct bindings the whole repo can supply
(`mesa`, `py-pde`, `network`, `pymunk/walls`, `pymunk/movers` — see §8), pair/`k`-tuples
that contain *both* `pymunk` variants are excluded:

| size k | `C(5,k)` | minus both-pymunk subsets | **enumerated** |
|---|---|---|---|
| 1 | 5 | 0 | **5** |
| 2 | 10 | 1 | **9** |
| 3 | 10 | 3 | **7** |
| 4 | 5 | 3 | **2** |
| total (min=1, max=4) | 30 | 7 | **23** |

These counts are pinned in the test suite; nothing silently changes them.

---

## 7. IMPLEMENTED — static capability filter (CAPABILITY_VALID / CAPABILITY_INVALID)

```python
@dataclass(frozen=True)
class CapabilitySurface:
    provides: frozenset[str]
    requires: frozenset[str]

@dataclass(frozen=True)
class CompositionClassification:
    shape: CompositionShape
    status: str                    # CAPABILITY_VALID | CAPABILITY_INVALID
    missing_capabilities: tuple[str, ...] = ()
```

- `capability_surfaces_from_registry(registry)` **constructs each adapter once with an
  empty config** (constructor-only — never `initialize`, never `step`) and reads its
  declared `provides` / `requires` plus its concrete `variant`, yielding one
  `(binding -> surface)` mapping.
- `bindings_from_registry(registry)` returns that registry's distinct bindings,
  canonically sorted (the smallest generic adjustment enabling `pymunk/walls` and
  `pymunk/movers` to be enumerated separately — no registry redesign).
- `classify_shape(shape, surfaces, required=())`:
  `provided` = union of the shape's surface `provides`;
  `needed` = union of the shape's surface `requires` + the optional world-level
  `required`;
  `missing` = sorted names in `needed` not in `provided` (deterministic);
  status = `CAPABILITY_VALID` iff `missing == ()`, else `CAPABILITY_INVALID`.
- `classify_shapes(...)` is the deterministic batch form.
- A binding with no pre-built surface raises a clear `ValueError` (explicit surfaces only;
  `classify_*` never constructs adapters).
- **Capability-valid does NOT mean executable** — coupling templates (Stage 3) still do
  not exist, and no `EXECUTABLE` verdict exists in this stage.

---

## 8. IMPLEMENTED — registry integration (the five-binding universe is real)

The universe is derived from the actual in-process registries (never hard-coded):

| registry | bindings it supplies |
|---|---|
| `default_registry()` | `mesa`, `py-pde`, `pymunk/walls` |
| `build_network_morphogenesis_registry()` | above + `network` |
| `build_field_guided_movers_registry()` | `mesa`, `py-pde`, `pymunk/movers` (wall entry overridden) |

Merging their surfaces yields all five variant-distinct bindings. Verified adapter
surfaces (from constructors):

| binding | provides | requires |
|---|---|---|
| `mesa` | agent_population, agent_step, field_sensing, agent_intentions | scalar_field |
| `py-pde` | scalar_field, reaction_diffusion, spatial_sampling, field_masking, field_gradient, field_sources | geometry_provider |
| `pymunk/walls` | rigid_body, collision_geometry, force_integration, geometry_provider | field_gradient, agent_intentions |
| `pymunk/movers` | rigid_body, force_integration, geometry_provider | scalar_field, field_gradient, field_sources |
| `network` | network_diffusion, agent_intentions | reaction_diffusion, rigid_body |

---

## 9. IMPLEMENTED — known capability-valid and known-invalid shapes

**Capability-valid** (with the declared world-level `required` set where applicable):

- `{py-pde, pymunk/walls, mesa}` — Experiment A (requires agent_population,
  reaction_diffusion, rigid_body, field_gradient)
- `{py-pde, pymunk/movers}` — Experiment B (requires reaction_diffusion, rigid_body,
  field_gradient)
- `{py-pde, pymunk/walls, network}` — Experiment C (requires reaction_diffusion,
  rigid_body, network_diffusion, field_gradient)
- `{py-pde, pymunk/movers, mesa}` and `{py-pde, pymunk/movers, network}` and
  `{mesa, py-pde, pymunk/walls, network}` are also capability-valid **but are not wired
  by any experiment** — the filter intentionally reports them as CAPABILITY_VALID
  (executability is a Stage 3 question, not a Stage 2 one).

**Capability-invalid:**

- `{py-pde, mesa}` → `CAPABILITY_INVALID`, missing `("geometry_provider",)`.
- Every single-binding shape is `CAPABILITY_INVALID` with its deterministic sorted
  `missing_capabilities` (e.g. `mesa` alone → `("scalar_field",)`).

---

## 10. IMPLEMENTED — repo hygiene, guards, and core purity

- `composition.py` was written experiment-free and operation-name-free so the scheduler
  op-name scan (`test_scheduler.py::test_core_knows_no_experiment_operation_names`) and
  the new architectural test (`test_composition_space.py::test_composition_core_is_experiment_free`)
  both pass.
- Guarded-core hashes re-baselined (sanctioned Task 2.3 extension path): `composition.py`
  is added and `__init__.py` updated in `CORE_COMMIT_HASHES`
  (`tests/test_field_guided_movers.py`); `tests/test_network_morphogenesis.py` reuses the
  dict automatically. Both guard messages now read "Task 2.3".
- `src/sim_alchemist/core/__init__.py` re-exports the composition API.
- No scientific baseline parameter changed; nothing was deleted; no prior test weakened.

---

## 11. IMPLEMENTED — tests (`tests/test_composition_space.py`, 40 tests)

- **ComponentBinding** (6): value equality + hashing; variant normalization (None/"");
  invalid input rejection; canonical serialization; round-trip; walls-vs-movers identity.
- **CompositionShape** (9): order-independent equality; canonical ordering; deterministic
  `shape_id` (24 hex); variant changes `shape_id`; input-order-independent `shape_id`;
  round-trip; duplicate rejection; same-component variant exclusion; empty shape rejection.
- **CompositionSpace** (9): default bounds; custom bounds honored; invalid bounds; two
  deterministic-enumeration checks; no duplicate shapes; **exact counts 5/9/7/2, total 23**;
  variant exclusivity; size-first-then-canonical ordering.
- **Registry-derived bindings** (4): default registry = 3 bindings; network registry adds
  `network`; movers registry swaps walls for movers; full universe (5 bindings) matches the
  merged registries.
- **Capability filter** (8): A/B/C shapes capability-valid (with their real world-level
  requires); `{py-pde, mesa}` → CAPABILITY_INVALID; deterministic missing lists for every
  single-binding shape; extra world-required capability reported; deterministic batch
  classification; capability-valid-but-not-executable shapes; unknown binding fails loudly.
- **Static-only proofs** (2): monkeypatched `initialize`/`step` on all five adapter classes
  prove neither is ever called while building surfaces or classifying; a patched
  `AdapterFactory.build` counter proves classification never constructs new adapters.
- **Core purity** (1): `composition.py` source contains no experiment identifier /
  operation-name vocabulary.

---

## 12. Validation results (closing gate)

- `uv run pytest` — **274 passed** (271 fast + 3 slow canonicals), 0 failures.
- `uv run python run_validation.py` — A–G **PASS** (bitwise-identical replay intact).
- `uv run python run_stability.py` — S1–S6 **PASS**.
- `uv run ruff check .` — clean.
- `uv run pyright` — 0 errors.
- `uv sync` environment already at lock; no dependency changed.

---

## 13. Limitations (preserved, not hidden)

- The filter is **static-capability-only**. There is no coupling-template registry /
  classification (COUPLING_UNAVAILABLE / COUPLING_INVALID), no schedule- or clock-level
  validation, and no EXECUTABLE verdict. Capability-valid ≠ executable.
- The 5-binding universe and the A/B/C shapes live only in tests; nothing in `core/`
  knows about them (that is the point of the purity test).
- Capability surfaces are read by **constructing** each adapter (constructor-only, never
  stepped). This is documented and safe today (all constructors are pure parameter
  storage), but a future external adapter whose constructor has side effects would need
  a metadata-only capability surface.
- Determinism is same-runtime / same-environment (the repo-wide standing limitation).

---

## 14. Stage 3/4/5 — confirmed NOT implemented

As required by the Stage 1+2 task, **nothing beyond the shape/space + static capability
filter was built**:

- Stage 3 — CouplingTemplate registry, per-experiment templates owned by the coupling
  modules, COUPLING_UNAVAILABLE / COUPLING_INVALID / SCHEDULE_INVALID / CLOCK_INVALID /
  EXECUTABLE classification: **NOT started**.
- Stage 4 — world generation from compositions + `ComponentSpec` variant stamping:
  **NOT started**.
- Stage 5 — `CompositionCatalog` / `CompositionSearcher` / composition lineage table /
  discovery demo: **NOT started**.

---

## 15. Files changed

- `src/sim_alchemist/core/composition.py` — NEW (Stage 1+2 deliverable).
- `src/sim_alchemist/core/__init__.py` — re-exports composition API (+ `__all__`).
- `tests/test_composition_space.py` — NEW (40 tests).
- `tests/test_field_guided_movers.py` — guarded-core dict re-baselined (composition.py +
  __init__.py) + guard message updated to Task 2.3.
- `tests/test_network_morphogenesis.py` — guard message/history updated to Task 2.3.
- `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md` — status updated.
- `TASK_2.3_STAGE1_2_REPORT.md` — this report.