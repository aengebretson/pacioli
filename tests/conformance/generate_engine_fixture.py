"""Translate validated JSON conformance fixtures into a tiny C++ test artifact."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from harness import discover_scenarios


def _timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return str(int(parsed.timestamp() * 1_000_000_000))


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
