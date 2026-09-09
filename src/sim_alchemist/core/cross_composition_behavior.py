"""Cross-composition sweep behavior aggregation (Task 2.5 Stage 3).

Pure projection of completed Stage 2 sweep results onto a common-observable
surface.  No simulation, no execution, no ranking, no persistence.

Input: the result of a completed ``CrossCompositionSweep``
(``CrossCompositionSweepResult``) optionally with its ``LineageStore``
for metric extraction.  Output: ``CrossCompositionBehaviorResult`` with
one ``CrossCompositionObservation`` per executed run (baseline + variants),
distinguishing composition / sweep / run identity, preserving baseline vs
variant semantics, and deriving the common-observable vocabulary from actual
metric names produced by the executed pool.

The module reuses ``CommonObservable`` / ``CommonObservableSet`` from the
Task 2.4 common-observable layer (``core/observables.py``) without altering
that layer.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.cross_sweep import CrossCompositionSweepResult, CompositionSpaceBinding
from sim_alchemist.core.lineage import LineageStore
from sim_alchemist.core.observables import CommonObservable, CommonObservableSet

__all__ = [
    "CrossCompositionObservation",
    "CrossCompositionBehaviorResult",
    "aggregate_sweep_behavior",
]


class CrossCompositionBehaviorError(ValueError):
    """Stage 3 aggregation could not be completed over the given sweep result."""


@dataclass(frozen=True)
class CrossCompositionObservation:
    """One executed run (baseline or variant) reduced to common observables.

    Preserves the full structural identity from Stage 2 so that Stage 4
    can compare compositions on the same observable surface without losing
    which observation came from which parameter child.
    """

    composition_id: str
    sweep_id: str | None
    run_id: str
    baseline: bool
    mutation_ref: str | None  # parameter path for C variants; None for A/B/baseline
    common_observables: tuple[CommonObservable, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "sweep_id": self.sweep_id,
            "run_id": self.run_id,
            "baseline": self.baseline,
            "mutation_ref": self.mutation_ref,
            "common_observables": [
                obs.as_dict() for obs in self.common_observables
            ],
        }


@dataclass(frozen=True)
class CrossCompositionBehaviorResult:
    """The aggregated common-observable view over one completed sweep pass.

    ``vocabulary`` = genuinely common metric names (intersection of available
    names across observations); ``union_vocabulary`` = full sorted union.
    Both are derived deterministically from the actual executed pool, never
    from a fixed hardcoded list.
    """

    cross_split_sweep_id: str
    observations: tuple[CrossCompositionObservation, ...]
    vocabulary: tuple[str, ...]
    union_vocabulary: tuple[str, ...]
    timing: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(
            self, "vocabulary", tuple(sorted(set(self.vocabulary)))
        )
        object.__setattr__(
            self, "union_vocabulary", tuple(sorted(set(self.union_vocabulary)))
        )

    def observation_for(self, composition_id: str) -> tuple[CrossCompositionObservation, ...]:
        return tuple(
            o for o in self.observations if o.composition_id == composition_id
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cross_split_sweep_id": self.cross_split_sweep_id,
            "observations": [o.as_dict() for o in self.observations],
            "vocabulary": list(self.vocabulary),
            "union_vocabulary": list(self.union_vocabulary),
            "timing": (
                self.timing.as_dict()
                if hasattr(self.timing, "as_dict")
                else self.timing
            ),
        }


def _build_observable_set(
    metrics: dict[str, float],
) -> tuple[CommonObservable, ...]:
    """Build one sorted tuple of CommonObservable from a metrics dict."""
    rows: list[CommonObservable] = []
    for name in sorted(metrics):
        rows.append(CommonObservable(name=name, value=metrics[name], available=True))
    return tuple(rows)


def aggregate_sweep_behavior(
    sweep_result: CrossCompositionSweepResult,
    store: LineageStore | None = None,
) -> CrossCompositionBehaviorResult:
    """Pure projection of a completed Stage 2 sweep onto common observables.

    Reads metrics from ``store`` (lineage) when available; raises
    ``CrossCompositionBehaviorError`` if any required identity or metric
    is missing.  No simulation executes.  No database is written.
    """
    if sweep_result.state != "executed":
        raise CrossCompositionBehaviorError(
            "Sweep result is not executed (state must be 'executed')"
        )
    observations: list[CrossCompositionObservation] = []
    # Vocabulary is derived dynamically from actual names produced.
    union_names: set[str] = set()
    available_per_obs: list[set[str]] = []
    # Process bindings in canonical catalog order (already ordered in result).
    for binding in sweep_result.bindings:
        cid = binding.composition_id
        sweep_id = binding.sweep_id
        # Baseline observation (root control) — always present for executable.
        baseline_run_id = binding.baseline_run_id
        if baseline_run_id is None:
            raise CrossCompositionBehaviorError(
                f"binding for {cid} has no baseline_run_id"
            )
        # Read metrics from lineage if available; otherwise metrics must be
        # embedded in some future extension; for Stage 3 we require store.
        metrics: dict[str, float] = {}
        if store is not None:
            rec = store.get_run(baseline_run_id)
            if rec is not None and rec.metrics is not None:
                metrics = dict(rec.metrics)
        # Build observable set for baseline.
        baseline_obs = _build_observable_set(metrics)
        observations.append(
            CrossCompositionObservation(
                composition_id=cid,
                sweep_id=sweep_id,
                run_id=baseline_run_id,
                baseline=True,
                mutation_ref=None,
                common_observables=baseline_obs,
            )
        )
        union_names.update(metrics)
        available_per_obs.append({name for name in metrics})
        # Variant observations for swept compositions.
        for variant_run_id in binding.variant_run_ids:
            vmetrics: dict[str, float] = {}
            if store is not None:
                vrec = store.get_run(variant_run_id)
                if vrec is not None and vrec.metrics is not None:
                    vmetrics = dict(vrec.metrics)
            variant_obs = _build_observable_set(vmetrics)
            observations.append(
                CrossCompositionObservation(
                    composition_id=cid,
                    sweep_id=sweep_id,
                    run_id=variant_run_id,
                    baseline=False,
                    mutation_ref=None,  # Stage 3 preserves identity only;
                                       # parameter path kept in binding.ref
                                       # for experiment-local reference.
                    common_observables=variant_obs,
                )
            )
            union_names.update(vmetrics)
            available_per_obs.append({name for name in vmetrics})
    # Derive vocabulary from what was actually produced across all observations.
    genuinely_common = set.intersection(*available_per_obs) if available_per_obs else set()
    vocabulary = tuple(sorted(genuinely_common))
    union_vocabulary = tuple(sorted(union_names))
    return CrossCompositionBehaviorResult(
        cross_split_sweep_id=sweep_result.cross_split_sweep_id,
        observations=tuple(observations),
        vocabulary=vocabulary,
        union_vocabulary=union_vocabulary,
    )
