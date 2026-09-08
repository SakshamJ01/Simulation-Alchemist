# TASK 2.3 REPORT — Build Stage 3+4+5 (CouplingTemplate Registry, World Generation, CompositionCatalog)

**Status:** COMPLETE (Build Stages 3+4+5)
**Date:** 2026-09-08
**Milestone:** Task 2.3 Build Stages 3+4+5 (per `TASK_2.3_DESIGN.md` §22, items 3–5)
**Scope:** the experiment-owned `CouplingTemplate` + `CouplingTemplateRegistry`
(Stage 3), the executable classification taxonomy with `COUPLING_UNAVAILABLE` /
`COUPLING_INVALID` / `SCHEDULE_INVALID` / `CLOCK_INVALID` / `EXECUTABLE`, declarative
world generation with `ComponentSpec.variant` stamping and `composition_id`
identity (Stage 4), and the queryable `CompositionCatalog` over the full 23-shape
repository space (Stage 5). **CompositionSearcher, search integration, lineage
writes, discovery demo, and Task 2.4 were NOT implemented.**

---

## 1. Objective

Stage 1+2 proved capability-valid does not mean executable; Stage 3+4+5 close that
gap with the design's Option E hybrid (separate template registry + experiment-declared
templates). The composite world is now fully *declared* data:

- a `CouplingTemplate` authored next to an experiment's coupling logic declares the
  exact binding set, the world identity/defaults, the experiment's contracts and
  macro-step order, the registered operation names, per-component configs, and the
  clock parameters;
- a deterministic 6-status funnel classifies every enumerated shape from a bounded
  universe — no simulation, no invented coupling;
- an `EXECUTABLE` shape's template **generates** a declarative `WorldDefinition`
  (variant-stamped `ComponentSpec`s) that is byte-identical through the existing
  compose path and bitwise-identical in trajectories to the experiment facade;
- a `CompositionCatalog` snapshots the whole space once, per-shape explainable
  (`status` + `reason`), with the 3 executable worlds materializable on request.

---

## 2. IMPLEMENTED — `CouplingTemplate` (Stage 3, authoring surface)

```python
@dataclass(frozen=True)
class CouplingTemplate:
    name: str                                   # "morphogenesis" | "field_guided_movers" | "adaptive_network"
    bindings: tuple[ComponentBinding, ...]      # canonical binding set (variant-aware)
    world_id: str                               # "chemo_morphogenesis" | "field_guided_movers" | "adaptive_network"
    contracts: tuple[CouplingContract, ...]     # the experiment's declared contracts
    schedule: tuple[str, ...]                   # the experiment's declared macro-step order
    operations: tuple[str, ...]                 # the operation names the coupling registers
    requires: tuple[str, ...] = ()              # world-level capabilities
    executor_ref: str | None = None             # opaque experiment-owned executor identity
    component_configs: Mapping[str, Mapping] = {}   # per-component constructor configs
    macro_timestep: float = 0.2
    max_steps: int = 160
    seed: int = 0
    config: Mapping[str, Any] = {}              # world-level shared config
```

- `__post_init__` canonicalizes `bindings` through `CompositionShape` (so input order
  never matters) and rejects empty/non-string `name`, empty `bindings`, empty
  `world_id`, empty `contracts`, empty `schedule`, and empty `operations` with
  `ValueError`. The exact design shape (`name/bindings/world_id/contracts/schedule/
  requires/executor_ref`) is extended with the fields Stage 4 world generation
  actually needs — a documented superset, never a deviation.
- **`operations` is mandatory on purpose and SCHEDULE⊆operations is NOT enforced at
  construction** so synthetic `SCHEDULE_INVALID` templates remain constructible for
  the defensive taxonomy tests. The well-formed templates all pass the gate.
- `contracts` never enter the funnel implicitly — the only legitimate sources are the
  coupling modules' declared template sets (colocation preserved, drift-proof).
- `as_dict()` / `from_dict()` round-trip (contracts via `CouplingContract.from_dict`).

---

## 3. IMPLEMENTED — `CouplingTemplateRegistry`

```python
class CouplingTemplateRegistry:
    def register(self, template) -> CouplingTemplate   # raises DuplicateTemplateError
    def lookup(self, shape) -> CouplingTemplate | None
    def by_name(self, name) -> CouplingTemplate | None
    def templates(self) -> tuple[CouplingTemplate, ...]
    # __len__, __iter__, from_sequence
```

- Registration is the only way in; a template is rejected if either its `name` or its
  canonical `shape.shape_id` is already present (`DuplicateTemplateError(ValueError)`).
  Two templates for one component set can never exist.
- Lookup is by content-addressed shape identity — the same shape built in any order
  finds the same template.
- `templates()` returns deterministic (name-sorted) tuples. **There is no discovery.**

---

## 4. IMPLEMENTED — the executable taxonomy funnel + `CompositionVerdict`

```python
@dataclass(frozen=True)
class CompositionVerdict:
    shape: CompositionShape
    status: str            # CAPABILITY_INVALID | COUPLING_UNAVAILABLE | COUPLING_INVALID
                           #   | SCHEDULE_INVALID | CLOCK_INVALID | EXECUTABLE
    missing_capabilities: tuple[str, ...] = ()
    template: str | None = None
    reasons: tuple[str, ...] = ()
    composition_id: str | None = None
    @property executable; def explain()
```

`classify_composition(shape, surfaces, templates, *, build_adapters)` runs one strict,
deterministic order:

1. **capability filter** — `classify_shape` (Stage 1+2) with the template's world-level
   `requires` folded in when a template matches; failure → `CAPABILITY_INVALID`
   (reason lists the missing capabilities; the matched template name is still reported);
2. **template lookup** — no template → `COUPLING_UNAVAILABLE`
   (`"no declared CouplingTemplate binds this component set: …"`), never executable;
3. **coupling contracts** — `resolve_contracts(adapters, template.contracts)` exactly
   as the composer does; rejection → `COUPLING_INVALID` with per-issue reasons
   `${contract} (${producer} -> ${consumer}${variant}): ${what}. ${fix}` from the
   `ContractIssue`s (the core never emits a bare "invalid composition");
4. **schedule** — any `schedule` op not in `template.operations` → `SCHEDULE_INVALID`
   (unknown ops sorted, deterministic);
5. **clock** — any constructed adapter whose `native_timestep` is `None`, `<= 0`, or
   does not divide `macro_timestep` (> `1e-12` tolerance) → `CLOCK_INVALID`.
6. otherwise → **`EXECUTABLE`** with the template's `composition_id`.

Only template-bound shapes cause adapter *construction*, and then purely to read
constructor metadata (`engine_id`, `native_timestep`) and to power `resolve_contracts`;
nothing is initialized or stepped — the same static-only discipline as Stage 1+2.
Non-executable template-bound verdicts still carry a `composition_id`; `EXECUTABLE`
has empty reasons.

---

## 5. IMPLEMENTED — `composition_id`: content-addressed composition identity

```python
def composition_id(shape, *, contracts, schedule, requires, macro_timestep=0.2) -> str
```

- `sha256(json.dumps({shape: shape_id, contracts: contracts_key(contracts),
  schedule: [...], requires: sorted(set(requires)), macro_timestep}, sort_keys=1))[:24]`
  — the repo's 24-hex convention.
- Distinguishes: same components + different variant (different `shape_id`), same
  components + different contracts or schedule or requires or macro timestep
  (different `composition_id`). Contract sets are validation metadata — they
  distinguish `composition_id`, **not** `world_hash` (matches design §13).
- `template_composition_id(template)` derives it from a template. Content-addressed,
  deterministic across runs.

---

## 6. IMPLEMENTED — world generation (Stage 4) + `ComponentSpec.variant`

```python
class ComponentSpec:
    id: str
    config: dict[str, Any]
    variant: str | None = None          # NEW, Task 2.3 Stage 4
```

- `variant` is declared metadata (the concrete binding identity of a dual-variant
  component id), never a factory argument. `""`/whitespace normalizes to `None`;
  non-str rejects with `TypeError`. `from_dict` reads `data.get("variant")`, so
  legacy variant-free YAML still loads.
- `as_dict()` always emits `id`/`variant`/`config`, so the variant participates in
  `WorldDefinition.as_dict()` → `world_hash` → `run_id_of`: **world identity is now
  variant-aware** (design §13).

```python
def generate_world(template) -> WorldDefinition:
```

- Components = `ComponentSpec(binding.component, dict(template.component_configs[...]),
  variant=binding.variant)` per canonical binding; `requires`/`schedule` =
  template's; `macro_timestep`/`max_steps`/`seed`/`config` = template's; `id` =
  `world_id`.
- `generate_world` **never constructs or consults an adapter** (proven by test with
  patched factories). Deterministic and immutable: fresh dicts on every call.
- The generated world and the facade world are identical except for the explicit
  variant stamps (and hence differ in `run_id_of` while composing to the **same**
  trajectories — bitwise-proven, §12).

---

## 7. IMPLEMENTED — the three experiment-owned templates

Templates are co-located in the coupling modules (science stays where it has always
lived):

| template `name` | binding set | `world_id` | contracts | executor_ref |
|---|---|---|---|---|
| `morphogenesis` | `{mesa, py-pde, pymunk/walls}` | `chemo_morphogenesis` | `MORPHOGENESIS_CONTRACTS` | `chemomech.simulation.run_world` |
| `field_guided_movers` | `{py-pde, pymunk/movers}` | `field_guided_movers` | `FIELD_GUIDED_MOVERS_CONTRACTS` | `experiments.field_guided_movers.model.run_world` |
| `adaptive_network` | `{py-pde, pymunk/walls, network}` | `adaptive_network` | `NETWORK_MORPHOGENESIS_CONTRACTS` | `experiments.network_morphogenesis.experiment.run_network_world` |

Each `operations =` the coupling module's op-name tuple (the exact set its
`build_*_operations` registers), and `component_configs` are copied from that
module's world builder components (`{spec.id: dict(spec.config)}`). `executor_ref`
is an opaque identifier the core never resolves.

---

## 8. IMPLEMENTED — `experiments/catalog.py`: the repository composition universe

```python
repository_surfaces()    # keyed by ComponentBinding across default + C + B registries
repository_bindings()    # the five distinct bindings, canonically sorted
repository_templates()   # CouplingTemplateRegistry with the three templates
build_repository_adapters(shape, template)   # constructor-only dispatch
build_repository_catalog(generate_worlds=False)
```

- The five-binding universe is derived from the actual registries (never
  hard-coded): `mesa`, `py-pde`, `network`, `pymunk/walls`, `pymunk/movers`.
- Surfaces are merged per `(component, variant)` key **across** registries, because
  one registry id = one builder: `walls` comes from `default_registry()`, `network`
  from the C registry, `movers` from the B registry. Adapter dispatch in
  `build_repository_adapters` mirrors that (network→C, movers variant→B, else
  default).

---

## 9. IMPLEMENTED — `CompositionCatalog` (Stage 5, query/explain facade)

```python
@dataclass(frozen=True)
class CatalogCandidate:
    shape, status, shape_id, bindings, missing_capabilities,
    template, reason, composition_id, generated_world
    @property generated_world_available   # status == EXECUTABLE
    def explain()

class CompositionCatalog:
    def __init__(space, surfaces, templates, *, build_adapters, generate_worlds=False)
    all() / executable() / invalid() / by_status(s) / by_shape_id(id) / status_counts() / explain(id)
```

- Built **eagerly but cheaply**: every shape of the space is classified exactly once
  in the deterministic enumeration order; `generate_worlds=True` additionally
  materializes the `WorldDefinition` of exactly the executable candidates. Nothing is
  simulated, persisted, searched, or written.
- The catalog is an immutable snapshot — query only. `status_counts()` returns
  sorted-count dict; `explain(shape_id)` gives a human-readable verdict
  (`shape`, `status`, missing capabilities, matched template, composition id, reason)
  per candidate, the design §21 UX.

---

## 10. IMPLEMENTED — the 23-shape catalog: exact, pinned counts

Enumerating the five bindings at `min_size=1..max_size=4` with variant exclusivity
(`walls` and `movers` never share a shape):

| classification | count | shapes |
|---|---|---|
| `EXECUTABLE` | **3** | `{mesa, py-pde, pymunk/walls}`, `{py-pde, pymunk/movers}`, `{py-pde, pymunk/walls, network}` |
| `COUPLING_UNAVAILABLE` | **4** | `{py-pde, pymunk/movers, mesa}`, `{py-pde, pymunk/walls, mesa, network}`, `{py-pde, pymunk/movers, network}`, `{mesa, network, py-pde, pymunk/movers}` |
| `CAPABILITY_INVALID` | **16** | the remaining 23 − 7 (the design's "~17 bottom shapes" — measured 16 exactly) |
| `COUPLING_INVALID` / `SCHEDULE_INVALID` / `CLOCK_INVALID` | **0** (real) | covered defensively by synthetic templates |
| **total** | **23** | 5 / 9 / 7 / 2 per size k |

All three design §11 unwired capability-valid shapes classify `COUPLING_UNAVAILABLE`
(never `EXECUTABLE`, never invented coupling); the fourth (`{mesa, network, py-pde,
pymunk/movers}`) is also capability-valid (the `movers` variant supplies
`geometry_provider`, `mesa`+`network` hide no unprovided requirement) but unwired.
Counts pinned in `tests/test_catalog.py`; nothing changes them silently.

---

## 11. IMPLEMENTED — repo hygiene, guards, and core purity

- `templates.py` and `catalog.py` are experiment-free and operation-name-free: the
  scheduler op-name scan plus dedicated core-purity scans (16 experiment-word
  substrings + 9 operation names) pass for both modules.
- `core/world.py`'s `variant` docstring is the only place an experiment vocabulary
  word ("mesa"/"py-pde") appears — as identifying *the* repo's dual-variant example;
  the low-level purity scans target `templates.py`/`catalog.py` only (same precedent
  as `composition.py`'s test in Stage 1+2).
- Guarded-core hashes re-baselined (sanctioned Task 2.3 extension path, documented in
  `tests/test_field_guided_movers.py`): `__init__.py` and `world.py` re-pinned,
  `templates.py` + `catalog.py` added;
  `tests/test_network_morphogenesis.py` reuses the dict automatically.
- All 19 core modules export their complete API through `__init__.py`.
- No scientific baseline parameter changed; nothing was deleted; no prior test
  weakened.

---

## 12. IMPLEMENTED — tests (3 new files, 83 collected tests)

**`tests/test_templates.py` (37, Stage 3 + taxonomy)**

well-formedness (blank name/bindings/world_id/contracts/schedule/operations →
`ValueError`; frozen; non-str macro_timestep/max_steps), registry (empty, duplicate
name / duplicate shape → `DuplicateTemplateError`, canonical-shape lookup, sorted
templates, `from_sequence`, serialization round-trip), classification
(3 EXECUTABLE with matching `composition_id` == `template_composition_id`, the
4 COUPLING_UNAVAILABLE, synthetic COUPLING_INVALID / SCHEDULE_INVALID / CLOCK_INVALID,
funnel precedence + explain text, CAPABILITY_INVALID still template-annotated,
non-executable template-bound verdicts carry `composition_id`), `composition_id`
(deterministic, distinguishes contracts/schedule/requires/macro timestep, 24 hex),
and the ops-drift guard `set(build_*_operations(generate_world(template) components))
== set(template.operations) == set(<EXP>_SCHEDULE)`.

**`tests/test_world_generation.py` (22 = 19 fast + 3 slow, Stage 4)**

determinism; variant stamps (walls/movers/None per template); `run_id_of` generated
vs facade differs but is deterministic; dict + YAML round-trips incl. legacy
variant-free YAML; compose smoke through the generic core (default/C/B registry per
template, 1-step, `compose_into`); immutability/isolation (mutating one generated
world never touches another or the template); adapter-free generation (patched
`AdapterFactory.build`/`ComponentRegistry.build` raise on construction); per-component
config identity vs the facade world; headless-executor-module invariance; **slow
A/B/C bitwise**: the generated worlds executed through the plain `AlchemistEngine`
+ default/C/B registry reproduce the experiment-facade 160-step trajectories exactly
(recursive `_close`/`_assert_same` tolerance comparison of the full trajectory dicts).

**`tests/test_catalog.py` (24, Stage 5)**

status counts {16, 4, 3} and total 23; query surfaces `all/executable/invalid/
by_status`; bindings↔shape consistency; `by_shape_id`/`explain`; EXECUTABLE candidates
exactly the 3 templates with matching `composition_id`; COUPLING_UNAVAILABLE unbound
reasons; `generate_worlds` opt-in (exactly 3 materialized, equal to
`generate_world(template)`); no-simulation guarantee (BaseAdapter `initialize`/`step`/
`shutdown`/`apply_event` patched to raise during catalog construction);
classification-only adapter builds (direct `CompositionCatalog` construction isolates
the 8 template-matched builds from `build_repository_catalog()`'s extra 10
surface-derivation builds — `repository_bindings()` re-derives surfaces); determinism
across rebuilds; core purity scans.

---

## 13. Validation results (closing gate)

- `uv run pytest tests/ -m "not slow"` — **353 passed**, 6 deselected, 0 failures.
- Slow suite (`-m "slow"`) — **6 passed** (3 canonical regression + 3 world-generation
  bitwise); full suite total **359 passed**, 0 failures.
- Slow bitwise world-generation runtime ≈ 100 s for all 6 slow tests (160-step runs).
- `uv run python run_validation.py` — A–G **PASS** (bitwise-identical replay intact).
- `uv run python run_stability.py` — S1–S6 **PASS**.
- `uv run ruff check .` — clean.
- `uv run pyright` — 0 errors.
- `uv sync` — environment already at lock; no dependency changed.
- `uv run python run_catalog_demo.py --generate-worlds` — 23 shapes, 16/4/3, writes
  the 3 executable worlds as YAML (`generated_worlds/` by default).

---

## 14. Limitations (preserved, not hidden)

- Classification is **static**: `EXECUTABLE` means "statically known to compose" —
  it says nothing about whether the run is scientifically meaningful.
- Capability surfaces / clock divisibility are read by **constructing** adapters
  (constructor-only, never stepped), the same documented Stage 1+2 convention.
- Only 23 shapes × 1 catalog today; the `CompositionCatalog` is an in-memory snapshot,
  not persisted, and there is **no search integration** yet.
- The clock gate uses float divisibility with a `1e-12` tolerance (native dts 0.5/0.2/
  0.1 divide 0.2 cleanly; a hypothetical `0.3` dt would be rejected).
- Determinism is same-runtime / same-environment (the repo-wide standing limitation).

---

## 15. Confirmed NOT implemented (Task 2.4 + Stage-5 parasole)

- `CompositionSearcher` / search integration over the candidate space — NOT started.
- `composition_id` lineage table, lineage UX, discovery demo — NOT started.
- Automatic coupling inference, plugin discovery, AI/ML/optimizer/distributed
  execution — NOT started (explicitly out of scope).
- No new dependencies; no new experiment; no simulation-science change.

---

## 16. Files changed

- `src/sim_alchemist/core/templates.py` — NEW (Stages 3+4 deliverable).
- `src/sim_alchemist/core/catalog.py` — NEW (Stage 5 deliverable).
- `src/sim_alchemist/core/world.py` — MOD (`ComponentSpec.variant`, normalization,
  from_dict, as_dict).
- `src/sim_alchemist/core/__init__.py` — MOD (re-exports templates + catalog API).
- `chemomech/coupling.py`, `experiments/field_guided_movers/coupling.py`,
  `experiments/network_morphogenesis/coupling.py` — MOD (template builders).
- `experiments/catalog.py` — NEW (repository surfaces/bindings/templates/adapters).
- `run_catalog_demo.py` — NEW (CLI demo).
- `tests/test_templates.py`, `tests/test_world_generation.py`, `tests/test_catalog.py` —
  NEW (80 tests).
- `tests/test_field_guided_movers.py`, `tests/test_network_morphogenesis.py` —
  MOD (guarded-core dict re-baselined / comments).
- Docs: `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md`, this report,
  `TASK_2.3_CHECKPOINT.md`.<br>

Same gates as Task 1.8/2.0 milestones: fast suite + validation + stability + lint +
types green; nothing to paper over.