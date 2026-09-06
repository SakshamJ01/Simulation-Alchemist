"""Task 1.6 demonstration: one base run, one mutation, one variant run, lineage.

Loads Experiment C (Adaptive Network Morphogenesis) from its declarative YAML
world, executes the *unmodified* base world, applies one meaningful mutation
(network diffusion ``loss`` 0.05 -> 0.14), executes the variant through the
same generic executor, and prints the real measured metrics, the metric
deltas, and the parent/child lineage records from the SQLite store.

Use ``--steps N`` to control the run length (default 10 macro-steps for a
fast local demonstration; 160 matches the canonical regression).
"""

from __future__ import annotations

import argparse
import dataclasses

from experiments.network_morphogenesis.experiment import (
    run_network_world,
    specs_by_path,
)
from sim_alchemist.core import (
    LineageStore,
    Mutation,
    VariantRunner,
    compare_metrics,
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--steps", type=int, default=10,
        help="number of macro-steps (default 10 for a fast demo; 160 = canonical)",
    )
    args = parser.parse_args(argv)

    world = load_world_yaml("worlds/adaptive_network.yaml")
    if args.steps != 160:
        world = dataclasses.replace(
            world, max_steps=args.steps, config={**world.config, "n_steps": args.steps}
        )

    store = LineageStore(":memory:")
    runner = VariantRunner(store, run_network_world, parameter_specs=specs_by_path())

    mutation = Mutation("components.network.config.loss", 0.14)
    base = runner.run(world)
    variant = runner.run_variant(world, mutation)
    deltas = compare_metrics(base.metrics, variant.metrics)

    print(f"Adaptive Network Morphogenesis mutation demo ({args.steps} macro-steps)")
    print()
    print("BASE (unmutated)")
    print(" ", _fmt(base.metrics))
    print()
    print("VARIANT")
    print(f"   {variant.mutations[0].display()}")
    print(" ", _fmt(variant.metrics))
    print()
    print("DIFFERENCE")
    for name, delta in deltas.items():
        print(
            f"  {name:>18}  {delta.base:+.6f} -> {delta.variant:+.6f}  ({delta.absolute:+.6f})"
        )
    print()
    print("LINEAGE")
    print("Base")
    print(f"  {base.run_id}  (world '{base.world.id}', seed {base.seed})")
    for record in store.children_of(base.run_id):
        which = "Variant-001" if record.run_id == variant.run_id else "Variant-???"
        print(f"   +-- {which}  {record.run_id}")
        for m in record.mutations:
            print(f"       mutation: {m.display()}")


if __name__ == "__main__":
    main()