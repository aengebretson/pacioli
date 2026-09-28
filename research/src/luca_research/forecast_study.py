"""Bounded, reproducible comparison of expiration-aligned variance forecasts.

The study deliberately separates its date-only predeclaration from parsing or
using close values. Callers first build and persist a plan from the saved
calendar and the set of available dates, and only then pass the close rows to
``run_forecast_study``.  The numerical work reuses ``run_expiry_forecast``;
there is no second implementation of the rolling, EWMA, or GARCH estimators.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
import math
import re
from typing import Any, Mapping, Sequence

from .contracts import HARD_MAX_OBSERVATIONS, canonical_sha256, parse_close_input
from .estimators import qlike, squared_variance_error
from .expiration_calendar import ExpirationCalendar
from .expiry_forecast import MODEL_NAMES, REQUEST_SCHEMA, run_expiry_forecast


PLAN_SCHEMA = "luca.expiry-forecast-study-plan.v1"
RESULT_SCHEMA = "luca.expiry-forecast-study-result.v1"
APP_SCHEMA = "luca.spx-research-display.v1"
STUDY_ID = "spx-expiry-forecast-study-2023-2025-v1"
MAX_ORIGINS = 60
MODEL_CONFIGURATION = {
    "fitting_window_returns": 252,
    "minimum_fit_returns": 252,
    "mean": "zero",
    "ewma_decay": 0.94,
    "calendar_days_per_year": 365.2425,
    "garch_max_iterations": 500,
    "optimizer_tolerance": 1e-8,
    "refit_policy": "fit_once_at_information_cutoff",
    "selected_model": "rolling",
    "selection_basis": (
        "Predeclared rolling baseline with EWMA and GARCH(1,1) challengers; "
        "no selection or parameter change uses an outcome in this study."
    ),
}
BOUNDARY_RULE = {
    "omega_lower_tolerance_decimal_squared": 1e-12,
    "alpha_lower_tolerance": 1e-8,
    "beta_lower_tolerance": 1e-8,
    "persistence_upper_distance": 1e-6,
}
PARTITIONS = (
    {
        "id": "exploratory_development_2023",
        "origin_start": "2023-01-01",
        "origin_end": "2023-12-31",
        "use": "retrospective model-development description",
    },
    {
        "id": "exploratory_comparison_2024",
        "origin_start": "2024-01-01",
        "origin_end": "2024-12-31",
        "use": "retrospective comparison description",
    },
    {
        "id": "exploratory_retrospective_holdout_2025",
        "origin_start": "2025-01-01",
        "origin_end": "2025-12-31",
        "use": "retrospective holdout-shaped description; not untouched evidence",
    },
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StudyCloseRow:
    """One source-index row retained with its upstream provenance."""

    dataset_id: str
    instrument_id: str
    date: date
    close: float
    source_id: str
    row_hash: str


def _plan_hash(document: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in document.items() if key != "sha256"})


def _iso_date(value: str, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD")
    return parsed


def _identity(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field} must be a non-empty mapping")
    return dict(value)


def _partition_for(origin: date) -> str:
    for partition in PARTITIONS:
        if _iso_date(partition["origin_start"], "partition start") <= origin <= _iso_date(
            partition["origin_end"], "partition end"
        ):
            return str(partition["id"])
    raise ValueError(f"origin {origin.isoformat()} is outside the predeclared partitions")


def parse_study_close_rows(raw_rows: Sequence[Mapping[str, Any]]) -> tuple[StudyCloseRow, ...]:
    """Validate already-decoded source rows without changing their values."""

    if not 1 <= len(raw_rows) <= HARD_MAX_OBSERVATIONS:
        raise ValueError(f"close row count must be in 1..{HARD_MAX_OBSERVATIONS}")
    parsed: list[StudyCloseRow] = []
    previous: date | None = None
    dataset_id: str | None = None
    instrument_id: str | None = None
    for index, raw in enumerate(raw_rows):
        expected = {"dataset_id", "instrument_id", "date", "close", "source_id", "row_hash"}
        if set(raw) != expected:
            raise ValueError(f"close row {index} must contain exactly {sorted(expected)}")
        observed = _iso_date(raw["date"], f"close row {index} date")
        if previous is not None and observed <= previous:
            raise ValueError("close rows must have unique, strictly increasing dates")
        previous = observed
        close = raw["close"]
        if isinstance(close, bool) or not isinstance(close, (int, float)):
            raise ValueError(f"close row {index} close must be numeric")
        close = float(close)
        if not math.isfinite(close) or close <= 0.0:
            raise ValueError(f"close row {index} close must be positive and finite")
        for name in ("dataset_id", "instrument_id"):
            if not isinstance(raw[name], str) or not raw[name]:
                raise ValueError(f"close row {index} {name} must be non-empty")
        dataset_id = dataset_id or str(raw["dataset_id"])
        instrument_id = instrument_id or str(raw["instrument_id"])
        if raw["dataset_id"] != dataset_id or raw["instrument_id"] != instrument_id:
            raise ValueError("the bounded study accepts one dataset and one instrument")
        for name in ("source_id", "row_hash"):
            if not isinstance(raw[name], str) or not _HASH_RE.fullmatch(raw[name]):
                raise ValueError(f"close row {index} {name} must be a lowercase SHA-256")
        parsed.append(
            StudyCloseRow(
                dataset_id=dataset_id,
                instrument_id=instrument_id,
                date=observed,
                close=close,
                source_id=str(raw["source_id"]),
                row_hash=str(raw["row_hash"]),
            )
        )
    return tuple(parsed)


def _nearest_expiration(calendar: ExpirationCalendar, cutoff: date) -> dict[str, Any]:
    target = cutoff + timedelta(days=30)
    left = target - timedelta(days=7)
    right = target + timedelta(days=7)
    candidates = calendar.expirations(left.isoformat(), right.isoformat(), root="SPXW")
    pm_candidates = [item for item in candidates if item["settlement"] == "PM"]
    if not pm_candidates:
        raise ValueError(f"no PM expiration candidate is near {target.isoformat()}")
    return min(
        pm_candidates,
        key=lambda item: (abs((_iso_date(item["date"], "expiration date") - target).days), item["date"]),
    )


def _overlap_records(origins: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    for left_index, left in enumerate(origins):
        left_dates = set(left["interval"]["interval_end_dates"])
        for right in origins[left_index + 1 :]:
            common = sorted(left_dates.intersection(right["interval"]["interval_end_dates"]))
            if common:
                overlaps.append(
                    {
                        "left_origin_id": left["origin_id"],
                        "right_origin_id": right["origin_id"],
                        "shared_return_endpoint_count": len(common),
                        "first_shared_endpoint": common[0],
                        "last_shared_endpoint": common[-1],
                    }
                )
    return overlaps


def build_study_plan(
    available_dates: Sequence[str],
    calendar_document: Mapping[str, Any],
    *,
    source_identity: Mapping[str, Any],
    calendar_file_sha256: str,
    code_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Predeclare the bounded study using dates only, before close outcomes load."""

    if not _HASH_RE.fullmatch(calendar_file_sha256):
        raise ValueError("calendar_file_sha256 must be a lowercase SHA-256")
    parsed_dates = tuple(_iso_date(value, "available date") for value in available_dates)
    if not parsed_dates or list(parsed_dates) != sorted(set(parsed_dates)):
        raise ValueError("available dates must be unique and strictly increasing")
    available = set(parsed_dates)
    calendar = ExpirationCalendar(dict(calendar_document))
    reference = calendar.reference()
    coverage = reference["coverage"]
    sessions = calendar.sessions(coverage["start"], "2026-02-15")
    session_dates = [_iso_date(item["date"], "calendar session date") for item in sessions]

    origins: list[dict[str, Any]] = []
    for year in range(2023, 2026):
        for month in range(1, 13):
            in_month = [item for item in session_dates if item.year == year and item.month == month]
            if not in_month:
                raise ValueError(f"calendar has no cash session in {year:04d}-{month:02d}")
            cutoff = in_month[0]
            expiration = _nearest_expiration(calendar, cutoff)
            interval = calendar.forecast_interval(
                cutoff.isoformat(), expiration["expiration_id"], allow_rule_candidate=True
            )
            cutoff_position = session_dates.index(cutoff)
            expected_fit_dates = session_dates[max(0, cutoff_position - 252) : cutoff_position + 1]
            missing_fit = [item.isoformat() for item in expected_fit_dates if item not in available]
            interval_dates = [_iso_date(item, "forecast endpoint") for item in interval["interval_end_dates"]]
            missing_outcome = [item.isoformat() for item in interval_dates if item not in available]
            exclusions: list[dict[str, Any]] = []
            if len(expected_fit_dates) != 253:
                exclusions.append(
                    {
                        "reason": "insufficient_calendar_fit_sessions",
                        "message": f"calendar supplied {len(expected_fit_dates)} of 253 required closes",
                    }
                )
            if cutoff not in available or missing_fit:
                exclusions.append(
                    {
                        "reason": "missing_fit_close",
                        "message": f"{len(missing_fit)} expected fit-session closes are unavailable",
                        "dates": missing_fit,
                    }
                )
            if missing_outcome:
                exclusions.append(
                    {
                        "reason": "missing_outcome_close",
                        "message": f"{len(missing_outcome)} expected outcome closes are unavailable",
                        "dates": missing_outcome,
                    }
                )
            origins.append(
                {
                    "origin_id": f"spx-{cutoff.isoformat()}-{expiration['date']}",
                    "partition": _partition_for(cutoff),
                    "cutoff": cutoff.isoformat(),
                    "target_calendar_days": 30,
                    "expiration_target": (cutoff + timedelta(days=30)).isoformat(),
                    "expiration": dict(expiration),
                    "actual_calendar_days": (
                        _iso_date(expiration["date"], "expiration date") - cutoff
                    ).days,
                    "interval": interval,
                    "fit_partition": {
                        "boundary": "all observations are at or before cutoff",
                        "expected_close_count": 253,
                        "expected_return_count": 252,
                        "first_date": expected_fit_dates[0].isoformat(),
                        "last_date": expected_fit_dates[-1].isoformat(),
                        "dates": [item.isoformat() for item in expected_fit_dates],
                    },
                    "outcome_partition": {
                        "boundary": "strictly after cutoff through PM expiration close",
                        "expected_close_count": len(interval_dates),
                        "first_date": interval_dates[0].isoformat(),
                        "last_date": interval_dates[-1].isoformat(),
                        "dates": [item.isoformat() for item in interval_dates],
                    },
                    "precheck_exclusions": exclusions,
                }
            )
    if len(origins) > MAX_ORIGINS:
        raise ValueError(f"predeclared origin count exceeds the hard study cap of {MAX_ORIGINS}")
    overlaps = _overlap_records(origins)
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "study_id": STUDY_ID,
        "research_use": "exploratory_retrospective_previously_inspected",
        "status": "predeclared",
        "predeclaration_sequence": (
            "calendar and source-date availability define this plan; persist this document "
            "before parsing close fields or calculating outcome scores"
        ),
        "origin_rule": {
            "coverage": {"start": "2023-01-01", "end": "2025-12-31"},
            "frequency": "monthly",
            "cutoff": "first cash-session close of each calendar month",
            "expiration": (
                "nearest stored SPXW PM rule candidate to cutoff plus 30 calendar days; "
                "ties choose the earlier candidate"
            ),
            "maximum_origins": MAX_ORIGINS,
            "predeclared_origin_count": len(origins),
        },
        "partitions": [dict(item) for item in PARTITIONS],
        "model_configuration": dict(MODEL_CONFIGURATION),
        "scoring": {
            "forecast_quantity": "sum of h=1..H conditional variances",
            "realized_quantity": "sum of squared close-to-close decimal log returns over identical endpoints",
            "primary_units": "decimal_log_return_squared_over_the_expiration_horizon",
            "qlike": "log(forecast_cumulative_variance) + realized_cumulative_variance / forecast_cumulative_variance",
            "signed_variance_error": "forecast_cumulative_variance - realized_cumulative_variance",
            "absolute_variance_error": "abs(signed_variance_error)",
            "squared_variance_error": "signed_variance_error ** 2",
            "common_origin_rule": "include an origin only when all three predeclared models are scored",
            "garch_boundary_rule": dict(BOUNDARY_RULE),
            "inference": "descriptive only; no standard errors, p-values, or significance claims",
        },
        "dependence": {
            "overlap_definition": "two labels share one or more daily-return endpoints",
            "overlapping_pair_count": len(overlaps),
            "overlapping_pairs": overlaps,
            "treatment": "retain and identify overlap; do not treat origin losses as independent",
        },
        "identities": {
            "source_index": _identity(source_identity, "source_identity"),
            "calendar": {**reference, "file_sha256": calendar_file_sha256},
            "code": _identity(code_identity, "code_identity"),
        },
        "origins": origins,
        "limitations": [
            "All underlying historical data had already been inspected; no partition is genuinely untouched evidence.",
            "Calendar expiration rows are rule candidates and do not prove an SPXW contract was historically listed.",
            "The cash-session calendar is not a historical announcement-vintage calendar.",
            "Daily closes do not establish intraday quote availability, tradeability, option fair value, or hedged P&L.",
            "Overlapping expiration labels make losses dependent; this study performs no significance inference.",
        ],
    }
    plan["sha256"] = _plan_hash(plan)
    return plan


def _row_payload(row: StudyCloseRow) -> dict[str, Any]:
    return {
        "dataset_id": row.dataset_id,
        "instrument_id": row.instrument_id,
        "date": row.date.isoformat(),
        "close": row.close,
        "source_id": row.source_id,
        "row_hash": row.row_hash,
    }


def _partition_payload(rows: Sequence[StudyCloseRow], *, boundary: str) -> dict[str, Any]:
    observations = [_row_payload(row) for row in rows]
    return {
        "boundary": boundary,
        "row_count": len(rows),
        "first_date": rows[0].date.isoformat(),
        "last_date": rows[-1].date.isoformat(),
        "sha256": canonical_sha256(observations),
        "observations": observations,
    }


def _normalized_input(rows: Sequence[StudyCloseRow], origin_id: str) -> tuple[dict[str, Any], str]:
    document = {
        "schema_version": "luca.normalized-close.v1",
        "input_id": f"{origin_id}-fit252",
        "close_unit": "index_points",
        "observations": [
            {"date": row.date.isoformat(), "close": row.close} for row in rows
        ],
    }
    parsed = parse_close_input(document, max_observations=HARD_MAX_OBSERVATIONS)
    return document, parsed.sha256


def _realized_outcome(
    cutoff_row: StudyCloseRow, outcome_rows: Sequence[StudyCloseRow], calendar_days: int
) -> dict[str, Any]:
    previous = cutoff_row
    returns: list[dict[str, Any]] = []
    for current in outcome_rows:
        value = math.log(current.close) - math.log(previous.close)
        squared = value * value
        returns.append(
            {
                "start_date_exclusive": previous.date.isoformat(),
                "end_date_inclusive": current.date.isoformat(),
                "log_return_decimal": value,
                "squared_log_return_decimal_squared": squared,
            }
        )
        previous = current
    cumulative = math.fsum(item["squared_log_return_decimal_squared"] for item in returns)
    year_fraction = calendar_days / MODEL_CONFIGURATION["calendar_days_per_year"]
    annualized = cumulative / year_fraction
    return {
        "availability_to_forecast_fit": False,
        "return_definition": "close_to_close_decimal_log_return",
        "period_returns": returns,
        "cumulative_realized_variance_decimal_squared": cumulative,
        "annualization": {
            "calendar_days": calendar_days,
            "calendar_days_per_year": MODEL_CONFIGURATION["calendar_days_per_year"],
            "calendar_year_fraction": year_fraction,
            "annualized_variance": annualized,
            "annualized_volatility": math.sqrt(annualized),
        },
    }


def _garch_boundary(model: Mapping[str, Any]) -> dict[str, Any]:
    parameters = model["parameters"]["decimal_return_units"]
    omega = float(parameters["omega"])
    alpha = float(parameters["alpha[1]"])
    beta = float(parameters["beta[1]"])
    persistence = alpha + beta
    flags = {
        "omega_near_lower_boundary": omega <= BOUNDARY_RULE["omega_lower_tolerance_decimal_squared"],
        "alpha_near_lower_boundary": alpha <= BOUNDARY_RULE["alpha_lower_tolerance"],
        "beta_near_lower_boundary": beta <= BOUNDARY_RULE["beta_lower_tolerance"],
        "persistence_near_upper_boundary": persistence
        >= 1.0 - BOUNDARY_RULE["persistence_upper_distance"],
    }
    return {
        "rule": dict(BOUNDARY_RULE),
        "estimates": {"omega": omega, "alpha": alpha, "beta": beta, "alpha_plus_beta": persistence},
        "flags": flags,
        "near_boundary": any(flags.values()),
    }


def _score_models(forecast: Mapping[str, Any], realized: Mapping[str, Any]) -> dict[str, Any]:
    realized_variance = float(realized["cumulative_realized_variance_decimal_squared"])
    scores: dict[str, Any] = {}
    for name in MODEL_NAMES:
        model = forecast.get("models", {}).get(name)
        if not model or model.get("status") != "complete":
            exclusion = model.get("exclusion") if isinstance(model, Mapping) else None
            scores[name] = {
                "status": "excluded",
                "reason": "forecast_model_excluded",
                "detail": exclusion,
            }
            continue
        predicted = float(model["forecast"]["W_P_decimal_squared"])
        error = predicted - realized_variance
        score: dict[str, Any] = {
            "status": "scored",
            "units": "decimal_log_return_squared_over_the_expiration_horizon",
            "forecast_cumulative_variance": predicted,
            "realized_cumulative_variance": realized_variance,
            "signed_variance_error": error,
            "absolute_variance_error": abs(error),
            "squared_variance_error": squared_variance_error(predicted, realized_variance),
            "qlike": qlike(predicted, realized_variance),
            "convergence": model["fit"]["convergence"],
            "boundary_estimate": None,
        }
        if name == "garch_1_1":
            score["boundary_estimate"] = _garch_boundary(model)
        scores[name] = score
    return scores


def _aggregate(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {
            "origin_count": 0,
            "mean_forecast_cumulative_variance": None,
            "mean_realized_cumulative_variance": None,
            "mean_signed_variance_error": None,
            "mean_absolute_variance_error": None,
            "mean_squared_variance_error": None,
            "mean_qlike": None,
        }
    count = len(scores)
    mean = lambda field: math.fsum(float(item[field]) for item in scores) / count
    return {
        "origin_count": count,
        "mean_forecast_cumulative_variance": mean("forecast_cumulative_variance"),
        "mean_realized_cumulative_variance": mean("realized_cumulative_variance"),
        "mean_signed_variance_error": mean("signed_variance_error"),
        "mean_absolute_variance_error": mean("absolute_variance_error"),
        "mean_squared_variance_error": mean("squared_variance_error"),
        "mean_qlike": mean("qlike"),
    }


def _comparison_summary(origin_results: Sequence[Mapping[str, Any]], plan: Mapping[str, Any]) -> dict[str, Any]:
    common_ids = [
        item["origin_id"]
        for item in origin_results
        if all(item.get("scores", {}).get(name, {}).get("status") == "scored" for name in MODEL_NAMES)
    ]
    common_set = set(common_ids)
    models: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    for name in MODEL_NAMES:
        available = [
            item["scores"][name]
            for item in origin_results
            if item.get("scores", {}).get(name, {}).get("status") == "scored"
        ]
        common = [
            item["scores"][name]
            for item in origin_results
            if item["origin_id"] in common_set
        ]
        models[name] = {
            "all_available_origins": _aggregate(available),
            "common_origins": _aggregate(common),
        }
        failures.extend(
            {
                "origin_id": item["origin_id"],
                "model": name,
                "exclusion": item.get("scores", {}).get(name),
            }
            for item in origin_results
            if item.get("scores", {}).get(name, {}).get("status") != "scored"
        )

    by_partition: dict[str, Any] = {}
    for partition in PARTITIONS:
        partition_results = [
            item for item in origin_results if item["partition"] == partition["id"]
        ]
        partition_common = [
            item for item in partition_results if item["origin_id"] in common_set
        ]
        by_partition[partition["id"]] = {
            "planned_origin_count": len(partition_results),
            "common_origin_count": len(partition_common),
            "models": {
                name: _aggregate([item["scores"][name] for item in partition_common])
                for name in MODEL_NAMES
            },
        }

    garch_scored = [
        item for item in origin_results if item.get("scores", {}).get("garch_1_1", {}).get("status") == "scored"
    ]
    boundary_counts: Counter[str] = Counter()
    boundary_origins: list[str] = []
    for item in garch_scored:
        boundary = item["scores"]["garch_1_1"]["boundary_estimate"]
        for name, flagged in boundary["flags"].items():
            if flagged:
                boundary_counts[name] += 1
        if boundary["near_boundary"]:
            boundary_origins.append(item["origin_id"])
    common_metrics = {
        name: models[name]["common_origins"]["mean_qlike"] for name in MODEL_NAMES
    }
    finite_leaders = {name: value for name, value in common_metrics.items() if value is not None}
    qlike_leader = min(finite_leaders, key=finite_leaders.get) if finite_leaders else None
    return {
        "planned_origin_count": len(plan["origins"]),
        "terminal_origin_count": len(origin_results),
        "common_origin_count": len(common_ids),
        "common_origin_ids": common_ids,
        "model_comparison": models,
        "by_partition": by_partition,
        "fit_failures": failures,
        "garch_diagnostics": {
            "converged_and_scored_count": len(garch_scored),
            "excluded_count": len(origin_results) - len(garch_scored),
            "near_boundary_origin_count": len(boundary_origins),
            "near_boundary_origin_ids": boundary_origins,
            "boundary_flag_counts": dict(sorted(boundary_counts.items())),
        },
        "dependence": dict(plan["dependence"]),
        "descriptive_lowest_common_mean_qlike_model": qlike_leader,
        "interpretation": (
            "All metrics are descriptive. Common-origin tables exclude an origin from every model "
            "when any model fails, while all failures remain listed. Overlap precludes independent-loss inference."
        ),
    }


def run_forecast_study(
    plan: Mapping[str, Any],
    close_rows: Sequence[StudyCloseRow],
    *,
    input_available_at: str,
) -> dict[str, Any]:
    """Execute a persisted plan with cutoff-only fitting and separate outcomes."""

    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("sha256") != _plan_hash(plan):
        raise ValueError("study plan schema or content hash is invalid")
    if len(plan.get("origins", ())) > MAX_ORIGINS:
        raise ValueError("study plan exceeds the origin cap")
    rows = tuple(close_rows)
    if not rows:
        raise ValueError("close_rows cannot be empty")
    source_identity = plan["identities"]["source_index"]
    if (
        len(rows) != source_identity.get("row_count")
        or rows[0].date.isoformat() != source_identity.get("first_date")
        or rows[-1].date.isoformat() != source_identity.get("last_date")
        or rows[0].dataset_id != source_identity.get("dataset_id")
        or rows[0].instrument_id != source_identity.get("instrument_id")
        or any(
            row.dataset_id != rows[0].dataset_id or row.instrument_id != rows[0].instrument_id
            for row in rows
        )
    ):
        raise ValueError("close_rows do not match the predeclared source identity")
    row_by_date = {row.date.isoformat(): row for row in rows}
    if len(row_by_date) != len(rows):
        raise ValueError("close_rows contain duplicate dates")

    origin_results: list[dict[str, Any]] = []
    for origin in plan["origins"]:
        result: dict[str, Any] = {
            "origin_id": origin["origin_id"],
            "partition": origin["partition"],
            "cutoff": origin["cutoff"],
            "expiration": origin["expiration"]["date"],
            "status": "excluded",
            "identities": {
                "predeclaration_sha256": plan["sha256"],
                "source_index_file_sha256": plan["identities"]["source_index"].get("file_sha256"),
                "calendar_content_sha256": plan["identities"]["calendar"]["sha256"],
                "calendar_file_sha256": plan["identities"]["calendar"]["file_sha256"],
                "code": plan["identities"]["code"],
            },
            "precheck_exclusions": list(origin["precheck_exclusions"]),
            "fit_input": None,
            "outcome_input": None,
            "forecast": None,
            "realized_outcome": None,
            "scores": {
                name: {"status": "excluded", "reason": "origin_precheck_excluded"}
                for name in MODEL_NAMES
            },
        }
        if origin["precheck_exclusions"]:
            origin_results.append(result)
            continue
        fit_rows = [row_by_date[value] for value in origin["fit_partition"]["dates"]]
        outcome_rows = [row_by_date[value] for value in origin["outcome_partition"]["dates"]]
        fit_document, fit_sha256 = _normalized_input(fit_rows, origin["origin_id"])
        request = {
            "schema_version": REQUEST_SCHEMA,
            "run_id": origin["origin_id"],
            "research_use": "exploratory_historical",
            "input": {
                "input_id": fit_document["input_id"],
                "sha256": fit_sha256,
                "available_at": input_available_at,
            },
            "interval": origin["interval"],
            "model": dict(MODEL_CONFIGURATION),
        }
        forecast = run_expiry_forecast(request, fit_document)
        fit_partition = _partition_payload(
            fit_rows, boundary="cutoff-truncated closes supplied to every model"
        )
        fit_partition["normalized_input_id"] = fit_document["input_id"]
        fit_partition["normalized_input_sha256"] = fit_sha256
        outcome_partition = _partition_payload(
            outcome_rows,
            boundary="future close numbers parsed after the predeclaration and never supplied to fitting",
        )
        realized = _realized_outcome(
            fit_rows[-1], outcome_rows, int(origin["actual_calendar_days"])
        )
        scores = _score_models(forecast, realized)
        scored_count = sum(item["status"] == "scored" for item in scores.values())
        result.update(
            {
                "status": "complete" if scored_count == len(MODEL_NAMES) else "partial",
                "fit_input": fit_partition,
                "outcome_input": outcome_partition,
                "forecast": forecast,
                "realized_outcome": realized,
                "scores": scores,
                "separation_checks": {
                    "fit_last_date_equals_cutoff": fit_rows[-1].date.isoformat() == origin["cutoff"],
                    "all_outcome_dates_after_cutoff": all(
                        row.date > fit_rows[-1].date for row in outcome_rows
                    ),
                    "forecast_post_cutoff_observations_ignored": forecast.get("inputs", [{}])[0].get(
                        "post_cutoff_observation_count_ignored"
                    )
                    if forecast.get("inputs")
                    else None,
                    "identical_fit_identity_across_models": len(
                        {
                            model["fit"]["eligible_history_sha256"]
                            for model in forecast.get("models", {}).values()
                            if model.get("fit")
                        }
                    )
                    == 1,
                },
            }
        )
        origin_results.append(result)

    summary = _comparison_summary(origin_results, plan)
    result_document: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "study_id": plan["study_id"],
        "research_use": plan["research_use"],
        "status": "complete",
        "predeclaration_sha256": plan["sha256"],
        "predeclaration": dict(plan),
        "comparison_summary": summary,
        "origin_results": origin_results,
        "next_design_recommendation": {
            "basis": {
                "common_origin_count": summary["common_origin_count"],
                "descriptive_lowest_mean_qlike_model": summary[
                    "descriptive_lowest_common_mean_qlike_model"
                ],
                "garch_excluded_count": summary["garch_diagnostics"]["excluded_count"],
                "garch_near_boundary_origin_count": summary["garch_diagnostics"][
                    "near_boundary_origin_count"
                ],
                "overlapping_pair_count": summary["dependence"]["overlapping_pair_count"],
            },
            "recommendation": (
                "Freeze this specification and any model choice made from these descriptive results. "
                "Evaluate it on subsequently unavailable dates with versioned market-data vintages and "
                "qualified historical listings. Predeclare either non-overlapping expirations or a "
                "dependence-aware inference method; do not retune this inspected 2023-2025 sample."
            ),
        },
        "limitations": list(plan["limitations"]),
    }
    result_document["sha256"] = canonical_sha256(result_document)
    return result_document


def build_app_document(result: Mapping[str, Any]) -> dict[str, Any]:
    """Create the existing viewer's runs shape plus a study comparison summary."""

    plan = result["predeclaration"]
    origin_plan = {item["origin_id"]: item for item in plan["origins"]}
    runs: list[dict[str, Any]] = []
    for item in result["origin_results"]:
        planned = origin_plan[item["origin_id"]]
        model_summaries: dict[str, Any] = {}
        for name in MODEL_NAMES:
            score = item["scores"][name]
            model = item["forecast"]["models"][name] if item["forecast"] else None
            if score["status"] != "scored" or not model:
                model_summaries[name] = {
                    "status": "excluded",
                    "exclusion": score,
                }
                continue
            cumulative = score["forecast_cumulative_variance"]
            model_summaries[name] = {
                "status": "scored",
                "cumulative_variance": cumulative,
                "annualized_volatility_percent": model["forecast"]["annualization"][
                    "annualized_volatility"
                ]
                * 100.0,
                "horizon_standard_deviation_percent": math.sqrt(cumulative) * 100.0,
                "realized_cumulative_variance": score["realized_cumulative_variance"],
                "qlike": score["qlike"],
                "signed_variance_error": score["signed_variance_error"],
                "squared_variance_error": score["squared_variance_error"],
                "convergence": score["convergence"],
                "boundary_estimate": score["boundary_estimate"],
            }
        realized = item["realized_outcome"]
        runs.append(
            {
                "id": item["origin_id"],
                "label": f"{item['cutoff']} to {item['expiration']} · exploratory historical",
                "partition": item["partition"],
                "summary": {
                    "status": item["status"],
                    "cutoff": item["cutoff"],
                    "expiration": item["expiration"],
                    "sessions": len(planned["interval"]["interval_end_dates"]),
                    "calendar_days": planned["actual_calendar_days"],
                    "models": model_summaries,
                    "subsequent_realized": {
                        "cumulative_squared_daily_log_returns": realized[
                            "cumulative_realized_variance_decimal_squared"
                        ]
                        if realized
                        else None,
                        "annualized_volatility_percent": realized["annualization"][
                            "annualized_volatility"
                        ]
                        * 100.0
                        if realized
                        else None,
                        "note": "Outcome loaded after forecast input was cutoff-truncated; exploratory, previously inspected history.",
                    },
                },
                "provenance": {
                    "study_result_sha256": result["sha256"],
                    "predeclaration_sha256": result["predeclaration_sha256"],
                    "source_index": plan["identities"]["source_index"],
                    "code": plan["identities"]["code"],
                    "fit_input_sha256": item["fit_input"]["sha256"] if item["fit_input"] else None,
                    "outcome_input_sha256": item["outcome_input"]["sha256"]
                    if item["outcome_input"]
                    else None,
                    "historical_vintage_availability_verified": False,
                },
                "calendar": plan["identities"]["calendar"],
                "expiration": planned["expiration"],
                "forecast": item["forecast"],
                "limitations": list(plan["limitations"]),
            }
        )
    return {
        "schema_version": APP_SCHEMA,
        "title": "SPX Expiry Forecast Study · Exploratory 2023–2025",
        "study": {
            "id": result["study_id"],
            "research_use": result["research_use"],
            "result_sha256": result["sha256"],
            "comparison_summary": result["comparison_summary"],
            "next_design_recommendation": result["next_design_recommendation"],
            "limitations": result["limitations"],
        },
        "runs": runs,
    }


def render_report(result: Mapping[str, Any]) -> str:
    """Render a compact Markdown handoff report from the machine result."""

    summary = result["comparison_summary"]
    plan = result["predeclaration"]
    lines = [
        "# SPX expiration-forecast study",
        "",
        "> Exploratory retrospective research on previously inspected history. This is not genuinely untouched performance evidence.",
        "",
        "## Predeclared design",
        "",
        f"- Study: `{result['study_id']}`",
        f"- Predeclaration SHA-256: `{result['predeclaration_sha256']}`",
        f"- Origins: {summary['planned_origin_count']} monthly cutoffs from 2023 through 2025 (cap {MAX_ORIGINS})",
        "- Origin: first cash-session close each month; endpoint: nearest stored SPXW PM rule candidate to +30 calendar days",
        "- Shared fit: trailing 252 decimal log returns, zero mean, fixed cutoff, identical horizon and input identity",
        "- Models: rolling variance, EWMA(0.94), and pinned `arch` normal GARCH(1,1)",
        "- Scores: cumulative horizon variance QLIKE, signed/absolute/squared variance error",
        "",
        "The date-only predeclaration was persisted before close fields were parsed or outcome scores were calculated. Each result retains a 253-close cutoff-truncated fit partition and a separate future outcome partition.",
        "",
        "## Common-origin model comparison",
        "",
        "| Model | Common origins | Mean QLIKE | Mean signed error | Mean absolute error | Mean squared error |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in MODEL_NAMES:
        metrics = summary["model_comparison"][name]["common_origins"]
        value = lambda field: "n/a" if metrics[field] is None else f"{metrics[field]:.10g}"
        lines.append(
            f"| {name} | {metrics['origin_count']} | {value('mean_qlike')} | "
            f"{value('mean_signed_variance_error')} | {value('mean_absolute_variance_error')} | "
            f"{value('mean_squared_variance_error')} |"
        )
    lines.extend(
        [
            "",
            f"The descriptively lowest common-origin mean QLIKE model is `{summary['descriptive_lowest_common_mean_qlike_model']}`. This is a ranking of this inspected sample, not a significance or profitability claim.",
            "",
            "## Partitions",
            "",
            "| Partition | Planned origins | Common origins |",
            "|---|---:|---:|",
        ]
    )
    for partition in PARTITIONS:
        item = summary["by_partition"][partition["id"]]
        lines.append(
            f"| {partition['id']} | {item['planned_origin_count']} | {item['common_origin_count']} |"
        )
    diagnostics = summary["garch_diagnostics"]
    lines.extend(
        [
            "",
            "## Diagnostics and dependence",
            "",
            f"- Retained fit/model exclusions: {len(summary['fit_failures'])}",
            f"- GARCH converged and scored: {diagnostics['converged_and_scored_count']}; excluded: {diagnostics['excluded_count']}",
            f"- GARCH near-boundary origins under the predeclared rule: {diagnostics['near_boundary_origin_count']}",
            f"- Overlapping origin pairs: {summary['dependence']['overlapping_pair_count']}",
            "- Overlapping labels are retained and identified; no independent-window standard errors, p-values, or significance tests are reported.",
            "",
            "## Next design",
            "",
            result["next_design_recommendation"]["recommendation"],
            "",
            "## Identities",
            "",
            f"- Source index file SHA-256: `{plan['identities']['source_index'].get('file_sha256')}`",
            f"- Calendar content SHA-256: `{plan['identities']['calendar']['sha256']}`",
            f"- Calendar file SHA-256: `{plan['identities']['calendar']['file_sha256']}`",
            f"- Result SHA-256: `{result['sha256']}`",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in result["limitations"])
    lines.extend(["", "No option fair value, VRP, actionable signal, trade, order, or hedged P&L is produced by this study.", ""])
    return "\n".join(lines)


__all__ = [
    "APP_SCHEMA",
    "MAX_ORIGINS",
    "PLAN_SCHEMA",
    "RESULT_SCHEMA",
    "STUDY_ID",
    "StudyCloseRow",
    "build_app_document",
    "build_study_plan",
    "parse_study_close_rows",
    "render_report",
    "run_forecast_study",
]
