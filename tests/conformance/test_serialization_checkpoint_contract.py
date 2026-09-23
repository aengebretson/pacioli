"""Dependency-free validator for O3 serialization/checkpoint fixtures.

This module validates declared canonical values, digests, checkpoint compatibility,
prefix continuity, lifecycle relationships, and context-selected lifecycle heads. It
intentionally does not calculate positions, cash, or settlement obligations: expected
financial state is data produced by the authoritative engine and equality between
execution modes is checked as a contract assertion.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import struct
import unittest
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "serialization-checkpoints"
FIXTURE_FILES = (
    FIXTURE_ROOT / "canonical-vectors.json",
    FIXTURE_ROOT / "valid-append.json",
    FIXTURE_ROOT / "late-correction.json",
)

SUPPORTED = {
    "fixture": "luca.serialization-checkpoint-fixture.v1",
    "bytes": "luca.canonical-bytes.v1",
    "provenance": "luca.provenance.v1",
    "event_header": "luca.event-header.v1",
    "event": "luca.economic-event.v1",
    "money": "luca.money.v1",
    "quantity": "luca.quantity.v1",
    "price": "luca.price.v1",
    "record": "luca.lifecycle-record.v1",
    "record_sequence": "luca.lifecycle-record-sequence.v1",
    "position": "luca.position-balance.v1",
    "cash": "luca.cash-balance.v1",
    "settlement": "luca.settlement-obligation.v1",
    "state": "luca.portfolio-state.v1",
    "context": "luca.evaluation-context.v1",
    "manifest": "luca.checkpoint-manifest.v1",
    "resume": "luca.checkpoint-resume.v1",
}

CANONICAL_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{9}Z$"
)
CANONICAL_INTEGER = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
CANONICAL_UNSIGNED_INTEGER = re.compile(r"^(?:0|[1-9][0-9]*)$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
U64_MAX = (1 << 64) - 1


class ContractError(ValueError):
    def __init__(self, category: str, message: str):
        super().__init__(f"{category}: {message}")
        self.category = category


def _fail(category: str, message: str) -> None:
    raise ContractError(category, message)


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("schema_shape", f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream, object_pairs_hook=_pairs_no_duplicates)
    return _object(value, str(path))


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
    value: dict[str, Any], required: set[str], context: str, optional: set[str] | None = None
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing or unknown:
        _fail(
            "schema_shape",
            f"{context} fields differ (missing={sorted(missing)}, unknown={sorted(unknown)})",
        )


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail("schema_shape", f"{context} must be a non-empty string without NUL")
    if unicodedata.normalize("NFC", value) != value:
        _fail("canonical_encoding", f"{context} must be NFC-normalized")
    return value


def _version(value: Any, expected: str, context: str) -> str:
    actual = _string(value, context)
    if actual != expected:
        _fail("unsupported_version", f"{context} is {actual!r}, expected {expected!r}")
    return actual


def _integer(value: Any, context: str, *, minimum: int = I64_MIN) -> int:
    if not isinstance(value, str) or CANONICAL_INTEGER.fullmatch(value) is None:
        _fail("canonical_encoding", f"{context} must be a canonical decimal integer string")
    result = int(value)
    if result < minimum or result > I64_MAX:
        _fail("schema_shape", f"{context} is outside the signed 64-bit range")
    return result


def _unsigned_integer(value: Any, context: str, *, minimum: int = 0) -> int:
    if not isinstance(value, str) or CANONICAL_UNSIGNED_INTEGER.fullmatch(value) is None:
        _fail(
            "canonical_encoding",
            f"{context} must be a canonical unsigned decimal integer string",
        )
    result = int(value)
    if result < minimum or result > U64_MAX:
        _fail("schema_shape", f"{context} is outside the unsigned 64-bit range")
    return result


def _timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or CANONICAL_TIMESTAMP.fullmatch(value) is None:
        _fail("canonical_encoding", f"{context} must be UTC with exactly nine fractional digits")
    try:
        datetime.fromisoformat(value[:26] + "+00:00")
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid timestamp: {error}")
    return value


def _date(value: Any, context: str) -> str:
    if not isinstance(value, str):
        _fail("schema_shape", f"{context} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid date: {error}")
    if parsed.isoformat() != value:
        _fail("canonical_encoding", f"{context} must use YYYY-MM-DD")
    return value


def _digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be a lowercase SHA-256 hex digest")
    return value


def _pack_length(length: int, context: str) -> bytes:
    if length > 0xFFFFFFFF:
        _fail("canonical_encoding", f"{context} exceeds the v1 32-bit length limit")
    return struct.pack(">I", length)


def _encode_node(value: Any) -> bytes:
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x01"
    if value is True:
        return b"\x02"
    if isinstance(value, int) and not isinstance(value, bool):
        if value < I64_MIN or value > I64_MAX:
            _fail("canonical_encoding", "integer is outside the signed 64-bit range")
        return b"\x03" + struct.pack(">q", value)
    if isinstance(value, float):
        _fail("canonical_encoding", "binary floating-point values are forbidden")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            _fail("canonical_encoding", "text must be NFC-normalized")
        encoded = value.encode("utf-8")
        return b"\x04" + _pack_length(len(encoded), "text") + encoded
    if isinstance(value, list):
        return b"\x05" + _pack_length(len(value), "array") + b"".join(
            _encode_node(item) for item in value
        )
    if isinstance(value, dict):
        encoded_items: list[tuple[bytes, bytes]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("canonical_encoding", "map keys must be text")
            if unicodedata.normalize("NFC", key) != key:
                _fail("canonical_encoding", "map keys must be NFC-normalized")
            encoded_key = key.encode("utf-8")
            encoded_items.append((encoded_key, _encode_node(item)))
        encoded_items.sort(key=lambda item: item[0])
        body = b"".join(
            _pack_length(len(key), "map key") + key + item
            for key, item in encoded_items
        )
        return b"\x06" + _pack_length(len(encoded_items), "map") + body
    _fail("canonical_encoding", f"unsupported canonical value type {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Encode one value using the explicitly versioned LCB1 format."""

    return b"LCB1" + _encode_node(value)


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class _Decoder:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def take(self, count: int) -> bytes:
        end = self.offset + count
        if end > len(self.data):
            _fail("canonical_encoding", "truncated canonical bytes")
        result = self.data[self.offset:end]
        self.offset = end
        return result

    def length(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def node(self) -> Any:
        tag = self.take(1)
        if tag == b"\x00":
            return None
        if tag == b"\x01":
            return False
        if tag == b"\x02":
            return True
        if tag == b"\x03":
            return struct.unpack(">q", self.take(8))[0]
        if tag == b"\x04":
            try:
                result = self.take(self.length()).decode("utf-8")
            except UnicodeDecodeError as error:
                _fail("canonical_encoding", f"text is not valid UTF-8: {error}")
            if unicodedata.normalize("NFC", result) != result:
                _fail("canonical_encoding", "decoded text is not NFC-normalized")
            return result
        if tag == b"\x05":
            return [self.node() for _ in range(self.length())]
        if tag == b"\x06":
            result: dict[str, Any] = {}
            previous: bytes | None = None
            for _ in range(self.length()):
                raw_key = self.take(self.length())
                if previous is not None and raw_key <= previous:
                    _fail("canonical_encoding", "map keys are not strictly byte-sorted")
                previous = raw_key
                try:
                    key = raw_key.decode("utf-8")
                except UnicodeDecodeError as error:
                    _fail("canonical_encoding", f"map key is not valid UTF-8: {error}")
                if unicodedata.normalize("NFC", key) != key:
                    _fail("canonical_encoding", "decoded map key is not NFC-normalized")
                result[key] = self.node()
            return result
        _fail("canonical_encoding", f"unknown canonical tag 0x{tag.hex()}")


def decode_canonical(data: bytes) -> Any:
    if not data.startswith(b"LCB1"):
        _fail("unsupported_version", "canonical bytes do not start with LCB1")
    decoder = _Decoder(data[4:])
    value = decoder.node()
    if decoder.offset != len(decoder.data):
        _fail("canonical_encoding", "trailing canonical bytes")
    return value


def _fixed(value: Any, schema: str, scale: str, context: str) -> dict[str, Any]:
    fixed = _object(value, context)
    _keys(fixed, {"schema_version", "scale", "scaled_value"}, context)
    _version(fixed["schema_version"], schema, f"{context}.schema_version")
    if fixed["scale"] != scale:
        _fail("schema_shape", f"{context}.scale must be {scale!r}")
    _integer(fixed["scaled_value"], f"{context}.scaled_value")
    return fixed


def _money(value: Any, context: str, *, positive: bool = False) -> dict[str, Any]:
    money = _object(value, context)
    _keys(money, {"schema_version", "currency", "scale", "scaled_value"}, context)
    _version(money["schema_version"], SUPPORTED["money"], f"{context}.schema_version")
    if not isinstance(money["currency"], str) or CURRENCY.fullmatch(money["currency"]) is None:
        _fail("schema_shape", f"{context}.currency must be three uppercase ASCII letters")
    if money["scale"] != "6":
        _fail("schema_shape", f"{context}.scale must be '6'")
    minimum = 1 if positive else I64_MIN
    _integer(money["scaled_value"], f"{context}.scaled_value", minimum=minimum)
    return money


def _provenance(value: Any, context: str) -> dict[str, Any]:
    provenance = _object(value, context)
    _keys(
        provenance,
        {
            "schema_version",
            "source_record_ids",
            "transformation_name",
            "transformation_version",
            "transformation_metadata",
        },
        context,
    )
    _version(provenance["schema_version"], SUPPORTED["provenance"], f"{context}.schema_version")
    source_ids = provenance["source_record_ids"]
    if not isinstance(source_ids, list) or not source_ids:
        _fail("schema_shape", f"{context}.source_record_ids must be a non-empty array")
    for index, source_id in enumerate(source_ids):
        _string(source_id, f"{context}.source_record_ids[{index}]")
    if len(source_ids) != len(set(source_ids)):
        _fail("duplicate_identity", f"{context}.source_record_ids contains duplicates")
    _string(provenance["transformation_name"], f"{context}.transformation_name")
    _string(provenance["transformation_version"], f"{context}.transformation_version")
    metadata = provenance["transformation_metadata"]
    if metadata is not None:
        if not isinstance(metadata, str) or "\x00" in metadata:
            _fail("schema_shape", f"{context}.transformation_metadata must be text without NUL")
        if unicodedata.normalize("NFC", metadata) != metadata:
            _fail("canonical_encoding", f"{context}.transformation_metadata must be NFC-normalized")
        if len(metadata.encode("utf-8")) > 1024:
            _fail("schema_shape", f"{context}.transformation_metadata exceeds 1024 bytes")
    return provenance


def _event(value: Any, context: str) -> dict[str, Any]:
    event = _object(value, context)
    variant = event.get("variant")
    common = {"schema_version", "variant", "header"}
    if variant == "cash_movement":
        _keys(event, common | {"amount"}, context)
    elif variant == "equity_trade":
        _keys(
            event,
            common | {"instrument", "quantity", "price", "quote_currency", "settlement_date"},
            context,
        )
    else:
        _fail("schema_shape", f"{context}.variant is unsupported")
    _version(event["schema_version"], SUPPORTED["event"], f"{context}.schema_version")

    header = _object(event["header"], f"{context}.header")
    _keys(header, {"schema_version", "record_id", "account", "effective_at", "provenance"}, f"{context}.header")
    _version(header["schema_version"], SUPPORTED["event_header"], f"{context}.header.schema_version")
    _string(header["record_id"], f"{context}.header.record_id")
    _string(header["account"], f"{context}.header.account")
    _timestamp(header["effective_at"], f"{context}.header.effective_at")
    _provenance(header["provenance"], f"{context}.header.provenance")

    if variant == "cash_movement":
        _money(event["amount"], f"{context}.amount")
    else:
        _string(event["instrument"], f"{context}.instrument")
        quantity = _fixed(event["quantity"], SUPPORTED["quantity"], "8", f"{context}.quantity")
        if _integer(quantity["scaled_value"], f"{context}.quantity.scaled_value") == 0:
            _fail("schema_shape", f"{context}.quantity must be non-zero")
        _fixed(event["price"], SUPPORTED["price"], "8", f"{context}.price")
        if not isinstance(event["quote_currency"], str) or CURRENCY.fullmatch(event["quote_currency"]) is None:
            _fail("schema_shape", f"{context}.quote_currency is invalid")
        _date(event["settlement_date"], f"{context}.settlement_date")
    return event


def _record(value: Any, context: str) -> dict[str, Any]:
    record = _object(value, context)
    _keys(
        record,
        {
            "schema_version",
            "record_id",
            "economic_event_id",
            "account",
            "action",
            "recorded_at",
            "acceptance_sequence",
            "causal_record_id",
            "provenance",
            "event",
        },
        context,
    )
    _version(record["schema_version"], SUPPORTED["record"], f"{context}.schema_version")
    _string(record["record_id"], f"{context}.record_id")
    _string(record["economic_event_id"], f"{context}.economic_event_id")
    _string(record["account"], f"{context}.account")
    action = record["action"]
    if action not in {"originate", "correct", "cancel", "reverse"}:
        _fail("schema_shape", f"{context}.action is unsupported")
    _timestamp(record["recorded_at"], f"{context}.recorded_at")
    _unsigned_integer(
        record["acceptance_sequence"], f"{context}.acceptance_sequence", minimum=1
    )
    causal = record["causal_record_id"]
    if action == "originate":
        if causal is not None:
            _fail("schema_shape", f"{context}.causal_record_id must be null for originate")
    elif causal is None:
        _fail("schema_shape", f"{context}.causal_record_id is required for {action}")
    else:
        _string(causal, f"{context}.causal_record_id")
    provenance = _provenance(record["provenance"], f"{context}.provenance")
    event = record["event"]
    if action == "cancel":
        if event is not None:
            _fail("schema_shape", f"{context}.event must be null for cancel")
    else:
        event = _event(event, f"{context}.event")
        header = event["header"]
        if (
            header["record_id"] != record["record_id"]
            or header["account"] != record["account"]
            or header["provenance"] != provenance
        ):
            _fail("schema_shape", f"{context} record fields disagree with its event header")
    return record


def _record_sequence(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": SUPPORTED["record_sequence"], "records": records}


def _scaled_value(value: dict[str, Any]) -> int:
    return int(value["scaled_value"])


def _validate_relationship(
    record: dict[str, Any], target: dict[str, Any], context: str
) -> None:
    action = record["action"]
    if target["action"] in {"cancel", "reverse"}:
        _fail(
            "incompatible_event_relationship",
            f"{context} targets terminal {target['action']} record {target['record_id']!r}",
        )
    if action in {"correct", "cancel"}:
        if record["economic_event_id"] != target["economic_event_id"]:
            _fail(
                "incompatible_event_relationship",
                f"{context} supersession changes economic-event identity",
            )
    elif record["economic_event_id"] == target["economic_event_id"]:
        _fail(
            "incompatible_event_relationship",
            f"{context} reversal must start a distinct economic-event identity",
        )

    if action == "cancel":
        return
    event = record["event"]
    target_event = target["event"]
    if target_event is None or event["variant"] != target_event["variant"]:
        _fail("incompatible_event_relationship", f"{context} lifecycle event types differ")

    if event["variant"] == "cash_movement":
        if event["amount"]["currency"] != target_event["amount"]["currency"]:
            _fail("incompatible_event_relationship", f"{context} changes cash currency")
        if action == "reverse" and _scaled_value(event["amount"]) != -_scaled_value(
            target_event["amount"]
        ):
            _fail(
                "incompatible_event_relationship",
                f"{context} cash reversal is not the exact offset",
            )
    else:
        if (
            event["instrument"] != target_event["instrument"]
            or event["quote_currency"] != target_event["quote_currency"]
        ):
            _fail(
                "incompatible_event_relationship",
                f"{context} changes an equity-trade natural key",
            )
        if action == "reverse" and (
            _scaled_value(event["price"]) != _scaled_value(target_event["price"])
            or _scaled_value(event["quantity"]) != -_scaled_value(target_event["quantity"])
        ):
            _fail(
                "incompatible_event_relationship",
                f"{context} equity reversal is not the exact quantity and price offset",
            )

    if (
        action == "reverse"
        and event["header"]["effective_at"] < target_event["header"]["effective_at"]
    ):
        _fail(
            "incompatible_event_relationship",
            f"{context} reversal economically predates its target",
        )


def _validate_records(records_value: Any, context: str) -> list[dict[str, Any]]:
    records = _objects(records_value, context, nonempty=True)
    ids: set[str] = set()
    economic_origins: set[str] = set()
    expected_sequence = 1
    previous_recorded_at: str | None = None
    known: dict[str, dict[str, Any]] = {}
    successors: dict[str, str] = {}
    for index, record in enumerate(records):
        item = f"{context}[{index}]"
        _record(record, item)
        record_id = record["record_id"]
        if record_id in ids:
            _fail("duplicate_identity", f"duplicate record ID {record_id!r}")
        ids.add(record_id)
        if record["action"] in {"originate", "reverse"}:
            economic_id = record["economic_event_id"]
            if economic_id in economic_origins:
                _fail("duplicate_identity", f"duplicate economic origin {economic_id!r}")
            economic_origins.add(economic_id)
        sequence = _unsigned_integer(record["acceptance_sequence"], f"{item}.acceptance_sequence")
        if sequence != expected_sequence:
            _fail("deterministic_ordering", f"{context} must be contiguous from sequence 1")
        expected_sequence += 1
        if previous_recorded_at is not None and record["recorded_at"] < previous_recorded_at:
            _fail("deterministic_ordering", f"{context}.recorded_at must not decrease")
        previous_recorded_at = record["recorded_at"]
        causal = record["causal_record_id"]
        if causal is not None:
            if causal not in known:
                _fail(
                    "lineage_reference_missing",
                    f"{record_id!r} has unavailable causal target {causal!r}",
                )
            target = known[causal]
            if record["account"] != target["account"]:
                _fail(
                    "incompatible_account",
                    f"{item} and target {causal!r} have different accounts",
                )
            if causal in successors:
                _fail(
                    "conflicting_lifecycle_successor",
                    f"{causal!r} already has lifecycle successor {successors[causal]!r}",
                )
            successors[causal] = record_id
            _validate_relationship(record, target, item)
        known[record_id] = record
    return records


def _state(value: Any, context: str) -> dict[str, Any]:
    state = _object(value, context)
    _keys(state, {"schema_version", "positions", "settled_cash", "open_settlement_obligations"}, context)
    _version(state["schema_version"], SUPPORTED["state"], f"{context}.schema_version")

    positions = _objects(state["positions"], f"{context}.positions")
    position_keys: list[tuple[str, str]] = []
    for index, position in enumerate(positions):
        item = f"{context}.positions[{index}]"
        _keys(position, {"schema_version", "account", "instrument", "quantity"}, item)
        _version(position["schema_version"], SUPPORTED["position"], f"{item}.schema_version")
        _string(position["account"], f"{item}.account")
        _string(position["instrument"], f"{item}.instrument")
        quantity = _fixed(position["quantity"], SUPPORTED["quantity"], "8", f"{item}.quantity")
        if _integer(quantity["scaled_value"], f"{item}.quantity.scaled_value") == 0:
            _fail("schema_shape", f"{item} must omit zero quantity")
        position_keys.append((position["account"], position["instrument"]))
    if position_keys != sorted(position_keys) or len(position_keys) != len(set(position_keys)):
        _fail("deterministic_ordering", f"{context}.positions must be unique and key-sorted")

    cash = _objects(state["settled_cash"], f"{context}.settled_cash")
    cash_keys: list[tuple[str, str]] = []
    for index, balance in enumerate(cash):
        item = f"{context}.settled_cash[{index}]"
        _keys(balance, {"schema_version", "account", "amount"}, item)
        _version(balance["schema_version"], SUPPORTED["cash"], f"{item}.schema_version")
        _string(balance["account"], f"{item}.account")
        amount = _money(balance["amount"], f"{item}.amount")
        if _integer(amount["scaled_value"], f"{item}.amount.scaled_value") == 0:
            _fail("schema_shape", f"{item} must omit zero amount")
        cash_keys.append((balance["account"], amount["currency"]))
    if cash_keys != sorted(cash_keys) or len(cash_keys) != len(set(cash_keys)):
        _fail("deterministic_ordering", f"{context}.settled_cash must be unique and key-sorted")

    obligations = _objects(
        state["open_settlement_obligations"], f"{context}.open_settlement_obligations"
    )
    direction_order = {"receivable": 0, "payable": 1}
    obligation_keys: list[tuple[str, str, str, int]] = []
    for index, obligation in enumerate(obligations):
        item = f"{context}.open_settlement_obligations[{index}]"
        _keys(
            obligation,
            {"schema_version", "account", "settlement_date", "direction", "amount"},
            item,
        )
        _version(obligation["schema_version"], SUPPORTED["settlement"], f"{item}.schema_version")
        _string(obligation["account"], f"{item}.account")
        _date(obligation["settlement_date"], f"{item}.settlement_date")
        if obligation["direction"] not in direction_order:
            _fail("schema_shape", f"{item}.direction is unsupported")
        amount = _money(obligation["amount"], f"{item}.amount", positive=True)
        obligation_keys.append(
            (
                obligation["account"],
                obligation["settlement_date"],
                amount["currency"],
                direction_order[obligation["direction"]],
            )
        )
    if obligation_keys != sorted(obligation_keys) or len(obligation_keys) != len(set(obligation_keys)):
        _fail("deterministic_ordering", f"{context}.open_settlement_obligations must be unique and key-sorted")
    return state


def _context(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(
        result,
        {
            "schema_version",
            "recorded_through",
            "economic_as_of",
            "settlement_as_of_date",
            "reference_data_inputs",
            "price_inputs",
            "calendar_inputs",
            "rounding_inputs",
            "fx_inputs",
        },
        context,
    )
    _version(result["schema_version"], SUPPORTED["context"], f"{context}.schema_version")
    _timestamp(result["recorded_through"], f"{context}.recorded_through")
    _timestamp(result["economic_as_of"], f"{context}.economic_as_of")
    _date(result["settlement_as_of_date"], f"{context}.settlement_as_of_date")
    for field in (
        "reference_data_inputs",
        "price_inputs",
        "calendar_inputs",
        "rounding_inputs",
        "fx_inputs",
    ):
        inputs = _objects(result[field], f"{context}.{field}")
        identities: list[tuple[str, str]] = []
        for index, item in enumerate(inputs):
            item_context = f"{context}.{field}[{index}]"
            _keys(item, {"id", "version", "digest"}, item_context)
            identities.append(
                (_string(item["id"], f"{item_context}.id"), _string(item["version"], f"{item_context}.version"))
            )
            _digest(item["digest"], f"{item_context}.digest")
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            _fail("deterministic_ordering", f"{context}.{field} must be unique and sorted")
    return result


def _identity(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(result, {"id", "version"}, context)
    _string(result["id"], f"{context}.id")
    _string(result["version"], f"{context}.version")
    return result


def _partition(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(result, {"definition", "version", "keys"}, context)
    _string(result["definition"], f"{context}.definition")
    _string(result["version"], f"{context}.version")
    keys = result["keys"]
    if not isinstance(keys, list) or not keys:
        _fail("schema_shape", f"{context}.keys must be a non-empty array")
    for index, key in enumerate(keys):
        _string(key, f"{context}.keys[{index}]")
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        _fail("deterministic_ordering", f"{context}.keys must be unique and sorted")
    return result


def _event_prefix(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(
        result,
        {
            "kind",
            "first_sequence",
            "last_sequence",
            "record_count",
            "last_record_id",
            "record_schema_version",
            "canonical_input_digest",
        },
        context,
    )
    if result["kind"] != "acceptance_sequence_inclusive":
        _fail("schema_shape", f"{context}.kind is unsupported")
    first = _unsigned_integer(result["first_sequence"], f"{context}.first_sequence", minimum=1)
    last = _unsigned_integer(result["last_sequence"], f"{context}.last_sequence", minimum=1)
    count = _unsigned_integer(result["record_count"], f"{context}.record_count", minimum=1)
    if first != 1 or last - first + 1 != count:
        _fail("prefix_continuity", f"{context} is not one inclusive contiguous prefix")
    _string(result["last_record_id"], f"{context}.last_record_id")
    _version(result["record_schema_version"], SUPPORTED["record"], f"{context}.record_schema_version")
    _digest(result["canonical_input_digest"], f"{context}.canonical_input_digest")
    return result


def _lineage(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(result, {"lifecycle_record_ids", "active_record_ids", "source_record_ids"}, context)
    for field in ("lifecycle_record_ids", "active_record_ids", "source_record_ids"):
        items = result[field]
        if not isinstance(items, list) or any(not isinstance(item, str) or not item for item in items):
            _fail("schema_shape", f"{context}.{field} must be an array of non-empty strings")
        for index, item in enumerate(items):
            _string(item, f"{context}.{field}[{index}]")
        if len(items) != len(set(items)):
            _fail("duplicate_identity", f"{context}.{field} contains duplicates")
    return result


def _manifest(value: Any, context: str) -> dict[str, Any]:
    manifest = _object(value, context)
    _keys(
        manifest,
        {
            "schema_version",
            "serialization_version",
            "digest_algorithm",
            "projection",
            "engine_version",
            "policy",
            "partition",
            "event_prefix",
            "evaluation_context",
            "canonical_state_digest",
            "resolved_event_watermark",
            "lineage",
        },
        context,
    )
    _version(manifest["schema_version"], SUPPORTED["manifest"], f"{context}.schema_version")
    _version(manifest["serialization_version"], SUPPORTED["bytes"], f"{context}.serialization_version")
    if manifest["digest_algorithm"] != "sha-256":
        _fail("unsupported_version", f"{context}.digest_algorithm is unsupported")
    _identity(manifest["projection"], f"{context}.projection")
    _string(manifest["engine_version"], f"{context}.engine_version")
    _identity(manifest["policy"], f"{context}.policy")
    _partition(manifest["partition"], f"{context}.partition")
    _event_prefix(manifest["event_prefix"], f"{context}.event_prefix")
    _context(manifest["evaluation_context"], f"{context}.evaluation_context")
    _digest(manifest["canonical_state_digest"], f"{context}.canonical_state_digest")
    watermark = _object(manifest["resolved_event_watermark"], f"{context}.resolved_event_watermark")
    _keys(watermark, {"effective_at", "acceptance_sequence", "record_id"}, f"{context}.resolved_event_watermark")
    _timestamp(watermark["effective_at"], f"{context}.resolved_event_watermark.effective_at")
    _unsigned_integer(
        watermark["acceptance_sequence"],
        f"{context}.resolved_event_watermark.acceptance_sequence",
        minimum=1,
    )
    _string(watermark["record_id"], f"{context}.resolved_event_watermark.record_id")
    _lineage(manifest["lineage"], f"{context}.lineage")
    return manifest


def _source_ids(records: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for record in records:
        for source_id in record["provenance"]["source_record_ids"]:
            if source_id not in result:
                result.append(source_id)
    return result


def _event_sort_key(record: dict[str, Any]) -> tuple[str, int]:
    event = record["event"]
    if event is None:
        _fail("lineage_reference_missing", "active lineage references a cancellation")
    return event["header"]["effective_at"], int(record["acceptance_sequence"])


def _active_heads(
    records: list[dict[str, Any]], evaluation_context: dict[str, Any]
) -> list[dict[str, Any]]:
    selected_by_economic_id: dict[str, list[dict[str, Any]]] = {}
    recorded_through = evaluation_context["recorded_through"]
    economic_as_of = evaluation_context["economic_as_of"]
    for record in records:
        if record["recorded_at"] <= recorded_through:
            selected_by_economic_id.setdefault(record["economic_event_id"], []).append(record)

    active: list[dict[str, Any]] = []
    for chain in selected_by_economic_id.values():
        head = chain[-1]
        if (
            head["action"] != "cancel"
            and head["event"]["header"]["effective_at"] <= economic_as_of
        ):
            active.append(head)
    return sorted(active, key=_event_sort_key)


def _bind_lineage(
    lineage: dict[str, Any],
    records: list[dict[str, Any]],
    evaluation_context: dict[str, Any],
    context: str,
) -> list[dict[str, Any]]:
    record_ids = [record["record_id"] for record in records]
    if lineage["lifecycle_record_ids"] != record_ids:
        _fail("lineage_reference_missing", f"{context} lifecycle lineage does not equal the prefix")
    if lineage["source_record_ids"] != _source_ids(records):
        _fail("lineage_reference_missing", f"{context} source lineage is incomplete or reordered")
    by_id = {record["record_id"]: record for record in records}
    try:
        active = [by_id[record_id] for record_id in lineage["active_record_ids"]]
    except KeyError as error:
        _fail("lineage_reference_missing", f"{context} active record {error.args[0]!r} is absent")
    expected_active = _active_heads(records, evaluation_context)
    active_ids = [record["record_id"] for record in active]
    expected_ids = [record["record_id"] for record in expected_active]
    if set(active_ids) != set(expected_ids):
        _fail(
            "lineage_reference_missing",
            f"{context} active lineage does not equal the context-selected lifecycle heads",
        )
    if active_ids != expected_ids:
        _fail("deterministic_ordering", f"{context} active lineage is not in economic replay order")
    return active


def _bind_manifest(
    manifest: dict[str, Any], records: list[dict[str, Any]], state: dict[str, Any], context: str
) -> None:
    prefix = manifest["event_prefix"]
    count = int(prefix["record_count"])
    if count != len(records):
        _fail("incompatible_prefix", f"{context} record count does not match supplied prefix")
    if prefix["last_record_id"] != records[-1]["record_id"]:
        _fail("incompatible_prefix", f"{context} last record ID does not match supplied prefix")
    expected_input_digest = canonical_digest(_record_sequence(records))
    if prefix["canonical_input_digest"] != expected_input_digest:
        _fail("digest_mismatch", f"{context} canonical input digest is altered")
    if manifest["canonical_state_digest"] != canonical_digest(state):
        _fail("digest_mismatch", f"{context} canonical state digest is altered")

    lineage = manifest["lineage"]
    active = _bind_lineage(lineage, records, manifest["evaluation_context"], context)
    watermark = manifest["resolved_event_watermark"]
    if not active:
        _fail("lineage_reference_missing", f"{context} v1 checkpoint has no resolved event watermark")
    if (
        watermark["record_id"] != active[-1]["record_id"]
        or watermark["effective_at"] != active[-1]["event"]["header"]["effective_at"]
        or watermark["acceptance_sequence"] != active[-1]["acceptance_sequence"]
    ):
        _fail("lineage_reference_missing", f"{context} resolved event watermark is inconsistent")


def _resume(value: Any, context: str) -> dict[str, Any]:
    resume = _object(value, context)
    _keys(
        resume,
        {
            "schema_version",
            "serialization_version",
            "checkpoint_manifest_digest",
            "projection",
            "engine_version",
            "policy",
            "partition",
            "evaluation_context",
            "checkpoint_event_prefix",
            "checkpoint_state_digest",
        },
        context,
    )
    _version(resume["schema_version"], SUPPORTED["resume"], f"{context}.schema_version")
    _version(resume["serialization_version"], SUPPORTED["bytes"], f"{context}.serialization_version")
    _digest(resume["checkpoint_manifest_digest"], f"{context}.checkpoint_manifest_digest")
    _identity(resume["projection"], f"{context}.projection")
    _string(resume["engine_version"], f"{context}.engine_version")
    _identity(resume["policy"], f"{context}.policy")
    _partition(resume["partition"], f"{context}.partition")
    _context(resume["evaluation_context"], f"{context}.evaluation_context")
    _event_prefix(resume["checkpoint_event_prefix"], f"{context}.checkpoint_event_prefix")
    _digest(resume["checkpoint_state_digest"], f"{context}.checkpoint_state_digest")
    return resume


def validate_resume(
    manifest: dict[str, Any],
    resume: dict[str, Any],
    prefix_records: list[dict[str, Any]],
    suffix_records: list[dict[str, Any]],
) -> None:
    _manifest(manifest, "checkpoint_manifest")
    _resume(resume, "resume_request")
    if resume["checkpoint_manifest_digest"] != canonical_digest(manifest):
        _fail("digest_mismatch", "resume request does not identify the supplied manifest")
    if resume["projection"] != manifest["projection"]:
        _fail("incompatible_projection", "projection identity or version changed")
    if resume["engine_version"] != manifest["engine_version"]:
        _fail("incompatible_engine", "engine version changed")
    if resume["policy"] != manifest["policy"]:
        _fail("incompatible_policy", "policy identity or version changed")
    if resume["partition"] != manifest["partition"]:
        _fail("incompatible_partition", "partition definition changed")
    if resume["evaluation_context"] != manifest["evaluation_context"]:
        _fail("incompatible_context", "evaluation context or explicit context input changed")
    if resume["checkpoint_event_prefix"] != manifest["event_prefix"]:
        _fail("incompatible_prefix", "resume request identifies a different event prefix")
    if resume["checkpoint_state_digest"] != manifest["canonical_state_digest"]:
        _fail("digest_mismatch", "resume request identifies a different state digest")

    if not suffix_records:
        _fail("prefix_continuity", "resume suffix must not be empty")
    expected = len(prefix_records) + 1
    prefix_ids = {record["record_id"] for record in prefix_records}
    watermark = manifest["resolved_event_watermark"]
    watermark_key = (watermark["effective_at"], int(watermark["acceptance_sequence"]))
    for index, record in enumerate(suffix_records):
        sequence = int(record["acceptance_sequence"])
        if sequence != expected + index:
            _fail("prefix_continuity", "suffix acceptance sequences are not contiguous")
        if record["causal_record_id"] in prefix_ids:
            _fail(
                "late_lifecycle_knowledge",
                "a correction, cancellation, or reversal targets the checkpoint prefix",
            )
        if record["event"] is not None and _event_sort_key(record) <= watermark_key:
            _fail("late_lifecycle_knowledge", "a suffix event sorts at or before checkpoint state")


def _target(document: dict[str, Any], target: str) -> Any:
    if target == "prefix_records":
        return _record_sequence(document["records"][: int(document["prefix_record_count"])])
    if target == "all_records":
        return _record_sequence(document["records"])
    if target not in document:
        _fail("schema_shape", f"vector target {target!r} is unavailable")
    return document[target]


def _primitive_envelope(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(
        result,
        {"schema_version", "enabled", "optional", "signed_integer", "ordered_values"},
        context,
    )
    _version(
        result["schema_version"],
        "luca.canonical-test-value.v1",
        f"{context}.schema_version",
    )
    if not isinstance(result["enabled"], bool) or result["optional"] is not None:
        _fail("schema_shape", f"{context} boolean or optional primitive is invalid")
    integer = result["signed_integer"]
    if (
        isinstance(integer, bool)
        or not isinstance(integer, int)
        or integer < I64_MIN
        or integer > I64_MAX
    ):
        _fail("schema_shape", f"{context}.signed_integer must fit signed 64-bit")
    values = result["ordered_values"]
    if not isinstance(values, list):
        _fail("schema_shape", f"{context}.ordered_values must be an array")
    for index, item in enumerate(values):
        _string(item, f"{context}.ordered_values[{index}]")
    return result


def _canonical_vector_values(value: Any, context: str) -> dict[str, Any]:
    values = _object(value, context)
    _keys(
        values,
        {"primitive_envelope", "money", "provenance", "maximum_lifecycle_sequence"},
        context,
    )
    _primitive_envelope(values["primitive_envelope"], f"{context}.primitive_envelope")
    _money(values["money"], f"{context}.money")
    _provenance(values["provenance"], f"{context}.provenance")
    _unsigned_integer(
        values["maximum_lifecycle_sequence"],
        f"{context}.maximum_lifecycle_sequence",
        minimum=1,
    )
    return values


def _vectors(value: Any, document: dict[str, Any], context: str) -> None:
    vectors = _objects(value, context, nonempty=True)
    ids: set[str] = set()
    for index, vector in enumerate(vectors):
        item = f"{context}[{index}]"
        _keys(vector, {"id", "target", "canonical_hex", "sha256"}, item)
        vector_id = _string(vector["id"], f"{item}.id")
        if vector_id in ids:
            _fail("duplicate_identity", f"duplicate vector ID {vector_id!r}")
        ids.add(vector_id)
        target = _target(document, _string(vector["target"], f"{item}.target"))
        expected_hex = vector["canonical_hex"]
        if not isinstance(expected_hex, str) or re.fullmatch(r"[0-9a-f]*", expected_hex) is None:
            _fail("schema_shape", f"{item}.canonical_hex must be lowercase hexadecimal")
        _digest(vector["sha256"], f"{item}.sha256")
        first = canonical_bytes(target)
        second = canonical_bytes(target)
        if first != second or first.hex() != expected_hex:
            _fail("digest_mismatch", f"{vector_id!r} canonical byte vector differs")
        if hashlib.sha256(first).hexdigest() != vector["sha256"]:
            _fail("digest_mismatch", f"{vector_id!r} digest vector differs")
        if decode_canonical(first) != target or canonical_bytes(decode_canonical(first)) != first:
            _fail("canonical_encoding", f"{vector_id!r} does not round trip")


def _apply_path(value: dict[str, Any], path: str, replacement: Any) -> dict[str, Any]:
    if not path.startswith("/"):
        _fail("schema_shape", "mutation path must be an absolute JSON pointer")
    result = copy.deepcopy(value)
    current: Any = result
    parts = path[1:].split("/")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            _fail("schema_shape", f"mutation path {path!r} is unavailable")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        _fail("schema_shape", f"mutation path {path!r} is unavailable")
    current[parts[-1]] = replacement
    return result


def validate_fixture(document: dict[str, Any]) -> None:
    _version(document.get("fixture_schema"), SUPPORTED["fixture"], "fixture_schema")
    kind = document.get("case_kind")
    if kind == "canonical_vectors":
        _keys(document, {"fixture_schema", "case_kind", "case_id", "values", "vectors"}, "fixture")
        _string(document["case_id"], "case_id")
        values = _canonical_vector_values(document["values"], "values")
        _vectors(document["vectors"], values, "vectors")
        vector_targets = [vector.get("target") for vector in document["vectors"]]
        if len(vector_targets) != len(set(vector_targets)) or set(vector_targets) != set(values):
            _fail(
                "schema_shape",
                "canonical vectors must cover every named value exactly once",
            )
        return
    if kind not in {"compatible_append", "late_correction"}:
        _fail("schema_shape", f"case_kind {kind!r} is unsupported")
    _keys(
        document,
        {
            "fixture_schema",
            "case_kind",
            "case_id",
            "records",
            "prefix_record_count",
            "checkpoint_state",
            "checkpoint_manifest",
            "resume_request",
            "full_replay_state",
            "full_replay_lineage",
            "checkpoint_plus_suffix_state",
            "checkpoint_plus_suffix_lineage",
            "expected_resume_diagnostic",
            "incompatible_resume_cases",
            "vectors",
        },
        "fixture",
    )
    _string(document["case_id"], "case_id")
    records = _validate_records(document["records"], "records")
    prefix_count = document["prefix_record_count"]
    if isinstance(prefix_count, bool) or not isinstance(prefix_count, int) or not 0 < prefix_count < len(records):
        _fail("schema_shape", "prefix_record_count must split prefix from a non-empty suffix")
    prefix = records[:prefix_count]
    suffix = records[prefix_count:]
    checkpoint_state = _state(document["checkpoint_state"], "checkpoint_state")
    full_state = _state(document["full_replay_state"], "full_replay_state")
    manifest = _manifest(document["checkpoint_manifest"], "checkpoint_manifest")
    _bind_manifest(manifest, prefix, checkpoint_state, "checkpoint_manifest")
    resume = _resume(document["resume_request"], "resume_request")
    full_lineage = _lineage(document["full_replay_lineage"], "full_replay_lineage")
    _bind_lineage(
        full_lineage,
        records,
        manifest["evaluation_context"],
        "full_replay_lineage",
    )

    diagnostic = document["expected_resume_diagnostic"]
    if diagnostic is not None:
        _string(diagnostic, "expected_resume_diagnostic")
    if kind == "compatible_append":
        if diagnostic is not None:
            _fail("schema_shape", "compatible append must not expect a resume diagnostic")
        validate_resume(manifest, resume, prefix, suffix)
        if document["checkpoint_plus_suffix_state"] != full_state:
            _fail("digest_mismatch", "full replay and checkpoint-plus-suffix state differ")
        if document["checkpoint_plus_suffix_lineage"] != document["full_replay_lineage"]:
            _fail("lineage_reference_missing", "execution-mode lineage differs")
        incremental_lineage = _lineage(
            document["checkpoint_plus_suffix_lineage"], "checkpoint_plus_suffix_lineage"
        )
        _bind_lineage(
            incremental_lineage,
            records,
            manifest["evaluation_context"],
            "checkpoint_plus_suffix_lineage",
        )
    else:
        if document["checkpoint_plus_suffix_state"] is not None or document["checkpoint_plus_suffix_lineage"] is not None:
            _fail("schema_shape", "invalidated checkpoint must not declare an incremental result")
        try:
            validate_resume(manifest, resume, prefix, suffix)
        except ContractError as error:
            if error.category != diagnostic:
                raise
        else:
            _fail("schema_shape", "late-correction fixture unexpectedly permits checkpoint reuse")

    cases = _objects(document["incompatible_resume_cases"], "incompatible_resume_cases")
    for index, case in enumerate(cases):
        item = f"incompatible_resume_cases[{index}]"
        _keys(case, {"id", "path", "replacement", "expected_diagnostic"}, item)
        _string(case["id"], f"{item}.id")
        expected = _string(case["expected_diagnostic"], f"{item}.expected_diagnostic")
        candidate = _apply_path(resume, _string(case["path"], f"{item}.path"), case["replacement"])
        try:
            validate_resume(manifest, candidate, prefix, suffix)
        except ContractError as error:
            if error.category != expected:
                raise AssertionError(f"{case['id']}: expected {expected}, received {error.category}") from error
        else:
            _fail("schema_shape", f"{case['id']!r} unexpectedly permits checkpoint reuse")
    _vectors(document["vectors"], document, "vectors")


class SerializationCheckpointContractTest(unittest.TestCase):
    def _load_valid_append(self) -> dict[str, Any]:
        return _read_json(FIXTURE_ROOT / "valid-append.json")

    def _load_canonical_vectors(self) -> dict[str, Any]:
        return _read_json(FIXTURE_ROOT / "canonical-vectors.json")

    @staticmethod
    def _refresh_vector(document: dict[str, Any], target_name: str) -> None:
        target = document["values"][target_name]
        encoded = canonical_bytes(target)
        for vector in document["vectors"]:
            if vector["target"] == target_name:
                vector["canonical_hex"] = encoded.hex()
                vector["sha256"] = hashlib.sha256(encoded).hexdigest()
                return
        raise AssertionError(f"missing canonical vector for {target_name!r}")

    def test_every_named_fixture_validates_independently(self):
        self.assertEqual(len(FIXTURE_FILES), 3)
        for path in FIXTURE_FILES:
            with self.subTest(path=path.name):
                validate_fixture(_read_json(path))

    def test_unsupported_fixture_record_and_manifest_versions_are_rejected(self):
        fixture = self._load_valid_append()
        mutations = (
            ("fixture_schema", "luca.serialization-checkpoint-fixture.v2"),
            ("record", "luca.lifecycle-record.v2"),
            ("manifest", "luca.checkpoint-manifest.v2"),
        )
        for kind, version in mutations:
            candidate = copy.deepcopy(fixture)
            if kind == "fixture_schema":
                candidate["fixture_schema"] = version
            elif kind == "record":
                candidate["records"][0]["schema_version"] = version
            else:
                candidate["checkpoint_manifest"]["schema_version"] = version
            with self.subTest(kind=kind), self.assertRaisesRegex(ContractError, "unsupported_version"):
                validate_fixture(candidate)

    def test_altered_vector_and_manifest_hashes_are_rejected(self):
        fixture = self._load_valid_append()
        altered_vector = copy.deepcopy(fixture)
        altered_vector["vectors"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "digest_mismatch"):
            validate_fixture(altered_vector)

        altered_manifest = copy.deepcopy(fixture)
        altered_manifest["checkpoint_manifest"]["canonical_state_digest"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "digest_mismatch"):
            validate_fixture(altered_manifest)

    def test_reordered_inputs_and_broken_prefix_are_rejected(self):
        fixture = self._load_valid_append()
        reordered = copy.deepcopy(fixture)
        reordered["records"][0], reordered["records"][1] = reordered["records"][1], reordered["records"][0]
        with self.assertRaisesRegex(ContractError, "deterministic_ordering"):
            validate_fixture(reordered)

        prefix = fixture["records"][: fixture["prefix_record_count"]]
        suffix = copy.deepcopy(fixture["records"][fixture["prefix_record_count"] :])
        suffix[0]["acceptance_sequence"] = "99"
        with self.assertRaisesRegex(ContractError, "prefix_continuity"):
            validate_resume(fixture["checkpoint_manifest"], fixture["resume_request"], prefix, suffix)

    def test_broken_lineage_reference_is_rejected(self):
        fixture = self._load_valid_append()
        fixture["checkpoint_manifest"]["lineage"]["active_record_ids"][0] = "record-missing"
        with self.assertRaisesRegex(ContractError, "lineage_reference_missing"):
            validate_fixture(fixture)

    def test_lifecycle_relationships_and_derived_heads_are_enforced(self):
        late = _read_json(FIXTURE_ROOT / "late-correction.json")

        both_predecessor_and_head = copy.deepcopy(late)
        both_predecessor_and_head["full_replay_lineage"]["active_record_ids"] = [
            "record-cash-1000",
            "record-cash-1200-correction",
        ]
        with self.assertRaisesRegex(ContractError, "lineage_reference_missing"):
            validate_fixture(both_predecessor_and_head)

        omitted_head = copy.deepcopy(late)
        omitted_head["full_replay_lineage"]["active_record_ids"] = ["record-cash-1000"]
        with self.assertRaisesRegex(ContractError, "lineage_reference_missing"):
            validate_fixture(omitted_head)

        false_manifest = copy.deepcopy(late["checkpoint_manifest"])
        false_manifest["event_prefix"].update(
            {
                "last_sequence": "2",
                "record_count": "2",
                "last_record_id": "record-cash-1200-correction",
                "canonical_input_digest": canonical_digest(_record_sequence(late["records"])),
            }
        )
        false_manifest["canonical_state_digest"] = canonical_digest(late["full_replay_state"])
        false_manifest["lineage"] = copy.deepcopy(late["full_replay_lineage"])
        false_manifest["lineage"]["active_record_ids"] = ["record-cash-1000"]
        false_manifest["resolved_event_watermark"] = {
            "effective_at": "2026-02-01T09:00:00.000000000Z",
            "acceptance_sequence": "1",
            "record_id": "record-cash-1000",
        }
        with self.assertRaisesRegex(ContractError, "lineage_reference_missing"):
            _bind_manifest(
                false_manifest,
                late["records"],
                late["full_replay_state"],
                "checkpoint_manifest",
            )

        cross_account = copy.deepcopy(late)
        correction = cross_account["records"][1]
        correction["account"] = "acct-other"
        correction["event"]["header"]["account"] = "acct-other"
        with self.assertRaisesRegex(ContractError, "incompatible_account"):
            validate_fixture(cross_account)

        cross_identity = copy.deepcopy(late)
        cross_identity["records"][1]["economic_event_id"] = "economic-other"
        with self.assertRaisesRegex(ContractError, "incompatible_event_relationship"):
            validate_fixture(cross_identity)

    def test_lifecycle_sequence_supports_the_complete_uint64_domain(self):
        fixture = self._load_valid_append()
        record = copy.deepcopy(fixture["records"][0])
        record["acceptance_sequence"] = str((1 << 64) - 1)
        self.assertEqual(
            _record(record, "record")["acceptance_sequence"],
            "18446744073709551615",
        )

        record["acceptance_sequence"] = str(1 << 64)
        with self.assertRaisesRegex(ContractError, "unsigned 64-bit"):
            _record(record, "record")

        manifest = copy.deepcopy(fixture["checkpoint_manifest"])
        manifest["resolved_event_watermark"]["acceptance_sequence"] = str((1 << 64) - 1)
        self.assertEqual(
            _manifest(manifest, "manifest")["resolved_event_watermark"]["acceptance_sequence"],
            "18446744073709551615",
        )
        manifest["resolved_event_watermark"]["acceptance_sequence"] = str(1 << 64)
        with self.assertRaisesRegex(ContractError, "unsigned 64-bit"):
            _manifest(manifest, "manifest")

    def test_canonical_domain_vectors_validate_shape_before_matching_bytes(self):
        mutations = (
            ("money-version", "money", "schema_version", "luca.money.v2", "unsupported_version"),
            ("money-scale", "money", "scale", "7", "schema_shape"),
            ("money-currency", "money", "currency", "usd", "schema_shape"),
            (
                "provenance-version",
                "provenance",
                "schema_version",
                "luca.provenance.v2",
                "unsupported_version",
            ),
            (
                "duplicate-provenance-source",
                "provenance",
                "source_record_ids",
                ["source-trade-001", "source-trade-001"],
                "duplicate_identity",
            ),
        )
        for name, target, field, replacement, diagnostic in mutations:
            candidate = self._load_canonical_vectors()
            candidate["values"][target][field] = replacement
            self._refresh_vector(candidate, target)
            with self.subTest(name=name), self.assertRaisesRegex(ContractError, diagnostic):
                validate_fixture(candidate)

        unknown_field = self._load_canonical_vectors()
        unknown_field["values"]["money"]["extra"] = "forbidden"
        self._refresh_vector(unknown_field, "money")
        with self.assertRaisesRegex(ContractError, "schema_shape"):
            validate_fixture(unknown_field)

    def test_meaningful_mutations_change_the_relevant_digest(self):
        fixture = self._load_valid_append()
        original_records = _record_sequence(fixture["records"])
        altered_records = copy.deepcopy(original_records)
        altered_records["records"][0]["event"]["amount"]["scaled_value"] = "100000000001"
        altered_records["records"][0]["event"]["header"]["provenance"] = copy.deepcopy(
            altered_records["records"][0]["provenance"]
        )
        self.assertNotEqual(canonical_digest(original_records), canonical_digest(altered_records))

        reordered_records = copy.deepcopy(original_records)
        reordered_records["records"][0], reordered_records["records"][1] = (
            reordered_records["records"][1],
            reordered_records["records"][0],
        )
        self.assertNotEqual(canonical_digest(original_records), canonical_digest(reordered_records))

        for field, replacement in (
            ("schema_version", "luca.checkpoint-manifest.v2"),
            ("projection", {"id": "luca.portfolio-state", "version": "2"}),
            ("policy", {"id": "luca.portfolio-default", "version": "2"}),
            ("partition", {"definition": "account-set", "version": "1", "keys": ["acct-other"]}),
            ("engine_version", "luca-engine-2"),
        ):
            altered_manifest = copy.deepcopy(fixture["checkpoint_manifest"])
            altered_manifest[field] = replacement
            self.assertNotEqual(
                canonical_digest(fixture["checkpoint_manifest"]), canonical_digest(altered_manifest)
            )

        altered_context = copy.deepcopy(fixture["checkpoint_manifest"])
        altered_context["evaluation_context"]["economic_as_of"] = "2026-01-07T23:59:59.000000000Z"
        self.assertNotEqual(
            canonical_digest(fixture["checkpoint_manifest"]), canonical_digest(altered_context)
        )

    def test_binary_float_and_noncanonical_text_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "binary floating-point"):
            canonical_bytes({"amount": 1.5})
        with self.assertRaisesRegex(ContractError, "NFC-normalized"):
            canonical_bytes({"text": "e\u0301"})

    def test_map_insertion_order_does_not_change_canonical_bytes(self):
        self.assertEqual(
            canonical_bytes({"second": "b", "first": "a"}),
            canonical_bytes({"first": "a", "second": "b"}),
        )


if __name__ == "__main__":
    unittest.main()
