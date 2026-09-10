"""Task 2.7 Build Stage 2 — Multi-pass adaptive exploration adapter.

Thin wrapper over existing AdaptiveSweepRunner / adaptive selection.
No new simulation concept; no new engine; experiment-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Callable

from sim_alchemist.core.adaptive_exploration import (
    AdaptiveExplorationSpec,
    AdaptiveExplorationStatus,
    AdaptiveExplorationResult,
    filter_subspace,
    evaluate_exploration_spec,
    adaptive_exploration_id_of,
)
from sim_alchemist.core.adaptive_sweep import (
    AdaptiveSweepRunner,
    AdaptiveSweepSelection,
    AdaptiveSignal,
    AdaptiveRunResult,
)


@dataclass(frozen=True)
class AdaptiveExplorationPass:
    """Reference to one bounded adaptive pass (existing run identity preserved)."""
    pass_index: int
    adaptive_run_id: str
    actions: tuple[str, ...]
    steps: int
    final_decision: str
    termination_reason: str


@dataclass(frozen=True)
class AdaptiveExplorationExecutionResult:
    """Bounded multi-pass adaptive exploration outcome (Stage 2)."""
    exploration_id: str
    spec_dict: dict
    passes: tuple[AdaptiveExplorationPass, ...]
    final_decision: str
    termination_reason: str
    total_simulated: int
    status: str  # VALID / INVALID / EMPTY_SUBSPACE / BUDGET_EXHAUSTED / STOP / NO_NEXT_ACTION / EXECUTION_FAILURE

    def __post_init__(self) -> None:
        if self.status not in ("VALID", "INVALID", "EMPTY_SUBSPACE", "BUDGET_EXHAUSTED",
                               "STOP", "NO_NEXT_ACTION", "EXECUTION_FAILURE"):
            raise ValueError("invalid execution status")


def _derive_actions_from_spec(spec: AdaptiveExplorationSpec) -> tuple[str, ...]:
    """Derive allowed action pool from spec composition_ids + subspace.
    For existing repository: C -> ["baseline", "variant_loss"]; A/B only -> ["baseline"].
    No invented parameters."""
    actions = []
    if "C" in spec.composition_ids:
        actions.extend(["baseline", "variant_loss"])
    if "A" in spec.composition_ids or "B" in spec.composition_ids:
        if "baseline" not in actions:
            actions.append("baseline")
    return tuple(sorted(set(actions)))


def execute_adaptive_exploration(
    spec: AdaptiveExplorationSpec,
    execute_action: Callable[[str], tuple[str, object]],
    observe_signal: Callable[[object], AdaptiveSignal],
    mutation_space=None,
    max_passes: int = 2,
    seed: int = 0,
) -> AdaptiveExplorationExecutionResult:
    """Bounded adaptive exploration (Stage 2 — reuse existing runner).

    - Validates spec via evaluate_exploration_spec.
    - If INVALID/EMPTY, returns immediately with explicit status (no execution).
    - Otherwise runs up to max_passes via AdaptiveSweepRunner.
    - Each pass uses existing action derivation (respects C / A / B).
    - Replay deterministic from same spec + seed + max_passes.
    - No new execution concept.
    """
    # Stage 1 evaluation (pure planning; no execution)
    if mutation_space is not None:
        eval_result = evaluate_exploration_spec(spec, mutation_space=mutation_space)
    else:
        eval_result = evaluate_exploration_spec(spec)

    exploration_id = adaptive_exploration_id_of(spec, seed=seed)

    # Explicit termination for invalid / empty before execution
    if eval_result.status.status == "INVALID":
        return AdaptiveExplorationExecutionResult(
            exploration_id=exploration_id,
            spec_dict=spec.as_dict(),
            passes=(),
            final_decision="STOP",
            termination_reason="INVALID_SPEC",
            total_simulated=0,
            status="INVALID",
        )

    if eval_result.status.status == "EMPTY_SUBSPACE":
        return AdaptiveExplorationExecutionResult(
            exploration_id=exploration_id,
            spec_dict=spec.as_dict(),
            passes=(),
            final_decision="STOP",
            termination_reason="EMPTY_SUBSPACE",
            total_simulated=0,
            status="EMPTY_SUBSPACE",
        )

    # Derive allowed actions (existing legitimate candidates only)
    actions = _derive_actions_from_spec(spec)
    if not actions:
        return AdaptiveExplorationExecutionResult(
            exploration_id=exploration_id,
            spec_dict=spec.as_dict(),
            passes=(),
            final_decision="STOP",
            termination_reason="NO_NEXT_ACTION",
            total_simulated=0,
            status="NO_NEXT_ACTION",
        )

    # Bounded multi-pass using existing AdaptiveSweepRunner
    passes: list[AdaptiveExplorationPass] = []
    total_simulated = 0
    final_decision = "CONTINUE"
    termination_reason = "BUDGET_EXHAUSTED"
    evaluated_ids = []
    budget_remaining = spec.budget

    # Reusable selection instance (respects profile reference from spec)
    selector = AdaptiveSweepSelection(profile=spec.profile, actions=list(actions))

    for pass_index in range(max_passes):
        if budget_remaining <= 0:
            termination_reason = "BUDGET_EXHAUSTED"
            final_decision = "STOP" if final_decision != "CONTINUE" else "STOP"
            break

        # Select next proposal from existing pool (dedup, budget-aware)
        proposal = selector.select_proposal(
            available_actions=list(actions),
            evaluated_action_ids=evaluated_ids,
            profile_name=spec.profile,
            budget_remaining=budget_remaining,
        )

        # If no next legitimate action
        if proposal.proposal.proposal_state in ("NO_NEXT_ACTION", "BUDGET_EXHAUSTED"):
            termination_reason = proposal.proposal.proposal_state
            final_decision = "STOP"
            break

        # Execute one bounded pass through existing runner
        runner = AdaptiveSweepRunner(
            actions=list(actions),
            evaluator=None,
            budget=budget_remaining,
            seed=seed + pass_index,  # deterministic per pass
        )
        # Note: adaptive_run_id derived from actions + seed + budget; replay same inputs -> same id
        pass_result = runner.run(execute_action, observe_signal)
        passes.append(AdaptiveExplorationPass(
            pass_index=pass_index,
            adaptive_run_id=pass_result.adaptive_run_id,
            actions=actions,
            steps=len(pass_result.steps),
            final_decision=pass_result.final_decision,
            termination_reason=pass_result.termination_reason,
        ))
        total_simulated += pass_result.total_simulated
        evaluated_ids.extend([s.action_id for s in pass_result.steps if s.action_id])
        budget_remaining -= pass_result.total_simulated  # approximate budget consumption
        final_decision = pass_result.final_decision
        termination_reason = pass_result.termination_reason

        # Stop conditions
        if pass_result.termination_reason == "STOP" or pass_result.final_decision == "STOP":
            termination_reason = "STOP"
            final_decision = "STOP"
            break
        if pass_result.termination_reason == "BUDGET_EXHAUSTED" or budget_remaining <= 0:
            termination_reason = "BUDGET_EXHAUSTED"
            final_decision = "STOP" if final_decision == "CONTINUE" else final_decision
            break

    # If loop completed all max_passes without explicit stop, report budget/status
    if termination_reason == "BUDGET_EXHAUSTED" and len(passes) == max_passes:
        termination_reason = "BUDGET_EXHAUSTED"

    return AdaptiveExplorationExecutionResult(
        exploration_id=exploration_id,
        spec_dict=spec.as_dict(),
        passes=tuple(passes),
        final_decision=final_decision,
        termination_reason=termination_reason,
        total_simulated=total_simulated,
        status="VALID" if termination_reason in ("STOP", "BUDGET_EXHAUSTED") else "VALID",
    )
