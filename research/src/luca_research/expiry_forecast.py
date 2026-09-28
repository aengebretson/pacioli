"""Forecast physical cumulative variance over an explicit option interval.

This module extends the Q1 rolling, EWMA, and ``arch`` GARCH implementations.
It intentionally accepts a caller-supplied daily-close schedule: this package
does not guess exchange holidays or pretend daily data can resolve an intraday
or morning-settled expiration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import math
import platform
import re
from typing import Any, Mapping, Sequence

from .contracts import (
    HARD_MAX_GARCH_ITERATIONS,
    HARD_MAX_OBSERVATIONS,
    ContractError,
    Diagnostic,
    NormalizedCloseInput,
    canonical_sha256,
    parse_close_input,
)
from .estimators import (
    ewma_variance,
    flat_variance_forecast,
    historical_variance,
)
from .garch import GarchFitFailure, fit_garch11


REQUEST_SCHEMA = "luca.expiry-variance-request.v1"
RESULT_SCHEMA = "luca.expiry-variance-result.v1"
MODULE_VERSION = "1.0.0"
MODEL_NAMES = ("rolling", "ewma", "garch_1_1")
MODEL_VERSIONS = {
    "rolling": "luca.q1-rolling-variance.v1",
    "ewma": "luca.q1-ewma.v1",
    "garch_1_1": "luca.q1-arch-garch-1-1.v1",
}
SUPPORTED_BOUNDARY_PRECISION = "daily_close"
SUPPORTED_REFIT_POLICY = "fit_once_at_information_cutoff"
MAX_FORECAST_INTERVALS = 366

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CalendarIdentity:
    calendar_id: str
    version: str
    source: str


@dataclass(frozen=True)
class ExpiryInterval:
    cutoff: date
    expiration: date
    interval_end_dates: tuple[date, ...]
    boundary_precision: str
    calendar: CalendarIdentity


@dataclass(frozen=True)
class ExpiryModelConfig:
    fitting_window_returns: int
    minimum_fit_returns: int
    mean: str
    ewma_decay: float
    calendar_days_per_year: float
    garch_max_iterations: int
    optimizer_tolerance: float
    refit_policy: str
    selected_model: str
    selection_basis: str


@dataclass(frozen=True)
class ExpiryForecastRequest:
    run_id: str
    research_use: str
    input_id: str
    input_sha256: str
    input_available_at: str
    interval: ExpiryInterval
    model: ExpiryModelConfig
    sha256: str


def _exact_keys(
    value: Mapping[str, Any], required: set[str], field: str, errors: list[Diagnostic]
) -> None:
    for key in sorted(required - set(value)):
        errors.append(
            Diagnostic("missing_field", f"missing required field {field}.{key}", f"{field}.{key}")
        )
    for key in sorted(set(value) - required):
        errors.append(Diagnostic("unknown_field", f"unknown field {field}.{key}", f"{field}.{key}"))


def _mapping(value: Any, field: str, errors: list[Diagnostic]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(Diagnostic("invalid_type", f"{field} must be an object", field))
        return {}
    return value


def _identifier(value: Any, field: str, errors: list[Diagnostic]) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        errors.append(Diagnostic("invalid_identifier", f"{field} must be a stable identifier", field))
        return "invalid"
    return value


def _nonempty_string(value: Any, field: str, errors: list[Diagnostic]) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        errors.append(
            Diagnostic(
                "invalid_string",
                f"{field} must be a non-empty string of at most 512 characters",
                field,
            )
        )
        return "invalid"
    return value


def _parse_date(value: Any, field: str, errors: list[Diagnostic]) -> date:
    if not isinstance(value, str):
        errors.append(Diagnostic("invalid_date", f"{field} must use YYYY-MM-DD", field))
        return date.min
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        is_partial_session = "T" in value or " " in value
        errors.append(
            Diagnostic(
                "unsupported_partial_session_precision" if is_partial_session else "invalid_date",
                (
                    f"{field} must be a calendar date; intraday timestamps are unsupported"
                    if is_partial_session
                    else f"{field} must use YYYY-MM-DD"
                ),
                field,
            )
        )
        return date.min
    if value != parsed.isoformat():
        errors.append(Diagnostic("noncanonical_date", f"{field} must use YYYY-MM-DD", field))
    return parsed


def _utc_timestamp(value: Any, field: str, errors: list[Diagnostic]) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append(
            Diagnostic(
                "invalid_utc_timestamp",
                f"{field} must be an ISO 8601 UTC timestamp ending in Z",
                field,
            )
        )
        return "1970-01-01T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        errors.append(Diagnostic("invalid_utc_timestamp", f"{field} is not a valid timestamp", field))
        return "1970-01-01T00:00:00Z"
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        errors.append(Diagnostic("invalid_utc_timestamp", f"{field} must be UTC", field))
    return value


def _integer(
    value: Any,
    field: str,
    errors: list[Diagnostic],
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        errors.append(
            Diagnostic(
                "invalid_integer",
                f"{field} must be an integer in [{minimum}, {maximum}]",
                field,
            )
        )
        return minimum
    return value


def _finite_number(
    value: Any,
    field: str,
    errors: list[Diagnostic],
    *,
    minimum_exclusive: float | None = None,
    maximum_exclusive: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(Diagnostic("invalid_number", f"{field} must be a finite number", field))
        return 0.0
    try:
        result = float(value)
    except (OverflowError, ValueError):
        errors.append(
            Diagnostic(
                "number_not_representable",
                f"{field} must be representable as a finite binary64 number",
                field,
            )
        )
        return 0.0
    if not math.isfinite(result):
        errors.append(Diagnostic("invalid_number", f"{field} must be finite", field))
        return 0.0
    if minimum_exclusive is not None and result <= minimum_exclusive:
        errors.append(
            Diagnostic("number_out_of_range", f"{field} must be greater than {minimum_exclusive}", field)
        )
    if maximum_exclusive is not None and result >= maximum_exclusive:
        errors.append(
            Diagnostic("number_out_of_range", f"{field} must be less than {maximum_exclusive}", field)
        )
    return result


def parse_expiry_request(document: Any) -> ExpiryForecastRequest:
    """Validate the expiry request without reading data or external calendars."""
    errors: list[Diagnostic] = []
    root = _mapping(document, "request", errors)
    _exact_keys(
        root,
        {"schema_version", "run_id", "research_use", "input", "interval", "model"},
        "request",
        errors,
    )
    if root.get("schema_version") != REQUEST_SCHEMA:
        errors.append(
            Diagnostic(
                "unsupported_schema",
                f"request.schema_version must be {REQUEST_SCHEMA}",
                "request.schema_version",
            )
        )
    run_id = _identifier(root.get("run_id"), "request.run_id", errors)
    research_use_value = root.get("research_use")
    allowed_research_uses = {
        "illustrative_fixture",
        "exploratory_historical",
        "unexamined_evaluation",
    }
    if research_use_value not in allowed_research_uses:
        errors.append(
            Diagnostic(
                "invalid_research_use",
                "request.research_use must explicitly distinguish fixture, "
                "exploratory history, or unexamined evaluation",
                "request.research_use",
            )
        )
        research_use = "illustrative_fixture"
    else:
        research_use = str(research_use_value)

    input_ref = _mapping(root.get("input"), "request.input", errors)
    _exact_keys(input_ref, {"input_id", "sha256", "available_at"}, "request.input", errors)
    input_id = _identifier(input_ref.get("input_id"), "request.input.input_id", errors)
    hash_value = input_ref.get("sha256")
    if not isinstance(hash_value, str) or not _HASH_RE.fullmatch(hash_value):
        errors.append(
            Diagnostic(
                "invalid_hash",
                "request.input.sha256 must be a lowercase SHA-256 digest",
                "request.input.sha256",
            )
        )
        input_sha256 = "0" * 64
    else:
        input_sha256 = hash_value
    input_available_at = _utc_timestamp(
        input_ref.get("available_at"), "request.input.available_at", errors
    )

    interval_raw = _mapping(root.get("interval"), "request.interval", errors)
    _exact_keys(
        interval_raw,
        {"cutoff", "expiration", "interval_end_dates", "boundary_precision", "calendar"},
        "request.interval",
        errors,
    )
    cutoff = _parse_date(interval_raw.get("cutoff"), "request.interval.cutoff", errors)
    expiration = _parse_date(
        interval_raw.get("expiration"), "request.interval.expiration", errors
    )
    boundary_precision_value = interval_raw.get("boundary_precision")
    if boundary_precision_value != SUPPORTED_BOUNDARY_PRECISION:
        errors.append(
            Diagnostic(
                "unsupported_partial_session_precision",
                f"request.interval.boundary_precision must be {SUPPORTED_BOUNDARY_PRECISION}",
                "request.interval.boundary_precision",
            )
        )
    boundary_precision = SUPPORTED_BOUNDARY_PRECISION

    raw_end_dates = interval_raw.get("interval_end_dates")
    if not isinstance(raw_end_dates, list):
        errors.append(
            Diagnostic(
                "invalid_type",
                "request.interval.interval_end_dates must be an array",
                "request.interval.interval_end_dates",
            )
        )
        raw_end_dates = []
    if not 1 <= len(raw_end_dates) <= MAX_FORECAST_INTERVALS:
        errors.append(
            Diagnostic(
                "invalid_horizon",
                f"request interval must contain 1..{MAX_FORECAST_INTERVALS} end dates",
                "request.interval.interval_end_dates",
            )
        )
        if len(raw_end_dates) > MAX_FORECAST_INTERVALS:
            raise ContractError(errors)
    end_dates = tuple(
        _parse_date(value, f"request.interval.interval_end_dates[{index}]", errors)
        for index, value in enumerate(raw_end_dates)
    )
    if expiration <= cutoff:
        errors.append(
            Diagnostic(
                "invalid_interval",
                "request.interval.expiration must be after cutoff",
                "request.interval",
            )
        )
    previous = cutoff
    for index, end_date in enumerate(end_dates):
        if end_date <= previous:
            errors.append(
                Diagnostic(
                    "unordered_interval_schedule",
                    "forecast interval end dates must be strictly increasing after cutoff",
                    f"request.interval.interval_end_dates[{index}]",
                )
            )
        if end_date > expiration:
            errors.append(
                Diagnostic(
                    "interval_past_expiration",
                    "forecast interval end date cannot be after expiration",
                    f"request.interval.interval_end_dates[{index}]",
                )
            )
        previous = end_date
    if end_dates and end_dates[-1] != expiration:
        errors.append(
            Diagnostic(
                "expiration_not_covered",
                "the final forecast interval must end on the explicit expiration date",
                "request.interval.interval_end_dates",
            )
        )

    calendar_raw = _mapping(interval_raw.get("calendar"), "request.interval.calendar", errors)
    _exact_keys(
        calendar_raw,
        {"calendar_id", "version", "source"},
        "request.interval.calendar",
        errors,
    )
    calendar = CalendarIdentity(
        calendar_id=_identifier(
            calendar_raw.get("calendar_id"), "request.interval.calendar.calendar_id", errors
        ),
        version=_nonempty_string(
            calendar_raw.get("version"), "request.interval.calendar.version", errors
        ),
        source=_nonempty_string(
            calendar_raw.get("source"), "request.interval.calendar.source", errors
        ),
    )

    model_raw = _mapping(root.get("model"), "request.model", errors)
    _exact_keys(
        model_raw,
        {
            "fitting_window_returns",
            "minimum_fit_returns",
            "mean",
            "ewma_decay",
            "calendar_days_per_year",
            "garch_max_iterations",
            "optimizer_tolerance",
            "refit_policy",
            "selected_model",
            "selection_basis",
        },
        "request.model",
        errors,
    )
    fitting_window = _integer(
        model_raw.get("fitting_window_returns"),
        "request.model.fitting_window_returns",
        errors,
        minimum=2,
        maximum=HARD_MAX_OBSERVATIONS - 1,
    )
    minimum_fit = _integer(
        model_raw.get("minimum_fit_returns"),
        "request.model.minimum_fit_returns",
        errors,
        minimum=2,
        maximum=HARD_MAX_OBSERVATIONS - 1,
    )
    if minimum_fit > fitting_window:
        errors.append(
            Diagnostic(
                "inconsistent_fitting_window",
                "minimum_fit_returns cannot exceed fitting_window_returns",
                "request.model.minimum_fit_returns",
            )
        )
    mean_value = model_raw.get("mean")
    if mean_value not in {"zero", "constant"}:
        errors.append(
            Diagnostic(
                "invalid_mean",
                "request.model.mean must be zero or constant",
                "request.model.mean",
            )
        )
        mean = "zero"
    else:
        mean = str(mean_value)
    ewma_decay = _finite_number(
        model_raw.get("ewma_decay"),
        "request.model.ewma_decay",
        errors,
        minimum_exclusive=0.0,
        maximum_exclusive=1.0,
    )
    calendar_days_per_year = _finite_number(
        model_raw.get("calendar_days_per_year"),
        "request.model.calendar_days_per_year",
        errors,
        minimum_exclusive=0.0,
    )
    garch_max_iterations = _integer(
        model_raw.get("garch_max_iterations"),
        "request.model.garch_max_iterations",
        errors,
        minimum=1,
        maximum=HARD_MAX_GARCH_ITERATIONS,
    )
    optimizer_tolerance = _finite_number(
        model_raw.get("optimizer_tolerance"),
        "request.model.optimizer_tolerance",
        errors,
        minimum_exclusive=0.0,
    )
    refit_policy_value = model_raw.get("refit_policy")
    if refit_policy_value != SUPPORTED_REFIT_POLICY:
        errors.append(
            Diagnostic(
                "unsupported_refit_policy",
                f"request.model.refit_policy must be {SUPPORTED_REFIT_POLICY}",
                "request.model.refit_policy",
            )
        )
    selected_model_value = model_raw.get("selected_model")
    if selected_model_value not in MODEL_NAMES:
        errors.append(
            Diagnostic(
                "invalid_selected_model",
                f"request.model.selected_model must be one of {', '.join(MODEL_NAMES)}",
                "request.model.selected_model",
            )
        )
        selected_model = "rolling"
    else:
        selected_model = str(selected_model_value)
    selection_basis = _nonempty_string(
        model_raw.get("selection_basis"), "request.model.selection_basis", errors
    )

    if errors:
        raise ContractError(errors)
    return ExpiryForecastRequest(
        run_id=run_id,
        research_use=research_use,
        input_id=input_id,
        input_sha256=input_sha256,
        input_available_at=input_available_at,
        interval=ExpiryInterval(
            cutoff=cutoff,
            expiration=expiration,
            interval_end_dates=end_dates,
            boundary_precision=boundary_precision,
            calendar=calendar,
        ),
        model=ExpiryModelConfig(
            fitting_window_returns=fitting_window,
            minimum_fit_returns=minimum_fit,
            mean=mean,
            ewma_decay=ewma_decay,
            calendar_days_per_year=calendar_days_per_year,
            garch_max_iterations=garch_max_iterations,
            optimizer_tolerance=optimizer_tolerance,
            refit_policy=SUPPORTED_REFIT_POLICY,
            selected_model=selected_model,
            selection_basis=selection_basis,
        ),
        sha256=canonical_sha256(document),
    )


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def _runtime_versions() -> dict[str, Any]:
    return {
        "expiry_forecast_module": MODULE_VERSION,
        "python": platform.python_version(),
        "dependencies": {
            "arch": _package_version("arch"),
            "numpy": _package_version("numpy"),
        },
    }


def _failure_artifact(
    diagnostics: Sequence[Diagnostic], *, run_id: str | None = None
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA,
        "run_id": run_id,
        "status": "failed",
        "research_use": None,
        "versions": _runtime_versions(),
        "request_sha256": None,
        "inputs": [],
        "configuration": None,
        "interval": None,
        "selection": None,
        "models": {},
        "exclusions": [],
        "errors": [item.to_dict() for item in diagnostics],
        "warnings": [],
    }


def _decimal_log_returns(closes: Sequence[float]) -> tuple[float, ...]:
    log_closes = tuple(math.log(value) for value in closes)
    returns = tuple(
        log_closes[index] - log_closes[index - 1]
        for index in range(1, len(log_closes))
    )
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("eligible closes produced a nonfinite decimal log return")
    return returns


def _history_sha256(
    input_data: NormalizedCloseInput, *, first_index: int, cutoff_index: int
) -> str:
    return canonical_sha256(
        {
            "close_unit": input_data.close_unit,
            "input_id": input_data.input_id,
            "observations": [
                {"close": item.close, "date": item.date.isoformat()}
                for item in input_data.observations[first_index : cutoff_index + 1]
            ],
            "schema_version": "luca.normalized-close.v1",
        }
    )


def _common_fit(
    request: ExpiryForecastRequest,
    input_data: NormalizedCloseInput,
    *,
    first_index: int,
    cutoff_index: int,
    return_count: int,
) -> dict[str, Any]:
    observations = input_data.observations
    return {
        "availability_cutoff": request.interval.cutoff.isoformat(),
        "input_available_at": request.input_available_at,
        "fit_start": observations[first_index].date.isoformat(),
        "fit_end": request.interval.cutoff.isoformat(),
        "observation_count": return_count + 1,
        "return_count": return_count,
        "fitting_window_return_limit": request.model.fitting_window_returns,
        "minimum_fit_returns": request.model.minimum_fit_returns,
        "mean_convention": request.model.mean,
        "return_definition": "close_to_close_log_return",
        "return_units": "log_decimal",
        "eligible_history_sha256": _history_sha256(
            input_data, first_index=first_index, cutoff_index=cutoff_index
        ),
        "refit_policy": request.model.refit_policy,
        "refit_count_for_request": 1,
        "evaluation_outcomes_used": False,
    }


def _forecast_payload(
    request: ExpiryForecastRequest, variances: Sequence[float]
) -> dict[str, Any]:
    if len(variances) != len(request.interval.interval_end_dates):
        raise ValueError("model returned a variance count different from the explicit interval count")
    if any(not math.isfinite(value) or value <= 0.0 for value in variances):
        raise ValueError("model returned a nonpositive or nonfinite conditional variance")
    starts = (request.interval.cutoff, *request.interval.interval_end_dates[:-1])
    periods = [
        {
            "h": index,
            "start_date_exclusive": start.isoformat(),
            "end_date_inclusive": end.isoformat(),
            "conditional_variance_decimal_squared": float(variance),
        }
        for index, (start, end, variance) in enumerate(
            zip(starts, request.interval.interval_end_dates, variances, strict=True), start=1
        )
    ]
    cumulative = math.fsum(float(value) for value in variances)
    calendar_days = (request.interval.expiration - request.interval.cutoff).days
    year_fraction = calendar_days / request.model.calendar_days_per_year
    annualized_variance = cumulative / year_fraction
    return {
        "period_forecasts": periods,
        "W_P_decimal_squared": cumulative,
        "cumulative_rule": "sum_h_1_through_H_conditional_variance",
        "annualization": {
            "convention": "actual_calendar_days_over_configured_calendar_days_per_year",
            "calendar_days": calendar_days,
            "calendar_days_per_year": request.model.calendar_days_per_year,
            "calendar_year_fraction": year_fraction,
            "annualized_variance": annualized_variance,
            "annualized_volatility": math.sqrt(annualized_variance),
        },
    }


def _excluded_model(
    request: ExpiryForecastRequest,
    name: str,
    common_fit: Mapping[str, Any],
    *,
    reason: str,
    message: str,
    convergence: Mapping[str, Any] | str,
) -> dict[str, Any]:
    return {
        "model_identity": {"name": name, "version": MODEL_VERSIONS[name]},
        "role": "selected" if name == request.model.selected_model else "challenger",
        "status": "excluded",
        "parameters": None,
        "fit": {**common_fit, "convergence": convergence},
        "forecast": None,
        "exclusion": {"reason": reason, "message": message},
    }


def _complete_model(
    request: ExpiryForecastRequest,
    name: str,
    common_fit: Mapping[str, Any],
    *,
    estimator: str,
    parameters: Mapping[str, Any],
    convergence: Mapping[str, Any] | str,
    variances: Sequence[float],
    fit_details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "model_identity": {"name": name, "version": MODEL_VERSIONS[name]},
        "role": "selected" if name == request.model.selected_model else "challenger",
        "status": "complete",
        "parameters": dict(parameters),
        "fit": {
            **common_fit,
            "estimator": estimator,
            "convergence": convergence,
            **dict(fit_details or {}),
        },
        "forecast": _forecast_payload(request, variances),
        "exclusion": None,
    }


def forecast_expiry_variance(
    request: ExpiryForecastRequest, input_data: NormalizedCloseInput
) -> dict[str, Any]:
    """Fit all three models once and forecast every supplied daily interval.

    Fitting is limited to the exact trailing window ending at ``cutoff``.
    Observations after the cutoff are ignored, even when present in a historical
    reconstruction input. Each model receives the identical decimal-return
    vector and horizon. A failed GARCH fit is recorded, never replaced.
    """
    if request.input_id != input_data.input_id:
        return _failure_artifact(
            [
                Diagnostic(
                    "input_id_mismatch",
                    "request input_id does not match normalized close input",
                    "request.input.input_id",
                )
            ],
            run_id=request.run_id,
        )
    if request.input_sha256 != input_data.sha256:
        return _failure_artifact(
            [
                Diagnostic(
                    "input_hash_mismatch",
                    "request input SHA-256 does not match normalized close input",
                    "request.input.sha256",
                )
            ],
            run_id=request.run_id,
        )

    observations = input_data.observations
    date_indices = {item.date: index for index, item in enumerate(observations)}
    cutoff_index = date_indices.get(request.interval.cutoff)
    if cutoff_index is None:
        return _failure_artifact(
            [
                Diagnostic(
                    "missing_cutoff_observation",
                    "cutoff must be an observation date in the normalized close input",
                    "request.interval.cutoff",
                )
            ],
            run_id=request.run_id,
        )

    first_index = max(0, cutoff_index - request.model.fitting_window_returns)
    fit_closes = tuple(item.close for item in observations[first_index : cutoff_index + 1])
    try:
        fit_returns = _decimal_log_returns(fit_closes)
    except (OverflowError, ValueError) as exc:
        return _failure_artifact(
            [Diagnostic("invalid_derived_return", str(exc), "input.observations")],
            run_id=request.run_id,
        )
    common_fit = _common_fit(
        request,
        input_data,
        first_index=first_index,
        cutoff_index=cutoff_index,
        return_count=len(fit_returns),
    )

    models: dict[str, dict[str, Any]] = {}
    exclusions: list[dict[str, Any]] = []
    horizon = len(request.interval.interval_end_dates)
    if len(fit_returns) < request.model.minimum_fit_returns:
        message = (
            f"only {len(fit_returns)} eligible returns are available; "
            f"{request.model.minimum_fit_returns} are required"
        )
        for name in MODEL_NAMES:
            models[name] = _excluded_model(
                request,
                name,
                common_fit,
                reason="insufficient_fit_returns",
                message=message,
                convergence="not_attempted",
            )
            exclusions.append(
                {"model": name, "reason": "insufficient_fit_returns", "message": message}
            )
    else:
        try:
            one_step, fitted_mean = historical_variance(fit_returns, request.model.mean)
            models["rolling"] = _complete_model(
                request,
                "rolling",
                common_fit,
                estimator="luca_research.estimators.historical_variance",
                parameters={
                    "fitted_mean": fitted_mean,
                    "one_step_variance_decimal_squared": one_step,
                    "ddof": 0 if request.model.mean == "zero" else 1,
                },
                convergence="not_applicable_closed_form",
                variances=flat_variance_forecast(one_step, horizon),
            )
        except ValueError as exc:
            models["rolling"] = _excluded_model(
                request,
                "rolling",
                common_fit,
                reason="rolling_fit_failure",
                message=str(exc),
                convergence="not_applicable_closed_form",
            )
            exclusions.append(
                {"model": "rolling", "reason": "rolling_fit_failure", "message": str(exc)}
            )

        try:
            one_step, fitted_mean = ewma_variance(
                fit_returns, request.model.ewma_decay, request.model.mean
            )
            models["ewma"] = _complete_model(
                request,
                "ewma",
                common_fit,
                estimator="luca_research.estimators.ewma_variance",
                parameters={
                    "decay": request.model.ewma_decay,
                    "fitted_mean": fitted_mean,
                    "initial_variance": "first_innovation_squared",
                    "one_step_variance_decimal_squared": one_step,
                },
                convergence="not_applicable_deterministic_recursion",
                variances=flat_variance_forecast(one_step, horizon),
            )
        except ValueError as exc:
            models["ewma"] = _excluded_model(
                request,
                "ewma",
                common_fit,
                reason="ewma_fit_failure",
                message=str(exc),
                convergence="not_applicable_deterministic_recursion",
            )
            exclusions.append(
                {"model": "ewma", "reason": "ewma_fit_failure", "message": str(exc)}
            )

        try:
            garch = fit_garch11(
                fit_returns,
                horizon=horizon,
                mean=request.model.mean,
                max_iterations=request.model.garch_max_iterations,
                optimizer_tolerance=request.model.optimizer_tolerance,
            )
            models["garch_1_1"] = _complete_model(
                request,
                "garch_1_1",
                common_fit,
                estimator="arch.arch_model",
                parameters={
                    "distribution": "normal",
                    "p": 1,
                    "q": 1,
                    "decimal_return_units": dict(garch.parameters_decimal),
                    "upstream_percent_return_units": dict(
                        garch.parameters_upstream_percent
                    ),
                },
                convergence=dict(garch.convergence),
                variances=garch.conditional_variances,
                fit_details={
                    "return_scale_for_fit": "percent",
                    "log_likelihood": garch.log_likelihood,
                    "aic": garch.aic,
                    "bic": garch.bic,
                },
            )
        except (GarchFitFailure, ValueError) as exc:
            details = getattr(exc, "details", {})
            convergence = dict(details) if isinstance(details, Mapping) else {}
            models["garch_1_1"] = _excluded_model(
                request,
                "garch_1_1",
                common_fit,
                reason="garch_fit_failure",
                message=str(exc),
                convergence=convergence or "fit_failed_before_convergence_details",
            )
            exclusions.append(
                {
                    "model": "garch_1_1",
                    "reason": "garch_fit_failure",
                    "message": str(exc),
                    "details": convergence,
                    "fallback_used": False,
                }
            )

    selected_status = models[request.model.selected_model]["status"]
    complete_count = sum(model["status"] == "complete" for model in models.values())
    if selected_status != "complete" or complete_count == 0:
        status = "failed"
    elif complete_count < len(MODEL_NAMES):
        status = "partial"
    else:
        status = "complete"

    warnings: list[dict[str, str]] = []
    ignored_count = len(observations) - cutoff_index - 1
    if ignored_count:
        warnings.append(
            {
                "code": "post_cutoff_observations_ignored",
                "message": f"{ignored_count} normalized close observations after cutoff were not used in fitting",
            }
        )
    if request.research_use != "unexamined_evaluation":
        warnings.append(
            {
                "code": "not_unexamined_evaluation",
                "message": "artifact is labelled fixture or exploratory history "
                "and is not held-out performance evidence",
            }
        )

    interval = request.interval
    calendar = interval.calendar
    return {
        "schema_version": RESULT_SCHEMA,
        "run_id": request.run_id,
        "status": status,
        "research_use": request.research_use,
        "versions": _runtime_versions(),
        "request_sha256": request.sha256,
        "inputs": [
            {
                "schema_version": "luca.normalized-close.v1",
                "input_id": input_data.input_id,
                "sha256": input_data.sha256,
                "available_at": request.input_available_at,
                "close_unit": input_data.close_unit,
                "observation_count": len(observations),
                "first_date": observations[0].date.isoformat(),
                "last_date": observations[-1].date.isoformat(),
                "eligible_history_sha256": common_fit["eligible_history_sha256"],
                "eligible_history_observation_count": common_fit["observation_count"],
                "post_cutoff_observation_count_ignored": ignored_count,
            }
        ],
        "configuration": {
            "fitting_window_returns": request.model.fitting_window_returns,
            "minimum_fit_returns": request.model.minimum_fit_returns,
            "mean": request.model.mean,
            "ewma_decay": request.model.ewma_decay,
            "garch": {
                "distribution": "normal",
                "p": 1,
                "q": 1,
                "max_iterations": request.model.garch_max_iterations,
                "optimizer_tolerance": request.model.optimizer_tolerance,
                "implementation": "luca_research.garch.fit_garch11",
            },
            "refit_policy": request.model.refit_policy,
            "outcome_dependent_refit_by_this_module": False,
        },
        "interval": {
            "cutoff": interval.cutoff.isoformat(),
            "expiration": interval.expiration.isoformat(),
            "boundary_precision": interval.boundary_precision,
            "interval_count": horizon,
            "interval_end_dates": [value.isoformat() for value in interval.interval_end_dates],
            "schedule_sha256": canonical_sha256(
                [value.isoformat() for value in interval.interval_end_dates]
            ),
            "calendar": {
                "calendar_id": calendar.calendar_id,
                "version": calendar.version,
                "source": calendar.source,
            },
            "partial_session_supported": False,
        },
        "units": {
            "input_return": "log_decimal",
            "period_variance": "decimal_return_squared",
            "W_P": "decimal_return_squared",
            "annualized_variance": "decimal_return_squared_per_calendar_year",
            "annualized_volatility": "decimal_per_sqrt_calendar_year",
        },
        "selection": {
            "selected_model": request.model.selected_model,
            "selected_status": selected_status,
            "selection_basis": request.model.selection_basis,
            "selection_supplied_by_caller": True,
            "evaluation_outcomes_used_by_this_module": False,
            "challenger_models": [
                name for name in MODEL_NAMES if name != request.model.selected_model
            ],
            "fallback_used": False,
        },
        "models": models,
        "exclusions": exclusions,
        "errors": [],
        "warnings": warnings,
    }


def run_expiry_forecast(request_document: Any, input_document: Any) -> dict[str, Any]:
    """Validate JSON-compatible mappings and return a JSON-compatible artifact.

    The callable performs no filesystem, network, calendar, provider, or
    database access. Expected contract and model-fit failures are returned as
    structured artifacts.
    """
    try:
        request = parse_expiry_request(request_document)
    except ContractError as exc:
        run_id = None
        if isinstance(request_document, Mapping) and isinstance(
            request_document.get("run_id"), str
        ):
            run_id = request_document["run_id"]
        return _failure_artifact(exc.diagnostics, run_id=run_id)
    try:
        input_data = parse_close_input(
            input_document, max_observations=HARD_MAX_OBSERVATIONS
        )
    except ContractError as exc:
        return _failure_artifact(exc.diagnostics, run_id=request.run_id)
    return forecast_expiry_variance(request, input_data)


__all__ = [
    "CalendarIdentity",
    "ExpiryForecastRequest",
    "ExpiryInterval",
    "ExpiryModelConfig",
    "MODEL_NAMES",
    "REQUEST_SCHEMA",
    "RESULT_SCHEMA",
    "forecast_expiry_variance",
    "parse_expiry_request",
    "run_expiry_forecast",
]
