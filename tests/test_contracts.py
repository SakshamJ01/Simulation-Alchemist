"""Task 2.2 validation: coupling contracts + pre-execution validation.

Core layer checks A-M::

    A  a validly declared contract resolves against its adapter set
    B  a contract naming an uncomposed producer is rejected
    C  a contract naming an uncomposed consumer is rejected
    D  a contract through an unprovided producer capability is rejected
    E  a contract through an unprovided consumer capability is rejected
    F  a payload key missing from the producer's state vocabulary is rejected
    G  variant mismatches (declared vs composed) are rejected
    H  an unsupported timing is rejected
    I  an unsupported mechanism is rejected
    J  multiple failing contracts are reported together, deterministically
    K  repeated validation of a failing set produces an identical error
    L  the error message names contract, producer, consumer, variant, reason,
       and remediation
    M  the layer never infers couplings: an empty contract set always resolves

Experiment checks::

    N  the A/B/C declared contract sets resolve against each world's adapters
    O  composing WITH the declared contracts yields bitwise the same science
       as composing without them
    P  the Task 2.2 gap: a capability-valid but coupling-invalid composition
       (py-pde + movers variant + network) is rejected before any step
    Q  plain ``compose`` with contracts accepts the validated A/B worlds
    R  facades and the variant-runner executor still run with contracts wired
"""

from __future__ import annotations

import hashlib
from typing import cast

import numpy as np
import pytest

from chemomech.coupling import (
    MORPHOGENESIS_CONTRACTS,
    MorphogenesisState,
    build_morphogenesis_operations,
    build_morphogenesis_world,
)
from chemomech.simulation import Trajectory, WorldConfig
from chemomech.validate import build_agents
from experiments.field_guided_movers.coupling import (
    FIELD_GUIDED_MOVERS_CONTRACTS,
    MoversState,
    build_field_guided_movers_operations,
    build_field_guided_movers_registry,
    build_field_guided_movers_world,
)
from experiments.field_guided_movers.model import (
    FieldGuidedMoversEngine,
    MoversAdapter,
    MoversConfig,
    MoversTrajectory,
)
from experiments.network_morphogenesis.adapter import AdaptiveNetworkAdapter
from experiments.network_morphogenesis.coupling import (
    NETWORK_MORPHOGENESIS_CONTRACTS,
    NETWORK_MORPHOGENESIS_SCHEDULE,
    NetworkMorphogenesisState,
    build_network_morphogenesis_operations,
    build_network_morphogenesis_registry,
    build_network_morphogenesis_world,
)
from experiments.network_morphogenesis.experiment import run_network_world
from experiments.network_morphogenesis.model import (
    NetworkMorphogenesisConfig,
    NetworkMorphogenesisEngine,
    NetworkMorphogenesisTrajectory,
    run_network_morphogenesis,
)
from sim_alchemist.adapters.mesa import MesaAdapter
from sim_alchemist.adapters.pde import PyPDEAdapter
from sim_alchemist.adapters.pymunk import PymunkAdapter
from sim_alchemist.core.capabilities import SimulationEngine
from sim_alchemist.core.composer import build_components, compose, resolve_capabilities
from sim_alchemist.core.contracts import (
    CouplingContract,
    PayloadItem,
    UnresolvedContractError,
    adapter_by_id,
    contracts_key,
    resolve_contracts,
)

GRADIENT_WALLS = CouplingContract(
    name="gradient-force",
    producer="py-pde",
    producer_capability="field_gradient",
    consumer="pymunk",
    consumer_capability="force_integration",
    payload=(("gradient", "vec2"),),
    transform="gradient-force",
    variant="walls",
)


def sha(arr) -> str:
    return hashlib.sha256(np.asarray(arr).tobytes()).hexdigest()


def experiment_a_adapters() -> list[SimulationEngine]:
    return [PyPDEAdapter(n=8), PymunkAdapter(n=8), MesaAdapter()]


def experiment_b_adapters() -> list[SimulationEngine]:
    return [PyPDEAdapter(n=8), MoversAdapter(MoversConfig(n=8))]


def experiment_c_adapters() -> list[SimulationEngine]:
    return [
        PyPDEAdapter(n=8),
        PymunkAdapter(n=8),
        AdaptiveNetworkAdapter(grid_rows=4, grid_cols=6),
    ]


def compose_a(cfg: WorldConfig, contracts) -> Trajectory:
    world = build_morphogenesis_world(cfg)
    trajectory = Trajectory(config=cfg)
    state = MorphogenesisState()

    def operations(adapters):
        pde, pymunk, mesa = adapters
        return build_morphogenesis_operations(pde, pymunk, mesa, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, pymunk, mesa = adapters
        mesa.set_field(pde.get_field())
        mesa.set_wallspace(pymunk._wallspace)
        mesa.create_model()

    compose(
        world,
        _default_registry(),
        operations,
        on_initialize=on_initialize,
        contracts=contracts,
    ).run()
    return trajectory


def _default_registry():
    from sim_alchemist.core.registry import default_registry

    return default_registry()


def compose_b(cfg: MoversConfig, contracts) -> MoversTrajectory:
    world = build_field_guided_movers_world(cfg)
    trajectory = MoversTrajectory(config=cfg)
    state = MoversState()

    def operations(adapters):
        pde, movers = adapters
        return build_field_guided_movers_operations(pde, movers, cfg, trajectory, state)

    def on_initialize(adapters):
        pde, _movers = adapters
        field = pde.get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    compose(
        world,
        build_field_guided_movers_registry(),
        operations,
        on_initialize=on_initialize,
        contracts=contracts,
    ).run()
    return trajectory


def compose_c(cfg: NetworkMorphogenesisConfig, contracts) -> NetworkMorphogenesisTrajectory:
    world = build_network_morphogenesis_world(n=cfg.n, n_steps=cfg.n_steps)
    trajectory = NetworkMorphogenesisTrajectory(config=cfg)
    state = NetworkMorphogenesisState()

    def operations(adapters):
        pde, pymunk, network = adapters
        return build_network_morphogenesis_operations(
            pde, pymunk, network, world.config, trajectory, state
        )

    def on_initialize(adapters):
        pde, _pymunk, _network = adapters
        field = pde.get_field()
        if field is not None and trajectory.start_u.size == 0:
            trajectory.start_u = field.u.copy()

    compose(
        world,
        build_network_morphogenesis_registry(),
        operations,
        on_initialize=on_initialize,
        contracts=contracts,
    ).run()
    return trajectory


# ----------------------------------------------------------------------
# A. A validly declared contract resolves against its adapter set
# ----------------------------------------------------------------------
def test_a_valid_contract_resolves() -> None:
    adapters = experiment_a_adapters()
    resolve_contracts(adapters, MORPHOGENESIS_CONTRACTS)
    assert adapter_by_id(adapters, "py-pde") is adapters[0]
    assert adapter_by_id(adapters, "pymunk") is adapters[1]
    assert adapter_by_id(adapters, "mesa") is adapters[2]


def test_a_payload_normalization_and_key() -> None:
    contract = CouplingContract(
        name="blocked-mask",
        producer="pymunk",
        producer_capability="geometry_provider",
        consumer="py-pde",
        consumer_capability="field_masking",
        payload=[("blocked", "bool_2d")],
        transform="blocked-mask",
        variant="walls",
    )
    assert contract.payload == (PayloadItem("blocked", "bool_2d"),)
    rebuilt = CouplingContract.from_dict(contract.as_dict())
    assert rebuilt == contract
    assert contracts_key([contract]) == contracts_key([rebuilt])


# ----------------------------------------------------------------------
# B/C. Uncomposed endpoints are rejected
# ----------------------------------------------------------------------
def test_b_missing_producer_rejected() -> None:
    contract = CouplingContract(
        name="ghost-edge",
        producer="ghost.field",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="ghost-edge",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError, match="ghost.field"):
        resolve_contracts(experiment_a_adapters(), [contract])


def test_c_missing_consumer_rejected() -> None:
    contract = CouplingContract(
        name="ghost-edge",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="ghost.body",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="ghost-edge",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError, match="ghost.body"):
        resolve_contracts(experiment_a_adapters(), [contract])


# ----------------------------------------------------------------------
# D/E. Unprovided capabilities are rejected
# ----------------------------------------------------------------------
def test_d_missing_producer_capability_rejected() -> None:
    contract = CouplingContract(
        name="magnetise",
        producer="py-pde",
        producer_capability="nanobot_forge",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="magnetise",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError, match="nanobot_forge"):
        resolve_contracts(experiment_a_adapters(), [contract])


def test_e_missing_consumer_capability_rejected() -> None:
    contract = CouplingContract(
        name="entangle",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="quantum_entangler",
        payload=(("gradient", "vec2"),),
        transform="entangle",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError, match="quantum_entangler"):
        resolve_contracts(experiment_a_adapters(), [contract])


# ----------------------------------------------------------------------
# F. Payload vocabulary + shape validation
# ----------------------------------------------------------------------
def test_f_missing_payload_key_rejected() -> None:
    contract = CouplingContract(
        name="field-sensing-ish",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("charge", "scalar"), ("u", "array_1d")),
        transform="field-sensing-ish",
    )
    with pytest.raises(UnresolvedContractError, match="charge"):
        resolve_contracts(experiment_a_adapters(), [contract])


def test_f_unsupported_payload_shape_rejected() -> None:
    contract = CouplingContract(
        name="spooky",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("u", "hyper_cube"),),
        transform="spooky",
    )
    with pytest.raises(UnresolvedContractError, match="hyper_cube"):
        resolve_contracts(experiment_a_adapters(), [contract])


def test_f_duplicate_payload_key_rejected() -> None:
    contract = CouplingContract(
        name="dupe",
        producer="py-pde",
        producer_capability="scalar_field",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("u", "array_1d"), ("u", "array_1d")),
        transform="dupe",
    )
    with pytest.raises(UnresolvedContractError, match="more than once"):
        resolve_contracts(experiment_a_adapters(), [contract])


# ----------------------------------------------------------------------
# G. Variant binding rules
# ----------------------------------------------------------------------
def test_g_variant_mismatch_rejected() -> None:
    # Wall-targeting contract vs the movers-variant pymunk adapter.
    with pytest.raises(UnresolvedContractError, match="walls"):
        resolve_contracts(experiment_b_adapters(), [GRADIENT_WALLS])


def test_g_unpinned_variant_endpoint_rejected() -> None:
    unpinned = CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
    )
    with pytest.raises(UnresolvedContractError, match="variant"):
        resolve_contracts(experiment_b_adapters(), [unpinned])


def test_g_variant_pinned_but_uncomposable_rejected() -> None:
    contract = CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="mesa",
        consumer_capability="field_sensing",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError, match="variant"):
        resolve_contracts(experiment_a_adapters(), [contract])


# ----------------------------------------------------------------------
# H/I. Timing + mechanism lexicon
# ----------------------------------------------------------------------
def test_h_unsupported_timing_rejected() -> None:
    contract = CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
        variant="walls",
        timing="before-macro-step",
    )
    with pytest.raises(UnresolvedContractError, match="before-macro-step"):
        resolve_contracts(experiment_a_adapters(), [contract])


def test_i_unsupported_mechanism_rejected() -> None:
    contract = CouplingContract(
        name="gradient-force",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="pymunk",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="gradient-force",
        variant="walls",
        mechanism="event-bus",
    )
    with pytest.raises(UnresolvedContractError, match="event-bus"):
        resolve_contracts(experiment_a_adapters(), [contract])


# ----------------------------------------------------------------------
# J. Multiple failing contracts reported together, deterministically
# ----------------------------------------------------------------------
def test_j_multiple_issues_reported_together() -> None:
    bad_consumer = CouplingContract(
        name="ghost-edge",
        producer="py-pde",
        producer_capability="field_gradient",
        consumer="ghost.body",
        consumer_capability="force_integration",
        payload=(("gradient", "vec2"),),
        transform="ghost-edge",
        variant="walls",
    )
    with pytest.raises(UnresolvedContractError) as exc:
        resolve_contracts(experiment_b_adapters(), [GRADIENT_WALLS, bad_consumer])
    issues = exc.value.issues
    assert len(issues) == 2
    assert sorted(i.contract for i in issues) == ["ghost-edge", "gradient-force"]


# ----------------------------------------------------------------------
# K. Deterministic repeated validation
# ----------------------------------------------------------------------
def test_k_deterministic_repeated_validation() -> None:
    def run_once():
        try:
            resolve_contracts(experiment_b_adapters(), [GRADIENT_WALLS])
        except UnresolvedContractError as exc:
            return exc
        return None

    first = run_once()
    second = run_once()
    assert first is not None and second is not None
    assert str(first) == str(second)
    assert first.issues == second.issues


# ----------------------------------------------------------------------
# L. The error message is actionable
# ----------------------------------------------------------------------
def test_l_error_message_is_actionable() -> None:
    with pytest.raises(UnresolvedContractError) as exc:
        resolve_contracts(experiment_b_adapters(), [GRADIENT_WALLS])
    text = str(exc.value)
    assert "gradient-force" in text
    assert "py-pde" in text and "pymunk" in text
    assert "walls" in text
    assert "variant 'movers'" in text
    assert "compose" in text  # remediation present
    assert "before any engine stepped" in text


# ----------------------------------------------------------------------
# M. Never infer couplings: empty contract set always resolves
# ----------------------------------------------------------------------
def test_m_no_automatic_coupling_inferred() -> None:
    resolve_contracts(experiment_a_adapters(), [])
    resolve_contracts(experiment_b_adapters(), [])
    # The movers world has a latent scalar_field->field_sensing overlap, but
    # with an empty declaration nothing is asserted and nothing is invented.
    resolve_contracts(experiment_c_adapters(), [])


# ----------------------------------------------------------------------
# N. Each experiment's declared contracts resolve on its own world
# ----------------------------------------------------------------------
def test_n_experiment_a_contracts_resolve() -> None:
    resolve_contracts(experiment_a_adapters(), MORPHOGENESIS_CONTRACTS)


def test_n_experiment_b_contracts_resolve() -> None:
    resolve_contracts(experiment_b_adapters(), FIELD_GUIDED_MOVERS_CONTRACTS)


def test_n_experiment_c_contracts_resolve() -> None:
    resolve_contracts(experiment_c_adapters(), NETWORK_MORPHOGENESIS_CONTRACTS)


# ----------------------------------------------------------------------
# O. Contracts do not change the science (bitwise)
# ----------------------------------------------------------------------
def test_o_contracts_preserve_a_science() -> None:
    cfg = WorldConfig(n=16, seed=0, n_steps=8, agent_configs=build_agents())
    with_contracts = compose_a(cfg, MORPHOGENESIS_CONTRACTS)
    without = compose_a(cfg, None)
    assert sha(with_contracts.final_u) == sha(without.final_u)
    assert with_contracts.force_mags == without.force_mags
    assert with_contracts.wall_speeds == without.wall_speeds


def test_o_contracts_preserve_b_science() -> None:
    cfg = MoversConfig(n=16, seed=0, n_steps=8)
    with_contracts = compose_b(cfg, FIELD_GUIDED_MOVERS_CONTRACTS)
    without = compose_b(cfg, None)
    assert sha(with_contracts.final_u) == sha(without.final_u)
    assert with_contracts.positions == without.positions
    assert with_contracts.force_mags == without.force_mags


def test_o_contracts_preserve_c_science() -> None:
    cfg = NetworkMorphogenesisConfig(n=16, seed=0, n_steps=4)
    with_contracts = compose_c(cfg, NETWORK_MORPHOGENESIS_CONTRACTS)
    without = compose_c(cfg, None)
    assert sha(with_contracts.final_u) == sha(without.final_u)
    assert with_contracts.walls_per_step == without.walls_per_step


# ----------------------------------------------------------------------
# P. The Task 2.2 gap: capability-valid but coupling-invalid is rejected
# ----------------------------------------------------------------------
def test_p_capability_valid_coupling_invalid_rejected() -> None:
    world = build_network_morphogenesis_world(n=8, n_steps=2)
    registry = build_network_morphogenesis_registry()

    def movers_factory(cfg: dict) -> MoversAdapter:
        return MoversAdapter(
            MoversConfig(n=int(cfg.get("n", 8)), seed=0)
        )

    registry.register("pymunk", movers_factory)
    adapters = build_components(registry, world)

    # Capability layer PASSES: movers satisfy rigid_body/geometry_provider and
    # the pde satisfies the network's reaction_diffusion requirement.
    resolve_capabilities(adapters, list(world.requires))

    # Contract layer REJECTS: the declared walls-variant edges are not realized.
    noop_ops = {name: (lambda dt: None) for name in NETWORK_MORPHOGENESIS_SCHEDULE}
    with pytest.raises(UnresolvedContractError) as exc:
        compose(world, registry, noop_ops, contracts=NETWORK_MORPHOGENESIS_CONTRACTS)
    text = str(exc.value)
    assert "pymunk" in text and "walls" in text

    # Failure is pre-execution: adapters were never initialized/stepped.
    pde = cast(PyPDEAdapter, adapter_by_id(adapters, "py-pde"))
    assert pde._initialized is False


# ----------------------------------------------------------------------
# Q. Plain compose accepts the validated worlds WITH declared contracts
# ----------------------------------------------------------------------
def test_q_plain_compose_accepts_a_with_contracts() -> None:
    cfg = WorldConfig(n=16, seed=0, n_steps=4, agent_configs=build_agents())
    trajectory = compose_a(cfg, MORPHOGENESIS_CONTRACTS)
    assert len(trajectory.t_field) == cfg.n_steps


def test_q_plain_compose_accepts_b_with_contracts() -> None:
    cfg = MoversConfig(n=16, seed=0, n_steps=4)
    trajectory = compose_b(cfg, FIELD_GUIDED_MOVERS_CONTRACTS)
    assert len(trajectory.t_field) == cfg.n_steps


# ----------------------------------------------------------------------
# R. Facades and the executor keep running with contracts wired
# ----------------------------------------------------------------------
def test_r_facades_still_run() -> None:
    b = FieldGuidedMoversEngine(MoversConfig(n=16, seed=0, n_steps=2))
    b_traj = b.run()
    assert len(b_traj.t_field) == 2

    c = NetworkMorphogenesisEngine(NetworkMorphogenesisConfig(n=16, seed=0, n_steps=2))
    c_traj = c.run()
    assert len(c_traj.t_field) == 2


def test_r_executor_still_runs() -> None:
    world = build_network_morphogenesis_world(n=16, n_steps=2)
    outcome = run_network_world(world)
    assert isinstance(outcome.trajectory, NetworkMorphogenesisTrajectory)

    # Determinism through the executor (id-based adapter binding).
    again = run_network_world(world)
    assert sha(outcome.trajectory.final_u) == sha(again.trajectory.final_u)


# ----------------------------------------------------------------------
# Determinism cross-check of the whole network run (same seed -> same trace)
# ----------------------------------------------------------------------
def test_network_facade_replay_deterministic() -> None:
    t1 = run_network_morphogenesis(NetworkMorphogenesisConfig(n=16, seed=0, n_steps=3))
    t2 = run_network_morphogenesis(NetworkMorphogenesisConfig(n=16, seed=0, n_steps=3))
    assert sha(t1.final_u) == sha(t2.final_u)
    assert t1.walls_per_step == t2.walls_per_step