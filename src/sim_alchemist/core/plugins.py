"""General Experiment Plugin System & Registry (Phase 4A).

Defines the ExperimentPlugin protocol and PluginRegistry enabling modular,
decoupled authoring, discovery, and execution of multi-physics simulation
experiments without hardcoding experiment branches in core.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sim_alchemist.core.behavior import InterestingnessProfile
    from sim_alchemist.core.mutation import ParameterSpec
    from sim_alchemist.core.runner import ExecOutcome
    from sim_alchemist.core.sweep import MutationSpace
    from sim_alchemist.core.templates import CouplingTemplate
    from sim_alchemist.core.world import WorldDefinition


@dataclass(frozen=True)
class PluginMetadata:
    """Standardized metadata manifest for an ExperimentPlugin."""

    name: str
    version: str
    description: str
    author: str = "Simulation Alchemist"
    capabilities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    min_core_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Plugin metadata 'name' cannot be empty.")
        if not re.match(r"^\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?$", self.version):
            raise ValueError(f"Invalid semantic version string: '{self.version}'")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "capabilities": list(self.capabilities),
            "tags": list(self.tags),
            "min_core_version": self.min_core_version,
        }


@runtime_checkable
class ExperimentPlugin(Protocol):
    """Formal protocol required for all modular simulation experiment plugins."""

    @property
    def metadata(self) -> PluginMetadata:
        """Plugin manifest metadata."""
        ...

    @property
    def coupling_template(self) -> CouplingTemplate:
        """The declarative CouplingTemplate specifying world construction and schedule."""
        ...

    @property
    def executor(self) -> Callable[[WorldDefinition], ExecOutcome]:
        """The conforming execution callable for simulating worlds of this experiment."""
        ...

    @property
    def parameter_specs(self) -> Sequence[ParameterSpec]:
        """Sequence of declared ParameterSpecs for parameter mutation and sweeps."""
        ...

    @property
    def default_mutation_space(self) -> MutationSpace | None:
        """Default parameter sweep space if registered."""
        ...

    @property
    def default_interestingness_profile(self) -> InterestingnessProfile | None:
        """Default feature weighting profile for behavioral interestingness ranking."""
        ...


@dataclass
class GenericExperimentPlugin:
    """Concrete, reusable implementation of ExperimentPlugin."""

    metadata: PluginMetadata
    coupling_template: CouplingTemplate
    executor: Callable[[WorldDefinition], ExecOutcome]
    parameter_specs: tuple[ParameterSpec, ...] = ()
    default_mutation_space: MutationSpace | None = None
    default_interestingness_profile: InterestingnessProfile | None = None


class PluginValidationError(ValueError):
    """Raised when a plugin fails structural or contract validation."""


class PluginRegistry:
    """Thread-safe, validate-on-registration registry for Simulation Alchemist plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, ExperimentPlugin] = {}

    def register(self, plugin: ExperimentPlugin) -> None:
        """Validate and register an ExperimentPlugin."""
        issues = self.validate_plugin(plugin)
        if issues:
            raise PluginValidationError(f"Plugin '{plugin.metadata.name}' failed validation: {'; '.join(issues)}")

        name = plugin.metadata.name
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' is already registered.")
        self._plugins[name] = plugin

    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name. Returns True if removed."""
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False

    def get(self, name: str) -> ExperimentPlugin | None:
        """Retrieve a registered plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[ExperimentPlugin]:
        """Return all registered plugins sorted by name."""
        return sorted(self._plugins.values(), key=lambda p: p.metadata.name)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)

    @staticmethod
    def validate_plugin(plugin: Any) -> list[str]:
        """Check compliance with ExperimentPlugin protocol and return any issues."""
        issues: list[str] = []
        if not hasattr(plugin, "metadata") or not isinstance(plugin.metadata, PluginMetadata):
            issues.append("Plugin must have a valid 'metadata' of type PluginMetadata")
            return issues

        if not hasattr(plugin, "coupling_template") or plugin.coupling_template is None:
            issues.append("Plugin must provide a non-None 'coupling_template'")

        if not hasattr(plugin, "executor") or not callable(plugin.executor):
            issues.append("Plugin must provide a callable 'executor'")

        if not hasattr(plugin, "parameter_specs"):
            issues.append("Plugin must provide 'parameter_specs' attribute")

        return issues


#: Global default plugin registry instance
_GLOBAL_PLUGIN_REGISTRY = PluginRegistry()


def default_plugin_registry() -> PluginRegistry:
    """Return the shared global PluginRegistry."""
    return _GLOBAL_PLUGIN_REGISTRY
