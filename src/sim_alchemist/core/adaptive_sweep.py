"""Task 2.6 Build Stage 1 — Adaptive Discovery Foundation.

Smallest generic, experiment-free data contract for adaptive discovery
 driven by measured convergence / behavior signals.

Provides:
- ``AdaptiveSignal`` (measured signal + threshold + direction)
- ``AdaptiveState`` (current iteration, observed signals, decision)
- ``AdaptiveDecision`` (CONTINUE / STOP / HOLD — deterministic vocabulary)
- Pure evaluation: signals + configuration -> state + decision
- Canonical serialization (``as_dict``, sorted, no timestamps)
- Integration hook: consumes existing ``BehaviorFeatures`` / ``InterestingnessProfile``
  to prove the generic contract on real repository types.

Stage 1 is DATA CONTRACT ONLY. No simulation, no sweep execution,
no search loop, no mutation, no ranking, no frontier, no CLI.

Stage 2 boundary (RUNNING): adaptive execution loop with deterministic
candidate progression, measured-signal evaluation, budget-controlled
termination, and reuse of existing sweep/run lineage.

Stage 3 boundary (NOT started): adaptive ranking / frontier selection.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Core purity: this module references only generic types. Any optional
# references to experiment-specific behavior APIs are deferred to the
# helper functions below and guarded with graceful fallbacks.
# ---------------------------------------------------------------------------


class AdaptiveDecision:
    """Deterministic vocabulary for adaptive continuation decisions."""

    CONTINUE = "CONTINUE"
    STOP = "STOP"
    HOLD = "HOLD"

    _VALID = frozenset({CONTINUE, STOP, HOLD})

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls._VALID


@dataclass(frozen=True)
class AdaptiveSignal:
    """One measured adaptive signal.

    Explicit missing data: ``available=False`` means the signal is not
    usable; ``value=None`` must only occur when ``available=False``.
    When ``available=True`` the value is required to be a finite float.

    Direction / criterion are configuration, not derived from value.
    """

    name: str
    value: float | None = None
    available: bool = True
    direction: str = "max"  # "max" / "min" / "target" / "close"
    threshold: float | None = None
    criterion: str = "threshold"  # "threshold" / "stability" / "convergence"
    step: int | None = None
    horizon: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("AdaptiveSignal requires non-empty name")
        if not self.available and self.value is not None:
            # Explicit missing: value must not pretend to exist.
            # We allow this to be corrected by callers; do not raise so
            # that partial inputs can be inspected before evaluation.
            pass
        if self.available:
            if self.value is None:
                raise ValueError(
                    f"AdaptiveSignal '{self.name}': available=True but value=None"
                )
            if not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
                raise ValueError(
                    f"AdaptiveSignal '{self.name}': available=True requires finite float value"
                )
        if self.direction not in ("max", "min", "target", "close"):
            raise ValueError(
                f"AdaptiveSignal '{self.name}': direction must be max/min/target/close"
            )
        if self.criterion not in ("threshold", "stability", "convergence"):
            raise ValueError(
                f"AdaptiveSignal '{self.name}': criterion must be threshold/stability/convergence"
            )

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": None if not self.available else float(self.value),
            "available": bool(self.available),
            "direction": self.direction,
            "threshold": None if self.threshold is None else float(self.threshold),
            "criterion": self.criterion,
            "step": self.step,
            "horizon": self.horizon,
        }


@dataclass(frozen=True)
class AdaptiveState:
    """Deterministic adaptive state for one iteration/pass.

    Explanation is derived deterministically from observed signal values,
    thresholds, and the evaluation configuration — never from external
    state, randomness, or LLM/symbolic reasoning.
    """

    iteration: int
    signals: Mapping[str, AdaptiveSignal]
    decision: str  # must be a valid AdaptiveDecision value
    explanation: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.iteration, int) or self.iteration < 0:
            raise ValueError("AdaptiveState iteration must be non-negative int")
        if not AdaptiveDecision.is_valid(self.decision):
            raise ValueError(
                f"AdaptiveState decision must be one of {AdaptiveDecision._VALID}, got '{self.decision}'"
            )
        if not isinstance(self.signals, Mapping):
            raise TypeError("AdaptiveState signals must be a Mapping[str, AdaptiveSignal]")
        # Verify signal names match mapping keys
        for k, s in self.signals.items():
            if not isinstance(s, AdaptiveSignal):
                raise TypeError(f"AdaptiveState signals[{k!r}] must be AdaptiveSignal")
            if s.name != k:
                raise ValueError(
                    f"AdaptiveState signals key {k!r} mismatches signal.name {s.name!r}"
                )
        if not isinstance(self.explanation, str) or not self.explanation:
            raise ValueError("AdaptiveState requires non-empty explanation")

    def as_dict(self) -> dict:
        d = {
            "decision": self.decision,
            "explanation": self.explanation,
            "iteration": self.iteration,
            "metadata": dict(sorted((str(k), v) for k, v in self.metadata.items())),
            "signals": {
                name: sig.as_dict() for name, sig in sorted(self.signals.items())
            },
        }
        return dict(sorted(d.items()))


# ---------------------------------------------------------------------------
# Pure evaluation
# ---------------------------------------------------------------------------


def _evaluate_single(
    signal: AdaptiveSignal,
) -> tuple[bool, str]:
    """Return (met_criterion, explanation_fragment) for one signal."""
    if not signal.available:
        return False, f"{signal.name}: unavailable"
    value = float(signal.value)  # type: ignore[arg-type]
    # Threshold criterion
    if signal.criterion == "threshold":
        if signal.threshold is None:
            return False, f"{signal.name}: threshold criterion but threshold=None"
        thresh = float(signal.threshold)
        if signal.direction == "max":
            met = value >= thresh
        elif signal.direction == "min":
            met = value <= thresh
        elif signal.direction == "target":
            met = abs(value - thresh) < 1e-6  # exact equality for target
        elif signal.direction == "close":
            met = abs(value - thresh) <= max(1e-6, abs(thresh) * 1e-3)
        else:
            met = False
        fragment = (
            f"{signal.name}={value:.6g} {signal.direction}={thresh:.6g} met={met}"
        )
        return met, fragment
    # Stability / convergence: treated as satisfied only when value
    # is finite and threshold (if provided) is met; stability implies
    # the signal has settled (no further change needed). For Stage 1
    # we represent stability as "threshold met and available".
    if signal.criterion in ("stability", "convergence"):
        met = signal.available and signal.threshold is not None and (
            (signal.direction == "max" and value >= float(signal.threshold))
            or (signal.direction == "min" and value <= float(signal.threshold))
            or (signal.direction in ("target", "close") and abs(value - float(signal.threshold)) < 1e-6)
        )
        # If no threshold given for stability, treat as satisfied only when
        # available (pure measurement, no claim of convergence).
        if signal.threshold is None:
            met = signal.available
        fragment = f"{signal.name}={value:.6g} criterion={signal.criterion} met={met}"
        return met, fragment
    return False, f"{signal.name}: unknown criterion={signal.criterion}"


def evaluate_adaptive_decision(
    signals: Mapping[str, AdaptiveSignal] | Sequence[AdaptiveSignal],
    iteration: int = 0,
    config: dict | None = None,
) -> AdaptiveState:
    """Pure evaluation: observed signals -> deterministic adaptive state.

    Decision rules (explicit, deterministic):
      - If ANY signal is unavailable -> HOLD (missing data prevents action)
      - If ALL available signals meet their criterion -> STOP (converged)
      - Else -> CONTINUE (still exploring / not settled)

    Explanation is assembled deterministically from per-signal fragments.
    No randomness, no external state, no engine interaction.
    """
    if isinstance(signals, Sequence) and not isinstance(signals, (str, bytes)):
        signal_map = {}
        for s in signals:  # type: ignore[union-attr]
            if not isinstance(s, AdaptiveSignal):
                raise TypeError("signals sequence must contain only AdaptiveSignal")
            signal_map[s.name] = s
        signals = signal_map  # type: ignore[assignment]
    if not isinstance(signals, Mapping):
        raise TypeError("signals must be Mapping[str, AdaptiveSignal] or Sequence[AdaptiveSignal]")
    # Build ordered evaluation
    names = sorted(str(k) for k in signals)
    fragments: list[str] = []
    all_met = True
    any_unavailable = False
    for name in names:
        sig = signals[name]  # type: ignore[index]
        if not isinstance(sig, AdaptiveSignal):
            raise TypeError(f"signals[{name!r}] is not AdaptiveSignal")
        met, frag = _evaluate_single(sig)
        fragments.append(frag)
        if not sig.available:
            any_unavailable = True
        if not met:
            all_met = False
    # Decision logic
    if any_unavailable:
        decision = AdaptiveDecision.HOLD
    elif all_met:
        decision = AdaptiveDecision.STOP
    else:
        decision = AdaptiveDecision.CONTINUE
    # Explanation assembled deterministically from fragments + rule
    explanation = "; ".join(fragments)
    explanation += (
        f" | rules: unavailable->HOLD({any_unavailable}) all_met->STOP({all_met}) => {decision}"
    )
    # Config may override explanation prefix or metadata; keep pure.
    metadata: dict = {}
    if config is not None and isinstance(config, dict):
        metadata = dict(sorted(config.items()))
    return AdaptiveState(
        iteration=int(iteration) if iteration is not None else 0,
        signals=dict(sorted((str(k), signals[str(k)]) for k in names)),
        decision=decision,
        explanation=explanation,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Integration with existing repository types (proof of contract, no execution)
# ---------------------------------------------------------------------------


def adaptive_signal_from_features(
    features,
    profile=None,
    observable: str = "final_field_mean",
    feature: str = "mean",
    direction: str | None = None,
    threshold: float | None = None,
) -> AdaptiveSignal:
    """Produce an AdaptiveSignal from existing BehaviorFeatures + InterestingnessProfile.

    Demonstrates the generic contract consuming actual repository measurement
    types without requiring an engine, adapter, or simulation run.
    """
    # Deferred import to avoid circular dependencies and preserve core purity.
    try:
        from sim_alchemist.core.behavior import BehaviorFeatures, InterestingnessProfile
    except ImportError:  # pragma: no cover
        BehaviorFeatures = None  # type: ignore
        InterestingnessProfile = None  # type: ignore
    flat: dict[str, float | None] = {}
    if BehaviorFeatures is not None and isinstance(features, BehaviorFeatures):
        flat = features.flatten()
    elif isinstance(features, dict):
        flat = dict(features)
    key = f"{observable}:{feature}"
    raw = flat.get(key)
    available = raw is not None and isinstance(raw, (int, float)) and math.isfinite(raw)
    value = float(raw) if available else None
    dir_use = direction
    if dir_use is None and InterestingnessProfile is not None and isinstance(profile, InterestingnessProfile):
        # Profile directions map feature key -> bool (True = max, False = min)
        d = profile.directions.get(key, True)
        dir_use = "max" if d else "min"
    dir_use = dir_use if dir_use is not None else "max"
    return AdaptiveSignal(
        name=f"behavior:{key}",
        value=value,
        available=available,
        direction=dir_use,
        threshold=threshold,
        criterion="threshold",
    )


# ---------------------------------------------------------------------------
# Canonical serialization / identity helpers (no new identity required per design)
# ---------------------------------------------------------------------------


def adaptive_state_canonical(state: AdaptiveState) -> str:
    """Deterministic string representation for comparison / replay.

    Sorted, no timestamps, no object repr(), independent of dict insertion
    order (because ``as_dict`` sorts everything).
    """
    return repr(sorted(state.as_dict().items()))


# ============================================================================
# Task 2.6 Build Stage 2 - Adaptive Execution Loop (smallest reusable)
# ============================================================================

import json
from hashlib import sha256


@dataclass(frozen=True)
class AdaptiveStepRecord:
    """One adaptive step: action executed, signal observed, decision made."""
    step_index: int
    action_id: str
    run_id: str | None
    signal_summary: dict  # canonical summary of observed signal(s)
    decision: str
    state_snapshot: dict  # canonical AdaptiveState.as_dict() snapshot

    def __post_init__(self) -> None:
        if self.step_index < 0:
            raise ValueError("step_index must be >= 0")
        if not AdaptiveDecision.is_valid(self.decision):
            raise ValueError(f"invalid decision: {self.decision}")

    def as_dict(self) -> dict:
        return dict(sorted({
            "step_index": self.step_index,
            "action_id": self.action_id,
            "run_id": self.run_id,
            "signal_summary": dict(sorted(self.signal_summary.items())),
            "decision": self.decision,
            "state_snapshot": dict(sorted(self.state_snapshot.items())) if isinstance(self.state_snapshot, dict) else self.state_snapshot,
        }.items()))


@dataclass(frozen=True)
class AdaptiveRunResult:
    """Result of a bounded adaptive execution over existing candidate actions."""
    adaptive_run_id: str
    steps: tuple[AdaptiveStepRecord, ...]
    final_decision: str
    termination_reason: str
    total_simulated: int

    def __post_init__(self) -> None:
        if not self.adaptive_run_id or not isinstance(self.adaptive_run_id, str):
            raise ValueError("adaptive_run_id must be non-empty str")
        if not AdaptiveDecision.is_valid(self.final_decision):
            raise ValueError(f"invalid final_decision: {self.final_decision}")

    def as_dict(self) -> dict:
        return dict(sorted({
            "adaptive_run_id": self.adaptive_run_id,
            "steps": [s.as_dict() for s in self.steps],
            "final_decision": self.final_decision,
            "termination_reason": self.termination_reason,
            "total_simulated": self.total_simulated,
        }.items()))


def adaptive_run_id_of(
    actions: Sequence[str],
    seed: int = 0,
    budget: int = 10,
) -> str:
    """Deterministic content-addressed identity for an adaptive run spec."""
    payload = json.dumps({
        "actions": sorted(str(a) for a in actions),
        "budgets": int(budget),
        "seed": int(seed),
    }, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()[:24]


class AdaptiveSweepSelection:
    """Adaptive selection over existing legitimate candidates."""

    def __init__(
        self,
        profile=None,
        actions: Sequence[str] | None = None,
    ):
        self.profile = profile
        self.actions = tuple(str(a) for a in (actions or []))

    def select_next(
        self,
        available_actions: Sequence[str],
        current_index: int = 0,
        evaluated_signals: Mapping[str, AdaptiveSignal] | None = None,
    ) -> str | None:
        sorted_avail = sorted(str(a) for a in available_actions)
        if not sorted_avail:
            return None
        idx = min(int(current_index), len(sorted_avail) - 1)
        return sorted_avail[idx]


class AdaptiveSweepRunner:
    """Bounded adaptive execution controller (Stage 2)."""

    def __init__(
        self,
        actions: Sequence[str],
        evaluator,
        budget: int = 5,
        seed: int = 0,
    ):
        if budget <= 0:
            raise ValueError("budget must be positive")
        self.actions = tuple(sorted(str(a) for a in actions))
        self.evaluator = evaluator
        self.budget = int(budget)
        self.seed = int(seed)
        self.adaptive_run_id = adaptive_run_id_of(self.actions, seed=seed, budget=budget)

    def run(
        self,
        execute_action,
        observe_signal,
        initial_state: AdaptiveState | None = None,
    ) -> AdaptiveRunResult:
        steps: list[AdaptiveStepRecord] = []
        current_index = 0
        termination = "BUDGET_EXHAUSTED"
        final_decision = AdaptiveDecision.CONTINUE
        simulated = 0

        for step_idx in range(self.budget):
            if current_index >= len(self.actions):
                termination = "NO_VALID_ACTION"
                break

            action_id = self.actions[current_index]
            run_id, outcome = execute_action(action_id)
            simulated += 1

            signal = observe_signal(outcome)

            state = evaluate_adaptive_decision([signal], iteration=step_idx, config={"action": action_id, "adaptive_run_id": self.adaptive_run_id})

            steps.append(AdaptiveStepRecord(
                step_index=step_idx,
                action_id=action_id,
                run_id=str(run_id) if run_id is not None else None,
                signal_summary=signal.as_dict(),
                decision=state.decision,
                state_snapshot=state.as_dict(),
            ))

            final_decision = state.decision

            if state.decision == AdaptiveDecision.STOP or state.decision == AdaptiveDecision.HOLD:
                termination = "STOP"
                break
            else:
                current_index += 1

        if termination == "BUDGET_EXHAUSTED" and final_decision == AdaptiveDecision.CONTINUE:
            termination = "BUDGET_EXHAUSTED"

        return AdaptiveRunResult(
            adaptive_run_id=self.adaptive_run_id,
            steps=tuple(steps),
            final_decision=final_decision,
            termination_reason=termination,
            total_simulated=simulated,
        )


# === Stage 3/4/5 APIs (merged from stage3_4) ===


@dataclass(frozen=True)
class AdaptiveProposal:
    """Deterministic proposal of next legitimate action from existing pool."""
    proposal_state: str  # PROPOSED / NO_NEXT_ACTION / BUDGET_EXHAUSTED / ALREADY_EVALUATED
    proposed_action_id: str | None
    selection_reason: str  # deterministic, explainable from inputs
    profile_used: str | None
    budget_remaining: int
    evaluated_ids: tuple[str, ...]  # canonical sorted list of already-evaluated action IDs

    def __post_init__(self) -> None:
        if self.proposal_state not in ("PROPOSED", "NO_NEXT_ACTION", "BUDGET_EXHAUSTED", "ALREADY_EVALUATED"):
            raise ValueError(f"invalid proposal_state: {self.proposal_state}")
        if self.proposed_action_id is not None and not isinstance(self.proposed_action_id, str):
            raise ValueError("proposed_action_id must be str or None")
        if self.budget_remaining < 0:
            raise ValueError("budget_remaining must be >= 0")

    def as_dict(self) -> dict:
        return dict(sorted({
            "proposal_state": self.proposal_state,
            "proposed_action_id": self.proposed_action_id,
            "selection_reason": self.selection_reason,
            "profile_used": self.profile_used,
            "budget_remaining": self.budget_remaining,
            "evaluated_ids": list(sorted(self.evaluated_ids)),
        }.items()))


@dataclass(frozen=True)
class AdaptiveSelectionResult:
    """Result of adaptive selection over completed behavior / existing candidates."""
    proposal: AdaptiveProposal
    source_context: dict  # canonical reference to source result/sweep/behavior (not full record)
    selection_identity: str  # deterministic content-addressed 24-hex

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, AdaptiveProposal):
            raise ValueError("proposal must be AdaptiveProposal")
        if not self.selection_identity or not isinstance(self.selection_identity, str):
            raise ValueError("selection_identity required")

    def as_dict(self) -> dict:
        return dict(sorted({
            "proposal": self.proposal.as_dict(),
            "source_context": dict(sorted(str(k), v) for k, v in self.source_context.items()),
            "selection_identity": self.selection_identity,
        }.items()))


def selection_id_of(
    proposal_state: str,
    proposed_action_id: str | None,
    evaluated_ids: Sequence[str],
    profile_name: str | None = None,
    seed: int = 0,
) -> str:
    """Deterministic identity for a selection result (no timestamps/repr/order)."""
    import json
    from hashlib import sha256
    payload = json.dumps({
        "state": proposal_state,
        "action": str(proposed_action_id) if proposed_action_id else None,
        "evaluated": sorted(str(i) for i in evaluated_ids),
        "profile": str(profile_name) if profile_name else None,
        "seed": int(seed),
    }, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()[:24]


# Enhance AdaptiveSweepSelection with proposal/dedup (Stage 3)
class AdaptiveSweepSelection:
    """Adaptive selection over existing legitimate candidates (Stage 3 enhanced)."""

    def __init__(
        self,
        profile=None,
        actions: Sequence[str] | None = None,
    ):
        self.profile = profile
        self.actions = tuple(str(a) for a in (actions or []))

    def select_next(
        self,
        available_actions: Sequence[str],
        current_index: int = 0,
        evaluated_signals: Mapping[str, AdaptiveSignal] | None = None,
    ) -> str | None:
        sorted_avail = sorted(str(a) for a in available_actions)
        if not sorted_avail:
            return None
        idx = min(int(current_index), len(sorted_avail) - 1)
        return sorted_avail[idx]

    def select_proposal(
        self,
        available_actions: Sequence[str],
        evaluated_action_ids: Sequence[str],
        profile_name: str | None = None,
        budget_remaining: int = 5,
    ) -> AdaptiveSelectionResult:
        """Stage 3 deterministic proposal with dedup and budget."""
        eval_set = set(str(i) for i in evaluated_action_ids)
        remaining = [str(a) for a in available_actions if str(a) not in eval_set]
        remaining_sorted = sorted(remaining)
        profile_str = str(profile_name) if profile_name else None

        if budget_remaining <= 0:
            proposal = AdaptiveProposal(
                proposal_state="BUDGET_EXHAUSTED",
                proposed_action_id=None,
                selection_reason="budget exhausted; no further evaluation allowed",
                profile_used=profile_str,
                budget_remaining=0,
                evaluated_ids=tuple(sorted(eval_set)),
            )
            return AdaptiveSelectionResult(
                proposal=proposal,
                source_context={"budget_remaining": budget_remaining},
                selection_identity=selection_id_of("BUDGET_EXHAUSTED", None, list(eval_set), profile_str),
            )

        if not remaining_sorted:
            proposal = AdaptiveProposal(
                proposal_state="NO_NEXT_ACTION",
                proposed_action_id=None,
                selection_reason="all legitimate candidates already evaluated; no untested action remains",
                profile_used=profile_str,
                budget_remaining=int(budget_remaining),
                evaluated_ids=tuple(sorted(eval_set)),
            )
            return AdaptiveSelectionResult(
                proposal=proposal,
                source_context={"remaining_candidates": []},
                selection_identity=selection_id_of("NO_NEXT_ACTION", None, list(eval_set), profile_str),
            )

        # Profile participates in selection semantics when it names a remaining candidate
        if profile_str and profile_str != "default" and profile_str in remaining_sorted:
            proposed = profile_str
            selection_reason = f"profile preference {profile_str} consulted among {len(remaining_sorted)} eligible; selected from untested pool"
        else:
            proposed = remaining_sorted[0]
            selection_reason = f"canonical sorted order; first untested from {len(remaining_sorted)} eligible; profile={profile_str or 'none'}; excluded already-evaluated={len(eval_set)}"

        proposal = AdaptiveProposal(
            proposal_state="PROPOSED",
            proposed_action_id=proposed,
            selection_reason=selection_reason,
            profile_used=profile_str,
            budget_remaining=int(budget_remaining) - 1,
            evaluated_ids=tuple(sorted(eval_set)),
        )
        return AdaptiveSelectionResult(
            proposal=proposal,
            source_context={"candidate_pool_size": len(remaining_sorted), "profile": profile_str},
            selection_identity=selection_id_of("PROPOSED", proposed, list(eval_set), profile_str),
        )


# Stage 4 feedback-driven loop adapter: connect selection result to runner
# (additive; preserves existing static AdaptiveSweepRunner.run())
def adaptive_continue_from_result(
    prior_result: AdaptiveRunResult,
    available_actions: Sequence[str],
    profile_name: str | None = None,
    budget_remaining: int = 2,
) -> AdaptiveSelectionResult:
    """Stage 4 proposal from a completed adaptive run."""
    evaluated_ids = [s.action_id for s in prior_result.steps if s.action_id is not None]
    sel = AdaptiveSweepSelection(profile=None, actions=list(available_actions))
    return sel.select_proposal(available_actions, evaluated_ids, profile_name=profile_name, budget_remaining=budget_remaining)