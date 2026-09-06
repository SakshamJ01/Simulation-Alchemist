"""Stability / bounded-force validation tests (checks S1-S6).

Wraps ``run_stability.validate_stability``: the same nominal and extreme
world runs are executed once in a session fixture, and each S-check is
asserted through it.  The checks verify bounded trajectories, the analytic
terminal-velocity bound, NaN freedom, integrator order-of-convergence, and
short-horizon agreement across physics discretizations.
"""

import pytest

from run_stability import validate_stability


@pytest.fixture(scope="session")
def stability_results():
    """[(name, passed, detail), ...] from the validated stability suite."""
    return validate_stability(seed=0, n_steps=160)


CHECKS = {
    "S1_walls_in_bounds": "walls stay inside the domain bounds",
    "S2_speed_bounded": "speeds below the analytic terminal-velocity bound",
    "S3_no_nan": "field and forces remain finite",
    "S4_extreme_force_bounded": "extreme forcing (Fmax=10) stays bounded",
    "S5_integrator_convergence": "halving dt reduces discretization error",
    "S6_short_horizon_agreement": "physics discretization agreement",
}


@pytest.mark.parametrize("name", list(CHECKS))
def test_stability_checks(stability_results, name) -> None:
    result = {r[0]: r for r in stability_results}
    assert name in result, f"missing stability check {name}"
    passed, detail = result[name][1], result[name][2]
    assert passed, f"{name}: {detail}"