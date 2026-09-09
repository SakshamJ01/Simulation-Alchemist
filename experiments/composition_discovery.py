"""Task 2.4 Stage 5: cross-composition discovery figures.

The generic core stays matplotlib-free; this experiment-facing module owns the
single quality-vs-diversity artifact.  It only *reads* Stage 4 results
(``CompositionAnalysisResult`` ranking rows, frontier membership, and the
per-composition isolation map): every plotted quantity is taken from the
analysis, never recomputed here.

``composition_labels`` maps the three canonical composition ids to their
human-readable experiment labels (A / B / C) via ``template_composition_id``,
so both the fast (``--steps 2``) and the canonical (160-step) runs label the
same compositions.

The figure is entirely deterministic: panels follow the analysis order, the
points within a panel are sorted by (label, composition id), and all plotted
values come from the analysis result.  No pixel tests are performed anywhere
in the suite; tests assert point counts, ordering, and membership instead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim_alchemist.core import CompositionAnalysisResult

from chemomech.coupling import build_morphogenesis_template
from experiments.field_guided_movers.coupling import (
    build_field_guided_movers_template,
)
from experiments.network_morphogenesis.coupling import (
    build_network_morphogenesis_template,
)
from sim_alchemist.core import template_composition_id

__all__ = ["composition_labels", "make_diversity_scatter"]


def composition_labels() -> dict[str, str]:
    """The three canonical composition ids -> experiment labels (A/B/C)."""
    labels: dict[str, str] = {}
    for label, build in (
        ("A", build_morphogenesis_template),
        ("B", build_field_guided_movers_template),
        ("C", build_network_morphogenesis_template),
    ):
        labels[template_composition_id(build())] = label
    return labels


def _scatter_data(
    analysis: CompositionAnalysisResult,
    labels: Mapping[str, str],
) -> tuple[list[dict], set[str]]:
    """Points (score, isolation, label, frontier member?) in stable order."""
    frontier_members = set(analysis.frontier.member_ids())
    isolation = analysis.frontier.isolation
    points: list[dict] = []
    for row in analysis.ranking.rows:
        points.append(
            {
                "composition_id": row.composition_id,
                "score": row.score,
                "isolation": isolation.get(row.composition_id, 0.0),
                "label": labels.get(row.composition_id, row.composition_id),
            }
        )
    points.sort(key=lambda p: (p["label"], p["composition_id"]))
    return points, frontier_members


def make_diversity_scatter(
    analyses: Sequence[CompositionAnalysisResult],
    out_path: Path,
    labels: Mapping[str, str] | None = None,
    *,
    dpi: int = 130,
) -> None:
    """ONE figure: one panel per analysis, quality score vs pool isolation.

    x = the profile's ranking score; y = the composition's minimum normalized
    behavioral distance to any other evaluated composition (the Stage 4
    ``isolation`` map).  Frontier members are drawn with a star marker; every
    evaluated composition gets exactly one labelled point.  Every value is
    read from the analysis result -- nothing is recalculated here.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not analyses:
        raise ValueError("no analyses to draw")
    labels = labels or {}
    n_panels = len(analyses)
    fig, axes = plt.subplots(
        1, n_panels, figsize=(5.4 * n_panels, 4.6), squeeze=False
    )
    for ax, analysis in zip(axes[0], analyses):
        points, frontier_members = _scatter_data(analysis, labels)
        for point in points:
            member = point["composition_id"] in frontier_members
            ax.scatter(
                [point["score"]],
                [point["isolation"]],
                marker="*" if member else "o",
                s=170 if member else 60,
                color="C1" if member else "C0",
                alpha=0.85,
                zorder=3 if member else 1,
            )
            ax.annotate(
                point["label"],
                (point["score"], point["isolation"]),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=8,
            )
        ax.set_xlabel("profile quality score")
        ax.set_ylabel("min normalized behavioral distance\n(any other composition)")
        ax.set_title(
            f"{analysis.profile.name}  (frontier: {len(frontier_members)}/"
            f"{len(points)} selected)"
        )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)