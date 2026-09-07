# TASK 2.2 REPORT — Coupling-Contract Layer + Pre-Execution Composition Validation

**Status:** COMPLETE
**Date:** 2026-09-07
**Milestone:** Task 2.2 (Build mode of Task 2.1's §14 minimal implementation)
**Scope:** Framework-only coupler — new `src/sim_alchemist/core/contracts.py`; optional
`contracts=` on `compose()`/`compose_into()`; real declared contracts for Experiments
A, B, C; adapter variant + capability + grid + payload metadata; capability-valid /
coupling-invalid rejection proof. **Task 2.3 NOT started.**

---

## 1. Objective

Task 2.1 identified the architectural gap: **capability-compatible ≠ coupling-compatible
≠ executable composition.** `resolve_capabilities` is name-only, and scientific couplings
live as implicit closures inside each experiment's operations dict. Recall the motivating
case:

| Set | capability-valid? | wired today? |
|---|---|---|
| py-pde, pymunk(walls), mesa | yes | A |
| py-pde, pymunk(movers) | yes | B |
| py-pde, pymunk(walls), network | yes | C |
| py-pde, pymunk(movers), network | **yes** | **no experiment** |

The final row is capability-valid yet has no declared coupling — nothing ever detected it.
Task 2.2 closes that gap by adding a **declarative coupling-contract layer** that:

- states, as data, every producer→consumer scientific edge each experiment's schedule
  materializes;
- validates those declared edges against the live composed adapters **before any engine
  step**, raising an actionable `UnresolvedContractError` listing every missing edge;
- **never invents or synthesizes couplings** — an undeclared (capability-valid) edge is a
  rejection, not a prompt to auto-couple;
- is strictly additive (optional `contracts=`), keeping Experiments A/B/C bitwise identical
  to the Task 2.1 baseline when the parameter is omitted;
- binds adapters **by id + variant, never positionally**, so an executor cannot silently
  mis-wire when component order changes.

---

## 2. IMPLEMENTED — `core/contracts.py` (the coupling-contract layer)

New core file, stdlib only, zero experiment knowledge, no banned experiment op-name
substrings (`contracts.py` verified clean by the `test_scheduler` scan):

| Concept | Description |
|---|---|
| `PayloadItem(key, shape)` | frozen; one shared state key + its payload shape; `as_dict()`/`from_dict()` |
| `SUPPORTED_PAYLOAD_SHAPES` | `{"scalar","vec2","vec2_list","bool_2d","array_1d"}` |
| `CouplingContract` | frozen dataclass; `payload` accepts `(key, shape)` pairs **or** `PayloadItem`, normalized to `PayloadItem`; defaults `timing="same-macro-step"`, `mechanism="direct"`, `variant=None`, `coordinate_system=None`, `grid=None`; `__init__` validates non-empty strings, variant str-or-None, grid int>`0`-or-None; `as_dict()`/`from_dict()` round-trip |
| `ContractIssue` | frozen; one concrete problem: `contract`, `producer`, `consumer`, `variant`, `what`, `fix` |
| `UnresolvedContractError` | lists every issue, deterministically sorted, with the `what`/`fix` remediation baked in; message surfaces the producer→consumer edge + variant for each rejection |
| `resolve_contracts(adapters, contracts)` | the validator (see §3) |
| `adapter_by_id(adapters, component_id)` | id + variant metadata lookup (never positional) |
| `contracts_key(contracts)` | sha256 of the canonical JSON of the contract set — deterministic content identity |

### The resolver rules (`resolve_contracts`)

Validation order: identity → capability → coupling → payload → timing/mechanism →
coordinate system → grid → self/duplicate keys. Each failure yields a `ContractIssue`.
Rules enforced (all but the last are hard errors):

1. **Presence** — every declared producer and consumer must exist as a composed adapter.
2. **Capabilities** — the producer must declare the contract's `producer_capability`;
   the consumer must declare the `consumer_capability`.
3. **Variant binding** — `_endpoint_variant(adapter)` reads the adapter's `variant`
   metadata. If a contract pins a `variant`:
   - neither endpoint is a variant component ⇒ fail ("pins variant but no tagged endpoint");
   - a tagged endpoint's variant ≠ pinned variant ⇒ fail ("endpoint is 'movers', not 'walls'").
   If a contract does **not** pin a variant but an endpoint *is* variant-tagged ⇒ fail
   ("variant component but contract does not pin a variant"). Untagged components (no
   `variant` metadata) are variant-agnostic.
4. **Payload** — no duplicate keys; every shape ∈ `SUPPORTED_PAYLOAD_SHAPES`; each key
   present in the producer's `state_keys` **when the producer declares them** (producers
   that declare no state vocabulary are not key-checked — documented limitation, §9).
5. **Timing / mechanism** — must be `same-macro-step` / `direct` (current vocabulary).
6. **Coordinate system** — if the contract declares one, it must be in every endpoint's
   announced coordinate systems; endpoints that both announce systems must agree.
7. **Grid** — if both endpoints expose a grid and they differ ⇒ fail; if the contract
   declares a grid it must match each endpoint that exposes one.
8. **Self-edge** — `producer == consumer` ⇒ fail.
9. **No inference (soft rule, by construction)** — with an empty contract set nothing is
   checked and nothing is invented (unit-tested §7 M).

---

## 3. IMPLEMENTED — optional `contracts=` threading through the composer

`compose()` and `compose_into()` now accept an optional `contracts: Sequence[CouplingContract]
| None = None`. The composition stage order is:

```
resolve_capabilities  ->  resolve_contracts  ->  _install
```

`resolve_contracts` runs only when `contracts` is non-empty (or non-None); when omitted the
behavior is **exactly** today's. Docstrings updated. This is the strictly-additive seam Task
2.1 §7 required — the guarded-core re-baseline happened exactly once for this sanctioned
extension (`composer.py`, `__init__.py`, `contracts.py`).

---

## 4. IMPLEMENTED — adapter metadata (variant / state_keys / grid / coordinate system)

`BaseAdapter` gains `_variant`, `_state_keys`, `_grid`, `_coordinate_system` (defaults
`None`, `()`, `None`, `"unit-square-2d"`) and read-only properties. Concrete adapters set:

| Adapter | variant | state_keys | grid |
|---|---|---|---|
| `PyPDEAdapter` | — | `u, v, blocked, gradient, sources` | n |
| `PymunkAdapter` (walls) | `walls` | `walls, geometry, blocked, wall_tracks, forces, wall_adds, wall_removes` | n |
| `MesaAdapter` | — | `agents, intentions` | — |
| `MoversAdapter` (B) | `movers` | `positions, velocities, count, forces` | n |
| `AdaptiveNetworkAdapter` (C) | — | `load, positions, weights, edge_throughput` | — |

This is what lets the contract layer resolve the `pymunk` dual-variant overload
(walls vs movers) that capability names alone cannot separate (Task 2.1 §2).

---

## 5. IMPLEMENTED — declared contracts (colocated with each coupling module)

Contracts live next to each experiment's operations builder so they cannot drift from the
closures they describe. `transform` is an opaque experiment-owned rule id; the core never
interprets it. All declare `coordinate_system="unit-square-2d"`; `grid` is left `None`
(grid equality is auto-checked from adapter metadata). Payload positions for B's mover-source
and C's load-source use shape `vec2_list` (positions) — a correction vs Task 2.1's plan.

**Experiment A — `MORPHOGENESIS_CONTRACTS`** (4 edges):
- `blocked-mask` pymunk(walls) `geometry_provider` → py-pde `field_masking`, `blocked/bool_2d`
- `gradient-force` py-pde `field_gradient` → pymunk(walls) `force_integration`, `gradient/vec2`
- `wall-intentions` mesa `agent_intentions` → pymunk(walls) `rigid_body`, `intentions/array_1d`
- `field-sensing` py-pde `scalar_field` → mesa `field_sensing`, `u/array_1d` + `v/array_1d`

**Experiment B — `FIELD_GUIDED_MOVERS_CONTRACTS`** (2 edges):
- `gradient-force` py-pde `field_gradient` → pymunk(movers) `force_integration`, `gradient/vec2`
- `mover-source` pymunk(movers) `geometry_provider` → py-pde `field_sources`, `positions/vec2_list`

**Experiment C — `NETWORK_MORPHOGENESIS_CONTRACTS`** (5 edges):
- `blocked-mask` pymunk(walls) `geometry_provider` → py-pde `field_masking`, `blocked/bool_2d`
- `blocked-reweight` pymunk(walls) `geometry_provider` → network `network_diffusion`, `blocked/bool_2d`
- `gradient-force` py-pde `field_gradient` → pymunk(walls) `force_integration`, `gradient/vec2`
- `load-source` network `network_diffusion` → py-pde `field_sources`, `load/array_1d` + `positions/vec2_list`
- `throughput-grow` network `network_diffusion` → pymunk(walls) `rigid_body`, `edge_throughput/scalar`

---

## 6. IMPLEMENTED — facades & the executor hardened to id-based lookup

- `chemomech/engine.py`, `experiments/field_guided_movers/model.py`,
  `experiments/network_morphogenesis/model.py` — facades now pass
  `contracts=<EXPERIMENT>_CONTRACTS` through `compose_into`.
- `experiments/network_morphogenesis/experiment.py` `run_network_world` — replaced the
  Task 2.1-flagged **positional** `adapters[0..2]` indexing with `adapter_by_id` (`"py-pde"`,
  `"pymunk"`, `"network"`) and passes `contracts=NETWORK_MORPHOGENESIS_CONTRACTS`. This
  closes Task 2.1 §10's #3 risk (silent mis-wiring under component reorder).

---

## 7. IMPLEMENTED — tests (`tests/test_contracts.py`, ~24 tests)

| Group | Coverage |
|---|---|
| **A–M core resolver** | A valid resolve on all three experiment adapter sets; B payload normalization + `PayloadItem` passthrough + `as_dict`/`from_dict` round-trip; C `contracts_key` deterministic; D missing producer; E missing consumer; F producer/consumer capability absent; G variant pinned but no tagged endpoint; H endpoint tagged but contract unpinned; I pinned ≠ tagged variant; J unsupported timing; K unsupported mechanism; L multi-issue deterministic ordering + actionable message (names contract, endpoints, variant, remediation, "before any engine stepped"); M empty contract set never infers couplings |
| **payload + coord/grid** | duplicate payload key fails; unsupported payload shape fails; payload key absent from producer `state_keys` fails; contract declares coordinate system the endpoints don't → fails; producer/consumer coordinate mismatch → fails; grid mismatch (both expose, differ) → fails; contract-declared grid vs endpoint mismatch → fails; self-edge fails; repeated validation yields identical issue list; `adapter_by_id` resolves by id (composed-unordered test) and raises on unknown id |
| **N–R composition + integration** | N each experiment's declared contracts resolve on its own world; O `compose` with `contracts=` vs without is **bitwise-identical** science for A (n=8), B (n=8), C (n=4); P the **gap proof** — Exp C world with `pymunk` overridden to `MoversAdapter` passes `resolve_capabilities` but `compose(..., contracts=NETWORK_MORPHOGENESIS_CONTRACTS)` raises `UnresolvedContractError` (walls-variant mismatches) **before `_install`** (asserts the pde adapter was never initialized); Q plain `compose` accepts A/B with their declared contracts; R B facade, C facade, and `run_network_world` all run with contracts wired (plus C network-replay determinism) |

The gap-proof test P is exactly the Task 2.1 §9 "capability-valid but coupling-invalid" case:
`resolve_capabilities` passes (pde + movers + network shape) yet the contract layer rejects
the walls-variant mismatch before any engine steps — proving the new gate fires where the
capability layer was blind.

---

## 8. IMPLEMENTED — repository hygiene

- Core changes confined to: **new** `core/contracts.py`; **modified** `core/composer.py`
  (optional `contracts=`, `resolve_contracts` stage), `core/__init__.py` (re-exports).
  No other core file changed.
- Guarded-core immutability guard (`tests/test_field_guided_movers.py` `CORE_COMMIT_HASHES`,
  reused by `tests/test_network_morphogenesis.py`) **re-baselined** with a "Task 2.2
  sanctioned extension" note (the sanctioned milestone pattern from Tasks 1.3/1.6/1.7/1.8/
  1.9/2.0); assertion messages now read "Task 2.2 must not change the core".
- Banned op-name scan (`test_scheduler.py`) confirmed clean: `contracts.py` has zero hits of
  `geometry.sync`/`field.step`/`physics.force`/`physics.step`/`agents.step`/`agents.apply`/
  `movers.force`/`movers.step`/`field.source`.
- **No new dependencies** (stdlib `hashlib`/`json`/`dataclasses` only). Environment unchanged.
- Documents updated: this report, `PROJECT_STATE.md`, `IMPLEMENTATION_PLAN.md`.

---

## 9. Scientific / architectural limitations (preserved, not hidden)

- **Payload keys are only validated against a producer that declares `state_keys`.**
  A producer that exposes no state vocabulary skips the key check (documented; all three
  experiments' producers do declare their keys, so the guarantees hold for the wired worlds).
- **The contract layer validates declared edges; it cannot invent scientific meaning.** It
  states "this schedule materializes edge X", not what X *means* — that stays in the
  experiment-owned `transform` closures (Task 2.1 §5 constraint).
- **No new model physics / no new simulation concept.** Contract validation is pure
  pre-execution bookkeeping over the existing adapters. Existing documented limitations
  (clamped frozen-wall PDE approximation, uncalibrated network diffusion rule, reservoir
  recharging, thin frictionless wall rods, same-runtime determinism) are untouched.
- **Mismatched-pair detection is exhaustive of the declared set, not of the universe:**
  an *undeclared but capability-valid* edge (e.g. the 4th row of §1) is rejected only when a
  shape is composed with a contract set that would need it; composing with an empty contract
  set remains exactly today's (unchecked) behavior. The guarantee is "declared edges are
  honored and never invented", not "every possible coupling is enumerated".

---

## 10. Validation results (closing gate)

- `pytest` — **full suite PASSES: 233 passed** (incl. the ~24 new Task 2.2 contract tests and
  the slow 160-step canonical regressions). No prior test weakened.
- `run_validation.py` — validation **A–G all PASS** (canonical baseline bitwise unchanged).
- `run_stability.py` — stability **S1–S6 all PASS**.
- `ruff check .` — **CLEAN**.
- `pyright` — **0 errors, 0 warnings**.

---

## 11. File tree (new / changed)

```
src/sim_alchemist/core/
    contracts.py     NEW  CouplingContract, PayloadItem, ContractIssue,
                          UnresolvedContractError, resolve_contracts, adapter_by_id,
                          contracts_key, SUPPORTED_PAYLOAD_SHAPES
    composer.py      MOD  optional contracts= on compose/compose_into; resolve_contracts
                          stage between resolve_capabilities and _install
    __init__.py      MOD  re-exports the contract API
src/sim_alchemist/adapters/
    base.py          MOD  _variant/_state_keys/_grid/_coordinate_system + properties
    pde.py pymunk.py mesa.py  MOD  variant, state_keys, grid metadata
experiments/field_guided_movers/model.py  MOD  MoversAdapter variant/state_keys/grid
experiments/network_morphogenesis/adapter.py  MOD  network state_keys
chemomech/coupling.py        MOD  MORPHOGENESIS_CONTRACTS
chemomech/engine.py          MOD  facade contracts + id lookup
experiments/field_guided_movers/coupling.py  MOD  FIELD_GUIDED_MOVERS_CONTRACTS
experiments/field_guided_movers/model.py     MOD  facade contracts + id lookup
experiments/network_morphogenesis/coupling.py   MOD  NETWORK_MORPHOGENESIS_CONTRACTS
experiments/network_morphogenesis/model.py      MOD  facade contracts + id lookup
experiments/network_morphogenesis/experiment.py MOD  run_network_world -> adapter_by_id +
                                                     contracts (positional indexing removed)
tests/
    test_contracts.py  NEW   ~24 tests (core A–M, payload/coord/grid, composition N–R)
    test_field_guided_movers.py  MOD  CORE_COMMIT_HASHES re-baselined (Task 2.2 note)
    test_network_morphogenesis.py MOD  guard message -> Task 2.2
TASK_2.2_REPORT.md     NEW  this report
PROJECT_STATE.md       MOD  milestone / architecture / validation updated
IMPLEMENTATION_PLAN.md MOD  Task 2.2 marked complete; Task 2.1 status corrected
```

---

## 12. What Task 2.3 (next, NOT started) could build

Nothing planned or started. Natural candidates per `IMPLEMENTATION_PLAN.md` (still future):
`core/composition.py` (`ComponentOption`/`CompositionSpace`/
`enumerate_composition_shapes()`, the 3-stage resolver over the contract layer built here),
a `CompositionSearcher` shape-loop over `SearchRunner` with shape-aware identity, a compact
`compositions` lineage table, and the discovery demo over the wired shapes. **Task 2.3 is not
to be started until issued.**