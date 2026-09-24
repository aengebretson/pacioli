"""Callable historical/EWMA/GARCH evaluation pipeline."""

from __future__ import annotations

from datetime import date
from importlib.metadata import PackageNotFoundError, version
import math
import platform
from typing import Any, Mapping, Sequence

from . import __version__
from .contracts import (
    AnalysisRequest,
    ContractError,
    Diagnostic,
    NormalizedCloseInput,
    RESULT_SCHEMA,
    canonical_sha256,
    parse_close_input,
    parse_request,
)
from .estimators import (
    annualize_cumulative_variance,
    ewma_variance,
    flat_variance_forecast,
    historical_variance,
    qlike,
    realized_close_variance,
    squared_variance_error,
)
from .garch import GarchFitFailure, fit_garch11


MODEL_NAMES = ("historical", "ewma", "garch_1_1")
NUMERICAL_AGREEMENT_RTOL = 1e-10
NUMERICAL_AGREEMENT_ATOL = 1e-12


def _dependency_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def runtime_versions() -> dict[str, Any]:
    runtime_packages = (
        "arch",
        "formulaic",
        "interface-meta",
        "narwhals",
        "numpy",
        "packaging",
        "pandas",
        "patsy",
        "python-dateutil",
        "scipy",
        "six",
        "statsmodels",
        "typing-extensions",
        "wrapt",
    )
    return {
        "luca_research": __version__,
        "python": platform.python_version(),
        "dependencies": {
            package: _dependency_version(package) for package in runtime_packages
        },
    }


def failure_artifact(
    diagnostics: Sequence[Diagnostic],
    *,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "analysis_id": analysis_id,
        "status": "failed",
        "versions": runtime_versions(),
        "inputs": [],
        "request_sha256": None,
        "evaluation_records": [],
        "metrics": {},
        "exclusions": [],
        "fit_failures": [],
        "errors": [item.to_dict() for item in diagnostics],
        "warnings": [],
        "statistical_inference": "descriptive_only_no_naive_significance_claims",
    }


def _request_summary(request: AnalysisRequest) -> dict[str, Any]:
    boundaries = request.boundaries
    model = request.model
    return {
        "boundaries": {
            "fit_start": boundaries.fit_start.isoformat(),
            "selection_start": boundaries.selection_start.isoformat(),
            "selection_end": boundaries.selection_end.isoformat(),
            "holdout_start": boundaries.holdout_start.isoformat(),
            "holdout_end": boundaries.holdout_end.isoformat(),
        },
        "model": {
            "lookback_returns": model.lookback_returns,
            "minimum_fit_returns": model.minimum_fit_returns,
            "mean": model.mean,
            "ewma_decay": model.ewma_decay,
            "calendar_days_per_year": model.calendar_days_per_year,
            "garch": {
                "distribution": "normal",
                "max_iterations": model.garch_max_iterations,
                "optimizer_tolerance": model.optimizer_tolerance,
                "p": 1,
                "q": 1,
                "return_scale_for_fit": "percent",
                "random_seed": model.random_seed,
                "random_seed_usage": "recorded_contract_value; analytic_fit_and_forecast_use_no_random_draws",
            },
        },
        "limits": {
            "max_observations": request.limits.max_observations,
            "max_origins": request.limits.max_origins,
        },
        "host_agreement_tolerances": {
            "relative": NUMERICAL_AGREEMENT_RTOL,
            "absolute": NUMERICAL_AGREEMENT_ATOL,
            "rule": "abs(hosted-standalone) <= absolute + relative*abs(standalone)",
            "nonnumeric_fields": "exact",
        },
    }


def _input_summary(input_data: NormalizedCloseInput) -> dict[str, Any]:
    return {
        "input_id": input_data.input_id,
        "sha256": input_data.sha256,
        "schema_version": "luca.normalized-close.v1",
        "observation_count": len(input_data.observations),
        "first_date": input_data.observations[0].date.isoformat(),
        "last_date": input_data.observations[-1].date.isoformat(),
        "units": {
            "close": input_data.close_unit,
            "return": "log_decimal",
            "variance": "decimal_return_squared",
            "annualized_variance": "decimal_return_squared_per_calendar_year",
        },
    }


def _available_prefix_hash(
    input_data: NormalizedCloseInput, *, first_index: int, last_index: int
) -> str:
    return canonical_sha256(
        {
            "close_unit": input_data.close_unit,
            "input_id": input_data.input_id,
            "observations": [
                {"close": item.close, "date": item.date.isoformat()}
                for item in input_data.observations[first_index : last_index + 1]
            ],
            "schema_version": "luca.normalized-close.v1",
        }
    )


def _failure_details(exc: BaseException) -> dict[str, Any]:
    details = getattr(exc, "details", None)
    return dict(details) if isinstance(details, Mapping) else {}


def _forecast_entry(
    interval_variances: Sequence[float],
    *,
    realized_annualized: float,
    calendar_days: int,
    calendar_days_per_year: float,
    parameters: Mapping[str, Any],
    fit: Mapping[str, Any],
) -> dict[str, Any]:
    cumulative = math.fsum(interval_variances)
    annualized = annualize_cumulative_variance(
        cumulative,
        horizon_calendar_days=calendar_days,
        calendar_days_per_year=calendar_days_per_year,
    )
    return {
        "interval_variances_decimal_squared": list(interval_variances),
        "cumulative_variance_decimal_squared": cumulative,
        "annualized_variance": annualized,
        "parameters": dict(parameters),
        "fit": dict(fit),
        "losses": {
            "qlike": qlike(annualized, realized_annualized),
            "squared_variance_error": squared_variance_error(annualized, realized_annualized),
        },
    }


def _metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("all", "selection", "holdout"):
        selected = list(records) if split == "all" else [record for record in records if record["split"] == split]
        if not selected:
            continue
        model_metrics: dict[str, Any] = {}
        for model in MODEL_NAMES:
            qlikes = [record["forecasts"][model]["losses"]["qlike"] for record in selected]
            squared_errors = [record["forecasts"][model]["losses"]["squared_variance_error"] for record in selected]
            model_metrics[model] = {
                "origin_count": len(selected),
                "mean_qlike": math.fsum(qlikes) / len(qlikes),
                "mean_squared_variance_error": math.fsum(squared_errors) / len(squared_errors),
            }
        result[split] = {
            "eligible_origins": [record["origin"] for record in selected],
            "models": model_metrics,
        }
    return result


def _overlapping_windows(request: AnalysisRequest) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    ordered = sorted(request.windows, key=lambda item: (item.origin, item.endpoint))
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            if right.origin < left.endpoint and left.origin < right.endpoint:
                warnings.append(
                    {
                        "code": "overlapping_horizons_dependent",
                        "message": f"labels ({left.origin}, {left.endpoint}] and ({right.origin}, {right.endpoint}] overlap; metrics are dependent",
                    }
                )
    return warnings


def _analyze(request: AnalysisRequest, input_data: NormalizedCloseInput) -> dict[str, Any]:
    if request.input_id != input_data.input_id:
        return failure_artifact(
            [Diagnostic("input_id_mismatch", "request input_id does not match normalized input", "request.input.input_id")],
            analysis_id=request.analysis_id,
        )
    if request.input_sha256 != input_data.sha256:
        return failure_artifact(
            [Diagnostic("input_hash_mismatch", "request input hash does not match normalized input", "request.input.sha256")],
            analysis_id=request.analysis_id,
        )

    observations = input_data.observations
    dates = [item.date for item in observations]
    closes = [item.close for item in observations]
    date_indices = {value: index for index, value in enumerate(dates)}
    returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
    fit_start_index = date_indices.get(request.boundaries.fit_start)
    errors: list[Diagnostic] = []
    if fit_start_index is None:
        errors.append(Diagnostic("missing_boundary_date", "fit_start must be an observation date", "request.boundaries.fit_start"))
    for index, window in enumerate(request.windows):
        if window.origin not in date_indices:
            errors.append(Diagnostic("missing_origin_date", "origin must be an observation date", f"request.windows[{index}].origin"))
        if window.endpoint not in date_indices:
            errors.append(Diagnostic("missing_endpoint_date", "endpoint must be an observation date", f"request.windows[{index}].endpoint"))
    if errors:
        return failure_artifact(errors, analysis_id=request.analysis_id)
    assert fit_start_index is not None

    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    fit_failures: list[dict[str, Any]] = []
    for window in request.windows:
        origin_index = date_indices[window.origin]
        endpoint_index = date_indices[window.endpoint]
        earliest_index = max(fit_start_index, origin_index - request.model.lookback_returns)
        fit_returns = returns[earliest_index:origin_index]
        horizon = endpoint_index - origin_index
        if len(fit_returns) < request.model.minimum_fit_returns:
            exclusions.append(
                {
                    "origin": window.origin.isoformat(),
                    "endpoint": window.endpoint.isoformat(),
                    "reason": "insufficient_fit_returns",
                    "available": len(fit_returns),
                    "required": request.model.minimum_fit_returns,
                    "applies_to": list(MODEL_NAMES),
                }
            )
            continue
        if horizon < 1:
            exclusions.append(
                {
                    "origin": window.origin.isoformat(),
                    "endpoint": window.endpoint.isoformat(),
                    "reason": "empty_horizon",
                    "applies_to": list(MODEL_NAMES),
                }
            )
            continue
        try:
            historical_one_step, historical_mean = historical_variance(fit_returns, request.model.mean)
            ewma_one_step, ewma_mean = ewma_variance(fit_returns, request.model.ewma_decay, request.model.mean)
        except ValueError as exc:
            exclusions.append(
                {
                    "origin": window.origin.isoformat(),
                    "endpoint": window.endpoint.isoformat(),
                    "reason": "baseline_fit_failure",
                    "message": str(exc),
                    "applies_to": list(MODEL_NAMES),
                }
            )
            continue
        try:
            garch = fit_garch11(
                fit_returns,
                horizon=horizon,
                mean=request.model.mean,
                max_iterations=request.model.garch_max_iterations,
                optimizer_tolerance=request.model.optimizer_tolerance,
            )
        except (GarchFitFailure, ValueError) as exc:
            failure = {
                "origin": window.origin.isoformat(),
                "endpoint": window.endpoint.isoformat(),
                "model": "garch_1_1",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "details": _failure_details(exc),
            }
            fit_failures.append(failure)
            exclusions.append(
                {
                    "origin": window.origin.isoformat(),
                    "endpoint": window.endpoint.isoformat(),
                    "reason": "garch_fit_failure",
                    "applies_to": list(MODEL_NAMES),
                }
            )
            continue

        future_returns = returns[origin_index:endpoint_index]
        realized_cumulative = realized_close_variance(future_returns)
        calendar_days = (window.endpoint - window.origin).days
        realized_annualized = annualize_cumulative_variance(
            realized_cumulative,
            horizon_calendar_days=calendar_days,
            calendar_days_per_year=request.model.calendar_days_per_year,
        )
        shared_fit = {
            "availability_cutoff": window.origin.isoformat(),
            "available_input_prefix": {
                "input_id": input_data.input_id,
                "sha256": _available_prefix_hash(
                    input_data,
                    first_index=earliest_index,
                    last_index=origin_index,
                ),
                "observation_count": len(fit_returns) + 1,
            },
            "fit_start": dates[earliest_index].isoformat(),
            "fit_end": window.origin.isoformat(),
            "return_count": len(fit_returns),
            "lookback_return_limit": request.model.lookback_returns,
            "mean_convention": request.model.mean,
        }
        forecasts = {
            "historical": _forecast_entry(
                flat_variance_forecast(historical_one_step, horizon),
                realized_annualized=realized_annualized,
                calendar_days=calendar_days,
                calendar_days_per_year=request.model.calendar_days_per_year,
                parameters={"fitted_mean": historical_mean, "one_step_variance": historical_one_step},
                fit={**shared_fit, "estimator": "historical_variance", "ddof": 0 if request.model.mean == "zero" else 1},
            ),
            "ewma": _forecast_entry(
                flat_variance_forecast(ewma_one_step, horizon),
                realized_annualized=realized_annualized,
                calendar_days=calendar_days,
                calendar_days_per_year=request.model.calendar_days_per_year,
                parameters={
                    "decay": request.model.ewma_decay,
                    "fitted_mean": ewma_mean,
                    "one_step_variance": ewma_one_step,
                },
                fit={**shared_fit, "estimator": "ewma", "initial_variance": "first_innovation_squared"},
            ),
            "garch_1_1": _forecast_entry(
                garch.conditional_variances,
                realized_annualized=realized_annualized,
                calendar_days=calendar_days,
                calendar_days_per_year=request.model.calendar_days_per_year,
                parameters={
                    "decimal_return_units": dict(garch.parameters_decimal),
                    "upstream_percent_return_units": dict(garch.parameters_upstream_percent),
                },
                fit={
                    **shared_fit,
                    "estimator": "arch.arch_model",
                    "distribution": "normal",
                    "convergence": dict(garch.convergence),
                    "log_likelihood": garch.log_likelihood,
                    "aic": garch.aic,
                    "bic": garch.bic,
                },
            ),
        }
        records.append(
            {
                "origin": window.origin.isoformat(),
                "endpoint": window.endpoint.isoformat(),
                "split": window.split,
                "availability_cutoff": window.origin.isoformat(),
                "horizon": {
                    "endpoint_rule": "explicit_supplied_endpoint_inclusive_of_close_return_ending_at_endpoint",
                    "interval_count": horizon,
                    "calendar_days": calendar_days,
                    "annualization_factor": request.model.calendar_days_per_year / calendar_days,
                },
                "realized_proxy": {
                    "name": "close_to_close_sum_squared_log_returns",
                    "interval_count": horizon,
                    "cumulative_variance_decimal_squared": realized_cumulative,
                    "annualized_variance": realized_annualized,
                },
                "forecasts": forecasts,
            }
        )

    status = "complete" if len(records) == len(request.windows) else ("partial" if records else "failed")
    result_errors: list[dict[str, str]] = []
    if not records:
        result_errors.append(
            Diagnostic("no_eligible_origins", "no origin completed all three models", "request.windows").to_dict()
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "analysis_id": request.analysis_id,
        "status": status,
        "versions": runtime_versions(),
        "inputs": [_input_summary(input_data)],
        "request_sha256": request.sha256,
        "configuration": _request_summary(request),
        "evaluation_records": records,
        "metrics": _metrics(records),
        "exclusions": exclusions,
        "fit_failures": fit_failures,
        "errors": result_errors,
        "warnings": _overlapping_windows(request),
        "statistical_inference": "descriptive_only_no_naive_significance_claims",
    }


def run_analysis(request_document: Any, input_document: Any) -> dict[str, Any]:
    """Validate explicit documents and return a deterministic result artifact.

    Expected data and fit failures are represented in the returned artifact;
    callers do not need to catch validation exceptions. This function performs
    no filesystem, network, database, provider, or ledger access.
    """
    try:
        request = parse_request(request_document)
    except ContractError as exc:
        analysis_id = request_document.get("analysis_id") if isinstance(request_document, Mapping) and isinstance(request_document.get("analysis_id"), str) else None
        return failure_artifact(exc.diagnostics, analysis_id=analysis_id)
    try:
        input_data = parse_close_input(input_document, max_observations=request.limits.max_observations)
    except ContractError as exc:
        return failure_artifact(exc.diagnostics, analysis_id=request.analysis_id)
    return _analyze(request, input_data)
