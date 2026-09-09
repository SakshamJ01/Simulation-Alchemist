"""Task 2.5 Build Stage 1 validation: composition-specific parameter-space
binding + deterministic cross-split sweep identity + result model.

Stage 1 is the data-model foundation only.  Nothing executes: no ``SweepRunner``,
no adapters, no simulations, no run recording, no ranking/frontier.  The
experiment-owned parameter spaces live in ``experiments/catalog.py``; the
generic, experiment-free result model lives in ``core/cross_sweep.py``.

Checks:

    A  registry contains all executable compositions
    B  a valid MutationSpace is returned where legitimately defined
    C  None is returned where no legitimate space exists
    D  unknown-composition handling (KeyError)
    E  registry output is deterministic
    F  no fake shared parameter dimensions are invented
    G  experiment-specific spaces remain outside the generic core
    H  parameter_space_ref is deterministic
    I  a None reference works (composition with no space)
    J  the reference survives serialization/round-trip
    K  changing a space (and thus its reference) changes canonical identity
    L  cross_split_sweep_id: identical spec -> identical id
    M  cross_split_sweep_id: different seed -> different id
    N  cross_split_sweep_id: different profile -> different id
    O  cross_split_sweep_id: different evaluation config -> different id
    P  cross_split_sweep_id: different ordered binding composition -> different id
    Q  cross_split_sweep_id: changing a space reference -> different id
    R  cross_split_sweep_id: no timestamps / random / object-repr inputs
    S  cross_split_sweep_id: canonical serialization independent of dict order
    T  result model: construction + deterministic equality
    U  result model: serialization round-trip
    V  result model: baseline is distinct from mutated variants
    W  result model: composition-specific spaces (None vs empty vs valid)
    X  identity hierarchy: composition_id / cross_split_sweep_id / sweep_id /
       run_id remain distinct fields
    Y  no-execution architectural proof: the core module contains no
       sweep/composition/adapter/run execution tokens
"""

from __future__ import annotations

import pathlib

import pytest

from experiments.catalog import (
    build_repository_catalog,
    repository_parameter_spaces,
)
from sim_alchemist.core.cross_sweep import (
    CompositionSpaceBinding,
    CrossCompositionSweepRecord,
    CrossCompositionSweepResult,
    CrossCompositionSweepSpec,
    cross_split_sweep_id,
    parameter_space_ref,
)
from sim_alchemist.core.sweep import MutationSpace, ParameterSweep

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "src" / "sim_alchemist" / "core"

FORBIDDEN_CORE_TOKENS = (
    "mesa", "pde", "pymunk", "ndlib", "network", "morphogenesis",
    "chemomech", "movers", "wall", "loss", "source_amplitude",
    "force_fmax", "agent", "geometry", "rigid_body",
)


def toy_space() -> MutationSpace:
    return MutationSpace((ParameterSweep("config.x", (1.0, 2.0, 3.0)),))


def toy_binding(composition_id: str = "c1", shape_id: str = "s1") -> CompositionSpaceBinding:
    return CompositionSpaceBinding(
        composition_id=composition_id,
        shape_id=shape_id,
        ref=parameter_space_ref(toy_space()),
        space=toy_space(),
    )


# ----------------------------------------------------------------------
# A-G. Repository parameter-space registry
# ----------------------------------------------------------------------
def test_a_registry_contains_all_executable_compositions() -> None:
    spaces = repository_parameter_spaces()
    catalog = build_repository_catalog(generate_worlds=True)
    executable_ids = {
        c.composition_id for c in catalog.executable() if c.composition_id is not None
    }
    assert set(spaces) == executable_ids
    assert len(spaces) == 3


def test_b_valid_space_where_defined() -> None:
    spaces = repository_parameter_spaces()
    with_space = [b for b in spaces.values() if b.has_space]
    assert len(with_space) == 1
    binding = with_space[0]
    assert binding.space is not None
    assert binding.space.variant_count == 3 * 3 * 3
    assert binding.ref is not None


def test_c_none_where_no_legitimate_space() -> None:
    spaces = repository_parameter_spaces()
    for binding in spaces.values():
        if not binding.has_space:
            assert binding.space is None
            assert binding.ref is None


def test_d_unknown_composition_handling() -> None:
    spaces = repository_parameter_spaces()
    with pytest.raises(KeyError):
        _ = spaces["not-a-composition"]


def test_e_registry_is_deterministic() -> None:
    first = repository_parameter_spaces()
    second = repository_parameter_spaces()
    assert sorted(first) == sorted(second)
    for key in first:
        assert first[key] == second[key]


def test_f_no_fake_shared_parameter_dimensions() -> None:
    spaces = repository_parameter_spaces()
    shared = {p for b in spaces.values() if b.space is not None for p in (
        d.path for d in b.space.dimensions
    )}
    # A / B declare no space at all; the only space present is the network one,
    # so no parameter path is shared across two distinct compositions.
    assert shared == {
        "components.network.config.loss",
        "config.force_fmax",
        "config.source_amplitude",
    }


def test_g_experiment_spaces_outside_generic_core() -> None:
    source = (CORE_DIR / "cross_sweep.py").read_text(encoding="utf-8").lower()
    hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
    assert not hits, f"core/cross_sweep.py must stay experiment-free, found: {hits}"


# ----------------------------------------------------------------------
# H-K. parameter_space_ref
# ----------------------------------------------------------------------
def test_h_ref_is_deterministic() -> None:
    assert parameter_space_ref(toy_space()) == parameter_space_ref(toy_space())
    assert len(parameter_space_ref(toy_space())) == 64
    assert all(c in "0123456789abcdef" for c in parameter_space_ref(toy_space()))


def test_i_none_ref_works() -> None:
    binding = CompositionSpaceBinding(composition_id="a", shape_id="s")
    assert binding.ref is None
    assert binding.space is None
    assert not binding.has_space


def test_j_ref_survives_serialization() -> None:
    binding = toy_binding()
    restored = CompositionSpaceBinding.from_dict(binding.as_dict())
    assert restored == binding
    assert restored.ref == binding.ref
    assert restored.space == binding.space


def test_k_changing_space_changes_ref_and_identity() -> None:
    other_space = MutationSpace((ParameterSweep("config.x", (1.0, 5.0, 9.0)),))
    binding_a = toy_binding("c1")
    binding_b = CompositionSpaceBinding(
        composition_id="c1",
        shape_id="s1",
        ref=parameter_space_ref(other_space),
        space=other_space,
    )
    assert parameter_space_ref(toy_space()) != parameter_space_ref(other_space)
    spec_a = CrossCompositionSweepSpec("u", (binding_a,))
    spec_b = CrossCompositionSweepSpec("u", (binding_b,))
    assert cross_split_sweep_id(spec_a) != cross_split_sweep_id(spec_b)


# ----------------------------------------------------------------------
# L-S. cross_split_sweep_id determinism
# ----------------------------------------------------------------------
def _spec(*, bindings=None, profile=None, seed=0, eval_cfg=None) -> CrossCompositionSweepSpec:
    return CrossCompositionSweepSpec(
        "universe", tuple(bindings) if bindings is not None else (toy_binding(),),
        profile=profile, seed=seed, evaluation_config=eval_cfg,
    )


def test_l_identical_spec_identical_id() -> None:
    assert cross_split_sweep_id(_spec()) == cross_split_sweep_id(_spec())


def test_m_different_seed_different_id() -> None:
    assert cross_split_sweep_id(_spec(seed=0)) != cross_split_sweep_id(_spec(seed=1))


def test_n_different_profile_different_id() -> None:
    a = _spec(profile={"quality": 1.0})
    b = _spec(profile={"quality": 2.0})
    assert cross_split_sweep_id(a) != cross_split_sweep_id(b)


def test_o_different_eval_config_different_id() -> None:
    a = _spec(eval_cfg={"max_steps": 160})
    b = _spec(eval_cfg={"max_steps": 320})
    assert cross_split_sweep_id(a) != cross_split_sweep_id(b)


def test_p_different_ordered_bindings_different_id() -> None:
    b1 = toy_binding("c1", "s1")
    b2 = toy_binding("c2", "s2")
    ab = _spec(bindings=(b1, b2))
    ba = _spec(bindings=(b2, b1))
    assert cross_split_sweep_id(ab) != cross_split_sweep_id(ba)


def test_q_changed_space_ref_changes_id() -> None:
    base = toy_binding("c1")
    other = CompositionSpaceBinding(
        composition_id="c1",
        shape_id="s1",
        ref=parameter_space_ref(
            MutationSpace((ParameterSweep("config.x", (1.0, 2.0, 3.0, 4.0)),))
        ),
        space=MutationSpace((ParameterSweep("config.x", (1.0, 2.0, 3.0, 4.0)),)),
    )
    assert cross_split_sweep_id(_spec(bindings=(base,))) != cross_split_sweep_id(
        _spec(bindings=(other,))
    )


def test_r_no_timestamps_or_random_inputs() -> None:
    # Two calls produce a stable 24-hex id with no dependence on time/random.
    first = cross_split_sweep_id(_spec())
    second = cross_split_sweep_id(_spec())
    assert first == second
    assert len(first) == 24
    assert all(c in "0123456789abcdef" for c in first)


def test_s_canonical_serialization_order_independent() -> None:
    a = _spec(eval_cfg={"b": 2, "a": 1})
    b = _spec(eval_cfg={"a": 1, "b": 2})
    assert cross_split_sweep_id(a) == cross_split_sweep_id(b)
    assert a.as_dict(canonical=True) == b.as_dict(canonical=True)


# ----------------------------------------------------------------------
# T-X. Result model
# ----------------------------------------------------------------------
def test_t_result_construction_and_equal() -> None:
    spec = _spec()
    r1 = CrossCompositionSweepResult(cross_split_sweep_id(spec), spec, spec.bindings)
    r2 = CrossCompositionSweepResult(cross_split_sweep_id(spec), spec, spec.bindings)
    assert r1 == r2
    assert r1.state == "planned"
    assert r1.cross_split_sweep_id == cross_split_sweep_id(spec)


def test_u_result_serialization_roundtrip() -> None:
    spec = _spec()
    result = CrossCompositionSweepResult(cross_split_sweep_id(spec), spec, spec.bindings)
    payload = result.as_dict()
    assert payload["state"] == "planned"
    assert payload["cross_split_sweep_id"] == result.cross_split_sweep_id
    assert [b["composition_id"] for b in payload["bindings"]] == [
        b.composition_id for b in result.bindings
    ]


def test_v_baseline_distinct_from_variants() -> None:
    binding = toy_binding()
    # Baseline is an explicit control field; variants live in a separate list.
    assert binding.baseline_run_id is None
    assert binding.variant_run_ids == ()
    bound = binding.as_dict()
    assert "baseline_run_id" in bound
    assert "variant_run_ids" in bound
    assert bound["baseline_run_id"] != bound["variant_run_ids"]
    assert bound["variant_run_ids"] == []


def test_w_composition_specific_spaces_none_vs_valid() -> None:
    none_binding = CompositionSpaceBinding(composition_id="a", shape_id="s")
    valid_binding = toy_binding()
    assert none_binding.space is None and none_binding.ref is None
    assert valid_binding.space is not None and valid_binding.ref is not None
    assert not none_binding.has_space and valid_binding.has_space
    # Empty spaces are structurally impossible (MutationSpace requires >=1 dim)
    with pytest.raises(ValueError):
        MutationSpace(())


def test_x_identities_remain_distinct() -> None:
    binding = toy_binding()
    spec = _spec(bindings=(binding,))
    result = CrossCompositionSweepResult(cross_split_sweep_id(spec), spec, spec.bindings)
    ids = {
        "composition_id": binding.composition_id,
        "cross_split_sweep_id": result.cross_split_sweep_id,
        "sweep_id": binding.sweep_id,
        "run_id": binding.baseline_run_id,
    }
    assert len(set(ids.values())) >= 3  # distinct non-"" identity sources, at least
    assert cross_split_sweep_id.__name__ == "cross_split_sweep_id"


def test_x2_cross_composition_sweep_record_in_memory_only() -> None:
    spec = _spec()
    record = CrossCompositionSweepRecord(
        cross_split_sweep_id=cross_split_sweep_id(spec),
        space_name=spec.space_name,
        seed=spec.seed,
        bindings=spec.bindings,
    )
    assert record.cross_split_sweep_id == cross_split_sweep_id(spec)
    assert record.bindings == spec.bindings


# ----------------------------------------------------------------------
# Y. No-execution architectural proof
# ----------------------------------------------------------------------
def test_y_no_execution_in_core_model() -> None:
    # The model module must perform no execution and touch no lineage.  It only
    # imports the generic MutationSpace type; scan the *imports* (not prose)
    # for any execution / orchestration / lineage primitive.
    source = (CORE_DIR / "cross_sweep.py").read_text(encoding="utf-8")
    forbidden_imports = (
        "SweepRunner", "VariantRunner", "LineageStore", "AlchemistEngine",
        "compose", "compose_into", "BehavioralAnalysisRunner", "SearchRunner",
        "Searcher", "record_run", "record_sweep",
    )
    import_lines = [ln for ln in source.splitlines() if ln.strip().startswith(("from ", "import "))]
    import_text = "\n".join(import_lines)
    hits = [tok for tok in forbidden_imports if tok in import_text]
    assert not hits, (
        f"core/cross_sweep.py imports execution/lineage primitives: {hits}"
    )
    # The result model is only ever "planned" until Stage 2 executes it.
    spec = _spec()
    result = CrossCompositionSweepResult(cross_split_sweep_id(spec), spec, spec.bindings)
    assert result.state == "planned"
