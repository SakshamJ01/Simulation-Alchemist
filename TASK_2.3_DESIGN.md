# TASK 2.3 DESIGN — Composition Space and Deterministic Composition Enumeration

**Status:** PLAN-ONLY design deliverable. **No source code was modified.** Nothing
here is implemented; §23 describes the *smallest safe future Build task*. Task 2.4
was not started.

---

## 1. Current architecture audit (verified against source)

### 1.1 Engine / component ecosystem

| Component id | Variant | Adapter | Provides | Requires |
|---|---|---|---|---|
| `mesa` | — | `MesaAdapter` | agent_population, agent_step, field_sensing, agent_intentions | scalar_field |
| `py-pde` | — | `PyPDEAdapter` | scalar_field, reaction_diffusion, spatial_sampling, field_masking, field_gradient, field_sources | geometry_provider |
| `pymunk` | `walls` | `PymunkAdapter` | rigid_body, collision_geometry, force_integration, geometry_provider | field_gradient, agent_intentions |
| `pymunk` | `movers` | `MoversAdapter` | rigid_body, force_integration, geometry_provider | scalar_field, field_gradient, field_sources |
| `network` | — | `AdaptiveNetworkAdapter` | network_diffusion, agent_intentions | reaction_diffusion, rigid_body |

Verified in `src/sim_alchemist/adapters/{mesa,pde,pymunk}.py`,
`experiments/field_guided_movers/model.py:238-253`,
`experiments/network_morphogenesis/adapter.py:49-66`.

### 1.2 Validated experiments

| Experiment | Binding set | Contracts | Schedule |
|---|---|---|---|
| A — chemo-mechanical morphogenesis | `{mesa, py-pde, pymunk/walls}` | `MORPHOGENESIS_CONTRACTS` (4) | `MORPHOGENESIS_SCHEDULE` |
| B — field-guided movers | `{py-pde, pymunk/movers}` | `FIELD_GUIDED_MOVERS_CONTRACTS` (2) | `FIELD_GUIDED_MOVERS_SCHEDULE` |
| C — adaptive network morphogenesis | `{py-pde, pymunk/walls, network}` | `NETWORK_MORPHOGENESIS_CONTRACTS` (5) | `NETWORK_MORPHOGENESIS_SCHEDULE` |

All three runnable through the generic `AlchemistEngine` + core `StepScheduler`
against declaratively-described worlds (`compose(world, registry, operations)`
proved bitwise identical to the facade paths).

### 1.3 Reusable infrastructure (as-built)

`WorldDefinition`/`ComponentSpec` (`world.py`), `ComponentRegistry`/`AdapterFactory`
(`registry.py`), `resolve_capabilities` (`composer.py`), `CouplingContract` /
`resolve_contracts` / `adapter_by_id` / `contracts_key` (`contracts.py`, Task 2.2),
`AlchemistEngine` (`engine.py`), `SimulationClock` (`clock.py`), `StepScheduler`
(`scheduler.py`), `EventBus` (`events.py`), `WorldState` (`state.py`), `Mutation` /
`clone_world` (`mutation.py`), `VariantRunner` (`runner.py`), `SweepRunner`
(`sweep.py`), `BehaviorAnalyzer` / `InterestingnessProfile` / `rank_by_profile` /
`behavior_distance` (`behavior.py`), `SearchRunner` / `select_diverse_frontier`
(`search.py`).

### 1.4 Safety pipeline (as-built)

```
  candidate world
        ↓
  capability validation      resolve_capabilities         (composer.py:42)
        ↓
  coupling-contract validation  resolve_contracts         (contracts.py, optional contracts=)
        ↓
  schedule validation        StepSchedule                 (scheduler.py:67; unknown ops rejected)
        ↓
  clock validation           SimulationClock divisibility (clock.py:26)
        ↓
  execution
```

Task 2.2 established that capability compatibility alone is NOT enough (e.g.
`{py-pde, pymunk/movers, network}` is capability-valid yet executable by no
experiment).

### 1.5 Identity semantics (as-built)

- `world_hash(world)` = sha256 of sorted `world.as_dict()` JSON (`lineage.py:44`) —
  covers components (id + config), requires, schedule, macro_timestep, max_steps,
  seed, config.
- `run_id_of(world)` = sha256(`world_hash` | `seed`)[:24] (`lineage.py:52`).
- `contracts_key(contracts)` = sha256 of canonical JSON of the contract set
  (`contracts.py:247`).
- `sweep_id_of` / `search_id_of` / `behavior_analysis_id_of` are analogous
  content-addressed digests (24-hex, no random ids).
- Mutation: `_MUTABLE_TOP_LEVEL = {seed, max_steps, macro_timestep}`,
  `_IMMUTABLE_TOP_LEVEL = {id, schedule, requires}`; `components` is *navigable*
  only to `components.<id>.config.<leaf>` (`mutation.py:60-66`).

### 1.6 The exact architecture gap

- `ComponentRegistry._factories` maps **one factory per component id**
  (`registry.py:41`); the `pymunk` walls/movers duality is expressed by
  *overriding* the `pymunk` entry (Experiment B) at registry build time. A single
  registry/world therefore cannot contain both variants simultaneously.
- `ComponentSpec` has **no variant field** (`world.py:25`); the concrete binding is
  implicit — it lives in whichever registry factory composes the world. So the same
  `ComponentSpec("pymunk", …)` is structurally identical for A and B unless their
  configs happen to differ.
- There is **no elementary, enumerated, hashable representation of a component set**.
  Consequently nothing can enumerate candidate compositions, run them through the
  existing validation funnel, classify them, or give them stable identity; and world
  identity cannot today distinguish `pymunk/walls` from `pymunk/movers`.

---

## 2. Composition definition

A *composition* is **E: components + variants + coupling contracts**, with the
schedule carried as part of the executable declaration.

- **Elementary unit = `ComponentBinding(component, variant)`** — e.g. `("pymunk","walls")`
  vs `("pymunk","movers")`.
- **Search unit = `CompositionShape`** — an *unordered, canonically-sorted set of
  bindings*; this is the identity of *which components, which variants*.
- **Executable unit = `CouplingTemplate`** — the experiment-owned declaration that
  pairs a binding set with its coupling contracts (the Task 2.2 `CONTRACTS`), its
  schedule, its world-level `requires`, and an opaque executor reference.

Component presence alone is provably insufficient (`{mesa, py-pde, pymunk}` is
runnable only under `walls`; `{py-pde, pymunk/walls, network}` runs as C while the
same set under `movers` is unwired), so variant membership is mandatory, and a
template/coupling declaration is mandatory before anything can be declared
executable.

---

## 3. Component identity

Canonical identity = the canonical pair **`(component, variant)`**,
`variant=None` allowed (`None` = unambiguous id). This one identity is used for
enumeration, equality, hashing, world identity, lineage, and persistence.

- canonical key: `f"{component}|{variant or '_core'}"`; serialization is
  structural: `{"component": "py-pde", "variant": null}`.
- frozen dataclass equality/hash (stdlib field-based); **never list position**
  (`AlchemistEngine` already keys engines by `engine_id`, `engine.py:102`).
- deterministic across process runs; content-addressed.
- future-proof: an optional `version` can later be folded onto the pair without
  changing the model.

**Build-gap to flag (Build Stage 4):** because `ComponentSpec` has no `variant`,
world identity cannot today distinguish A's `pymunk` from B's `pymunk` unless the
configs differ. The Build task adds an optional `variant` field to `ComponentSpec`
(guarded-core, sanctioned re-baseline) so the variant stamp flows into
`as_dict()` and therefore into `world_hash` — making world identity
composition-aware.

---

## 4. CompositionShape

Minimal immutable representation (future `src/sim_alchemist/core/composition.py`):

```python
@dataclass(frozen=True)
class ComponentBinding:
    component: str
    variant: str | None = None
    # to_dict/from_dict round-trip; equality + hash are field-based

@dataclass(frozen=True)
class CompositionShape:
    bindings: tuple[ComponentBinding, ...]   # canonically sorted, deduplicated
```

- **Order semantics:** set semantics. Bindings are stored in canonical sort order
  `(component, variant-or-"")`; order is immaterial to correctness (every downstream
  validation stage is position-free) but stored canonically so equality, hash, and
  `shape_id` are deterministic.
- **Mutual exclusion:** no two bindings may share a `component` (variants of one id
  are mutually exclusive), mirroring the registry and `engine.engines`.
- **Requirements:** deterministic, hashable, serializable/canonicalizable, variant
  aware, stable across process runs — all satisfied via frozen dataclass +
  canonical `to_dict`/`from_dict` + `shape_id` digest (see §12).
- A building note: `to_dict` must normalize each binding's `variant` so that an
  empty string and `None` serialize identically (normalize `""` → `None`).

---

## 5. CompositionSpace

```python
@dataclass(frozen=True)
class CompositionSpace:
    name: str
    universe: tuple[ComponentBinding, ...]     # all registered/variant bindings
    min_size: int = 2
    max_size: int = 4
```

- `enumerate_shapes()` yields every size-k subset of the canonically-sorted universe
  for `k in [min_size, max_size]`, applying the same-component mutual-exclusion rule
  (a filter on `itertools.combinations`, never a solver).
- Deterministic; right-size-first ordering.
- The universe is derived from the **registry it will be composed against** (so only
  registered, buildable bindings are enumerated today; plugin universes later flow in
  unchanged, §18).

---

## 6. Enumeration strategy

- Singletons: **allowed for analysis** but almost always `CAPABILITY_INVALID`
  (every real adapter `requires` something from another).
- **Minimum composition size = 2** (all wired experiments are size ≥ 2).
- **Maximum composition size = 4** (largest experiment today is 3; a 4th member is
  exactly the known-unwired discovery target).
- **Duplicate engine ids are not allowed** (one world = one adapter per `engine_id`).
- **Multiple variants of one engine id are mutually exclusive** (walls XOR movers).
- Roles are dimensions over the binding universe, not optional bag items.

Current universe (5 bindings): `mesa`, `py-pde`, `network`, `pymunk/walls`,
`pymunk/movers`. Enumeration is `itertools.combinations` over that universe with the
exclusivity filter — no heuristic, no solver.

---

## 7. Combinatorial growth (exact counts from the repository)

Naive power set of 5 bindings: 2⁵ = **32** sets (31 non-empty). With variant
exclusivity (every subset of `{mesa, py-pde, network}` × pymunk ∈ `{∅, walls, movers}`):
**24** sets total, **23** non-empty.

| size k | shapes | composition |
|---|---|---|
| 1 | **5** | `mesa`, `py-pde`, `network`, `pymunk/walls`, `pymunk/movers` |
| 2 | **9** | 6 one-`{mesa,pde,network}`+pymunk-variant + 3 `{mesa,pde,network}` pairs |
| 3 | **7** | 6 `{mesa,pde,network}`-pair+pymunk-variant + `{mesa,py-pde,network}` |
| 4 | **2** | `{mesa,py-pde,network}` + `walls` / + `movers` |

**Scaling:** N independent engines with Vᵥ variants each → ∏(1+Vᵥ) binding sets;
50 single-variant engines → 2⁵⁰ ≈ 1.1 × 10¹⁵; 100 → 2¹⁰⁰. Unbounded enumeration
explodes.

**Smallest pruning hooks (nothing more is needed now):**
1. **Variant exclusivity** — walls/movers never co-enumerate (always).
2. **Configurable `min_size`/`max_size`** — the practical world dominates; a
   default max of 4 keeps the raw space at 23 shapes today.
3. **Static capability filter** — pure set operations over cached per-binding
   capability surfaces, *before any adapter construction* (§8).
4. **The finite CouplingTemplate set** — only template-matched shapes can be
   executable; every other shape remains statically classified (§9). No solver, no
   constraint engine.

---

## 8. Capability filtering

`CompositionSpace` integrates with the existing `CapabilityResolver` semantics by
**reusing `resolve_capabilities` unchanged** at execution time and adding a *thin
static sibling* at enumeration time:

- A per-`ComponentBinding` capability surface (provides + requires) is resolved
  **once per (component, variant)** via registry metadata — a cached descriptor on
  the registry factory, populated from the adapter's capability surfaces *without
  calling `initialize`* (constructors only; capabilities are constant per binding).
- The static filter computes provided = union of surfaces, needed = union of
  requirements + optional world-level `requires`; missing ⇒ `CAPABILITY_INVALID`.
- World-level requirements are supported when a template supplies them (§9);
  provider requirements are the default source.
- Variant-specific capabilities participate because the surface is keyed by
  (component, variant), so `walls` and `movers` get different surfaces.
- **No duplication of `resolve_capabilities` logic:** a single shared helper
  computes provided/needed from a sequence of capability surfaces; the live
  composer path and the static shape path both call it.

---

## 9. Coupling-template strategy (the central problem)

**Recommended: Option E hybrid, principally D (separate template registry) + C
(experiment-declared).** A `CouplingTemplateRegistry` is populated declaratively by
the experiments; it is the only legitimate source of contracts and schedules.

```python
@dataclass(frozen=True)
class CouplingTemplate:
    name: str                       # "morphogenesis" | "field-guided-movers" | "adaptive-network"
    bindings: tuple[ComponentBinding, ...]  # canonical binding set it realizes
    world_id: str                   # "chemo_morphogenesis" | "field_guided_movers" | "adaptive_network"
    contracts: tuple[CouplingContract, ...] # = the experiment's <EXP>_CONTRACTS (Task 2.2)
    schedule: tuple[str, ...]       # = the experiment's <EXP>_SCHEDULE
    requires: tuple[str, ...]       # world-level capabilities
    executor_ref: str               # opaque experiment-bound ops/observables/executor identity
```

Rules (non-negotiable):

- **Contracts are NEVER inferred.** A shape is `EXECUTABLE` iff its canonical
  binding-set equals *some template's* binding set; validation then reuses
  `resolve_contracts` exactly as the composer does today.
- No template ⇒ no contracts ⇒ not executable, no matter how capability-valid.
- Templates hold **no science** — only references to experiment-owned data already
  co-located in the coupling modules (colocation preserved, drift-proof).

**Answer to "represent a candidate with no experiment coupling yet":** enumerate it
as a `CompositionShape` (it enumerates fine), classify it `COUPLING_UNAVAILABLE`.
`mesa + network` gets no meaning — `CAPABILITY_INVALID` or `COUPLING_UNAVAILABLE`,
never invented coupling.

---

## 10. Candidate status taxonomy

One static funnel, top to bottom, no simulation:

```
CAPABILITY_INVALID    required capability missing from the binding set's union
COUPLING_UNAVAILABLE  capability-valid, but no CouplingTemplate for these bindings
COUPLING_INVALID      template exists, resolve_contracts rejects a declared edge
                      (endpoint absent, variant mismatch, capability/payload/key/
                       coordinate/grid violation) — reasons from ContractIssue
SCHEDULE_INVALID      template schedule names a non-registered operation
CLOCK_INVALID         a binding's native dt does not divide macro_timestep
EXECUTABLE            all static gates pass
```

This distinguishes precisely: (1) impossible with current components
(`CAPABILITY_INVALID`), (2) compatible but unwired (`COUPLING_UNAVAILABLE`), (3)
declared but technically invalid (`COUPLING_INVALID` / `SCHEDULE_INVALID` /
`CLOCK_INVALID`), (4) fully executable (`EXECUTABLE`).

Default route: a shape with no template is classified `COUPLING_UNAVAILABLE`
(never `COUPLING_INVALID`, which implies a template exists). `SCHEDULE_INVALID` /
`CLOCK_INVALID` only apply to template-bound shapes (defensive; today all three
wired templates pass both).

---

## 11. Known current compositions

**Templates (EXECUTABLE)** — confirmed from source:

| Template | Binding set | Contracts | Schedule |
|---|---|---|---|
| `morphogenesis` | `{mesa, py-pde, pymunk/walls}` | `MORPHOGENESIS_CONTRACTS` | `MORPHOGENESIS_SCHEDULE` |
| `field-guided-movers` | `{py-pde, pymunk/movers}` | `FIELD_GUIDED_MOVERS_CONTRACTS` | `FIELD_GUIDED_MOVERS_SCHEDULE` |
| `adaptive-network` | `{py-pde, pymunk/walls, network}` | `NETWORK_MORPHOGENESIS_CONTRACTS` | `NETWORK_MORPHOGENESIS_SCHEDULE` |

**Known capability-valid but coupling-unavailable** (Task 2.1 §8.4/8.5, §9; Task 2.2
gap-proof — now given explicit classifications):

| Binding set | Capability-valid? | Classification |
|---|---|---|
| `{py-pde, pymunk/movers, mesa}` | yes | `COUPLING_UNAVAILABLE` (agent intentions un-consumed; walls absent) |
| `{py-pde, pymunk/walls, mesa, network}` | yes | `COUPLING_UNAVAILABLE` (two `agent_intentions` producers; no template resolves the ambiguity) |
| `{py-pde, pymunk/movers, network}` | yes | `COUPLING_UNAVAILABLE` (the Task 2.2 gap-proof case) |

Remaining bottom ~17 shapes fail `CAPABILITY_INVALID` (e.g. `{mesa, py-pde}` lacks
`geometry_provider`).

---

## 12. World generation design (design only, not built)

`EXECUTABLE shape → template → WorldDefinition`:

- components = `ComponentSpec(binding.component, template-default-config)` **with
  `variant` stamped** (new optional field on `ComponentSpec`, Build Stage 4);
- `requires` = template.requires;
- `schedule` = template.schedule;
- `contracts` = template.contracts (passed to compose, as Task 2.2);
- clock: `macro_timestep` from template default (0.2 today), `max_steps`/`seed`
  from time space defaults (configurable);
- `config` = the template's experiment-sanctioned default config.

**Important:** automatic scientific configuration is NOT built. The only auto-config
is experiment-declared defaults; nothing is invented. The generated `WorldDefinition`
is a plain typed object — inspectable, `to_yaml`-able, and byte-identical through the
existing compose path.

---

## 13. Composition identity

- `shape_id` = sha256(canonical sorted-bindings JSON)[:24] — distinguishes
  `pymunk/walls` from `pymunk/movers`; content-addressed, deterministic across runs.
- `composition_id` = sha256(`shape_id` | `contracts_key` | `schedule` |
  `requires` | `macro_timestep`)[:24] — distinguishes same shape with different
  contracts or schedule.
- **World identity** stays `world_hash(WorldDefinition)`, now **variant-aware** via
  the stamped `ComponentSpec.variant`, and already covers the rest of the world
  content (components+config, requires, schedule, macro_timestep, max_steps, config;
  `run_id_of` additionally folds in the seed). Contract sets are validation metadata
  (not science), so they distinguish `composition_id`, not `world_hash`.
- **No random ids**; 24-hex repo convention throughout.

Distinguishes (all four, per Task 2.3 §14):
- same components + different variant → different `shape_id`/`world_hash`;
- same components + different contracts → different `composition_id`;
- same composition + different schedule → different `composition_id` + `world_hash`;
- same composition + different configuration → different `world_hash` (config is in
  `as_dict`).

---

## 14. Lineage implications

One SQLite lineage store (no second database). Two orthogonal axes:

- **Composition axis:** a different shape/template ⇒ different world content ⇒
  different `world_hash`/`run_id`. A "composition variant" is a **new root** run, not
  a parameter child. `composition_id` is recorded as compact metadata on the run
  record (additive field) so queries can group/compare by composition.
- **Parameter axis:** within one composition, Task 1.6–2.0 mutation navigates
  `components.<id>.config.*` exactly as today; `parent_run_id` chains are unchanged.

Lineage can therefore answer: "parameter child of which root (composition) run?" and
"composition root whose shape/template is X" — distinguished without a second
database.

---

## 15. Mutation vs composition

**Recommended: C — a sibling concept to parameter mutation**, not a special mutation.

Rationale, grounded in source: the mutation grammar is *leaf-parameter navigation* on
fixed structural fields (`_MUTABLE_TOP_LEVEL`); `components` membership/order and
`schedule`/`requires` are structural and immovable (`mutation.py:60-66`). Changing the
binding set is a *structural transform* — it cannot be written as a dot-path leaf
change without breaking the grammar's contract.

Design: `apply_composition_transform(shape)` is a separate, deterministic sibling that
maps a `CompositionShape` (+ template) to a fresh template-bound `WorldDefinition`;
ordinary parameter mutation then applies within it. Deterministic identity is
preserved because both derive from content-addressed hashes. No new lineage concepts.

---

## 16. Future search integration (design only, not built)

```
CompositionSpace
    ↓ enumerate_shapes()            (deterministic, canonical order)
    ↓ static classify               (capability → template-match → schedule/clock)
    ↓ EXECUTABLE shapes only
    ↓ generate executable worlds    (WorldDefinition per template)
    ↓ per-world root:
        SearchRunner.search()       (existing Tasks 1.6–2.0 machinery)
        BehaviorAnalyzer            (existing)
        rank_by_profile             (existing)
        select_diverse_frontier     (existing; cross-composition diversity via
                                     behavior_distance over per-shape vectors)
```

No new search engine, no optimizer: the future `CompositionSearcher` is a thin,
deterministic loop over validated shapes that reuses the existing mutation / search /
behavior / diversity pipeline verbatim, with the composition axis adding `shape_id` /
`composition_id` identity (metadata only).

---

## 17. Scientific safety

Preserve the three hard tiers:

> **technical compatibility** ⊆ **executable compatibility** ⊆ **scientific validity**

- Technical compatibility = capability-name satisfaction (existing).
- Executable compatibility = template match + `resolve_contracts` + schedule + clock.
- Scientific validity = only experiment-declared semantics.

Declared semantics are enforced per edge by `CouplingContract` + adapter metadata:
state meaning (payload keys), payload shape, coordinate system (`unit-square-2d`),
timing (`same-macro-step`), mechanism (`direct`), directionality (producer →
consumer), variant identity. **Nothing is ever auto-coupled**; a capability-valid
shape with no template is `COUPLING_UNAVAILABLE`. No new physics, no new simulation
concept, no AI-driven composition.

---

## 18. Scalability / pruning

- All pruning stages are **static** set/dict/sha operations over ≤ universe size.
- Ordering guarantees expense: capable filter and template-match run on bindings
  alone; **adapter construction happens only for EXECUTABLE shapes at execution
  time** (§8 must be observed as the "before adapter construction" stage).
- `enumerate_shapes()` may be a generator (lazy) if a large universe ever needs it —
  not required today.
- Capability surfaces cached per (component, variant).
- Sizes bounded by `min_size`/`max_size`.
- Today: 23 raw shapes → ~6 capability-valid → 3 executable. Everything but the 3 is
  eliminated statically, with **zero simulations**.

---

## 19. Future plugin compatibility

- `ComponentBinding` / `CompositionShape` are registry-agnostic: the universe is
  whatever the registry enumerates. A future plugin registry supplies additional
  `(component, variant)` pairs without changing the shape model.
- Multiple versions can be folded into the variant string (e.g. `version` suffix) or
  a future optional `version` field — model stays stable.
- **No plugin infrastructure is added now** (explicitly out of scope, consistent with
  the task constraint).

---

## 20. Test design (future suite — described only, not built)

| Check | Description |
|---|---|
| A. deterministic enumeration | same space ⇒ identical ordered shape list across runs |
| B. variant-aware identity | `shape_id` / equality differ for `walls` vs `movers` bindings |
| C. no duplicate shapes | canonical set semantics; no (component, variant) duplicates; `to_dict` normalizes `""`/`None` variants |
| D. configurable min/max size | `enumerate_shapes()` honors `min_size`/`max_size` bounds |
| E. capability filtering | e.g. `{mesa, py-pde}` → `CAPABILITY_INVALID` (no `geometry_provider`) |
| F. coupling filtering | `EXECUTABLE` vs `COUPLING_UNAVAILABLE` vs `COUPLING_INVALID` |
| G. executable status classification | full taxonomy incl. defensive `SCHEDULE_INVALID`/`CLOCK_INVALID` |
| H. known A/B/C compositions resolve | A/B/C binding sets classify `EXECUTABLE`; generated worlds compose and are bitwise-identical to the facade worlds (noop schedule run) |
| I. capability-valid/coupling-invalid rejected | `{py-pde, pymunk/movers, network}` → `COUPLING_UNAVAILABLE`, never `EXECUTABLE` |
| J. world identity changes with composition | variant change, config change, schedule change, contracts change all change identity (see §13) |
| K. deterministic canonical serialization | `to_dict`/`from_dict`/`shape_id` round-trip stable |
| L. combinatorial count correctness | exact per-k table of §7 asserted (5 / 9 / 7 / 2) |
| M. parent remains immutable | shape/world parent never mutated by enumeration or generation |
| N. no automatic coupling inference | `{mesa, network}` never becomes executable; no template, no contracts |

---

## 21. UX / explainability

Every candidate carries `status` + human-readable `reasons`:

```
Candidate: {mesa, py-pde, pymunk/movers}
status:    COUPLING_UNAVAILABLE
reason:    capability-valid, but no declared CouplingTemplate binds this shape;
           agents would sense the field with no wall regimen and un-consumed
           intentions.
```

`COUPLING_INVALID` reasons reuse the `UnresolvedContractError` issues verbatim
(contract name, producer → consumer, variant, `what`, `fix`). The core never emits a
bare "invalid composition".

---

## 22. Exact staged implementation sequence (future BUILD tasks)

1. **Stage 1 — CompositionShape + identity.** `core/composition.py`:
   `ComponentBinding`, `CompositionShape`, canonical `to_dict`/`from_dict`,
   `shape_id`; `CompositionSpace` + `enumerate_shapes()` (variant exclusivity,
   `min_size`/`max_size`). Tests: A, B, C, D, K, L.
2. **Stage 2 — capability filtering.** Static per-(component, variant) capability
   surface cache + shared provided/needed helper; `CAPABILITY_INVALID` classification.
   Tests: E, M.
3. **Stage 3 — coupling-template availability.** `CouplingTemplate` +
   `CouplingTemplateRegistry` declared from the three coupling modules; taxonomy
   `COUPLING_UNAVAILABLE` / `COUPLING_INVALID` (reusing `resolve_contracts`).
   Tests: F, G, I, N.
4. **Stage 4 — executable world construction.** Stamp `ComponentSpec.variant`,
   template config defaults, `requires`/`schedule`/`contracts`; `SCHEDULE_INVALID` /
   `CLOCK_INVALID` gates; `composition_id` identity; guarded-core re-baseline.
   Tests: H, J.
5. **Stage 5 — catalog + lineage metadata.** `CompositionCatalog` status/reason
   facade (UX, §21); `composition_id` lineage metadata; docs
   (`TASK_2.3_REPORT.md`).

---

## 23. Smallest safe first Build task

> **"Add `src/sim_alchemist/core/composition.py` implementing Stages 1 and 2 only:**
> `ComponentBinding` + `CompositionShape` with canonical, variant-aware identity
> (`shape_id`) and serialization, `CompositionSpace` with deterministic,
> variant-exclusive, bounded enumeration, plus the static capability filter producing
> the `CAPABILITY_INVALID` classification. Do NOT add CouplingTemplates, world
> generation, or any search integration yet — unwired shapes ship classified as
> `COUPLING_UNAVAILABLE` by default."

Rationale: it lands the elementary shape/identity/space abstraction (the actual gap of
§1.6) with deterministic enumeration and an early static gate, while deferring the
template registry (the largest, most delicate step) to the separately-scoped Stage 3.
This keeps "contracts are never inferred" guaranteed by construction.

---

## 24. Required report (closing summary)

- **Architecture gap:** the concrete component binding (`(id, variant)`) exists *only*
  implicitly (registry override) and is absent from `ComponentSpec`/identity; there is
  no enumerable, hashable representation of a component set, hence no way to enumerate,
  classify, or give identity to candidate compositions.
- **Composition:** variant-aware binding set + experiment-owned coupling template when
  executable (E + hybrid template registry).
- **Component identity:** `(component, variant)` canonical pair.
- **CompositionShape:** canonical unordered/set semantics over bindings, frozen,
  deterministic.
- **CompositionSpace:** bounded universe + `enumerate_shapes()` (combinations +
  variant exclusivity, `min_size`/`max_size`).
- **Enumeration:** deterministic combinations; 23 raw shapes today (5 / 9 / 7 / 2).
- **Pruning:** variant exclusivity + size bounds + static capability filter + finite
  template set; no solver.
- **Capability filter:** static sibling of `resolve_capabilities`, before adapter
  construction; capabilities keyed by (component, variant).
- **Coupling templates:** experiment-owned `CouplingTemplateRegistry`; contracts never
  inferred; unwired = `COUPLING_UNAVAILABLE`.
- **Status taxonomy:** CAPABILITY_INVALID / COUPLING_UNAVAILABLE / COUPLING_INVALID /
  SCHEDULE_INVALID / CLOCK_INVALID / EXECUTABLE.
- **Known valid:** A `{mesa, py-pde, pymunk/walls}`, B `{py-pde, pymunk/movers}`,
  C `{py-pde, pymunk/walls, network}`.
- **Known unwired:** `{py-pde, pymunk/movers, mesa}`, `{py-pde, pymunk/walls, mesa,
  network}`, `{py-pde, pymunk/movers, network}`.
- **World generation:** template-bound `WorldDefinition` + `ComponentSpec.variant`
  stamp, experiment-sanctioned defaults, inspectable/`to_yaml`-able.
- **Identity/lineage:** `shape_id` / `composition_id` content-addressed; single
  lineage DB; composition axis = new roots, parameter axis unchanged; `composition_id`
  as metadata.
- **Mutation vs composition:** sibling structural transform (not a dot-path mutation).
- **Future search:** reuses existing mutation/search/behavior/diversity pipeline.
- **Smallest Build task:** Task 2.3 Build Stage 1 (+ Stage 2) as §23.
- **Confirmation:** PLAN-ONLY; no source, test, dependency, or world file was
  modified; no commits; no plugin/AI/optimizer/distributed infrastructure; Task 2.4
  not started.