"""Task 2.3 (Build Stage 3+4+5) demonstration: coupling templates + catalog.

Builds the repository composition catalog over the five-binding universe
(mesa / network / py-pde / pymunk-walls / pymunk-movers) and classifies all
23 shapes (k = 1..4) through the executable taxonomy:

    capability filter -> CouplingTemplate registry -> coupling contracts
        -> schedule -> clock -> EXECUTABLE

Every decision is reachable: each candidate carries its shape identity, its
taxonomy status, the reasons (missing capabilities, or the "no declared
template" verdict), the matched template and composition id (executable
candidates), and -- with ``--generate-worlds`` -- the generated declarative
``WorldDefinition`` of the three executable compositions.

Usage::

    uv run python run_catalog_demo.py [--generate-worlds [--worlds-dir DIR]]

Nothing is simulated: classification only ever *constructs* adapters (to read
constructor metadata) and never initializes or steps them.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from experiments.catalog import (
    build_repository_catalog,
    repository_bindings,
)


def _label_binding(binding) -> str:
    return f"{binding.component}/{binding.variant}" if binding.variant else binding.component


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulation Alchemist composition catalog demo")
    parser.add_argument(
        "--generate-worlds",
        action="store_true",
        help="also generate the WorldDefinition of every EXECUTABLE candidate",
    )
    parser.add_argument(
        "--worlds-dir",
        default="generated_worlds",
        help="directory to serialize the generated worlds into (with --generate-worlds)",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("Task 2.3 Build Stage 3+4+5 - composition catalog")
    print("=" * 78)

    print("\ncomposition universe (5 bindings, deterministic order):")
    for i, binding in enumerate(repository_bindings(), start=1):
        print(f"  {i}. {_label_binding(binding)}")

    start = time.perf_counter()
    catalog = build_repository_catalog(generate_worlds=args.generate_worlds)
    elapsed = time.perf_counter() - start

    counts = catalog.status_counts()
    print(f"\n23 shapes classified in {elapsed:.3f}s (constructor-only; nothing stepped):")
    for status, count in counts.items():
        print(f"  {count:>2} x {status}")
    print(f"  {len(catalog.executable()):>2} x EXECUTABLE -> composable worlds")

    print("\nexecutable compositions (the three experiment worlds):")
    for candidate in catalog.executable():
        print(candidate.explain())
        print()

    print("example held-back shapes (capability-valid but not declared):")
    for candidate in catalog.by_status("COUPLING_UNAVAILABLE"):
        bindings = " + ".join(_label_binding(b) for b in candidate.bindings)
        print(f"  {bindings}: {candidate.reason}")

    print(f"\n{len(catalog.by_status('CAPABILITY_INVALID'))} capability-invalid "
          f"shapes are filtered before any template is consulted.")

    if args.generate_worlds:
        worlds_dir = Path(args.worlds_dir)
        worlds_dir.mkdir(parents=True, exist_ok=True)
        for candidate in catalog.executable():
            assert candidate.generated_world is not None
            path = worlds_dir / f"{candidate.template}.yaml"
            candidate.generated_world.to_yaml(path)
            print(f"generated world -> {path}")


if __name__ == "__main__":
    main()