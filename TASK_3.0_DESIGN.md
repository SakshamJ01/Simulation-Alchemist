# TASK 3.0 — DESIGN: Full Roadmap Re-Audit + New Composition Design

**Status:** PLAN-ONLY COMPLETE. No source/test/dependency/world/CLI/experiment
changes. No execution. No commit. The only artifacts are this design document and
the `PROJECT_STATE.md` milestone update.

**Date:** 2026-09-11
**Model:** Inkling Small Free (PLAN ONLY)
**HEAD verified:** `ad8343c` "feat: complete adaptive comparison archive" on
`master` tracking `origin/master` (`https://github.com/SakshamJ01/Simulation-Alchemist.git`).
Task 2.9 complete, Task 3.0 NOT started. Working tree has no tracked
modifications (only untracked scratch files, untouched).

---

## 1. Executive summary

The repository already contains every piece of discovery plumbing a researcher
would need to add a new coupled simulation world: capability surfaces, coupling
contracts, coupling templates, a 6-status executable taxonomy, world generation,
lineage, sweeps, behavioral characterization, ranking, diversity frontiers,
adaptive exploration, and an archive. Yet the executable universe is **exactly
the three hand-authored experiments A/B/C**. None of the four capability-valid
but `COUPLING_UNAVAILABLE` shapes — the project's own documented "honest
discovery targets" (TASK_2.1_DESIGN.md §8.4/§8.5) — has ever been converted into
a running composition. The framework therefore has never *proven* its core
promise: that a genuinely new coupled composition can be authored by a
researcher and pass through the complete discovery pipeline without hacking the
generic core.

**Task 3.0 recommendation:** author and validate **a new experiment — Gated
Mover Morphogenesis — the `{mesa, py-pde, pymunk/movers}` composition** —
converting exactly one `COUPLING_UNAVAILABLE` shape into `EXECUTABLE` via
declared, experiment-owned contracts, and driving it through the existing
discovery pipeline. This is the smallest scientifically defensible step: it
reuses all three existing adapters, needs **zero generic-core changes**, keeps
the 5-binding universe and the 23-shape catalog intact (only 4→3
`COUPLING_UNAVAILABLE`, 3→4 `EXECUTABLE`), introduces no dependency, and adds a
scientifically new decision layer (agent-gated chemotaxis) on top of Experiment
B's unconditional chemotaxis.

---

## 2. Original README vision

The README describes **Baseline v0.1**: three independent simulation engines
(py-pde continuous reaction-diffusion, Pymunk rigid-body walls, Mesa agents)
composed into one deterministic closed feedback loop:

```
field ↔ geometry ↔ agents
```

with the explicit intent (IMPLEMENTATION_PLAN.md §1): "a world is not a
simulation — it is a graph of simulations with shared state and synchronized
time. The magic happens at the composition layer, not in any individual engine."
The MVP goal (IMPLEMENTATION_PLAN.md §2) is a composition engine that lets a
user "discover, match, wire, and run" independent subsystems as a unified world.
The deeper architectural goal of Tasks 1.3–2.9 was to *extract a reusable
composition core* so new worlds can be authored declaratively. Task 3.0 must
stay faithful to that vision: prove the extracted core can accept and explore a
genuinely new coupled world.

---

## 3. Repository starting state

- **Git:** HEAD `ad8343c` (clean tracked tree; untracked scratch files are
  session leftovers and are *not* part of this plan).
- **Catalog:** 23 shapes over 5 bindings = **16 `CAPABILITY_INVALID` /
  4 `COUPLING_UNAVAILABLE` / 3 `EXECUTABLE`** (A: morphogenesis, B:
  field-guided-movers, C: adaptive-network).
- **Guard:** `tests/test_field_guided_movers.py::CORE_COMMIT_HASHES` pins 23
  files under `src/sim_alchemist/core/`; `test_network_morphogenesis.py`
  reuses the dict. `src/sim_alchemist/adapters/*` is NOT guarded.
- **Validated science:** `run_validation.py` A–G PASS, `run_stability.py`
  S1–S6 PASS, full pytest 695 passed / 1 failed (the single failure is the
  pre-existing, unrelated `test_cross_composition_sweep_cli_stage5.py::
  test_cli_parse_and_analysis_path`).
- **Parameter spaces:** only C registers a real `MutationSpace` (27 variants);
  A and B are baseline-only (`space=None`).

---

## 4. Completed architectural evolution

Tasks 1.2→2.9 built, in order: core `StepScheduler` (1.2); declarative
composition layer `WorldDefinition`/`ComponentRegistry`/`compose()` (1.3);
Experiment C as a third composed world with a fourth engine (1.5); generic
mutation + SQLite lineage + variant runner (1.6); deterministic sweeps +
ranking (1.7); behavioral characterization + interestingness engine (1.8);
guided beam search (1.9); diversity-preserving search (2.0); cross-composition
design (2.1, PLAN); coupling contracts (`contracts.py`, 2.2); composition
shapes/spaces + templates + 6-status taxonomy + world generation + catalog
(2.3); cross-composition evaluation/search/common observables/ranking/frontier/
CLI+figure (2.4); cross-composition parameter-space binding + sweep execution +
common-observable aggregation (2.5); adaptive signal/selection/exploration CLI
(2.6–2.7); adaptive comparison (2.8); persistent adaptive-comparison archive +
read-only query/audit + authoritative feature linkage (2.9). The generic core is
experiment-free by purity scan (`tests/test_cross_sweep_stage1.py:::
test_generic_core_...` asserts it).

---

## 5. Current capability map

**Adapters (5 bindings, 4 classes):**

| id | variant | provides | requires | grid / coord | timestep |
|----|---------|----------|----------|--------------|----------|
| `mesa` | – | `agent_population`, `agent_step`, `field_sensing`, `agent_intentions` | `scalar_field` | – / `unit-square-2d` | 0.2 (macro) |
| `py-pde` | – | `scalar_field`, `reaction_diffusion`, `spatial_sampling`, `field_masking`, `field_gradient`, `field_sources` | `geometry_provider` | n=32 / `unit-square-2d` | 0.2 (field_step) |
| `pymunk` | `walls` | `rigid_body`, `collision_geometry`, `force_integration`, `geometry_provider` | `field_gradient`, `agent_intentions` | n=32 / `unit-square-2d` | 0.05 |
| `pymunk` | `movers` | `rigid_body`, `force_integration`, `geometry_provider` | `scalar_field`, `field_gradient`, `field_sources` | n=32 / `unit-square-2d` | 0.05 |
| `network` | – | `network_diffusion`, `agent_intentions` | `reaction_diffusion`, `rigid_body` | grid_graph / `unit-square-2d` | 0.2 |

**Registries:** `default_registry()` (mesa, py-pde, pymunk/walls); B overrides
`pymunk` with `MoversAdapter`; C adds `network`. **Surfaces** merge all three
(`repository_surfaces()`, keyed by component+variant).

**Templates:** `morphogenesis` (A, 4 contracts / 7 ops), `field_guided_movers`
(B, 2 contracts / 5 ops), `adaptive_network` (C, 5 contracts / 9 ops).

**Executors:** `repository_executors()` maps each template's
`template_composition_id` → a conforming `WorldDefinition → ExecOutcome`
executor (A: `run_morphogenesis_world`, B: `run_field_guided_movers_world`, C:
`run_network_world`).

**Metrics/observables:** A exports 8, B 8, C 9 scalar metrics; the shared
triple `final_field_mean` / `final_field_std` / `field_entropy` is the genuinely
common vocabulary. C additionally exports 9 per-step `ObservableSeries`.

**Discovery layers:** `CompositionSearcher` (one baseline per EXECUTABLE),
`extract_common_observables` (pure projection), `rank_compositions` +
`select_frontier` (analysis-only), `CrossCompositionSweep` (per-composition
sweep-or-baseline), adaptive exploration/compare, archive.

---

## 6. Current discovery pipeline (verified against source)

| Stage | Status | Where |
|-------|--------|-------|
| Composition definition | implemented, generic | `core/world.py`, `core/composition.py` |
| Composition validation (capability + contracts) | implemented, generic; contracts never inferred | `core/composer.py`, `core/contracts.py` |
| Executable classification (6-status funnel) | implemented, static, generic | `core/templates.py::classify_composition` |
| World generation | implemented, deterministic, adapter-free | `core/templates.py::generate_world` |
| Parameter-space binding | implemented (data model); only C owns a space | `core/cross_sweep.py`, `experiments/catalog.py::repository_parameter_spaces()` |
| Sweep / search | implemented, generic | `core/sweep.py`, `core/search.py`, `core/cross_composition_sweep.py` |
| Common observables | implemented, pure, O(n) | `core/observables.py`, `core/composition_search.py` |
| Behavior characterization | implemented, generic | `core/behavior.py` |
| Ranking | implemented, generic | `core/behavior.py::rank_by_profile`, `core/composition_analysis.py::rank_compositions` |
| Diversity frontier | implemented, generic | `core/behavior.py::select_diverse_frontier`, `core/composition_analysis.py::select_frontier` |
| Adaptive exploration | **partial**: generic shell; demo wired C-only; action pool letter-derived (`_derive_actions_from_spec` keys on "A"/"B"/"C") | `core/adaptive_exploration.py`, `core/adaptive_exploration_runner.py`, `run_adaptive_exploration.py` |
| Adaptive comparison | **partial**: analysis-only; needs externally supplied feature vectors | `core/adaptive_comparison.py` |
| Archive | **store API complete; no production writer** — `record_adaptive_comparison`/`record_exploration_session` are called only by tests/scratch | `core/lineage.py`, `run_adaptive_comparison_archive.py` (read-only CLI) |
| Deterministic retrieval / audit | implemented; `identity_recomputable=False`, `resolvable_from_archive=False` by design | `core/lineage.py::verify_adaptive_comparison`, `feature_linkage_of` |

**Interpretation:** the composition→receive/discovery spine is complete and
generic. The adaptive/archive tail is present as generic plumbing but is
letter-coupled in action derivation and has no production caller for writes —
both are documented as deferred architecture work, **not** Task 3.0 scope.

---

## 7. Remaining gaps

1. **No new composition has ever entered the framework** since Task 2.3
   created the composition universe. The 4 `COUPLING_UNAVAILABLE` shapes are
   still unwired.
2. Only C has a declared parameter space; A and B are baseline-only — the
   sweep/discovery machinery has only ever been driven by C's space.
3. The adaptive action-pool derivation is experiment-letter-coupled
   (A/B/C) — a generic core smell, unguarded but still generic.
4. The archive write path has no production caller; comparison feature data
   is not durably persisted (OUTCOME B), so `resolvable_from_archive` is
   permanently False by design.
5. `MesaAdapter` (`src/sim_alchemist/adapters/mesa.py`) hard-imports
   `chemomech.agents` (`AgentConfig`, `ChemoMechanicalModel`) — the core Mesa
   adapter is chemically tied to Experiment A's wall model, so *this* task's
   new Mesa agent must be an experiment-owned override (established B/C
   adapter-override pattern), not a core change.

---

## 8. Deferred directions

- Candidate 3 (new engine/subsystem): rejected for Task 3.0; see §12.
- Candidate E (temporal multi-pass divergence/convergence analysis): rejected
  for Task 3.0; see §13.
- Plugin/adapter registry, generalized world composition beyond `compose()`,
  cross-platform deterministic replay (version-pinned), CLI surface for the
  archive write path, and the adaptive letter-coupling cleanup: all in
  IMPLEMENTATION_PLAN.md NExT/DEFERRED; all remain after Task 3.0.
- The `mesa → movers` coupling being declined here for Candidate B is not
  touched by Task 3.0 (Task 2.1 §8.5 stays unwired).

---

## 9. Candidate 3.0 directions

| # | Direction | One-line |
|---|-----------|----------|
| A | `{mesa, py-pde, pymunk/movers}` | add a Mesa decision layer over Experiment B's movers (the Task 2.1 §8.4 target) |
| B | `{mesa, py-pde, pymunk/walls, network}` | four-way all-subsystem loop (the Task 2.1 §8.5 target) |
| C | genuinely new subsystem/engine | e.g. cellular automata / gridlife, 3D physics, CA reaction-diffusion |
| D | temporal multi-pass divergence analysis | deferred "scientific analysis depth" idea |
| E | another repository-derived direction | evidence enumeration in §14 |

---

## 10. Candidate A analysis — `{mesa, py-pde, pymunk/movers}` (Gated Mover Morphogenesis)

**Scientific framing.** Experiment B is *unconditional chemotaxis*: movers
deposit activator/inhibitor at their current positions every macro step, and are
pushed by bounded field-gradient forces. Candidate A adds a Mesa sensing/decision
layer — a new agent class that senses the SAME field (reusing the `field-sensing`
pattern from A) and **gates/modulates** each mover's deposition (and/or force
gain) with per-mover hysteresis + cooldown. Closed loop: field → agents sense →
agents gate → movers deposit/withhold → sources reshape field → movers still
follow gradients. This is genuinely new dynamics: *regulated* chemotaxis with a
policy layer, not walls (A), not unconditional movers (B), not network transport
(C).

**Movere-space facts (from source).** `MoversAdapter` (Experiment B) owns
`MoverSpace` (6 discs, radius 0.05, mass 1, damping 0.2, `phys_dt=0.05`, 4
substeps, deterministic pymunk, bounds-clamped). Couplings: `gradient_force`
(`F=Fmax·tanh(|∇u|/g_sat)·ĝ`, `Fmax=0.8`, `g_sat=2.0`) and `mover_source`
(deposit u +0.03, consume v −0.04 in radius 0.04, unconditionally each step).
No blocked mask, no geometry producer into the PDE. B's world needs no Mesa.

**The Mesa problem (verified).** `MesaAdapter` provides `agent_population` /
`agent_step` / `field_sensing` / `agent_intentions`, requires `scalar_field`,
but `MesaAdapter.create_model()` imports `chemomech.agents.ChemoMechanicalModel`
(wall-building) and `set_wallspace` needs a wallspace — which `MoverSpace` does
not provide. Therefore Candidate A **must** ship an experiment-owned Mesa agent
model + a Mesa adapter override (precedent: `MoversAdapter` overrides `pymunk`,
`AdaptiveNetworkAdapter` adds `network`). This is experiment science, not core
work, and the Mesa binding's *capability surface stays identical*, so the
catalog's static classification and the 5-binding universe are unchanged.

**New coupling edge.** Task 2.1 §8.4 exactly: "agents sense the field, movers
react to gradients ... Mesa `intentions` would be un-consumed." Candidate A
declares a new experiment-owned contract that consumes Mesa `agent_intentions`
at the movers consumer (`field_sources`/`force_integration`), e.g.
`name="mover-gate", producer="mesa", producer_capability="agent_intentions",
consumer="pymunk", consumer_capability="field_sources", variant="movers",
transform_id="gated-source"`. Nothing is inferred; the rule (hysteresis
threshold, cooldown, per-mover history) is experiment-owned.

**Schedule (declared, ~7 ops):**
`field.step → agents.step → agents.apply → movers.force → movers.step →
field.source → observables.record` (agents must sense the fresh field; gating
must precede `movers.force` for force modulation or `field.source` for
deposition gating).

**Clock/grid compatibility:** py-pde 0.2 = mesa 0.2 (integer ratio); movers
0.05 divides both (4 substeps); shared 32×32 grid, `unit-square-2d`. `CLOCK_INVALID`
will not trigger.

**Observables (scientifically meaningful, not filler):**
- B's existing 8 metrics (`final_field_mean`, `final_field_std`, `field_entropy`,
  `n_movers`, `total_displacement`, `mean_speed`, `mean_force`, `mean_gradient`)
  — kept so the common triple stays common.
- new: `deposition_events` (count of gated-on steps), `deposition_suppression`
  (fraction of steps a gate withheld a deposit the mover otherwise would have
  made), `active_gates` (mean simultaneous open gates), `gate_switch_rate`
  (agent decision sign-change rate) — all directly tied to the new policy layer.
- per-step `ObservableSeries`: `gate_open`, `deposited`, `field_mean`, `field_std`,
  `mover_mean_speed`, `mover_dispersion` (B-style posture), matching the 9-series
  precedent in C.

**Parameter space (first legitimate non-C space).** The experiment genuinely owns:
- `config.gate_threshold` (|∇u| or u threshold for opening a gate; bounds 0..1)
- `config.gate_cooldown` (steps a gate stays closed after closing; bounds 0..20)
- `config.source_amplitude` (scales `source_u`/`source_v` when the gate is open;
  bounds 0..2)
`repository_parameter_spaces()` gains a real binding for the new composition id.
No fabricated space, no invented dimension.

**Verdict: VALID NEW EXPERIMENT.** Architecturally possible, scientifically
meaningful, deterministic, bounded, reuses adapters, zero core changes. The Mesa
`WallBuildingAgent` semantics do NOT map to movers — which is precisely why a new
agent class + new contract is required (i.e., genuine science, not a wiring
stunt).

---

## 11. Candidate B analysis — `{mesa, py-pde, pymunk/walls, network}` (four-way)

Scientific framing is *competing/cooperating wall morphogenesis*: the network
grows walls along high-throughput transport edges while cells build/dissolve
dissipative walls on steep gradients. Edges: field↔walls (force + mask), agents→
walls (build/dissolve), network→field (source), walls→network (edge reweight),
network→walls (grow).

**Ambiguity (verified, matches Task 2.1 §8.5):** TWO `agent_intentions`
producers (`mesa` and `network`), and TWO wall-creation channels (agents and
throughput-grow). The contract layer can represent them canonically (contracts
key on producer), but the *science* of how mesa-owned and network-owned walls
coexist must be declared, not assumed. It is the longest schedule (~11 ops), the
largest new coupling surface, and the hardest attribution/debugging/calibration
(a review of A/C shows 200+ lines of coupling each; four-way is strictly more).
Not the right *first* new composition; becomes reachable after A validates the
agent-control pattern.

**Verdict: COHERENT BUT OVERCOMPLICATED FOR A FIRST BUILD.** Deferred to a
later task (would be the second new experiment).

---

## 12. Candidate C analysis — genuinely new subsystem/engine

The IMPLEMENTATION_PLAN names gridlife/Lenia/Gray-Scott/SmoothLife (cellular
automata) and PyBullet (3D) as *possible later* engines; FMI/Mosaik/distributed
are on the DEFERRED list. No such adapter exists in-repo; `pyproject.toml` pins
8 runtime deps, none automotive.

**Evaluation:** a CA engine on the same 32×32 grid is the most principled future
direction (a genuinely new pattern-formation paradigm, grid/clock compatible,
reusable mask/projection transforms). But it requires: a new dependency
(violates the standing no-new-deps invariant), a new capability surface (grows
the universe; re-baselines pinned catalog/guard/tests), a full experiment
scaffold (adapter, coupling, template, executor, worlds, tests), and it would
dominate the whole task ("rewrite the framework" smell). **Rejected for Task
3.0.** It is the roadmap's future, not the present, because Task 3.0's mission
is to prove the *composition* path for a genuinely new world — reusing the four
existing engines — before introducing a fifth.

---

## 13. Candidate D analysis — temporal multi-pass divergence/convergence analysis

The project does have per-step series (`C.build_network_observables`) and
Task 1.8 divergence features, but Task 2.9's OUTCOME-B audit established there is
**no authoritative durable feature data** for adaptive passes (pass ids are
content-addressed `adaptive_run_id`s, never `runs.run_id`; real proof DB has
`feature_snapshot=NULL`, `resolvable_from_archive=False` by design). Adding
deeper temporal analysis now would produce more analysis *infrastructure* on a
foundation that cannot yet be fed durably, and it would not advance the
composition-framework mission. **Verdict: engineering convenience, not
scientific leverage — rejected.** It becomes practical only after the archive
write path gains a production caller and durable feature persistence.

---

## 14. Candidate E — repository-derived directions (evidence)

Searched the repository for TODOs/deferred text. Relevant artifacts:
- `IMPLEMENTATION_PLAN.md` NEXT/DEFERRED: plugin registry, generalized world
  composition, cross-platform replay (version-pinned), CLI, experiment DB.
- `AGENTS.md` "Will Become / NOT implemented": capability discovery, plugin
  architecture, experiment database, external-engine adapters, replay; "next
  phase is extracting reusable Alchemist abstractions ... Do not start building
  that until the extraction task is issued."
- `AGENTS.md` next-milestone line currently names Task 2.5 Build Stage 2 but is
  stale relative to the completed 2.6–2.9 work (git + PROJECT_STATE are
  authoritative).
- Archives/Task-2.9: `feature_linkage_of` never resolves (OUTCOME B) and the
  write path is unexercised — documented, not silently fixed here.
None of these is as tight, low-risk, and scientifically defensible as Candidate A;
they are deferred-framework work, not a *composition* milestone.

---

## 15. Candidate comparison matrix (scored 1–5; reverse = 5 is best)

| Criterion | A (gated movers) | B (four-way) | C (new engine) | D (temporal analysis) |
|---|---|---|---|---|
| Scientific value | 4 | 4 | 5 | 3 |
| Alignment with README | 4 | 4 | 5 | 2 |
| Framework value | 5 | 4 | 4 | 3 |
| Reuse of existing core | 5 | 4 | 2 | 4 |
| Determinism | 5 | 5 | 4 | 4 |
| Testability | 5 | 3 | 3 | 4 |
| Implementation risk (reverse) | 4 | 2 | 1 | 3 |
| Regression risk (reverse) | 5 | 2 | 1 | 4 |
| Scientific ambiguity (reverse) | 4 | 1 | 3 | 3 |
| Future leverage | 5 | 4 | 5 | 3 |
| **Total** | **46** | **33** | **33** | **33** |

Note: scoring rewards architectural/scientific leverage (a genuinely new,
explorable composition with a new decision layer), not ease.

---

## 16. Recommended direction (must be earned, not preselected)

**"Author and validate one genuinely new coupled composition — Gated Mover
Morphogenesis (`{mesa, py-pde, pymunk/movers}`) — declared purely in the
experiment layer through the existing contract/template/registry/catalog
machinery, converted from `COUPLING_UNAVAILABLE` to `EXECUTABLE`, and driven
through the existing discovery pipeline."**

This is the one capability that most strongly proves the framework extracted
from the A/B/C prototype now supports a new coupled scientific world: it cannot
be faked by aliasing an existing experiment (new agent class, new coupling
contract, new schedule, new parameter space, new observables), it requires zero
generic-core edits (guard holds), it does not collapse into "the same universe
re-arranged" (the coupling topology actually changes — the un-consumed Mesa
`agent_intentions` edge now feeds the movers consumer), and it is small enough to
be scientifically validated rather than merely wired.

---

## 17. Scientific justification

Experiment B is unconditional chemotaxis. Adding a sensory decision layer over
the movers produces *regulated* chemotaxis — a control layer that withholds
deposition unless the field at the mover satisfies an experiment-declared
condition, with hysteresis/cooldown. The feedback loop field → agents → movers →
field is closed and deterministic; a "gating OFF" configuration (gate always
open, or bypassing Mesa) reconstructs B bitwise-ish as a control, so the delta
is attributable to the policy alone. This is real, small, testable ecology-style
science for the composition framework — not a parameter tweak of an existing
world.

---

## 18. Architectural justification

- No `src/sim_alchemist/core/*` change → `CORE_COMMIT_HASHES` guard holds; no
  guarded-file re-baseline needed.
- Experiment-owned adapter override follows the proven B/C pattern
  (`MoversAdapter`, `AdaptiveNetworkAdapter`).
- The universe stays 5 bindings / 23 shapes; catalog status distribution moves
  from {16, 4, 3} to {16, 3, 4} — the smallest possible catalog growth, and the
  executable set grows by exactly the documented `COUPLING_UNAVAILABLE` target.
- Discovery identity changes are deliberate and recomputed deterministically
  (`composition_discovery_id_of`, `cross_split_sweep_id`, etc., are content
  addressed over the new executable set) — this is a *sanctioned recomputation*,
  not an ABI break; prior experiments' run/world identity is untouched.
- The composition graph adds exactly the edges Task 2.1 flagged as missing; the
  contract layer validates them; nothing is inferred.

---

## 19. Selected composition

`{mesa, py-pde, pymunk/movers}` — **Gated Mover Morphogenesis (Experiment D)**,
resolving
`mesa` (experiment-owned gating agent override), `py-pde` (Schnakenberg field),
`pymunk/movers` (MoversAdapter).

---

## 20. Coupling graph

```
py-pde ──► pymunk(movers)   gradient → bounded force (movers.force)          [B rule, reused]
pymunk(movers) ─► py-pde    position → source/sink injection (field.source)  [B rule, reused]
py-pde ──► mesa             scalar_field → field sensing (agents.step)       [A pattern, reused]
mesa ──► pymunk(movers)     agent_intentions → gate/release mover deposition
                             (NEW experiment-owned transform "gated-source")
```
Direction and payload of each edge are explicit and experiment-owned. The new
edge is the difference between Appendix B and B.

---

## 21. Data flow (per macro step)

1. `field.step` — py-pde advances u/v; agents' sensed field is the new one.
2. `agents.step` — agent model reads `u`/`∇u` at each mover position, updates
   per-mover gate state with hysteresis + cooldown, publishes intentions.
3. `agents.apply` — coupling op translates intentions into gate open/closed per
   mover id (experiment-owned transform).
4. `movers.force` — bounded gradient force (unchanged B rule).
5. `movers.step` — pymunk integration (damped, bounds-clamped).
6. `field.source` — deposit u/consume v only at movers whose gate is open
   (amplitude scaled by `source_amplitude`); closed gates deposit nothing.
7. `observables.record` — metric + series capture.

---

## 22. Component/variant ownership

- `mesa` (reused binding, variant None): experiment-owned gating-adapter
  override constructs the new agent model; capability surface identical.
- `py-pde` (unchanged).
- `pymunk/movers` (unchanged `MoversAdapter`).

---

## 23. Core vs experiment ownership

| Concern | Owner |
|---------|-------|
| Coupling science (gate rule, hysteresis, cooldown) | EXPERIMENT |
| `CouplingTemplate` + contracts + schedule | EXPERIMENT (co-located coupling module, per A/B/C precedent) |
| Agent model + Mesa adapter override | EXPERIMENT |
| Executor `run_gated_movers_world` | EXPERIMENT |
| Metrics + per-step observables + `MutationSpace` | EXPERIMENT |
| Registry extension / `build_*_registry` | EXPERIMENT |
| `repository_surfaces/templates/executors/parameter_spaces` registration | EXPERIMENT (`experiments/catalog.py`) |
| Catalog/classify/generate-works/determinism/lineage/sweep/behavior/rank/frontier | GENERIC CORE (unchanged) |
| Identity recomputation (new composition_id, discovery_id, sweep_id) | GENERIC CORE (content-addressed; happens automatically) |
| Sanctioned re-baseline of pinned catalog-count constants + canonical identities | TESTS (documented re-baseline, no guarded file) |

**Rule honored:** scientific meaning → experiment; generic composition
mechanics → core; persistence/lineage replay → lineage; reporting → tooling.
No experiment name leaks into generic core (it never dispatches on
composition).

---

## 24. Parameter ownership

Experiment-declared `ParameterSweep`s over three genuinely meaningful
dimensions — `config.gate_threshold`, `config.gate_cooldown`,
`config.source_amplitude` — with bounds declared in the coupling module and
validated against them during space construction (same pattern as
`_network_parameter_space`). A/B/C spaces untouched. If a dimension lacks a
safe tuning range it is dropped; a baseline-only mode (gating by-pass) is also
declared so "no safe tunables" is never forced.

---

## 25. Observable ownership

Experiment-owned `build_gated_movers_metrics`/`build_gated_movers_observables`.
Keep the shared triple (`final_field_mean`, `final_field_std`, `field_entropy`)
verbatim-identical in meaning and naming to remain genuinely-common; add the
policy metrics of §10. Each new observable documents source subsystem
(mesa/movers/field), scientific meaning (e.g. `deposition_suppression` = policy
restraint vs open-loop), aggregation (per-run scalar or per-step series),
sampling time (per macro step on `t_field`), availability (present for D,
missing elsewhere → `available=False`), and comparability (NOT claimed equal to
any A/B/C quantity absent an explicit semantic alias — preserved honesty).

---

## 26. Identity model

- `template_composition_id(template)` — deterministic 24-hex over the new
  template (shape + contracts + schedule + clock + binding configs). New value;
  A/B/C ids unchanged.
- Generated world builders get `ComponentSpec.variant` stamped per binding from
  the template (existing `generate_world`).
- `run_id_of` (sha256 of world content + seed) — unchanged; D's runs get their
  own deterministic ids; A/B/C run ids unchanged.
- `composition_discovery_id_of` and `cross_split_sweep_id` recompute over the
  new executable set — deterministic, documented, and re-verified, not
  hand-patched.

---

## 27. Lineage model

D's runs record through the existing `LineageStore`: `RunRecord` (with
`composition_id` stamped by `evaluate_composition_baseline`), optional
`SweepRecord`, optional per-run `feature_snapshot` and `behavior_analyses`
(compact metadata only; **no trajectories persisted**). The Task 2.9 archive
remains as-is: D adds no archive records during this task unless a Stage-3
optional proof drives the exploration/archive write path (which has no
production caller today — see §31; wiring it is deferred, not assumed).

---

## 28. Determinism

- Same inputs → same world (world hash), same run id, same trajectory (same
  `seed`, same pymunk/py-pde stepping), same sweep/search/analysis.
- Replay is **same-runtime/environment** — explicitly NOT universal
  cross-platform bitwise equivalence (README limitation preserved).
- New agent model: deterministic stepping, fixed iteration order, no
  wall-clock/hash-order dependence; API `random` seeded by world seed.

---

## 29. Backward compatibility

- A, B, C: no behavior change. `contracts use` is additive; templates/executors/
  spaces for A/B/C untouched; run/world identities unchanged.
- Guarded `src/sim_alchemist/core/*`: byte-identical (guard holds).
- `experiments/catalog.py`: grows (new template/executor/space entries); the
  23-shape universe and 16 `CAPABILITY_INVALID` count unchanged; the 4→3
  `COUPLING_UNAVAILABLE` and 3→4 `EXECUTABLE` shifts and the two canonical
  identity constants in discovery/sweep tests are **sanctioned re-baselines**
  with the exact expectations updated and old values retained as comments.
- Dependency lockfiles untouched; no new dependency.

---

## 30. Scientific limitations (preserved, not hidden)

- Uncalibrated: gating threshold/cooldown are hand-tuned demonstration values.
- Same frozen-mask / clamped-obstacle PDE approximation (py-pde walls frozen)
  if any mask is later added — the movers produce no mask, so the coupling is
  purely source-based.
- Mover deposit is point-spread in a radius; not a calibrated transport model.
- Deterministic replay is same-runtime only.
- Diversity/interestingness are behavior-feature heuristics, not calibrated
  metrics.
- The agent policy is a simplified hysteresis model, not a claim about real
  cells/chemotaxis.

---

## 31. Failure modes (detection / mitigation / test)

| Failure | Detection | Mitigation | Test |
|---------|-----------|------------|------|
| Capability mismatch (e.g., core mesa adapter used accidentally) | `compose(..., contracts=...)` raises `UnresolvedContractError` | experiment-owned registry override; capability surface asserted identical | Stage 1 capability/contract test |
| Contract mismatch (wrong producer/consumer capability) | `resolve_contracts` before install | declare only real edges; `mover-gate` matches `agent_intentions`→`field_sources`(variant movers) | contract-resolution unit test (associative; Task 2.2 pattern) |
| Schedule mismatch | `SCHEDULE_INVALID` if declared op absent from operation registry | schedule built from the same registry as the ops | classification test |
| Clock mismatch | `CLOCK_INVALID` if native timestep not divisible by macro | 0.2 macro = 4×0.05 (movers), 1×0.2 (mesa/py-pde) | classification test |
| Scientific ambiguity (double meaning of gate) | code review; explicit per-mover semantics | gate = discrete open/closed per mover id, single transform id | explain/matrix test |
| Missing observable | executor metric dict missing name → `available=False` explicit; never imputed | declare full metric set up front | common-observable extraction test |
| Parameter-space mismatch (space vs PARAMETER_SPECS) | `ValueError` on out-of-bounds during space construction | validate against declared bounds | space-validation test |
| Executor mismatch (wrong composition id keyed) | fail-fast on unknown id in `repository_executors` | register by `template_composition_id`, assert in test | executor-map test |
| Nondeterministic output | same seed → same run id/trajectory hash | no wall-clock, seeded RNGs | determinism test (bitwise) |
| Baseline regression | run_validation A–G / run_stability S1–S6 / prior tests | no core or A/B/C code touched; catalog additions only | full suite gate |
| Lineage inconsistency | deterministic `run_id_of` recomputed in test | exercise via runner/evaluate path | lineage round-trip test |
| Archive incompatibility | archive CLI `verify` and `feature_linkage_of` remain OUTCOME-B | no archive schema change this task | archive tests (unchanged) |

---

## 32. Test strategy

- New `tests/test_gated_movers_stage1.py` (structural: catalog classification,
  contracts, template registry, world generation, identity determinism,
  generic-core purity, experiment-free core scan).
- New `tests/test_gated_movers_stage2.py` (execution: deterministic baseline,
  gating-OFF vs B control, boundedness, replay bitwise, metrics/series shape).
- New `tests/test_gated_movers_stage3.py` (discovery: one `CompositionSearch`
  baseline, common-observable availability, sweep via new `MutationSpace`,
  behavior features, ranking + frontier membership).
- Guard checks (23 pinned hashes) must pass unmodified.
- Regression: full pytest suite, `run_validation.py` A–G, `run_stability.py`
  S1–S6, ruff, pyright. The single historical failure
  (`test_cross_composition_sweep_cli_stage5.py::test_cli_parse_and_analysis_path`)
  stays separate; any new failure must be attributable to Task 3.0, never
  conflated with it.

---

## 33. Performance / execution budget

- Structural classification + world generation: sub-millisecond static ops (23→
  recompute over same space; string/fmt trivial).
- Short-horizon baseline (Task-2.9 style): a 10–20-step D run reuses B's per-step
  cost; target wall time well under B's `run_validation` budget (B 160-step ~
  seconds; D with 1 Mesa model + 6 movers is comparable, likely less geometry).
- Discovery integration: reuses the canonical 160-step discovery default (the
  slow suite) once in Stage 3, plus a fast short-horizon subset.
- Framework overhead vs simulation runtime: controllable/measure-able
  (scheduler/observables are microseconds per step); no new machinery introduced.

---

## 34. Implementation stages (smallest sensible staging)

**Stage 1 — composition declaration + contracts + adapter binding + structural
tests (architecture proof).**
- Files (experiment-owned + tests + docs):
  - `experiments/gated_movers/coupling.py` (GATED_MOVERS_CONTRACTS, schedule,
    template builder, world builder, registry builder with gating-adapter
    override and new agent model)
  - `experiments/gated_movers/model.py` (agent model, gating adapter,
    `MoversConfig`-compatible config)
  - `experiments/gated_movers/experiment.py` (`run_gated_movers_world`,
    `PARAMETER_SPECS`, `build_gated_movers_metrics`)
  - `worlds/gated_movers.yaml`
  - `experiments/catalog.py` (register template/executor/space binding)
  - `tests/test_gated_movers_stage1.py`
  - `TASK_3.0_STAGE1_REPORT.md`, `PROJECT_STATE.md`
- Acceptance: shape `{mesa, py-pde, pymunk/movers}` classified EXECUTABLE;
  `generate_world` yields a plain deterministic `WorldDefinition`; contracts
  resolve; catalog counts {16,3,4}; no core change; no execution; no sweep.
- Hard stop: NO long simulations, NO sweeps, NO adaptive search, NO archive
  migration, NO CLI.

**Stage 2 — executable world + deterministic baseline + scientific validation.**
- Files: `tests/test_gated_movers_stage2.py`, optional scientific snippet/
  figure; `TASK_3.0_STAGE2_REPORT.md`; `PROJECT_STATE.md`.
- Acceptance: short-horizon deterministic baseline runs; gating-ON diverges
  from gating-OFF (B-ish control) measurably; bounded field/movers; replay
  bitwise; metrics/series shape correct; observables policy series meaningful.
- Hard stop: no discovery integration yet.

**Stage 3 — integration through the existing discovery pipeline.**
- Files: `tests/test_gated_movers_stage3.py`; `TASK_3.0_STAGE3_REPORT.md`;
  `PROJECT_STATE.md`; optional bounded experiment-owned adaptive pass and its
  own driver (NO generic-core change).
- Acceptance: D participates in `CompositionSearcher` (one baseline), common-
  observable envelope (shared triple + explicit unavailable for D-specific
  names on A/B/C), sweep via its new `MutationSpace` through
  `CrossCompositionSweep`, `BehavioralAnalysisRunner` features, `rank_*` +
  `select_frontier` membership; A/B/C behavior preserved; no new optimizer/ML/
  GA/Bayesian/RL; no new dependency; no guarded-core change.

---

## 35. Smallest Stage 1 (exactly)

`coupling.py` (template + contracts + schedule + world/registry builders) +
agent model + gating Mesa adapter override + catalog registration + ONE test
file asserting (a) EXECUTABLE classification of `{mesa, py-pde, pymunk/movers}`,
(b) deterministic world/identity, (c) resolved contracts, (d) generic-core
byte-identity (guard). No simulation, no CLI, no sweep.

---

## 36. Stage 2 (execution)

Deterministic short-horizon baseline + gating-OFF control + boundedness +
replay + metrics/series validation; scientific claims limited to
"regulated v uncontrolled chemotaxis differ in a bounded, deterministic way."

---

## 37. Stage 3 (discovery integration)

Composition search → common observables → sweep → behavior → ranking →
diversity frontier, all through existing generic machinery, with A/B/C
bitwise-unchanged and the prior experiment-space untouched.

---

## 38. Non-goals (explicit §40 prohibitions)

- No ML / GA / Bayesian optimization / RL. (Task 3.0 adds no optimizer of any
  kind; discovery integration only *reuses* existing deterministic
  rank/frontier.)
- No automatic coupling inference. The `mover-gate` edge is explicitly declared
  and experiment-owned; unwired shapes stay `COUPLING_UNAVAILABLE`.
- No automatic parameter synthesis. Only the experiment's declared 3-dim space.
- No distributed simulation, plugin architecture, dashboard/web UI, or giant
  visualization subsystem; no universal metric equivalence; no global-optimum
  claims.
- No new engine (Candidate C rejected for Task 3.0).
- No fixing of the letter-coupled `_derive_actions_from_spec` or the archive
  write path (deferred; documented, not silently changed).
- No new dependencies; no guard re-baselines; no A/B/C edits; no worlds A/B/C
  changes; no dependency lockfile changes. (The only sanctioned re-baselines
  are the two catalog-count/identity constants in existing discovery-constant
  tests, with old→new documented.)

---

## 39. Future extensibility test

"A researcher adds composition X" today requires: coupling module + contracts +
schedule (experiment-owned); adapter/agent override if new; executor; metrics;
parameter space; then three entries in `experiments/catalog.py` (template,
executor, space) — all experiment-owned, no core edit. After Task 3.0 that is
exactly the D path, now demonstrated and documented with D as the reference
example and the letters A/B/C fully generalized (catalog registration, not
letters). If adding a composition required editing generic core modules, that
would be an architectural smell — Task 3.0 explicitly verifies the D path needs
none.

---

## 40. Acceptance criteria (measurable)

- [x] selected composition is genuinely new (new agent class, new coupling
      contract, new schedule, new parameter space, new observables; not an A/B/C
      alias or cosmetic variant)
- [ ] scientific coupling graph explicitly defined (contracts + schedule in the
      coupling module, fully experiment-owned)
- [ ] no automatic coupling inference (edge declared, validated, never invented)
- [ ] generic core remains experiment-free and byte-identical (guard passes)
- [ ] composition classified by existing resolver as EXECUTABLE ({16,4,3}→{16,3,4})
- [ ] `generate_world` produces a real deterministic world
- [ ] deterministic structural identity works (`template_composition_id`,
      `run_id_of`, discovery/sweep ids recomputed deterministically)
- [ ] baseline execution works (short-horizon Stage 2)
- [ ] deterministic replay works (same-runtime, bitwise)
- [ ] observables are scientifically justified (triple preserved + policy metrics
      with meaning/units/sampling/aggregation documented)
- [ ] parameter-space ownership is explicit (declared SPECS + bounds; `space`
      only where the experiment owns dimensions)
- [ ] lineage compatibility preserved (runs/sweeps/features through existing
      store; archive schema untouched)
- [ ] existing A/B/C behavior preserved (bitwise regression + full suite gate)
- [ ] discovery pipeline consumes the new composition (search → observables →
      sweep → behavior → rank → frontier, Stages 2–3)
- [ ] no new optimizer/ML/GA/Bayesian/RL system
- [ ] no unnecessary dependency (zero new deps)
- [ ] scientific limitations documented (§30)
- [ ] bounded proof is practical (Stage 1 structural; Stage 2 short-horizon;
      Stage 3 one canonical + fast subset)
- [x] future researcher extension path is demonstrated/simpler (D = the worked
      reference; single experiment-owned package + 3 catalog entries)
  ([x] items are satisfied by this design itself.)

---

## 41. Recovery / checkpoint strategy

If a build session approaches the context ceiling: stop, write
`TASK_3.0_CHECKPOINT.md` with verified HEAD, repository state, candidates + the
A/B/C/D scores table, the chosen direction, the exact Stage-in-progress, and the
next action; then reread `README.md`, `AGENTS.md`, `PROJECT_STATE.md`,
`IMPLEMENTATION_PLAN.md`, `TASK_3.0_DESIGN.md`, `TASK_2.1_DESIGN.md`, and the
relevant Stage report; verify `git status`/`git log --oneline -20`; do not redo
completed analysis.

---

## 42. Final recommendation + hard boundary

**Recommendation:** Task 3.0 = Gated Mover Morphogenesis
(`{mesa, py-pde, pymunk/movers}`), built in the three stages above with the
smaller Stage 1 first. This is the highest-leverage candidate: it proves the
composition framework accepts a genuinely new coupled scientific world,
converts the precisely documented `COUPLING_UNAVAILABLE` target, needs zero
generic-core changes, adds zero dependencies, and produces new — not merely
re-packaged — science (a decision layer over chemotaxis).

**Hard boundary:** Task 3.0's scope ends when the discovery pipeline consumes
D through the existing generic machinery. It must NOT: add a new engine, build
a plugin system, wire the archive write path, generalize the adaptive action
derivation, add ML/GA/RL/Bayesian, grow dependency files, or modify A/B/C. Those
remain future tasks. Build Stage 1 must not start until this plan is approved.

---

*End of TASK_3.0_DESIGN.md — PLAN-ONLY. No code, no tests, no experiments, no
worlds, no dependencies, no execution, no commit.*