"""Composition shape/space + static capability filter tests (Task 2.3 Stage 1+2).

Covers the CompositionShape identity model (ComponentBinding /
CompositionShape), deterministic bounded enumeration (CompositionSpace), and
the static capability filter (CAPABILITY_VALID / CAPABILITY_INVALID).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from experiments.field_guided_movers.coupling import build_field_guided_movers_registry
from experiments.field_guided_movers.model import MoversAdapter
from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_registry,
)
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core import (
    CAPABILITY_INVALID,
    CAPABILITY_VALID,
    CapabilitySurface,
    ComponentBinding,
    CompositionShape,
    CompositionSpace,
    bindings_from_registry,
    capability_surfaces_from_registry,
    classify_shape,
    classify_shapes,
    default_registry,
)

MESA = ComponentBinding("mesa")
PDE = ComponentBinding("py-pde")
WALLS = ComponentBinding("pymunk", "walls")
MOVERS = ComponentBinding("pymunk", "movers")
NETWORK = ComponentBinding("network")

# Canonical (component, variant-or-"") order of the five registry-visible
# bindings: mesa < network < py-pde < pymunk/movers < pymunk/walls.
EXPECTED_UNIVERSE = (MESA, NETWORK, PDE, MOVERS, WALLS)


def _full_universe() -> tuple[ComponentBinding, ...]:
    return EXPECTED_UNIVERSE


def _full_surfaces() -> dict[ComponentBinding, CapabilitySurface]:
    """Merged static capability surfaces of every registry the repo ships."""
    surfaces: dict[ComponentBinding, CapabilitySurface] = {}
    surfaces.update(capability_surfaces_from_registry(default_registry()))
    surfaces.update(capability_surfaces_from_registry(build_network_morphogenesis_registry()))
    surfaces.update(capability_surfaces_from_registry(build_field_guided_movers_registry()))
    return surfaces


# ----------------------------------------------------------------------
# ComponentBinding: value identity, variant normalization, serialization
# ----------------------------------------------------------------------
class TestComponentBinding:
    def test_value_equality_and_hash(self) -> None:
        assert ComponentBinding("pymunk", "walls") == ComponentBinding("pymunk", "walls")
        assert hash(ComponentBinding("pymunk", "walls")) == hash(ComponentBinding("pymunk", "walls"))
        assert ComponentBinding("pymunk", "walls") != ComponentBinding("pymunk", "movers")
        assert ComponentBinding("mesa") != ComponentBinding("py-pde")

    def test_variant_normalization(self) -> None:
        assert ComponentBinding("py-pde").variant is None
        assert ComponentBinding("py-pde", "").variant is None
        assert ComponentBinding("py-pde", "") == ComponentBinding("py-pde", None)
        assert ComponentBinding("py-pde", "  ").variant is None
        assert ComponentBinding("pymunk", "walls").variant == "walls"

    def test_invalid_inputs(self) -> None:
        with pytest.raises(ValueError):
            ComponentBinding("")
        with pytest.raises(ValueError):
            ComponentBinding("   ")
        with pytest.raises(TypeError):
            ComponentBinding("py-pde", cast(Any, 3))

    def test_canonical_serialization(self) -> None:
        assert ComponentBinding("py-pde").as_dict() == {"component": "py-pde", "variant": None}
        assert ComponentBinding("pymunk", "walls").as_dict() == {
            "component": "pymunk",
            "variant": "walls",
        }
        assert ComponentBinding("pymunk", "walls").as_dict() != ComponentBinding(
            "pymunk", "movers"
        ).as_dict()

    def test_serialization_round_trip(self) -> None:
        for binding in (ComponentBinding("py-pde"), ComponentBinding("pymunk", "walls")):
            assert ComponentBinding.from_dict(binding.as_dict()) == binding

    def test_walls_and_movers_are_distinct_identities(self) -> None:
        assert WALLS != MOVERS
        assert (WALLS.component, WALLS.variant) == ("pymunk", "walls")
        assert (MOVERS.component, MOVERS.variant) == ("pymunk", "movers")


# ----------------------------------------------------------------------
# CompositionShape: canonical unordered set semantics + content-addressed id
# ----------------------------------------------------------------------
class TestCompositionShape:
    def test_order_independent_equality(self) -> None:
        assert CompositionShape((WALLS, PDE)) == CompositionShape((PDE, WALLS))

    def test_canonical_ordering(self) -> None:
        shape = CompositionShape((WALLS, PDE, MESA))
        assert shape.bindings == (MESA, PDE, WALLS)
        assert shape.components() == ("mesa", "py-pde", "pymunk")

    def test_deterministic_shape_id(self) -> None:
        a = CompositionShape((WALLS, PDE, MESA))
        b = CompositionShape((MESA, PDE, WALLS))
        assert a == b
        assert a.shape_id == b.shape_id
        assert len(a.shape_id) == 24

    def test_variant_changes_shape_id(self) -> None:
        assert CompositionShape((PDE, WALLS)).shape_id != CompositionShape((PDE, MOVERS)).shape_id

    def test_input_order_independent_shape_id(self) -> None:
        assert CompositionShape((WALLS, PDE)).shape_id == CompositionShape((PDE, WALLS)).shape_id

    def test_serialization_round_trip(self) -> None:
        shape = CompositionShape((WALLS, PDE))
        restored = CompositionShape.from_dict(shape.as_dict())
        assert restored == shape
        assert restored.shape_id == shape.shape_id

    def test_rejects_duplicate_binding(self) -> None:
        with pytest.raises(ValueError):
            CompositionShape((PDE, PDE))

    def test_rejects_two_variants_of_same_component(self) -> None:
        with pytest.raises(ValueError, match="variant exclusivity"):
            CompositionShape((WALLS, MOVERS))

    def test_rejects_empty_shape(self) -> None:
        with pytest.raises(ValueError):
            CompositionShape(())


# ----------------------------------------------------------------------
# CompositionSpace: bounded, deterministic, variant-exclusive enumeration
# ----------------------------------------------------------------------
class TestCompositionSpace:
    def test_default_bounds(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe())
        assert space.min_size == 2
        assert space.max_size == 4
        shapes = space.enumerate_shapes()
        assert all(2 <= len(s) <= 4 for s in shapes)
        assert len(shapes) == 18  # 9 + 7 + 2

    def test_custom_bounds_honored(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        shapes = space.enumerate_shapes()
        assert [len(s) for s in shapes] == [1] * 5 + [2] * 9 + [3] * 7 + [4] * 2

    def test_invalid_bounds(self) -> None:
        with pytest.raises(ValueError):
            CompositionSpace(name="full", universe=_full_universe(), min_size=-1)
        with pytest.raises(ValueError):
            CompositionSpace(name="full", universe=_full_universe(), min_size=3, max_size=2)
        with pytest.raises(ValueError):
            CompositionSpace(name="full", universe=_full_universe(), max_size=6)
        with pytest.raises(ValueError):
            CompositionSpace(name="full", universe=())
        with pytest.raises(ValueError):
            CompositionSpace(name="full", universe=(PDE, PDE))

    def test_deterministic_enumeration(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        assert space.enumerate_shapes() == space.enumerate_shapes()

    def test_no_duplicate_shapes(self) -> None:
        shapes = CompositionSpace(
            name="full", universe=_full_universe(), min_size=1, max_size=4
        ).enumerate_shapes()
        ids = [s.shape_id for s in shapes]
        assert len(ids) == len(set(ids))

    def test_exact_counts(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        shapes = space.enumerate_shapes()
        counts = {k: sum(1 for s in shapes if len(s) == k) for k in range(1, 5)}
        assert counts == {1: 5, 2: 9, 3: 7, 4: 2}
        assert len(shapes) == 23

    def test_variant_exclusivity(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        shapes = space.enumerate_shapes()
        for shape in shapes:
            ids = shape.components()
            assert len(ids) == len(set(ids))
        both_variants = [s for s in shapes if WALLS in s.bindings and MOVERS in s.bindings]
        assert both_variants == []

    def test_repeated_enumeration_identical(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        first = space.enumerate_shapes()
        second = space.enumerate_shapes()
        assert first == second
        assert [s.shape_id for s in first] == [s.shape_id for s in second]

    def test_size_first_then_canonical_order(self) -> None:
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=2, max_size=2)
        shapes = space.enumerate_shapes()
        assert len(shapes) == 9
        assert shapes[0] == CompositionShape((MESA, NETWORK))
        assert shapes[-1] == CompositionShape((PDE, WALLS))


# ----------------------------------------------------------------------
# Registry-derived bindings: the five-binding universe comes from the
# real registries (default = 3; network registry adds one; movers registry
# swaps the walls binding for the movers binding).
# ----------------------------------------------------------------------
class TestRegistryDerivedBindings:
    def test_default_registry_three_bindings(self) -> None:
        assert bindings_from_registry(default_registry()) == (MESA, PDE, WALLS)

    def test_network_registry_adds_network_binding(self) -> None:
        assert bindings_from_registry(build_network_morphogenesis_registry()) == (
            MESA,
            NETWORK,
            PDE,
            WALLS,
        )

    def test_movers_registry_swaps_walls_for_movers(self) -> None:
        bindings = bindings_from_registry(build_field_guided_movers_registry())
        assert MOVERS in bindings
        assert WALLS not in bindings
        assert bindings == (MESA, PDE, MOVERS)

    def test_full_universe_matches_registries(self) -> None:
        assert set(_full_surfaces()) == set(_full_universe())
        assert len(_full_surfaces()) == 5


# ----------------------------------------------------------------------
# Static capability filter: CAPABILITY_VALID / CAPABILITY_INVALID
# ----------------------------------------------------------------------
class TestCapabilityFilter:
    def test_known_a_shape_capability_valid(self) -> None:
        surfaces = _full_surfaces()
        shape = CompositionShape((PDE, WALLS, MESA))
        result = classify_shape(shape, surfaces)
        assert result.status == CAPABILITY_VALID
        assert result.missing_capabilities == ()
        with_reqs = classify_shape(
            shape,
            surfaces,
            required=("agent_population", "reaction_diffusion", "rigid_body", "field_gradient"),
        )
        assert with_reqs.status == CAPABILITY_VALID

    def test_known_b_shape_capability_valid(self) -> None:
        surfaces = _full_surfaces()
        shape = CompositionShape((PDE, MOVERS))
        assert classify_shape(shape, surfaces).status == CAPABILITY_VALID
        with_reqs = classify_shape(
            shape, surfaces, required=("reaction_diffusion", "rigid_body", "field_gradient")
        )
        assert with_reqs.status == CAPABILITY_VALID

    def test_known_c_shape_capability_valid(self) -> None:
        surfaces = _full_surfaces()
        shape = CompositionShape((PDE, WALLS, NETWORK))
        assert classify_shape(shape, surfaces).status == CAPABILITY_VALID
        with_reqs = classify_shape(
            shape,
            surfaces,
            required=("reaction_diffusion", "rigid_body", "network_diffusion", "field_gradient"),
        )
        assert with_reqs.status == CAPABILITY_VALID

    def test_pde_plus_mesa_is_capability_invalid(self) -> None:
        shape = CompositionShape((PDE, MESA))
        result = classify_shape(shape, _full_surfaces())
        assert result.status == CAPABILITY_INVALID
        assert result.missing_capabilities == ("geometry_provider",)

    def test_single_binding_shapes_missing_reported(self) -> None:
        surfaces = _full_surfaces()
        expected = {
            MESA: ("scalar_field",),
            PDE: ("geometry_provider",),
            WALLS: ("agent_intentions", "field_gradient"),
            MOVERS: ("field_gradient", "field_sources", "scalar_field"),
            NETWORK: ("reaction_diffusion", "rigid_body"),
        }
        for binding, missing in expected.items():
            result = classify_shape(CompositionShape((binding,)), surfaces)
            assert result.status == CAPABILITY_INVALID
            assert result.missing_capabilities == missing

    def test_extra_required_capability_reported(self) -> None:
        result = classify_shape(
            CompositionShape((PDE, WALLS, MESA)),
            _full_surfaces(),
            required=("agent_population", "reaction_diffusion", "rigid_body", "field_gradient", "nonexistent_cap"),
        )
        assert result.status == CAPABILITY_INVALID
        assert result.missing_capabilities == ("nonexistent_cap",)

    def test_classification_deterministic(self) -> None:
        surfaces = _full_surfaces()
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        first = classify_shapes(space.enumerate_shapes(), surfaces)
        second = classify_shapes(space.enumerate_shapes(), surfaces)
        assert [(c.status, c.missing_capabilities) for c in first] == [
            (c.status, c.missing_capabilities) for c in second
        ]
        assert len(first) == 23

    def test_capability_valid_does_not_imply_executable(self) -> None:
        surfaces = _full_surfaces()
        for shape in (
            CompositionShape((PDE, MOVERS, MESA)),
            CompositionShape((PDE, MOVERS, NETWORK)),
            CompositionShape((MESA, PDE, WALLS, NETWORK)),
        ):
            result = classify_shape(shape, surfaces)
            assert result.status == CAPABILITY_VALID
            assert result.missing_capabilities == ()

    def test_classify_unknown_binding_fails_loudly(self) -> None:
        shape = CompositionShape((ComponentBinding("unknown_id"),))
        with pytest.raises(ValueError, match="no capability surface"):
            classify_shape(shape, _full_surfaces())


# ----------------------------------------------------------------------
# Capability analysis must never initialize or step an engine, and must
# never construct new adapters during classification.
# ----------------------------------------------------------------------
class TestStaticOnly:
    def test_no_initialize_or_step_during_capability_work(self, monkeypatch: Any) -> None:
        calls = {"initialize": 0, "step": 0}

        def _initialize(self, config: dict) -> None:
            calls["initialize"] += 1

        def _step(self, dt: float) -> None:
            calls["step"] += 1

        for adapter_cls in (
            MesaAdapter,
            PyPDEAdapter,
            PymunkAdapter,
            MoversAdapter,
            AdaptiveNetworkAdapter,
        ):
            monkeypatch.setattr(adapter_cls, "initialize", _initialize)
            monkeypatch.setattr(adapter_cls, "step", _step)
        surfaces = _full_surfaces()
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        results = classify_shapes(space.enumerate_shapes(), surfaces)
        assert calls == {"initialize": 0, "step": 0}
        assert {r.status for r in results} <= {CAPABILITY_VALID, CAPABILITY_INVALID}

    def test_classify_uses_prebuilt_surfaces_only(self, monkeypatch: Any) -> None:
        from sim_alchemist.core.registry import AdapterFactory

        original = AdapterFactory.build
        builds = [0]

        def counting_build(self, config: dict) -> object:
            builds[0] += 1
            return original(self, config)

        monkeypatch.setattr(AdapterFactory, "build", counting_build)
        surfaces = _full_surfaces()
        builds_before = builds[0]
        assert builds_before > 0
        assert len(surfaces) == 5
        space = CompositionSpace(name="full", universe=_full_universe(), min_size=1, max_size=4)
        classify_shapes(space.enumerate_shapes(), surfaces)
        assert builds[0] == builds_before


# ----------------------------------------------------------------------
# Core-purity architectural test: composition.py must not leak experiment
# identifiers or operation names into the generic core.
# ----------------------------------------------------------------------
def test_composition_core_is_experiment_free() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "sim_alchemist"
        / "core"
        / "composition.py"
    )
    source = path.read_text().lower()
    forbidden = (
        "mesa",
        "pde",
        "pymunk",
        "ndlib",
        "network_diffusion",
        "morphogenesis",
        "chemomech",
        "field-guided",
        "movers",
        "experiments",
        "wall",
        "geometry",
        "gradient",
        "scalar_field",
        "agent_intentions",
        "rigid_body",
    )
    hits = [word for word in forbidden if word in source]
    assert not hits, f"core/composition.py must stay experiment-free, found: {hits}"