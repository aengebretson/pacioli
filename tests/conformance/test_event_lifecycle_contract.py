"""Dependency-free validator for the contract-first O2 lifecycle fixtures.

This validates identities, causal structure, provenance, knowledge-cutoff chain
heads and expected-state shape. It deliberately does not reproduce position,
cash or settlement calculations.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "event-lifecycle"
CONTRACT_VERSION = "luca.event-lifecycle.v1"
TIMESTAMP = re.compile(
    r"^(?P<seconds>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?(?P<timezone>Z|[+-][0-9]{2}:[0-9]{2})$"
)
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ContractError(ValueError):
    def __init__(self, category: str, message: str, record_id: str | None = None):
        super().__init__(f"{category}: {message}")
        self.category = category
        self.record_id = record_id


def _fail(category: str, message: str, record_id: str | None = None) -> None:
    raise ContractError(category, message, record_id)


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("schema_shape", f"{context} must be an object")
    return value


def _objects(value: Any, context: str, *, nonempty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _fail("schema_shape", f"{context} must be an array of objects")
    if nonempty and not value:
        _fail("schema_shape", f"{context} must not be empty")
    return value


def _keys(
    value: dict[str, Any],
    required: set[str],
    context: str,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing or unknown:
        _fail(
            "schema_shape",
            f"{context} fields differ (missing={sorted(missing)}, unknown={sorted(unknown)})",
        )


def _string(value: dict[str, Any], field: str, context: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        _fail("schema_shape", f"{context}.{field} must be a non-empty string")
    return result


def _timestamp(value: Any, context: str) -> int:
    match = TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        _fail("schema_shape", f"{context} must be an ISO 8601 timestamp with timezone")
    try:
        zone = "+00:00" if match.group("timezone") == "Z" else match.group("timezone")
        parsed = datetime.fromisoformat(match.group("seconds") + zone)
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid timestamp: {error}")
    delta = parsed.astimezone(timezone.utc) - EPOCH
    fraction = match.group("fraction") or ""
    return (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + int(fraction.ljust(9, "0") or "0")
    )


def _date(value: Any, context: str) -> date:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        _fail("schema_shape", f"{context} must be an ISO 8601 date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid date: {error}")


def _decimal(value: Any, context: str) -> Decimal:
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        _fail("schema_shape", f"{context} must be a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as error:  # pragma: no cover - guarded by the regex
        _fail("schema_shape", f"{context} is not a decimal: {error}")


def _currency(value: Any, context: str) -> str:
    if not isinstance(value, str) or not CURRENCY.fullmatch(value):
        _fail("schema_shape", f"{context} must be a three-letter uppercase currency")
    return value


def _validate_source_records(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(
        _objects(document.get("source_records"), "source_records", nonempty=True)
    ):
        context = f"source_records[{index}]"
        _keys(
            source,
            {
                "source_record_id",
                "source_id",
                "observed_at",
                "source_event_at",
                "payload_hash",
                "kind",
            },
            context,
        )
        source_id = _string(source, "source_record_id", context)
        _string(source, "source_id", context)
        _string(source, "kind", context)
        _timestamp(source.get("observed_at"), f"{context}.observed_at")
        if source.get("source_event_at") is not None:
            _timestamp(source["source_event_at"], f"{context}.source_event_at")
        payload_hash = _object(source.get("payload_hash"), f"{context}.payload_hash")
        _keys(payload_hash, {"algorithm", "value"}, f"{context}.payload_hash")
        _string(payload_hash, "algorithm", f"{context}.payload_hash")
        _string(payload_hash, "value", f"{context}.payload_hash")
        if source_id in result:
            _fail("duplicate_identity", f"duplicate source_record_id {source_id!r}")
        result[source_id] = source
    return result


def _validate_event(value: Any, context: str) -> dict[str, Any]:
    event = _object(value, context)
    event_type = event.get("type")
    if event_type == "cash_movement":
        _keys(event, {"type", "currency", "amount"}, context)
        _currency(event.get("currency"), f"{context}.currency")
        _decimal(event.get("amount"), f"{context}.amount")
    elif event_type == "equity_trade":
        _keys(
            event,
            {
                "type",
                "instrument",
                "quantity",
                "price",
                "quote_currency",
                "settlement_date",
            },
            context,
        )
        _string(event, "instrument", context)
        if _decimal(event.get("quantity"), f"{context}.quantity") == 0:
            _fail("schema_shape", f"{context}.quantity must be non-zero")
        _decimal(event.get("price"), f"{context}.price")
        _currency(event.get("quote_currency"), f"{context}.quote_currency")
        _date(event.get("settlement_date"), f"{context}.settlement_date")
    else:
        _fail("schema_shape", f"{context}.type is not supported")
    return event


def _validate_records(
    document: dict[str, Any], source_records: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    records: dict[str, dict[str, Any]] = {}
    recorded_times: dict[str, int] = {}
    sequences: set[int] = set()
    economic_origins: set[str] = set()
    listed_sequences: list[int] = []

    for index, record in enumerate(
        _objects(document.get("records"), "records", nonempty=True)
    ):
        context = f"records[{index}]"
        common = {
            "record_id",
            "economic_event_id",
            "account",
            "action",
            "recorded_at",
            "acceptance_sequence",
            "effective_at",
            "provenance",
            "event",
        }
        action = record.get("action")
        if action in {"originate", "correct", "cancel", "reverse"}:
            causal = {
                "originate": set(),
                "correct": {"supersedes_record_id"},
                "cancel": {"supersedes_record_id"},
                "reverse": {"reverses_record_id"},
            }[action]
            _keys(record, common | causal, context)
        else:
            _fail("schema_shape", f"{context}.action is not supported")

        record_id = _string(record, "record_id", context)
        economic_id = _string(record, "economic_event_id", context)
        _string(record, "account", context)
        if record_id in records:
            _fail("duplicate_identity", f"duplicate record_id {record_id!r}")
        if action in {"originate", "reverse"}:
            if economic_id in economic_origins:
                _fail("duplicate_identity", f"duplicate economic origin {economic_id!r}")
            economic_origins.add(economic_id)

        sequence = record.get("acceptance_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            _fail("deterministic_ordering", f"{context}.acceptance_sequence must be positive")
        if sequence in sequences:
            _fail("deterministic_ordering", f"duplicate acceptance_sequence {sequence}")
        sequences.add(sequence)
        listed_sequences.append(sequence)
        recorded_times[record_id] = _timestamp(record.get("recorded_at"), f"{context}.recorded_at")

        provenance = _object(record.get("provenance"), f"{context}.provenance")
        _keys(
            provenance,
            {"source_record_ids", "transformation_name", "transformation_version"},
            f"{context}.provenance",
        )
        source_ids = provenance.get("source_record_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(not isinstance(item, str) or not item for item in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            _fail("schema_shape", f"{context}.provenance.source_record_ids must be unique strings")
        for source_id in source_ids:
            if source_id not in source_records:
                _fail(
                    "provenance_reference_missing",
                    f"{record_id!r} references unknown source record {source_id!r}",
                )
            observed_at = _timestamp(
                source_records[source_id]["observed_at"],
                f"source record {source_id!r}.observed_at",
            )
            if observed_at > recorded_times[record_id]:
                _fail("schema_shape", f"{record_id!r} predates source evidence {source_id!r}")
        _string(provenance, "transformation_name", f"{context}.provenance")
        _string(provenance, "transformation_version", f"{context}.provenance")

        if action == "cancel":
            if record.get("effective_at") is not None or record.get("event") is not None:
                _fail("schema_shape", f"{context} cancellation must have null effective_at and event")
        else:
            _timestamp(record.get("effective_at"), f"{context}.effective_at")
            _validate_event(record.get("event"), f"{context}.event")

        records[record_id] = record

    if listed_sequences != list(range(1, len(listed_sequences) + 1)):
        _fail(
            "deterministic_ordering",
            "records must be listed in contiguous acceptance_sequence order beginning at 1",
        )
    prior_time: int | None = None
    for record in document["records"]:
        current = recorded_times[record["record_id"]]
        if prior_time is not None and current < prior_time:
            _fail("deterministic_ordering", "recorded_at must not decrease with acceptance_sequence")
        prior_time = current

    return records, recorded_times


def _causal_target(record: dict[str, Any]) -> str | None:
    if record["action"] in {"correct", "cancel"}:
        return record["supersedes_record_id"]
    if record["action"] == "reverse":
        return record["reverses_record_id"]
    return None


def _validate_causality(
    records: dict[str, dict[str, Any]], recorded_times: dict[str, int]
) -> None:
    edges: dict[str, str] = {}
    for record_id, record in records.items():
        target_id = _causal_target(record)
        if target_id is None:
            continue
        if not isinstance(target_id, str) or not target_id or target_id not in records:
            _fail(
                "causal_reference_missing",
                f"{record_id!r} targets unavailable record {target_id!r}",
                record_id,
            )
        if target_id == record_id:
            _fail("causal_self_reference", f"{record_id!r} targets itself", record_id)
        edges[record_id] = target_id

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(record_id: str) -> None:
        if record_id in visiting:
            _fail("causal_cycle", f"cycle reaches {record_id!r}", record_id)
        if record_id in visited:
            return
        visiting.add(record_id)
        target_id = edges.get(record_id)
        if target_id is not None:
            visit(target_id)
        visiting.remove(record_id)
        visited.add(record_id)

    for record_id in records:
        visit(record_id)

    successors: dict[str, str] = {}
    for record_id, target_id in edges.items():
        record = records[record_id]
        target = records[target_id]
        record_key = (recorded_times[record_id], record["acceptance_sequence"])
        target_key = (recorded_times[target_id], target["acceptance_sequence"])
        if target_key >= record_key:
            _fail(
                "causal_reference_unavailable",
                f"{record_id!r} targets record {target_id!r} not yet available",
                record_id,
            )
        if record["account"] != target["account"]:
            _fail(
                "incompatible_account",
                f"{record_id!r} and {target_id!r} have different accounts",
                record_id,
            )
        if target_id in successors:
            _fail(
                "conflicting_lifecycle_successor",
                f"{target_id!r} has successors {successors[target_id]!r} and {record_id!r}",
                record_id,
            )
        successors[target_id] = record_id
        _validate_relationship(record, target)

    for record_id in records:
        root_id = record_id
        while root_id in edges:
            root_id = edges[root_id]
        if records[root_id]["action"] not in {"originate", "reverse"}:
            _fail(
                "incompatible_event_relationship",
                f"{record_id!r} does not descend from an origin or reversal",
                record_id,
            )


def _validate_relationship(record: dict[str, Any], target: dict[str, Any]) -> None:
    action = record["action"]
    record_id = record["record_id"]
    if target["action"] in {"cancel", "reverse"}:
        _fail(
            "incompatible_event_relationship",
            f"a {target['action']} record is terminal",
            record_id,
        )
    if action in {"correct", "cancel"}:
        if record["economic_event_id"] != target["economic_event_id"]:
            _fail(
                "incompatible_event_relationship",
                "supersession must retain economic_event_id",
                record_id,
            )
    elif record["economic_event_id"] == target["economic_event_id"]:
        _fail(
            "incompatible_event_relationship",
            "reversal must use a new economic_event_id",
            record_id,
        )

    if action == "cancel":
        return
    event = record["event"]
    target_event = target["event"]
    if target_event is None or event["type"] != target_event["type"]:
        _fail(
            "incompatible_event_relationship",
            "lifecycle event types differ",
            record_id,
        )

    if event["type"] == "cash_movement":
        if event["currency"] != target_event["currency"]:
            _fail("incompatible_event_relationship", "cash currencies differ", record_id)
        if action == "reverse" and _decimal(event["amount"], "reversal amount") != -_decimal(
            target_event["amount"], "target amount"
        ):
            _fail(
                "incompatible_event_relationship",
                "cash reversal is not the exact opposite",
                record_id,
            )
    else:
        stable_fields = ["instrument", "quote_currency"]
        if any(event[field] != target_event[field] for field in stable_fields):
            _fail(
                "incompatible_event_relationship",
                "equity relationship changes a stable term",
                record_id,
            )
        if action == "reverse" and _decimal(
            event["price"], "reversal price"
        ) != _decimal(target_event["price"], "target price"):
            _fail(
                "incompatible_event_relationship",
                "trade reversal price differs from its target",
                record_id,
            )
        if action == "reverse" and _decimal(
            event["quantity"], "reversal quantity"
        ) != -_decimal(target_event["quantity"], "target quantity"):
            _fail(
                "incompatible_event_relationship",
                "trade reversal is not the exact opposite",
                record_id,
            )

    if action == "reverse":
        record_effective = _timestamp(record["effective_at"], "reversal effective_at")
        target_effective = _timestamp(target["effective_at"], "target effective_at")
        if record_effective < target_effective:
            _fail(
                "incompatible_event_relationship",
                "reversal predates its target economically",
                record_id,
            )


def _validate_lineage(
    value: Any,
    context: str,
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
    expected_record_ids: list[str],
) -> None:
    lineage_record_ids: list[str] = []
    for index, item in enumerate(_objects(value, context, nonempty=True)):
        item_context = f"{context}[{index}]"
        _keys(item, {"record_id", "source_record_ids"}, item_context)
        record_id = _string(item, "record_id", item_context)
        source_ids = item.get("source_record_ids")
        if record_id not in records or record_id in lineage_record_ids:
            _fail("expected_output", f"{item_context} has unknown or duplicate record_id")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(source_id not in source_records for source_id in source_ids)
        ):
            _fail("expected_output", f"{item_context}.source_record_ids are invalid")
        if source_ids != records[record_id]["provenance"]["source_record_ids"]:
            _fail(
                "expected_output",
                f"{item_context}.source_record_ids do not match immutable provenance",
            )
        lineage_record_ids.append(record_id)
    if lineage_record_ids != expected_record_ids:
        _fail("expected_output", f"{context} must follow record_ids in causal order")


def _validate_chain_path(
    record_ids: Any,
    context: str,
    records: dict[str, dict[str, Any]],
) -> list[str]:
    if (
        not isinstance(record_ids, list)
        or not record_ids
        or len(record_ids) != len(set(record_ids))
        or any(record_id not in records for record_id in record_ids)
    ):
        _fail("expected_output", f"{context} must contain unique known records")
    if records[record_ids[0]]["action"] not in {"originate", "reverse"}:
        _fail("expected_output", f"{context} must begin with an origin or reversal")
    for predecessor_id, successor_id in zip(record_ids, record_ids[1:]):
        if _causal_target(records[successor_id]) != predecessor_id:
            _fail("expected_output", f"{context} is not a direct causal chain")
    return record_ids


def _validate_active_chain(
    chain: dict[str, Any],
    context: str,
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> None:
    _keys(
        chain,
        {
            "economic_event_id",
            "record_ids",
            "active_record_id",
            "reverses_record_id",
            "source_lineage",
        },
        context,
    )
    economic_id = _string(chain, "economic_event_id", context)
    active_id = _string(chain, "active_record_id", context)
    record_ids = _validate_chain_path(chain.get("record_ids"), f"{context}.record_ids", records)
    if active_id != record_ids[-1] or records[active_id]["action"] == "cancel":
        _fail("expected_output", f"{context}.active_record_id must be the active chain head")
    if any(records[record_id]["economic_event_id"] != economic_id for record_id in record_ids):
        _fail("expected_output", f"{context}.economic_event_id does not match its records")
    reverses = chain.get("reverses_record_id")
    if reverses is not None and (not isinstance(reverses, str) or reverses not in records):
        _fail("expected_output", f"{context}.reverses_record_id is invalid")
    root_reverses = (
        records[record_ids[0]].get("reverses_record_id")
        if records[record_ids[0]]["action"] == "reverse"
        else None
    )
    if reverses != root_reverses:
        _fail("expected_output", f"{context}.reverses_record_id does not match its root")
    _validate_lineage(
        chain.get("source_lineage"),
        f"{context}.source_lineage",
        records,
        source_records,
        record_ids,
    )


def _validate_inactive_chain(
    chain: dict[str, Any],
    context: str,
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> None:
    _keys(
        chain,
        {
            "economic_event_id",
            "record_ids",
            "terminal_record_id",
            "disposition",
            "source_lineage",
        },
        context,
    )
    economic_id = _string(chain, "economic_event_id", context)
    terminal_id = _string(chain, "terminal_record_id", context)
    record_ids = _validate_chain_path(chain.get("record_ids"), f"{context}.record_ids", records)
    if chain.get("disposition") != "cancelled":
        _fail("expected_output", f"{context}.disposition must be cancelled")
    if terminal_id != record_ids[-1] or records[terminal_id]["action"] != "cancel":
        _fail("expected_output", f"{context}.terminal_record_id must be a cancellation head")
    if any(records[record_id]["economic_event_id"] != economic_id for record_id in record_ids):
        _fail("expected_output", f"{context}.economic_event_id does not match its records")
    _validate_lineage(
        chain.get("source_lineage"),
        f"{context}.source_lineage",
        records,
        source_records,
        record_ids,
    )


def _derive_known_chains(
    records: dict[str, dict[str, Any]],
    recorded_times: dict[str, int],
    recorded_through: int,
) -> dict[str, dict[str, Any]]:
    """Resolve lifecycle paths selected by knowledge time, without projecting them."""
    selected_by_economic_id: dict[str, list[str]] = {}
    selected_records = sorted(
        (
            record
            for record_id, record in records.items()
            if recorded_times[record_id] <= recorded_through
        ),
        key=lambda record: record["acceptance_sequence"],
    )
    for record in selected_records:
        selected_by_economic_id.setdefault(record["economic_event_id"], []).append(
            record["record_id"]
        )

    result: dict[str, dict[str, Any]] = {}
    for economic_id, selected_ids in selected_by_economic_id.items():
        roots = [
            record_id
            for record_id in selected_ids
            if records[record_id]["action"] in {"originate", "reverse"}
        ]
        if len(roots) != 1:
            _fail(
                "expected_output",
                f"knowledge-selected economic event {economic_id!r} has no unique root",
            )

        successors: dict[str, str] = {}
        for record_id in selected_ids:
            record = records[record_id]
            if record["action"] in {"correct", "cancel"}:
                successors[record["supersedes_record_id"]] = record_id

        path = [roots[0]]
        while path[-1] in successors:
            path.append(successors[path[-1]])
        if set(path) != set(selected_ids):
            _fail(
                "expected_output",
                f"knowledge-selected economic event {economic_id!r} is not one complete chain",
            )

        head_id = path[-1]
        result[economic_id] = {
            "record_ids": path,
            "head_id": head_id,
            "active": records[head_id]["action"] != "cancel",
        }
    return result


def _validate_chains_at_recorded_cutoff(
    active_chains: list[dict[str, Any]],
    inactive_chains: list[dict[str, Any]],
    context: str,
    records: dict[str, dict[str, Any]],
    recorded_times: dict[str, int],
    recorded_through: int,
) -> None:
    listed = {
        chain["economic_event_id"]: (chain, True) for chain in active_chains
    }
    listed.update(
        {chain["economic_event_id"]: (chain, False) for chain in inactive_chains}
    )
    derived = _derive_known_chains(records, recorded_times, recorded_through)

    if set(listed) != set(derived):
        missing = sorted(set(derived) - set(listed))
        unexpected = sorted(set(listed) - set(derived))
        _fail(
            "expected_output",
            f"{context} lifecycle chains differ at recorded_through "
            f"(missing={missing}, unexpected={unexpected})",
        )

    for economic_id, expected in derived.items():
        chain, listed_active = listed[economic_id]
        if listed_active != expected["active"]:
            _fail(
                "expected_output",
                f"{context} lifecycle disposition for {economic_id!r} does not match "
                "the recorded_through head",
            )
        if chain["record_ids"] != expected["record_ids"]:
            _fail(
                "expected_output",
                f"{context} lifecycle path for {economic_id!r} does not contain every "
                "record selected by recorded_through",
            )
        head_field = "active_record_id" if listed_active else "terminal_record_id"
        if chain[head_field] != expected["head_id"]:
            _fail(
                "expected_output",
                f"{context}.{head_field} for {economic_id!r} does not match the "
                "recorded_through head",
            )


def _validate_projection_records(expected: dict[str, Any], context: str) -> None:
    position_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(_objects(expected.get("positions"), f"{context}.positions")):
        item_context = f"{context}.positions[{index}]"
        _keys(item, {"account", "instrument", "quantity"}, item_context)
        key = (_string(item, "account", item_context), _string(item, "instrument", item_context))
        _decimal(item.get("quantity"), f"{item_context}.quantity")
        if key in position_keys:
            _fail("expected_output", f"duplicate expected position {key!r}")
        position_keys.add(key)

    cash_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(_objects(expected.get("settled_cash"), f"{context}.settled_cash")):
        item_context = f"{context}.settled_cash[{index}]"
        _keys(item, {"account", "currency", "amount"}, item_context)
        key = (_string(item, "account", item_context), _currency(item.get("currency"), f"{item_context}.currency"))
        _decimal(item.get("amount"), f"{item_context}.amount")
        if key in cash_keys:
            _fail("expected_output", f"duplicate expected cash balance {key!r}")
        cash_keys.add(key)

    settlement_keys: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(
        _objects(
            expected.get("open_settlement_obligations"),
            f"{context}.open_settlement_obligations",
        )
    ):
        item_context = f"{context}.open_settlement_obligations[{index}]"
        _keys(
            item,
            {"account", "settlement_date", "currency", "direction", "amount"},
            item_context,
        )
        account = _string(item, "account", item_context)
        settlement_date = item.get("settlement_date")
        _date(settlement_date, f"{item_context}.settlement_date")
        currency = _currency(item.get("currency"), f"{item_context}.currency")
        direction = item.get("direction")
        if direction not in {"payable", "receivable"}:
            _fail("expected_output", f"{item_context}.direction is invalid")
        if _decimal(item.get("amount"), f"{item_context}.amount") <= 0:
            _fail("expected_output", f"{item_context}.amount must be positive")
        key = (account, settlement_date, currency, direction)
        if key in settlement_keys:
            _fail("expected_output", f"duplicate expected settlement {key!r}")
        settlement_keys.add(key)


def _validate_evaluations(
    document: dict[str, Any],
    records: dict[str, dict[str, Any]],
    recorded_times: dict[str, int],
    source_records: dict[str, dict[str, Any]],
) -> None:
    names: set[str] = set()
    for index, evaluation in enumerate(
        _objects(document.get("evaluations"), "evaluations", nonempty=True)
    ):
        context = f"evaluations[{index}]"
        _keys(evaluation, {"name", "context", "expected"}, context)
        name = _string(evaluation, "name", context)
        if name in names:
            _fail("duplicate_identity", f"duplicate evaluation name {name!r}")
        names.add(name)
        projection_context = _object(evaluation.get("context"), f"{context}.context")
        _keys(
            projection_context,
            {"economic_as_of", "recorded_through", "settlement_as_of_date"},
            f"{context}.context",
        )
        _timestamp(projection_context.get("economic_as_of"), f"{context}.context.economic_as_of")
        recorded_through = _timestamp(
            projection_context.get("recorded_through"),
            f"{context}.context.recorded_through",
        )
        _date(
            projection_context.get("settlement_as_of_date"),
            f"{context}.context.settlement_as_of_date",
        )

        expected = _object(evaluation.get("expected"), f"{context}.expected")
        _keys(
            expected,
            {
                "active_event_chains",
                "inactive_event_chains",
                "positions",
                "settled_cash",
                "open_settlement_obligations",
                "journals",
                "arithmetic",
            },
            f"{context}.expected",
        )
        active_chains = _objects(
            expected["active_event_chains"],
            f"{context}.expected.active_event_chains",
        )
        inactive_chains = _objects(
            expected["inactive_event_chains"],
            f"{context}.expected.inactive_event_chains",
        )
        for chain_index, chain in enumerate(active_chains):
            _validate_active_chain(
                chain,
                f"{context}.expected.active_event_chains[{chain_index}]",
                records,
                source_records,
            )
        for chain_index, chain in enumerate(inactive_chains):
            _validate_inactive_chain(
                chain,
                f"{context}.expected.inactive_event_chains[{chain_index}]",
                records,
                source_records,
            )
        chain_ids = [
            chain["economic_event_id"] for chain in active_chains + inactive_chains
        ]
        if len(chain_ids) != len(set(chain_ids)):
            _fail("expected_output", f"{context}.expected repeats an economic event chain")
        for chain in active_chains + inactive_chains:
            for record_id in chain["record_ids"]:
                record_time = _timestamp(
                    records[record_id]["recorded_at"],
                    f"record {record_id!r}.recorded_at",
                )
                if record_time > recorded_through:
                    _fail(
                        "expected_output",
                        f"{context}.expected includes {record_id!r} after recorded_through",
                    )
        _validate_chains_at_recorded_cutoff(
            active_chains,
            inactive_chains,
            f"{context}.expected",
            records,
            recorded_times,
            recorded_through,
        )
        _validate_projection_records(expected, f"{context}.expected")
        journals = _object(expected.get("journals"), f"{context}.expected.journals")
        _keys(journals, {"status", "reason"}, f"{context}.expected.journals")
        if journals.get("status") != "deferred":
            _fail("expected_output", f"{context}.expected.journals.status must be deferred")
        _string(journals, "reason", f"{context}.expected.journals")
        arithmetic = expected.get("arithmetic")
        if (
            not isinstance(arithmetic, list)
            or not arithmetic
            or any(not isinstance(item, str) or not item for item in arithmetic)
        ):
            _fail("expected_output", f"{context}.expected.arithmetic must contain notes")


def validate_contract(document: dict[str, Any]) -> None:
    _keys(
        document,
        {
            "contract_version",
            "name",
            "description",
            "valid",
            "source_records",
            "records",
        },
        "document",
        {"evaluations", "expected_diagnostic"},
    )
    if document.get("contract_version") != CONTRACT_VERSION:
        _fail("schema_shape", f"contract_version must be {CONTRACT_VERSION!r}")
    _string(document, "name", "document")
    _string(document, "description", "document")
    if not isinstance(document.get("valid"), bool):
        _fail("schema_shape", "document.valid must be boolean")
    if document["valid"]:
        if set(document) != {
            "contract_version",
            "name",
            "description",
            "valid",
            "source_records",
            "records",
            "evaluations",
        }:
            _fail("schema_shape", "valid document must contain evaluations only")
    else:
        if set(document) != {
            "contract_version",
            "name",
            "description",
            "valid",
            "source_records",
            "records",
            "expected_diagnostic",
        }:
            _fail("schema_shape", "invalid document must contain expected_diagnostic only")
        diagnostic = _object(document["expected_diagnostic"], "expected_diagnostic")
        _keys(diagnostic, {"category", "record_id"}, "expected_diagnostic")
        _string(diagnostic, "category", "expected_diagnostic")
        _string(diagnostic, "record_id", "expected_diagnostic")

    source_records = _validate_source_records(document)
    records, recorded_times = _validate_records(document, source_records)
    _validate_causality(records, recorded_times)
    if document["valid"]:
        _validate_evaluations(document, records, recorded_times, source_records)


def load_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError("json_parse", f"{path}: {error}") from error
    return _object(document, str(path))


class EventLifecycleContractTest(unittest.TestCase):
    def test_recorded_order_preserves_nanosecond_precision(self):
        self.assertLess(
            _timestamp("2026-01-01T00:00:00.000000001Z", "earlier"),
            _timestamp("2026-01-01T00:00:00.000000002Z", "later"),
        )

    def test_every_json_fixture_parses_independently(self):
        paths = sorted(FIXTURE_ROOT.glob("*.json"))
        self.assertEqual(len(paths), 10)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertIsInstance(load_document(path), dict)

    def test_valid_fixtures_satisfy_contract(self):
        paths = sorted(FIXTURE_ROOT.glob("valid-*.json"))
        self.assertEqual(
            {path.name for path in paths},
            {"valid-equity-reversal-correction.json", "valid-late-cash-correction.json"},
        )
        for path in paths:
            with self.subTest(path=path.name):
                document = load_document(path)
                self.assertTrue(document["valid"])
                validate_contract(document)

    def test_invalid_fixtures_produce_stable_diagnostics(self):
        paths = sorted(FIXTURE_ROOT.glob("invalid-*.json"))
        self.assertEqual(len(paths), 8)
        for path in paths:
            with self.subTest(path=path.name):
                document = load_document(path)
                self.assertFalse(document["valid"])
                diagnostic = document["expected_diagnostic"]
                with self.assertRaises(ContractError) as raised:
                    validate_contract(document)
                self.assertEqual(raised.exception.category, diagnostic["category"])
                self.assertEqual(raised.exception.record_id, diagnostic["record_id"])

    def test_duplicate_record_identity_is_rejected(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        mutated["records"][1]["record_id"] = mutated["records"][0]["record_id"]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "duplicate_identity")

    def test_missing_provenance_reference_is_rejected(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        mutated["records"][0]["provenance"]["source_record_ids"] = ["not-present"]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "provenance_reference_missing")

    def test_duplicate_ordering_input_is_rejected(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        mutated["records"][1]["acceptance_sequence"] = 1
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "deterministic_ordering")

    def test_missing_evaluation_context_is_rejected(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        del mutated["evaluations"][0]["context"]["recorded_through"]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "schema_shape")

    def test_malformed_expected_output_is_rejected_without_projecting(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        mutated["evaluations"][0]["expected"]["positions"] = [{"account": "fund-a"}]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "schema_shape")

    def test_expected_chain_cannot_omit_known_correction(self):
        document = load_document(FIXTURE_ROOT / "valid-late-cash-correction.json")
        mutated = copy.deepcopy(document)
        chain = mutated["evaluations"][1]["expected"]["active_event_chains"][0]
        chain["record_ids"] = ["cash-record-v1"]
        chain["active_record_id"] = "cash-record-v1"
        chain["source_lineage"] = chain["source_lineage"][:1]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "expected_output")

    def test_expected_chains_cannot_omit_known_economic_identity(self):
        document = load_document(FIXTURE_ROOT / "valid-equity-reversal-correction.json")
        mutated = copy.deepcopy(document)
        mutated["evaluations"][0]["expected"]["active_event_chains"] = [
            mutated["evaluations"][0]["expected"]["active_event_chains"][0]
        ]
        with self.assertRaises(ContractError) as raised:
            validate_contract(mutated)
        self.assertEqual(raised.exception.category, "expected_output")

    def test_reversal_price_uses_decimal_value_equality(self):
        document = load_document(FIXTURE_ROOT / "valid-equity-reversal-correction.json")
        mutated = copy.deepcopy(document)
        mutated["records"][3]["event"]["price"] = "55.0"
        validate_contract(mutated)


if __name__ == "__main__":
    unittest.main()
