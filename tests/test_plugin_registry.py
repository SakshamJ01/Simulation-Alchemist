"""Tests for Phase 4A: Experiment Plugin System & Registry."""

from __future__ import annotations

import pytest

from experiments.catalog import build_repository_plugins
from sim_alchemist.core.plugins import (
    ExperimentPlugin,
    GenericExperimentPlugin,
    PluginMetadata,
    PluginRegistry,
    PluginValidationError,
    default_plugin_registry,
)


def test_plugin_metadata_validation() -> None:
    """Verify PluginMetadata validation rules."""
    # Valid metadata
    meta = PluginMetadata(
        name="test_plugin",
        version="1.2.3",
        description="A test simulation plugin",
        author="Tester",
        capabilities=("reaction_diffusion", "rigid_body"),
        tags=("test",),
    )
    assert meta.name == "test_plugin"
    assert meta.version == "1.2.3"
    d = meta.as_dict()
    assert d["name"] == "test_plugin"
    assert "reaction_diffusion" in d["capabilities"]

    # Invalid empty name
    with pytest.raises(ValueError, match="cannot be empty"):
        PluginMetadata(name="", version="1.0.0", description="desc")

    # Invalid semver
    with pytest.raises(ValueError, match="Invalid semantic version"):
        PluginMetadata(name="plugin", version="invalid-version", description="desc")


def test_plugin_registry_crud_operations() -> None:
    """Verify registration, listing, retrieval, and removal in PluginRegistry."""
    registry = PluginRegistry()
    assert len(registry) == 0

    plugins = build_repository_plugins()
    assert len(plugins) == 4

    for p in plugins:
        registry.register(p)

    assert len(registry) == 4
    assert "gated_movers" in registry
    assert "morphogenesis" in registry
    assert "field_guided_movers" in registry
    assert "adaptive_network" in registry

    # Retrieval
    p_d = registry.get("gated_movers")
    assert p_d is not None
    assert p_d.metadata.name == "gated_movers"
    assert isinstance(p_d, ExperimentPlugin)

    # Re-registration fails
    with pytest.raises(ValueError, match="already registered"):
        registry.register(p_d)

    # Listing is sorted
    names = [p.metadata.name for p in registry.list_plugins()]
    assert names == sorted(names)

    # Unregister
    assert registry.unregister("gated_movers") is True
    assert "gated_movers" not in registry
    assert len(registry) == 3
    assert registry.unregister("non_existent") is False


def test_plugin_validation_errors() -> None:
    """Verify PluginRegistry rejects malformed plugins."""
    registry = PluginRegistry()

    # Missing coupling template
    bad_plugin = GenericExperimentPlugin(
        metadata=PluginMetadata(name="bad_plugin", version="0.1.0", description="bad"),
        coupling_template=None,  # type: ignore
        executor=lambda w: None,  # type: ignore
    )
    with pytest.raises(PluginValidationError, match="coupling_template"):
        registry.register(bad_plugin)


def test_default_plugin_registry_singleton() -> None:
    """Verify default_plugin_registry behavior."""
    reg = default_plugin_registry()
    assert isinstance(reg, PluginRegistry)
