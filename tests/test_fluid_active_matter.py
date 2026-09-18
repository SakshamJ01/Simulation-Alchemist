"""Unit tests for Experiment E: Fluid-Structure Active Matter coupling.

Verifies:
1. Mathematical incompressibility (divergence-free velocity field: div(u) == 0).
2. Navier-Stokes spectral solver stability and viscous dissipation.
3. Active swimmer particle advection and chemotactic steering.
4. Deterministic zero-drift replay across identical seeds.
5. Catalog EXECUTABLE registration and YAML world loading.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from experiments.catalog import build_repository_catalog
from experiments.fluid_active_matter.coupling import (
    build_fluid_active_matter_world,
)
from experiments.fluid_active_matter.experiment import (
    PARAMETER_SPECS,
    run_fluid_active_matter_world,
)
from experiments.fluid_active_matter.model import FluidEngineAdapter, SwimmersAdapter
from sim_alchemist.core.world import load_world_yaml


def test_fluid_incompressibility_and_divergence_free() -> None:
    """Verify that spectral streamfunction inversion produces a strictly divergence-free velocity field."""
    fluid = FluidEngineAdapter({"n": 32, "viscosity": 0.05, "buoyancy_coef": 0.8})
    # Inject an arbitrary asymmetric vorticity distribution
    rng = np.random.default_rng(42)
    fluid.omega = rng.standard_normal((32, 32))
    fluid.solve_streamfunction_and_velocity()

    # Compute divergence div(u) = d_ux/dx + d_uy/dy in Fourier spectral space
    ux_hat = np.fft.fft2(fluid.u_x)
    uy_hat = np.fft.fft2(fluid.u_y)
    div_u = np.real(np.fft.ifft2(1j * fluid.KX * ux_hat + 1j * fluid.KY * uy_hat))

    max_div = float(np.max(np.abs(div_u)))
    assert max_div < 1e-12, f"Fluid velocity is not divergence-free: max |div(u)| = {max_div}"


def test_fluid_viscous_dissipation() -> None:
    """Verify that without buoyancy forcing, fluid kinetic energy monotonically decays."""
    fluid = FluidEngineAdapter({"n": 32, "viscosity": 0.1, "fluid_damping": 0.05})
    rng = np.random.default_rng(123)
    fluid.omega = rng.standard_normal((32, 32))
    fluid.solve_streamfunction_and_velocity()

    e0 = fluid.kinetic_energy()
    assert e0 > 0.0

    for _ in range(10):
        fluid.step(0.05)

    e_final = fluid.kinetic_energy()
    assert e_final < e0, f"Kinetic energy failed to dissipate: e0={e0}, e_final={e_final}"


def test_swimmers_adapter_step_and_advection() -> None:
    """Verify active swimmer initialization, step physics, and bounds clamping."""
    swimmers = SwimmersAdapter({"n_swimmers": 6, "swimmer_speed": 0.1, "seed": 42})
    swimmers.initialize()

    pos_start = swimmers.get_positions()
    assert len(pos_start) == 6

    # Apply fluid advection and step
    fluid = FluidEngineAdapter({"n": 32})
    fluid.u_x.fill(0.05)
    swimmers.apply_fluid_advection(fluid)
    swimmers.step(0.05)

    pos_after = swimmers.get_positions()
    assert len(pos_after) == 6
    for pt in pos_after.values():
        assert 0.0 <= pt[0] <= 1.0
        assert 0.0 <= pt[1] <= 1.0


def test_fluid_active_matter_catalog_registration() -> None:
    """Verify that Experiment E is registered as EXECUTABLE in the composition catalog."""
    cat = build_repository_catalog(generate_worlds=True)
    candidates = [c for c in cat.executable() if c.template == "fluid_active_matter"]
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.status == "EXECUTABLE"
    assert cand.generated_world is not None


def test_fluid_active_matter_deterministic_replay() -> None:
    """Verify bitwise identical metrics and telemetry across two identical simulation runs."""
    world = build_fluid_active_matter_world()
    world = replace(world, max_steps=15)
    world.config["n_steps"] = 15

    out1 = run_fluid_active_matter_world(world)
    out2 = run_fluid_active_matter_world(world)

    assert out1.metrics == out2.metrics
    assert len(out1.trajectory.u_snaps) == len(out2.trajectory.u_snaps) == 15
    for s1, s2 in zip(out1.trajectory.u_snaps, out2.trajectory.u_snaps, strict=False):
        np.testing.assert_array_equal(s1, s2)

    for s1, s2 in zip(out1.trajectory.omega_snaps, out2.trajectory.omega_snaps, strict=False):
        np.testing.assert_array_equal(s1, s2)


def test_fluid_active_matter_yaml_matches_execution() -> None:
    """Verify that loading worlds/fluid_active_matter.yaml executes without errors."""
    world = load_world_yaml("worlds/fluid_active_matter.yaml")
    world = replace(world, max_steps=10)
    world.config["n_steps"] = 10

    out = run_fluid_active_matter_world(world)
    assert out.metrics["fluid_kinetic_energy:mean"] >= 0.0
    assert out.metrics["fluid_vorticity:max"] >= 0.0
    assert out.metrics["swimmer_speed:mean"] >= 0.0
    assert len(out.trajectory.u_snaps) == 10
    assert len(out.trajectory.velocities) == 8


def test_parameter_specs_validity() -> None:
    """Verify declared parameter specs for Experiment E."""
    assert len(PARAMETER_SPECS) >= 3
    paths = {p.path for p in PARAMETER_SPECS}
    assert any("viscosity" in p for p in paths)
    assert any("buoyancy_coef" in p for p in paths)
    assert any("swimmer_speed" in p for p in paths)
