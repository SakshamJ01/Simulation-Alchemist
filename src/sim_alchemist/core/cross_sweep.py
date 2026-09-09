"""Cross-composition parameter-space binding and result model (Task 2.5 Stage 1).

Stage 1 is the *data-model foundation* of the joint structural + parametric
discovery layer: it binds a parameter space (a ``MutationSpace``) to each
composition of the executable catalog and defines the deterministic,
content-addressed identity of a whole cross-composition sweep pass.

The layer is deliberately **experiment-free**: it only knows opaque
composition identities (``composition_id`` / ``shape_id``), opaque
parameter-space *references* (strings), and the generic ``MutationSpace``.
Which composition has which space, what the reference means, and what values
are explored are scientific facts owned by the experiment layer
(``experiments/catalog.py``); this module never names an experiment and never
executes anything.

Two principles drive the design:

* **Parameter identity stays honest.** ``CompositionSpaceBinding`` pairs one
  composition with *its own* space. ``space=None`` means "this composition has
  no registered parameter sweep space" -- it is *not* an error and *not* an
  empty mutation space. The reference (``ref``) is opaque metadata; the core
  does not interpret it.
* **Identity stays separate.** ``composition_id`` (one concrete structural
  composition), ``cross_split_sweep_id`` (the whole multi-composition sweep
  specification), ``sweep_id`` (one composition's parameter sweep) and
  ``run_id`` (one executed world) remain distinct, never overloaded.

Stage 1 executes nothing: no ``SweepRunner``, no adapters, no simulation, no
run recording. ``CrossCompositionSweepResult`` distinguishes a *planned* pass
(no execution) from an *executed* pass (Stage 2 populates per-composition
sweep/run identities); Stage 1 only ever constructs ``planned`` results.
``CrossCompositionSweepRecord`` is defined here as an immutable in-memory
metadata type; durable lineage persistence of such records is deferred to
Stage 2 together with the orchestrator that actually creates them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sim_alchemist.core.sweep import MutationSpace

__all__ = [
    "CompositionSpaceBinding",
    "CrossCompositionSweepRecord",
    "CrossCompositionSweepResult",
    "CrossCompositionSweepSpec",
    "cross_split_sweep_id",
    "parameter_space_ref",
]


def parameter_space_ref(space: MutationSpace) -> str:
    """Deterministic, opaque reference to a parameter space definition.

    The reference is a content address over the canonical, dictionary-order-
    independent serialisation of the ``MutationSpace`` (its declared
    dimensions/values).  Changing the space definition changes the reference,
    so a reference is a faithful fingerprint of "this composition's declared
    parameter range".  The core never interprets the reference - it is opaque
    naming-only metadata carried by a binding/result.
    """
    payload = json.dumps(
        space.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompositionSpaceBinding:
    """One composition and its own parameter space (Stage 1 data model).

    ``composition_id`` / ``shape_id`` identify the concrete composition.
    ``ref`` is the opaque content reference to the space definition (``None``
    when no space is registered).  ``space`` carries the generic
    ``MutationSpace`` or ``None`` when no space is registered.

    The three later fields are the **executed** identities a Stage-2
    orchestrator fills in; Stage 1 leaves them at their empty defaults:
    ``sweep_id`` (one composition's parameter sweep), ``baseline_run_id`` (the
    composition's baseline - an explicit control, never a mutated variant) and
    ``variant_run_ids`` (the executed parameter variants in generation order).
    """

    composition_id: str
    shape_id: str
    ref: str | None = None
    space: MutationSpace | None = None
    sweep_id: str | None = None
    baseline_run_id: str | None = None
    variant_run_ids: tuple[str, ...] = ()

    @property
    def has_space(self) -> bool:
        """A space is registered if and only if a reference is present."""
        return self.ref is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "shape_id": self.shape_id,
            "ref": self.ref,
            "space": self.space.to_dict() if self.space is not None else None,
            "sweep_id": self.sweep_id,
            "baseline_run_id": self.baseline_run_id,
            "variant_run_ids": list(self.variant_run_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompositionSpaceBinding:
        space_dict = data.get("space")
        return cls(
            composition_id=str(data["composition_id"]),
            shape_id=str(data["shape_id"]),
            ref=data.get("ref"),
            space=MutationSpace.from_dict(space_dict) if space_dict is not None else None,
            sweep_id=data.get("sweep_id"),
            baseline_run_id=data.get("baseline_run_id"),
            variant_run_ids=tuple(data.get("variant_run_ids", [])),
        )


@dataclass(frozen=True)
class CrossCompositionSweepSpec:
    """The complete, canonical specification of one cross-composition sweep.

    ``bindings`` is the ordered composition->space binding list (in canonical
    catalog order, never dict order).  ``profile`` / ``seed`` /
    ``evaluation_config`` capture the guiding/discovery configuration.
    ``as_dict(canonical=True)`` returns an order-independent serialisation so
    that the identity function below is a pure function of the definition.
    """

    space_name: str
    bindings: tuple[CompositionSpaceBinding, ...]
    profile: Any = None
    seed: int = 0
    evaluation_config: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", tuple(self.bindings))

    def as_dict(self, canonical: bool = True) -> dict[str, Any]:
        bindings = [b.as_dict() for b in self.bindings]
        profile_data = (
            None
            if self.profile is None
            else (
                self.profile.as_dict()
                if hasattr(self.profile, "as_dict")
                else dict(self.profile)
            )
        )
        return {
            "space_name": self.space_name,
            "bindings": bindings,
            "profile": profile_data,
            "seed": self.seed,
            "evaluation_config": (
                dict(self.evaluation_config) if self.evaluation_config is not None else None
            ),
        }


def cross_split_sweep_id(spec: CrossCompositionSweepSpec) -> str:
    """Deterministic, content-addressed identity of a cross-composition sweep.

    The identity covers everything that defines a sweep specification: the
    composition universe (space name), the *ordered* composition->parameter-
    space bindings (each including its opaque space reference), the discovery
    profile, the seed, and the evaluation configuration.  It contains no
    transient runtime data (timestamps, object identities, results).  The same
    canonical definition always produces the same 24-hex id; changing the
    universe, a binding, a space reference, the profile, the seed, or the
    evaluation configuration produces a different id.  ``as_dict(canonical)``
    plus ``sort_keys`` make it independent of dictionary insertion order.
    """
    payload = json.dumps(
        spec.as_dict(canonical=True),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class CrossCompositionSweepResult:
    """The (planned or executed) outcome of one cross-composition sweep.

    ``cross_split_sweep_id`` identifies the specification; ``spec`` is the
    full definition; ``bindings`` is the per-composition binding list.
    ``state`` is ``"planned"`` (Stage 1 - no execution has happened) or
    ``"executed"`` (Stage 2 populates the per-composition ``sweep_id`` /
    ``baseline_run_id`` / ``variant_run_ids`` on each binding).  Stage 1 only
    constructs ``planned`` results.

    The baseline is represented explicitly on each binding as
    ``baseline_run_id`` and is never a mutated variant; variant runs live in
    ``variant_run_ids``.  The model can therefore later hold per-composition
    sweep/run identities without Stage 1 having to populate them.
    """

    cross_split_sweep_id: str
    spec: CrossCompositionSweepSpec
    bindings: tuple[CompositionSpaceBinding, ...] = ()
    state: Literal["planned", "executed"] = "planned"

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", tuple(self.bindings))
        if self.state not in ("planned", "executed"):
            raise ValueError(f"state must be 'planned' or 'executed', got {self.state!r}")

    def binding(self, composition_id: str) -> CompositionSpaceBinding | None:
        return next((b for b in self.bindings if b.composition_id == composition_id), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cross_split_sweep_id": self.cross_split_sweep_id,
            "spec": self.spec.as_dict(canonical=True),
            "bindings": [b.as_dict() for b in self.bindings],
            "state": self.state,
        }


@dataclass(frozen=True)
class CrossCompositionSweepRecord:
    """Immutable in-memory metadata of one cross-composition sweep.

    Stage 1 defines this as a compact data type only; durable lineage
    persistence (a store table + methods) is explicitly deferred to Stage 2
    together with the orchestrator that creates these records.  It carries no
    trajectories, no per-step data, and no transient timestamps - consistent
    with the compact-only lineage policy.  The per-composition ``bindings``
    already hold the composition/sweep/baseline identities.
    """

    cross_split_sweep_id: str
    space_name: str
    seed: int
    bindings: tuple[CompositionSpaceBinding, ...] = ()
