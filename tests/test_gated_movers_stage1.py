"""Task 3.0 Stage 1 structural test for Experiment D (gated mover morphogenesis).

Declaration-only: no long simulation, no sweep execution.  The only runtime
check is a FAST_STEPS (2-step) executor smoke run so the composition id ->
executor wiring is proven without a 160-step canonical D run (that belongs to
Stage 2).  Verifies: EXECUTABLE classification, composed-world identity,
contracts resolve with the 5-binding repository (mesa / py-pde /
pymunk-movers), parameter specs declared (not bound to cross-composition
sweep yet).
"""
from __future__ import annotations

from experiments.catalog import (
    build_repository_catalog,
    repository_executors,
)
from experiments.gated_movers.coupling import build_gated_movers_template
from experiments.gated_movers.experiment import PARAMETER_SPECS
from sim_alchemist.core import EXECUTABLE
from sim_alchemist.core.catalog import CatalogCandidate
from tests.test_composition_search import build_fast_repository_catalog


def _dd_row(catalog) -> CatalogCandidate:
    return next(c for c in catalog.executable() if c.template == "gated_movers")


def test_d_template_is_executable_via_repository() -> None:
    catalog = build_repository_catalog()
    d = _dd_row(catalog)
    assert d.status == EXECUTABLE
    assert d.template == "gated_movers"
    assert catalog.status_counts()["EXECUTABLE"] == 4


def test_d_template_has_all_contracts() -> None:
    template = build_gated_movers_template()
    names = [c.name for c in template.contracts]
    # mover-gate uses consumer_capability="rigid_body" (the movers adapter's
    # own capability) rather than "field_sources"; the pymunk/movers adapter
    # does not expose field_sources, so this is the resolvable formulation.
    # Documented deviation from the design's provisional proposal (itself a
    # plan-only sketch, not an implemented binding).
    assert "mover-gate" in names
    assert "field-sensing" in names
    assert "gradient-force" in names
    assert "mover-source" in names


def test_d_parameter_specs_declared() -> None:
    assert len(PARAMETER_SPECS) == 3
    paths = [s.path for s in PARAMETER_SPECS]
    assert "config.gate_threshold" in paths
    assert "config.gate_cooldown" in paths
    assert "config.source_amplitude" in paths


def test_d_executor_registered_smoke() -> None:
    executors = repository_executors()
    catalog = build_fast_repository_catalog(generate_worlds=True)
    d = _dd_row(catalog)
    assert d.composition_id in executors
    assert d.generated_world is not None
    outcome = executors[d.composition_id](d.generated_world)
    assert outcome.metrics
    assert "gate_switch_rate" in outcome.metrics