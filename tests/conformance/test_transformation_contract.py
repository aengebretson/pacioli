"""Dependency-free validator for the O5 transformation contract fixtures.

The fixtures are a semantic design vocabulary, not production serialization.
This validator checks declarations, compatibility, exact decimal assertions,
and references.  It intentionally does not replay LUCA portfolio projections.
"""

from __future__ import annotations

import json
import re
import unittest
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "transformation-contract"
CONTRACT_VERSION = "luca.transformation-contract.v1"
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class ContractError(ValueError):
    def __init__(self, category: str, message: str):
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


def _strings(
    value: Any, context: str, *, nonempty: bool = False, unique: bool = True
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        _fail("schema_shape", f"{context} must be an array of non-empty strings")
    if nonempty and not value:
        _fail("schema_shape", f"{context} must not be empty")
    if unique and len(value) != len(set(value)):
        _fail("duplicate_identity", f"{context} must not contain duplicates")
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


def _identifier(value: Any, context: str) -> str:
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        _fail("invalid_identifier", f"{context} must be a stable lower-case identifier")
    return value


def _version(value: Any, context: str) -> str:
    if not isinstance(value, str) or VERSION.fullmatch(value) is None:
        _fail("invalid_identifier", f"{context} must be a non-empty version identifier")
    return value


def _timestamp(value: Any, context: str) -> str:
    if not isinstance(value, str) or TIMESTAMP.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid timestamp: {error}")
    if parsed.tzinfo is None:
        _fail("schema_shape", f"{context} must include a timezone")
    return value


def _date(value: Any, context: str) -> str:
    if not isinstance(value, str):
        _fail("schema_shape", f"{context} must be an ISO 8601 date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        _fail("schema_shape", f"{context} is not a valid date: {error}")
    return value


def _decimal(value: Any, context: str, scale: int | None = None) -> Decimal:
    if not isinstance(value, str) or DECIMAL.fullmatch(value) is None:
        _fail("schema_shape", f"{context} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:  # pragma: no cover - guarded by regex
        _fail("schema_shape", f"{context} is not a decimal: {error}")
    if scale is not None and max(0, -result.as_tuple().exponent) > scale:
        _fail("schema_shape", f"{context} exceeds declared scale {scale}")
    return result


def _port(value: Any, context: str) -> dict[str, Any]:
    port = _object(value, context)
    _keys(port, {"name", "type", "unit", "currency"}, context)
    _identifier(port.get("name"), f"{context}.name")
    _string(port, "type", context)
    _string(port, "unit", context)
    currency = port.get("currency")
    if currency is not None and (not isinstance(currency, str) or CURRENCY.fullmatch(currency) is None):
        _fail("schema_shape", f"{context}.currency must be null or an uppercase currency")
    return port


LAW_VALUES = {"proved", "not_claimed", "counterexample"}


def _operation(value: Any, context: str) -> dict[str, Any]:
    operation = _object(value, context)
    _keys(
        operation,
        {
            "id",
            "classification",
            "input_ports",
            "output_port",
            "operation_version",
            "policy",
            "evaluation_context",
            "ordering",
            "partitioning",
            "rounding",
            "errors",
            "lineage",
            "laws",
        },
        context,
    )
    _identifier(operation.get("id"), f"{context}.id")
    if operation.get("classification") not in {
        "normalization",
        "map",
        "ordered_fold",
        "reduction",
        "comparison",
    }:
        _fail("schema_shape", f"{context}.classification is not supported")

    ports = [_port(port, f"{context}.input_ports[{index}]") for index, port in enumerate(
        _objects(operation.get("input_ports"), f"{context}.input_ports", nonempty=True)
    )]
    if len({port["name"] for port in ports}) != len(ports):
        _fail("duplicate_identity", f"{context}.input_ports has duplicate names")
    _port(operation.get("output_port"), f"{context}.output_port")
    _version(operation.get("operation_version"), f"{context}.operation_version")

    policy = _object(operation.get("policy"), f"{context}.policy")
    _keys(policy, {"id", "version"}, f"{context}.policy")
    _identifier(policy.get("id"), f"{context}.policy.id")
    _version(policy.get("version"), f"{context}.policy.version")

    evaluation = _object(operation.get("evaluation_context"), f"{context}.evaluation_context")
    _keys(
        evaluation,
        {
            "id",
            "engine_version",
            "recorded_through",
            "economic_as_of",
            "settlement_as_of_date",
        },
        f"{context}.evaluation_context",
    )
    _identifier(evaluation.get("id"), f"{context}.evaluation_context.id")
    _version(evaluation.get("engine_version"), f"{context}.evaluation_context.engine_version")
    _timestamp(evaluation.get("recorded_through"), f"{context}.evaluation_context.recorded_through")
    _timestamp(evaluation.get("economic_as_of"), f"{context}.evaluation_context.economic_as_of")
    _date(
        evaluation.get("settlement_as_of_date"),
        f"{context}.evaluation_context.settlement_as_of_date",
    )

    ordering = _object(operation.get("ordering"), f"{context}.ordering")
    _keys(ordering, {"required", "keys", "arbitrary_reordering"}, f"{context}.ordering")
    if not isinstance(ordering.get("required"), bool):
        _fail("schema_shape", f"{context}.ordering.required must be boolean")
    ordering_keys = _strings(ordering.get("keys"), f"{context}.ordering.keys")
    if ordering["required"] != bool(ordering_keys):
        _fail("ordering_metadata", f"{context}.ordering required flag and keys disagree")
    if ordering.get("arbitrary_reordering") not in {"equivalent", "rejected"}:
        _fail("ordering_metadata", f"{context}.ordering.arbitrary_reordering is invalid")
    if ordering["required"] and ordering["arbitrary_reordering"] != "rejected":
        _fail("ordering_metadata", f"{context} requires order but permits reordering")

    partitioning = _object(operation.get("partitioning"), f"{context}.partitioning")
    _keys(
        partitioning,
        {"supported", "keys", "merge_operation"},
        f"{context}.partitioning",
    )
    if not isinstance(partitioning.get("supported"), bool):
        _fail("schema_shape", f"{context}.partitioning.supported must be boolean")
    partition_keys = _strings(partitioning.get("keys"), f"{context}.partitioning.keys")
    merge_operation = partitioning.get("merge_operation")
    if partitioning["supported"]:
        if not partition_keys or not isinstance(merge_operation, str) or not merge_operation:
            _fail("partition_metadata", f"{context} supported partitioning needs keys and merge")
    elif partition_keys or merge_operation is not None:
        _fail("partition_metadata", f"{context} unsupported partitioning must not declare merge")

    rounding = _object(operation.get("rounding"), f"{context}.rounding")
    _keys(rounding, {"mode", "scale", "applies_at"}, f"{context}.rounding")
    if rounding.get("mode") not in {"none", "half_even", "not_applicable"}:
        _fail("rounding_metadata", f"{context}.rounding.mode is invalid")
    scale = rounding.get("scale")
    if scale is not None and (not isinstance(scale, int) or isinstance(scale, bool) or scale < 0):
        _fail("rounding_metadata", f"{context}.rounding.scale is invalid")
    if rounding["mode"] == "not_applicable" and scale is not None:
        _fail("rounding_metadata", f"{context} non-arithmetic rounding must have null scale")
    _string(rounding, "applies_at", f"{context}.rounding")

    errors = _strings(operation.get("errors"), f"{context}.errors", nonempty=True)
    for index, error in enumerate(errors):
        _identifier(error, f"{context}.errors[{index}]")

    lineage = _object(operation.get("lineage"), f"{context}.lineage")
    _keys(lineage, {"requires", "emits"}, f"{context}.lineage")
    _strings(lineage.get("requires"), f"{context}.lineage.requires", nonempty=True)
    emitted = set(
        _strings(lineage.get("emits"), f"{context}.lineage.emits", nonempty=True)
    )
    if not {
        "operation_version",
        "policy_version",
        "engine_version",
        "context_id",
    }.issubset(emitted):
        _fail("schema_shape", f"{context}.lineage.emits omits result version identity")

    laws = _object(operation.get("laws"), f"{context}.laws")
    _keys(
        laws,
        {
            "identity",
            "associativity",
            "commutativity",
            "invertibility",
            "distributivity",
            "domain",
        },
        f"{context}.laws",
    )
    for law in ("identity", "associativity", "commutativity", "invertibility", "distributivity"):
        if laws.get(law) not in LAW_VALUES:
            _fail("law_declaration", f"{context}.laws.{law} is invalid")
    _string(laws, "domain", f"{context}.laws")
    if operation["classification"] != "reduction" and any(
        laws[law] == "proved" for law in ("identity", "associativity", "commutativity")
    ):
        _fail("law_declaration", f"{context} claims a reduction law for a non-reduction")
    return operation


def _operations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(
        _objects(document.get("operations"), "operations", nonempty=True)
    ):
        operation = _operation(candidate, f"operations[{index}]")
        operation_id = operation["id"]
        if operation_id in result:
            _fail("duplicate_identity", f"duplicate operation id {operation_id!r}")
        result[operation_id] = operation
    return result


def _check_composition(
    value: Any, operations: dict[str, dict[str, Any]], context: str
) -> None:
    edge = _object(value, context)
    _keys(edge, {"from", "to", "to_port"}, context)
    source_id = _identifier(edge.get("from"), f"{context}.from")
    target_id = _identifier(edge.get("to"), f"{context}.to")
    port_name = _identifier(edge.get("to_port"), f"{context}.to_port")
    if source_id not in operations or target_id not in operations:
        _fail("lineage_reference_missing", f"{context} references an unknown operation")
    source = operations[source_id]
    target = operations[target_id]
    target_port = next(
        (port for port in target["input_ports"] if port["name"] == port_name), None
    )
    if target_port is None:
        _fail("operation_type_mismatch", f"{context} references an unknown target port")
    output = source["output_port"]
    if output["type"] == "RawLifecycleRecordSet" and target_port["type"] == "ResolvedEconomicEventSet":
        _fail("unresolved_lifecycle_input", f"{context} bypasses lifecycle resolution")
    if output["type"] != target_port["type"]:
        _fail("operation_type_mismatch", f"{context} port types are incompatible")
    if output["unit"] != target_port["unit"]:
        _fail("unit_mismatch", f"{context} port units are incompatible")
    if output["currency"] != target_port["currency"]:
        _fail("currency_mismatch", f"{context} port currencies are incompatible")
    if source["evaluation_context"] != target["evaluation_context"]:
        _fail("context_mismatch", f"{context} evaluation contexts are incompatible")


def _arithmetic(value: Any, context: str) -> Decimal:
    assertion = _object(value, context)
    _keys(assertion, {"id", "operator", "operands", "expected", "scale", "rounding"}, context)
    _identifier(assertion.get("id"), f"{context}.id")
    scale = assertion.get("scale")
    if not isinstance(scale, int) or isinstance(scale, bool) or scale < 0:
        _fail("schema_shape", f"{context}.scale must be a non-negative integer")
    operands = [
        _decimal(item, f"{context}.operands[{index}]")
        for index, item in enumerate(
            _strings(
                assertion.get("operands"),
                f"{context}.operands",
                nonempty=True,
                unique=False,
            )
        )
    ]
    operator = assertion.get("operator")
    if operator == "sum":
        result = sum(operands, Decimal(0))
    elif operator == "subtract" and len(operands) == 2:
        result = operands[0] - operands[1]
    elif operator == "product" and len(operands) == 2:
        result = operands[0] * operands[1]
    else:
        _fail("schema_shape", f"{context}.operator/operand count is unsupported")
    rounding = assertion.get("rounding")
    if rounding == "half_even":
        result = result.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN)
    elif rounding != "none":
        _fail("schema_shape", f"{context}.rounding is unsupported")
    expected = _decimal(assertion.get("expected"), f"{context}.expected", scale)
    if result != expected:
        _fail("arithmetic_mismatch", f"{context}: calculated {result}, expected {expected}")
    return expected


def _arithmetic_assertions(document: dict[str, Any]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for index, value in enumerate(
        _objects(document.get("arithmetic"), "arithmetic", nonempty=True)
    ):
        assertion_id = value.get("id")
        calculated = _arithmetic(value, f"arithmetic[{index}]")
        if assertion_id in result:
            _fail("duplicate_identity", f"duplicate arithmetic id {assertion_id!r}")
        result[assertion_id] = calculated
    return result


def _trace(
    value: Any, operations: dict[str, dict[str, Any]], context: str
) -> set[str]:
    entries = _objects(value, context, nonempty=True)
    traced: set[str] = set()
    for index, entry in enumerate(entries):
        item_context = f"{context}[{index}]"
        _keys(
            entry,
            {
                "operation_id",
                "operation_version",
                "policy_id",
                "policy_version",
                "engine_version",
                "context_id",
            },
            item_context,
        )
        operation_id = _identifier(entry.get("operation_id"), f"{item_context}.operation_id")
        if operation_id not in operations:
            _fail("lineage_reference_missing", f"{item_context} references an unknown operation")
        operation = operations[operation_id]
        expected = (
            operation["operation_version"],
            operation["policy"]["id"],
            operation["policy"]["version"],
            operation["evaluation_context"]["engine_version"],
            operation["evaluation_context"]["id"],
        )
        actual = (
            entry.get("operation_version"),
            entry.get("policy_id"),
            entry.get("policy_version"),
            entry.get("engine_version"),
            entry.get("context_id"),
        )
        if actual != expected:
            _fail("lineage_version_mismatch", f"{item_context} does not match its declaration")
        if operation_id in traced:
            _fail("duplicate_identity", f"{context} repeats operation {operation_id!r}")
        traced.add(operation_id)
    return traced


def _validate_reduction_fixture(
    document: dict[str, Any], operations: dict[str, dict[str, Any]]
) -> None:
    _keys(
        document,
        {
            "contract_version",
            "fixture_id",
            "fixture_kind",
            "operations",
            "values",
            "execution_modes",
            "expected_output",
            "arithmetic",
            "law_checks",
        },
        "document",
    )
    if len(operations) != 1:
        _fail("schema_shape", "a reduction-law fixture declares exactly one operation")
    operation = next(iter(operations.values()))
    if operation["classification"] != "reduction":
        _fail("schema_shape", "a reduction-law fixture requires a reduction operation")

    values: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_objects(document.get("values"), "values", nonempty=True)):
        context = f"values[{index}]"
        _keys(
            item,
            {"id", "account", "currency", "amount", "event_id", "source_record_ids"},
            context,
        )
        item_id = _identifier(item.get("id"), f"{context}.id")
        _string(item, "account", context)
        if not isinstance(item.get("currency"), str) or CURRENCY.fullmatch(item["currency"]) is None:
            _fail("schema_shape", f"{context}.currency is invalid")
        _decimal(item.get("amount"), f"{context}.amount", 6)
        _identifier(item.get("event_id"), f"{context}.event_id")
        _strings(item.get("source_record_ids"), f"{context}.source_record_ids", nonempty=True)
        if item_id in values:
            _fail("duplicate_identity", f"duplicate value id {item_id!r}")
        values[item_id] = item
    accounts = {item["account"] for item in values.values()}
    currencies = {item["currency"] for item in values.values()}
    if len(accounts) != 1 or len(currencies) != 1:
        _fail("partition_metadata", "the exact reduction example requires one compatible key")

    modes = _object(document.get("execution_modes"), "execution_modes")
    _keys(modes, {"full", "incremental", "partitioned"}, "execution_modes")
    full = _object(modes["full"], "execution_modes.full")
    _keys(full, {"value_ids", "expected_amount"}, "execution_modes.full")
    full_ids = _strings(full["value_ids"], "execution_modes.full.value_ids", nonempty=True)
    if set(full_ids) != set(values):
        _fail("lineage_reference_missing", "full execution must reference every value")
    full_sum = sum((_decimal(values[item]["amount"], item, 6) for item in full_ids), Decimal(0))
    if full_sum != _decimal(full["expected_amount"], "execution_modes.full.expected_amount", 6):
        _fail("arithmetic_mismatch", "full reduction amount is incorrect")

    incremental = _object(modes["incremental"], "execution_modes.incremental")
    _keys(
        incremental,
        {"prefix_value_ids", "prefix_amount", "suffix_value_ids", "expected_amount"},
        "execution_modes.incremental",
    )
    prefix = _strings(
        incremental["prefix_value_ids"], "execution_modes.incremental.prefix_value_ids", nonempty=True
    )
    suffix = _strings(
        incremental["suffix_value_ids"], "execution_modes.incremental.suffix_value_ids", nonempty=True
    )
    if prefix + suffix != full_ids:
        _fail("ordering_metadata", "incremental prefix and suffix must preserve the full input order")
    prefix_sum = sum((_decimal(values[item]["amount"], item, 6) for item in prefix), Decimal(0))
    if prefix_sum != _decimal(incremental["prefix_amount"], "incremental.prefix_amount", 6):
        _fail("arithmetic_mismatch", "incremental prefix amount is incorrect")
    incremental_sum = prefix_sum + sum(
        (_decimal(values[item]["amount"], item, 6) for item in suffix), Decimal(0)
    )
    if incremental_sum != _decimal(incremental["expected_amount"], "incremental.expected_amount", 6):
        _fail("arithmetic_mismatch", "incremental result is incorrect")

    partitioned = _object(modes["partitioned"], "execution_modes.partitioned")
    _keys(partitioned, {"partitions", "expected_amount"}, "execution_modes.partitioned")
    referenced: list[str] = []
    partials: list[Decimal] = []
    for index, partition in enumerate(
        _objects(partitioned["partitions"], "execution_modes.partitioned.partitions", nonempty=True)
    ):
        context = f"execution_modes.partitioned.partitions[{index}]"
        _keys(partition, {"id", "value_ids", "expected_amount"}, context)
        _identifier(partition.get("id"), f"{context}.id")
        ids = _strings(partition["value_ids"], f"{context}.value_ids", nonempty=True)
        if any(item not in values for item in ids):
            _fail("lineage_reference_missing", f"{context} references an unknown value")
        partial = sum((_decimal(values[item]["amount"], item, 6) for item in ids), Decimal(0))
        if partial != _decimal(partition["expected_amount"], f"{context}.expected_amount", 6):
            _fail("arithmetic_mismatch", f"{context} partial result is incorrect")
        referenced.extend(ids)
        partials.append(partial)
    if len(referenced) != len(set(referenced)) or set(referenced) != set(values):
        _fail("partition_metadata", "partitioned execution must cover every value exactly once")
    partition_sum = sum(partials, Decimal(0))
    if partition_sum != _decimal(partitioned["expected_amount"], "partitioned.expected_amount", 6):
        _fail("arithmetic_mismatch", "partition merge result is incorrect")
    if len({full_sum, incremental_sum, partition_sum}) != 1:
        _fail("execution_mode_mismatch", "full, incremental, and partitioned outputs differ")

    expected = _object(document.get("expected_output"), "expected_output")
    _keys(
        expected,
        {
            "account",
            "currency",
            "amount",
            "source_event_ids",
            "source_record_ids",
            "operation_trace",
        },
        "expected_output",
    )
    if expected.get("account") not in accounts or expected.get("currency") not in currencies:
        _fail("unit_mismatch", "expected output key does not match the reduced values")
    if _decimal(expected.get("amount"), "expected_output.amount", 6) != full_sum:
        _fail("arithmetic_mismatch", "expected output amount differs from execution modes")
    known_events = {item["event_id"] for item in values.values()}
    known_sources = {
        source for item in values.values() for source in item["source_record_ids"]
    }
    if set(_strings(expected["source_event_ids"], "expected_output.source_event_ids", nonempty=True)) != known_events:
        _fail("lineage_reference_missing", "expected output event lineage is incomplete")
    if set(_strings(expected["source_record_ids"], "expected_output.source_record_ids", nonempty=True)) != known_sources:
        _fail("lineage_reference_missing", "expected output source lineage is incomplete")
    if _trace(
        expected["operation_trace"], operations, "expected_output.operation_trace"
    ) != set(operations):
        _fail("lineage_reference_missing", "expected output operation trace is incomplete")

    _arithmetic_assertions(document)
    checks = _objects(document.get("law_checks"), "law_checks", nonempty=True)
    observed_laws: set[str] = set()
    for index, check in enumerate(checks):
        context = f"law_checks[{index}]"
        law = check.get("law")
        if law == "identity":
            _keys(check, {"id", "law", "value", "identity", "expected"}, context)
            result = _decimal(check["value"], f"{context}.value") + _decimal(
                check["identity"], f"{context}.identity"
            )
            expected_value = _decimal(check["expected"], f"{context}.expected")
            if result != expected_value or _decimal(check["value"], f"{context}.value") != expected_value:
                _fail("law_violation", f"{context} does not prove identity")
        elif law == "associativity":
            _keys(check, {"id", "law", "values", "expected"}, context)
            law_values = [
                _decimal(item, f"{context}.values[{position}]")
                for position, item in enumerate(_strings(check["values"], f"{context}.values", nonempty=True))
            ]
            if len(law_values) != 3:
                _fail("schema_shape", f"{context} needs three values")
            left = (law_values[0] + law_values[1]) + law_values[2]
            right = law_values[0] + (law_values[1] + law_values[2])
            if left != right or left != _decimal(check["expected"], f"{context}.expected"):
                _fail("law_violation", f"{context} does not prove associativity")
        elif law == "commutativity":
            _keys(check, {"id", "law", "left", "right", "expected"}, context)
            left = _decimal(check["left"], f"{context}.left")
            right = _decimal(check["right"], f"{context}.right")
            expected_value = _decimal(check["expected"], f"{context}.expected")
            if left + right != right + left or left + right != expected_value:
                _fail("law_violation", f"{context} does not prove commutativity")
        else:
            _fail("schema_shape", f"{context}.law is unsupported")
        _identifier(check.get("id"), f"{context}.id")
        observed_laws.add(law)
    if observed_laws != {"identity", "associativity", "commutativity"}:
        _fail("law_declaration", "reduction fixture must demonstrate its three claimed laws")
    for law in observed_laws:
        if operation["laws"][law] != "proved":
            _fail("law_declaration", f"operation does not declare {law} as proved")


def _validate_ordered_fixture(
    document: dict[str, Any], operations: dict[str, dict[str, Any]]
) -> None:
    _keys(
        document,
        {
            "contract_version",
            "fixture_id",
            "fixture_kind",
            "operations",
            "source_records",
            "records",
            "composition",
            "expected",
            "arithmetic",
            "ordering_counterexample",
            "invalidation_cases",
        },
        "document",
    )
    for index, edge in enumerate(_objects(document["composition"], "composition", nonempty=True)):
        try:
            _check_composition(edge, operations, f"composition[{index}]")
        except ContractError as error:
            _fail("declared_compatibility", f"composition[{index}] failed: {error}")

    sources = _strings(document.get("source_records"), "source_records", nonempty=True)
    records: dict[str, dict[str, Any]] = {}
    sequences: list[int] = []
    for index, record in enumerate(_objects(document.get("records"), "records", nonempty=True)):
        context = f"records[{index}]"
        _keys(
            record,
            {
                "record_id",
                "economic_event_id",
                "action",
                "acceptance_sequence",
                "recorded_at",
                "effective_at",
                "account",
                "supersedes_record_id",
                "source_record_ids",
                "event",
            },
            context,
        )
        record_id = _identifier(record.get("record_id"), f"{context}.record_id")
        _identifier(record.get("economic_event_id"), f"{context}.economic_event_id")
        action = record.get("action")
        if action not in {"originate", "correct"}:
            _fail("schema_shape", f"{context}.action is unsupported in this fixture")
        sequence = record.get("acceptance_sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            _fail("ordering_metadata", f"{context}.acceptance_sequence is invalid")
        sequences.append(sequence)
        _timestamp(record.get("recorded_at"), f"{context}.recorded_at")
        _timestamp(record.get("effective_at"), f"{context}.effective_at")
        _string(record, "account", context)
        predecessor = record.get("supersedes_record_id")
        if action == "originate" and predecessor is not None:
            _fail("schema_shape", f"{context} originate must not supersede")
        if action == "correct" and (not isinstance(predecessor, str) or not predecessor):
            _fail("schema_shape", f"{context} correction must supersede a record")
        record_sources = _strings(record.get("source_record_ids"), f"{context}.source_record_ids", nonempty=True)
        if any(source not in sources for source in record_sources):
            _fail("lineage_reference_missing", f"{context} references an unknown source record")
        event = _object(record.get("event"), f"{context}.event")
        _keys(
            event,
            {"type", "instrument", "quantity", "price", "quote_currency", "settlement_date"},
            f"{context}.event",
        )
        if event.get("type") != "equity_trade":
            _fail("schema_shape", f"{context}.event.type must be equity_trade")
        _string(event, "instrument", f"{context}.event")
        if _decimal(event.get("quantity"), f"{context}.event.quantity", 8) == 0:
            _fail("schema_shape", f"{context}.event.quantity must be non-zero")
        _decimal(event.get("price"), f"{context}.event.price", 8)
        if not isinstance(event.get("quote_currency"), str) or CURRENCY.fullmatch(event["quote_currency"]) is None:
            _fail("schema_shape", f"{context}.event.quote_currency is invalid")
        _date(event.get("settlement_date"), f"{context}.event.settlement_date")
        if record_id in records:
            _fail("duplicate_identity", f"duplicate record id {record_id!r}")
        records[record_id] = record
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        _fail("ordering_metadata", "records must be listed in unique acceptance order")
    for record in records.values():
        predecessor = record["supersedes_record_id"]
        if predecessor is not None:
            if predecessor not in records:
                _fail("lineage_reference_missing", "correction references an unknown predecessor")
            if records[predecessor]["acceptance_sequence"] >= record["acceptance_sequence"]:
                _fail("ordering_violation", "correction precedes its target")

    expected = _object(document.get("expected"), "expected")
    _keys(
        expected,
        {
            "normalized_record_ids",
            "resolution",
            "positions",
            "settled_cash",
            "open_settlement_obligations",
            "operation_trace",
        },
        "expected",
    )
    normalized = _strings(expected["normalized_record_ids"], "expected.normalized_record_ids", nonempty=True)
    if normalized != list(records):
        _fail("lineage_reference_missing", "normalized record order must retain every raw record")
    resolution = _object(expected["resolution"], "expected.resolution")
    _keys(
        resolution,
        {"economic_event_id", "record_ids", "active_record_id", "source_record_ids"},
        "expected.resolution",
    )
    chain = _strings(resolution["record_ids"], "expected.resolution.record_ids", nonempty=True)
    active = _identifier(resolution.get("active_record_id"), "expected.resolution.active_record_id")
    if any(record not in records for record in chain) or active not in records or active != chain[-1]:
        _fail("lineage_reference_missing", "resolved lifecycle chain is incomplete")
    if chain != list(records):
        _fail("lineage_reference_missing", "resolved lifecycle chain must retain every raw record")
    economic_ids = {records[record]["economic_event_id"] for record in chain}
    if economic_ids != {resolution.get("economic_event_id")}:
        _fail("lineage_reference_missing", "resolved lifecycle economic identity is inconsistent")
    expected_sources = {
        source for record in chain for source in records[record]["source_record_ids"]
    }
    if set(_strings(resolution["source_record_ids"], "expected.resolution.source_record_ids", nonempty=True)) != expected_sources:
        _fail("lineage_reference_missing", "resolved lifecycle source lineage is incomplete")
    positions = _objects(expected["positions"], "expected.positions", nonempty=True)
    for index, item in enumerate(positions):
        context = f"expected.positions[{index}]"
        _keys(
            item,
            {"account", "instrument", "quantity", "source_event_ids"},
            context,
        )
        _string(item, "account", context)
        _string(item, "instrument", context)
        _decimal(item.get("quantity"), f"{context}.quantity", 8)
        event_ids = _strings(
            item.get("source_event_ids"), f"{context}.source_event_ids", nonempty=True
        )
        if any(event_id not in economic_ids for event_id in event_ids):
            _fail("lineage_reference_missing", f"{context} references an unknown economic event")

    settled_cash = _objects(expected["settled_cash"], "expected.settled_cash")
    for index, item in enumerate(settled_cash):
        context = f"expected.settled_cash[{index}]"
        _keys(item, {"account", "currency", "amount", "source_event_ids"}, context)
        _string(item, "account", context)
        if not isinstance(item.get("currency"), str) or CURRENCY.fullmatch(item["currency"]) is None:
            _fail("schema_shape", f"{context}.currency is invalid")
        _decimal(item.get("amount"), f"{context}.amount", 6)
        event_ids = _strings(
            item.get("source_event_ids"), f"{context}.source_event_ids", nonempty=True
        )
        if any(event_id not in economic_ids for event_id in event_ids):
            _fail("lineage_reference_missing", f"{context} references an unknown economic event")

    obligations = _objects(
        expected["open_settlement_obligations"],
        "expected.open_settlement_obligations",
        nonempty=True,
    )
    for index, item in enumerate(obligations):
        context = f"expected.open_settlement_obligations[{index}]"
        _keys(
            item,
            {
                "account",
                "settlement_date",
                "currency",
                "direction",
                "amount",
                "source_event_ids",
            },
            context,
        )
        _string(item, "account", context)
        _date(item.get("settlement_date"), f"{context}.settlement_date")
        if not isinstance(item.get("currency"), str) or CURRENCY.fullmatch(item["currency"]) is None:
            _fail("schema_shape", f"{context}.currency is invalid")
        if item.get("direction") not in {"payable", "receivable"}:
            _fail("schema_shape", f"{context}.direction is invalid")
        _decimal(item.get("amount"), f"{context}.amount", 6)
        event_ids = _strings(
            item.get("source_event_ids"), f"{context}.source_event_ids", nonempty=True
        )
        if any(event_id not in economic_ids for event_id in event_ids):
            _fail("lineage_reference_missing", f"{context} references an unknown economic event")

    if _trace(expected["operation_trace"], operations, "expected.operation_trace") != set(
        operations
    ):
        _fail("lineage_reference_missing", "expected operation trace is incomplete")
    arithmetic = _arithmetic_assertions(document)
    if _decimal(positions[0]["quantity"], "expected.positions[0].quantity", 8) != arithmetic.get(
        "corrected-position"
    ):
        _fail("arithmetic_mismatch", "expected position differs from its arithmetic assertion")
    if _decimal(
        obligations[0]["amount"],
        "expected.open_settlement_obligations[0].amount",
        6,
    ) != arithmetic.get("corrected-trade-gross"):
        _fail("arithmetic_mismatch", "expected obligation differs from its arithmetic assertion")

    counterexample = _object(document.get("ordering_counterexample"), "ordering_counterexample")
    _keys(
        counterexample,
        {"operation_id", "valid_order", "permuted_order", "expected_category", "reason"},
        "ordering_counterexample",
    )
    operation_id = _identifier(counterexample.get("operation_id"), "ordering_counterexample.operation_id")
    if operation_id not in operations or operations[operation_id]["classification"] != "ordered_fold":
        _fail("lineage_reference_missing", "ordering counterexample must reference an ordered fold")
    valid_order = _strings(counterexample["valid_order"], "ordering_counterexample.valid_order", nonempty=True)
    permuted = _strings(counterexample["permuted_order"], "ordering_counterexample.permuted_order", nonempty=True)
    if valid_order != list(records) or set(permuted) != set(records):
        _fail("lineage_reference_missing", "ordering counterexample must use the fixture records")
    if [records[item]["acceptance_sequence"] for item in permuted] == sorted(sequences):
        _fail("ordering_metadata", "ordering counterexample does not reorder the records")
    if counterexample.get("expected_category") != "ordering_violation":
        _fail("expected_category_mismatch", "ordering counterexample category is not stable")
    _string(counterexample, "reason", "ordering_counterexample")
    if operations[operation_id]["laws"]["commutativity"] != "counterexample":
        _fail("law_declaration", "ordered fold must declare the commutativity counterexample")

    cases = _objects(document.get("invalidation_cases"), "invalidation_cases", nonempty=True)
    triggers: set[str] = set()
    for index, case in enumerate(cases):
        context = f"invalidation_cases[{index}]"
        _keys(
            case,
            {
                "id",
                "trigger",
                "changed_fields",
                "before",
                "after",
                "affected_operations",
                "affected_partition_keys",
                "prior_result_reuse",
                "required_action",
                "reason",
            },
            context,
        )
        _identifier(case.get("id"), f"{context}.id")
        trigger = case.get("trigger")
        if trigger not in {"late_lifecycle_record", "policy_version_change", "evaluation_context_change"}:
            _fail("schema_shape", f"{context}.trigger is unsupported")
        triggers.add(trigger)
        _strings(case.get("changed_fields"), f"{context}.changed_fields", nonempty=True)
        if _string(case, "before", context) == _string(case, "after", context):
            _fail("invalidation_policy", f"{context} before and after identities must differ")
        affected = _strings(case.get("affected_operations"), f"{context}.affected_operations", nonempty=True)
        if any(operation not in operations for operation in affected):
            _fail("lineage_reference_missing", f"{context} references an unknown operation")
        _strings(case.get("affected_partition_keys"), f"{context}.affected_partition_keys", nonempty=True)
        if case.get("prior_result_reuse") != "rejected":
            _fail("invalidation_policy", f"{context} must reject stale deterministic results")
        if case.get("required_action") not in {
            "resolve_and_recompute_affected_partitions",
            "recompute_operation_and_downstream",
            "reevaluate_settlement_dependent_operations",
        }:
            _fail("invalidation_policy", f"{context}.required_action is unsupported")
        _string(case, "reason", context)
    if triggers != {"late_lifecycle_record", "policy_version_change", "evaluation_context_change"}:
        _fail("invalidation_policy", "lifecycle, policy, and context changes must all be covered")


def _validate_comparison_fixture(
    document: dict[str, Any], operations: dict[str, dict[str, Any]]
) -> None:
    _keys(
        document,
        {
            "contract_version",
            "fixture_id",
            "fixture_kind",
            "operations",
            "evidence_ids",
            "inputs",
            "expected",
            "arithmetic",
        },
        "document",
    )
    if len(operations) != 1 or next(iter(operations.values()))["classification"] != "comparison":
        _fail("schema_shape", "comparison fixture requires one comparison operation")
    evidence = set(_strings(document.get("evidence_ids"), "evidence_ids", nonempty=True))
    inputs = _object(document.get("inputs"), "inputs")
    _keys(inputs, {"projected_cash", "observations"}, "inputs")
    projected = _objects(inputs["projected_cash"], "inputs.projected_cash", nonempty=True)
    observations = _objects(inputs["observations"], "inputs.observations", nonempty=True)
    projected_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, item in enumerate(projected):
        context = f"inputs.projected_cash[{index}]"
        _keys(item, {"account", "currency", "amount", "source_event_ids", "source_record_ids"}, context)
        _string(item, "account", context)
        if not isinstance(item.get("currency"), str) or CURRENCY.fullmatch(item["currency"]) is None:
            _fail("schema_shape", f"{context}.currency is invalid")
        _decimal(item.get("amount"), f"{context}.amount", 6)
        _strings(item.get("source_event_ids"), f"{context}.source_event_ids", nonempty=True)
        sources = _strings(item.get("source_record_ids"), f"{context}.source_record_ids", nonempty=True)
        if any(source not in evidence for source in sources):
            _fail("lineage_reference_missing", f"{context} references unknown evidence")
        key = (item["account"], item["currency"])
        if key in projected_by_key:
            _fail("duplicate_identity", f"{context} repeats projected key {key!r}")
        projected_by_key[key] = item
    observed_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, item in enumerate(observations):
        context = f"inputs.observations[{index}]"
        _keys(item, {"observation_id", "account", "currency", "amount", "source_record_id"}, context)
        _identifier(item.get("observation_id"), f"{context}.observation_id")
        _string(item, "account", context)
        if not isinstance(item.get("currency"), str) or CURRENCY.fullmatch(item["currency"]) is None:
            _fail("schema_shape", f"{context}.currency is invalid")
        _decimal(item.get("amount"), f"{context}.amount", 6)
        if item.get("source_record_id") not in evidence:
            _fail("lineage_reference_missing", f"{context} references unknown evidence")
        key = (item["account"], item["currency"])
        if key in observed_by_key:
            _fail("duplicate_identity", f"{context} repeats observation key {key!r}")
        observed_by_key[key] = item

    expected = _object(document.get("expected"), "expected")
    _keys(expected, {"breaks", "operation_trace"}, "expected")
    breaks = _objects(expected["breaks"], "expected.breaks", nonempty=True)
    for index, item in enumerate(breaks):
        context = f"expected.breaks[{index}]"
        _keys(
            item,
            {
                "account",
                "currency",
                "kind",
                "expected_amount",
                "observed_amount",
                "difference",
                "projection_source_record_ids",
                "observation_source_record_id",
            },
            context,
        )
        if item.get("kind") != "amount_mismatch":
            _fail("schema_shape", f"{context}.kind is unsupported")
        expected_amount = _decimal(item.get("expected_amount"), f"{context}.expected_amount", 6)
        observed_amount = _decimal(item.get("observed_amount"), f"{context}.observed_amount", 6)
        difference = _decimal(item.get("difference"), f"{context}.difference", 6)
        if observed_amount - expected_amount != difference:
            _fail("arithmetic_mismatch", f"{context}.difference must be observed minus expected")
        key = (item.get("account"), item.get("currency"))
        if key not in projected_by_key or key not in observed_by_key:
            _fail("lineage_reference_missing", f"{context} has no matching input key")
        if expected_amount != _decimal(
            projected_by_key[key]["amount"], f"{context}.projected_input", 6
        ) or observed_amount != _decimal(
            observed_by_key[key]["amount"], f"{context}.observed_input", 6
        ):
            _fail("arithmetic_mismatch", f"{context} amounts differ from the input records")
        projection_sources = _strings(
            item.get("projection_source_record_ids"),
            f"{context}.projection_source_record_ids",
            nonempty=True,
        )
        if any(source not in evidence for source in projection_sources):
            _fail("lineage_reference_missing", f"{context} projection lineage is unknown")
        if item.get("observation_source_record_id") not in evidence:
            _fail("lineage_reference_missing", f"{context} observation lineage is unknown")
    if _trace(expected["operation_trace"], operations, "expected.operation_trace") != set(
        operations
    ):
        _fail("lineage_reference_missing", "expected operation trace is incomplete")
    arithmetic = _arithmetic_assertions(document)
    if _decimal(breaks[0]["difference"], "expected.breaks[0].difference", 6) != arithmetic.get(
        "cash-break-difference"
    ):
        _fail("arithmetic_mismatch", "expected break differs from its arithmetic assertion")


def _validate_invalid_fixture(
    document: dict[str, Any], operations: dict[str, dict[str, Any]]
) -> list[str]:
    _keys(
        document,
        {
            "contract_version",
            "fixture_id",
            "fixture_kind",
            "operations",
            "composition_cases",
            "partition_counterexamples",
        },
        "document",
    )
    categories: list[str] = []
    for index, case in enumerate(
        _objects(document.get("composition_cases"), "composition_cases", nonempty=True)
    ):
        context = f"composition_cases[{index}]"
        _keys(case, {"id", "edge", "expected_category", "reason"}, context)
        _identifier(case.get("id"), f"{context}.id")
        expected = _identifier(case.get("expected_category"), f"{context}.expected_category")
        _string(case, "reason", context)
        edge = _object(case.get("edge"), f"{context}.edge")
        try:
            _check_composition(edge, operations, f"{context}.edge")
        except ContractError as error:
            if error.category != expected:
                _fail(
                    "expected_category_mismatch",
                    f"{context} expected {expected}, received {error.category}",
                )
            declared_errors = set(operations[edge["from"]]["errors"]) | set(
                operations[edge["to"]]["errors"]
            )
            if expected not in declared_errors:
                _fail(
                    "schema_shape",
                    f"{context} expected category is absent from both operation declarations",
                )
            categories.append(error.category)
        else:
            _fail("expected_category_mismatch", f"{context} unexpectedly composed")

    for index, case in enumerate(
        _objects(
            document.get("partition_counterexamples"),
            "partition_counterexamples",
            nonempty=True,
        )
    ):
        context = f"partition_counterexamples[{index}]"
        _keys(
            case,
            {
                "id",
                "operation_id",
                "left_key",
                "right_key",
                "declared_merge_keys",
                "required_merge_keys",
                "expected_category",
                "reason",
            },
            context,
        )
        _identifier(case.get("id"), f"{context}.id")
        operation_id = _identifier(case.get("operation_id"), f"{context}.operation_id")
        if operation_id not in operations:
            _fail("lineage_reference_missing", f"{context} references an unknown operation")
        left = _object(case.get("left_key"), f"{context}.left_key")
        right = _object(case.get("right_key"), f"{context}.right_key")
        declared = _strings(case.get("declared_merge_keys"), f"{context}.declared_merge_keys", nonempty=True)
        required = _strings(case.get("required_merge_keys"), f"{context}.required_merge_keys", nonempty=True)
        if required != operations[operation_id]["partitioning"]["keys"]:
            _fail("partition_metadata", f"{context} required keys differ from the operation")
        invalid = any(key not in declared for key in required) or any(
            left.get(key) != right.get(key) for key in required if key not in declared
        )
        actual = "partition_key_mismatch" if invalid else None
        expected = case.get("expected_category")
        if actual != expected:
            _fail("expected_category_mismatch", f"{context} expected {expected}, received {actual}")
        if expected not in operations[operation_id]["errors"]:
            _fail("schema_shape", f"{context} category is absent from the operation declaration")
        _string(case, "reason", context)
        categories.append(actual)
    return categories


def validate_document(document: Any) -> list[str]:
    value = _object(document, "document")
    if value.get("contract_version") != CONTRACT_VERSION:
        _fail("schema_shape", "contract_version is unsupported")
    _identifier(value.get("fixture_id"), "fixture_id")
    operations = _operations(value)
    kind = value.get("fixture_kind")
    if kind == "reduction_law":
        _validate_reduction_fixture(value, operations)
    elif kind == "ordered_lifecycle":
        _validate_ordered_fixture(value, operations)
    elif kind == "comparison":
        _validate_comparison_fixture(value, operations)
    elif kind == "invalid_composition":
        return _validate_invalid_fixture(value, operations)
    else:
        _fail("schema_shape", "fixture_kind is unsupported")
    return []


def load_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError("json_parse", f"{path}: {error}") from error
    validate_document(document)
    return document


class TransformationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = sorted(FIXTURE_ROOT.glob("*.json"))

    def test_every_json_fixture_parses_and_validates_independently(self):
        self.assertEqual(len(self.paths), 4)
        for path in self.paths:
            with self.subTest(path=path.name):
                load_document(path)

    def test_fixture_set_covers_operations_laws_failures_and_invalidation(self):
        documents = [json.loads(path.read_text(encoding="utf-8")) for path in self.paths]
        classifications = {
            operation["classification"]
            for document in documents
            for operation in document["operations"]
        }
        self.assertEqual(
            classifications,
            {"normalization", "map", "ordered_fold", "reduction", "comparison"},
        )
        invalid = next(
            document for document in documents if document["fixture_kind"] == "invalid_composition"
        )
        categories = validate_document(invalid)
        self.assertEqual(
            set(categories),
            {
                "currency_mismatch",
                "unit_mismatch",
                "context_mismatch",
                "operation_type_mismatch",
                "unresolved_lifecycle_input",
                "partition_key_mismatch",
            },
        )
        ordered = next(
            document for document in documents if document["fixture_kind"] == "ordered_lifecycle"
        )
        self.assertEqual(
            {case["trigger"] for case in ordered["invalidation_cases"]},
            {"late_lifecycle_record", "policy_version_change", "evaluation_context_change"},
        )

    def test_wrong_exact_arithmetic_is_rejected(self):
        document = json.loads((FIXTURE_ROOT / "valid-exact-cash-reduction.json").read_text())
        document["arithmetic"][0]["expected"] = "800.000001"
        with self.assertRaisesRegex(ContractError, "arithmetic_mismatch"):
            validate_document(document)

    def test_missing_lineage_reference_is_rejected(self):
        document = json.loads((FIXTURE_ROOT / "valid-equity-lifecycle-fold.json").read_text())
        document["records"][1]["source_record_ids"] = ["unknown-source"]
        with self.assertRaisesRegex(ContractError, "lineage_reference_missing"):
            validate_document(document)

    def test_incompatible_declared_valid_edge_is_rejected(self):
        document = json.loads((FIXTURE_ROOT / "valid-equity-lifecycle-fold.json").read_text())
        document["operations"][1]["input_ports"][0]["type"] = "OtherRecordSet"
        with self.assertRaisesRegex(ContractError, "declared_compatibility"):
            validate_document(document)

    def test_ordering_and_partition_metadata_are_enforced(self):
        document = json.loads((FIXTURE_ROOT / "valid-equity-lifecycle-fold.json").read_text())
        document["operations"][1]["ordering"]["keys"] = []
        with self.assertRaisesRegex(ContractError, "ordering_metadata"):
            validate_document(document)
        document = json.loads((FIXTURE_ROOT / "valid-exact-cash-reduction.json").read_text())
        document["execution_modes"]["partitioned"]["partitions"][1]["value_ids"].append(
            "cash-delta-1"
        )
        document["execution_modes"]["partitioned"]["partitions"][1][
            "expected_amount"
        ] = "1050.000000"
        with self.assertRaisesRegex(ContractError, "partition_metadata"):
            validate_document(document)

    def test_stable_invalid_category_cannot_be_relabelled(self):
        document = json.loads((FIXTURE_ROOT / "invalid-compositions.json").read_text())
        document["composition_cases"][0]["expected_category"] = "unit_mismatch"
        with self.assertRaisesRegex(ContractError, "expected_category_mismatch"):
            validate_document(document)

    def test_fixture_identifiers_are_checked(self):
        document = json.loads((FIXTURE_ROOT / "valid-cash-reconciliation.json").read_text())
        document["fixture_id"] = "Not Stable"
        with self.assertRaisesRegex(ContractError, "invalid_identifier"):
            validate_document(document)


if __name__ == "__main__":
    unittest.main()
