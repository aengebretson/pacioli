"""Loader and structural validator for implementation-neutral LUCA fixtures."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


class FixtureError(ValueError):
    """A fixture is absent, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Scenario:
    path: Path
    definition: dict[str, Any]
    expected: dict[str, dict[str, dict[str, Any]]]


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureError(f"{path}: cannot load JSON: {error}") from error
    if not isinstance(value, dict):
        raise FixtureError(f"{path}: top level must be an object")
    return value


def _required_string(record: dict[str, Any], field: str, context: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise FixtureError(f"{context}: {field} must be a non-empty string")
    return value


def _decimal(record: dict[str, Any], field: str, context: str) -> None:
    value = _required_string(record, field, context)
    if not DECIMAL.fullmatch(value):
        raise FixtureError(f"{context}: {field} must be a decimal string")


def _currency(record: dict[str, Any], context: str) -> None:
    if not CURRENCY.fullmatch(_required_string(record, "currency", context)):
        raise FixtureError(f"{context}: currency must be a three-character uppercase code")


def _records(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise FixtureError(f"{context} must be an array of objects")
    return value


def _validate_position(record: dict[str, Any], context: str) -> None:
    _required_string(record, "account", context)
    _required_string(record, "instrument", context)
    _decimal(record, "quantity", context)


def _validate_cash(record: dict[str, Any], context: str) -> None:
    _required_string(record, "account", context)
    _currency(record, context)
    _decimal(record, "amount", context)


def _validate_settlement(record: dict[str, Any], context: str) -> None:
    _required_string(record, "account", context)
    _currency(record, context)
    _decimal(record, "amount", context)
    if record.get("direction") not in ("payable", "receivable"):
        raise FixtureError(f"{context}: direction must be payable or receivable")
    if not DATE.fullmatch(_required_string(record, "settlement_date", context)):
        raise FixtureError(f"{context}: settlement_date must be an ISO 8601 date")


VALIDATORS = {
    "positions": _validate_position,
    "cash": _validate_cash,
    "settlements": _validate_settlement,
}


def _validate_state(document: dict[str, Any], kind: str, context: str) -> None:
    if set(document) != {"as_of", kind}:
        raise FixtureError(f"{context}: expected exactly as_of and {kind}")
    if not TIMESTAMP.fullmatch(_required_string(document, "as_of", context)):
        raise FixtureError(f"{context}: as_of must be an ISO 8601 timestamp with timezone")
    for index, record in enumerate(_records(document[kind], f"{context}.{kind}")):
        VALIDATORS[kind](record, f"{context}.{kind}[{index}]")


def _validate_definition(definition: dict[str, Any], directory: Path) -> None:
    name = _required_string(definition, "name", str(directory / "scenario.json"))
    if name != directory.name:
        raise FixtureError(f"{directory}: scenario name must match directory name")
    _required_string(definition, "description", name)
    initial = definition.get("initial_state")
    if not isinstance(initial, dict) or set(initial) != {"positions", "cash", "settlements"}:
        raise FixtureError(f"{name}: initial_state must contain positions, cash, and settlements")
    for kind, validator in VALIDATORS.items():
        for index, record in enumerate(_records(initial[kind], f"{name}.initial_state.{kind}")):
            validator(record, f"{name}.initial_state.{kind}[{index}]")

    for index, event in enumerate(_records(definition.get("inputs"), f"{name}.inputs")):
        context = f"{name}.inputs[{index}]"
        event_type = event.get("type")
        _required_string(event, "account", context)
        if event_type == "cash_deposit":
            _currency(event, context)
            _decimal(event, "amount", context)
            timestamp_field = "effective_at"
        elif event_type == "equity_trade":
            if event.get("side") not in ("buy", "sell"):
                raise FixtureError(f"{context}: side must be buy or sell")
            _required_string(event, "instrument", context)
            _decimal(event, "quantity", context)
            _currency(event, context)
            _decimal(event, "price", context)
            if not DATE.fullmatch(_required_string(event, "settlement_date", context)):
                raise FixtureError(f"{context}: settlement_date must be an ISO 8601 date")
            timestamp_field = "trade_at"
        else:
            raise FixtureError(f"{context}: unsupported input type {event_type!r}")
        if not TIMESTAMP.fullmatch(_required_string(event, timestamp_field, context)):
            raise FixtureError(f"{context}: {timestamp_field} must be an ISO 8601 timestamp with timezone")

    projections = definition.get("expected_projections")
    if not isinstance(projections, dict) or not projections:
        raise FixtureError(f"{name}: expected_projections must be a non-empty object")
    for phase, files in projections.items():
        if not isinstance(phase, str) or not phase or not isinstance(files, dict):
            raise FixtureError(f"{name}: projection phase names and file maps are required")
        if set(files) != set(VALIDATORS):
            raise FixtureError(f"{name}.{phase}: must reference positions, cash, and settlements")
        if any(not isinstance(filename, str) or Path(filename).name != filename for filename in files.values()):
            raise FixtureError(f"{name}.{phase}: expected files must be local filenames")


def load_scenario(directory: Path) -> Scenario:
    definition = _read_object(directory / "scenario.json")
    _validate_definition(definition, directory)
    expected: dict[str, dict[str, dict[str, Any]]] = {}
    for phase, files in definition["expected_projections"].items():
        expected[phase] = {}
        for kind, filename in files.items():
            document = _read_object(directory / filename)
            _validate_state(document, kind, str(directory / filename))
            expected[phase][kind] = document
    return Scenario(directory, definition, expected)


def discover_scenarios(root: Path | None = None) -> list[Scenario]:
    root = root or Path(__file__).parent
    directories = sorted(path for path in root.iterdir() if path.is_dir() and (path / "scenario.json").exists())
    scenarios = [load_scenario(path) for path in directories]
    names = [scenario.definition["name"] for scenario in scenarios]
    if len(names) != len(set(names)):
        raise FixtureError("scenario names must be unique")
    if not scenarios:
        raise FixtureError(f"{root}: no conformance scenarios found")
    return scenarios
