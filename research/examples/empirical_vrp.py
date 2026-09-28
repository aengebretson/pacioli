"""Bounded retrospective SPX direct-VRP calibration and pricing illustration.

This example reads coordinator-supplied files and writes one machine-readable
artifact.  It performs no acquisition, order submission, or live-data access.
The default dates are predeclared so the held-out 2023 segment cannot affect
the physical fit, and the exact-date 2024-01-03 VIX join cannot see later rows.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from luca_research.vrp import (
    ArtifactMetadata,
    CalibrationConfig,
    EuropeanOptionInputs,
    MonteCarloPricingConfig,
    PhysicalEstimationConfig,
    VixDailyClose,
    build_empirical_artifact,
    calibrate_vix_term_structure,
    estimate_physical_dynamics,
    filter_physical_returns,
    join_vix_closes_at_cutoff,
    price_european_options_monte_carlo,
    summarize_filter_segment,
)


FIT_FIRST_RETURN_DATE = "2019-12-03"
FIT_LAST_RETURN_DATE = "2022-12-30"
HOLDOUT_FIRST_RETURN_DATE = "2023-01-03"
HOLDOUT_LAST_RETURN_DATE = "2023-12-29"
CUTOFF_DATE = "2024-01-03"
CUTOFF_UTC = "2024-01-03T21:15:00Z"
STATE_AS_OF_UTC = "2024-01-03T21:00:00Z"
RETROSPECTIVE_AVAILABILITY_UTC = "2026-09-28T16:15:33.291006Z"

VIX_FILES = {
    "VIX9D": "VIX9D_History.csv",
    "VIX": "VIX_History.csv",
    "VIX3M": "VIX3M_History.csv",
    "VIX6M": "VIX6M_History.csv",
    "VIX1Y": "VIX1Y_History.csv",
}
VIX_URLS = {
    label: f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{filename}"
    for label, filename in VIX_FILES.items()
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_spx_closes(path: Path) -> list[dict[str, str | float]]:
    rows: list[dict[str, str | float]] = []
    with path.open(newline="", encoding="utf-8") as source:
        for raw in csv.reader(source):
            if len(raw) != 6:
                raise ValueError("daily/index.csv contains a row with an unexpected shape")
            dataset_id, instrument_id, observation_date, close, source_id, row_hash = raw
            if instrument_id != "spx-index":
                continue
            parsed_date = date.fromisoformat(observation_date)
            if parsed_date < date.fromisoformat("2019-12-02") or parsed_date > date.fromisoformat(
                CUTOFF_DATE
            ):
                continue
            value = float(close)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("SPX closes must be positive and finite")
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "date": observation_date,
                    "close": value,
                    "source_id": source_id,
                    "row_hash": row_hash,
                }
            )
    rows.sort(key=lambda item: str(item["date"]))
    dates = [str(item["date"]) for item in rows]
    if len(rows) < 500 or len(set(dates)) != len(dates):
        raise ValueError("SPX close extract is too short or contains duplicate dates")
    if dates[-1] != CUTOFF_DATE:
        raise ValueError("SPX close extract has no exact cutoff-date close")
    return rows


def _read_vix_cutoff_close(
    path: Path,
    *,
    label: str,
    source_sha256: str,
) -> tuple[VixDailyClose, ...]:
    matches: list[VixDailyClose] = []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]:
            raise ValueError(f"{path.name} has unexpected columns")
        for row in reader:
            parsed = date.fromisoformat(
                f"{row['DATE'][6:10]}-{row['DATE'][0:2]}-{row['DATE'][3:5]}"
            )
            if parsed.isoformat() != CUTOFF_DATE:
                continue
            matches.append(
                VixDailyClose(
                    label=label,
                    observation_date=parsed.isoformat(),
                    close_percent=float(row["CLOSE"]),
                    source_sha256=source_sha256,
                    source_url=VIX_URLS[label],
                )
            )
    return tuple(matches)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fit-particles", type=int, default=96)
    parser.add_argument("--fit-max-evaluations", type=int, default=1_000)
    parser.add_argument("--state-particles", type=int, default=512)
    parser.add_argument("--pricing-paths", type=int, default=80_000)
    return parser


def main() -> int:
    args = _argument_parser().parse_args()
    reference_dir = args.reference_dir.resolve()
    output_path = args.output.resolve()
    index_path = reference_dir / "daily" / "index.csv"
    manifest_path = reference_dir / "daily" / "manifest.json"
    calendar_path = reference_dir / "spx-calendar.json"
    vix_manifest_path = reference_dir / "vix" / "manifest.json"

    raw_hashes = {
        "daily/index.csv": _sha256(index_path),
        "daily/manifest.json": _sha256(manifest_path),
        "spx-calendar.json": _sha256(calendar_path),
        "vix/manifest.json": _sha256(vix_manifest_path),
    }
    vix_paths = {
        label: reference_dir / "vix" / filename
        for label, filename in VIX_FILES.items()
    }
    for label, path in vix_paths.items():
        raw_hashes[f"vix/{path.name}"] = _sha256(path)
    vix_manifest = json.loads(vix_manifest_path.read_text(encoding="utf-8"))
    declared_vix_hashes = {
        str(item["symbol"]): str(item["sha256"])
        for item in vix_manifest.get("files", [])
        if item.get("status") == "downloaded"
    }
    for label, path in vix_paths.items():
        actual = raw_hashes[f"vix/{path.name}"]
        if declared_vix_hashes.get(label) != actual:
            raise ValueError(f"{path.name} does not match the supplied VIX manifest")

    closes = _read_spx_closes(index_path)
    close_dates = [str(item["date"]) for item in closes]
    close_values = [float(item["close"]) for item in closes]
    return_dates = close_dates[1:]
    returns = [
        math.log(current) - math.log(previous)
        for previous, current in zip(close_values[:-1], close_values[1:], strict=True)
    ]
    return_identity_records = [
        {
            "previous_date": str(previous["date"]),
            "previous_row_hash": str(previous["row_hash"]),
            "return_date": str(current["date"]),
            "return_row_hash": str(current["row_hash"]),
        }
        for previous, current in zip(closes[:-1], closes[1:], strict=True)
    ]
    fit_indexes = [
        index
        for index, item_date in enumerate(return_dates)
        if FIT_FIRST_RETURN_DATE <= item_date <= FIT_LAST_RETURN_DATE
    ]
    if fit_indexes != list(range(fit_indexes[0], fit_indexes[-1] + 1)):
        raise ValueError("physical fit return slice is not contiguous")
    fit_returns = returns[fit_indexes[0] : fit_indexes[-1] + 1]

    physical_estimation = estimate_physical_dynamics(
        fit_returns,
        risk_free_log_rates=0.0,
        config=PhysicalEstimationConfig(
            particle_count=args.fit_particles,
            seed=17,
            max_evaluations=args.fit_max_evaluations,
            tolerance=1.0e-5,
        ),
    )
    cutoff_filter = filter_physical_returns(
        returns,
        physical_estimation.physical,
        lambda1=physical_estimation.lambda1,
        risk_free_log_rates=0.0,
        particle_count=args.state_particles,
        seed=29,
    )
    heldout_indexes = [
        index
        for index, item_date in enumerate(return_dates)
        if HOLDOUT_FIRST_RETURN_DATE <= item_date <= HOLDOUT_LAST_RETURN_DATE
    ]
    heldout_diagnostics = summarize_filter_segment(
        cutoff_filter,
        returns,
        start_index=heldout_indexes[0],
        end_index_exclusive=heldout_indexes[-1] + 1,
    )

    histories: dict[str, tuple[VixDailyClose, ...]] = {}
    for label, path in vix_paths.items():
        histories[label] = _read_vix_cutoff_close(
            path,
            label=label,
            source_sha256=raw_hashes[f"vix/{path.name}"],
        )
    vix_join = join_vix_closes_at_cutoff(
        histories,
        cutoff_date=CUTOFF_DATE,
        information_cutoff_utc=CUTOFF_UTC,
        assumed_close_time=(
            "21:15Z (4:15 p.m. ET) based on the documented VIX RTH calculation "
            "window; the supplied daily files contain no close timestamp"
        ),
    )
    if len(vix_join.observations) < 2:
        raise ValueError("fewer than two exact-cutoff VIX terms are available")

    physical = physical_estimation.physical
    gamma1_star = physical.gamma1 + physical_estimation.lambda1 + 0.5
    fixed_persistence = physical.beta + physical.alpha * gamma1_star**2
    remaining = 1.0 - 1.0e-8 - fixed_persistence
    if remaining <= 0.0:
        raise ValueError("fitted return-risk terms leave no stationary Q branch")
    maximum_gamma2_star = math.sqrt(remaining / physical.rho)
    lambda2_lower = -physical.gamma2
    lambda2_upper = -physical.gamma2 + maximum_gamma2_star
    pricing_calibration = calibrate_vix_term_structure(
        physical,
        fixed_lambda1=physical_estimation.lambda1,
        h_next=cutoff_filter.h_next_mean,
        observations=vix_join.observations,
        report_horizon_trading_days=21,
        config=CalibrationConfig(
            lambda2_lower=lambda2_lower,
            lambda2_upper=lambda2_upper,
            lambda2_initial=(lambda2_lower + lambda2_upper) / 2.0,
            max_evaluations=300,
            tolerance=1.0e-10,
        ),
    )

    spot_close = close_values[-1]
    illustrative_strike = round(spot_close / 5.0) * 5.0
    option_inputs = EuropeanOptionInputs(
        contract_id="illustrative-SPXW-2024-02-02-ATM-straddle",
        forward=spot_close,
        strike=illustrative_strike,
        discount_factor=1.0,
        horizon_trading_days=21,
        settlement="cash",
        contract_multiplier=100.0,
    )
    first_pricing_count = max(2_000, args.pricing_paths // 4)
    if first_pricing_count % 2:
        first_pricing_count += 1
    if args.pricing_paths % 2 or first_pricing_count >= args.pricing_paths:
        raise ValueError("pricing-paths must be an even integer greater than 2,000")
    option_pricing = price_european_options_monte_carlo(
        physical,
        pricing_calibration.calibrated_risk_prices,
        h_next=cutoff_filter.h_next_mean,
        inputs=option_inputs,
        config=MonteCarloPricingConfig(
            path_counts=(first_pricing_count, args.pricing_paths),
            seed=101,
        ),
    )

    dataset_identity = {
        "classification": "retrospective_exploratory_daily_research",
        "historical_cutoff": CUTOFF_UTC,
        "raw_file_sha256": raw_hashes,
        "fit_first_return_date": FIT_FIRST_RETURN_DATE,
        "fit_last_return_date": FIT_LAST_RETURN_DATE,
        "heldout_first_return_date": HOLDOUT_FIRST_RETURN_DATE,
        "heldout_last_return_date": HOLDOUT_LAST_RETURN_DATE,
    }
    metadata = ArtifactMetadata(
        run_id="direct-vrp-spx-2024-01-03-exploratory-v1",
        dataset_id="spx-vix-daily-cutoff-2024-01-03-v1",
        dataset_sha256=_canonical_sha256(dataset_identity),
        dataset_classification="exploratory_historical",
        input_cutoff_utc=CUTOFF_UTC,
        availability_time_utc=RETROSPECTIVE_AVAILABILITY_UTC,
        state_as_of_utc=STATE_AS_OF_UTC,
        state_availability_time_utc=RETROSPECTIVE_AVAILABILITY_UTC,
    )
    input_provenance = [
        {
            "logical_path": logical_path,
            "sha256": digest,
            "preserved_outside_git": True,
            "source": (
                "Cboe official daily history"
                if logical_path.startswith("vix/")
                else "coordinator-supplied SPX research archive"
            ),
        }
        for logical_path, digest in sorted(raw_hashes.items())
    ]
    artifact = build_empirical_artifact(
        metadata,
        physical_estimation,
        cutoff_filter,
        pricing_calibration,
        vix_join,
        option_pricing,
        sample_boundaries={
            "physical_fit": {
                "first_return_date": FIT_FIRST_RETURN_DATE,
                "last_return_date": FIT_LAST_RETURN_DATE,
                "observation_count": len(fit_returns),
                "parameters_frozen_after": FIT_LAST_RETURN_DATE,
                "risk_free_log_rate_per_trading_day": 0.0,
                "rate_classification": "assumed_zero_no_historical_curve_supplied",
                "input_identity_sha256": _canonical_sha256(
                    return_identity_records[fit_indexes[0] : fit_indexes[-1] + 1]
                ),
            },
            "heldout_physical_diagnostics": {
                "first_return_date": HOLDOUT_FIRST_RETURN_DATE,
                "last_return_date": HOLDOUT_LAST_RETURN_DATE,
                "observation_count": len(heldout_indexes),
                "overlaps_physical_fit": False,
                "input_identity_sha256": _canonical_sha256(
                    return_identity_records[
                        heldout_indexes[0] : heldout_indexes[-1] + 1
                    ]
                ),
            },
            "state_filter": {
                "first_return_date": return_dates[0],
                "last_return_date": return_dates[-1],
                "parameters_refit_after_physical_fit": False,
                "risk_free_log_rate_per_trading_day": 0.0,
                "rate_classification": "assumed_zero_no_historical_curve_supplied",
                "input_identity_sha256": _canonical_sha256(return_identity_records),
            },
            "pricing_surface": {
                "observation_date": CUTOFF_DATE,
                "exact_date_join": True,
                "future_rows_used": False,
            },
        },
        heldout_diagnostics=heldout_diagnostics,
        input_provenance=input_provenance,
        contract_and_market_inputs={
            "underlying_spot": {
                "value": spot_close,
                "classification": "actual_archived_SPX_daily_close",
                "date": CUTOFF_DATE,
                "row_hash": closes[-1]["row_hash"],
            },
            "forward": {
                "value": spot_close,
                "classification": "assumed_equal_to_spot_not_observed_forward",
            },
            "discount_factor": {
                "value": 1.0,
                "classification": "assumed_zero_rate_no_curve_supplied",
            },
            "strike": {
                "value": illustrative_strike,
                "classification": "assumed_nearest_5_point_ATM_strike",
            },
            "expiration": {
                "value": "2024-02-02T21:00:00Z",
                "classification": "calendar_rule_candidate_not_verified_listing",
                "trading_day_horizon": 21,
                "calendar_day_horizon": 30,
            },
            "contract_multiplier": {
                "value": 100.0,
                "classification": "assumed_standard_SPX_multiplier_not_joined_to_contract_master",
            },
            "option_print": None,
            "event_time_quote": None,
        },
        extra_limitations=(
            "The supplied option inventory contains no verified 2024-02-02 listing, so expiry, strike, and multiplier are illustrative assumptions.",
            "The actual SPX close is not an observed forward; zero carry and a unit discount factor are assumptions made only for the pricing illustration.",
            "No same-time option quote or print is supplied, so the result cannot label a buy or sell opportunity.",
        ),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if artifact["status"] == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
