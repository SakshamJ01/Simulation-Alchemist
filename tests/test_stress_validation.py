"""Pytest wrapper for Phase 4 stress validation checks L1 through L5."""

from __future__ import annotations

import pytest
from run_stress_validation import (
    check_l1_long_horizon_stability,
    check_l2_lifecycle_stability,
    check_l3_boundary_extremes,
    check_l4_coupling_invariants,
    check_l5_reproducibility_fingerprinting,
)


@pytest.mark.parametrize("fn", [
    check_l1_long_horizon_stability,
    check_l2_lifecycle_stability,
    check_l3_boundary_extremes,
    check_l4_coupling_invariants,
    check_l5_reproducibility_fingerprinting,
])
def test_phase4_stress_check(fn) -> None:
    passed, msg = fn()
    assert passed, msg

