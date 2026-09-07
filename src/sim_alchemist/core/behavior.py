"""Generic behavioral characterization and interestingness (Task 1.8).

A simulation produces *observables*: named scalar time-series sampled on an
explicit time axis (wall count, mean field value, ...).  This module turns
those series into a compact, inspectable **behavioral feature vector**, then
ranks a population of runs against an explicit, human-readable
**interestingness profile**.

Everything is deterministic, stdlib-only, and experiment-free:

* ``ObservableSeries`` -- the minimal series contract (name, times, values);
* ``BehaviorAnalyzer`` -- per-series feature extraction with precise,
  documented formulas (temporal, trend, oscillation, stability, and
  baseline-relative divergence);
* ``BehaviorFeatures`` / ``UnitFeatures`` -- the serializable feature vector;
* ``InterestingnessProfile`` -- explicit feature weights, maximize/minimize
  directions, and deterministic tie-breakers;
* explicit min-max **normalization** across the analyzed population (raw
  features are always preserved);
* ``rank_by_profile`` / ``BehaviorRankingResult`` -- a ranking *built on the
  Task 1.7 contract* (score descending, then run id ascending) with a
  per-feature contribution explanation for every row.

There is no learned weight, no AI, no clustering, and no experiment concept
in this module.  ``interesting`` is never a magic scalar: it is the explicit
profile's score over well-defined features.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sim_alchemist.core.lineage import (
    LineageStore,
    RunRecord,
    _now_iso,
    run_id_of,
    world_hash,
)
from sim_alchemist.core.mutation import (
    Mutation,
    MutationRecord,
    ParameterSpec,
    apply_mutations,
)
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.sweep import MutationSpace
from sim_alchemist.core.world import WorldDefinition

__all__ = [
    "BehaviorAnalysisRecord",
    "BehaviorAnalysisResult",
    "BehaviorAnalyzer",
    "BehaviorFeatures",
    "BehaviorRankingResult",
    "BehaviorTiming",
    "BehavioralAnalysisRunner",
    "Contribution",
    "FeaturedRun",
    "InterestingnessProfile",
    "ObservableSeries",
    "RankedRow",
    "UnitFeatures",
    "rank_by_profile",
]

_EPS = 1e-12


# ---------------------------------------------------------------------------
# Observable series contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ObservableSeries:
    """One scalar observable over explicit simulation time.

    Contract:

    * ``name`` -- a stable, experiment-chosen identifier;
    * ``times`` -- strictly increasing, finite float times;
    * ``values`` -- finite floats, one per time point;
    * at least one point (empty series are rejected explicitly).

    ``empty``/single-point series are therefore handled predictably: empty
    construction fails loudly, and the analyzer defines every feature for a
    single point (mean = the value, zero spread, zero oscillation).
    """

    name: str
    times: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if isinstance(self.times, list):
            object.__setattr__(self, "times", tuple(self.times))
        if isinstance(self.values, list):
            object.__setattr__(self, "values", tuple(self.values))
        if not self.times:
            raise ValueError("an ObservableSeries needs at least one time point")
        if len(self.times) != len(self.values):
            raise ValueError(
                f"series {self.name!r} has {len(self.times)} times but "
                f"{len(self.values)} values"
            )
        for t in self.times:
            if not math.isfinite(t):
                raise ValueError(f"series {self.name!r} has a non-finite time {t!r}")
        for i, v in enumerate(self.values):
            if not math.isfinite(v):
                raise ValueError(
                    f"series {self.name!r} has a non-finite value {v!r} at index {i}"
                )
        for i in range(1, len(self.times)):
            if not self.times[i - 1] < self.times[i]:
                raise ValueError(
                    f"series {self.name!r} times must be strictly increasing "
                    f"({self.times[i - 1]!r} followed by {self.times[i]!r})"
                )

    @property
    def length(self) -> int:
        return len(self.values)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "times": list(self.times),
            "values": list(self.values),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ObservableSeries:
        return cls(
            name=str(data["name"]),
            times=tuple(float(t) for t in data["times"]),
            values=tuple(float(v) for v in data["values"]),
        )

    def resample_to(self, times: Sequence[float]) -> tuple[float, ...]:
        """Deterministic piecewise-linear resampling onto ``times``.

        Points outside the original range are clamped to the nearest endpoint.
        Used only to align a variant series onto the baseline's time grid.
        """
        if len(self.values) == 1:
            return tuple(float(self.values[0]) for _ in times)
        src_t = self.times
        src_v = self.values
        out: list[float] = []
        for target in times:
            if target <= src_t[0]:
                out.append(float(src_v[0]))
            elif target >= src_t[-1]:
                out.append(float(src_v[-1]))
            else:
                i = 0
                while i + 1 < len(src_t) and src_t[i + 1] < target:
                    i += 1
                hi = i + 1
                f = (target - src_t[i]) / (src_t[hi] - src_t[i])
                out.append(float(src_v[i] + f * (src_v[hi] - src_v[i])))
        return tuple(out)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _std(xs: Sequence[float]) -> float:
    mu = _mean(xs)
    return math.sqrt(max(0.0, sum((x - mu) ** 2 for x in xs) / len(xs)))


def _total_variation(values: Sequence[float]) -> float:
    return sum(
        abs(values[i] - values[i - 1]) for i in range(1, len(values))
    )


def _ls_slope(times: Sequence[float], values: Sequence[float]) -> float:
    """Least-squares slope of ``values`` vs ``times``.

    ``times`` are first normalized onto [0,1], so the slope is in "value per
    full series span" units (independent of the absolute time scale).
    """
    n = len(values)
    if n < 2:
        return 0.0
    span = times[-1] - times[0]
    tau = [0.0 if span == 0 else (t - times[0]) / span for t in times]
    tau_mean = _mean(tau)
    val_mean = _mean(values)
    num = sum((tau[i] - tau_mean) * (values[i] - val_mean) for i in range(n))
    den = sum((tau[i] - tau_mean) ** 2 for i in range(n))
    if den <= _EPS:
        return 0.0
    return num / den


def _fitted_residual_fraction(
    times: Sequence[float], values: Sequence[float]
) -> float:
    """Fraction of variance not explained by the best linear trend.

    0.0 -> the series is (numerically) a straight line; close to 1.0 -> the
    dynamics are dominated by non-trend (oscillatory/erratic) variation.
    """
    n = len(values)
    if n < 2:
        return 0.0
    mu = _mean(values)
    sigma2 = _std(values) ** 2
    if sigma2 <= _EPS:
        return 0.0
    span = times[-1] - times[0]
    slope = _ls_slope(times, values)
    tau = [0.0 if span == 0 else (t - times[0]) / span for t in times]
    intercept = mu - slope * _mean(tau)
    residual = sum(
        (values[i] - (intercept + slope * tau[i])) ** 2 for i in range(n)
    ) / n
    return max(0.0, min(1.0, residual / sigma2))


def _sign_change_rate(values: Sequence[float], dead_zone: float) -> tuple[int, float]:
    """Direction-flip count and rate in the first differences.

    Differences whose magnitude is below ``dead_zone`` are treated as flat
    (no direction); a flip is counted when the sign of consecutive *non-flat*
    differences changes.  The rate is normalized by the maximum possible
    flip count ``n-1`` so it lives in [0, 1].
    """
    n = len(values)
    if n < 2:
        return 0, 0.0
    last_sign = 0
    flips = 0
    for i in range(1, n):
        d = values[i] - values[i - 1]
        if abs(d) < dead_zone:
            continue
        sign = 1 if d > 0 else -1
        if last_sign != 0 and sign != last_sign:
            flips += 1
        last_sign = sign
    return flips, flips / (n - 1)


def _autocorr(xs: Sequence[float]) -> float:
    """Lag-1 autocorrelation of a centered series (None-equivalent -> 0.0).

    Defined only if there is residual variance and at least two samples;
    degenerate inputs map to the documented value 0.0 (no lag structure).
    """
    n = len(xs)
    if n < 2:
        return 0.0
    mu = _mean(xs)
    numer = sum((xs[i] - mu) * (xs[i + 1] - mu) for i in range(n - 1))
    denom = sum((x - mu) ** 2 for x in xs)
    if denom <= _EPS:
        return 0.0
    return max(-1.0, min(1.0, numer / denom))


def _pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Pearson correlation of two aligned series (same order).

    Returns ``None`` when the correlation is mathematically undefined (fewer
    than two points, or zero variance in either series) rather than silently
    reporting a number.
    """
    if len(a) < 2:
        return None
    mu_a, mu_b = _mean(a), _mean(b)
    va = sum((x - mu_a) ** 2 for x in a)
    vb = sum((x - mu_b) ** 2 for x in b)
    if va <= _EPS or vb <= _EPS:
        return None
    cov = sum((a[i] - mu_a) * (b[i] - mu_b) for i in range(len(a)))
    return max(-1.0, min(1.0, cov / math.sqrt(va * vb)))


@dataclass(frozen=True)
class UnitFeatures:
    """Behavioral features of one observable series.

    ``divergence`` holds baseline-relative quantities; each entry is ``None``
    when no baseline comparison is meaningful (e.g. the baseline run itself,
    or an observable the baseline does not expose) -- undefined features are
    reported explicitly, never coerced to zero.
    """

    name: str
    n_points: int
    temporal: Mapping[str, float]
    trend: Mapping[str, float]
    oscillation: Mapping[str, float]
    stability: Mapping[str, float]
    divergence: Mapping[str, float | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n_points": self.n_points,
            "temporal": dict(self.temporal),
            "trend": dict(self.trend),
            "oscillation": dict(self.oscillation),
            "stability": dict(self.stability),
            "divergence": dict(self.divergence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnitFeatures:
        div: dict[str, float | None] = {
            k: (None if v is None else float(v))
            for k, v in data["divergence"].items()
        }
        return cls(
            name=str(data["name"]),
            n_points=int(data["n_points"]),
            temporal={k: float(v) for k, v in data["temporal"].items()},
            trend={k: float(v) for k, v in data["trend"].items()},
            oscillation={k: float(v) for k, v in data["oscillation"].items()},
            stability={k: float(v) for k, v in data["stability"].items()},
            divergence=div,
        )


@dataclass(frozen=True)
class BehaviorFeatures:
    """The serializable feature vector of one run: per-observable units."""

    units: Mapping[str, UnitFeatures]

    def flatten(self) -> dict[str, float | None]:
        """Flat map ``"<observable>:<feature>" -> value`` used by profiles.

        Divergence features may be ``None`` (undefined); those are reported
        explicitly and excluded from scoring.
        """
        out: dict[str, float | None] = {}
        for unit in self.units.values():
            for block in ("temporal", "trend", "oscillation", "stability"):
                for key, value in getattr(unit, block).items():
                    out[f"{unit.name}:{key}"] = float(value)
            for key, value in unit.divergence.items():
                out[f"{unit.name}:{key}"] = None if value is None else float(value)
        return out

    def feature(self, key: str) -> float | None:
        return self.flatten().get(key)

    def as_dict(self) -> dict[str, Any]:
        return {"units": [u.as_dict() for u in self.units.values()]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BehaviorFeatures:
        return cls(
            units={u["name"]: UnitFeatures.from_dict(u) for u in data["units"]}
        )


class BehaviorAnalyzer:
    """Deterministic, per-series feature extraction.

    ``late_window_fraction`` (default 0.3) selects the trailing window used
    by the stability features.  The window rule is explicit: the late window
    is the last ``ceil(fraction * n)`` points (at least 2 when ``n >= 2``),
    and the early window is the first equally-sized block, so
    "early vs late divergence" is well defined for every series.
    """

    def __init__(self, *, late_window_fraction: float = 0.3, dead_zone_rel: float = 1e-6) -> None:
        if not 0.0 < late_window_fraction <= 1.0:
            raise ValueError("late_window_fraction must be in (0, 1]")
        if not 0.0 <= dead_zone_rel < 1.0:
            raise ValueError("dead_zone_rel must be in [0, 1)")
        self.late_window_fraction = late_window_fraction
        self.dead_zone_rel = dead_zone_rel

    def _window_size(self, n: int) -> int:
        if n < 2:
            return n
        return min(n, max(2, math.ceil(self.late_window_fraction * n)))

    def _series_features(
        self, series: ObservableSeries, *, baseline: ObservableSeries | None
    ) -> UnitFeatures:
        t = series.times
        x = series.values
        n = len(x)
        mu = _mean(x)
        sigma = _std(x)
        lo, hi = min(x), max(x)
        rng = hi - lo
        tv = _total_variation(x)
        activity = 0.0 if rng <= _EPS else tv / max(rng, _EPS)

        slope_t = _ls_slope(t, x)
        residual_frac = _fitted_residual_fraction(t, x)

        # Detrended residual: x - (LS line over normalized time).  Used by
        # the oscillation persistence and the reported lag-1 autocorrelation.
        span = t[-1] - t[0]
        tau = [0.0 if span == 0 else (tt - t[0]) / span for tt in t]
        intercept = mu - slope_t * _mean(tau)
        residual = [
            x[i] - (intercept + slope_t * tau[i]) for i in range(n)
        ]

        dead_zone = self.dead_zone_rel * (rng + 1.0)
        _, scr = _sign_change_rate(x, dead_zone)
        lag1 = _autocorr(residual)
        persist = abs(lag1)
        osc = scr * persist

        w = self._window_size(n)
        late = x[n - w : n]
        early = x[0:w]
        late_t = t[n - w : n]
        late_std = _std(late)
        late_slope = _ls_slope(late_t, late)
        late_var_ratio = 0.0 if sigma <= _EPS else (late_std**2) / (sigma**2)
        early_late = 0.0 if sigma <= _EPS else abs(_mean(late) - _mean(early)) / max(sigma, _EPS)

        divergence: dict[str, float | None] = {
            "final_delta": None,
            "rmsd": None,
            "correlation": None,
            "normalized_divergence": None,
        }
        if baseline is not None and baseline.name == series.name:
            aligned = series.resample_to(baseline.times)
            bvalues = baseline.values
            final_delta = aligned[-1] - bvalues[-1]
            rmsd = math.sqrt(
                sum((aligned[i] - bvalues[i]) ** 2 for i in range(len(bvalues)))
                / len(bvalues)
            )
            corr = _pearson(aligned, bvalues)
            bsigma = _std(bvalues)
            nrm = 0.0 if bsigma <= _EPS else rmsd / max(bsigma, _EPS)
            divergence = {
                "final_delta": float(final_delta),
                "rmsd": float(rmsd),
                "correlation": None if corr is None else float(corr),
                "normalized_divergence": float(nrm),
            }

        return UnitFeatures(
            name=series.name,
            n_points=n,
            temporal={
                "mean": mu,
                "std": sigma,
                "range": float(rng),
                "total_variation": float(tv),
                "activity_rate": float(activity),
            },
            trend={
                "trend_slope": float(slope_t),
                "residual_variance_fraction": float(residual_frac),
                "lag1_autocorr": float(lag1),
            },
            oscillation={
                "sign_change_rate": float(scr),
                "oscillation_persistence": float(persist),
                "oscillation_strength": float(osc),
            },
            stability={
                "late_window_std": float(late_std),
                "late_window_slope": float(late_slope),
                "late_vs_full_variance_ratio": float(late_var_ratio),
                "early_vs_late_divergence": float(early_late),
            },
            divergence=divergence,
        )

    def features(
        self,
        observables: Mapping[str, ObservableSeries],
        *,
        baseline: Mapping[str, ObservableSeries] | None = None,
    ) -> BehaviorFeatures:
        """Extract per-observable behavioral features for one run.

        ``baseline`` optionally supplies the reference series so that
        baseline-relative divergence features are computed for every
        observable the baseline exposes.
        """
        units: dict[str, UnitFeatures] = {}
        for name, series in observables.items():
            base_series = baseline.get(name) if baseline is not None else None
            units[name] = self._series_features(series, baseline=base_series)
        return BehaviorFeatures(units=units)


# ---------------------------------------------------------------------------
# Interestingness profile, normalization, and ranking
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InterestingnessProfile:
    """An explicit, human-readable ranking profile.

    ``weights`` maps flat feature keys (``"<observable>:<feature>"``) to a
    non-negative weight.  ``directions`` marks whether a feature should be
    *maximized* (True, default) or *minimized* (False).  Features are
    normalized across the analyzed population (min-max) before weighting, so
    heterogeneous units are comparable; the raw values are always preserved.
    A zero-weight feature never affects the score.
    """

    name: str
    description: str
    weights: Mapping[str, float]
    directions: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a profile needs a non-empty name")
        if not self.weights:
            raise ValueError(f"profile {self.name!r} needs at least one weight")
        for key, weight in self.weights.items():
            if not isinstance(weight, (int, float)):
                raise TypeError(f"weight for {key!r} must be numeric")
            w = float(weight)
            if not math.isfinite(w) or w < 0.0:
                raise ValueError(f"weight for {key!r} must be finite and >= 0")

    def direction(self, key: str) -> bool:
        return self.directions.get(key, True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "weights": dict(self.weights),
            "directions": dict(self.directions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InterestingnessProfile:
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            weights={k: float(v) for k, v in data["weights"].items()},
            directions={k: bool(v) for k, v in data.get("directions", {}).items()},
        )


def _normalize_across(
    raws: Sequence[Mapping[str, float | None]],
) -> list[dict[str, float | None]]:
    """Min-max normalization per feature across the population.

    Documented rules:

    * ``None`` (undefined) values are carried through as ``None`` and never
      injected with a fake number;
    * a feature that is ``None``/missing for *every* run is left ``None``;
    * a constant (zero-range) feature is normalized to 0.0 for every run: it
      carries no ranking information and its contribution is therefore equal
      across the population (harmless for ordering, explicit in the data).
    """
    keys: list[str] = sorted({k for raw in raws for k in raw})
    key_values: dict[str, list[float]] = {}
    for key in keys:
        vals = [raw[key] for raw in raws if raw.get(key) is not None]
        finite = [v for v in vals if v is not None]
        key_values[key] = [float(v) for v in finite]

    out: list[dict[str, float | None]] = []
    for raw in raws:
        norm: dict[str, float | None] = {}
        for key in keys:
            value = raw.get(key)
            if value is None:
                norm[key] = None
                continue
            vals = key_values[key]
            if not vals:
                norm[key] = None
                continue
            lo, hi = min(vals), max(vals)
            if hi - lo <= _EPS:
                norm[key] = 0.0
            else:
                norm[key] = (float(value) - lo) / (hi - lo)
        out.append(norm)
    return out


@dataclass(frozen=True)
class Contribution:
    """One feature's contribution to a run's interestingness score."""

    feature: str
    weight: float
    raw: float | None
    normalized: float | None
    contribution: float

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "feature": self.feature,
            "weight": self.weight,
            "contribution": self.contribution,
        }
        if self.raw is not None:
            out["raw"] = self.raw
        if self.normalized is not None:
            out["normalized"] = self.normalized
        return out


@dataclass(frozen=True)
class RankedRow:
    """One ranked run: identity, score, and per-feature explanation."""

    rank: int
    run_id: str
    kind: str  # "baseline" | "variant" (same vocabulary as Task 1.7)
    score: float
    contributions: Mapping[str, Contribution]
    raw_features: Mapping[str, float | None] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "run_id": self.run_id,
            "kind": self.kind,
            "score": self.score,
            "contributions": {
                k: c.as_dict() for k, c in self.contributions.items()
            },
            "raw_features": dict(self.raw_features),
        }

    def explanation(self, *, top: int | None = None) -> list[str]:
        """Human-readable lines describing *why* this run ranked this way."""
        ordered = sorted(
            self.contributions.values(),
            key=lambda c: (abs(c.contribution), c.feature),
            reverse=True,
        )
        if top is not None:
            ordered = ordered[:top]
        lines = [
            f"rank {self.rank} ({self.kind}, run {self.run_id}, score {self.score:.4g})"
        ]
        for c in ordered:
            if c.normalized is None:
                lines.append(
                    f"  {c.feature}: undefined (not scored), weight {c.weight:g}"
                )
            else:
                arrow = "favors" if c.contribution >= 0.0 else "penalizes"
                lines.append(
                    f"  {c.feature}: raw {c.raw:g}, norm {c.normalized:g}, "
                    f"{arrow} interest, w {c.weight:g} -> {c.contribution:+.4g}"
                )
        return lines


@dataclass(frozen=True)
class BehaviorRankingResult:
    """Ranked population with per-feature contributions.

    Ordering reuses the Task 1.7 rule: score descending, ties broken by
    ``run_id`` ascending, so the ranking is a pure function of the analyzed
    runs.
    """

    profile: InterestingnessProfile
    rows: tuple[RankedRow, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.as_dict(),
            "rows": [r.as_dict() for r in self.rows],
        }

    def run_ids_ranked(self) -> list[str]:
        return [r.run_id for r in self.rows]


def rank_by_profile(
    population: Sequence[FeaturedRun],
    profile: InterestingnessProfile,
) -> BehaviorRankingResult:
    """Rank a population against an explicit interestingness profile.

    Raw feature values are normalized (min-max) *across the population* per
    feature; each feature's contribution is ``weight * directional`` where
    ``directional = normalized`` when the profile maximizes it and
    ``1 - normalized`` when it minimizes it.  Undefined features contribute
    zero and are explained as such.
    """
    raws = [run.features.flatten() for run in population]
    normalized = _normalize_across(raws)

    scored: list[tuple[float, str, Mapping[str, Contribution], Mapping[str, float | None]]] = []
    for run, raw, norm in zip(population, raws, normalized):
        contributions: dict[str, Contribution] = {}
        for key, weight in profile.weights.items():
            value = raw.get(key)
            nv = None if value is None else norm.get(key)
            directional = nv if nv is not None else None
            if directional is not None and not profile.direction(key):
                directional = 1.0 - directional
            contribution = 0.0 if directional is None else weight * directional
            contributions[key] = Contribution(
                feature=key,
                weight=weight,
                raw=value,
                normalized=nv,
                contribution=float(contribution),
            )
        score = float(sum(c.contribution for c in contributions.values()))
        scored.append((score, run.run_id, contributions, raw))
    scored.sort(key=lambda kv: (-kv[0], kv[1]))

    rows = []
    for rank, (score, run_id, contribs, raw) in enumerate(scored, start=1):
        run = next(r for r in population if r.run_id == run_id)
        rows.append(
            RankedRow(
                rank=rank,
                run_id=run.run_id,
                kind=run.kind,
                score=score,
                contributions=contribs,
                raw_features=dict(raw),
            )
        )
    return BehaviorRankingResult(profile=profile, rows=tuple(rows))


# ---------------------------------------------------------------------------
# Run-level orchestration (recorded, lineage-linked)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FeaturedRun:
    """One analyzed run: identity, mutation, metrics, and feature vector.

    ``observables`` is kept in memory only (per-step data never enters the
    lineage store); ``features`` is the compact, persisted snapshot.
    """

    run_id: str
    kind: str
    world: WorldDefinition
    mutations: tuple[MutationRecord, ...]
    metrics: Mapping[str, float]
    features: BehaviorFeatures
    observables: Mapping[str, ObservableSeries] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "world_id": self.world.id,
            "mutations": [m.to_dict() for m in self.mutations],
            "metrics": dict(self.metrics),
            "features": self.features.as_dict(),
        }


@dataclass(frozen=True)
class BehaviorTiming:
    """Compact instrumentation of one behavioral analysis (no per-step data)."""

    n_planned: int
    n_skipped: int
    n_executed: int
    total_seconds: float
    mean_seconds: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n_planned": self.n_planned,
            "n_skipped": self.n_skipped,
            "n_executed": self.n_executed,
            "total_seconds": self.total_seconds,
            "mean_seconds": self.mean_seconds,
        }


class BehaviorAnalysisRecord:
    """Immutable metadata of one recorded behavioral analysis."""

    __slots__ = (
        "analysis_id",
        "base_run_id",
        "created_at",
        "profile",
        "ranked",
        "run_order",
        "timing",
        "world_hash",
        "world_id",
    )

    def __init__(
        self,
        analysis_id: str,
        *,
        world_id: str,
        world_hash: str,
        base_run_id: str,
        profile: InterestingnessProfile,
        run_order: Sequence[str],
        ranked: BehaviorRankingResult,
        timing: BehaviorTiming,
        created_at: str | None = None,
    ) -> None:
        self.analysis_id = analysis_id
        self.world_id = world_id
        self.world_hash = world_hash
        self.base_run_id = base_run_id
        self.profile = profile
        self.run_order = tuple(run_order)
        self.ranked = ranked
        self.timing = timing
        self.created_at = created_at or _now_iso()

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "world_id": self.world_id,
            "world_hash": self.world_hash,
            "base_run_id": self.base_run_id,
            "profile": self.profile.as_dict(),
            "run_order": list(self.run_order),
            "ranked": self.ranked.as_dict(),
            "timing": self.timing.as_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BehaviorAnalysisRecord:
        ranked_data = data["ranked"]
        return cls(
            analysis_id=str(data["analysis_id"]),
            world_id=str(data["world_id"]),
            world_hash=str(data["world_hash"]),
            base_run_id=str(data["base_run_id"]),
            profile=InterestingnessProfile.from_dict(ranked_data["profile"]),
            run_order=tuple(str(x) for x in data["run_order"]),
            ranked=BehaviorRankingResult(
                profile=InterestingnessProfile.from_dict(ranked_data["profile"]),
                rows=tuple(
                    RankedRow(
                        rank=int(r["rank"]),
                        run_id=str(r["run_id"]),
                        kind=str(r["kind"]),
                        score=float(r["score"]),
                        contributions={
                            k: Contribution(
                                feature=k,
                                weight=float(c["weight"]),
                                raw=(None if "raw" not in c else float(c["raw"])),
                                normalized=(
                                    None
                                    if "normalized" not in c
                                    else float(c["normalized"])
                                ),
                                contribution=float(c["contribution"]),
                            )
                            for k, c in r["contributions"].items()
                        },
                        raw_features={
                            k: (None if v is None else float(v))
                            for k, v in r.get("raw_features", {}).items()
                        },
                    )
                    for r in ranked_data["rows"]
                ),
            ),
            timing=BehaviorTiming(**{k: v for k, v in data["timing"].items()}),
            created_at=data.get("created_at"),
        )


def behavior_analysis_id_of(world: WorldDefinition, profile: InterestingnessProfile) -> str:
    """Deterministic analysis identity: base world + profile."""
    payload = json.dumps(
        {
            "world_hash": world_hash(world),
            "profile": profile.as_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class BehavioralAnalysisRunner:
    """Sequential, deterministic behavioral analysis over a mutation space.

    Reuses the Task 1.6/1.7 primitives directly (``apply_mutations`` with
    ``parameter_specs`` validation, deterministic ``run_id_of`` identity, the
    ``LineageStore``), and reuses ``MutationSpace`` generation order.  The
    baseline is always analyzed first as the control; its divergence features
    are undefined by construction (it is the reference).
    """

    def __init__(
        self,
        store: LineageStore,
        executor: Callable[[WorldDefinition], ExecOutcome],
        observables: Callable[[ExecOutcome], Mapping[str, ObservableSeries]],
        *,
        parameter_specs: Mapping[str, ParameterSpec] | None = None,
        analyzer: BehaviorAnalyzer | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._observables = observables
        self._specs = dict(parameter_specs or {})
        self._analyzer = analyzer or BehaviorAnalyzer()

    @property
    def store(self) -> LineageStore:
        return self._store

    def _validators(self) -> dict[str, Callable[[Any], bool]]:
        out: dict[str, Callable[[Any], bool]] = {}
        for path, spec in self._specs.items():
            fn = spec.validator()
            if fn is not None:
                out[path] = fn
        return out

    def analyze(
        self,
        base_world: WorldDefinition,
        mutation_space: MutationSpace,
        profile: InterestingnessProfile,
        *,
        analysis_id: str | None = None,
    ) -> BehaviorAnalysisResult:
        """Analyze baseline control + every variant under ``profile``.

        Validation mirrors ``SweepRunner`` phase 1: every combination is
        validated against the declared specs before any simulation starts;
        no-ops (worlds identical to the baseline) are skipped and counted.
        Runs are recorded once, with their compact feature snapshot, in the
        lineage store; per-step observables stay in memory only.
        """
        if analysis_id is None:
            analysis_id = behavior_analysis_id_of(base_world, profile)

        validators = self._validators()
        planned: list[tuple[Mutation, ...]] = []
        skipped = 0
        for mutations in mutation_space.variant_mutation_sets():
            child, _ = apply_mutations(base_world, mutations, validators=validators)
            if child.as_dict() == base_world.as_dict():
                skipped += 1
                continue
            planned.append(mutations)

        window_start = time.monotonic()

        base_outcome = self._executor(base_world)
        base_observables = dict(self._observables(base_outcome))
        base_features = self._analyzer.features(base_observables, baseline=None)
        base_record = RunRecord(
            run_id_of(base_world),
            base_world,
            parent_run_id=None,
            mutations=(),
            metrics=base_outcome.metrics,
            feature_snapshot=base_features.as_dict(),
        )
        self._store.record_run(base_record)
        base_run = FeaturedRun(
            run_id=base_record.run_id,
            kind="baseline",
            world=base_world,
            mutations=(),
            metrics=base_outcome.metrics,
            features=base_features,
            observables=base_observables,
        )
        base_seconds = time.monotonic() - window_start

        variants: list[FeaturedRun] = []
        variant_start = time.monotonic()
        for mutations in planned:
            child_world, records = apply_mutations(
                base_world, mutations, validators=validators
            )
            outcome = self._executor(child_world)
            observables = dict(self._observables(outcome))
            features = self._analyzer.features(observables, baseline=base_observables)
            child_record = RunRecord(
                run_id_of(child_world),
                child_world,
                parent_run_id=base_record.run_id,
                mutations=records,
                metrics=outcome.metrics,
                feature_snapshot=features.as_dict(),
            )
            self._store.record_run(child_record)
            variants.append(
                FeaturedRun(
                    run_id=child_record.run_id,
                    kind="variant",
                    world=child_world,
                    mutations=records,
                    metrics=outcome.metrics,
                    features=features,
                    observables=observables,
                )
            )
        variant_seconds = time.monotonic() - variant_start

        total = base_seconds + variant_seconds
        timing = BehaviorTiming(
            n_planned=len(mutation_space.variant_mutation_sets()),
            n_skipped=skipped,
            n_executed=len(variants),
            total_seconds=total,
            mean_seconds=total / max(1, len(variants)),
        )

        population = (base_run, *variants)
        ranking = rank_by_profile(population, profile)
        result = BehaviorAnalysisResult(
            analysis_id=analysis_id,
            world=base_world,
            profile=profile,
            population=population,
            ranking=ranking,
            timing=timing,
        )
        self._store.record_behavior_analysis(
            BehaviorAnalysisRecord(
                analysis_id=analysis_id,
                world_id=base_world.id,
                world_hash=world_hash(base_world),
                base_run_id=base_run.run_id,
                profile=profile,
                run_order=[r.run_id for r in population],
                ranked=ranking,
                timing=timing,
            )
        )
        return result


@dataclass(frozen=True)
class BehaviorAnalysisResult:
    """The full outcome of one behavioral analysis (in-memory).

    ``observables`` (per-step series) live only here and on ``FeaturedRun``;
    everything persisted is compact (features, ranking, timing).
    """

    analysis_id: str
    world: WorldDefinition
    profile: InterestingnessProfile
    population: tuple[FeaturedRun, ...]
    ranking: BehaviorRankingResult
    timing: BehaviorTiming

    def run(self, run_id: str) -> FeaturedRun | None:
        return next((r for r in self.population if r.run_id == run_id), None)

    def observables(self, run_id: str) -> Mapping[str, ObservableSeries] | None:
        run = self.run(run_id)
        return run.observables if run is not None else None

    def explain(self, run_id: str, *, top: int | None = None) -> list[str]:
        row = next((r for r in self.ranking.rows if r.run_id == run_id), None)
        if row is None:
            return []
        return row.explanation(top=top)

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "world_id": self.world.id,
            "profile": self.profile.as_dict(),
            "population": [r.as_dict() for r in self.population],
            "ranking": self.ranking.as_dict(),
            "timing": self.timing.as_dict(),
        }