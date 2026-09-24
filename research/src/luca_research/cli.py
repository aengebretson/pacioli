"""Offline CLI host for the pure volatility analysis API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .contracts import Diagnostic
from .pipeline import failure_artifact, run_analysis


def _load_json(path: Path, field: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read {field} JSON from {path}: {exc}") from exc


def _write_json(path: str, artifact: Any) -> None:
    serialized = json.dumps(artifact, allow_nan=False, indent=2, sort_keys=True) + "\n"
    if path == "-":
        sys.stdout.write(serialized)
    else:
        Path(path).write_text(serialized, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="luca-volatility",
        description="Run offline historical, EWMA, and GARCH(1,1) variance evaluation.",
    )
    parser.add_argument("--request", required=True, type=Path, help="luca.volatility-request.v1 JSON")
    parser.add_argument("--input", required=True, type=Path, help="luca.normalized-close.v1 JSON")
    parser.add_argument("--output", default="-", help="result JSON path, or - for stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = _load_json(args.request, "request")
        input_document = _load_json(args.input, "input")
        artifact = run_analysis(request, input_document)
    except ValueError as exc:
        artifact = failure_artifact([Diagnostic("cli_input_error", str(exc), "cli")])
    _write_json(args.output, artifact)
    return {"complete": 0, "partial": 3, "failed": 2}[artifact["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
