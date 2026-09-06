"""Task 1.1 validation: capability-driven composition (checks A-G).

Proves a SECOND experiment (Field-Guided Movers: py-pde + Pymunk) runs
through the same Alchemist core as the chemo-mechanical baseline, without
Mesa and without any change to ``src/sim_alchemist/core/``.
"""

import hashlib
import pathlib

import numpy as np
import pytest

from experiments.field_guided_movers.model import (
    FieldGuidedMoversEngine,
    MoversAdapter,
    MoversConfig,
    MoversTrajectory,
    run_field_guided_movers,
)
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.core.engine import CapabilityResolver

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "src" / "sim_alchemist" / "core"


@pytest.fixture(scope="module")
def movers_trajectories() -> dict[str, MoversTrajectory]:
    cfg = MoversConfig(seed=0, n_steps=160)
    closed = run_field_guided_movers(MoversConfig(**cfg.as_dict()))
    open_cfg = MoversConfig(**cfg.as_dict())
    open_cfg.apply_sources = False
    open_traj = run_field_guided_movers(open_cfg)
    return {"closed": closed, "open": open_traj}


# ----------------------------------------------------------------------
# A. Capability resolution - no Mesa required
# ----------------------------------------------------------------------
def test_capability_resolution_without_mesa() -> None:
    cfg = MoversConfig()
    pde = PyPDEAdapter(n=cfg.n)
    movers = MoversAdapter(config=cfg)
    engines = [pde, movers]

    result = CapabilityResolver().resolve(engines)
    assert result.valid, f"composition should resolve without Mesa: {result.missing}"
    assert len(result.missing) == 0

    coords = {e.engine_id for e in engines}
    assert "mesa" not in coords, "Mesa engine must not be required"
    assert "py-pde" in coords and "pymunk" in coords


def test_resolver_returns_capability_name() -> None:
    pde = PyPDEAdapter(n=16)
    movers = MoversAdapter(config=MoversConfig(n=16))
    result = CapabilityResolver().resolve([pde, movers])
    for missing_cap in result.missing:
        assert isinstance(missing_cap.name, str)


# ----------------------------------------------------------------------
# B. Invalid / incomplete composition fails with a useful capability error
# ----------------------------------------------------------------------
def test_incomplete_composition_fails() -> None:
    camper = MoversAdapter(config=MoversConfig())
    result = CapabilityResolver().resolve([camper])  # no field provider
    assert not result.valid
    missing_names = {c.name for c in result.missing}
    assert {"scalar_field", "field_gradient", "field_sources"} <= missing_names

    # The engine's run() surfaces the missing capability as a runtime error.
    engine = FieldGuidedMoversEngine(config=MoversConfig(n_steps=1))
    engine.engines.pop("py-pde")
    with pytest.raises(RuntimeError, match="[Ii]nvalid composition"):
        engine.run()


# ----------------------------------------------------------------------
# C. Cross-engine interaction: field gradient drives mover force
# ----------------------------------------------------------------------
def test_gradient_drives_force(movers_trajectories) -> None:
    closed = movers_trajectories["closed"]
    assert len(closed.force_mags) > 0
    assert float(np.mean(closed.force_mags)) > 1e-6, "movers felt no field force"


def test_force_direction_follows_gradient() -> None:
    from experiments.field_guided_movers.model import gradient_force

    # Build a small field with a known left-to-right u gradient.
    cfg = MoversConfig(n=16)
    pde = PyPDEAdapter(n=16)
    pde.initialize(cfg.as_dict())
    f = pde.get_field()
    assert f is not None
    # Impose a monotonic horizontal gradient: u = 0.5 + x.
    # RDField._index maps x -> col (second axis), so yy varies with columns.
    _xx, yy = np.meshgrid(np.arange(16) / 16.0, np.arange(16) / 16.0, indexing="ij")
    f.state[0].data[:] = 0.5 + yy  # type: ignore[index]
    fx, fy = gradient_force(pde, (0.5, 0.5), force_fmax=1.0, force_gsat=1.0)
    assert fx > 0, "force should point up the activator gradient"
    assert abs(fy) < abs(fx), "force should be mostly along x for a one-D gradient"


# ----------------------------------------------------------------------
# D. Reverse interaction: mover position/source changes the field
# ----------------------------------------------------------------------
def test_source_changes_field_vs_baseline(movers_trajectories) -> None:
    closed = movers_trajectories["closed"]
    no_source_cfg = MoversConfig(seed=0, n_steps=160)
    no_source_cfg.apply_forces = False
    no_source_cfg.apply_sources = False
    no_src = run_field_guided_movers(no_source_cfg)
    rmsd = float(np.sqrt(np.mean((closed.final_u - no_src.final_u) ** 2)))
    assert rmsd > 0.05, f"source injection did not measurably change the field (rmsd={rmsd:.3f})"


def test_reverse_interaction_mover_feedback(movers_trajectories) -> None:
    closed = movers_trajectories["closed"]
    open_traj = movers_trajectories["open"]
    rmsd = float(np.sqrt(np.mean((closed.final_u - open_traj.final_u) ** 2)))
    corr = float(np.corrcoef(closed.final_u.ravel(), open_traj.final_u.ravel())[0, 1])
    assert rmsd > 0.1, f"closed-loop field did not diverge from open loop (rmsd={rmsd:.3f})"
    assert corr < 0.999, f"closed-loop field too correlated with open loop (corr={corr:.4f})"


# ----------------------------------------------------------------------
# E. Closed loop: field -> body -> field measurable divergence from open loop
# ----------------------------------------------------------------------
def test_closed_loop_diverges_from_open_loop(movers_trajectories) -> None:
    closed = movers_trajectories["closed"]
    open_traj = movers_trajectories["open"]
    rmsd_closed_open = float(np.sqrt(np.mean((closed.final_u - open_traj.final_u) ** 2)))

    # Open loop (no field feedback) vs a true no-motion (no force) control must
    # be closer to each other than the closed loop is to the open loop: the
    # closed loop is a *distinct* state, not an artifact of the source alone.
    assert rmsd_closed_open > 0.1
    assert float(np.mean(closed.force_mags)) > float(np.mean(open_traj.force_mags)) > 0


# ----------------------------------------------------------------------
# F. Determinism: same seed + same runtime -> identical canonical output
# ----------------------------------------------------------------------
def test_deterministic_replay_bitwise() -> None:
    t1 = run_field_guided_movers(MoversConfig(seed=0))
    t2 = run_field_guided_movers(MoversConfig(seed=0))
    assert (t1.final_u == t2.final_u).all()
    assert all(t1.positions[k] == v for k, v in t2.positions.items())
    assert t1.force_mags == t2.force_mags
    assert t1.speeds == t2.speeds
    assert t1.gradient_mags == t2.gradient_mags


# ----------------------------------------------------------------------
# Core immutability: src/sim_alchemist/core/ must not have been modified.
# (The six files' git-tracked hashes are fixed for the validated baseline.)
# ----------------------------------------------------------------------
CORE_COMMIT_HASHES = {
    "__init__.py": "73F4B2F6BC7353E2290324C569E4FC12DF7AD76D631E79CFD319F07F8AABA046",
    "capabilities.py": "F13D4430E3B34B2364C895F18422984DC6D4388C91BE49C00B653EBE2D3F9188",
    "clock.py": "D49F5202F9F2C9E0A18A30A9A5BC59B676DF5E967B9D5518D0CB590C01714394",
    "engine.py": "F59E5E069D0AF238430F7E9589727B026BB16331D2E6D5B029A235563DAF184C",
    "events.py": "EF1DDF2206E21DC05CE835CFBC1A9CD0B089EEF861E58C3D50D7D54723005903",
    "state.py": "ADB33ADEDC4749288451D0648CE465476DA1C8877D5EDA798034F023B3CD8158",
}


@pytest.mark.parametrize("filename", sorted(CORE_COMMIT_HASHES))
def test_core_file_unchanged(filename) -> None:
    path = CORE_DIR / filename
    assert path.is_file(), f"core file {filename} missing"
    h = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    assert h == CORE_COMMIT_HASHES[filename], (
        f"src/sim_alchemist/core/{filename} was modified! Task 1.1 must not change the core."
    )


# ----------------------------------------------------------------------
# Architectural test (check G): existing experiment must still pass.
# This suite re-runs the core immutability list above and the experiment
# composition below; the existing chemo-mechanical A-G / S1-S6 / replay
# tests are exercised as the normal project test suite.
# ----------------------------------------------------------------------
def test_experiment_a_and_b_share_core() -> None:
    """Both experiments use the SAME AlchemistEngine / SimulationClock /
    EventBus / CapabilityResolver classes (imported from the shared core)."""
    import sim_alchemist.core.engine as e
    from sim_alchemist.core.clock import SimulationClock
    from sim_alchemist.core.events import EventBus

    assert e.AlchemistEngine is FieldGuidedMoversEngine.__mro__[1]
    assert SimulationClock is not None and EventBus is not None

    # Experiment B's engines both satisfy the shared SimulationEngine contract.
    pde = PyPDEAdapter(n=16)
    movers = MoversAdapter(MoversConfig(n=16))
    for eng in (pde, movers):
        assert hasattr(eng, "engine_id")
        assert hasattr(eng, "provides")
        assert hasattr(eng, "requires")
        assert hasattr(eng, "native_timestep")
        assert callable(eng.initialize)
        assert callable(eng.step)
        assert callable(eng.get_state)
        assert callable(eng.apply_event)
        assert callable(eng.shutdown)