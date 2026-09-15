"""Repository-facing composition catalog for the four experiments (Task 3.0).

This is the experiment-owned side of the Stage 3-5 composition layer.  It
binds the four experiment coupling templates (A: morphogenesis, B:
field-guided movers, D: gated mover morphogenesis, C: adaptive network
morphogenesis) to the five-binding composition space and supplies the
adapter-construction hook the generic classification gate needs (constructor-
only; nothing is ever initialized or stepped here).

The five bindings come from the union of the experiment registries:
    * ``mesa``            -- core (agent sensing/decisions),
    * ``py-pde``          -- core (reaction-diffusion field),
    * ``pymunk/walls``    -- core (rigid-body wall physics),
    * ``pymunk/movers``   -- Experiment B + D point-mover variant,
    * ``network``         -- Experiment C network-diffusion variant.

Task 2.4 (Build Stage 1) adds ``repository_executors()``: the ``executor_ref``
mechanism points at the experiments' config-based runners (``WorldConfig ->
Trajectory`` for A, ``MoversConfig -> MoversTrajectory`` for B), which are
*not* conforming ``WorldDefinition -> ExecOutcome`` executors.  The smallest
missing abstraction is therefore a repository-owned map from the
content-addressed composition id to the experiment's conforming executor
(A and B expose their wrappers in ``chemomech/experiment.py`` and
``experiments/field_guided_movers/experiment.py``; C's ``run_network_world``
already conforms).  The generic core never sees a composition name -- it is
given the executor for the candidate it evaluates.
"""

from __future__ import annotations

from collections.abc import Sequence

from chemomech.coupling import build_morphogenesis_template
from chemomech.experiment import run_morphogenesis_world
from experiments.field_guided_movers.coupling import (
    build_field_guided_movers_registry,
    build_field_guided_movers_template,
)
from experiments.field_guided_movers.experiment import run_field_guided_movers_world
from experiments.gated_movers.coupling import (
    build_gated_movers_registry,
    build_gated_movers_template,
)
from experiments.gated_movers.experiment import (
    run_gated_movers_world,
)
from experiments.gated_movers.experiment import (
    specs_by_path as gated_specs_by_path,
)
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_registry,
    build_network_morphogenesis_template,
)
from experiments.network_morphogenesis.experiment import (
    run_network_world,
)
from experiments.network_morphogenesis.experiment import (
    specs_by_path as network_specs_by_path,
)
from sim_alchemist.core.capabilities import SimulationEngine
from sim_alchemist.core.catalog import CompositionCatalog
from sim_alchemist.core.composition import (
    CapabilitySurface,
    ComponentBinding,
    CompositionShape,
    CompositionSpace,
    capability_surfaces_from_registry,
)
from sim_alchemist.core.cross_sweep import (
    CompositionSpaceBinding,
    parameter_space_ref,
)
from sim_alchemist.core.registry import default_registry
from sim_alchemist.core.runner import Executor
from sim_alchemist.core.sweep import MutationSpace, ParameterSweep
from sim_alchemist.core.templates import (
    CouplingTemplate,
    CouplingTemplateRegistry,
    template_composition_id,
)


def _binding_key(binding: ComponentBinding) -> tuple[str, str]:
    return (binding.component, binding.variant or "")


def repository_bindings() -> tuple[ComponentBinding, ...]:
    """The five distinct bindings of the repository composition universe."""
    return tuple(sorted(repository_surfaces(), key=_binding_key))


def repository_surfaces() -> dict[ComponentBinding, CapabilitySurface]:
    """Static capability surfaces for all five bindings (constructor-only).

    Capability surfaces are keyed by binding identity (component + variant),
    so the walls and movers variants of the ``pymunk`` component id coexist
    here even though a single registry can only register one ``pymunk``
    builder.  The three registries are merged by ``dict.update``.
    """
    surfaces: dict[ComponentBinding, CapabilitySurface] = {}
    surfaces.update(capability_surfaces_from_registry(default_registry()))
    surfaces.update(
        capability_surfaces_from_registry(build_network_morphogenesis_registry())
    )
    surfaces.update(
        capability_surfaces_from_registry(build_field_guided_movers_registry())
    )
    surfaces.update(
        capability_surfaces_from_registry(build_gated_movers_registry())
    )
    return surfaces


def repository_templates() -> CouplingTemplateRegistry:
    """The four experiment coupling templates, registered deterministically."""
    registry = CouplingTemplateRegistry()
    for template in (
        build_morphogenesis_template(),
        build_field_guided_movers_template(),
        build_gated_movers_template(),
        build_network_morphogenesis_template(),
    ):
        registry.register(template)
    return registry


def build_repository_adapters(
    shape: CompositionShape,
    template: CouplingTemplate,
) -> Sequence[SimulationEngine]:
    """Construct (only) the adapters a template-matched shape needs.

    Dispatch by template + binding identity: the ``network`` component id comes
    from Experiment C, the ``pymunk/movers`` variant from Experiment B, the
    whole gated-movers composition from Experiment D (whose ``mesa`` binding is
    the experiment-owned gating adapter), and everything else from the core
    default registry.  Constructors run with the template's component configs;
    no adapter is initialized or stepped.
    """

    def _registry_for(binding: ComponentBinding) -> object:
        if template.name == "gated_movers":
            return build_gated_movers_registry()
        if binding.component == "network":
            return build_network_morphogenesis_registry()
        if binding.variant == "movers":
            return build_field_guided_movers_registry()
        return default_registry()

    configs = dict(template.component_configs)
    adapters: list[SimulationEngine] = []
    for binding in shape:
        registry = _registry_for(binding)
        adapters.append(
            registry.build(binding.component, dict(configs.get(binding.component, {})))
        )
    return adapters


def build_repository_catalog(*, generate_worlds: bool = False) -> CompositionCatalog:
    """The full 23-shape repository catalog (k = 1..4 over five bindings).

    ``generate_worlds=True`` materializes the ``WorldDefinition`` of every
    ``EXECUTABLE`` candidate (exactly four).
    """
    space = CompositionSpace(
        name="repository",
        universe=repository_bindings(),
        min_size=1,
        max_size=4,
    )
    return CompositionCatalog(
        space,
        repository_surfaces(),
        repository_templates(),
        build_adapters=build_repository_adapters,
        generate_worlds=generate_worlds,
    )


def repository_executors() -> dict[str, Executor]:
    """Conforming executors keyed by the executable composition ids.

    Keys are ``template_composition_id`` of the four experiment templates
    (content-addressed, immutable).  A and B wrappers are supplied here
    because their staged ``executor_ref`` points at config-based runners; C's
    ``run_network_world`` and D's ``run_gated_movers_world`` already conform
    to the ``Executor`` contract.
    """
    return {
        template_composition_id(build_morphogenesis_template()): run_morphogenesis_world,
        template_composition_id(build_field_guided_movers_template()): run_field_guided_movers_world,
        template_composition_id(build_gated_movers_template()): run_gated_movers_world,
        template_composition_id(build_network_morphogenesis_template()): run_network_world,
    }


def _network_parameter_space() -> MutationSpace:
    """The legitimate parameter space of the network composition (C).

    Built from the experiment's declared ``PARAMETER_SPECS`` (paths + bounds)
    so no scientific dimension is invented and no existing parameter value is
    changed.  The three mutable dimensions are the ones the coupling layer
    already carries experimental meaning for:
    ``components.network.config.loss`` (0..1), ``config.force_fmax`` (0..10)
    and ``config.source_amplitude`` (0..1).  Value lists are modest
    exploration points strictly inside the declared valid bounds.
    """
    specs = network_specs_by_path()
    dims = (
        ParameterSweep("components.network.config.loss", (0.2, 0.5, 0.8)),
        ParameterSweep("config.force_fmax", (2.0, 5.0, 8.0)),
        ParameterSweep("config.source_amplitude", (0.2, 0.5, 0.8)),
    )
    for dim in dims:
        spec = specs[dim.path]
        for value in dim.values:
            if not (spec.minimum <= value <= spec.maximum):
                raise ValueError(
                    f"value {value} for {dim.path} outside declared bounds "
                    f"[{spec.minimum}, {spec.maximum}]"
                )
    return MutationSpace(dims)


def _gated_movers_parameter_space() -> MutationSpace:
    """The legitimate gate-policy parameter space of Experiment D.

    Stage 3 keeps this deliberately small: threshold and cooldown are the
    two fields directly consumed by the gate hysteresis rule.  The authored
    ``source_amplitude`` spec is left out here because it changes deposition
    strength, not the gate policy itself.
    """
    specs = gated_specs_by_path()
    dims = (
        ParameterSweep("config.gate_threshold", (0.25, 0.75)),
        ParameterSweep("config.gate_cooldown", (0, 8)),
    )
    for dim in dims:
        spec = specs[dim.path]
        for value in dim.values:
            if not (spec.minimum <= value <= spec.maximum):
                raise ValueError(
                    f"value {value} for {dim.path} outside declared bounds "
                    f"[{spec.minimum}, {spec.maximum}]"
                )
    return MutationSpace(dims)


def repository_parameter_spaces() -> dict[str, CompositionSpaceBinding]:
    """Experiment-owned parameter spaces keyed by executable composition id.

    Mirrors ``repository_executors()``: the map is keyed by the
    content-addressed ``template_composition_id`` of each experiment template.
    A composition owns a real ``MutationSpace`` only where the experiment
    declares a legitimate parameter space; otherwise it binds ``space=None``
    (and ``ref=None``) meaning "no registered parameter sweep space" -- never
    an error and never an empty space.  The experiment keeps the generic core
    free of any science: the core sees only opaque refs and the generic
    ``MutationSpace``.

    Task 3.0 Build Stage 3 promotes Experiment D from its Stage 1/2
    baseline-only binding to a real, D-owned gate-policy ``MutationSpace``.
    A/B remain baseline-only.  C keeps its original 27-variant network space.
    """
    a_template = build_morphogenesis_template()
    b_template = build_field_guided_movers_template()
    c_template = build_network_morphogenesis_template()
    d_template = build_gated_movers_template()
    c_space = _network_parameter_space()
    d_space = _gated_movers_parameter_space()
    bindings = (
        CompositionSpaceBinding(
            composition_id=template_composition_id(a_template),
            shape_id=a_template.shape.shape_id,
        ),
        CompositionSpaceBinding(
            composition_id=template_composition_id(b_template),
            shape_id=b_template.shape.shape_id,
        ),
        CompositionSpaceBinding(
            composition_id=template_composition_id(c_template),
            shape_id=c_template.shape.shape_id,
            ref=parameter_space_ref(c_space),
            space=c_space,
        ),
        CompositionSpaceBinding(
            composition_id=template_composition_id(d_template),
            shape_id=d_template.shape.shape_id,
            ref=parameter_space_ref(d_space),
            space=d_space,
        ),
    )
    return {b.composition_id: b for b in bindings}
