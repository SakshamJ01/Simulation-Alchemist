# Simulation Alchemist — Baseline v0.1

**Baseline v0.1** of Simulation Alchemist is the **validated chemo-mechanical
prototype** (Tasks 0.1–0.3). It is the verified scientific starting point out
of which the Simulation Alchemist composition core will be extracted. This is
a working scientific prototype, not yet the framework.

## What this prototype is

Three independent simulation engines are composed into a single deterministic
closed feedback loop. A morphogen (activator) field grows Turing patterns, a
set of wall agents sense the field and deposit/dissolve rigid mechanical
walls, and the walls both block the field and are themselves pushed around by
the field's gradient. Field changes the geometry, geometry changes the field,
and the agents couple the two.

## The three simulation engines

| Engine | Role | Module |
|--------|------|--------|
| **py-pde** | Continuous reaction-diffusion subsystem (Schnakenberg field, wall cells frozen) | `chemomech/reaction_diffusion.py` |
| **Pymunk** | Rigid-body/wall subsystem (dynamic rod bodies, damping, bounds clamping) | `chemomech/physics.py` |
| **Mesa** | Agent subsystem (wall-building agents sense the field and decide) | `chemomech/agents.py` |

The orchestration loop that wires them together lives un-refactored in
`chemomech/simulation.py`.

## The feedback loop

Macro-step order (deterministic):

```
1. geometry    read live wall transforms from pymunk
2. rasterize   walls -> PDE blocked-cell mask (fed to the PDE RHS)
3. evolve      py-pde advances the reaction-diffusion field
4. sample      field gradient at each wall centre of mass
5. apply       bounded force to each wall body at its COM
6. advance     pymunk integrates wall motion (force, damping, bounds clamp)
7. agents      Mesa agents sense the NEW field and decide wall build/dissolve
8. translate   dissolve then create walls in the pymunk space
```

```
        +------------------+      +------------------+
        |  Mesa agents     | ---> |  wall placement  |
        |  sense + decide  | <--- |  intentions      |
        +------------------+      +------------------+
                ^                          |
                | u(x,t)                   v
        +------------------+      +------------------+
        |  py-pde field    | <--- |  rasterized mask |
        |  evolves         | ---> |  Pymunk walls    |
        +------------------+      +--------+---------+
                ^                           |
                +------ field force -------+
```

The force model is deliberately simple and documented in
`chemomech/simulation.py`: `F = Fmax * tanh(|grad u| / g_sat) * grad u/|grad u|`
applied at each wall centre of mass, so wall motion is bounded, damped, and
clamped to the world bounds.

## Installing

Requires `uv` (installed separately) and Python 3.13. The parser of package
wheels is resolved and locked for a reproducible environment:

```
uv sync
```

This creates `.venv` from `uv.lock`. All commands below are run through `uv run`
so no globally installed packages are needed.

## Running validation (checks A–G + figures)

```
uv run python run_validation.py
```

Runs four world experiments (baseline, static, dynamic, replay) plus a
mechanical machine test, and writes the baseline-evidence figures:

| Figure | Content | Evidence |
|--------|---------|----------|
| `figures/01_baseline_turing.png` | morphogen pattern, no walls | A |
| `figures/02_static_wall_coupling.png` | static walls + blocked cells + field | A, C |
| `figures/03_dynamic_wall_coupling.png` | dynamic walls + trajectories + field | B, D, F |
| `figures/04_wall_trajectory.png` | every wall's centre-of-mass path | B, F |
| `figures/05_feedback_metrics.png` | walls, force, speed, decisions over time | F |

## Running stability checks (S1–S6)

```
uv run python run_stability.py
```

Verifies boundedness of the coupled loop: walls stay in the domain, speeds
respect the analytic terminal-velocity bound, no NaN/Inf, extreme forcing stays
bounded, integrator order of convergence, and short-horizon agreement across
physics discretizations.

## Running the test suite

```
uv run pytest
```

`tests/` wraps the same scientific checks (A–G and S1–S6) as pytest without
recomputing the simulations per test. The suite is slow on purpose: a full
160-macro-step world run takes roughly a minute.

## Scientific limitations (preserved, not hidden)

- The clamped-obstacle PDE approximation (wall cells frozen) is **not** a true
  no-flux boundary.
- Parameters are hand-tuned for the validated runs.
- The wall model is simplified (thin frictionless rods; walls pass through
  walls).
- The Pymunk/PDE coupling is an experimental model, not a calibrated
  physics/simulation claim.
- Claims of sustained non-equilibrium behaviour remain hypotheses to be
  tested.
- Deterministic replay is same-runtime/environment; it is **not** universal
  cross-platform bitwise equivalence.

## Development commands

- `uv run pytest tests/` — run all tests
- `uv run python -m ruff check .` — lint
- `uv run pyright` — type checking

See `AGENTS.md` for current repository state and `IMPLEMENTATION_PLAN.md` for
the roadmap.