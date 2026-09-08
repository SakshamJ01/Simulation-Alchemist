"""Composition catalog tests (Task 2.3 Stage 5).

The ``CompositionCatalog`` pre-classifies every shape of a ``CompositionSpace``
through the executable taxonomy and makes each decision reachable as a flat
``CatalogCandidate`` row.  These tests pin the repository catalog's exact shape
(23 = 16 capability-invalid + 4 coupling-unavailable + 3 executable), probe its
query surface, prove that construction performs no simulation and no world
generation unless asked, and keep the two new core modules experiment-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from experiments.catalog import (
    build_repository_adapters,
    build_repository_catalog,
    repository_bindings,
    repository_surfaces,
    repository_templates,
)
from sim_alchemist.adapters.base import BaseAdapter
from sim_alchemist.core import (
    CAPABILITY_INVALID,
    COUPLING_UNAVAILABLE,
    EXECUTABLE,
    CompositionSpace,
    generate_world,
    template_composition_id,
)
from sim_alchemist.core.catalog import CatalogCandidate, CompositionCatalog
from sim_alchemist.core.registry import AdapterFactory
from sim_alchemist.core.templates import classify_composition

CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "sim_alchemist" / "core"

EXPECTED = {CAPABILITY_INVALID: 16, COUPLING_UNAVAILABLE: 4, EXECUTABLE: 3}


def _bindings_set(candidate: CatalogCandidate) -> set[tuple[str, str | None]]:
    return {(b.component, b.variant) for b in candidate.bindings}


class TestCatalogShape:
    def test_full_catalog_has_23_candidates(self) -> None:
        catalog = build_repository_catalog()
        assert len(catalog.all()) == 23
        assert len(catalog.invalid()) == 20
        assert len(catalog.executable()) == 3

    def test_status_counts_exact(self) -> None:
        assert build_repository_catalog().status_counts() == EXPECTED

    def test_query_surfaces_agree(self) -> None:
        catalog = build_repository_catalog()
        assert len(catalog.by_status(EXECUTABLE)) == 3
        assert len(catalog.by_status(COUPLING_UNAVAILABLE)) == 4
        assert len(catalog.by_status(CAPABILITY_INVALID)) == 16
        assert len(catalog.by_status("nonsense-status")) == 0

    def test_candidates_match_their_shape(self) -> None:
        catalog = build_repository_catalog()
        for candidate in catalog.all():
            assert candidate.shape.bindings == candidate.bindings
            assert candidate.shape.shape_id == candidate.shape_id

    def test_by_shape_id_and_missing(self) -> None:
        catalog = build_repository_catalog()
        candidate = catalog.executable()[0]
        assert catalog.by_shape_id(candidate.shape_id) is candidate
        assert catalog.by_shape_id("nope") is None
        assert "no candidate" in catalog.explain("nope")


class TestCatalogExecutable:
    def test_executable_are_the_three_experiment_worlds(self) -> None:
        catalog = build_repository_catalog()
        by_binding = {tuple(sorted(_bindings_set(c))): c for c in catalog.executable()}
        assert set(by_binding) == {
            (("mesa", None), ("py-pde", None), ("pymunk", "walls")),
            (("py-pde", None), ("pymunk", "movers")),
            (("network", None), ("py-pde", None), ("pymunk", "walls")),
        }
        templates = {c.template for c in catalog.executable()}
        assert templates == {"adaptive_network", "field_guided_movers", "morphogenesis"}

    def test_executable_composition_id_matches_template(self) -> None:
        catalog = build_repository_catalog()
        registry = repository_templates()
        for candidate in catalog.executable():
            template = registry.by_name(candidate.template or "")
            assert template is not None
            assert candidate.composition_id == template_composition_id(template)
            assert candidate.reason is None
            assert candidate.missing_capabilities == ()
            assert candidate.generated_world_available

    def test_classification_agrees_with_direct_funnel(self) -> None:
        catalog = build_repository_catalog()
        for candidate in catalog.executable():
            verdict = classify_composition(
                candidate.shape,
                repository_surfaces(),
                repository_templates(),
                build_adapters=build_repository_adapters,
            )
            assert verdict.status == EXECUTABLE
            assert verdict.template == candidate.template

    def test_coupling_unavailable_candidates_are_unbound(self) -> None:
        catalog = build_repository_catalog()
        for candidate in catalog.by_status(COUPLING_UNAVAILABLE):
            assert candidate.template is None
            assert candidate.composition_id is None
            assert candidate.reason is not None
            assert "no declared CouplingTemplate" in candidate.reason
            assert not candidate.generated_world_available

    def test_capability_invalid_candidates_report_missing(self) -> None:
        catalog = build_repository_catalog()
        for candidate in catalog.by_status(CAPABILITY_INVALID):
            assert candidate.missing_capabilities
            assert "capability" in (candidate.reason or "")

    def test_explain_is_decision_reachable(self) -> None:
        catalog = build_repository_catalog()
        candidate = catalog.by_status(COUPLING_UNAVAILABLE)[0]
        text = candidate.explain()
        assert candidate.shape_id in text
        assert COUPLING_UNAVAILABLE in text
        assert "reason:" in text or "no declared CouplingTemplate" in text


class TestCatalogWorldGeneration:
    def test_worlds_generated_only_for_executable(self) -> None:
        registry = repository_templates()
        catalog = build_repository_catalog(generate_worlds=True)
        executable = catalog.executable()
        assert len(executable) == 3
        for candidate in catalog.all():
            if candidate.status == EXECUTABLE:
                assert candidate.generated_world is not None
                template = registry.by_name(candidate.template or "")
                assert template is not None
                assert candidate.generated_world.id == template.world_id
            else:
                assert candidate.generated_world is None

    def test_generated_world_is_the_template_world(self) -> None:
        catalog = build_repository_catalog(generate_worlds=True)
        registry = repository_templates()
        for candidate in catalog.executable():
            template = registry.by_name(candidate.template or "")
            assert template is not None
            assert candidate.generated_world == generate_world(template)

    def test_generation_is_opt_in(self) -> None:
        assert all(c.generated_world is None for c in build_repository_catalog().all())


class TestCatalogNoSimulation:
    def test_construction_never_initializes_or_steps(self, monkeypatch) -> None:
        def _boom(self, *args: Any, **kwargs: Any):
            raise AssertionError(f"{self.__class__.__name__} must not be run during catalog construction")

        monkeypatch.setattr(BaseAdapter, "initialize", _boom)
        monkeypatch.setattr(BaseAdapter, "step", _boom)
        monkeypatch.setattr(BaseAdapter, "shutdown", _boom)
        monkeypatch.setattr(BaseAdapter, "apply_event", _boom)
        build_repository_catalog(generate_worlds=True)

    def test_no_simulation_also_for_classify_only(self, monkeypatch) -> None:
        def _boom(self, *args: Any, **kwargs: Any):
            raise AssertionError("adapters must not run here")

        monkeypatch.setattr(BaseAdapter, "initialize", _boom)
        monkeypatch.setattr(BaseAdapter, "step", _boom)
        for _ in range(2):
            build_repository_catalog()

    def test_construction_builds_adapters_only_for_matched_shapes(self, monkeypatch) -> None:
        builds = [0]

        def _counting(self, config: dict[str, Any]):
            builds[0] += 1
            return self.builder(config)

        monkeypatch.setattr(AdapterFactory, "build", _counting)
        surfaces = repository_surfaces()
        templates = repository_templates()
        build_count_before = builds[0]
        space = CompositionSpace(
            name="repository",
            universe=tuple(sorted(surfaces, key=lambda b: (b.component, b.variant or ""))),
            min_size=1,
            max_size=4,
        )
        catalog = CompositionCatalog(
            space,
            surfaces,
            templates,
            build_adapters=build_repository_adapters,
        )
        # Only the three template-matched shapes construct adapters during
        # classification: 3 (A) + 2 (B) + 3 (C) components.
        assert builds[0] - build_count_before == 3 + 2 + 3
        assert len(catalog.executable()) == 3

    def test_world_generation_happens_only_when_requested(self, monkeypatch) -> None:
        import sim_alchemist.core.catalog as catalog_module

        calls = [0]
        original = catalog_module.generate_world

        def _counting(*args: Any, **kwargs: Any):
            calls[0] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(catalog_module, "generate_world", _counting)
        build_repository_catalog(generate_worlds=False)
        assert calls[0] == 0

        build_repository_catalog(generate_worlds=True)
        assert calls[0] == 3  # exactly the three EXECUTABLE candidates


class TestCatalogDeterminism:
    def test_two_constructions_are_identical(self) -> None:
        a = build_repository_catalog(generate_worlds=True)
        b = build_repository_catalog(generate_worlds=True)
        assert [c.shape_id for c in a.all()] == [c.shape_id for c in b.all()]
        assert [c.status for c in a.all()] == [c.status for c in b.all()]
        assert [c.composition_id for c in a.all()] == [c.composition_id for c in b.all()]
        for ca, cb in zip(a.all(), b.all()):
            if ca.status == EXECUTABLE:
                assert ca.generated_world == cb.generated_world
            else:
                assert ca.generated_world is None and cb.generated_world is None

    def test_universe_and_binding_order_stable(self) -> None:
        assert [b.component for b in repository_bindings()] == [
            "mesa", "network", "py-pde", "pymunk", "pymunk",
        ]
        variants = {b.component: b.variant for b in repository_bindings()}
        assert variants["pymunk"] in ("movers", "walls")
        space = CompositionSpace(name="repository", universe=repository_bindings(), min_size=1, max_size=4)
        assert len(list(space.enumerate_shapes())) == 23


class TestCorePurity:
    """templates.py + catalog.py must stay experiment-free like composition.py."""

    FORBIDDEN = (
        "mesa", "pde", "pymunk", "ndlib", "network_diffusion",
        "morphogenesis", "chemomech", "field-guided", "movers",
        "experiments", "wall", "geometry", "gradient", "scalar_field",
        "agent_intentions", "rigid_body",
    )
    FORBIDDEN_OPERATIONS = (
        "geometry.sync", "field.step", "physics.force", "physics.step",
        "agents.step", "agents.apply", "movers.force", "movers.step",
        "field.source",
    )

    @pytest.mark.parametrize("module", ["templates.py", "catalog.py"])
    def test_core_is_experiment_free(self, module: str) -> None:
        source = (CORE_DIR / module).read_text(encoding="utf-8").lower()
        hits = [word for word in self.FORBIDDEN if word in source]
        assert not hits, f"core/{module} must stay experiment-free, found: {hits}"

    @pytest.mark.parametrize("module", ["templates.py", "catalog.py"])
    def test_core_knows_no_experiment_operation_names(self, module: str) -> None:
        source = (CORE_DIR / module).read_text(encoding="utf-8")
        hits = [op for op in self.FORBIDDEN_OPERATIONS if op in source]
        assert not hits, f"core/{module} must not name experiment operations, found: {hits}"