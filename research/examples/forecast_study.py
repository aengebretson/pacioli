#!/usr/bin/env python3
"""Run the bounded 2023-2025 SPX expiration-forecast study offline."""

from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from luca_research.forecast_study import (
    build_app_document,
    build_study_plan,
    parse_study_close_rows,
    render_report,
    run_forecast_study,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CODE_PATHS = (
    "research/src/luca_research/forecast_study.py",
    "research/src/luca_research/expiry_forecast.py",
    "research/src/luca_research/estimators.py",
    "research/src/luca_research/garch.py",
    "research/examples/forecast_study.py",
)
OUTPUT_NAMES = {
    "plan": "forecast-study-predeclaration.json",
    "result": "forecast-study-result.json",
    "app": "forecast-study-app.json",
    "report": "forecast-study-report.md",
    "manifest": "forecast-study-output-manifest.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _code_identity() -> dict[str, Any]:
    return {
        "base_git_commit": _git_head(),
        "working_tree_note": (
            "The exact source-file hashes identify this uncommitted implementation-worker run; "
            "the base commit alone does not identify the study code."
        ),
        "files": [
            {"path": relative, "sha256": _sha256(REPOSITORY_ROOT / relative)}
            for relative in CODE_PATHS
        ],
    }


def _read_index_metadata(path: Path) -> tuple[list[str], dict[str, Any]]:
    """Read only identities/dates; deliberately do not parse close values."""

    available_dates: list[str] = []
    dataset_ids: set[str] = set()
    instrument_ids: set[str] = set()
    source_ids: set[str] = set()
    previous: date | None = None
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if len(row) != 6:
                raise ValueError(f"index CSV line {line_number} must have exactly six fields")
            dataset_id, instrument_id, observed_text, _unread_close, source_id, row_hash = row
            observed = date.fromisoformat(observed_text)
            if observed.isoformat() != observed_text:
                raise ValueError(f"index CSV line {line_number} has a noncanonical date")
            if previous is not None and observed <= previous:
                raise ValueError("index CSV dates must be unique and strictly increasing")
            previous = observed
            if len(source_id) != 64 or len(row_hash) != 64:
                raise ValueError(f"index CSV line {line_number} has an invalid hash length")
            int(source_id, 16)
            int(row_hash, 16)
            available_dates.append(observed_text)
            dataset_ids.add(dataset_id)
            instrument_ids.add(instrument_id)
            source_ids.add(source_id)
    if len(dataset_ids) != 1 or len(instrument_ids) != 1:
        raise ValueError("the bounded index input must contain one dataset and one instrument")
    identity = {
        "path": str(path.resolve()),
        "file_sha256": _sha256(path),
        "file_size_bytes": path.stat().st_size,
        "format": "headerless_csv:dataset_id,instrument_id,date,close,source_id,row_hash",
        "dataset_id": next(iter(dataset_ids)),
        "instrument_id": next(iter(instrument_ids)),
        "row_count": len(available_dates),
        "first_date": available_dates[0],
        "last_date": available_dates[-1],
        "source_id_set_sha256": hashlib.sha256(
            "\n".join(sorted(source_ids)).encode("ascii")
        ).hexdigest(),
        "close_values_loaded_for_predeclaration": False,
    }
    return available_dates, identity


def _read_close_rows(path: Path):
    raw_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if len(row) != 6:
                raise ValueError(f"index CSV line {line_number} must have exactly six fields")
            dataset_id, instrument_id, observed, close, source_id, row_hash = row
            try:
                close_value = float(close)
            except ValueError as exc:
                raise ValueError(f"index CSV line {line_number} close is not numeric") from exc
            raw_rows.append(
                {
                    "dataset_id": dataset_id,
                    "instrument_id": instrument_id,
                    "date": observed,
                    "close": close_value,
                    "source_id": source_id,
                    "row_hash": row_hash,
                }
            )
    return parse_study_close_rows(raw_rows)


def _manifest(output_dir: Path) -> dict[str, Any]:
    entries = []
    for role in ("plan", "result", "app", "report"):
        path = output_dir / OUTPUT_NAMES[role]
        entries.append(
            {
                "role": role,
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": "luca.expiry-forecast-study-output-manifest.v1",
        "files": entries,
        "generated_data_policy": "research outputs remain outside Git",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="headerless daily/index.csv")
    parser.add_argument("--calendar", required=True, type=Path, help="stored spx-calendar.json")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--input-available-at",
        required=True,
        help="UTC extraction-availability timestamp ending in Z; not a historical market timestamp",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    calendar_document = _json(args.calendar)

    # Phase 1 reads source identities and dates, not close values. Persisting the
    # plan here makes the declared origins, partitions, exclusions, and scoring
    # rules inspectable before any outcome score is calculated.
    available_dates, source_identity = _read_index_metadata(args.index)
    plan = build_study_plan(
        available_dates,
        calendar_document,
        source_identity=source_identity,
        calendar_file_sha256=_sha256(args.calendar),
        code_identity=_code_identity(),
    )
    plan_path = args.output_dir / OUTPUT_NAMES["plan"]
    _write_json(plan_path, plan)

    # Phase 2 parses numerical closes only after the immutable plan is on disk.
    rows = _read_close_rows(args.index)
    if _sha256(args.index) != source_identity["file_sha256"]:
        raise ValueError("index CSV changed between predeclaration and numerical loading")
    result = run_forecast_study(plan, rows, input_available_at=args.input_available_at)
    if _code_identity() != plan["identities"]["code"]:
        raise ValueError("study code changed after the predeclaration was written")
    app_document = build_app_document(result)
    report = render_report(result)

    result_path = args.output_dir / OUTPUT_NAMES["result"]
    app_path = args.output_dir / OUTPUT_NAMES["app"]
    report_path = args.output_dir / OUTPUT_NAMES["report"]
    _write_json(result_path, result)
    _write_json(app_path, app_document)
    report_path.write_text(report, encoding="utf-8")
    manifest = _manifest(args.output_dir)
    manifest_path = args.output_dir / OUTPUT_NAMES["manifest"]
    _write_json(manifest_path, manifest)

    sys.stdout.write(
        json.dumps(
            {
                "status": result["status"],
                "study_id": result["study_id"],
                "result_sha256": result["sha256"],
                "planned_origins": result["comparison_summary"]["planned_origin_count"],
                "common_origins": result["comparison_summary"]["common_origin_count"],
                "outputs": {name: str((args.output_dir / value).resolve()) for name, value in OUTPUT_NAMES.items()},
            },
            allow_nan=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
