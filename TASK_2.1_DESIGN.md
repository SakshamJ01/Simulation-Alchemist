# TASK 2.1 — Cross-Composition Compatibility and Discovery Design

**Status:** PLAN-ONLY design deliverable. No source code was modified by this
task. Nothing here is implemented; §14 describes the *smallest future
implementation* for a later Build task.

---

## 1. Current architecture audit

| Layer | What exists today | Gap for cross-composition search |
|---|---|---|
| Components | 4 engine ids: `mesa`, `py-pde`, `pymunk`, `network`; `pymunk` is dual-variant (`PymunkAdapter` wall regimen vs `MoversAdapter` point probes) | Same id ⇒ different contract shape; nothing declares which variant is bound |
| Capabilities | `Capability(name, version, metadata)` + `CapabilitySet` (`core/capabilities.py`); `satisfies()` matches by **name only** | Semantics are invisible ("walls" and "movers" both claim `rigid_body`); version/metadata unused by resolution |
| Composer | `build_components → resolve_capabilities → compose_into` (`core/composer.py:36-102`); validates capability names + schedule op names against the experiment's operations dict | **No coupling-edge validation**; a name-satisfiable shape is assumed runnable |
| Couplings | Implicit closures inside each experiment's operations dict (`chemomech/coupling.py:135`, `experiments/field_guided_movers/coupling.py:139`, `experiments/network_morphogenesis/coupling.py:162`) | Edges exist as code, not data; no enumerable, checkable representation |
| Schedules | Named macros (`geometry.sync`, `physics.force`, `physics.grow`, `network.route`, `field.source`, `agents.apply`, …) dispatched by core `StepScheduler` | Op names are opaque strings; schedule validation checks presence only |
| Events | Typed `EventType`/`EventBus` exist (`core/events.py`) | **Dormant** in the runtime path — couplings reach into adapter state directly (`pde.set_blocked`, `pymunk.apply_force`, `pde.apply_sources`, `network.set_load`) |
| Executors | `run_network_world` resolves adapters **by position** (`adapters[0..2]`, `experiments/network_morphogenesis/experiment.py:169-171`) | Silent mis-wiring if component order changes |
| Registry | `ComponentRegistry` maps id → single factory; `default_registry()` = `mesa`/`py-pde`/`pymunk`; experiments override/register (`network`, movers-under-`pymunk`) | One factory per id, no variant metadata |

Adapter capability surface (verified against source):

| Adapter | provides | requires |
|---|---|---|
| `PyPDEAdapter` (`py-pde`) | scalar_field, reaction_diffusion, spatial_sampling, field_masking, field_gradient, field_sources | geometry_provider |
| `PymunkAdapter` (`pymunk`/walls) | rigid_body, collision_geometry, force_integration, geometry_provider | field_gradient, agent_intentions |
| `MesaAdapter` (`mesa`) | agent_population, agent_step, field_sensing, agent_intentions | scalar_field |
| `MoversAdapter` (`pymunk`/movers, Exp B) | rigid_body, force_integration, geometry_provider | scalar_field, field_gradient, field_sources |
| `AdaptiveNetworkAdapter` (`network`, Exp C) | network_diffusion, agent_intentions | reaction_diffusion, rigid_body |

Clock: `macro_timestep = 0.2`; native dt — py-pde 0.2, mesa 0.2, network 0.2,
pymunk 0.05 (≈4 substeps). `SimulationClock` already validates
`macro % native == 0`.

World model: `WorldDefinition{id, components(ComponentSpec: id+config),
requires, schedule, macro_timestep, max_steps, seed, config}` —
**no coupling/edge data**.

---

## 2. Capability compatibility vs coupling compatibility

Three distinct notions, only the first is checked today:

1. **Capability-compatible** — every adapter `requires` and the world `requires`
   are name-satisfied by the union of `provides`. Passes `resolve_capabilities`.
2. **Coupling-compatible** — every producer→consumer data edge the schedule
   materializes is hostable by that adapter set (state keys, dtype/shape,
   coordinate system, grid size, timing, variant binding). **Not represented
   anywhere.**
3. **Executable** — capability + coupling compatible **and** a registered
   operations dict whose every scheduled op name exists, **and** clock
   divisibility.

Exhaustive name-level enumeration over the five adapter variants shows the
capability filter alone can no longer separate the wired experiments from
unwired shapes:

| Set | Pymunk variant | Capability-valid? | Executable today? |
|---|---|---|---|
| py-pde, pymunk, mesa | walls | yes | **A — wired** |
| py-pde, pymunk | movers | yes | **B — wired** |
| py-pde, pymunk, network | walls | yes | **C — wired** |
| py-pde, pymunk, mesa | movers | yes | **no — no experiment** |
| py-pde, pymunk, network | movers | yes | **no — no experiment** |
| py-pde, pymunk, mesa, network | walls | yes | **no — no experiment** |
| py-pde, pymunk, mesa, network | movers | yes | **no — no experiment** |

All other subsets fail `resolve_capabilities` at name level (see §9).

**Conclusion (the architectural gap):** the capability layer enumerates the
*searchable* shapes correctly but is blind to whether any declared coupling
edge exists. Discovery needs a coupling-contract layer that *validates declared
scientific edges and never invents or synthesizes couplings itself*.

---

## 3. Existing coupling graph (extracted from the operations closures)

```
Experiment A   mesa ───────────► pymunk(walls)   agents.apply: pending intentions → wall add/remove
               pymunk(walls) ──► py-pde          geometry.sync: blocked mask → field_masking
               py-pde ─────────► pymunk(walls)   physics.force: field gradient → bounded force
               py-pde ─────────► mesa            field → sensing (adapter wiring)

Experiment B   py-pde ─────────► pymunk(movers)  movers.force: gradient → bounded force
               pymunk(movers) ─► py-pde          field.source: mover positions → source/sink deposit

Experiment C   network ────────► py-pde          field.source: node load → chemical source
               network ────────► pymunk(walls)   physics.grow: highest-throughput edge → wall add
               pymunk(walls) ──► py-pde          geometry.sync: blocked → field_masking
               pymunk(walls) ──► network         geometry.sync: blocked → edge reweight
               py-pde ─────────► pymunk(walls)   physics.force: gradient → force
```

Shared implicit assumptions: unit-square domain [0,1]², common grid `n×n`,
`blocked` boolean arrays, source-dict schema `{x, y, u, v, radius}`. All of
these are coupling data that must become declarative.

---

## 4. Composition compatibility matrix

Row = producer of an edge, column = consumer. `✓` = acted on by a wired
experiment, `⚠` = capability-valid but no experiment binding (edge would be
invented), `—` = no edge exists/meaningful.

| producer \ consumer | mesa sensing | pymunk walls | pymunk movers | network | py-pde |
|---|---|---|---|---|---|
| py-pde (field/gradient/sources) | ✓ | ✓ gradient→force | ✓ gradient→force + sources consumed | — | — |
| pymunk walls (geometry/blocked) | — | — | ⚠ | ✓ blocked→reweight | ✓ blocked→mask |
| pymunk movers (positions) | — | ⚠ | — | ⚠ | ✓ source deposit |
| mesa (intentions) | — | ✓ wall add/remove | ⚠ un-consumed | — | — |
| network (load/positions/topology) | — | ✓ grow walls | ⚠ | — | ✓ load→source |

Matrix drives the CompositionSpace: a candidate shape is coupling-valid iff
every **declared** contract edge in its template set lands on a `✓` (or a
deliberately wired new edge provided by the experiment's own coupling code).

---

## 5. Proposed coupling-contract model

A data-only, stdlib, frozen dataclass — new file `core/contracts.py` (future):

```python
@dataclass(frozen=True)
class CouplingContract:
    name: str                          # e.g. "blocked-mask", "gradient-force"
    producer: str                      # component id providing the source
    producer_capability: str           # e.g. "geometry_provider"
    variant: str | None = None         # disambiguate "walls"/"movers" on pymunk
    consumer: str                      # component id receiving
    consumer_capability: str           # e.g. "field_masking"
    payload: tuple[tuple[str, str], ...]  # (state_key, dtype/shape), e.g. (("blocked","bool_2d"),)
    transform: str                     # stable experiment-owned rule id, or "direct"
    timing: str                        # "same-macro-step"
    mechanism: str = "direct"          # today always "direct"; events are future
```

Design constraints (user-mandated):

- **Coupling contracts validate declared scientific edges; they never invent
  couplings.** A contract states "this experiment's schedule materializes data
  edge X between producer P and consumer C". If a candidate shape cannot host a
  declared edge, the shape is rejected — the resolver never tries to fabricate
  edge P→C that no experiment wiring implements.
- **Experiment-specific transformations remain outside the generic core.** The
  contract names the *transform id* (`transform: "tanh-gradient-force"`,
  `"source-deposit"`, `"blocked-mask"`, `"load-source"`, `"throughput-grow"`,
  `"blocked-reweight"`); the actual rule stays a closure in the experiment's
  coupling module. The core never knows what the transforms do.
- Declarations are colocated with each experiment's operations builder so they
  cannot drift from the closures they describe.
- `world.requires` stays capability-oriented; each experiment also exposes
  `CONTRACTS: tuple[CouplingContract, ...]` as the coupling-oriented twin.

---

## 6. CompositionSpace design

```python
@dataclass(frozen=True)
class ComponentOption:                  # one concrete binding of an id
    component_id: str
    variant: str                        # "walls" | "movers" | "core"
    factory_key: str                    # registry lookup key

@dataclass(frozen=True)
class CompositionSpace:
    name: str
    universes: tuple[tuple[str, tuple[ComponentOption, ...]], ...]  # dimension → options
    required_capabilities: tuple[str, ...]
    contract_templates: tuple[str, ...] # Contract edge names each shape must host
    schedule_templates: tuple[tuple[str, ...], ...]
```

- `enumerate_composition_shapes()` — deterministic `itertools.product` over the
  universes (right-most dimension fastest, matching `MutationSpace` ordering),
  each tuple projected onto a `WorldDefinition`-compatible shape.
- `composition_id_of(space, shape)` — sha256 digest of (space id, shape) so
  lineage/identity is deterministic and content-addressed.
- Shapes carry the same clock/seed determinism guarantees as today: same
  (space, shape, mutation space, profile, seed) ⇒ same result.
- Variant awareness is mandatory: `ComponentOption.variant` is what lets the
  resolver distinguish walls vs movers under the id `pymunk`, closing the
  overload ambiguity of §2.

---

## 7. Coupling resolver design

Three deterministic, pre-simulation stages applied per candidate shape:

1. **Capability filter** — reuse/extend `resolve_capabilities`, variant-aware
   now that `provides`/`requires` differ per bound adapter (they already do).
2. **Contract filter (new)** — every contract edge named by the shape's
   template set must be live-hosted: producer present with matching capability
   + variant, consumer present with matching capability, payload keys and
   dtype/shape consistent, shared coordinate system (`unit-square-2d`) and grid
   `n`. Failures raise `UnresolvedContractError` listing the missing edges.
   No edge is ever created ad hoc (§5).
3. **Schedule + clock validation** — existing `compose_into` (op-name presence)
   plus `SimulationClock` divisibility; unchanged semantics.

Integration point (future, smallest change): an **optional** `contracts=...`
parameter threaded through `compose` / `compose_into`; when omitted, behavior
is exactly today's (A/B/C baselines untouched). No signature is broken, no
guarded core file needs re-baselining for the optional path.

---

## 8. Valid composition candidates (for future discovery)

Verified against the capability surface of §1 and the graph of §3:

1. `py-pde + pymunk(walls) + mesa` — **Experiment A** (wired; baseline).
2. `py-pde + pymunk(movers)` — **Experiment B** (wired).
3. `py-pde + pymunk(walls) + network` — **Experiment C** (wired).
4. `py-pde + pymunk(movers) + mesa` — capability-valid, **coupling-undefined**:
   agents sense the field, movers react to gradients, no wall regimen exists;
   Mesa `intentions` would be un-consumed. Reachable only if a new experiment
   declares the missing contracts.
5. `py-pde + pymunk(walls) + mesa + network` — capability-valid,
   **contractually ambiguous**: two `agent_intentions` producers (Mesa and the
   network); source injection could be driven by both. The contract layer must
   force an explicit choice of which producer feeds which consumer.

Candidates 1–3 run today (bitwise through the generic compose path). 4–5 are
the honest *discovery targets* — they require new experiment coupling code,
**not** framework code. This is the exact reason §2's gap matters.

---

## 9. Invalid composition examples

Name-level failures (already rejected by the current composer):

- `py-pde + mesa` — no `geometry_provider`.
- `mesa + pymunk(walls)` — no `scalar_field` / `field_gradient`.
- `py-pde + network` — no `rigid_body`.
- `pymunk(walls) + network` — no `reaction_diffusion` / `field_gradient`.
- `mesa + network` — multiple requirements unmet.
- `py-pde + pymunk(walls)` — no `agent_intentions`.

Capability-valid but coupling-invalid (must be rejected by the §7 contract
filter, not invented around):

- `py-pde + pymunk(movers) + network` — capability-valid yet no experiment
  binding; would imply duplicate/competing source injection and unplaced
  reservoir nodes. Without a declared contract set this shape must **not**
  compose.

---

## 10. Scientific safety rules

- **Adapter lookup is component-id + variant based, never positional.** The
  `adapters[0..2]` pattern in `experiments/network_morphogenesis/experiment.py`
  must be replaced by id/variant-keyed lookup in any executor before
  cross-composition search becomes safe.
- Contracts **validate declared edges; they never synthesize scientific
  meaning.** A rejected shape is a rejection, not a prompt to auto-couple.
- Contracts declare the coordinate system (`unit-square-2d`) and grid `n`, so
  mismatched pairs fail at compose time instead of silently running nonsense.
- No new model physics: composition searches combine **existing** adapters
  only. Existing documented limitations (clamped frozen-wall PDE approximation,
  uncalibrated network diffusion rule, reservoir recharging, thin frictionless
  wall rods) must be preserved in any future work.
- Determinism preserved: same (space, shape, mutations, profile, seed) ⇒ same
  result; `world_hash`/identity must incorporate shape identity once shapes
  become first-class.
- No global-optimality claims; bounded deterministic enumeration retained.
- `world_hash`/`run_id`-style identity, compaction, and lineage semantics are
  unchanged for already-wired worlds.

---

## 11. Discovery pipeline

```
CompositionSpace
  → enumerate_composition_shapes()        (deterministic product order)
  → resolver (capability → contract → schedule/clock)
  → per-shape binding {executor, observables builder, parameter specs}
  → existing SearchRunner.search()        (Tasks 1.6–2.0, unchanged)
  → record (shape_id + run_id) in LineageStore       (metadata only)
  → cross-shape rank_by_profile()         (existing Task 1.8 ranking)
```

- Fully reused machinery: `apply_mutations`, `ParameterSpec`, deterministic
  `run_id`, `rank_by_profile`, `BehavioralAnalysisRunner`, Task 2.0 diversity
  primitives.
- No GA/evolutionary/Bayesian/ML/RL/clustering; deterministic, sequential.
- Only compact metadata persists (a future `compositions` table); trajectories
  stay in memory.

---

## 12. Architectural risks (ranked)

1. **The searchable surface is minuscule.** Only 3 wired shapes exist; without
   new experiment coupling code, composition search discovers nothing beyond
   today's baselines. Mitigation: be explicit that discovery targets require
   new coupling modules.
2. **Variant overloading.** `rigid_body`/`agent_intentions`/`geometry_provider`
   are shared across semantically different adapters; contracts must key on
   variant, not id alone.
3. **Positional executor indexing.** `run_network_world` (and any analog) will
   silently mis-wire when a shape changes component order; a hard rule and a
   test are required before enucleation.
4. **Contract drift.** Declarations are hand-extracted from closures; mitigation
   is colocation with the ops builder plus a test asserting every declared edge
   maps to a named scheduled operation.
5. **Baseline disturbance.** Reaching validation state must be strictly
   additive (optional `contracts=`), keeping A/B/C bitwise identical; existing
   guarded-core hashes must not be re-baselined for the optional path.
6. **Timestep/coordinate mismatch** in unwired shapes (e.g., mesa+network) has
   no calibration; safety rules of §10 gate these.

---

## 13. Recommended implementation sequence (Build mode, future)

1. `core/contracts.py` — `CouplingContract` + `CouplingRegistry` (data only).
2. Variant tags surfaced on `AdapterFactory` (id + variant identity).
3. Declare `CONTRACTS` in the three coupling modules; wire the optional
   contract filter into `compose`/`compose_into`.
4. `core/composition.py` — `ComponentOption`/`CompositionSpace` +
   `enumerate_composition_shapes()` + the 3-stage resolver.
5. `CompositionSearcher` (shape loop over `SearchRunner`) + shape-aware
   identity + a compact `compositions` lineage table (metadata only).
6. New contract-validation tests; existing suite must stay green unchanged.
7. Demo runner over the three wired shapes (no new experiment code).

---

## 14. Exact smallest implementation task (for later Build mode)

> **Add `src/sim_alchemist/core/contracts.py`** defining `CouplingContract`
> (frozen dataclass per §5) and `resolve_contracts(adapters, contracts)` that
> validates each declared edge against the live adapters and raises
> `UnresolvedContractError` naming the missing producer/consumer edges.
> Thread it as an **optional** `contracts=` parameter through
> `compose`/`compose_into` (no signature break; omitted ⇒ today's behavior).
> Declare `CONTRACTS` in the three coupling modules and add tests proving the
> four capability-valid-but-unwired shapes (§8.4/8.5, §9) fail the contract
> filter while A/B/C still compose bitwise-identical.

This adds the coupling-compatibility gate to the framework with **zero new
simulation concept**, before any CompositionSpace/search work is attempted.

---

## §18 Required report (this design's closing summary)

- **Architecture gap:** capability resolution is name-only and couplings live as
  implicit closures; there is no declarative coupling-contract layer, so
  capability-valid shapes exist that are not executable and nothing detects the
  difference.
- **Recommended coupling model:** `CouplingContract` (§5) — data-only declared
  scientific edges, variant-aware, transform ids owned by experiments, validated
  in the composer via an optional contract filter (§7).
- **Composition matrix:** §4; the three wired experiments occupy exactly the
  `✓` edges; four unwired capability-valid shapes carry `⚠`/ambiguous edges.
- **Candidate compositions (3–5):** §8 — the three wired experiments plus
  `py-pde+pymunk(movers)+mesa` and `py-pde+pymunk(walls)+mesa+network` as
  discovery targets.
- **Invalid combinations:** §9 (six name-level failures + the movers+network
  case that is capability-valid but coupling-invalid).
- **Biggest risks:** minuscule discovery surface (only 3 wired shapes), variant
  overloading of capability names, positional executor indexing, contract
  drift, baseline disturbance.
- **Smallest generic implementation required:** `contracts.py` +
  `resolve_contracts` + optional `contracts=` compose validation (detailed in
  §14), ahead of any CompositionSpace/search work.
- **Exact next Build task:** §14 as stated.
- **Confirmation:** no source code, dependency, or test files were modified by
  Task 2.1; no commits were made; Task 2.2 was not started.