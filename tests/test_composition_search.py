"""Cross-composition evaluation identity + baseline evaluation (Task 2.4 Stage 1).

Stage 1 delivers the *result layer* of the cross-composition discovery loop:
a content-addressed identity for a discovery pass
(``composition_discovery_id_of``), the compact ``CompositionEvaluation`` result
model, the additive nullable ``composition_id`` lineage stamp on the existing
``runs`` table (with in-place migration for pre-2.4 stores), and the generic
``EXECUTABLE``-only baseline evaluation
(``evaluate_composition_baseline``) driven by the experiment-owned executors
surfaced via ``repository_executors``.

These tests prove, in order:

  * identity A-E: deterministic, content-addressed, profile/seed/config-aware;
  * result model A-D: field population, round-trip, dict independence;
  * lineage A-E: persistence, root-parent semantics, pre-2.4 migration,
    legacy load, idempotence;
  * executable evaluation A-F: all three EXECUTABLE compositions recognized,
    one root baseline each, composition identity retained, non-executables
    never evaluated, idempotent re-evaluation, cross-store determinism.

The executable evaluations use fast (``FAST_STEPS``) generated worlds; the
canonical full-length bitwise parity of generated worlds vs the experiment
facades is already proven by the slow tests in ``test_world_generation.py``.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from chemomech.coupling import build_morphogenesis_template
from chemomech.experiment import build_morphogenesis_metrics, run_morphogenesis_world
from chemomech.simulation import WorldConfig, run_world
from experiments.catalog import (
    build_repository_adapters,
    repository_bindings,
    repository_executors,
    repository_surfaces,
    repository_templates,
)
from experiments.field_guided_movers.coupling import (
    build_field_guided_movers_template,
)
from experiments.field_guided_movers.experiment import (
    build_movers_metrics,
    run_field_guided_movers_world,
)
from experiments.field_guided_movers.model import MoversConfig, run_field_guided_movers
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_template,
)
from sim_alchemist.core import (
    COUPLING_UNAVAILABLE,
    EXECUTABLE,
    CompositionEvaluation,
    CompositionEvaluationError,
    CompositionSpace,
    CouplingTemplateRegistry,
    ExecOutcome,
    InterestingnessProfile,
    LineageStore,
    RunRecord,
    WorldDefinition,
    composition_discovery_id_of,
    evaluate_composition_baseline,
    run_id_of,
    template_composition_id,
    world_hash,
)
from sim_alchemist.core.catalog import CompositionCatalog

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = REPO_ROOT / "src" / "sim_alchemist" / "core"

FAST_STEPS = 2

# Tokens that must never appear in the generic core evaluation sources (they
# are experiment or domain identifiers, not data keys).
FORBIDDEN_CORE_TOKENS = (
    "ndlib",
    "mesa",
    "pymunk",
    "chemomech",
    "morphogen",
    "network",
    "adapt",
)


def _fast_template(template, *, steps: int = FAST_STEPS):
    return dataclasses.replace(
        template,
        max_steps=steps,
        config={**dict(template.config), "n_steps": steps},
    )


def build_fast_repository_catalog(*, generate_worlds: bool = True) -> CompositionCatalog:
    """The 23-shape repository catalog with FAST_STEPS world generation.

    ``composition_id`` ignores ``max_steps``/``config`` (shape + contracts +
    schedule + requires + macro timestep only), so executable composition ids
    are identical to the canonical repository catalog -- fast to evaluate.
    """
    registry = CouplingTemplateRegistry()
    for build in (
        build_morphogenesis_template,
        build_field_guided_movers_template,
        build_network_morphogenesis_template,
    ):
        registry.register(_fast_template(build(), steps=FAST_STEPS))
    space = CompositionSpace(
        name="repository",
        universe=repository_bindings(),
        min_size=1,
        max_size=4,
    )
    return CompositionCatalog(
        space,
        repository_surfaces(),
        registry,
        build_adapters=build_repository_adapters,
        generate_worlds=generate_worlds,
    )


def _profile(*, name: str = "x") -> InterestingnessProfile:
    return InterestingnessProfile(name=name, description="", weights={"o:f": 1.0})


@pytest.fixture(scope="module")
def fast_catalog() -> CompositionCatalog:
    return build_fast_repository_catalog(generate_worlds=True)


@pytest.fixture(scope="module")
def evaluated_store(fast_catalog):
    """All three executable baselines, evaluated once into one fresh store."""
    store = LineageStore(":memory:")
    executors = repository_executors()
    evals = [
        evaluate_composition_baseline(store, executors[c.composition_id], c)
        for c in fast_catalog.executable()
    ]
    return store, evals


# ----------------------------------------------------------------------
# 1. Discovery identity (composition_discovery_id_of): A-E
# ----------------------------------------------------------------------
class TestDiscoveryIdentity:
    def test_a_deterministic(self, fast_catalog) -> None:
        a = composition_discovery_id_of(fast_catalog, _profile())
        b = composition_discovery_id_of(fast_catalog, _profile())
        assert a == b
        assert len(a) == 24

    def test_b_content_addressed_across_catalog_instances(self) -> None:
        cat1 = build_fast_repository_catalog()
        cat2 = build_fast_repository_catalog()
        assert composition_discovery_id_of(cat1, _profile()) == composition_discovery_id_of(
            cat2, _profile()
        )

    def test_c_profile_change_changes_id(self, fast_catalog) -> None:
        alt = InterestingnessProfile(name="y", description="", weights={"o:g": 2.0})
        assert composition_discovery_id_of(fast_catalog, alt) != composition_discovery_id_of(
            fast_catalog, _profile()
        )

    def test_d_seed_and_evaluation_config_change_id(self, fast_catalog) -> None:
        base = composition_discovery_id_of(fast_catalog, _profile(), seed=0)
        assert composition_discovery_id_of(fast_catalog, _profile(), seed=1) != base
        assert composition_discovery_id_of(
            fast_catalog, _profile(), seed=0, evaluation_config={"max_steps": 3}
        ) != base
        assert composition_discovery_id_of(
            fast_catalog, _profile(), seed=0, evaluation_config={"max_steps": 2}
        ) != composition_discovery_id_of(
            fast_catalog, _profile(), seed=0, evaluation_config={"max_steps": 3}
        )

    def test_e_is_a_24_hex_not_a_uuid(self, fast_catalog) -> None:
        id_value = composition_discovery_id_of(fast_catalog, _profile())
        assert len(id_value) == 24
        try:
            int(id_value, 16)
        except ValueError as error:  # pragma: no cover - defensive
            raise AssertionError(f"not hex: {id_value!r}") from error
        assert set(id_value) <= set("0123456789abcdef")


# ----------------------------------------------------------------------
# 2. Result model (CompositionEvaluation): A-D
# ----------------------------------------------------------------------
class TestCompositionEvaluation:
    def _record(self, **overrides) -> RunRecord:
        world = WorldDefinition(
            id="world_x", components=(), config={}, seed=7, max_steps=1
        )
        kwargs = {"metrics": {"m": 1.0}, "composition_id": "abcdef", **overrides}
        return RunRecord(
            run_id=run_id_of(world),
            world=world,
            **kwargs,
        )

    def test_a_fields_populated_from_run_record(self) -> None:
        world = WorldDefinition(id="world_x", components=(), config={}, seed=7, max_steps=1)
        record = self._record()
        assert record.world == world
        ev = CompositionEvaluation.from_run_record(
            record, shape_id="shape_x", status=EXECUTABLE
        )
        assert ev.composition_id == "abcdef"
        assert ev.shape_id == "shape_x"
        assert ev.world_hash == world_hash(world)
        assert ev.world_id == "world_x"
        assert ev.run_id == run_id_of(world)
        assert ev.status == EXECUTABLE
        assert ev.seed == 7
        assert ev.metrics == {"m": 1.0}

    def test_b_as_dict_round_trip(self) -> None:
        ev = CompositionEvaluation.from_run_record(
            self._record(), shape_id="shape_x"
        )
        assert ev.status == EXECUTABLE  # default status
        assert CompositionEvaluation(**ev.as_dict()) == ev

    def test_c_metrics_are_copied(self) -> None:
        metrics = {"m": 1.0}
        ev = CompositionEvaluation(
            composition_id="c",
            shape_id="s",
            world_hash="h",
            run_id="r",
            world_id="w",
            status=EXECUTABLE,
            seed=0,
            metrics=metrics,
        )
        metrics["m"] = 999.0
        assert ev.metrics == {"m": 1.0}
        assert ev.as_dict()["metrics"] == {"m": 1.0}

    def test_d_missing_composition_stamp_is_empty_string(self) -> None:
        record = self._record(composition_id=None)
        assert record.composition_id is None
        ev = CompositionEvaluation.from_run_record(record, shape_id="shape_x")
        assert ev.composition_id == ""


# ----------------------------------------------------------------------
# 3. Lineage (composition_id column + migration): A-E
# ----------------------------------------------------------------------
class TestCompositionLineage:
    _pre24_runs_table = """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            parent_run_id TEXT,
            world_id TEXT NOT NULL,
            world_hash TEXT NOT NULL,
            seed INTEGER NOT NULL,
            mutations TEXT NOT NULL,
            world_json TEXT NOT NULL,
            metrics TEXT NOT NULL,
            feature_snapshot TEXT,
            created_at TEXT NOT NULL
        )
        """

    def test_a_fresh_store_has_composition_id_column(self) -> None:
        store = LineageStore(":memory:")
        cols = [r[1] for r in store._conn.execute("PRAGMA table_info(runs)")]
        assert "composition_id" in cols
        store.close()

    def test_b_record_and_read_back(self) -> None:
        store = LineageStore(":memory:")
        world = WorldDefinition(id="w", components=(), config={}, seed=0, max_steps=1)
        rec = RunRecord(
            run_id=run_id_of(world),
            world=world,
            metrics={"m": 1.0},
            composition_id="compid123",
        )
        store.record_run(rec)
        found = store.get_run(rec.run_id)
        assert found is not None
        assert found.composition_id == "compid123"
        assert found.parent_run_id is None
        store.close()

    def test_c_migration_from_pre24_store(self, tmp_path) -> None:
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(self._pre24_runs_table)
        conn.commit()
        conn.close()

        store = LineageStore(str(db_path))
        cols = [r[1] for r in store._conn.execute("PRAGMA table_info(runs)")]
        assert "composition_id" in cols
        store.close()

    def test_d_legacy_run_loads_with_null_stamp(self, tmp_path) -> None:
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(self._pre24_runs_table)
        conn.commit()
        conn.close()

        store = LineageStore(str(db_path))
        world = WorldDefinition(id="old", components=(), config={}, seed=0, max_steps=1)
        legacy = RunRecord(run_id="legacy00000000000000000001", world=world, metrics={"m": 1.0})
        store.record_run(legacy)
        found = store.get_run(legacy.run_id)
        assert found is not None
        assert found.composition_id is None
        store.close()

    def test_e_idempotent_recording(self) -> None:
        store = LineageStore(":memory:")
        world = WorldDefinition(id="w", components=(), config={}, seed=0, max_steps=1)
        rec = RunRecord(
            run_id=run_id_of(world), world=world, metrics={"m": 1.0}, composition_id="x"
        )
        store.record_run(rec)
        store.record_run(rec)
        assert store.run_count == 1
        store.close()


# ----------------------------------------------------------------------
# 4. Executable evaluation (evaluate_composition_baseline): A-F
# ----------------------------------------------------------------------
class TestExecutableEvaluation:
    def test_a_three_executables_recognized(self, fast_catalog) -> None:
        executable = fast_catalog.executable()
        assert len(executable) == 3
        assert fast_catalog.status_counts() == {
            COUPLING_UNAVAILABLE: 4,
            EXECUTABLE: 3,
            "CAPABILITY_INVALID": 16,
        }
        for candidate in executable:
            assert candidate.generated_world is not None
            assert candidate.composition_id is not None

    def test_b_each_evaluates_to_a_root_baseline(self, evaluated_store) -> None:
        store, evals = evaluated_store
        assert len(evals) == 3
        run_ids = {ev.run_id for ev in evals}
        assert len(run_ids) == 3
        for ev in evals:
            assert ev.status == EXECUTABLE
            assert ev.metrics
            record = store.get_run(ev.run_id)
            assert record is not None
            assert record.parent_run_id is None
            assert record.composition_id == ev.composition_id

    def test_c_composition_identity_retained(self, fast_catalog, evaluated_store) -> None:
        _, evals = evaluated_store
        registry = repository_templates()
        by_composition = {ev.composition_id: ev for ev in evals}
        for candidate in fast_catalog.executable():
            template = registry.by_name(candidate.template or "")
            assert template is not None
            assert template_composition_id(template) == candidate.composition_id
            assert candidate.composition_id in by_composition

    def test_d_non_executables_never_evaluated(self, fast_catalog) -> None:
        def _boom(world):  # pragma: no cover - must never be called
            raise AssertionError("non-executable candidates must never be simulated")

        store = LineageStore(":memory:")
        for candidate in fast_catalog.invalid():
            with pytest.raises(CompositionEvaluationError):
                evaluate_composition_baseline(store, _boom, candidate)
        assert store.run_count == 0
        store.close()

    def test_d2_missing_generated_world_rejected(self) -> None:
        catalog = build_fast_repository_catalog(generate_worlds=False)
        candidate = catalog.executable()[0]

        def _boom(world):  # pragma: no cover - must never be called
            raise AssertionError("no-world candidates must never be simulated")

        store = LineageStore(":memory:")
        with pytest.raises(CompositionEvaluationError):
            evaluate_composition_baseline(store, _boom, candidate)
        assert store.run_count == 0
        store.close()

    def test_e_reevaluation_is_idempotent(self, fast_catalog) -> None:
        store = LineageStore(":memory:")
        executors = repository_executors()
        candidate = fast_catalog.executable()[0]
        first = evaluate_composition_baseline(store, executors[candidate.composition_id], candidate)
        second = evaluate_composition_baseline(store, executors[candidate.composition_id], candidate)
        assert first.run_id == second.run_id
        assert first.as_dict() == second.as_dict()
        assert store.run_count == 1
        store.close()

    def test_f_deterministic_across_stores(self, fast_catalog) -> None:
        executors = repository_executors()

        def _evaluate() -> list[dict]:
            store = LineageStore(":memory:")
            evals = [
                evaluate_composition_baseline(store, executors[c.composition_id], c)
                for c in fast_catalog.executable()
            ]
            store.close()
            return [ev.as_dict() for ev in evals]

        assert _evaluate() == _evaluate()


# ----------------------------------------------------------------------
# 5. Executor surface: repository_executors resolves every executable
# ----------------------------------------------------------------------
class TestRepositoryExecutors:
    def test_keys_are_the_executable_composition_ids(self, fast_catalog) -> None:
        executors = repository_executors()
        assert set(executors) == {c.composition_id for c in fast_catalog.executable()}

    def test_each_executor_returns_an_exec_outcome(self) -> None:
        executors = repository_executors()
        catalog = build_fast_repository_catalog(generate_worlds=True)
        for candidate in catalog.executable():
            composition_id = candidate.composition_id
            world = candidate.generated_world
            assert composition_id is not None
            assert world is not None
            outcome = executors[composition_id](world)
            assert isinstance(outcome, ExecOutcome)
            assert outcome.metrics


# ----------------------------------------------------------------------
# 6. Core purity: composition_search.py stays experiment-free
# ----------------------------------------------------------------------
class TestCorePurity:
    def test_composition_search_is_experiment_free(self) -> None:
        source = (CORE_DIR / "composition_search.py").read_text(encoding="utf-8").lower()
        hits = [tok for tok in FORBIDDEN_CORE_TOKENS if tok in source]
        assert not hits, f"core/composition_search.py contains experiment identifiers: {hits}"


# ----------------------------------------------------------------------
# 7. Slow: the new Experiment A/B executors reproduce facade metrics
#    (C's run_network_world already proven bitwise in the Task 2.3 slow
#    suite; these close the loop for the two wrappers added here.)
# ----------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.parametrize(
    ("template_builder", "executor", "facade", "metric_builder", "facade_config"),
    [
        (
            build_morphogenesis_template,
            run_morphogenesis_world,
            run_world,
            build_morphogenesis_metrics,
            WorldConfig(),
        ),
        (
            build_field_guided_movers_template,
            run_field_guided_movers_world,
            run_field_guided_movers,
            build_movers_metrics,
            MoversConfig(),
        ),
    ],
)
def test_slow_executor_metrics_match_facade(
    template_builder, executor, facade, metric_builder, facade_config
) -> None:
    from sim_alchemist.core import generate_world

    outcome = executor(generate_world(template_builder()))
    assert outcome.metrics == metric_builder(facade(facade_config))