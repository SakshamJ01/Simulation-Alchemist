"""Task 1.8 demonstration: behavioral characterization + interestingness.

Loads Experiment C (Adaptive Network Morphogenesis) from its declarative YAML
world, declares a small mutation space, executes the baseline control plus
every variant sequentially through the generic ``BehavioralAnalysisRunner``,
extracts deterministic behavioral features from each run's per-step
observables, and ranks the population against an explicit, human-readable
``InterestingnessProfile`` (no learned weights: every feature contributes
``weight * directional`` where the direction is declared ``max``/``min``).

Usage examples::

    uv run python run_behavior_demo.py \\
        --dim components.network.config.loss:0.05,0.08,0.11,0.14 \\
        --feature wall_count:activity_rate:0.4:max \\
        --feature network_load_max:late_vs_full_variance_ratio:0.3:min \\
        --feature field_mean:oscillation_strength:0.3:max

Variants follow the documented Cartesian product order (right-most dimension
varies fastest, as in ``run_sweep.py``).  Use ``--steps N`` to control run
length (default 10 macro-steps for a fast local demonstration; 160 matches the
canonical regression) and ``--db PATH`` to persist the lineage + behavioral
analysis records to a SQLite file.
"""

from __future__ import annotations

import argparse
import dataclasses
import tempfile
from pathlib import Path

from experiments.network_morphogenesis.experiment import (
    build_network_observables,
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    BehavioralAnalysisRunner,
    InterestingnessProfile,
    LineageStore,
    MutationSpace,
    ParameterSweep,
    load_world_yaml,
    world_hash,
)


def _parse_dim(spec: str) -> ParameterSweep:
    if ":" not in spec:
        raise SystemExit(f"--dim expects 'path:value1,value2,...', got {spec!r}")
    path, raw_values = spec.split(":", 1)
    values = []
    for token in raw_values.split(","):
        token = token.strip()
        try:
            values.append(float(token))
        except ValueError:
            values.append(token)
    return ParameterSweep(path=path, values=tuple(values))


def _parse_feature(spec: str) -> tuple[str, float, bool]:
    """Parse ``feature:weight[:min|max]`` (direction defaults to ``max``)."""
    parts = spec.rsplit(":", 2)
    maximize = True
    if len(parts) == 2:
        feature, weight_token = parts
    elif len(parts) == 3:
        feature, weight_token, dir_token = parts
        if dir_token.strip().lower() not in ("min", "max"):
            raise SystemExit(f"direction must be 'min' or 'max' in {spec!r}")
        maximize = dir_token.strip().lower() == "max"
    else:
        raise SystemExit(
            f"--feature expects 'feature:weight[:min|max]', got {spec!r}"
        )
    try:
        weight = float(weight_token)
    except ValueError:
        raise SystemExit(f"weight must be numeric in {spec!r}") from None
    if weight < 0:
        raise SystemExit(f"weight must be non-negative in {spec!r}")
    return feature, weight, maximize


def _fmt_features(features) -> str:
    flat = features.flatten()
    keys = sorted(
        flat.keys(),
        key=lambda k: (
            k.split(":")[0],
            ("temporal", "trend", "oscillation", "stability", "divergence").index(
                k.split(":")[1]
            )
            if k.split(":")[1] in ("temporal", "trend", "oscillation", "stability", "divergence")
            else 99,
            k.split(":")[1],
        ),
    )
    shown = [
        k
        for k in keys
        if k.split(":")[1]
        in ("total_variation", "activity_rate", "trend_slope", "residual_variance_fraction",
            "sign_change_rate", "oscillation_persistence", "oscillation_strength",
            "late_vs_full_variance_ratio", "rmsd")
    ]
    return ", ".join(
        f"{k}={v:g}" for k in shown if (v := flat[k]) is not None
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world", default="worlds/adaptive_network.yaml",
        help="path to the declarative world YAML (default adaptive_network.yaml)",
    )
    parser.add_argument(
        "--dim", action="append", required=True,
        help="sweep dimension 'path:value1,value2,...' (repeatable)",
    )
    parser.add_argument(
        "--feature", action="append", required=True,
        help="profile feature 'feature:weight[:min|max]' e.g. wall_count:activity_rate:0.4:max",
    )
    parser.add_argument(
        "--steps", type=int, default=10,
        help="number of macro-steps (default 10 for a fast demo; 160 = canonical)",
    )
    parser.add_argument(
        "--db", default=None,
        help="SQLite lineage file (default: a fresh temporary file)",
    )
    args = parser.parse_args(argv)

    world = load_world_yaml(args.world)
    if args.steps != 160:
        world = dataclasses.replace(
            world, max_steps=args.steps, config={**world.config, "n_steps": args.steps}
        )

    space = MutationSpace(tuple(_parse_dim(d) for d in args.dim))
    weights: dict[str, float] = {}
    directions: dict[str, bool] = {}
    for item in args.feature:
        feature, weight, maximize = _parse_feature(item)
        weights[feature] = weight
        directions[feature] = maximize
    profile = InterestingnessProfile(
        name="default-interestingness",
        description="explicit profile from --feature flags (no learned weights)",
        weights=weights,
        directions=directions,
    )

    db_path = args.db or str(Path(tempfile.gettempdir()) / "behavior_lineage.db")
    store = LineageStore(db_path)
    runner = BehavioralAnalysisRunner(
        store,
        run_network_world,
        lambda outcome: build_network_observables(outcome.trajectory),
        parameter_specs=specs_by_path(),
    )

    print(f"Adaptive Network Morphogenesis behavioral analysis ({args.steps} macro-steps)")
    print(f"Mutation space: {space.to_dict()['dimensions']}")
    print(f"Declared variants: {space.variant_count} (baseline control included)")
    print(f"Profile: {weights}")
    print()

    result = runner.analyze(world, space, profile)
    print(f"Analysis id   {result.analysis_id}")
    print(f"Base world    {world_hash(result.world)}")
    print()

    print("POPULATION (features; baseline shown first, then generation order)")
    for run in result.population:
        kind = run.kind
        marker = "  (baseline control)" if kind == "baseline" else ""
        print(f"  {run.run_id} [{kind}]{marker}")
        print(f"      {_fmt_features(run.features)}")
    print()

    if result.timing.n_skipped:
        print(f"(skipped {result.timing.n_skipped} no-op combination(s) identical to baseline)")
    print(
        f"TIMING  planned={result.timing.n_planned} executed={result.timing.n_executed} "
        f"total={result.timing.total_seconds:.2f}s "
        f"mean={result.timing.mean_seconds:.2f}s"
    )
    print()

    print("RANKING (profile: score descending, ties by run id ascending)")
    for row in result.ranking.rows:
        marker = "  (baseline control)" if row.kind == "baseline" else ""
        print(f"  {row.rank:>2}. {row.run_id}  score={row.score:.6g}  {row.kind}{marker}")
    print()
    print("WHY (top-ranked run)")
    print("\n".join(result.explain(result.ranking.rows[0].run_id)))
    print()

    print("LINEAGE")
    print(f"  Base    {result.population[0].run_id}  (baseline control)")
    print(
        f"\nPersisted to SQLite: {db_path}  "
        f"(runs={store.run_count}, behavior analyses={store.behavior_analysis_count})"
    )


if __name__ == "__main__":
    main()