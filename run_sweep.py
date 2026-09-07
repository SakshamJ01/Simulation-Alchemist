"""Task 1.7 demonstration: a deterministic variant sweep + generic ranking.

Loads Experiment C (Adaptive Network Morphogenesis) from its declarative YAML
world, declares a small mutation space (Cartesian product of per-parameter
value lists), executes the baseline control plus every variant sequentially
through the generic ``SweepRunner``, and prints the real measured metrics,
the recorded lineage, the sweep timing, and a generic ranking by a selected
metric.

Usage examples::

    uv run python run_sweep.py \\
        --dim components.network.config.loss:0.05,0.08,0.11,0.14 \\
        --dim config.force_fmax:0.4,0.8 \\
        --rank-by field_entropy

The ordering of variants is the documented Cartesian product order (right-most
dimension varies fastest).  Use ``--steps N`` to control run length (default
10 macro-steps for a fast local demonstration; 160 matches the canonical
regression) and ``--db PATH`` to persist lineage to a SQLite file.
"""

from __future__ import annotations

import argparse
import dataclasses
import tempfile
from pathlib import Path

from experiments.network_morphogenesis.experiment import (
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    LineageStore,
    MutationSpace,
    ParameterSweep,
    SweepRunner,
    load_world_yaml,
)

_METRIC_LABELS = {
    "wall_count": "walls",
    "network_load_mean": "network load",
    "network_load_max": "network load max",
    "n_sources": "sources",
    "final_field_mean": "field mean",
    "final_field_std": "field std",
    "field_entropy": "field entropy",
    "wall_movement": "wall movement",
    "growth_edges": "growth edges",
}


def _fmt(metrics: dict[str, float]) -> str:
    return ", ".join(
        f"{_METRIC_LABELS.get(k, k)}: {v:g}" for k, v in metrics.items() if k in _METRIC_LABELS
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
        "--steps", type=int, default=10,
        help="number of macro-steps (default 10 for a fast demo; 160 = canonical)",
    )
    parser.add_argument(
        "--rank-by", default="field_entropy",
        help="metric used for the final generic ranking (default field_entropy)",
    )
    parser.add_argument(
        "--ascending", action="store_true",
        help="rank ascending (smallest is best) instead of descending",
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
    db_path = args.db or str(Path(tempfile.gettempdir()) / "sweep_lineage.db")
    store = LineageStore(db_path)
    runner = SweepRunner(store, run_network_world, parameter_specs=specs_by_path())

    print(f"Adaptive Network Morphogenesis variant sweep ({args.steps} macro-steps)")
    print(f"Mutation space: {space.to_dict()['dimensions']}")
    print(f"Declared variants: {space.variant_count} (baseline control included)")
    print()

    result = runner.sweep(world, space)
    print(f"Sweep id      {result.sweep_id}")
    print()

    print("BASELINE (control)")
    print(f"  {result.base.run_id}  {_fmt(result.base.metrics)}")
    print()

    print(f"VARIANTS (generation order: {result.n_executed} executed)")
    for i, variant in enumerate(result.variants, start=1):
        mutations = "; ".join(m.display() for m in variant.mutations)
        print(f"  {i:>2}. {variant.run_id}  [{mutations}]")
        print(f"      {_fmt(variant.metrics)}")
    print()

    if result.timing.n_skipped:
        print(f"(skipped {result.timing.n_skipped} no-op combination(s) identical to baseline)")
    print(
        f"TIMING  planned={result.timing.n_planned} executed={result.timing.n_executed} "
        f"total={result.timing.total_seconds:.2f}s "
        f"mean={result.timing.mean_seconds:.2f}s"
    )
    print()

    print(f"RANKING by {args.rank_by} ({'ascending' if args.ascending else 'descending'})")
    for entry in result.ranking(args.rank_by, descending=not args.ascending):
        marker = " (baseline)" if entry.kind == "baseline" else ""
        print(f"  {entry.rank:>2}. {entry.run_id}  {entry.value:.6g}  {entry.kind}{marker}")
    print()

    print("LINEAGE")
    print(f"  Base    {result.base.run_id}")
    for variant in result.variants:
        print(f"   +-- variant {variant.run_id}")
    print(f"\nPersisted to SQLite: {db_path}  (runs={store.run_count}, sweeps={store.sweep_count})")


if __name__ == "__main__":
    main()