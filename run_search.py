"""Task 1.9 demonstration: guided simulation search (deterministic beam search).

Loads an experiment world from its declarative YAML, declares a mutation
space and an explicit ``InterestingnessProfile``, and runs the first
*discovery loop* of the framework through the generic ``SearchRunner``:

    GENERATE -> RUN -> ANALYZE -> SELECT -> (repeat)

Generation 0 executes the unmutated base world as the control; every later
generation mutates the current beam (the ``beam_width`` most interesting known
worlds), runs the unique children, and keeps the most interesting frontier.
The whole loop is deterministic: same world + spec + mutation space + profile
+ seed reproduce the identical candidates, generations, scores, and ranking.
A beam search is a bounded heuristic -- it never claims global optimality, it
only reports the most interesting behavior among the worlds actually tried.

Usage examples::

    uv run python run_search.py \\
        --dim components.network.config.loss:0.05,0.08,0.11,0.14 \\
        --dim config.force_fmax:0.4,0.8 \\
        --feature wall_count:activity_rate:0.4:max \\
        --feature field_mean:oscillation_strength:0.3:max \\
        --feature network_load_max:late_vs_full_variance_ratio:0.3:min \\
        --generations 3 --beam-width 2 --children 3

Use ``--steps N`` to control run length (default 10 macro-steps for a fast
local demonstration; 160 matches the canonical regression) and ``--db PATH``
to persist the lineage + search metadata to a SQLite file.
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
    InterestingnessProfile,
    LineageStore,
    MutationSpace,
    ParameterSweep,
    SearchRunner,
    SearchSpec,
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


def _save_figure(result, path: Path, profile_name: str) -> None:
    """One deterministic figure: final score vs generation, frontier + best.

    The frontier at generation ``g`` is the best *final-scoring* candidate
    among that generation's selected beam; the overall best candidate is
    highlighted.  Scores come from the final global ranking (the profile's
    normalization over every evaluated world), so all plotted y values are
    on the same scale.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gens = result.generations
    frontier_x: list[int] = []
    frontier_y: list[float] = []
    cand_x: list[int] = []
    cand_y: list[float] = []
    best = result.best()
    for g in gens:
        for cid in g.selected_candidate_ids:
            cand = result.candidate(cid)
            if cand is None or cand.score is None:
                continue
            cand_x.append(g.generation)
            cand_y.append(cand.score)
        selected = [result.candidate(cid) for cid in g.selected_candidate_ids]
        scored = sorted(
            (c for c in selected if c is not None and c.score is not None),
            key=lambda c: (-c.score, c.run_id),
        )
        if scored:
            frontier_x.append(g.generation)
            frontier_y.append(scored[0].score)

    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.scatter(cand_x, cand_y, marker="o", s=40, alpha=0.6, label="evaluated candidates")
    ax.plot(frontier_x, frontier_y, marker="o", color="C1", label="best of kept beam")
    if best is not None and best.score is not None:
        ax.scatter(
            [best.generation], [best.score],
            marker="*", s=260, color="C3", zorder=5, label=(
                f"best: {best.candidate_id} (score {best.score:.4g})"
            ),
        )
        ax.annotate(
            best.candidate_id,
            (best.generation, best.score),
            textcoords="offset points", xytext=(8, 6), fontsize=8,
        )
    ax.set_xlabel("generation")
    ax.set_ylabel("final interestingness score")
    ax.set_title(f"{profile_name}: guided beam search (score vs generation)")
    ax.legend(fontsize=8)
    ax.set_xticks(list(range(len(gens))))
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--world", default="worlds/adaptive_network.yaml",
        help="path to the declarative world YAML (default adaptive_network.yaml)",
    )
    parser.add_argument(
        "--dim", action="append", required=True,
        help="search dimension 'path:value1,value2,...' (repeatable)",
    )
    parser.add_argument(
        "--feature", action="append", required=True,
        help="profile feature 'feature:weight[:min|max]'",
    )
    parser.add_argument(
        "--generations", type=int, default=3,
        help="beam-expansion steps after generation 0 (default 3)",
    )
    parser.add_argument(
        "--beam-width", type=int, default=2,
        help="worlds kept per generation (default 2)",
    )
    parser.add_argument(
        "--children", type=int, default=3,
        help="child mutation sets generated per surviving parent (default 3)",
    )
    parser.add_argument(
        "--name", default="guided-search",
        help="search label (encoded into the search id)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="deterministic replay key for the search record (default 0)",
    )
    parser.add_argument(
        "--steps", type=int, default=10,
        help="number of macro-steps (default 10 for a fast demo; 160 = canonical)",
    )
    parser.add_argument(
        "--db", default=None,
        help="SQLite lineage file (default: a fresh temporary file)",
    )
    parser.add_argument(
        "--figure", default="figures/search_beam_scores.png",
        help="matplotlib artifact path (score vs generation)",
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
        name=args.name,
        description="explicit profile from --feature flags (no learned weights)",
        weights=weights,
        directions=directions,
    )
    spec = SearchSpec(
        name=args.name,
        generations=args.generations,
        beam_width=args.beam_width,
        children_per_parent=args.children,
        mutation_space=space,
        profile=profile,
        seed=args.seed,
    )

    db_path = args.db or str(Path(tempfile.gettempdir()) / "search_lineage.db")
    store = LineageStore(db_path)
    runner = SearchRunner(
        store,
        run_network_world,
        lambda outcome: build_network_observables(outcome.trajectory),
        parameter_specs=specs_by_path(),
    )

    print(f"Guided simulation search ({world.id}, {args.steps} macro-steps)")
    print(f"Mutation space: {space.to_dict()['dimensions']}")
    print(f"Beam search: {spec.generations} generations, beam {spec.beam_width}, "
          f"{spec.children_per_parent} children per parent")
    print(f"Profile: {weights}")
    print()

    result = runner.search(world, spec)
    print(f"Search id     {result.search_id}")
    print(f"Base world    {world_hash(result.world)}")
    print()

    print("GENERATIONS (parents -> children -> kept beam, best first)")
    for g in result.generations:
        label = "root control" if g.generation == 0 else ""
        best = (
            f"  best {g.best_candidate_id} score={g.best_score:.6g}"
            if g.best_candidate_id is not None and g.best_score is not None else ""
        )
        print(
            f"  gen {g.generation}  "
            f"kept={list(g.selected_candidate_ids)}  "
            f"children={len(g.child_candidate_ids)}{best}  {label}"
        )
    print()

    print("FINAL RANKING (all evaluated candidates, ties by run id ascending)")
    for row in result.final_ranking.rows:
        marker = "  (root control)" if row.kind == "baseline" else ""
        best_marker = " <== best" if result.rank_of(
            result.by_run_id(row.run_id).candidate_id
        ) == 1 else ""
        print(f"  {row.rank:>2}. {row.run_id}  score={row.score:.6g}  {row.kind}{marker}{best_marker}")
    print()

    best = result.best()
    print("WHY (best candidate)")
    if best is not None:
        print(
            f"  {best.candidate_id} (run {best.run_id}, generation {best.generation})"
        )
        path = " -> ".join(result.lineage_path(best.candidate_id))
        print(f"  lineage path: {path}")
        mutations = result.mutation_path(best.candidate_id)
        if mutations:
            print("  mutations (" + "; ".join(m.display() for m in mutations) + ")")
    print("\n".join(f"  {ln}" for ln in result.explain_best()))
    print()

    if result.timing.n_skipped:
        print(
            f"(skipped {result.timing.n_skipped} no-op / duplicate generated "
            f"world(s) already seen)"
        )
    t = result.timing
    print(
        f"TIMING  generated={t.n_generated} executed={t.n_executed} "
        f"total={t.total_seconds:.2f}s exec={t.execution_seconds:.2f}s "
        f"analysis={t.analysis_seconds:.2f}s mean={t.mean_seconds:.2f}s"
    )

    _save_figure(result, Path(args.figure), profile.name)
    print(f"Figure     {args.figure}")

    print("LINEAGE")
    print(f"  Root    {result.root.run_id}  (baseline control)")
    print(
        f"\nPersisted to SQLite: {db_path}  "
        f"(runs={store.run_count}, searches={store.search_count})"
    )


if __name__ == "__main__":
    main()