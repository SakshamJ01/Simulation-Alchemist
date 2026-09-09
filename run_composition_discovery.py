"""Task 2.4 Stages 4+5 demonstration: cross-composition discovery.

Runs ONE deterministic discovery search over the three canonical repository
compositions (A/B/C), then analyzes the already-evaluated pool through the
Stage 4 ranking + frontier layer under two explicit profiles, and renders the
single quality-vs-diversity artifact.

Order of operations (all generic core, no experiment knowledge here):

    SEARCH (Stage 2/3) -> ANALYZE x2 (Stage 4) -> FIGURE (Stage 5)

The search uses ``CompositionSearcher`` over the 23-shape repository catalog:
every ``EXECUTABLE`` composition (A, B, C) is evaluated exactly once as a
baseline and reduced to a common-observable envelope.  Stage 4 then joins the
three envelopes under one shared vocabulary -- only observables genuinely
available in *every* composition (final_field_mean, final_field_std,
field_entropy) -- ranks them with ``rank_by_profile`` (pool-level min-max,
weight/direction scoring) and selects the behaviorally diverse frontier with
``select_diverse_frontier``.  Stage 5 renders quality vs diversity with the
frontier highlighted.

Profiles (explicit, defensible, no learned weights):

    Profile A "structural_quality"  -- quality-focused:
        final_field_std   max  x1.0
        field_entropy     min  x0.5
        final_field_mean  max  x0.25
    Profile B "field_level"  -- alternative:
        final_field_mean  max  x1.0
        final_field_std   min  x0.5
        field_entropy     min  x0.25

Usage::

    uv run python run_composition_discovery.py                 # canonical 160 steps
    uv run python run_composition_discovery.py --steps 2 --no-figure  # fast check
    uv run python run_composition_discovery.py --beam-width 2 \\
        --figure figures/discovery_quality_diversity.png

The whole CLI is deterministic: with identical arguments the printed report
(except the explicitly labelled timing line) and the figure are reproducible.
"""

from __future__ import annotations

import argparse
import dataclasses
import tempfile
from pathlib import Path

from chemomech.coupling import build_morphogenesis_template
from experiments.catalog import (
    build_repository_adapters,
    repository_bindings,
    repository_executors,
    repository_surfaces,
)
from experiments.composition_discovery import (
    composition_labels,
    make_diversity_scatter,
)
from experiments.field_guided_movers.coupling import (
    build_field_guided_movers_template,
)
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_template,
)
from sim_alchemist.core import (
    CompositionAnalysisResult,
    CompositionAnalyst,
    CompositionCatalog,
    CompositionSearcher,
    CompositionSearchSpec,
    CompositionSpace,
    CouplingTemplateRegistry,
    InterestingnessProfile,
    LineageStore,
)

PROFILE_A = InterestingnessProfile(
    name="structural_quality",
    description="quality-focused: patterned, low-entropy, strong fields",
    weights={"final_field_std": 1.0, "field_entropy": 0.5, "final_field_mean": 0.25},
    directions={"final_field_std": True, "field_entropy": False, "final_field_mean": True},
)

PROFILE_B = InterestingnessProfile(
    name="field_level",
    description="alternative: high overall field level with mild spread",
    weights={"final_field_mean": 1.0, "final_field_std": 0.5, "field_entropy": 0.25},
    directions={"final_field_mean": True, "final_field_std": False, "field_entropy": False},
)


def _fast_template(template, *, steps: int):
    return dataclasses.replace(
        template,
        max_steps=steps,
        config={**dict(template.config), "n_steps": steps},
    )


def _catalog(*, steps: int | None) -> CompositionCatalog:
    """The three-template repository catalog; ``steps`` bounds the worlds.

    ``composition_id`` ignores ``max_steps``/``config``, so the executable
    composition ids are identical for fast (``--steps 2``) and canonical
    (160-step) runs.
    """
    registry = CouplingTemplateRegistry()
    for build in (
        build_morphogenesis_template,
        build_field_guided_movers_template,
        build_network_morphogenesis_template,
    ):
        template = build()
        if steps is not None:
            template = _fast_template(template, steps=steps)
        registry.register(template)
    return CompositionCatalog(
        CompositionSpace(
            name="repository",
            universe=repository_bindings(),
            min_size=1,
            max_size=4,
        ),
        repository_surfaces(),
        registry,
        build_adapters=build_repository_adapters,
        generate_worlds=True,
    )


def _specline(profile: InterestingnessProfile) -> str:
    parts = []
    for feature in sorted(profile.weights):
        direction = "max" if profile.direction(feature) else "min"
        parts.append(f"{feature}:{profile.weights[feature]:g}:{direction}")
    return ", ".join(parts)


def _print_ranking(analysis: CompositionAnalysisResult, labels: dict[str, str]) -> None:
    print("  RANKING  (common observables, pool min-max, ties by run id ascending)")
    for row in analysis.ranking.rows:
        label = labels.get(row.composition_id, row.composition_id)
        print(
            f"    {row.rank:>2}. {label}  {row.composition_id}  "
            f"score={row.score:.6g}"
        )


def _print_frontier(analysis: CompositionAnalysisResult, labels: dict[str, str]) -> None:
    print(
        f"  FRONTIER  (selection q={analysis.frontier.selection.quality_weight:g} "
        f"d={analysis.frontier.selection.diversity_weight:g}, "
        f"beam={analysis.frontier.beam_width})"
    )
    for member in analysis.frontier.members:
        label = labels.get(member.composition_id, member.composition_id)
        print(
            f"    {member.composition_id}  {label}  rank={member.rank}  "
            f"score={member.quality_score:.6g}  "
            f"div={member.diversity_score:.6g}  "
            f"combined={member.combined_score:.6g}  "
            f"[{member.selection_reason}]"
        )


def _print_explanation(analysis: CompositionAnalysisResult, labels: dict[str, str]) -> None:
    if not analysis.ranking.rows:
        print("  EXPLANATION  (no evaluated compositions)")
        return
    top = analysis.ranking.rows[0]
    label = labels.get(top.composition_id, top.composition_id)
    print(f"  WHY  ({label} / {top.composition_id}, rank {top.rank})")
    print("\n".join(f"    {line}" for line in top.explanation))


def _print_analysis(
    analysis: CompositionAnalysisResult,
    labels: dict[str, str],
    *,
    header: str,
) -> None:
    print()
    print(f"=== {header}: {analysis.profile.name} ===")
    print(f"  Analysis id  {analysis.analysis_id}")
    print(f"  Profile      {_specline(analysis.profile)}")
    print(
        f"  Frontier     {len(analysis.frontier.members)} selected / "
        f"{len(analysis.ranking.rows)} evaluated  "
        f"signatures={analysis.frontier.diagnostics.n_unique_signatures}  "
        f"mean pairwise dist={analysis.frontier.diagnostics.mean_pairwise_distance:.4g}"
    )
    _print_ranking(analysis, labels)
    _print_frontier(analysis, labels)
    _print_explanation(analysis, labels)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--steps",
        type=int,
        default=None,
        help="macro-steps per composition (None = canonical 160; e.g. 2 for a "
             "fast check)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="deterministic replay key (default 0)",
    )
    parser.add_argument(
        "--db", default=None,
        help="SQLite lineage file (default: a fresh temporary file)",
    )
    parser.add_argument(
        "--quality-weight", type=float, default=1.0,
        help="frontier weight on profile quality (default 1.0)",
    )
    parser.add_argument(
        "--diversity-weight", type=float, default=1.0,
        help="frontier weight on behavioral distance (default 1.0)",
    )
    parser.add_argument(
        "--beam-width", type=int, default=None,
        help="frontier size (default: the whole evaluated pool)",
    )
    parser.add_argument(
        "--profile", choices=("all", "a", "b"), default="all",
        help="which explicit profiles to analyze (default all)",
    )
    parser.add_argument(
        "--figure", default="figures/discovery_quality_diversity.png",
        help="matplotlib artifact path (quality vs diversity)",
    )
    parser.add_argument(
        "--no-figure", action="store_true",
        help="skip figure rendering (pure text report)",
    )
    args = parser.parse_args(argv)

    if args.quality_weight < 0 or args.diversity_weight < 0:
        raise SystemExit("quality/diversity weights must be non-negative")
    if args.beam_width is not None and args.beam_width <= 0:
        raise SystemExit("--beam-width must be a positive integer")

    labels = composition_labels()
    catalog = _catalog(steps=args.steps)
    executable = catalog.executable()
    if len(executable) != 3:
        raise SystemExit(f"expected 3 executable compositions, got {len(executable)}")

    db_path = args.db or str(Path(tempfile.gettempdir()) / "discovery_lineage.db")
    store = LineageStore(db_path)
    spec = CompositionSearchSpec(profile=PROFILE_A, seed=args.seed, evaluation_config=None)
    searcher = CompositionSearcher(catalog, repository_executors(), store)
    result = searcher.search(spec)
    run_count = store.run_count
    store.close()

    horizon = args.steps if args.steps is not None else 160
    print(f"Cross-composition discovery  ({horizon} macro-steps, seed {args.seed})")
    print(f"Discovery id     {result.discovery_id}")
    print(f"Catalog          {len(catalog.all())} shapes, "
          f"{len(executable)} EXECUTABLE ({', '.join(sorted(labels.values()))})")
    if result.observable_sets:
        common = set(result.observable_sets[0].available_names)
        for other in result.observable_sets[1:]:
            common &= set(other.available_names)
        print("Common observables (genuinely common across every composition)")
        print("  " + ", ".join(sorted(common)))
    else:
        print("Common observables  (none evaluated)")

    analyst = CompositionAnalyst()
    analyses = []
    for profile in (PROFILE_A, PROFILE_B):
        if args.profile == "a" and profile is PROFILE_B:
            continue
        if args.profile == "b" and profile is PROFILE_A:
            continue
        analysis = analyst.analyze(
            result,
            profile,
            quality_weight=args.quality_weight,
            diversity_weight=args.diversity_weight,
            beam_width=args.beam_width,
        )
        analyses.append(analysis)
        _print_analysis(
            analysis,
            labels,
            header="PROFILE A" if profile is PROFILE_A else "PROFILE B",
        )

    print()
    print("TIMING  (wall-clock; excluded from canonical identity)")
    t = result.timing
    print(
        f"  discovery: evaluation={t.evaluation_seconds:.2f}s "
        f"extraction={t.observation_seconds:.3f}s total={t.total_seconds:.2f}s "
        f"per-composition={t.mean_seconds:.2f}s"
    )
    for analysis in analyses:
        at = analysis.timing
        print(
            f"  {analysis.profile.name}: extraction={at.extraction_seconds:.4f}s "
            f"ranking={at.ranking_seconds:.4f}s frontier={at.frontier_seconds:.4f}s "
            f"analysis-total={at.total_seconds:.4f}s"
        )

    if not args.no_figure:
        make_diversity_scatter(analyses, Path(args.figure), labels)
        print(f"FIGURE           {args.figure}")
    else:
        print("FIGURE           (skipped by --no-figure)")
    print(f"Persisted to    {db_path}  (runs={run_count})")


if __name__ == "__main__":
    main()