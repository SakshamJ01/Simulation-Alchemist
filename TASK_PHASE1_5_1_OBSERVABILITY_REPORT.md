# Phase 1.5.1 — Simulation Observability & Visual Validation Report

## 1. Implemented Behavior

### A. Real Trajectory & Telemetry Serialization (`workbench/app.py`)
- Trajectory frames are serialized truthful to the underlying simulation execution via `_serialize_trajectory(trajectory)`:
  - `u_snaps`: Real 2D reaction-diffusion scalar field snapshot matrices extracted from `MoversTrajectory` and `GatedMoversTrajectory`.
  - `positions`: Exact per-mover coordinate paths `[(x0, y0), (x1, y1), ...]` in $[0.0, 1.0]$.
  - `speeds`, `force_mags`, `gradient_mags`: True recorded per-step floats.
  - `active_gates`, `suppressed_gates`, `gate_deposits`: Real per-step policy observables.
- No synthetic or fabricated frames are generated or displayed.

### B. Truthful Canvas Rendering & Scrubber Controls (`workbench/templates/index.html`)
- **2D Field Heatmap**: Implemented an HTML5 2D Canvas rendering engine mapping scalar field values $u$ to the perceptually uniform **Viridis** colormap (`#440154` $\to$ `#21918c` $\to$ `#fde725`).
- **Mover Visuals**: Continuous mover coordinates rendered with historical trajectory trails and direction vectors.
- **Gate Indicators**: In Experiment D, mover tokens display active vs closed gate status rings.
- **Time Navigation**: Interactive Play/Pause, Step Forward, Step Backward, and Scrubbing controls bound strictly to the sequence of recorded macro-steps ($0 \dots N-1$).
- **Live Telemetry Readout**: Displays speed, force, and active gate counts corresponding to the selected frame.

### C. Gating ON vs OFF Controlled Comparison & Provenance Fix (`workbench/app.py` & `workbench/templates/index.html`)
- `/comparison` executes two distinct, controlled simulation runs:
  - Branch ON: Gated Sensing with hysteresis ($T=0.50$, cooldown=4).
  - Branch OFF: Unconditional Chemotaxis ($T=0.00$, cooldown=0).
- Fixed the previous provenance collision bug by explicitly updating the execution configurations so that both runs yield distinct content-addressed SHA-256 Run IDs (`on_run_id != off_run_id`).
- Real metric deltas are computed and displayed in a diff table alongside dual side-by-side comparison canvases (`canvas-on` vs `canvas-off`).

---

## 2. Automated Evidence

### A. Focused Workbench Test Suite (`tests/test_workbench.py`)
Ran `uv run pytest tests/test_workbench.py -v`:
- `test_flask_import`: PASSED
- `test_index_route`: PASSED
- `test_run_d_gated_movers`: PASSED (verified trajectory presence and field frames)
- `test_run_abc_experiments`: PASSED (verified A, B, C execution through `/run`)
- `test_run_invalid_requests`: PASSED (verified 400 error on unknown experiment)
- `test_comparison_route`: PASSED (verified distinct Run IDs, non-zero deltas, and dual trajectories)
**Result: 6 passed in 63.08s**

### B. Static Analysis & Linting
- **Ruff**: `uv run ruff check workbench/ tests/test_workbench.py`
  - Output: `All checks passed!` (0 errors)
- **Pyright**: `uv run pyright workbench/app.py tests/test_workbench.py`
  - Output: `0 errors, 0 warnings, 0 informations`

### C. Baseline Science & Stability Gates
- **Scientific Validation (`run_validation.py`)**: Checks A–G PASSED.
  - A: static reproduces 0.2
  - B: mechanical response
  - C: geometry feedback
  - D: field feedback
  - E: agent feedback
  - F: closed loop
  - G: determinism
  - Output: `ALL PASSED: True`
- **Numerical Stability (`run_stability.py`)**: Checks S1–S6 PASSED.
  - S1: walls in bounds
  - S2: speed bounded
  - S3: no NaN
  - S4: extreme force bounded
  - S5: integrator convergence
  - S6: short horizon agreement
  - Output: `ALL STABILITY CHECKS PASSED: True`

---

## 3. Manual Browser Evidence
- **Experiment B Flow**:
  1. Select `field_guided_movers` $\to$ Set `max_steps=12`, `seed=42` $\to$ Click `Run Simulation`.
  2. Canvas renders the evolving Schnakenberg field and green mover tokens.
  3. Clicking `Play` animates movers along the field gradient with trailing motion history.
  4. Scrubber slider allows frame-by-frame inspection ($0/12 \to 12/12$).
  5. Telemetry reflects real recorded speed and force magnitude.
  6. Provenance JSON export downloads intact session record.
- **Experiment D Flow**:
  1. Select `gated_movers` $\to$ Gate Threshold and Cooldown controls appear.
  2. Run simulation with $T=0.50$ $\to$ Observe field evolution and gated deposition events.
  3. Click `Compare Gating ON vs OFF`:
     - Two distinct runs execute.
     - Provenance bar confirms distinct SHA-256 IDs (e.g. `on_run_id: 329b98f6...` vs `off_run_id: 5c975ef...`).
     - Delta table displays true differences (`deposition_events`: $0.0$ vs $36.0$, $\Delta = -36.0$; `deposition_suppression`: $36.0$ vs $0.0$, $\Delta = +36.0$).
     - Dual canvases visually illustrate the spatial differences between Gated vs Unconditional chemotaxis.

---

## 4. Remaining Limitations
- Single-step simulation resolution is bound to macro-step recordings (`u_snaps` frequency). Sub-step micro-integrations in physics are aggregated into macro-step positions.
- Full 2D scalar fields are sent over JSON; for very large grids ($N > 256$) or long horizons ($N > 500$), decimation or binary payload formats will be recommended in future phases.
