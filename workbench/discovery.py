"""Phase 3 Discovery & Research Automation Orchestration Layer.

This module is the researcher-facing orchestration and integration layer for
systematic parameter exploration in the Researcher Workbench.

Design Rule:
    DO NOT rebuild existing generic discovery algorithms. This module calls
    existing generic core machinery:
    - ``sim_alchemist.core.sweep.ParameterSweep`` & ``MutationSpace``
    - ``sim_alchemist.core.mutation.apply_mutations``
    - ``sim_alchemist.core.lineage.run_id_of`` & ``world_hash``
    - ``sim_alchemist.core.behavior.BehaviorAnalyzer`` & ``ObservableSeries``
    - ``sim_alchemist.core.behavior.rank_by_profile`` & ``InterestingnessProfile``
    - ``sim_alchemist.core.behavior.select_diverse_frontier``
    - ``experiments.catalog.repository_executors`` & ``repository_parameter_spaces``

This module owns:
    1. Discovery request validation against declared ``ParameterSpec``s.
    2. Bounded exploration orchestration with strict evaluation budget caps (K <= 50).
    3. Baseline control execution first, followed by deterministic Cartesian variants.
    4. Runtime estimation calibrated against empirical benchmark measurements.
    5. Behavioral feature extraction, transparent profile ranking, and diversity frontier identification.
    6. Trajectory retention policy & durable persistence to WorkbenchStore (workbench.db).
"""

from __future__ import annotations

import copy
import math
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from experiments.catalog import (
    repository_executors,
    repository_parameter_spaces,
    repository_templates,
)
from experiments.gated_movers.experiment import (
    specs_by_path as gated_specs_by_path,
)
from experiments.network_morphogenesis.experiment import (
    build_network_observables,
)
from experiments.network_morphogenesis.experiment import (
    specs_by_path as network_specs_by_path,
)
from sim_alchemist.core.behavior import (
    BehaviorAnalyzer,
    BehaviorFeatures,
    BehaviorRankingResult,
    FeaturedRun,
    InterestingnessProfile,
    ObservableSeries,
    rank_by_profile,
    select_diverse_frontier,
)
from sim_alchemist.core.lineage import run_id_of
from sim_alchemist.core.mutation import (
    MutationRecord,
    ParameterSpec,
    apply_mutations,
)
from sim_alchemist.core.runner import ExecOutcome
from sim_alchemist.core.sweep import MutationSpace, ParameterSweep, sweep_id_of
from sim_alchemist.core.templates import generate_world, template_composition_id
from sim_alchemist.core.world import WorldDefinition
from workbench.store import DiscoverySessionRecord, ExperimentRecord, WorkbenchStore

__all__ = [
    "MAX_DISCOVERY_CANDIDATES",
    "DiscoveryCandidateOutcome",
    "DiscoveryCandidateRecord",
    "DiscoveryExplorationResult",
    "DiscoveryPassResult",
    "build_mutation_space",
    "characterize_and_rank_candidates",
    "estimate_discovery_runtime",
    "extract_candidate_observables",
    "get_default_interestingness_profile",
    "get_default_mutation_space",
    "get_experiment_parameter_specs",
    "run_bounded_discovery_exploration",
    "run_discovery_pass",
    "serialize_discovery_trajectory",
    "validate_discovery_space",
]

#: Hard ceiling on total candidates executed in a single interactive discovery pass.
MAX_DISCOVERY_CANDIDATES: int = 50

#: Empirical per-step execution time coefficients in seconds (calibrated on workstation).
_CALIBRATED_PER_STEP_SECONDS: dict[str, float] = {
    "gated_movers": 0.75,  # Measured ~9.08s for 12 macro-steps
    "adaptive_network": 0.15,  # Measured ~1.8s for 12 macro-steps
    "network_morphogenesis": 0.15,
}


def _normalize_template_name(template_name: str) -> str:
    """Map common synonyms to canonical template names in repository."""
    if template_name in ("network_morphogenesis", "adaptive_network"):
        return "adaptive_network"
    return template_name


@dataclass(frozen=True)
class DiscoveryCandidateOutcome:
    """The execution outcome of one candidate in a discovery pass."""

    candidate_id: str
    run_id: str
    composition_id: str
    experiment_template: str
    parameters: dict[str, Any]
    seed: int
    max_steps: int
    metrics: dict[str, float]
    trajectory: Any | None
    execution_time_seconds: float
    is_baseline: bool
    mutations: tuple[MutationRecord, ...]
    world_definition: WorldDefinition

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "composition_id": self.composition_id,
            "experiment_template": self.experiment_template,
            "parameters": dict(self.parameters),
            "seed": self.seed,
            "max_steps": self.max_steps,
            "metrics": dict(self.metrics),
            "execution_time_seconds": self.execution_time_seconds,
            "is_baseline": self.is_baseline,
            "mutations": [m.to_dict() for m in self.mutations],
        }


@dataclass(frozen=True)
class DiscoveryCandidateRecord:
    """Enriched, persistent discovery candidate with ranking and frontier metadata."""

    candidate_id: str
    record_id: str
    run_id: str
    composition_id: str
    experiment_template: str
    parameters: dict[str, Any]
    seed: int
    max_steps: int
    metrics: dict[str, float]
    features: dict[str, float | None]
    rank: int
    score: float
    contributions: dict[str, dict[str, Any]]
    is_frontier: bool
    diversity_distance: float
    selection_reason: str
    is_baseline: bool
    has_trajectory: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryExplorationResult:
    """The aggregate outcome of an executed bounded discovery exploration pass."""

    experiment_template: str
    composition_id: str
    mutation_space: MutationSpace
    sweep_id: str
    candidates: tuple[DiscoveryCandidateOutcome, ...]
    n_planned: int
    n_skipped: int
    n_executed: int
    total_runtime_seconds: float

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_template": self.experiment_template,
            "composition_id": self.composition_id,
            "sweep_id": self.sweep_id,
            "candidate_count": self.candidate_count,
            "n_planned": self.n_planned,
            "n_skipped": self.n_skipped,
            "n_executed": self.n_executed,
            "total_runtime_seconds": self.total_runtime_seconds,
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass(frozen=True)
class DiscoveryPassResult:
    """Complete discovery pass outcome including ranked candidates, frontier, and session linkage."""

    session_id: str
    name: str
    experiment_template: str
    composition_id: str
    created_at: str
    candidates: list[DiscoveryCandidateRecord]
    frontier_candidates: list[DiscoveryCandidateRecord]
    ranking_profile: dict[str, Any]
    search_spec: dict[str, Any]
    summary_metrics: dict[str, Any]
    total_runtime_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "experiment_template": self.experiment_template,
            "composition_id": self.composition_id,
            "created_at": self.created_at,
            "candidates": [c.as_dict() for c in self.candidates],
            "frontier_candidates": [c.as_dict() for c in self.frontier_candidates],
            "ranking_profile": self.ranking_profile,
            "search_spec": self.search_spec,
            "summary_metrics": self.summary_metrics,
            "total_runtime_seconds": self.total_runtime_seconds,
        }


def get_experiment_parameter_specs(template_name: str) -> dict[str, ParameterSpec]:
    """Retrieve declared ParameterSpecs for an experiment template."""
    norm_name = _normalize_template_name(template_name)
    if norm_name == "gated_movers":
        return gated_specs_by_path()
    if norm_name == "adaptive_network":
        return network_specs_by_path()
    raise ValueError(
        f"Experiment template '{template_name}' does not declare parameter specifications. "
        "Parameter exploration is currently supported for Experiment D ('gated_movers') "
        "and Experiment C ('network_morphogenesis')."
    )


def validate_discovery_space(
    template_name: str,
    sweeps: Sequence[ParameterSweep | Mapping[str, Any]],
) -> tuple[ParameterSweep, ...]:
    """Validate user-requested parameter sweeps against experiment ParameterSpecs."""
    specs = get_experiment_parameter_specs(template_name)
    validated_sweeps: list[ParameterSweep] = []

    for sweep_item in sweeps:
        if isinstance(sweep_item, ParameterSweep):
            sweep = sweep_item
        elif isinstance(sweep_item, Mapping):
            sweep = ParameterSweep.from_dict(sweep_item)
        else:
            raise TypeError(f"Expected ParameterSweep or Mapping, got {type(sweep_item).__name__}")

        if sweep.path not in specs:
            valid_paths = ", ".join(sorted(specs.keys()))
            raise ValueError(
                f"Invalid parameter path '{sweep.path}' for experiment '{template_name}'. "
                f"Supported paths are: {valid_paths}"
            )

        spec = specs[sweep.path]
        for val in sweep.values:
            if not (isinstance(val, (int, float)) and math.isfinite(val)):
                raise ValueError(f"Value '{val}' for parameter '{sweep.path}' must be a finite number.")
            if spec.minimum is not None and val < spec.minimum:
                raise ValueError(
                    f"Value {val} for parameter '{sweep.path}' is below legal minimum "
                    f"{spec.minimum} declared in ParameterSpec."
                )
            if spec.maximum is not None and val > spec.maximum:
                raise ValueError(
                    f"Value {val} for parameter '{sweep.path}' is above legal maximum "
                    f"{spec.maximum} declared in ParameterSpec."
                )

        validated_sweeps.append(sweep)

    if not validated_sweeps:
        raise ValueError("Discovery space requires at least one parameter dimension.")

    total_variants = math.prod(len(s.values) for s in validated_sweeps)
    if total_variants > MAX_DISCOVERY_CANDIDATES:
        raise ValueError(
            f"Discovery subspace variant count ({total_variants}) exceeds maximum allowed cap "
            f"of {MAX_DISCOVERY_CANDIDATES} evaluations. Please narrow parameter value lists."
        )

    return tuple(validated_sweeps)


def get_default_mutation_space(template_name: str) -> MutationSpace:
    """Retrieve the pre-registered default MutationSpace for an experiment."""
    norm_name = _normalize_template_name(template_name)
    templates = repository_templates()
    template = templates.by_name(norm_name)
    if template is None:
        raise ValueError(f"Unknown experiment template: '{template_name}'")

    comp_id = template_composition_id(template)
    spaces = repository_parameter_spaces()
    binding = spaces.get(comp_id)
    if binding is None or binding.space is None:
        raise ValueError(
            f"Template '{template_name}' has no registered parameter space in repository."
        )
    return binding.space


def build_mutation_space(
    template_name: str,
    sweeps: Sequence[ParameterSweep | Mapping[str, Any]] | None = None,
) -> MutationSpace:
    """Construct a validated MutationSpace for discovery exploration."""
    if sweeps is None or len(sweeps) == 0:
        return get_default_mutation_space(template_name)
    validated = validate_discovery_space(template_name, sweeps)
    return MutationSpace(validated)


def estimate_discovery_runtime(
    template_name: str,
    candidate_count: int,
    max_steps: int,
) -> float:
    """Calculate an empirically calibrated runtime estimate in seconds."""
    norm_name = _normalize_template_name(template_name)
    per_step = _CALIBRATED_PER_STEP_SECONDS.get(norm_name, 0.5)
    return round(float(candidate_count * (0.2 + per_step * max_steps)), 2)


def extract_candidate_observables(
    template_name: str,
    trajectory: Any,
) -> dict[str, ObservableSeries]:
    """Extract scalar ObservableSeries from a simulation trajectory for behavior analysis."""
    if trajectory is None:
        return {}

    norm_name = _normalize_template_name(template_name)
    if norm_name == "adaptive_network":
        return build_network_observables(trajectory)

    # Experiment D (gated movers)
    times = tuple(float(t) for t in getattr(trajectory, "t_field", []))
    if not times:
        return {}

    def _series(name: str, vals: Sequence[Any]) -> ObservableSeries:
        return ObservableSeries(name=name, times=times, values=tuple(float(v) for v in vals))

    u_snaps = getattr(trajectory, "u_snaps", [])
    field_means = [float(np.asarray(u).mean()) for u in u_snaps] if u_snaps else [0.0] * len(times)
    field_stds = [float(np.asarray(u).std()) for u in u_snaps] if u_snaps else [0.0] * len(times)

    return {
        "speed": _series("speed", getattr(trajectory, "speeds", [0.0] * len(times))),
        "force": _series("force", getattr(trajectory, "force_mags", [0.0] * len(times))),
        "gradient": _series("gradient", getattr(trajectory, "gradient_mags", [0.0] * len(times))),
        "field_mean": _series("field_mean", field_means),
        "field_std": _series("field_std", field_stds),
        "active_gates": _series("active_gates", getattr(trajectory, "active_gates", [0.0] * len(times))),
        "suppressed_gates": _series("suppressed_gates", getattr(trajectory, "suppressed_gates", [0.0] * len(times))),
        "gate_deposits": _series("gate_deposits", getattr(trajectory, "gate_deposits", [0.0] * len(times))),
    }


def get_default_interestingness_profile(template_name: str) -> InterestingnessProfile:
    """Return an authoritative default InterestingnessProfile for an experiment template."""
    norm_name = _normalize_template_name(template_name)
    if norm_name == "gated_movers":
        return InterestingnessProfile(
            name="hysteresis_deposition_balance",
            description="Balances high mover velocity and active deposition with pattern emergence.",
            weights={
                "speed:mean": 1.0,
                "field_std:final_delta": 1.0,
                "active_gates:mean": 0.8,
                "suppressed_gates:mean": 0.4,
            },
            directions={
                "speed:mean": True,
                "field_std:final_delta": True,
                "active_gates:mean": True,
                "suppressed_gates:mean": False,
            },
        )
    if norm_name == "adaptive_network":
        return InterestingnessProfile(
            name="adaptive_network_diffusion",
            description="Favors high field heterogeneity, sustained wall forces, and network transport.",
            weights={
                "field_std:final_delta": 1.0,
                "wall_force:mean": 1.0,
                "network_load_mean:mean": 0.8,
            },
            directions={
                "field_std:final_delta": True,
                "wall_force:mean": True,
                "network_load_mean:mean": True,
            },
        )
    raise ValueError(f"No default ranking profile declared for template '{template_name}'.")


def serialize_discovery_trajectory(trajectory: Any, max_visual_frames: int = 250) -> dict[str, Any]:
    """Serialize trajectory arrays into web-ready decimation payloads with synchronous decimation."""
    if trajectory is None:
        return {
            "available": False,
            "total_steps": 0,
            "stride": 1,
            "is_strided": False,
            "visual_frames_count": 0,
            "field_frames": [],
            "movers": {},
            "walls": {},
            "active_gates": [],
            "suppressed_gates": [],
            "gate_deposits": [],
            "gate_switches": [],
            "speeds": [],
            "force_mags": [],
            "gradient_mags": [],
        }

    u_snaps = getattr(trajectory, "u_snaps", [])
    total_steps = len(u_snaps) if u_snaps else 0
    if total_steps == 0:
        positions_dict = getattr(trajectory, "positions", {})
        if positions_dict:
            first_pts = next(iter(positions_dict.values()), [])
            total_steps = len(first_pts)

    if total_steps > max_visual_frames:
        stride = math.ceil(total_steps / max_visual_frames)
        sampled_indices = set(range(0, total_steps, stride))
        sampled_indices.add(total_steps - 1)
        step_indices = sorted(sampled_indices)
    else:
        stride = 1
        step_indices = list(range(total_steps))

    field_frames: list[dict[str, Any]] = []
    for idx in step_indices:
        if idx < len(u_snaps):
            arr = u_snaps[idx]
            if hasattr(arr, "tolist"):
                min_val = float(np.min(arr))
                max_val = float(np.max(arr))
                field_frames.append({
                    "step": idx,
                    "shape": list(arr.shape),
                    "min": min_val,
                    "max": max_val,
                    "grid": [[round(float(v), 3) for v in row] for row in arr],
                })

    positions_dict = getattr(trajectory, "positions", {})
    movers_data: dict[str, list[list[float]]] = {}
    for m_id, pts in positions_dict.items():
        movers_data[str(m_id)] = [
            [round(float(pts[idx][0]), 4), round(float(pts[idx][1]), 4)]
            for idx in step_indices
            if idx < len(pts)
        ]

    wall_tracks = getattr(trajectory, "wall_tracks", {})
    walls_data: dict[str, list[list[float]]] = {}
    for w_id, pts in wall_tracks.items():
        walls_data[str(w_id)] = [
            [round(float(coord), 4) for coord in pts[idx]]
            for idx in step_indices
            if idx < len(pts)
        ]

    active_gates = getattr(trajectory, "active_gates", [])
    suppressed_gates = getattr(trajectory, "suppressed_gates", [])
    gate_deposits = getattr(trajectory, "gate_deposits", [])
    gate_switches = getattr(trajectory, "gate_switches", [])
    speeds = getattr(trajectory, "speeds", [])
    force_mags = getattr(trajectory, "force_mags", [])
    gradient_mags = getattr(trajectory, "gradient_mags", [])

    return {
        "available": True,
        "total_steps": total_steps,
        "stride": stride,
        "is_strided": stride > 1,
        "visual_frames_count": len(step_indices),
        "field_frames": field_frames,
        "movers": movers_data,
        "walls": walls_data,
        "active_gates": [int(active_gates[idx]) for idx in step_indices if idx < len(active_gates)],
        "suppressed_gates": [int(suppressed_gates[idx]) for idx in step_indices if idx < len(suppressed_gates)],
        "gate_deposits": [int(gate_deposits[idx]) for idx in step_indices if idx < len(gate_deposits)],
        "gate_switches": [int(gate_switches[idx]) for idx in step_indices if idx < len(gate_switches)],
        "speeds": [round(float(speeds[idx]), 5) for idx in step_indices if idx < len(speeds)],
        "force_mags": [round(float(force_mags[idx]), 5) for idx in step_indices if idx < len(force_mags)],
        "gradient_mags": [round(float(gradient_mags[idx]), 5) for idx in step_indices if idx < len(gradient_mags)],
    }


def run_bounded_discovery_exploration(
    template_name: str,
    sweeps: Sequence[ParameterSweep | Mapping[str, Any]] | None = None,
    *,
    max_steps: int = 12,
    seed: int = 42,
    retain_all_trajectories: bool = False,
) -> DiscoveryExplorationResult:
    """Execute a bounded discovery exploration pass.

    Execution Lifecycle:
    1. Resolve template, composition_id, and conforming executor from repository.
    2. Build base WorldDefinition via generate_world(template) with seed and max_steps.
    3. Build validated MutationSpace (defaults to registered space if sweeps=None).
    4. Execute Baseline Control (unmutated base world) unconditionally first at index 0.
    5. Execute Cartesian product variants in deterministic order (right-most dimension fastest).
    6. Skip and count no-ops (mutation sets identical to the baseline).
    7. Return structured DiscoveryExplorationResult containing all candidate outcomes.
    """
    norm_name = _normalize_template_name(template_name)
    templates = repository_templates()
    template = templates.by_name(norm_name)
    if template is None:
        raise ValueError(f"Unknown experiment template: '{template_name}'")

    comp_id = template_composition_id(template)
    executors = repository_executors()
    if comp_id not in executors:
        raise ValueError(f"No conforming executor registered for composition '{comp_id}'.")
    executor_fn = executors[comp_id]

    # 1. Base world generation with requested horizon and seed
    raw_base_world = generate_world(template)
    cfg = copy.deepcopy(raw_base_world.config)
    cfg["n_steps"] = max_steps
    base_world = replace(raw_base_world, max_steps=max_steps, seed=seed, config=cfg)

    # 2. Build and validate mutation space
    mutation_space = build_mutation_space(template_name, sweeps)
    sweep_id = sweep_id_of(base_world, mutation_space)

    start_pass_time = time.monotonic()
    candidates: list[DiscoveryCandidateOutcome] = []
    skipped_no_ops = 0

    # 3. Phase 1: Baseline Control Run (unmutated base world)
    t0 = time.monotonic()
    base_outcome: ExecOutcome = executor_fn(base_world)
    base_duration = time.monotonic() - t0

    # Extract base parameter dictionary
    specs = get_experiment_parameter_specs(template_name)
    base_params: dict[str, Any] = {}
    for path in specs:
        parts = path.split(".")
        val = base_world.config
        for p in parts[1:]:  # skip 'config' prefix
            if isinstance(val, dict):
                val = val.get(p)
        base_params[path] = val

    candidates.append(
        DiscoveryCandidateOutcome(
            candidate_id="cand_0",
            run_id=run_id_of(base_world),
            composition_id=comp_id,
            experiment_template=norm_name,
            parameters=base_params,
            seed=seed,
            max_steps=max_steps,
            metrics=dict(base_outcome.metrics),
            trajectory=base_outcome.trajectory,  # Baseline trajectory is always retained
            execution_time_seconds=round(base_duration, 4),
            is_baseline=True,
            mutations=(),
            world_definition=base_world,
        )
    )

    # 4. Phase 2: Variant Runs in deterministic Cartesian order
    variant_sets = mutation_space.variant_mutation_sets()
    n_planned = len(variant_sets)

    for i, mutations in enumerate(variant_sets, start=1):
        mutated_world, records = apply_mutations(base_world, mutations)

        # Check for no-op mutation set
        if mutated_world.as_dict() == base_world.as_dict():
            skipped_no_ops += 1
            continue

        # Extract current parameter dictionary
        var_params = dict(base_params)
        for mut in mutations:
            var_params[mut.path] = mut.new_value

        t_var = time.monotonic()
        outcome: ExecOutcome = executor_fn(mutated_world)
        var_duration = time.monotonic() - t_var

        candidates.append(
            DiscoveryCandidateOutcome(
                candidate_id=f"cand_{len(candidates)}",
                run_id=run_id_of(mutated_world),
                composition_id=comp_id,
                experiment_template=norm_name,
                parameters=var_params,
                seed=seed,
                max_steps=max_steps,
                metrics=dict(outcome.metrics),
                trajectory=outcome.trajectory if retain_all_trajectories else None,
                execution_time_seconds=round(var_duration, 4),
                is_baseline=False,
                mutations=records,
                world_definition=mutated_world,
            )
        )

    total_duration = time.monotonic() - start_pass_time

    return DiscoveryExplorationResult(
        experiment_template=norm_name,
        composition_id=comp_id,
        mutation_space=mutation_space,
        sweep_id=sweep_id,
        candidates=tuple(candidates),
        n_planned=n_planned,
        n_skipped=skipped_no_ops,
        n_executed=len(candidates) - 1,  # exclude baseline from variant execution count
        total_runtime_seconds=round(total_duration, 4),
    )


def characterize_and_rank_candidates(
    exploration_result: DiscoveryExplorationResult,
    profile: InterestingnessProfile | None = None,
    *,
    beam_width: int = 3,
    quality_weight: float = 0.7,
    diversity_weight: float = 0.3,
) -> tuple[list[dict[str, Any]], BehaviorRankingResult, list[tuple[str, float, float, float, float, str]]]:
    """Extract 18-feature behavior vectors, rank by profile, and compute diversity frontier."""
    template_name = exploration_result.experiment_template
    if profile is None:
        profile = get_default_interestingness_profile(template_name)

    # 1. Extract scalar observable series for each candidate
    obs_map: dict[str, dict[str, ObservableSeries]] = {}
    for cand in exploration_result.candidates:
        obs_map[cand.run_id] = extract_candidate_observables(template_name, cand.trajectory)

    # Baseline observables are reference for divergence features
    base_run_id = exploration_result.candidates[0].run_id
    base_obs = obs_map.get(base_run_id, {})

    # 2. Extract 18-feature BehaviorFeatures using generic core BehaviorAnalyzer
    analyzer = BehaviorAnalyzer()
    featured_runs: list[FeaturedRun] = []
    features_by_run_id: dict[str, BehaviorFeatures] = {}

    for cand in exploration_result.candidates:
        feats = analyzer.features(obs_map[cand.run_id], baseline=base_obs)
        features_by_run_id[cand.run_id] = feats
        featured_runs.append(
            FeaturedRun(
                run_id=cand.run_id,
                kind="baseline" if cand.is_baseline else "variant",
                world=cand.world_definition,
                mutations=cand.mutations,
                metrics=cand.metrics,
                features=feats,
                observables=obs_map[cand.run_id],
            )
        )

    # 3. Transparent ranking using generic core rank_by_profile
    ranking_result = rank_by_profile(featured_runs, profile)

    # 4. Diversity frontier selection using generic core select_diverse_frontier
    frontier_inputs: list[tuple[str, float, dict[str, float]]] = []
    for r in ranking_result.rows:
        cand_feats = features_by_run_id[r.run_id]
        # Filter finite floats for Euclidean distance calculation
        vector = {k: float(v) for k, v in cand_feats.flatten().items() if v is not None and math.isfinite(v)}
        frontier_inputs.append((r.run_id, r.score, vector))

    frontier_tuples = select_diverse_frontier(
        frontier_inputs,
        beam_width=beam_width,
        quality_weight=quality_weight,
        diversity_weight=diversity_weight,
    )

    frontier_map: dict[str, tuple[float, float, str]] = {}
    for f in frontier_tuples:
        # (run_id, quality_score, diversity_score, combined_score, min_distance, selection_reason)
        frontier_map[f[0]] = (f[2], f[4], f[5])

    # 5. Assemble enriched candidate dictionaries
    enriched: list[dict[str, Any]] = []
    for r in ranking_result.rows:
        cand_outcome = next(c for c in exploration_result.candidates if c.run_id == r.run_id)
        is_front = r.run_id in frontier_map
        f_info = frontier_map.get(r.run_id, (0.0, 0.0, "unselected"))

        contrib_dict: dict[str, dict[str, Any]] = {}
        for k, c in r.contributions.items():
            contrib_dict[k] = {
                "weight": c.weight,
                "raw": c.raw,
                "normalized": c.normalized,
                "contribution": c.contribution,
            }

        enriched.append({
            "candidate_id": cand_outcome.candidate_id,
            "run_id": cand_outcome.run_id,
            "composition_id": cand_outcome.composition_id,
            "experiment_template": cand_outcome.experiment_template,
            "parameters": cand_outcome.parameters,
            "seed": cand_outcome.seed,
            "max_steps": cand_outcome.max_steps,
            "metrics": cand_outcome.metrics,
            "features": features_by_run_id[r.run_id].flatten(),
            "rank": r.rank,
            "score": round(r.score, 4),
            "contributions": contrib_dict,
            "is_frontier": is_front,
            "diversity_distance": round(f_info[1], 4),
            "selection_reason": f_info[2],
            "is_baseline": cand_outcome.is_baseline,
            "has_trajectory": cand_outcome.trajectory is not None,
            "execution_time_seconds": cand_outcome.execution_time_seconds,
            "raw_trajectory": cand_outcome.trajectory,
            "world_definition": cand_outcome.world_definition,
        })

    return enriched, ranking_result, frontier_tuples


def run_discovery_pass(
    template_name: str,
    sweeps: Sequence[ParameterSweep | Mapping[str, Any]] | None = None,
    *,
    profile: InterestingnessProfile | None = None,
    beam_width: int = 3,
    quality_weight: float = 0.7,
    diversity_weight: float = 0.3,
    max_steps: int = 12,
    seed: int = 42,
    session_name: str = "",
    notes: str = "",
    store: WorkbenchStore | None = None,
    retain_all_trajectories: bool = False,
) -> DiscoveryPassResult:
    """End-to-end bounded discovery pass orchestrator.

    Executes:
    1. Bounded exploration runner across parameter subspace.
    2. 18-feature extraction, transparent profile ranking, and greedy diversity frontier.
    3. Persists each candidate as a Phase 2 ExperimentRecord in WorkbenchStore.
    4. Applies Trajectory Retention Policy (full trajectory for baseline & frontier; lazy for others).
    5. Persists DiscoverySessionRecord in WorkbenchStore and returns complete DiscoveryPassResult.
    """
    if store is None:
        store = WorkbenchStore()

    norm_name = _normalize_template_name(template_name)
    if profile is None:
        profile = get_default_interestingness_profile(norm_name)

    # 1. Execute bounded exploration
    # Baseline trajectory is always captured; variants captured if retain_all_trajectories
    exploration = run_bounded_discovery_exploration(
        norm_name,
        sweeps,
        max_steps=max_steps,
        seed=seed,
        retain_all_trajectories=True,  # Capture in-memory to compute observables; persistence is filtered below
    )

    # 2. Extract features, rank, and select frontier
    enriched_items, _ranking_res, _frontier_res = characterize_and_rank_candidates(
        exploration,
        profile,
        beam_width=beam_width,
        quality_weight=quality_weight,
        diversity_weight=diversity_weight,
    )

    session_id = f"disc_{uuid.uuid4().hex[:12]}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pass_name = session_name or f"{norm_name.replace('_', ' ').title()} Discovery ({created_at[:10]})"

    name_map = {
        "morphogenesis": "Morphogenesis (A)",
        "field_guided_movers": "Field-guided movers (B)",
        "adaptive_network": "Adaptive network (C)",
        "gated_movers": "Gated mover morphogenesis (D)",
    }
    exp_display_name = name_map.get(norm_name, norm_name)

    candidate_records: list[DiscoveryCandidateRecord] = []
    frontier_records: list[DiscoveryCandidateRecord] = []
    candidate_record_ids: list[str] = []
    frontier_record_ids: list[str] = []

    # 3. Persistence to WorkbenchStore with Trajectory Retention Policy
    for item in enriched_items:
        rec_id = f"rec_{uuid.uuid4().hex[:12]}"
        is_front = bool(item["is_frontier"])
        is_base = bool(item["is_baseline"])

        # Trajectory Retention Policy:
        # Full trajectory saved if: (1) baseline, OR (2) frontier, OR (3) retain_all_trajectories requested
        should_retain_traj = is_base or is_front or retain_all_trajectories
        serialized_traj = serialize_discovery_trajectory(item["raw_trajectory"]) if should_retain_traj else None

        tags = ["discovery", norm_name, "baseline" if is_base else "variant"]
        if is_front:
            tags.append("frontier")

        record = ExperimentRecord(
            record_id=rec_id,
            run_id=item["run_id"],
            composition_id=item["composition_id"],
            experiment_template=norm_name,
            experiment_name=exp_display_name,
            created_at=created_at,
            status="completed",
            execution_time_seconds=float(item["execution_time_seconds"]),
            seed=seed,
            max_steps=max_steps,
            parameters=item["parameters"],
            canonical_world=item["world_definition"].as_dict(),
            metrics=item["metrics"],
            feature_snapshot={"features": item["features"]},
            trajectory_summary={
                "available": should_retain_traj,
                "total_steps": serialized_traj.get("total_steps", max_steps) if serialized_traj else max_steps,
            },
            tags=tags,
            notes=f"Generated by Discovery Session '{pass_name}'. Rank: {item['rank']}, Score: {item['score']:.3f}",
        )

        store.save_record(record, trajectory=serialized_traj)
        candidate_record_ids.append(rec_id)
        if is_front:
            frontier_record_ids.append(rec_id)

        cand_rec = DiscoveryCandidateRecord(
            candidate_id=item["candidate_id"],
            record_id=rec_id,
            run_id=item["run_id"],
            composition_id=item["composition_id"],
            experiment_template=norm_name,
            parameters=item["parameters"],
            seed=seed,
            max_steps=max_steps,
            metrics=item["metrics"],
            features=item["features"],
            rank=item["rank"],
            score=item["score"],
            contributions=item["contributions"],
            is_frontier=is_front,
            diversity_distance=item["diversity_distance"],
            selection_reason=item["selection_reason"],
            is_baseline=is_base,
            has_trajectory=should_retain_traj,
        )
        candidate_records.append(cand_rec)
        if is_front:
            frontier_records.append(cand_rec)

    # 4. Save DiscoverySessionRecord in WorkbenchStore
    search_spec_dict = {
        "template": norm_name,
        "max_steps": max_steps,
        "seed": seed,
        "sweeps": [s.to_dict() for s in exploration.mutation_space.dimensions],
    }
    summary_dict = {
        "candidate_count": len(candidate_records),
        "frontier_count": len(frontier_records),
        "total_runtime_seconds": exploration.total_runtime_seconds,
        "n_planned": exploration.n_planned,
        "n_skipped": exploration.n_skipped,
        "quality_weight": quality_weight,
        "diversity_weight": diversity_weight,
    }

    session_record = DiscoverySessionRecord(
        session_id=session_id,
        name=pass_name,
        experiment_template=norm_name,
        composition_id=exploration.composition_id,
        created_at=created_at,
        search_spec=search_spec_dict,
        ranking_profile=profile.as_dict(),
        candidate_record_ids=candidate_record_ids,
        frontier_record_ids=frontier_record_ids,
        summary_metrics=summary_dict,
        notes=notes,
    )
    store.save_discovery_session(session_record)

    return DiscoveryPassResult(
        session_id=session_id,
        name=pass_name,
        experiment_template=norm_name,
        composition_id=exploration.composition_id,
        created_at=created_at,
        candidates=candidate_records,
        frontier_candidates=frontier_records,
        ranking_profile=profile.as_dict(),
        search_spec=search_spec_dict,
        summary_metrics=summary_dict,
        total_runtime_seconds=exploration.total_runtime_seconds,
    )
