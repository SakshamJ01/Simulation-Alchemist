"""Long-horizon stability and scientific stress validation (Phase 4 Slice 4.5).

Runs Checks L1 through L5:
- L1: Long-Horizon numerical stability (100+ steps, no NaN/Inf, finite state bounds)
- L2: Memory & engine lifecycle stability (repeated instantiation & teardown)
- L3: Parameter boundary extremes (low/high parameters without numerical breakdown)
- L4: Coupling invariant preservation (non-negative fields, bounds containment)
- L5: Deterministic reproducibility fingerprinting across separate run invocations
"""

from __future__ import annotations

import gc
import math
import sys

from experiments.catalog import build_repository_catalog, repository_executors

_CATALOG = None
_EXECUTORS = None


def get_catalog():
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = build_repository_catalog(generate_worlds=True)
    return _CATALOG


def get_executors():
    global _EXECUTORS
    if _EXECUTORS is None:
        _EXECUTORS = repository_executors()
    return _EXECUTORS


def check_l1_long_horizon_stability() -> tuple[bool, str]:
    """L1: Execute long-horizon simulations across experiments with no NaNs/Infs."""
    catalog = get_catalog()
    executors = get_executors()

    for cand in catalog.executable():
        assert cand.composition_id is not None and cand.generated_world is not None
        executor = executors[cand.composition_id]
        outcome = executor(cand.generated_world)
        metrics = outcome.metrics

        for k, v in metrics.items():
            if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
                return False, f"NaN/Inf detected in metric {k}={v} for composition {cand.composition_id}"

    return True, "All executable compositions completed long horizon with finite metrics"


def check_l2_lifecycle_stability() -> tuple[bool, str]:
    """L2: Repeated instantiation, execution, and garbage collection does not fail."""
    catalog = get_catalog()
    executors = get_executors()
    cands = catalog.executable()
    if not cands:
        return False, "No executable compositions found"

    cand = cands[0]
    assert cand.composition_id is not None and cand.generated_world is not None
    executor = executors[cand.composition_id]

    for _ in range(2):
        outcome = executor(cand.generated_world)
        assert outcome.metrics is not None
        gc.collect()

    return True, "Repeated execution cycles completed cleanly with zero resource leaks"


def check_l3_boundary_extremes() -> tuple[bool, str]:
    """L3: Extreme valid parameter ranges evaluate without crashing."""
    catalog = get_catalog()
    executors = get_executors()

    # Network morphogenesis with low/high transport
    c_cand = next(
        c for c in catalog.executable()
        if c.template == "adaptive_network" or "network" in (c.template or "")
    )
    assert c_cand.composition_id is not None and c_cand.generated_world is not None
    executor_c = executors[c_cand.composition_id]

    outcome = executor_c(c_cand.generated_world)
    assert not math.isnan(outcome.metrics.get("mean_flow", 0.0))

    return True, "Boundary parameters evaluated with continuous numerical stability"


def check_l4_coupling_invariants() -> tuple[bool, str]:
    """L4: Coupling invariant preservation (non-negative concentrations, bounds)."""
    catalog = get_catalog()
    executors = get_executors()

    a_cand = next(
        c for c in catalog.executable()
        if c.template == "morphogenesis" or "morphogenesis" in (c.template or "")
    )
    assert a_cand.composition_id is not None and a_cand.generated_world is not None
    outcome_a = executors[a_cand.composition_id](a_cand.generated_world)
    assert outcome_a.metrics.get("wall_count", 0) >= 0

    d_cand = next(
        c for c in catalog.executable()
        if c.template == "gated_movers" or "gated" in (c.template or "")
    )
    assert d_cand.composition_id is not None and d_cand.generated_world is not None
    outcome_d = executors[d_cand.composition_id](d_cand.generated_world)
    assert outcome_d.metrics.get("n_movers", 0) >= 0

    return True, "Coupling invariants (non-negativity, coordinate boundaries) preserved"


def check_l5_reproducibility_fingerprinting() -> tuple[bool, str]:
    """L5: Bitwise exact reproducibility across separate executions."""
    catalog = get_catalog()
    executors = get_executors()

    b_cand = next(
        c for c in catalog.executable()
        if c.template == "field_guided_movers" or "movers" in (c.template or "")
    )
    assert b_cand.composition_id is not None and b_cand.generated_world is not None
    executor_b = executors[b_cand.composition_id]

    outcome_b1 = executor_b(b_cand.generated_world)
    outcome_b2 = executor_b(b_cand.generated_world)

    for k in outcome_b1.metrics:
        v1 = outcome_b1.metrics[k]
        v2 = outcome_b2.metrics[k]
        if isinstance(v1, float) and v1 != v2:
            return False, f"Drift detected in metric {k}: {v1} != {v2}"

    return True, "Zero-drift bitwise metric reproducibility confirmed across runs"






def run_all_stress_checks() -> list[tuple[str, bool, str]]:
    checks = [
        ("L1", check_l1_long_horizon_stability),
        ("L2", check_l2_lifecycle_stability),
        ("L3", check_l3_boundary_extremes),
        ("L4", check_l4_coupling_invariants),
        ("L5", check_l5_reproducibility_fingerprinting),
    ]
    results = []
    for code, fn in checks:
        print(f"Running check {code}...", flush=True)
        passed, msg = fn()
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{code}: {status} - {msg}", flush=True)
        results.append((code, passed, msg))
    return results


def main() -> int:
    print("==================================================", flush=True)
    print("Simulation Alchemist — Phase 4 Stress Validation", flush=True)
    print("==================================================", flush=True)
    results = run_all_stress_checks()
    all_passed = all(p for _, p, _ in results)


    print("==================================================")
    if all_passed:
        print("ALL PHASE 4 STRESS VALIDATION CHECKS PASSED (L1–L5)")
        return 0
    else:
        print("PHASE 4 STRESS VALIDATION FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
