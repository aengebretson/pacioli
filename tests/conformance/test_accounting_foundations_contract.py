"""Dependency-free validator for the narrow O4 accounting fixture contract.

The validator consumes fixture-declared O2 resolved inputs.  It checks closed
shapes, immutable lineage, policy mapping, exact journal arithmetic, cutoffs,
and the bounded portfolio cross-checks.  It deliberately does not implement a
general lifecycle resolver or portfolio projection engine.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "accounting-foundations"
VALID_FIXTURE = FIXTURE_ROOT / "valid-cash-equity-lifecycle.json"
INVALID_FIXTURE = FIXTURE_ROOT / "invalid-mutations.json"
CONTRACT_VERSION = "luca.accounting-foundations.v1"
LIFECYCLE_VERSION = "luca.event-lifecycle.v1"
ENGINE_VERSION = "fixture-accounting-engine-1"
PROJECTION_VERSION = "fixture-journal-projection-1"
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
MONEY_TEXT = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{6}$")
QUANTITY_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{8}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")

STABLE_DIAGNOSTICS = {
    "schema_shape",
    "duplicate_identity",
    "invalid_policy",
    "unsupported_event",
    "invalid_cutoff",
    "policy_context_mismatch",
    "unbalanced_entry",
    "mixed_currency_entry",
    "invalid_line_amount",
    "rounding_mismatch",
    "lineage_missing",
    "lineage_mismatch",
    "invalid_reversal_treatment",
    "portfolio_cross_check",
}

ACCOUNTS = {
    "cash": "asset.cash",
    "securities": "asset.equity-securities",
    "receivable": "asset.trade-receivable",
    "payable": "liability.trade-payable",
    "contributed_capital": "equity.contributed-capital",
}

UNSUPPORTED_CASES = [
    "withdrawals",
    "ordinary_equity_sells",
    "non_usd_or_cross_currency_activity",
    "fx",
    "fees_commissions_or_taxes",
    "lots_or_cost_basis_selection",
    "accruals_income_or_corporate_actions",
    "partial_or_multiple_reversals",
    "cancellation_reinterpretation",
    "settlement_calendar_or_failed_settlement",
    "legal_netting",
    "impairment_fair_value_or_pnl",
    "nav_tax_or_financial_statements",
]

BASE_POLICY = {
    "version": "1",
    "fixture_only": True,
    "compliance_claim": "none",
    "supported_event_types": ["cash_movement", "equity_trade"],
    "currency": "USD",
    "accounts": ACCOUNTS,
    "rounding": {
        "money_scale": 6,
        "quantity_scale": 8,
        "mode": "half_even",
        "applies_at": "abs(quantity) * price once; no balance rounding",
    },
    "ordering": {
        "lifecycle": ["recorded_at", "acceptance_sequence"],
        "economic_replay": ["effective_at", "acceptance_sequence"],
        "journal_presentation": [
            "recognized_on",
            "acceptance_sequence",
            "phase_ordinal",
            "journal_entry_id",
        ],
    },
    "unsupported_cases": UNSUPPORTED_CASES,
}


def _expected_policy(policy_id: str) -> dict[str, Any]:
    result = copy.deepcopy(BASE_POLICY)
    result["policy_id"] = policy_id
    if policy_id == "fixture.trade-date.v1":
        result["recognition"] = {
            "cash_movement": "effective_date",
            "positive_equity_trade": "trade_date_then_settlement",
            "negative_exact_reversal": "trade_date_then_settlement",
        }
    elif policy_id == "fixture.settlement-date.v1":
        result["recognition"] = {
            "cash_movement": "effective_date",
            "positive_equity_trade": "settlement_date",
            "negative_exact_reversal": "settlement_date",
        }
    else:  # pragma: no cover - caller limits the values
        raise AssertionError(policy_id)
    return result


EXPECTED_POLICIES = {
    policy_id: _expected_policy(policy_id)
    for policy_id in ("fixture.trade-date.v1", "fixture.settlement-date.v1")
}

EXPECTED_EVALUATIONS = {
    "original-trade-before-correction": {
        "active": ["opening-cash-record", "trade-record-v1"],
        "position": "100.00000000",
        "cash": "100000.000000",
        "obligation": ("payable", "5000.000000", "2026-06-04"),
        "calculation": {
            "position": "100.00000000 MSFT",
            "trade_value": "100.00000000 * 50.000000 = 5000.000000 USD",
            "settled_cash": "100000.000000 USD; trade not settled",
            "journal": "trade-date debits = credits = 105000.000000 USD; settlement-date debits = credits = 100000.000000 USD",
        },
    },
    "corrected-trade-before-settlement": {
        "active": ["opening-cash-record", "trade-record-v2"],
        "position": "80.00000000",
        "cash": "100000.000000",
        "obligation": ("payable", "4400.000000", "2026-06-04"),
        "calculation": {
            "position": "80.00000000 MSFT; correction replaces 100.00000000",
            "trade_value": "80.00000000 * 55.000000 = 4400.000000 USD",
            "settled_cash": "100000.000000 USD; corrected trade not settled",
            "journal": "trade-date debits = credits = 104400.000000 USD; settlement-date debits = credits = 100000.000000 USD",
        },
    },
    "corrected-trade-after-settlement": {
        "active": ["opening-cash-record", "trade-record-v2"],
        "position": "80.00000000",
        "cash": "95600.000000",
        "obligation": None,
        "calculation": {
            "position": "80.00000000 MSFT",
            "trade_value": "80.00000000 * 55.000000 = 4400.000000 USD",
            "settled_cash": "100000.000000 - 4400.000000 = 95600.000000 USD",
            "journal": "trade-date debits = credits = 108800.000000 USD; settlement-date debits = credits = 104400.000000 USD",
        },
    },
    "reversal-known-before-reversal-settlement": {
        "active": ["opening-cash-record", "trade-record-v2", "reversal-record-v1"],
        "position": "0.00000000",
        "cash": "95600.000000",
        "obligation": ("receivable", "4400.000000", "2026-06-06"),
        "calculation": {
            "position": "80.00000000 + -80.00000000 = 0.00000000 MSFT",
            "trade_value": "abs(-80.00000000) * 55.000000 = 4400.000000 USD",
            "settled_cash": "95600.000000 USD; reversal not settled",
            "journal": "trade-date debits = credits = 113200.000000 USD; settlement-date debits = credits = 104400.000000 USD",
        },
    },
    "reversal-after-settlement": {
        "active": ["opening-cash-record", "trade-record-v2", "reversal-record-v1"],
        "position": "0.00000000",
        "cash": "100000.000000",
        "obligation": None,
        "calculation": {
            "position": "80.00000000 + -80.00000000 = 0.00000000 MSFT",
            "trade_value": "4400.000000 purchase and 4400.000000 exact reversal",
            "settled_cash": "95600.000000 + 4400.000000 = 100000.000000 USD",
            "journal": "trade-date debits = credits = 117600.000000 USD; settlement-date debits = credits = 108800.000000 USD",
        },
    },
}


class ContractError(ValueError):
    def __init__(self, category: str, message: str):
        if category not in STABLE_DIAGNOSTICS:
            raise AssertionError(f"unstable diagnostic category {category!r}")
        super().__init__(f"{category}: {message}")
        self.category = category


def _fail(category: str, message: str) -> None:
    raise ContractError(category, message)


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


def _keys(value: dict[str, Any], required: set[str], context: str) -> None:
    missing = required - set(value)
    unknown = set(value) - required
    if missing or unknown:
        _fail(
            "schema_shape",
            f"{context} fields differ (missing={sorted(missing)}, unknown={sorted(unknown)})",
        )


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("schema_shape", f"{context} must be a non-empty string")
    return value


def _strings(value: Any, context: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        _fail("schema_shape", f"{context} must be an array of non-empty strings")
    if nonempty and not value:
        _fail("lineage_missing", f"{context} must not be empty")
    if len(value) != len(set(value)):
        _fail("duplicate_identity", f"{context} contains duplicate identities")
    return value


def _timestamp(value: Any, context: str) -> datetime:
    if not isinstance(value, str) or TIMESTAMP.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid timestamp: {error}")
    if parsed.tzinfo is None:
        _fail("schema_shape", f"{context} must have a timezone")
    return parsed


def _date(value: Any, context: str) -> date:
    if not isinstance(value, str):
        _fail("schema_shape", f"{context} must be an ISO 8601 date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid date: {error}")


def _decimal(value: Any, context: str) -> Decimal:
    if not isinstance(value, str) or DECIMAL_TEXT.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as error:  # pragma: no cover - guarded by regex
        _fail("schema_shape", f"{context} is not a decimal: {error}")


def _money(value: Any, context: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or MONEY_TEXT.fullmatch(value) is None:
        _fail("invalid_line_amount", f"{context} must have exactly six decimals")
    result = Decimal(value)
    if positive and result <= 0:
        _fail("invalid_line_amount", f"{context} must be positive")
    return result


def _quantity(value: Any, context: str) -> Decimal:
    if not isinstance(value, str) or QUANTITY_TEXT.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must have exactly eight decimals")
    return Decimal(value)


def _currency(value: Any, context: str) -> str:
    if not isinstance(value, str) or CURRENCY.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be a three-letter uppercase currency")
    return value


def _policy_ref(value: Any, context: str) -> tuple[str, str]:
    policy = _object(value, context)
    _keys(policy, {"policy_id", "version"}, context)
    return _string(policy["policy_id"], f"{context}.policy_id"), _string(
        policy["version"], f"{context}.version"
    )


def _validate_source_records(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(
        _objects(document.get("source_records"), "source_records", nonempty=True)
    ):
        context = f"source_records[{index}]"
        _keys(
            source,
            {"source_record_id", "source_id", "observed_at", "payload_hash"},
            context,
        )
        source_id = _string(source["source_record_id"], f"{context}.source_record_id")
        _string(source["source_id"], f"{context}.source_id")
        _timestamp(source["observed_at"], f"{context}.observed_at")
        payload_hash = _object(source["payload_hash"], f"{context}.payload_hash")
        _keys(payload_hash, {"algorithm", "value"}, f"{context}.payload_hash")
        if payload_hash != {"algorithm": "sha256", "value": payload_hash.get("value")}:
            _fail("schema_shape", f"{context}.payload_hash must use sha256")
        _string(payload_hash["value"], f"{context}.payload_hash.value")
        if source_id in result:
            _fail("duplicate_identity", f"duplicate source record {source_id!r}")
        result[source_id] = source
    return result


def _validate_event(value: Any, context: str) -> dict[str, Any]:
    event = _object(value, context)
    event_type = event.get("type")
    if event_type == "cash_movement":
        _keys(event, {"type", "currency", "amount"}, context)
        _currency(event["currency"], f"{context}.currency")
        amount = _money(event["amount"], f"{context}.amount", positive=True)
        if amount <= 0:
            _fail("unsupported_event", f"{context} only supports contributions")
    elif event_type == "equity_trade":
        _keys(
            event,
            {"type", "instrument", "quantity", "price", "quote_currency", "settlement_date"},
            context,
        )
        _string(event["instrument"], f"{context}.instrument")
        if _quantity(event["quantity"], f"{context}.quantity") == 0:
            _fail("unsupported_event", f"{context}.quantity must be non-zero")
        _money(event["price"], f"{context}.price", positive=True)
        _currency(event["quote_currency"], f"{context}.quote_currency")
        _date(event["settlement_date"], f"{context}.settlement_date")
    else:
        _fail("unsupported_event", f"{context}.type {event_type!r} is unsupported")
    return event


def _validate_records(
    document: dict[str, Any], source_records: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    sequences: set[int] = set()
    for index, record in enumerate(
        _objects(document.get("lifecycle_records"), "lifecycle_records", nonempty=True)
    ):
        context = f"lifecycle_records[{index}]"
        _keys(
            record,
            {
                "record_id",
                "economic_event_id",
                "account",
                "action",
                "recorded_at",
                "acceptance_sequence",
                "effective_at",
                "supersedes_record_id",
                "reverses_record_id",
                "provenance",
                "event",
            },
            context,
        )
        record_id = _string(record["record_id"], f"{context}.record_id")
        _string(record["economic_event_id"], f"{context}.economic_event_id")
        _string(record["account"], f"{context}.account")
        if record_id in result:
            _fail("duplicate_identity", f"duplicate lifecycle record {record_id!r}")
        action = record["action"]
        if action not in {"originate", "correct", "reverse"}:
            _fail("unsupported_event", f"{context}.action {action!r} is unsupported")
        _timestamp(record["recorded_at"], f"{context}.recorded_at")
        _timestamp(record["effective_at"], f"{context}.effective_at")
        sequence = record["acceptance_sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            _fail("schema_shape", f"{context}.acceptance_sequence must be positive")
        if sequence in sequences:
            _fail("duplicate_identity", f"duplicate acceptance sequence {sequence}")
        sequences.add(sequence)

        expected_causal = {
            "originate": (None, None),
            "correct": ("trade-record-v1", None),
            "reverse": (None, "trade-record-v2"),
        }[action]
        if (record["supersedes_record_id"], record["reverses_record_id"]) != expected_causal:
            category = "invalid_reversal_treatment" if action == "reverse" else "lineage_mismatch"
            _fail(category, f"{context} causal references are inconsistent")

        provenance = _object(record["provenance"], f"{context}.provenance")
        _keys(
            provenance,
            {"source_record_ids", "transformation_name", "transformation_version"},
            f"{context}.provenance",
        )
        source_ids = _strings(
            provenance["source_record_ids"],
            f"{context}.provenance.source_record_ids",
            nonempty=True,
        )
        if any(source_id not in source_records for source_id in source_ids):
            _fail("lineage_mismatch", f"{context} references unknown source evidence")
        _string(provenance["transformation_name"], f"{context}.provenance.transformation_name")
        _string(
            provenance["transformation_version"],
            f"{context}.provenance.transformation_version",
        )
        _validate_event(record["event"], f"{context}.event")
        event_currency = record["event"].get(
            "currency", record["event"].get("quote_currency")
        )
        if record["account"] != "fund-a" or event_currency != "USD":
            _fail(
                "unsupported_event",
                f"{context} is outside the fixture account/currency domain",
            )
        result[record_id] = record

    if sorted(sequences) != list(range(1, len(result) + 1)):
        _fail("schema_shape", "acceptance sequences must be contiguous from one")
    for record in result.values():
        for causal_field in ("supersedes_record_id", "reverses_record_id"):
            target = record[causal_field]
            if target is not None and target not in result:
                _fail("lineage_mismatch", f"{record['record_id']!r} has unknown causal target")
        if record["action"] == "correct":
            target = result[record["supersedes_record_id"]]
            stable = (
                record["economic_event_id"] == target["economic_event_id"]
                and record["account"] == target["account"]
                and record["event"]["type"] == target["event"]["type"]
                and record["event"].get("instrument") == target["event"].get("instrument")
                and record["event"].get("quote_currency")
                == target["event"].get("quote_currency")
            )
            if not stable:
                _fail("lineage_mismatch", "correction changes immutable event relationships")
        if record["action"] == "reverse":
            target = result[record["reverses_record_id"]]
            event = record["event"]
            target_event = target["event"]
            exact_offset = (
                record["economic_event_id"] != target["economic_event_id"]
                and record["account"] == target["account"]
                and event["type"] == target_event["type"] == "equity_trade"
                and event["instrument"] == target_event["instrument"]
                and event["quote_currency"] == target_event["quote_currency"]
                and Decimal(event["quantity"]) == -Decimal(target_event["quantity"])
                and Decimal(event["price"]) == Decimal(target_event["price"])
                and _timestamp(record["effective_at"], "reversal effective_at")
                >= _timestamp(target["effective_at"], "target effective_at")
            )
            if not exact_offset:
                _fail(
                    "invalid_reversal_treatment",
                    "reversal must be a later exact offset of its target",
                )
    return result


def _expected_lineage(
    record: dict[str, Any], records: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if record["action"] == "correct":
        predecessor = records[record["supersedes_record_id"]]
        record_ids = [predecessor["record_id"], record["record_id"]]
        source_ids = (
            predecessor["provenance"]["source_record_ids"]
            + record["provenance"]["source_record_ids"]
        )
    else:
        record_ids = [record["record_id"]]
        source_ids = list(record["provenance"]["source_record_ids"])
    return {
        "record_ids": record_ids,
        "economic_event_ids": [record["economic_event_id"]],
        "source_record_ids": source_ids,
        "reverses_record_id": record["reverses_record_id"],
    }


def _validate_lineage(
    value: Any,
    context: str,
    expected: dict[str, Any],
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    lineage = _object(value, context)
    required = {
        "record_ids",
        "economic_event_ids",
        "source_record_ids",
        "reverses_record_id",
    }
    missing = required - set(lineage)
    unknown = set(lineage) - required
    if missing:
        _fail("lineage_missing", f"{context} omits {sorted(missing)}")
    if unknown:
        _fail("schema_shape", f"{context} has unknown fields {sorted(unknown)}")
    record_ids = _strings(lineage["record_ids"], f"{context}.record_ids", nonempty=True)
    event_ids = _strings(
        lineage["economic_event_ids"], f"{context}.economic_event_ids", nonempty=True
    )
    source_ids = _strings(
        lineage["source_record_ids"], f"{context}.source_record_ids", nonempty=True
    )
    if any(record_id not in records for record_id in record_ids):
        _fail("lineage_mismatch", f"{context} references unknown lifecycle records")
    if any(source_id not in source_records for source_id in source_ids):
        _fail("lineage_mismatch", f"{context} references unknown source records")
    if not isinstance(lineage["reverses_record_id"], (str, type(None))):
        _fail("schema_shape", f"{context}.reverses_record_id must be string or null")
    if lineage != expected:
        _fail("lineage_mismatch", f"{context} differs from immutable active-record lineage")
    return lineage


def _validate_policies(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    required = set(next(iter(EXPECTED_POLICIES.values())))
    for index, policy in enumerate(_objects(document.get("policies"), "policies", nonempty=True)):
        context = f"policies[{index}]"
        _keys(policy, required, context)
        policy_id = _string(policy["policy_id"], f"{context}.policy_id")
        if policy_id in result:
            _fail("duplicate_identity", f"duplicate policy {policy_id!r}")
        expected = EXPECTED_POLICIES.get(policy_id)
        if expected is None or policy != expected:
            _fail("invalid_policy", f"{context} is not one of the closed fixture policies")
        result[policy_id] = policy
    if set(result) != set(EXPECTED_POLICIES):
        _fail("invalid_policy", "both fixture-only policies are required")
    return result


def _entry_expected_postings(
    record: dict[str, Any], policy_id: str, phase: str, context: str
) -> tuple[list[tuple[str, str]], Decimal, str, str, int]:
    event = record["event"]
    effective_date = record["effective_at"][:10]
    if event["type"] == "cash_movement":
        if phase != "immediate":
            _fail("policy_context_mismatch", f"{context} cash phase must be immediate")
        return (
            [("debit", ACCOUNTS["cash"]), ("credit", ACCOUNTS["contributed_capital"])],
            Decimal(event["amount"]),
            effective_date,
            "USD",
            0,
        )

    quantity = Decimal(event["quantity"])
    raw_value = abs(quantity) * Decimal(event["price"])
    value = raw_value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    settlement_date = event["settlement_date"]
    if quantity < 0:
        if record["action"] != "reverse" or record["reverses_record_id"] is None:
            _fail("invalid_reversal_treatment", f"{context} negative trade is not a reversal")
        if policy_id == "fixture.trade-date.v1" and phase == "trade_date":
            postings = [
                ("debit", ACCOUNTS["receivable"]),
                ("credit", ACCOUNTS["securities"]),
            ]
            return postings, value, effective_date, "USD", 0
        if phase == "settlement_date":
            postings = [("debit", ACCOUNTS["cash"]), ("credit", ACCOUNTS["receivable"])]
            if policy_id == "fixture.settlement-date.v1":
                postings[1] = ("credit", ACCOUNTS["securities"])
            return postings, value, settlement_date, "USD", 1
        _fail("invalid_reversal_treatment", f"{context} has invalid reversal phase")

    if policy_id == "fixture.trade-date.v1" and phase == "trade_date":
        return (
            [("debit", ACCOUNTS["securities"]), ("credit", ACCOUNTS["payable"])],
            value,
            effective_date,
            "USD",
            0,
        )
    if phase == "settlement_date":
        postings = [("debit", ACCOUNTS["payable"]), ("credit", ACCOUNTS["cash"])]
        if policy_id == "fixture.settlement-date.v1":
            postings[0] = ("debit", ACCOUNTS["securities"])
        return postings, value, settlement_date, "USD", 1
    _fail("policy_context_mismatch", f"{context} has invalid positive-trade phase")


def _validate_entries(
    document: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    entries: dict[str, dict[str, Any]] = {}
    lines: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(
        _objects(document.get("journal_entries"), "journal_entries", nonempty=True)
    ):
        context = f"journal_entries[{index}]"
        _keys(
            entry,
            {
                "journal_entry_id",
                "policy",
                "event_type",
                "active_record_id",
                "effective_at",
                "recorded_at",
                "recognized_on",
                "recognition_phase",
                "phase_ordinal",
                "settlement_context",
                "lineage",
                "lines",
            },
            context,
        )
        entry_id = _string(entry["journal_entry_id"], f"{context}.journal_entry_id")
        if entry_id in entries:
            _fail("duplicate_identity", f"duplicate journal entry {entry_id!r}")
        policy_id, policy_version = _policy_ref(entry["policy"], f"{context}.policy")
        if policy_id not in policies or policy_version != policies[policy_id]["version"]:
            _fail("policy_context_mismatch", f"{context} has unknown policy identity/version")
        record_id = _string(entry["active_record_id"], f"{context}.active_record_id")
        if record_id not in records:
            _fail("lineage_mismatch", f"{context} references an unknown active record")
        record = records[record_id]
        if entry["event_type"] != record["event"]["type"]:
            _fail("lineage_mismatch", f"{context}.event_type differs from its record")
        if entry["effective_at"] != record["effective_at"]:
            _fail("lineage_mismatch", f"{context}.effective_at differs from its record")
        if entry["recorded_at"] != record["recorded_at"]:
            _fail("lineage_mismatch", f"{context}.recorded_at differs from its record")
        _timestamp(entry["effective_at"], f"{context}.effective_at")
        _timestamp(entry["recorded_at"], f"{context}.recorded_at")
        _date(entry["recognized_on"], f"{context}.recognized_on")
        phase = entry["recognition_phase"]
        if phase not in {"immediate", "trade_date", "settlement_date"}:
            _fail("policy_context_mismatch", f"{context}.recognition_phase is invalid")

        settlement_context = _object(entry["settlement_context"], f"{context}.settlement_context")
        _keys(
            settlement_context,
            {"trade_date", "settlement_date", "recognition_rule"},
            f"{context}.settlement_context",
        )
        event = record["event"]
        expected_settlement = (
            {"trade_date": None, "settlement_date": None, "recognition_rule": "immediate"}
            if event["type"] == "cash_movement"
            else {
                "trade_date": record["effective_at"][:10],
                "settlement_date": event["settlement_date"],
                "recognition_rule": policies[policy_id]["recognition"][
                    "negative_exact_reversal" if Decimal(event["quantity"]) < 0 else "positive_equity_trade"
                ],
            }
        )
        if settlement_context != expected_settlement:
            _fail("policy_context_mismatch", f"{context}.settlement_context is inconsistent")

        expected_lineage = _expected_lineage(record, records)
        _validate_lineage(
            entry["lineage"],
            f"{context}.lineage",
            expected_lineage,
            records,
            source_records,
        )
        expected_postings, expected_amount, recognized_on, currency, phase_ordinal = (
            _entry_expected_postings(record, policy_id, phase, context)
        )
        if entry["recognized_on"] != recognized_on or entry["phase_ordinal"] != phase_ordinal:
            category = "invalid_reversal_treatment" if record["action"] == "reverse" else "policy_context_mismatch"
            _fail(category, f"{context} recognition timing is inconsistent")

        entry_lines = _objects(entry["lines"], f"{context}.lines", nonempty=True)
        if len(entry_lines) != 2:
            _fail("unbalanced_entry", f"{context} must contain exactly two fixture lines")
        debit_total = Decimal(0)
        credit_total = Decimal(0)
        currencies: set[str] = set()
        actual_postings: list[tuple[str, str]] = []
        actual_amounts: list[Decimal] = []
        for line_index, line in enumerate(entry_lines):
            line_context = f"{context}.lines[{line_index}]"
            _keys(
                line,
                {
                    "journal_line_id",
                    "journal_entry_id",
                    "account_id",
                    "side",
                    "amount",
                    "currency",
                    "lineage",
                },
                line_context,
            )
            line_id = _string(line["journal_line_id"], f"{line_context}.journal_line_id")
            if line_id in lines:
                _fail("duplicate_identity", f"duplicate journal line {line_id!r}")
            if line["journal_entry_id"] != entry_id:
                _fail("lineage_mismatch", f"{line_context} names the wrong parent entry")
            account_id = _string(line["account_id"], f"{line_context}.account_id")
            if account_id not in ACCOUNTS.values():
                _fail("policy_context_mismatch", f"{line_context} uses an undeclared account")
            side = line["side"]
            if side not in {"debit", "credit"}:
                _fail("schema_shape", f"{line_context}.side must be debit or credit")
            amount = _money(line["amount"], f"{line_context}.amount", positive=True)
            line_currency = _currency(line["currency"], f"{line_context}.currency")
            currencies.add(line_currency)
            _validate_lineage(
                line["lineage"],
                f"{line_context}.lineage",
                expected_lineage,
                records,
                source_records,
            )
            if side == "debit":
                debit_total += amount
            else:
                credit_total += amount
            actual_postings.append((side, account_id))
            actual_amounts.append(amount)
            lines[line_id] = line

        if len(currencies) != 1:
            _fail("mixed_currency_entry", f"{context} cannot balance across currencies")
        if debit_total != credit_total:
            _fail("unbalanced_entry", f"{context} debit and credit totals differ")
        reversal = record["action"] == "reverse"
        if actual_postings != expected_postings:
            category = "invalid_reversal_treatment" if reversal else "policy_context_mismatch"
            _fail(category, f"{context} postings differ from the fixture policy")
        if any(amount != expected_amount for amount in actual_amounts):
            _fail("rounding_mismatch", f"{context} lines differ from the rounded event value")
        if currencies != {currency}:
            _fail("policy_context_mismatch", f"{context} currency differs from its event")
        entries[entry_id] = entry
    return entries, lines


def _validate_context(value: Any, context: str) -> dict[str, Any]:
    result = _object(value, context)
    _keys(
        result,
        {"resolution_id", "recorded_through", "economic_as_of", "settlement_as_of_date"},
        context,
    )
    _string(result["resolution_id"], f"{context}.resolution_id")
    _timestamp(result["recorded_through"], f"{context}.recorded_through")
    _timestamp(result["economic_as_of"], f"{context}.economic_as_of")
    _date(result["settlement_as_of_date"], f"{context}.settlement_as_of_date")
    return result


def _validate_resolved_inputs(
    value: Any,
    context: str,
    expected_active: list[str],
    cutoff: dict[str, Any],
    records: dict[str, dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    inputs = _objects(value, context, nonempty=True)
    active_ids: list[str] = []
    economic_ids: set[str] = set()
    for index, item in enumerate(inputs):
        item_context = f"{context}[{index}]"
        _keys(item, {"active_record_id", "lineage"}, item_context)
        record_id = _string(item["active_record_id"], f"{item_context}.active_record_id")
        if record_id not in records:
            _fail("lineage_mismatch", f"{item_context} references unknown active record")
        if record_id in active_ids:
            _fail("duplicate_identity", f"{context} repeats active record {record_id!r}")
        record = records[record_id]
        if record["economic_event_id"] in economic_ids:
            _fail("lineage_mismatch", f"{context} has two heads for one economic event")
        if _timestamp(record["recorded_at"], f"record {record_id}.recorded_at") > _timestamp(
            cutoff["recorded_through"], f"{context}.recorded_through"
        ):
            _fail("invalid_cutoff", f"{record_id!r} is not known at the recorded cutoff")
        if _timestamp(record["effective_at"], f"record {record_id}.effective_at") > _timestamp(
            cutoff["economic_as_of"], f"{context}.economic_as_of"
        ):
            _fail("invalid_cutoff", f"{record_id!r} is after the economic cutoff")
        _validate_lineage(
            item["lineage"],
            f"{item_context}.lineage",
            _expected_lineage(record, records),
            records,
            source_records,
        )
        active_ids.append(record_id)
        economic_ids.add(record["economic_event_id"])
    if active_ids != expected_active:
        _fail("portfolio_cross_check", f"{context} differs from the bounded O2 resolution")
    return inputs


def _validate_portfolio_state(value: Any, context: str, expected: dict[str, Any]) -> dict[str, Any]:
    state = _object(value, context)
    _keys(state, {"positions", "settled_cash", "open_settlement_obligations"}, context)
    positions = _objects(state["positions"], f"{context}.positions")
    expected_position = expected["position"]
    if expected_position == "0.00000000":
        if positions:
            _fail("portfolio_cross_check", f"{context}.positions must omit a zero position")
    else:
        if positions != [
            {"account": "fund-a", "instrument": "MSFT", "quantity": expected_position}
        ]:
            _fail("portfolio_cross_check", f"{context}.positions differ from the bounded state")
        _quantity(positions[0]["quantity"], f"{context}.positions[0].quantity")

    cash = _objects(state["settled_cash"], f"{context}.settled_cash", nonempty=True)
    if cash != [{"account": "fund-a", "currency": "USD", "amount": expected["cash"]}]:
        _fail("portfolio_cross_check", f"{context}.settled_cash differs from the bounded state")

    obligations = _objects(
        state["open_settlement_obligations"], f"{context}.open_settlement_obligations"
    )
    if expected["obligation"] is None:
        if obligations:
            _fail("portfolio_cross_check", f"{context} must have no open obligation")
    else:
        direction, amount, settlement_date = expected["obligation"]
        expected_obligation = [{
            "account": "fund-a",
            "currency": "USD",
            "direction": direction,
            "amount": amount,
            "settlement_date": settlement_date,
        }]
        if obligations != expected_obligation:
            _fail("portfolio_cross_check", f"{context} obligation differs from the bounded state")
    return state


def _eligible_entries(
    entries: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    policy_id: str,
    active_ids: list[str],
    context: dict[str, Any],
) -> list[str]:
    settlement_cutoff = _date(context["settlement_as_of_date"], "settlement cutoff")
    eligible: list[dict[str, Any]] = []
    for entry in entries.values():
        entry_policy_id, _ = _policy_ref(entry["policy"], "entry.policy")
        if entry_policy_id != policy_id or entry["active_record_id"] not in active_ids:
            continue
        if (
            entry["recognition_phase"] == "settlement_date"
            and _date(entry["recognized_on"], "entry.recognized_on") > settlement_cutoff
        ):
            continue
        eligible.append(entry)
    eligible.sort(
        key=lambda entry: (
            entry["recognized_on"],
            records[entry["active_record_id"]]["acceptance_sequence"],
            entry["phase_ordinal"],
            entry["journal_entry_id"],
        )
    )
    return [entry["journal_entry_id"] for entry in eligible]


def _computed_balances(
    selected_ids: list[str], entries: dict[str, dict[str, Any]]
) -> tuple[dict[str, Decimal], dict[tuple[str, str], tuple[Decimal, list[str]]], list[str]]:
    debits = Decimal(0)
    credits = Decimal(0)
    accounts: dict[tuple[str, str], tuple[Decimal, list[str]]] = {}
    for entry_id in selected_ids:
        for line in entries[entry_id]["lines"]:
            amount = Decimal(line["amount"])
            signed = amount if line["side"] == "debit" else -amount
            debits += amount if line["side"] == "debit" else Decimal(0)
            credits += amount if line["side"] == "credit" else Decimal(0)
            key = (line["account_id"], line["currency"])
            prior, line_ids = accounts.get(key, (Decimal(0), []))
            accounts[key] = (prior + signed, line_ids + [line["journal_line_id"]])
    accounts = {key: value for key, value in accounts.items() if value[0] != 0}
    return {"debits": debits, "credits": credits}, accounts, selected_ids


def _money_text(value: Decimal) -> str:
    return format(value, ".6f")


def _validate_balances(
    value: Any,
    context: str,
    selected_ids: list[str],
    entries: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], tuple[Decimal, list[str]]]:
    balances = _object(value, context)
    _keys(balances, {"currency_totals", "account_balances"}, context)
    totals, accounts, ordered_ids = _computed_balances(selected_ids, entries)
    currency_totals = _objects(
        balances["currency_totals"], f"{context}.currency_totals", nonempty=True
    )
    expected_currency_total = [{
        "balance_id": f"{context}.usd-total",
        "currency": "USD",
        "debits": _money_text(totals["debits"]),
        "credits": _money_text(totals["credits"]),
        "journal_entry_ids": ordered_ids,
    }]
    if currency_totals != expected_currency_total:
        _fail("portfolio_cross_check", f"{context}.currency_totals are incorrect or untraceable")
    if totals["debits"] != totals["credits"]:
        _fail("unbalanced_entry", f"{context} aggregate journal is not balanced")

    actual_account_balances = _objects(
        balances["account_balances"], f"{context}.account_balances", nonempty=True
    )
    expected_account_balances = []
    for (account_id, currency), (net, line_ids) in sorted(accounts.items()):
        expected_account_balances.append({
            "balance_id": f"{context}.{account_id}.{currency}",
            "account_id": account_id,
            "currency": currency,
            "side": "debit" if net > 0 else "credit",
            "amount": _money_text(abs(net)),
            "journal_line_ids": line_ids,
        })
    if actual_account_balances != expected_account_balances:
        _fail("portfolio_cross_check", f"{context}.account_balances are incorrect or untraceable")
    ids = [item["balance_id"] for item in currency_totals + actual_account_balances]
    if len(ids) != len(set(ids)):
        _fail("duplicate_identity", f"{context} contains duplicate balance identities")
    return accounts


def _account_amount(
    accounts: dict[tuple[str, str], tuple[Decimal, list[str]]], account_id: str
) -> Decimal:
    return accounts.get((account_id, "USD"), (Decimal(0), []))[0]


def _validate_cross_check(
    value: Any,
    context: str,
    policy_id: str,
    expected: dict[str, Any],
    accounts: dict[tuple[str, str], tuple[Decimal, list[str]]],
) -> None:
    cross = _object(value, context)
    _keys(
        cross,
        {
            "account",
            "instrument",
            "currency",
            "position_quantity",
            "settled_cash_amount",
            "open_settlement_direction",
            "open_settlement_amount",
            "journal_cash_balance",
            "journal_control_account",
            "journal_control_balance",
            "status",
        },
        context,
    )
    obligation = expected["obligation"]
    expected_direction = obligation[0] if obligation else None
    expected_open_amount = obligation[1] if obligation else "0.000000"
    cash_net = _account_amount(accounts, ACCOUNTS["cash"])
    if cash_net < 0:
        _fail("portfolio_cross_check", f"{context} cash has an unexpected credit balance")
    if obligation and policy_id == "fixture.trade-date.v1":
        control_account = ACCOUNTS["payable"] if obligation[0] == "payable" else ACCOUNTS["receivable"]
        control_net = _account_amount(accounts, control_account)
        expected_control = -Decimal(obligation[1]) if obligation[0] == "payable" else Decimal(obligation[1])
        if control_net != expected_control:
            _fail("portfolio_cross_check", f"{context} settlement control differs from portfolio")
        control_amount = obligation[1]
    else:
        control_account = None
        control_amount = "0.000000"
    expected_cross = {
        "account": "fund-a",
        "instrument": "MSFT",
        "currency": "USD",
        "position_quantity": expected["position"],
        "settled_cash_amount": expected["cash"],
        "open_settlement_direction": expected_direction,
        "open_settlement_amount": expected_open_amount,
        "journal_cash_balance": _money_text(cash_net),
        "journal_control_account": control_account,
        "journal_control_balance": control_amount,
        "status": "consistent",
    }
    if cross != expected_cross or cross["journal_cash_balance"] != expected["cash"]:
        _fail("portfolio_cross_check", f"{context} does not match portfolio state")


def _validate_result(
    result: dict[str, Any],
    context: str,
    evaluation: dict[str, Any],
    expected: dict[str, Any],
    active_ids: list[str],
    policies: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    entries: dict[str, dict[str, Any]],
) -> str:
    _keys(
        result,
        {
            "result_id",
            "engine_version",
            "projection_version",
            "policy",
            "evaluation_context",
            "inputs",
            "journal_entry_ids",
            "balances",
            "cross_check",
            "policy_difference",
            "compatibility",
        },
        context,
    )
    result_id = _string(result["result_id"], f"{context}.result_id")
    if result["engine_version"] != ENGINE_VERSION or result["projection_version"] != PROJECTION_VERSION:
        _fail("policy_context_mismatch", f"{context} engine/projection version is incompatible")
    policy_id, version = _policy_ref(result["policy"], f"{context}.policy")
    if policy_id not in policies or version != policies[policy_id]["version"]:
        _fail("policy_context_mismatch", f"{context} policy identity/version is incompatible")
    if result["evaluation_context"] != evaluation["context"]:
        _fail("invalid_cutoff", f"{context} does not preserve all evaluation cutoffs")

    inputs = _object(result["inputs"], f"{context}.inputs")
    _keys(
        inputs,
        {
            "lifecycle_contract_version",
            "resolution_id",
            "active_record_ids",
            "economic_event_ids",
            "source_record_ids",
        },
        f"{context}.inputs",
    )
    expected_economic_ids = [records[record_id]["economic_event_id"] for record_id in active_ids]
    expected_source_ids: list[str] = []
    for record_id in active_ids:
        for source_id in _expected_lineage(records[record_id], records)["source_record_ids"]:
            if source_id not in expected_source_ids:
                expected_source_ids.append(source_id)
    expected_inputs = {
        "lifecycle_contract_version": LIFECYCLE_VERSION,
        "resolution_id": evaluation["context"]["resolution_id"],
        "active_record_ids": active_ids,
        "economic_event_ids": expected_economic_ids,
        "source_record_ids": expected_source_ids,
    }
    if inputs != expected_inputs:
        _fail("policy_context_mismatch", f"{context}.inputs differ from the resolved set")

    selected_ids = _strings(result["journal_entry_ids"], f"{context}.journal_entry_ids")
    if any(entry_id not in entries for entry_id in selected_ids):
        _fail("policy_context_mismatch", f"{context} selects unknown journal entries")
    expected_entry_ids = _eligible_entries(
        entries,
        records,
        policy_id,
        active_ids,
        evaluation["context"],
    )
    if selected_ids != expected_entry_ids:
        _fail("policy_context_mismatch", f"{context} selects entries incompatible with policy/cutoff")
    accounts = _validate_balances(result["balances"], f"{result_id}.balances", selected_ids, entries)
    _validate_cross_check(result["cross_check"], f"{context}.cross_check", policy_id, expected, accounts)
    _string(result["policy_difference"], f"{context}.policy_difference")
    compatibility = _object(result["compatibility"], f"{context}.compatibility")
    _keys(
        compatibility,
        {"reuse_key", "prior_result_reuse"},
        f"{context}.compatibility",
    )
    expected_reuse_key = {
        "engine_version": ENGINE_VERSION,
        "projection_version": PROJECTION_VERSION,
        "policy_id": policy_id,
        "policy_version": version,
        "resolution_id": evaluation["context"]["resolution_id"],
        "recorded_through": evaluation["context"]["recorded_through"],
        "economic_as_of": evaluation["context"]["economic_as_of"],
        "settlement_as_of_date": evaluation["context"]["settlement_as_of_date"],
    }
    if compatibility != {
        "reuse_key": expected_reuse_key,
        "prior_result_reuse": "rejected_on_any_key_change",
    }:
        _fail("policy_context_mismatch", f"{context} does not invalidate incompatible results")
    return policy_id


def validate_accounting_scenario(document: Any) -> None:
    document = _object(document, "document")
    _keys(
        document,
        {
            "contract_version",
            "fixture_id",
            "fixture_kind",
            "engine_version",
            "projection_version",
            "lifecycle_contract_version",
            "scope",
            "policies",
            "source_records",
            "lifecycle_records",
            "journal_entries",
            "evaluations",
        },
        "document",
    )
    if document["contract_version"] != CONTRACT_VERSION:
        _fail("schema_shape", "unsupported contract_version")
    if document["fixture_id"] != "valid.cash-equity-lifecycle":
        _fail("schema_shape", "unexpected fixture_id")
    if document["fixture_kind"] != "accounting_scenario":
        _fail("schema_shape", "fixture_kind must be accounting_scenario")
    if document["engine_version"] != ENGINE_VERSION or document["projection_version"] != PROJECTION_VERSION:
        _fail("policy_context_mismatch", "document version identity is incompatible")
    if document["lifecycle_contract_version"] != LIFECYCLE_VERSION:
        _fail("policy_context_mismatch", "lifecycle contract version is incompatible")
    expected_scope = {
        "fixture_only": True,
        "production_accounting_approval": False,
        "standards_claimed": [],
        "hidden_io": False,
    }
    if document["scope"] != expected_scope:
        _fail("invalid_policy", "scope must retain the fixture-only disclaimer")

    source_records = _validate_source_records(document)
    records = _validate_records(document, source_records)
    policies = _validate_policies(document)
    entries, _ = _validate_entries(document, policies, records, source_records)

    evaluations = _objects(document["evaluations"], "evaluations", nonempty=True)
    seen_evaluations: set[str] = set()
    seen_results: set[str] = set()
    for index, evaluation in enumerate(evaluations):
        context = f"evaluations[{index}]"
        _keys(
            evaluation,
            {
                "evaluation_id",
                "context",
                "resolved_inputs",
                "portfolio_state",
                "results",
                "hand_calculations",
            },
            context,
        )
        evaluation_id = _string(evaluation["evaluation_id"], f"{context}.evaluation_id")
        if evaluation_id in seen_evaluations:
            _fail("duplicate_identity", f"duplicate evaluation {evaluation_id!r}")
        seen_evaluations.add(evaluation_id)
        expected = EXPECTED_EVALUATIONS.get(evaluation_id)
        if expected is None:
            _fail("portfolio_cross_check", f"unexpected bounded evaluation {evaluation_id!r}")
        cutoff = _validate_context(evaluation["context"], f"{context}.context")
        resolved = _validate_resolved_inputs(
            evaluation["resolved_inputs"],
            f"{context}.resolved_inputs",
            expected["active"],
            cutoff,
            records,
            source_records,
        )
        active_ids = [item["active_record_id"] for item in resolved]
        _validate_portfolio_state(
            evaluation["portfolio_state"], f"{context}.portfolio_state", expected
        )
        if evaluation["hand_calculations"] != expected["calculation"]:
            _fail("portfolio_cross_check", f"{context}.hand_calculations are not the reviewed arithmetic")
        policy_ids: set[str] = set()
        for result_index, result in enumerate(
            _objects(evaluation["results"], f"{context}.results", nonempty=True)
        ):
            result_id = result.get("result_id")
            if result_id in seen_results:
                _fail("duplicate_identity", f"duplicate result {result_id!r}")
            seen_results.add(result_id)
            policy_id = _validate_result(
                result,
                f"{context}.results[{result_index}]",
                evaluation,
                expected,
                active_ids,
                policies,
                records,
                entries,
            )
            if policy_id in policy_ids:
                _fail("duplicate_identity", f"{context} repeats policy result {policy_id!r}")
            policy_ids.add(policy_id)
        if policy_ids != set(EXPECTED_POLICIES):
            _fail("policy_context_mismatch", f"{context} must evaluate both policies side by side")
    if set(seen_evaluations) != set(EXPECTED_EVALUATIONS):
        _fail("portfolio_cross_check", "the bounded lifecycle walkthrough is incomplete")


def _apply_mutation(document: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(document)
    _keys(mutation, {"operation", "path", "value"}, "mutation")
    path = mutation["path"]
    if not isinstance(path, list) or not path:
        _fail("schema_shape", "mutation.path must be non-empty")
    target: Any = mutated
    for component in path[:-1]:
        target = target[component]
    final = path[-1]
    if mutation["operation"] == "replace":
        target[final] = mutation["value"]
    elif mutation["operation"] == "replace_all_line_amounts":
        lines = target[final]
        if not isinstance(lines, list):
            _fail("schema_shape", "replace_all_line_amounts must target a line array")
        for line in lines:
            line["amount"] = mutation["value"]
    elif mutation["operation"] == "remove":
        del target[final]
    else:
        _fail(
            "schema_shape",
            "mutation.operation must be replace, remove, or replace_all_line_amounts",
        )
    return mutated


def _validate_invalid_manifest(document: Any) -> list[dict[str, Any]]:
    invalid = _object(document, "invalid fixture")
    _keys(
        invalid,
        {"contract_version", "fixture_id", "fixture_kind", "base_fixture_id", "cases"},
        "invalid fixture",
    )
    if invalid["contract_version"] != CONTRACT_VERSION:
        _fail("schema_shape", "invalid fixture has unsupported contract_version")
    if invalid["fixture_id"] != "invalid.accounting-mutations":
        _fail("schema_shape", "invalid fixture has an unexpected fixture_id")
    if invalid["fixture_kind"] != "invalid_mutations":
        _fail("schema_shape", "invalid fixture has the wrong fixture_kind")
    if invalid["base_fixture_id"] != "valid.cash-equity-lifecycle":
        _fail("schema_shape", "invalid fixture names the wrong baseline")
    cases = _objects(invalid["cases"], "invalid fixture.cases", nonempty=True)
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        context = f"invalid fixture.cases[{index}]"
        _keys(case, {"case_id", "expected_category", "mutation"}, context)
        case_id = _string(case["case_id"], f"{context}.case_id")
        if case_id in case_ids:
            _fail("duplicate_identity", f"duplicate invalid case {case_id!r}")
        case_ids.add(case_id)
        if case["expected_category"] not in STABLE_DIAGNOSTICS:
            _fail("schema_shape", f"{context} names an unstable diagnostic")
        mutation = _object(case["mutation"], f"{context}.mutation")
        _keys(mutation, {"operation", "path", "value"}, f"{context}.mutation")
        if not isinstance(mutation["path"], list) or not mutation["path"]:
            _fail("schema_shape", f"{context}.mutation.path must be non-empty")
    return cases


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


class AccountingFoundationsContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = {path.name: _load_json(path) for path in sorted(FIXTURE_ROOT.glob("*.json"))}
        cls.valid = cls.documents[VALID_FIXTURE.name]
        cls.invalid = cls.documents[INVALID_FIXTURE.name]

    def test_every_json_fixture_parses_independently(self) -> None:
        self.assertEqual(
            set(self.documents),
            {"invalid-mutations.json", "valid-cash-equity-lifecycle.json"},
        )
        for path in sorted(FIXTURE_ROOT.glob("*.json")):
            self.assertIsNotNone(_load_json(path), path.name)

    def test_valid_fixture_validates_twice(self) -> None:
        validate_accounting_scenario(copy.deepcopy(self.valid))
        validate_accounting_scenario(copy.deepcopy(self.valid))

    def test_invalid_vectors_cover_and_repeat_every_stable_category(self) -> None:
        cases = _validate_invalid_manifest(copy.deepcopy(self.invalid))
        _validate_invalid_manifest(copy.deepcopy(self.invalid))
        case_ids: set[str] = set()
        categories: set[str] = set()
        for case in cases:
            _keys(case, {"case_id", "expected_category", "mutation"}, "invalid case")
            case_id = _string(case["case_id"], "invalid case.case_id")
            self.assertNotIn(case_id, case_ids)
            case_ids.add(case_id)
            expected_category = case["expected_category"]
            self.assertIn(expected_category, STABLE_DIAGNOSTICS)
            categories.add(expected_category)
            for _ in range(2):
                mutated = _apply_mutation(self.valid, case["mutation"])
                with self.assertRaises(ContractError, msg=case_id) as raised:
                    validate_accounting_scenario(mutated)
                self.assertEqual(raised.exception.category, expected_category, case_id)
        self.assertEqual(categories, STABLE_DIAGNOSTICS)
        self.assertTrue({"zero-line", "inexact-line"}.issubset(case_ids))
        self.assertTrue({"missing-lineage", "mismatched-lineage"}.issubset(case_ids))
        self.assertTrue(
            {
                "portfolio-position-mismatch",
                "portfolio-cash-mismatch",
                "portfolio-settlement-mismatch",
            }.issubset(case_ids)
        )

    def test_policies_are_observably_different_from_same_resolved_inputs(self) -> None:
        for evaluation in self.valid["evaluations"]:
            results = {result["policy"]["policy_id"]: result for result in evaluation["results"]}
            trade = results["fixture.trade-date.v1"]
            settlement = results["fixture.settlement-date.v1"]
            self.assertEqual(trade["inputs"], settlement["inputs"])
            if evaluation["portfolio_state"]["open_settlement_obligations"]:
                self.assertNotEqual(trade["journal_entry_ids"], settlement["journal_entry_ids"])


if __name__ == "__main__":
    unittest.main()
