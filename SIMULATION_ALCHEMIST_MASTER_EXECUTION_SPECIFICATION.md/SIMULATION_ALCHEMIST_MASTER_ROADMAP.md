# Simulation Alchemist — Master Product & Research Roadmap

**Document role:** Long-horizon North Star for planning the project without repeatedly rediscovering what the software should become.

**Audience:** The repository coding agent, maintainers, researchers, and future contributors.

**Current status at roadmap creation:** Task 3.0 Stages 1–3 are complete. Experiment D is executable, short-horizon validated, and integrated into the existing generic sweep/behavior/discovery spine. The next major capability should begin with a researcher-facing UI/UX and real human testing loop.

---

## 0. PURPOSE

Simulation Alchemist should evolve from a scientifically validated prototype/framework into a **researcher-facing simulation laboratory** for composing, executing, observing, comparing, exploring, and eventually discovering chemo-mechanical and other coupled simulation systems.

This roadmap deliberately separates four concerns:

1. **Use it:** researchers can actually run and inspect simulations.
2. **Trust it:** results are deterministic, bounded where expected, auditable, and scientifically interpretable.
3. **Explore it:** users can sweep parameters, compare behaviors, rank interesting runs, preserve diversity, and guide exploration.
4. **Extend it:** researchers can author genuinely new compositions without modifying the generic core, while the system becomes increasingly general, inspectable, and reusable.

The roadmap is intentionally broad. It describes capabilities the project can reasonably grow toward; it does **not** authorize implementing every idea immediately.

---

# 1. NON-NEGOTIABLE PROJECT PRINCIPLES

## 1.1 Scientific honesty

The software must distinguish:

- execution evidence from scientific validation;
- correlation from causal interpretation;
- deterministic replay from scientific correctness;
- synthetic demonstrations from persisted experimental results;
- short-horizon validation from long-horizon claims;
- exploratory metrics from calibrated physical quantities.

Never manufacture data, hide failures, or tune thresholds after observing a result merely to make a hypothesis pass.

## 1.2 Generic core protection

Experiment-specific science belongs in experiment-owned layers.

The generic core must not accumulate branches such as:

```text
if composition_id == "D": ...
```

when a generic interface, contract, adapter, capability, or experiment-owned implementation can express the behavior cleanly.

## 1.3 No automatic coupling inference

The framework may validate declared couplings, capabilities, schedules, and compatibility.

It must never infer a scientific coupling simply because two components expose superficially compatible data.

## 1.4 Determinism as a first-class contract

Where the runtime claims deterministic behavior, the system must expose and test:

- seed identity;
- world identity;
- composition identity;
- parameter/mutation identity;
- run identity;
- replay equality;
- provenance.

Cross-platform determinism is a later goal and must not be confused with same-runtime determinism.

## 1.5 Human-in-the-loop development

Every major capability family should follow this cycle:

```text
BUILD → TEST → SHOW HUMAN → OBSERVE → REVISE → REGRESSION → DOCUMENT
```

A feature is not considered practically complete merely because automated tests pass.

## 1.6 Smallest useful increment

Prefer the smallest implementation that proves the architectural or scientific claim.

Do not add complexity merely because the framework could support it.

## 1.7 Evidence before expansion

Before adding another major subsystem, demonstrate that the existing one is useful through the UI, a reproducible experiment, or an explicit developer/researcher workflow.

---

# 2. CURRENT FOUNDATION

The project already has the following important foundation:

- composition definition and validation;
- executable classification;
- deterministic world generation;
- experiment-owned executors;
- parameter-space abstractions;
- sweep/search execution;
- common observables;
- behavior characterization;
- ranking;
- diversity frontier machinery;
- adaptive exploration/archive foundations;
- persistent identity/provenance concepts;
- four executable compositions A/B/C/D;
- Experiment D: Gated Mover Morphogenesis;
- D threshold × cooldown parameter space;
- deterministic short-horizon D validation;
- D participation in the existing discovery spine.

The project therefore no longer needs to prove that the framework can execute a new composition. It needs to prove that the framework is **usable by a researcher**, then expand its research capabilities without sacrificing its architectural boundaries.

---

# 3. FOUR-PHASE PRODUCT ROADMAP

The project should be organized into exactly **four broad phases**. Each phase contains iterative build/test/research loops and ends with a human-facing acceptance gate.

```text
PHASE 1 — RESEARCHER WORKBENCH
        ↓
PHASE 2 — TRUSTED EXPERIMENT LAB
        ↓
PHASE 3 — DISCOVERY & RESEARCH AUTOMATION
        ↓
PHASE 4 — GENERAL SIMULATION PLATFORM
```

Phases are not required to be completed in one giant implementation. Each phase is a container for many small milestones.

---

# PHASE 1 — RESEARCHER WORKBENCH

## Goal

Turn Simulation Alchemist from a framework primarily exercised through tests/CLIs into something a human can open, run, observe, compare, and understand.

**First implementation after this roadmap:** UI/UX, not another backend-only subsystem.

## 1A. Researcher dashboard foundation

Build a minimal desktop/local-web research workbench using the project's existing backend APIs.

The first UI should expose:

- experiment/composition selector;
- experiment description and capability summary;
- parameter controls;
- seed control;
- run length/time-step control;
- run button;
- stop/cancel/reset where supported;
- run status/progress;
- run history;
- result summary;
- error and warning display.

The UI must call existing simulation/application APIs rather than reimplementing simulation logic.

## 1B. Live/near-live simulation visualization

Researchers should be able to see what the simulation is doing.

Core visual views:

- PDE field heatmap/contour view;
- mover positions and trajectories;
- Mesa agent states;
- gate states for D;
- walls/geometry where relevant;
- source/deposition locations;
- time-step/frame controls;
- play/pause/replay.

The initial visualization should favor correctness and clarity over visual spectacle.

## 1C. Results and observables panel

Expose:

- scalar final metrics;
- time-series plots;
- field summary statistics;
- mover statistics;
- force/gradient statistics;
- experiment-specific metrics;
- availability/missing-data indicators;
- run identity and seed.

D should visibly expose:

- deposition_events;
- deposition_suppression;
- active_gates;
- gate_switch_rate.

## 1D. Comparison workspace

Users should be able to select two or more completed runs and compare:

- parameter values;
- scalar metrics;
- trajectory series;
- field snapshots;
- D gating behavior;
- common observables;
- behavior vectors/distances when available.

First mandatory comparison:

**D gating ON vs D gating OFF.**

Then:

**D threshold/cooldown variants.**

## 1E. Human testing loop

After the first UI slice, stop building and perform real human testing.

Test questions:

- Can a new user find an experiment without instructions?
- Can they understand what each parameter does?
- Can they start a run successfully?
- Can they tell when the run is finished?
- Can they understand the visualization?
- Can they interpret the reported metrics?
- Can they compare two runs without using the terminal?
- Can they tell synthetic/demo results from real persisted results?
- Can they recover from an error?

Record usability defects as first-class issues.

## 1F. Repeated UI/UX iterations

Each iteration should follow:

```text
implement small UI slice
→ manually test with real simulations
→ collect confusion/errors
→ fix UX
→ automate regression where possible
→ repeat
```

## Phase 1 acceptance gate

Phase 1 passes when a researcher can:

1. open the workbench;
2. choose A/B/C/D;
3. configure supported parameters;
4. run a short simulation;
5. watch/interrogate the result;
6. inspect metrics and time-series;
7. compare at least two runs;
8. replay a deterministic run;
9. understand warnings/errors without terminal logs;
10. export/save a reproducible run record or result package.

No advanced discovery automation is required to pass Phase 1.

---

# PHASE 2 — TRUSTED EXPERIMENT LAB

## Goal

Make the workbench scientifically useful for repeated experimentation, not merely visualization.

## 2A. Experiment configuration model

Introduce a human-readable experiment configuration workflow with:

- named experiment presets;
- explicit parameter schemas;
- parameter bounds;
- units/descriptions where known;
- validation messages;
- reproducible seeds;
- run metadata;
- optional notes/tags.

Avoid silently coercing scientifically invalid inputs.

## 2B. Run provenance and reproducibility

Every persisted run should expose:

- composition ID;
- experiment version/build identifier;
- world/config identity;
- parameter values;
- seed;
- runtime identity where relevant;
- run ID;
- parent/mutation identity when applicable;
- timestamps;
- software/schema version;
- provenance status.

Researchers must be able to answer:

> “Exactly what produced this result?”

## 2C. Experiment notebook / run history

Provide a lightweight experiment-history interface:

- runs;
- notes;
- tags;
- favorite/pin;
- compare;
- replay;
- duplicate as new experiment;
- export result bundle;
- filter/search.

## 2D. Visualization laboratory

Add more analysis views where useful:

- field evolution;
- trajectory overlays;
- gate-state timelines;
- deposition timelines;
- source activity;
- parameter-vs-metric plots;
- behavior-space scatter plots;
- run-to-run difference views;
- before/after snapshots.

## 2E. Safety and trust UI

Show:

- warnings;
- unavailable observables;
- boundedness violations;
- non-finite values;
- failed stages;
- unsupported combinations;
- provenance limitations;
- same-runtime vs cross-runtime replay status.

Never hide a scientific limitation behind a green “success” indicator.

## 2F. Human validation rounds

Each major visualization and workflow must be tested by actually running simulations.

The test protocol should include:

- first-time user walkthrough;
- researcher workflow test;
- long-ish short-horizon test;
- failure/recovery test;
- reproducibility test;
- interpretation test.

## 2G. Export/import

Support practical research interchange such as:

- JSON run metadata;
- CSV observable series;
- image export;
- compact report;
- reproducibility manifest;
- optional result bundle/archive.

Avoid committing to a heavyweight external data format until users need it.

## 2H. Performance and UX hardening

Measure:

- startup time;
- run launch latency;
- visualization latency;
- memory use;
- rendering frame rate where applicable;
- parameter validation responsiveness;
- large-run browsing behavior.

## Phase 2 acceptance gate

Researchers can conduct a repeatable experiment session without relying on raw terminal tooling, understand provenance, inspect failures/warnings, compare results, save findings, and export enough metadata to reproduce the run within the declared determinism limits.

---

# PHASE 3 — DISCOVERY & RESEARCH AUTOMATION

## Goal

Turn the simulation lab into a system that can systematically explore parameter spaces and compositions while keeping the researcher in control.

The generic discovery machinery already exists substantially; the goal is to make it **usable, inspectable, and progressively more capable**.

## 3A. Interactive parameter sweeps

UI for:

- choosing parameters;
- selecting bounded values;
- previewing variant counts;
- launching sweeps;
- progress/status;
- cancellation where supported;
- viewing completed/failed variants;
- comparing sweep results.

The UI should show exactly what will be executed before launch.

## 3B. Behavior-space exploration

Expose:

- behavior vectors;
- behavior distance;
- clustering/grouping where justified;
- representative runs;
- similarity/difference views;
- parameter-to-behavior relationships.

## 3C. Ranking and diversity frontier

Expose the existing generic ranking/frontier machinery visually:

- ranking table;
- score components where interpretable;
- diversity frontier;
- why a candidate was selected;
- composition ID;
- mutation parameters;
- linked run result.

The researcher should be able to inspect—not merely trust—a ranking result.

## 3D. Cross-composition exploration

Allow A/B/C/D to be compared through common observables and behavioral features without pretending that every metric has identical scientific meaning.

Explicitly show:

- shared observables;
- composition-specific observables;
- unavailable metrics;
- comparison caveats.

## 3E. Adaptive exploration

Generalize the current adaptive shell away from experiment-letter coupling.

Potential capabilities:

- researcher-defined action/subspace constraints;
- adaptive selection;
- bounded multi-pass exploration;
- deterministic lineage;
- exploration sessions;
- comparison of exploration trajectories.

No ML/GA/Bayesian/RL is required merely to call this adaptive exploration.

## 3F. Persistent discovery archive

Complete the archive path so discovery results can be durably recorded and later queried.

Capabilities can include:

- archived exploration sessions;
- archived comparisons;
- run/result linkage;
- provenance verification;
- feature linkage when authoritative data exists;
- corruption/audit checks;
- deterministic identities.

Do not fabricate feature linkage where the execution system cannot reconstruct it.

## 3G. Researcher-constrained discovery

Allow the researcher to specify:

- allowed compositions;
- allowed parameters/ranges;
- budget limits;
- forbidden combinations;
- required observables;
- minimum/maximum behavior constraints;
- diversity requirements;
- exploration objectives;
- seed policy;
- stop criteria.

## 3H. Discovery UI testing

The human testing loop becomes:

```text
research question
→ configure exploration
→ preview search space
→ execute
→ inspect progress
→ inspect candidates
→ inspect why they ranked
→ compare frontier
→ save/archive
→ reproduce a selected candidate
```

Test whether researchers actually understand and trust the discovery process.

## Phase 3 acceptance gate

A researcher can visually construct a bounded exploration, run it through the existing generic pipeline, inspect every stage's outputs, understand ranking/frontier outcomes, reproduce selected candidates, and preserve an auditable discovery session.

---

# PHASE 4 — GENERAL SIMULATION PLATFORM

## Goal

Generalize Simulation Alchemist from a strong research workbench/framework into a reusable platform for authoring and composing broader classes of coupled simulations.

This is where the longer-horizon architecture directions belong.

## 4A. General experiment/plugin model

Potential capabilities:

- experiment/plugin registry;
- externally packaged experiment modules;
- capability declarations;
- adapter registration;
- versioning;
- compatibility validation;
- safe discovery of installed experiments.

Only pursue this after repeated evidence that internal experiment-owned extension is insufficient.

## 4B. Adapter generalization

Remove accidental experiment-specific coupling from generic adapters.

Examples of future work:

- decouple Mesa adapter assumptions from Experiment A;
- generic agent adapter contracts;
- engine-neutral observation interfaces;
- stronger type/protocol contracts.

## 4C. General world composition

Possible future architecture beyond the existing composition model:

- more general world builders;
- reusable geometry/material/environment definitions;
- richer coupling graphs;
- multiple source/sink models;
- dynamic component creation where scientifically justified;
- declarative composition graphs.

No automatic scientific coupling inference.

## 4D. Broader coupling vocabulary

Expand supported coupling families as real experiments demand them:

- field → force;
- position → source/sink;
- field → agent sensing;
- agent intent → actuator;
- mechanics → field geometry;
- network state → agent/environment;
- events → source/force/control;
- delayed/filtered/hysteretic/control couplings.

Every new coupling must have explicit contracts and an experiment-owned validation case.

## 4E. Advanced time/event semantics

Potential future abstractions:

- multi-rate scheduling;
- event-driven updates;
- delayed couplings;
- asynchronous components with deterministic envelopes;
- checkpoint/restart;
- partial-step observability.

Only introduce these when actual experiments require them.

## 4F. Long-horizon and stress validation

After the system has a useful UI and persistent history, introduce:

- longer simulations;
- numerical stability studies;
- parameter sensitivity analysis;
- performance benchmarks;
- memory/scale tests;
- pathological-input tests;
- conservation/invariant checks where scientifically applicable.

## 4G. Cross-platform reproducibility

Eventually support stronger reproducibility guarantees:

- environment capture;
- dependency lock identity;
- engine/runtime metadata;
- numerical compatibility checks;
- cross-platform replay classification;
- result fingerprints.

Do not promise cross-platform bitwise equality where the underlying engines do not guarantee it.

## 4H. Advanced analysis ecosystem

Potential capabilities:

- richer statistical analysis;
- uncertainty analysis;
- sensitivity analysis;
- experiment batches;
- report generation;
- result provenance graphs;
- data export pipelines;
- integration with external analysis notebooks.

## 4I. Optional intelligent search

Only after the deterministic research/discovery machinery is mature may the project consider:

- Bayesian optimization;
- evolutionary search;
- reinforcement learning;
- learned surrogate models;
- active learning.

These are **optional future directions**, not requirements of the core framework.

They must sit above deterministic, auditable primitives rather than replacing them.

## 4J. Platform hardening and distribution

Eventually consider:

- packaged application/distribution;
- remote execution;
- job queues;
- parallel sweep execution;
- persistent databases;
- multi-user/project separation;
- permissions;
- cloud/HPC backends.

These should come only after local researcher workflows are proven useful.

## Phase 4 acceptance gate

Simulation Alchemist can support more than one family of coupled simulations through experiment-owned extensions, has clear generic contracts, useful researcher tooling, durable provenance, robust validation, and a demonstrably reusable extension model.

---

# 4. CROSS-PHASE CAPABILITY MAP

These capabilities may appear in different phases but should be remembered as part of the project's long-term surface.

## Authoring

- define compositions;
- declare capabilities;
- declare contracts;
- define schedules;
- generate worlds;
- define parameter spaces;
- describe experiments for humans.

## Execution

- run short simulations;
- run bounded batches;
- deterministic replay;
- checkpoint/restart;
- stage-level progress;
- failure recovery;
- cancellation.

## Observation

- live field views;
- trajectories;
- agent states;
- source/deposition events;
- gates/control states;
- scalar metrics;
- time-series;
- common and experiment-specific observables.

## Comparison

- run-to-run;
- parameter-to-parameter;
- composition-to-composition;
- behavior-space comparison;
- difference plots;
- frontier inspection.

## Discovery

- parameter sweeps;
- structural composition selection;
- behavior characterization;
- ranking;
- diversity frontier;
- adaptive exploration;
- researcher constraints;
- persistent discovery archives.

## Trust / provenance

- content-addressed identity;
- lineage;
- run manifests;
- archive audit;
- deterministic replay;
- data availability states;
- explicit synthetic-demo labeling;
- limitation reporting.

## Researcher productivity

- saved presets;
- run notes;
- tags;
- experiment history;
- exports;
- reports;
- reproducibility bundles;
- searchable archives.

## Generalization

- experiment registry;
- plugin/adapter architecture;
- reusable coupling templates;
- broader world composition;
- multi-rate/event semantics;
- external analysis integration.

---

# 5. REQUIRED ITERATION PATTERN FOR EVERY MAJOR FEATURE

Every feature that affects researcher experience must pass through this sequence:

### Step A — Design

Define:

- user problem;
- scientific purpose;
- existing API it uses;
- what is deliberately out of scope;
- success criteria;
- risks.

### Step B — Implement smallest slice

Do not build the entire subsystem before a human can touch something.

### Step C — Automated verification

Run the smallest relevant tests first, then broader regression.

### Step D — Human simulation test

A human actually performs the intended workflow.

### Step E — Record usability/science issues

Capture:

- confusion;
- misleading visualization;
- missing context;
- unexpected behavior;
- performance pain;
- scientific ambiguity.

### Step F — Fix and retest

Only then expand the feature.

### Step G — Gate and document

Update authoritative project status and preserve an evidence-backed milestone report.

---

# 6. DEFINITION OF “DONE”

A milestone is complete only when all applicable layers are green:

```text
ARCHITECTURE
    ↓
IMPLEMENTATION
    ↓
AUTOMATED TESTS
    ↓
STATIC QUALITY
    ↓
SCIENTIFIC/BEHAVIOR VALIDATION
    ↓
HUMAN UI/UX TEST
    ↓
DOCUMENTATION / PROVENANCE
    ↓
REGRESSION GATE
```

A backend feature with no user test is not fully done when that feature is intended for researchers.

A beautiful UI with unvalidated backend semantics is not done either.

---

# 7. ROADMAP GOVERNANCE

## 7.1 One authoritative current state

`PROJECT_STATE.md` remains the authoritative snapshot of what is currently complete, in progress, blocked, or next.

## 7.2 Long-term roadmap source

This document is the broad product/research North Star.

`IMPLEMENTATION_PLAN.md` may contain detailed milestone plans, but it must not contradict this roadmap.

## 7.3 Historical reports

Task reports remain historical evidence and should not be silently rewritten to change what happened.

## 7.4 No accidental milestone creation

An agent must not invent a new task number simply because it needs a label.

Before starting a new milestone, the repository should explicitly record:

- milestone name;
- objective;
- reason it comes next;
- scope;
- non-goals;
- acceptance gate.

## 7.5 Context-safe execution

For long agent sessions:

- checkpoint after major phases;
- summarize completed evidence;
- avoid re-reading huge unrelated files repeatedly;
- separate plan-only from implementation mode;
- stop at explicit gates;
- preserve exact test counts and command outputs.

---

# 8. CURRENT NEXT MOVE

The project has completed Task 3.0 Stages 1–3.

The next development effort should be **Phase 1 — Researcher Workbench**, beginning with a **PLAN-ONLY UI/UX architecture and researcher workflow design**.

That plan should answer:

- web/local desktop approach;
- frontend/backend boundary;
- existing APIs to expose;
- first five screens/views;
- simulation lifecycle in the UI;
- visualization strategy;
- result persistence strategy;
- run identity/provenance display;
- D gating ON/OFF workflow;
- testing protocol with actual humans;
- accessibility and responsive layout requirements;
- error/warning model;
- export/replay workflow;
- performance constraints;
- what must remain outside the UI.

**Do not implement the entire UI before this plan is reviewed.**

---

# 9. FIRST USER JOURNEY TO OPTIMIZE

The first successful researcher session should look like this:

```text
Open Simulation Alchemist
        ↓
Choose “Gated Mover Morphogenesis”
        ↓
See what the experiment is intended to demonstrate
        ↓
Adjust gate threshold / cooldown
        ↓
Run a short simulation
        ↓
Watch field + movers + gate states evolve
        ↓
Inspect deposition suppression / active gates / switch rate
        ↓
Compare against gating-OFF control
        ↓
Replay the selected run
        ↓
Save/export the result
```

If this flow is confusing, the project should improve the UX before adding another major research automation capability.

---

# 10. LONG-TERM NORTH STAR

The end-state vision is not “a dashboard over four experiments.”

It is:

> **A deterministic, inspectable, extensible research environment where scientists can author coupled simulation compositions, execute them safely, observe their dynamics, compare outcomes, explore parameter spaces, discover interesting behaviors, preserve provenance, and eventually extend the system with new simulation engines and coupling patterns without rewriting the generic core.**

The software should progressively move from:

```text
developer-driven prototype
```

toward:

```text
researcher-driven simulation laboratory
```

and eventually:

```text
reusable general-purpose coupled-simulation platform
```

without skipping the validation and human-testing steps between those states.
