"""Translate validated JSON conformance fixtures into a tiny C++ test artifact."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from harness import discover_scenarios


TIMESTAMP = re.compile(
    r"^(?P<seconds>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]+))?(?P<timezone>Z|[+-][0-9]{2}:[0-9]{2})$"
)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _timestamp(value: str) -> str:
    match = TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid ISO 8601 fixture timestamp: {value!r}")
    fraction = match.group("fraction") or ""
    if len(fraction) > 9:
        raise ValueError(
            f"fixture timestamp precision exceeds nanoseconds: {value!r}"
        )

    zone = "+00:00" if match.group("timezone") == "Z" else match.group("timezone")
    parsed = datetime.fromisoformat(match.group("seconds") + zone)
    delta = parsed.astimezone(timezone.utc) - EPOCH
    nanoseconds = (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + int(fraction.ljust(9, "0") or "0")
    )
    return str(nanoseconds)


def _date(value: str) -> str:
    return value.replace("-", "\t")


def generate(root: Path) -> str:
    lines = ["LUCA_CONFORMANCE_V1"]
    for scenario in discover_scenarios(root):
        definition = scenario.definition
        name = definition["name"]
        lines.append(f"SCENARIO\t{name}")
        for value in definition["initial_state"]["positions"]:
            lines.append("\t".join(("INITIAL_POSITION", value["account"], value["instrument"], value["quantity"])))
        for value in definition["initial_state"]["cash"]:
            lines.append("\t".join(("INITIAL_CASH", value["account"], value["currency"], value["amount"])))
        for index, value in enumerate(definition["inputs"]):
            if value["type"] == "cash_deposit":
                fields = ("CASH", str(index), value["account"], value["currency"], value["amount"], _timestamp(value["effective_at"]))
            else:
                fields = ("TRADE", str(index), value["account"], value["side"], value["instrument"], value["quantity"], value["currency"], value["price"], _timestamp(value["trade_at"]), *_date(value["settlement_date"]).split("\t"))
            lines.append("\t".join(fields))

        latest_event = max(
            _timestamp(value.get("effective_at", value.get("trade_at")))
            for value in definition["inputs"]
        )
        for phase, expected in scenario.expected.items():
            anchor_document = expected["positions"]
            if "as_of" in anchor_document:
                economic_as_of = _timestamp(anchor_document["as_of"])
                settlement_date = datetime.fromisoformat(anchor_document["as_of"].replace("Z", "+00:00")).date().isoformat()
            else:
                economic_as_of = latest_event
                settlement_date = anchor_document["as_of_date"]
            lines.append("\t".join(("PHASE", phase, economic_as_of, *_date(settlement_date).split("\t"))))
            for value in expected["positions"]["positions"]:
                lines.append("\t".join(("POSITION", value["account"], value["instrument"], value["quantity"])))
            for value in expected["cash"]["cash"]:
                lines.append("\t".join(("BALANCE", value["account"], value["currency"], value["amount"])))
            for value in expected["settlements"]["settlements"]:
                lines.append("\t".join(("SETTLEMENT", value["account"], value["currency"], value["amount"], value["direction"], *_date(value["settlement_date"]).split("\t"))))
            lines.append("END_PHASE")
        lines.append("END_SCENARIO")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(generate(arguments.root), encoding="utf-8")
