#!/usr/bin/env python3
"""Bounded illustrative expiry-variance calculation using the Q1 fixture."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

from luca_research.contracts import HARD_MAX_OBSERVATIONS, parse_close_input
from luca_research.expiry_forecast import REQUEST_SCHEMA, run_expiry_forecast


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = RESEARCH_ROOT / "fixtures" / "synthetic_spx_like.json"


def _request(input_id: str, input_sha256: str) -> dict[str, Any]:
    # This schedule is declared independently of the fixture's post-cutoff
    # values. It is illustrative and is not an exchange-calendar certification.
    interval_end_dates = [
        "2024-07-17",
        "2024-07-18",
        "2024-07-19",
        "2024-07-22",
        "2024-07-23",
        "2024-07-24",
        "2024-07-25",
        "2024-07-26",
        "2024-07-29",
        "2024-07-30",
        "2024-07-31",
        "2024-08-01",
        "2024-08-02",
        "2024-08-05",
        "2024-08-06",
        "2024-08-07",
        "2024-08-08",
        "2024-08-09",
        "2024-08-12",
        "2024-08-13",
        "2024-08-14",
    ]
    return {
        "schema_version": REQUEST_SCHEMA,
        "run_id": "illustrative-expiry-forecast-v1",
        "research_use": "illustrative_fixture",
        "input": {
            "input_id": input_id,
            "sha256": input_sha256,
            "available_at": "2024-09-03T21:00:00Z",
        },
        "interval": {
            "cutoff": "2024-07-16",
            "expiration": "2024-08-14",
            "interval_end_dates": interval_end_dates,
            "boundary_precision": "daily_close",
            "calendar": {
                "calendar_id": "illustrative-weekday-schedule",
                "version": "fixture-v1",
                "source": "illustrative fixture dates; not exchange-certified",
            },
        },
        "model": {
            "fitting_window_returns": 90,
            "minimum_fit_returns": 60,
            "mean": "zero",
            "ewma_decay": 0.94,
            "calendar_days_per_year": 365.2425,
            "garch_max_iterations": 500,
            "optimizer_tolerance": 1e-8,
            "refit_policy": "fit_once_at_information_cutoff",
            "selected_model": "garch_1_1",
            "selection_basis": (
                "predeclared for the illustrative API demonstration; "
                "not selected from this expiration outcome"
            ),
        },
    }


def _manual_checks(artifact: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for name, model in artifact.get("models", {}).items():
        if model.get("status") != "complete":
            checks[name] = {"status": "not_checked", "reason": "model_excluded"}
            continue
        forecast = model["forecast"]
        period_sum = math.fsum(
            period["conditional_variance_decimal_squared"]
            for period in forecast["period_forecasts"]
        )
        reported = forecast["W_P_decimal_squared"]
        annualization = forecast["annualization"]
        independently_annualized = (
            period_sum / annualization["calendar_year_fraction"]
        )
        checks[name] = {
            "status": "checked",
            "period_count": len(forecast["period_forecasts"]),
            "reported_W_P": reported,
            "independent_period_sum": period_sum,
            "W_P_absolute_difference": abs(reported - period_sum),
            "annualized_variance_absolute_difference": abs(
                annualization["annualized_variance"] - independently_annualized
            ),
        }
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="write the result artifact here instead of stdout",
    )
    args = parser.parse_args()

    with DEFAULT_INPUT.open("r", encoding="utf-8") as handle:
        input_document = json.load(handle)
    normalized = parse_close_input(
        input_document, max_observations=HARD_MAX_OBSERVATIONS
    )
    artifact = run_expiry_forecast(
        _request(normalized.input_id, normalized.sha256), input_document
    )
    checks = _manual_checks(artifact)

    encoded = json.dumps(artifact, allow_nan=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.write_text(encoded, encoding="utf-8")
    sys.stderr.write(
        json.dumps(
            {
                "demonstration": "illustrative_fixture_not_held_out_evidence",
                "artifact_status": artifact["status"],
                "manual_identity_checks": checks,
            },
            allow_nan=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if artifact["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
