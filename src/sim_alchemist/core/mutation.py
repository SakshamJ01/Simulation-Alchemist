"""Generic, deterministic world mutation (Task 1.6).

A mutation is a ``(path, new_value)`` pair naming one leaf inside a
``WorldDefinition``.  Applying a mutation never edits the parent world in
place: it returns a *new* ``WorldDefinition`` (an immutable clone of the
structure) plus a ``MutationRecord`` carrying the replaced value for lineage
bookkeeping.

Path grammar (dot-separated, dict/dataclass navigation only: no ``eval``,
no arbitrary code):

    components.<component-id>.config.<key...>
        a value nested inside one declared component's config dict
    config.<key...>
        a value in the world's shared top-level config dict
    seed | max_steps | macro_timestep
        a top-level ``WorldDefinition`` scalar

Structural fields (``schedule``, ``requires``, ``components`` itself, the
component ``id``) are intentionally not mutable: mutating structure would
produce a world the scheduler/composer contract cannot guarantee.

Validation is purely value-driven:

* an unresolvable path raises ``UnknownMutationPathError`` naming the path
  and the deepest valid prefix found;
* a value that is not type-compatible with the current leaf raises
  ``InvalidMutationValueError`` naming the path, the expected type, and the
  offending value;
* an optional ``validator`` (``range_validator`` / ``one_of`` or a custom
  predicate) rejects domain violations *before* any simulation runs.

This module has zero knowledge of any specific experiment: it only
understands the ``WorldDefinition`` grammar.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from sim_alchemist.core.world import ComponentSpec, WorldDefinition

__all__ = [
    "InvalidMutationValueError",
    "Mutation",
    "MutationError",
    "MutationRecord",
    "ParameterSpec",
    "UnknownMutationPathError",
    "apply_mutation",
    "apply_mutations",
    "clone_world",
    "one_of",
    "range_validator",
]

#: Scalar, non-structural ``WorldDefinition`` attributes that mutation may touch.
_MUTABLE_TOP_LEVEL = frozenset({"seed", "max_steps", "macro_timestep"})
#: Structural attributes that must never be changed by a mutation.
#: ``components`` is *navigable* (to reach a component's ``config``) but its
#: membership/order itself is not mutable, so it is handled by the tuple
#: branch rather than listed here.
_IMMUTABLE_TOP_LEVEL = frozenset({"id", "schedule", "requires"})


class MutationError(Exception):
    """Base error for any failure during world mutation."""


class UnknownMutationPathError(MutationError):
    """The mutation path does not resolve to an existing leaf.

    The message carries the offending path and the deepest valid prefix that
    was found, so failures identify exactly where the path went wrong.
    """


class InvalidMutationValueError(MutationError):
    """The new value is not valid for the targeted parameter.

    The message carries the path, the expected constraint, and the value.
    """


@dataclass(frozen=True)
class Mutation:
    """One declarative parameter change: ``path`` -> ``new_value``.

    Serializable (``to_dict``/``from_dict``) so a mutation set can be stored
    and re-applied verbatim.  A validator is *not* part of the mutation: it
    is a constraint supplied by the caller (e.g. a ``ParameterSpec``), keeping
    the mutation itself pure data.
    """

    path: str
    new_value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "new_value": self.new_value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mutation:
        return cls(path=data["path"], new_value=data["new_value"])

    @classmethod
    def from_record(cls, record: MutationRecord) -> Mutation:
        return cls(path=record.path, new_value=record.new_value)


@dataclass(frozen=True)
class MutationRecord:
    """A mutation together with the value it replaced as actually applied."""

    path: str
    old_value: Any
    new_value: Any

    def display(self) -> str:
        return f"{self.path} {self.old_value} -> {self.new_value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MutationRecord:
        return cls(
            path=data["path"],
            old_value=data.get("old_value"),
            new_value=data["new_value"],
        )


@dataclass(frozen=True)
class ParameterSpec:
    """Declared description of one mutable parameter of a world.

    This is the *generic* contract the experiment-facing side fills in; the
    core understands only bounded/typed ``minimum``/``maximum``/``allowed``
    constraints, never the experiment's semantics.
    """

    path: str
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    allowed: tuple[Any, ...] | None = None

    def validator(self) -> Callable[[Any], bool] | None:
        """Return a value predicate enforcing this spec's constraints."""
        if self.allowed is not None:
            return one_of(*self.allowed)
        if self.minimum is not None or self.maximum is not None:
            return range_validator(self.minimum, self.maximum)
        return None


def _fail_unknown(path: str, prefix: str, detail: str) -> None:
    raise UnknownMutationPathError(
        f"The mutation path '{path}' does not resolve; "
        f"deepest valid prefix reached: '{prefix}'. {detail}"
    )


def _coerce_for(old: Any, path: str, new_value: Any) -> Any:
    """Type-check ``new_value`` against the current leaf value.

    Rules: exact type is required except lossless numeric widening
    ``int -> float`` (``float -> int`` is rejected as potentially lossy).
    """
    if isinstance(old, bool) or isinstance(new_value, bool):
        if type(old) is not type(new_value):
            raise InvalidMutationValueError(
                f"The mutation path '{path}' expected type "
                f"{type(old).__name__}, got {type(new_value).__name__} "
                f"({new_value!r})."
            )
        return new_value
    if isinstance(old, int) and isinstance(new_value, int):
        return new_value
    if isinstance(old, float) and isinstance(new_value, (int, float)):
        return float(new_value)
    raise InvalidMutationValueError(
        f"The mutation path '{path}' expected type {type(old).__name__}, "
        f"got {type(new_value).__name__} ({new_value!r})."
    )


def _apply(
    node: Any,
    segments: list[str],
    full_path: str,
    prefix: str,
    new_value: Any,
) -> tuple[Any, Any, Any]:
    """Rebuild ``node`` with the leaf at ``segments`` replaced by ``new_value``.

    Returns ``(rebuilt_node, old_value, coerced_value)``.  ``node`` is treated
    immutably: every container on the path is copied, everything else is
    shared.
    """
    if not segments:
        # We are standing on the leaf: its current value is ``node``.
        coerced = _coerce_for(node, full_path, new_value)
        return coerced, node, coerced

    head, rest = segments[0], segments[1:]
    child_prefix = f"{prefix}.{head}" if prefix else head

    if isinstance(node, WorldDefinition):
        if head in _MUTABLE_TOP_LEVEL:
            _require_leaf(head, rest, full_path, child_prefix)
            old = getattr(node, head)
            coerced = _coerce_for(old, full_path, new_value)
            return replace(node, **{head: coerced}), old, coerced
        if head in _IMMUTABLE_TOP_LEVEL:
            _fail_unknown(
                full_path,
                prefix,
                f"the '{head}' field is structural and is not mutable by design.",
            )
        if head == "components":
            comps_new, old, coerced = _apply(
                node.components, rest, full_path, child_prefix, new_value
            )
            return replace(node, components=comps_new), old, coerced
        if head == "config":
            config_new, old, coerced = _apply(
                node.config, rest, full_path, child_prefix, new_value
            )
            return replace(node, config=config_new), old, coerced
        _fail_unknown(
            full_path,
            prefix,
            f"unknown top-level field '{head}'. Mutable top-level fields: "
            + ", ".join(sorted(_MUTABLE_TOP_LEVEL))
            + ".",
        )

    if isinstance(node, ComponentSpec):
        if head != "config":
            _fail_unknown(
                full_path,
                prefix,
                f"the component '{node.id}' has no mutable field '{head}'; "
                "only 'config' is mutable.",
            )
        config_new, old, coerced = _apply(
            node.config, rest, full_path, child_prefix, new_value
        )
        return replace(node, config=config_new), old, coerced

    if isinstance(node, dict):
        if head not in node:
            available = ", ".join(sorted(map(str, node))) or "(empty)"
            _fail_unknown(
                full_path,
                prefix,
                f"dictionary has no key '{head}'. Available keys: {available}.",
            )
        child_new, old, coerced = _apply(
            node[head], rest, full_path, child_prefix, new_value
        )
        out = dict(node)
        out[head] = child_new
        return out, old, coerced

    if isinstance(node, tuple):
        for spec in node:
            if spec.id == head:
                spec_new, old, coerced = _apply(
                    spec, rest, full_path, child_prefix, new_value
                )
                out = tuple((spec_new if s is spec else s) for s in node)
                return out, old, coerced
        available = ", ".join(sorted(s.id for s in node)) or "(world has no components)"
        _fail_unknown(
            full_path,
            prefix,
            f"no component with id '{head}'. Declared components: {available}.",
        )

    _fail_unknown(
        full_path,
        prefix,
        f"the path continues past a leaf value of type {type(node).__name__}.",
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _require_leaf(
    head: str, rest: list[str], full_path: str, child_prefix: str
) -> None:
    if rest:
        _fail_unknown(
            full_path,
            child_prefix,
            f"'{head}' is a scalar field and cannot be navigated further.",
        )


def clone_world(world: WorldDefinition) -> WorldDefinition:
    """Return a fully independent deep copy of ``world``.

    The clone shares no mutable objects with the parent, so either world can
    be edited without the other observing the change.
    """
    return copy.deepcopy(world)


def apply_mutation(
    world: WorldDefinition,
    mutation: Mutation,
    *,
    validator: Callable[[Any], bool] | None = None,
) -> tuple[WorldDefinition, MutationRecord]:
    """Apply one mutation, returning ``(child_world, record)``.

    The parent ``world`` is never modified.  If ``validator`` is supplied it
    is run against the coerced new value (after built-in type validation) and
    may raise ``ValueError``/return ``False`` to reject the value.

    Raises ``UnknownMutationPathError`` / ``InvalidMutationValueError`` before
    any simulation would start.
    """
    root = clone_world(world)
    segments = mutation.path.split(".")
    if not segments or not all(segments):
        raise UnknownMutationPathError(
            f"The mutation path '{mutation.path}' is not a valid dotted path."
        )
    rebuilt, old_value, coerced = _apply(
        root, segments, mutation.path, "", mutation.new_value
    )

    if validator is not None:
        try:
            ok = validator(coerced)
        except (ValueError, TypeError) as exc:  # validator reports its reason
            raise InvalidMutationValueError(
                f"The mutation path '{mutation.path}' rejected value "
                f"{mutation.new_value!r}: {exc}"
            ) from exc
        if not ok:
            raise InvalidMutationValueError(
                f"The mutation path '{mutation.path}' rejected value "
                f"{mutation.new_value!r}."
            )
    return rebuilt, MutationRecord(mutation.path, old_value, coerced)


def apply_mutations(
    world: WorldDefinition,
    mutations: list[Mutation] | tuple[Mutation, ...],
    *,
    validators: dict[str, Callable[[Any], bool]] | None = None,
) -> tuple[WorldDefinition, tuple[MutationRecord, ...]]:
    """Apply a sequence of mutations deterministically, left to right.

    Returns the final child world and the full ordered list of records (one
    per mutation, in application order).  Rerunning the same sequence on the
    same parent always produces the same child world.
    """
    current = world
    records: list[MutationRecord] = []
    for mutation in mutations:
        validator = validators.get(mutation.path) if validators else None
        current, record = apply_mutation(current, mutation, validator=validator)
        records.append(record)
    return current, tuple(records)


def range_validator(
    low: float | None, high: float | None
) -> Callable[[Any], bool]:
    """Return a validator rejecting values outside ``[low, high]``."""

    def _validate(value: Any) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"expected a number in [{low}, {high}], got {value!r}"
            )
        if low is not None and value < low:
            raise ValueError(f"must be >= {low}, got {value!r}")
        if high is not None and value > high:
            raise ValueError(f"must be <= {high}, got {value!r}")
        return True

    return _validate


def one_of(*choices: Any) -> Callable[[Any], bool]:
    """Return a validator accepting only a fixed set of values."""

    def _validate(value: Any) -> bool:
        if value not in choices:
            raise ValueError(f"must be one of {choices}, got {value!r}")
        return True

    return _validate