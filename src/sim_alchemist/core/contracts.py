"""Coupling contracts and their pre-execution validation (Task 2.2).

A ``CouplingContract`` is a *declaration*, authored next to an experiment's
operations, that a specific scientific edge exists between two components::

    producer --(capability)--> consumer

The contract pins the producer/consumer component ids, the capabilities the
edge flows through, the shared state vocabulary (``payload``), the
experiment-owned ``transform`` that materializes the edge, and, when a
component id is dual-variant, the concrete ``variant`` the edge targets.

``resolve_contracts`` validates every declared contract against a built
adapter set *before any engine steps*:

* the producer and consumer components exist in the set;
* each endpoint actually provides the declared capability;
* variant bindings are consistent (a variant-tagged endpoint must be pinned,
  and a pinned variant must match the tagged endpoint);
* every payload key belongs to the producer's declared state vocabulary and
  uses a documented shape;
* timing, mechanism, coordinate-system and grid constraints are consistent
  between the two endpoints.

Crucially the layer never *invents* an edge: capability compatibility alone
creates nothing.  Only a *declared* contract is validated, so a latent
(undeclared) coupling is simply not asserted, while a declared-but-unrealized
edge is rejected up front.

Constraints deliberately live in the contract next to the experiment science;
the generic core only validates -- it never interprets ``transform``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sim_alchemist.core.capabilities import SimulationEngine

SUPPORTED_TIMINGS: frozenset[str] = frozenset({"same-macro-step"})
SUPPORTED_MECHANISMS: frozenset[str] = frozenset({"direct"})
SUPPORTED_PAYLOAD_SHAPES: frozenset[str] = frozenset(
    {"scalar", "vec2", "vec2_list", "bool_2d", "array_1d"}
)


@dataclass(frozen=True)
class PayloadItem:
    """One ``(key, shape)`` entry of a contract's shared state vocabulary."""

    key: str
    shape: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("payload key must be a non-empty string")
        if not self.shape:
            raise ValueError("payload shape must be a non-empty string")

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "shape": self.shape}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PayloadItem:
        return cls(key=str(data["key"]), shape=str(data["shape"]))


@dataclass(frozen=True, init=False)
class CouplingContract:
    """A declared scientific edge between two components of a composed world.

    ``payload`` is the tuple of state keys the producer makes available to the
    consumer on this edge.  Entries may be given as ``(key, shape)`` pairs or
    as ``PayloadItem`` (they are normalized to ``PayloadItem`` on creation).

    ``variant`` pins the concrete variant of a dual-variant component id
    (e.g. the ``pymunk`` id is either ``walls`` or ``movers``).

    ``transform`` is an opaque experiment-owned identifier of the coupling
    rule that materializes the edge; the core never interprets it.
    """

    name: str
    producer: str
    producer_capability: str
    consumer: str
    consumer_capability: str
    transform: str
    payload: tuple[PayloadItem, ...]
    timing: str = "same-macro-step"
    mechanism: str = "direct"
    variant: str | None = None
    coordinate_system: str | None = None
    grid: int | None = None

    def __init__(
        self,
        name: str,
        producer: str,
        producer_capability: str,
        consumer: str,
        consumer_capability: str,
        payload: Sequence[PayloadItem | tuple[str, str]],
        transform: str,
        timing: str = "same-macro-step",
        mechanism: str = "direct",
        variant: str | None = None,
        coordinate_system: str | None = None,
        grid: int | None = None,
    ) -> None:
        for field_name, value in (
            ("name", name),
            ("producer", producer),
            ("producer_capability", producer_capability),
            ("consumer", consumer),
            ("consumer_capability", consumer_capability),
            ("transform", transform),
        ):
            if not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if variant is not None and not isinstance(variant, str):
            raise TypeError("variant must be a str or None")
        if grid is not None and (isinstance(grid, bool) or not isinstance(grid, int)):
            raise TypeError("grid must be a positive int or None")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "producer", producer)
        object.__setattr__(self, "producer_capability", producer_capability)
        object.__setattr__(self, "consumer", consumer)
        object.__setattr__(self, "consumer_capability", consumer_capability)
        object.__setattr__(self, "transform", transform)
        object.__setattr__(
            self,
            "payload",
            tuple(_as_payload_item(item) for item in payload),
        )
        object.__setattr__(self, "timing", timing)
        object.__setattr__(self, "mechanism", mechanism)
        object.__setattr__(self, "variant", variant)
        object.__setattr__(self, "coordinate_system", coordinate_system)
        object.__setattr__(self, "grid", grid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "producer": self.producer,
            "producer_capability": self.producer_capability,
            "consumer": self.consumer,
            "consumer_capability": self.consumer_capability,
            "payload": [item.as_dict() for item in self.payload],
            "transform": self.transform,
            "timing": self.timing,
            "mechanism": self.mechanism,
            "variant": self.variant,
            "coordinate_system": self.coordinate_system,
            "grid": self.grid,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CouplingContract:
        return cls(
            name=str(data["name"]),
            producer=str(data["producer"]),
            producer_capability=str(data["producer_capability"]),
            consumer=str(data["consumer"]),
            consumer_capability=str(data["consumer_capability"]),
            payload=tuple(PayloadItem.from_dict(i) for i in data["payload"]),
            transform=str(data["transform"]),
            timing=str(data.get("timing", "same-macro-step")),
            mechanism=str(data.get("mechanism", "direct")),
            variant=data.get("variant"),
            coordinate_system=data.get("coordinate_system"),
            grid=data.get("grid"),
        )


@dataclass(frozen=True)
class ContractIssue:
    """One concrete problem found while validating a declared contract."""

    contract: str
    producer: str
    consumer: str
    variant: str | None
    what: str
    fix: str


class UnresolvedContractError(Exception):
    """Coupling-contract validation rejected one or more declared edges.

    Every issue names its contract, endpoints, variant, reason and remediation
    so the failure is actionable at compose time.
    """

    def __init__(self, issues: Sequence[ContractIssue]) -> None:
        self.issues = tuple(sorted(issues, key=_issue_sort_key))
        count = len(self.issues)
        lines = [_format_issue(i) for i in self.issues]
        super().__init__(
            "Coupling contract validation rejected "
            f"{count} declared edge{'s' if count != 1 else ''} "
            "before any engine stepped:\n"
            + "\n".join(f"  - {line}" for line in lines)
        )


def adapter_by_id(
    adapters: Sequence[SimulationEngine], component_id: str
) -> SimulationEngine:
    """Return the composed adapter whose ``engine_id`` equals ``component_id``.

    Lookup by id + variant metadata (never by position) is the documented
    hardening for facades and executors.  Raises ``KeyError`` otherwise.
    """
    for adapter in adapters:
        if adapter.engine_id == component_id:
            return adapter
    available = ", ".join(sorted({a.engine_id for a in adapters})) or "(none)"
    raise KeyError(
        f"no composed adapter has engine_id {component_id!r}; "
        f"available: {available}"
    )


def resolve_contracts(
    adapters: Sequence[SimulationEngine],
    contracts: Sequence[CouplingContract],
) -> None:
    """Validate every declared contract against the built adapter set.

    Raises ``UnresolvedContractError`` listing every failing contract in a
    deterministic order; returns ``None`` when all declared edges resolve.
    This is a pre-execution gate: it must run before any engine step.
    """
    issues: list[ContractIssue] = []
    for contract in contracts:
        _validate_contract(contract, adapters, issues)
    if issues:
        raise UnresolvedContractError(issues)


def contracts_key(contracts: Sequence[CouplingContract]) -> str:
    """Deterministic identity of a contract set (canonical JSON sha256)."""
    canonical = json.dumps(
        [c.as_dict() for c in contracts],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_contract(
    contract: CouplingContract,
    adapters: Sequence[SimulationEngine],
    issues: list[ContractIssue],
) -> None:
    if contract.producer == contract.consumer:
        issues.append(
            _make_issue(
                contract,
                what="producer and consumer are the same component",
                fix="couple two distinct components (a contract is never a self-edge)",
            )
        )

    producer = _find_adapter(adapters, contract.producer)
    consumer = _find_adapter(adapters, contract.consumer)

    if producer is None:
        issues.append(
            _make_issue(
                contract,
                what=f"producer component '{contract.producer}' is not composed",
                fix="add a component with that engine_id to the world",
            )
        )
    if consumer is None:
        issues.append(
            _make_issue(
                contract,
                what=f"consumer component '{contract.consumer}' is not composed",
                fix="add a component with that engine_id to the world",
            )
        )
    if producer is None or consumer is None:
        return

    if not producer.provides.has(contract.producer_capability):
        issues.append(
            _make_issue(
                contract,
                what=f"producer '{contract.producer}' does not provide "
                f"capability '{contract.producer_capability}'",
                fix="compose a producer that provides it or fix the declared edge",
            )
        )
    if not consumer.provides.has(contract.consumer_capability):
        issues.append(
            _make_issue(
                contract,
                what=f"consumer '{contract.consumer}' does not provide "
                f"capability '{contract.consumer_capability}'",
                fix="compose a consumer that provides it or fix the declared edge",
            )
        )

    _validate_variant(contract, producer, consumer, issues)
    _validate_payload(contract, producer, issues)
    _validate_handoff(contract, issues)
    _validate_space(contract, producer, consumer, issues)


def _validate_variant(
    contract: CouplingContract,
    producer: SimulationEngine,
    consumer: SimulationEngine,
    issues: list[ContractIssue],
) -> None:
    tagged: list[tuple[str, str]] = []
    for endpoint, adapter in ((contract.producer, producer), (contract.consumer, consumer)):
        variant = _endpoint_variant(adapter)
        if variant is not None:
            tagged.append((endpoint, variant))

    if contract.variant is None:
        for endpoint, variant in tagged:
            issues.append(
                _make_issue(
                    contract,
                    what=f"endpoint '{endpoint}' is a variant component "
                    f"('{variant}') but the contract does not pin a variant",
                    fix=f"set variant='{variant}' to pin the intended binding",
                )
            )
        return

    if not tagged:
        issues.append(
            _make_issue(
                contract,
                variant=contract.variant,
                what="the contract pins a variant but neither endpoint is a "
                "variant component",
                fix="remove the variant from the contract or compose the "
                "variant adapter",
            )
        )
        return

    for endpoint, variant in tagged:
        if variant != contract.variant:
            issues.append(
                _make_issue(
                    contract,
                    variant=contract.variant,
                    what=f"endpoint '{endpoint}' is variant '{variant}', "
                    f"not '{contract.variant}'",
                    fix=f"compose the '{contract.variant}' variant of "
                    f"'{endpoint}', or declare variant='{variant}'",
                )
            )


def _validate_payload(
    contract: CouplingContract,
    producer: SimulationEngine,
    issues: list[ContractIssue],
) -> None:
    producer_keys = tuple(
        k for k in getattr(producer, "state_keys", ()) if isinstance(k, str) and k
    )
    seen: set[str] = set()
    for item in contract.payload:
        if item.key in seen:
            issues.append(
                _make_issue(
                    contract,
                    what=f"payload key '{item.key}' is declared more than once",
                    fix="declare each shared state key once",
                )
            )
        seen.add(item.key)

        if item.shape not in SUPPORTED_PAYLOAD_SHAPES:
            issues.append(
                _make_issue(
                    contract,
                    what=f"unsupported payload shape '{item.shape}' for key "
                    f"'{item.key}'",
                    fix="use one of the documented payload shapes",
                )
            )

        if producer_keys and item.key not in producer_keys:
            issues.append(
                _make_issue(
                    contract,
                    what=f"producer '{contract.producer}' does not declare "
                    f"payload key '{item.key}'",
                    fix="add the key to the producer's state vocabulary or "
                    "drop it from the contract",
                )
            )


def _validate_handoff(contract: CouplingContract, issues: list[ContractIssue]) -> None:
    if contract.timing not in SUPPORTED_TIMINGS:
        issues.append(
            _make_issue(
                contract,
                what=f"unsupported timing '{contract.timing}'",
                fix="use a supported timing",
            )
        )
    if contract.mechanism not in SUPPORTED_MECHANISMS:
        issues.append(
            _make_issue(
                contract,
                what=f"unsupported mechanism '{contract.mechanism}'",
                fix="use a supported mechanism",
            )
        )


def _validate_space(
    contract: CouplingContract,
    producer: SimulationEngine,
    consumer: SimulationEngine,
    issues: list[ContractIssue],
) -> None:
    producer_coord = _endpoint_coordinate_system(producer)
    consumer_coord = _endpoint_coordinate_system(consumer)

    if (
        contract.coordinate_system is not None
        and contract.coordinate_system not in {producer_coord, consumer_coord}
    ):
        issues.append(
            _make_issue(
                contract,
                what=f"contract declares coordinate system "
                f"'{contract.coordinate_system}'",
                fix="declare the endpoints' common coordinate system",
            )
        )
    if (
        producer_coord is not None
        and consumer_coord is not None
        and producer_coord != consumer_coord
    ):
        issues.append(
            _make_issue(
                contract,
                what=f"incompatible coordinate systems '{producer_coord}' vs "
                f"'{consumer_coord}'",
                fix="compose both endpoints in the same coordinate system",
            )
        )

    producer_grid = _endpoint_grid(producer)
    consumer_grid = _endpoint_grid(consumer)
    if (
        producer_grid is not None
        and consumer_grid is not None
        and producer_grid != consumer_grid
    ):
        issues.append(
            _make_issue(
                contract,
                what=f"grid mismatch: '{contract.producer}' is "
                f"{producer_grid}x{producer_grid} but '{contract.consumer}' is "
                f"{consumer_grid}x{consumer_grid}",
                fix="compose both endpoints on the same grid resolution",
            )
        )
    if contract.grid is not None:
        for endpoint, grid in (
            (contract.producer, producer_grid),
            (contract.consumer, consumer_grid),
        ):
            if grid is not None and grid != contract.grid:
                issues.append(
                    _make_issue(
                        contract,
                        what=f"endpoint '{endpoint}' grid {grid} does not match "
                        f"declared {contract.grid}",
                        fix="compose endpoints matching the declared grid",
                    )
                )


def _find_adapter(
    adapters: Sequence[SimulationEngine], component_id: str
) -> SimulationEngine | None:
    for adapter in adapters:
        if adapter.engine_id == component_id:
            return adapter
    return None


def _endpoint_variant(adapter: SimulationEngine) -> str | None:
    variant = getattr(adapter, "variant", None)
    return variant if isinstance(variant, str) and variant else None


def _endpoint_coordinate_system(adapter: SimulationEngine) -> str | None:
    coord = getattr(adapter, "coordinate_system", None)
    return coord if isinstance(coord, str) and coord else None


def _endpoint_grid(adapter: SimulationEngine) -> int | None:
    grid = getattr(adapter, "grid", None)
    return grid if isinstance(grid, int) and grid > 0 else None


def _make_issue(
    contract: CouplingContract,
    *,
    what: str,
    fix: str,
    variant: str | None = None,
) -> ContractIssue:
    return ContractIssue(
        contract=contract.name,
        producer=contract.producer,
        consumer=contract.consumer,
        variant=contract.variant if variant is None else variant,
        what=what,
        fix=fix,
    )


def _format_issue(issue: ContractIssue) -> str:
    variant = f", variant '{issue.variant}'" if issue.variant else ""
    return (
        f"contract '{issue.contract}' "
        f"({issue.producer} -> {issue.consumer}{variant}): "
        f"{issue.what}. {issue.fix}"
    )


def _issue_sort_key(
    issue: ContractIssue,
) -> tuple[str, str, str, str, str, str]:
    return (
        issue.contract,
        issue.producer,
        issue.consumer,
        issue.variant or "",
        issue.what,
        issue.fix,
    )


def _as_payload_item(item: PayloadItem | tuple[str, str]) -> PayloadItem:
    if isinstance(item, PayloadItem):
        return item
    return PayloadItem(key=item[0], shape=item[1])