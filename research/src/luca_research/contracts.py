"""Strict input contracts for the volatility research slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


INPUT_SCHEMA = "luca.normalized-close.v1"
REQUEST_SCHEMA = "luca.volatility-request.v1"
RESULT_SCHEMA = "luca.volatility-result.v1"
HARD_MAX_OBSERVATIONS = 10_000
HARD_MAX_ORIGINS = 100
HARD_MAX_GARCH_ITERATIONS = 2_000

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UNIT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    field: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}


class ContractError(ValueError):
    def __init__(self, diagnostics: Sequence[Diagnostic]):
        self.diagnostics = tuple(diagnostics)
        super().__init__("; ".join(item.message for item in diagnostics))


@dataclass(frozen=True)
class CloseObservation:
    date: date
    close: float


@dataclass(frozen=True)
class NormalizedCloseInput:
    input_id: str
    close_unit: str
    observations: tuple[CloseObservation, ...]
    sha256: str


@dataclass(frozen=True)
class EvaluationWindow:
    origin: date
    endpoint: date
    split: str


@dataclass(frozen=True)
class Boundaries:
    fit_start: date
    selection_start: date
    selection_end: date
    holdout_start: date
    holdout_end: date


@dataclass(frozen=True)
class ModelConfig:
    lookback_returns: int
    minimum_fit_returns: int
    mean: str
    ewma_decay: float
    calendar_days_per_year: float
    garch_max_iterations: int
    optimizer_tolerance: float
    random_seed: int


@dataclass(frozen=True)
class Limits:
    max_observations: int
    max_origins: int


@dataclass(frozen=True)
class AnalysisRequest:
    analysis_id: str
    input_id: str
    input_sha256: str
    boundaries: Boundaries
    windows: tuple[EvaluationWindow, ...]
    model: ModelConfig
    limits: Limits
    sha256: str


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: Any, field: str, errors: list[Diagnostic]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(Diagnostic("invalid_type", f"{field} must be an object", field))
        return {}
    return value


def _exact_keys(
    value: Mapping[str, Any], required: set[str], field: str, errors: list[Diagnostic]
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    for key in missing:
        errors.append(Diagnostic("missing_field", f"missing required field {field}.{key}", f"{field}.{key}"))
    for key in unknown:
        errors.append(Diagnostic("unknown_field", f"unknown field {field}.{key}", f"{field}.{key}"))


def _identifier(value: Any, field: str, errors: list[Diagnostic]) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        errors.append(Diagnostic("invalid_identifier", f"{field} must be a stable non-empty identifier", field))
        return "invalid"
    return value


def _date(value: Any, field: str, errors: list[Diagnostic]) -> date:
    if not isinstance(value, str):
        errors.append(Diagnostic("invalid_date", f"{field} must be an ISO 8601 date", field))
        return date.min
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(Diagnostic("invalid_date", f"{field} must be an ISO 8601 date", field))
        return date.min
    if parsed.isoformat() != value:
        errors.append(Diagnostic("noncanonical_date", f"{field} must use YYYY-MM-DD", field))
    return parsed


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
        errors.append(Diagnostic("nonfinite_number", f"{field} must be finite", field))
        return 0.0
    if minimum_exclusive is not None and result <= minimum_exclusive:
        errors.append(Diagnostic("number_out_of_range", f"{field} must be greater than {minimum_exclusive}", field))
    if maximum_exclusive is not None and result >= maximum_exclusive:
        errors.append(Diagnostic("number_out_of_range", f"{field} must be less than {maximum_exclusive}", field))
    return result


def parse_close_input(document: Any, *, max_observations: int) -> NormalizedCloseInput:
    errors: list[Diagnostic] = []
    root = _mapping(document, "input", errors)
    _exact_keys(root, {"schema_version", "input_id", "close_unit", "observations"}, "input", errors)
    if root.get("schema_version") != INPUT_SCHEMA:
        errors.append(Diagnostic("unsupported_schema", f"input.schema_version must be {INPUT_SCHEMA}", "input.schema_version"))
    input_id = _identifier(root.get("input_id"), "input.input_id", errors)
    close_unit_value = root.get("close_unit")
    if not isinstance(close_unit_value, str) or not _UNIT_RE.fullmatch(close_unit_value):
        errors.append(
            Diagnostic(
                "ambiguous_unit",
                "input.close_unit must be an explicit lowercase unit identifier",
                "input.close_unit",
            )
        )
        close_unit = "invalid"
    else:
        close_unit = close_unit_value

    raw_observations = root.get("observations")
    observations: list[CloseObservation] = []
    if not isinstance(raw_observations, list):
        errors.append(Diagnostic("invalid_type", "input.observations must be an array", "input.observations"))
        raw_observations = []
    if len(raw_observations) > max_observations:
        errors.append(
            Diagnostic(
                "observation_limit_exceeded",
                f"input has {len(raw_observations)} observations; limit is {max_observations}",
                "input.observations",
            )
        )
        raise ContractError(errors)
    if len(raw_observations) < 3:
        errors.append(Diagnostic("insufficient_observations", "at least 3 close observations are required", "input.observations"))

    previous: date | None = None
    seen: set[date] = set()
    for index, raw in enumerate(raw_observations):
        field = f"input.observations[{index}]"
        item = _mapping(raw, field, errors)
        _exact_keys(item, {"date", "close"}, field, errors)
        observed_date = _date(item.get("date"), f"{field}.date", errors)
        close = _finite_number(item.get("close"), f"{field}.close", errors, minimum_exclusive=0.0)
        if observed_date in seen:
            errors.append(Diagnostic("duplicate_date", f"duplicate observation date {observed_date.isoformat()}", f"{field}.date"))
        elif previous is not None and observed_date <= previous:
            errors.append(Diagnostic("unordered_dates", "observation dates must be strictly increasing", f"{field}.date"))
        seen.add(observed_date)
        previous = observed_date
        observations.append(CloseObservation(observed_date, close))

    if errors:
        raise ContractError(errors)

    normalized = {
        "close_unit": close_unit,
        "input_id": input_id,
        "observations": [
            {"close": observation.close, "date": observation.date.isoformat()}
            for observation in observations
        ],
        "schema_version": INPUT_SCHEMA,
    }
    return NormalizedCloseInput(input_id, close_unit, tuple(observations), canonical_sha256(normalized))


def parse_request(document: Any) -> AnalysisRequest:
    errors: list[Diagnostic] = []
    root = _mapping(document, "request", errors)
    _exact_keys(
        root,
        {"schema_version", "analysis_id", "input", "boundaries", "windows", "model", "limits"},
        "request",
        errors,
    )
    if root.get("schema_version") != REQUEST_SCHEMA:
        errors.append(Diagnostic("unsupported_schema", f"request.schema_version must be {REQUEST_SCHEMA}", "request.schema_version"))
    analysis_id = _identifier(root.get("analysis_id"), "request.analysis_id", errors)

    input_ref = _mapping(root.get("input"), "request.input", errors)
    _exact_keys(input_ref, {"input_id", "sha256"}, "request.input", errors)
    input_id = _identifier(input_ref.get("input_id"), "request.input.input_id", errors)
    input_sha256_value = input_ref.get("sha256")
    if not isinstance(input_sha256_value, str) or not _HASH_RE.fullmatch(input_sha256_value):
        errors.append(Diagnostic("invalid_hash", "request.input.sha256 must be a lowercase SHA-256 digest", "request.input.sha256"))
        input_sha256 = "0" * 64
    else:
        input_sha256 = input_sha256_value

    raw_limits = _mapping(root.get("limits"), "request.limits", errors)
    _exact_keys(raw_limits, {"max_observations", "max_origins"}, "request.limits", errors)
    max_observations = _integer(
        raw_limits.get("max_observations"),
        "request.limits.max_observations",
        errors,
        minimum=3,
        maximum=HARD_MAX_OBSERVATIONS,
    )
    max_origins = _integer(
        raw_limits.get("max_origins"),
        "request.limits.max_origins",
        errors,
        minimum=1,
        maximum=HARD_MAX_ORIGINS,
    )

    raw_model = _mapping(root.get("model"), "request.model", errors)
    _exact_keys(
        raw_model,
        {
            "lookback_returns",
            "minimum_fit_returns",
            "mean",
            "ewma_decay",
            "calendar_days_per_year",
            "garch_max_iterations",
            "optimizer_tolerance",
            "random_seed",
        },
        "request.model",
        errors,
    )
    lookback = _integer(raw_model.get("lookback_returns"), "request.model.lookback_returns", errors, minimum=2, maximum=HARD_MAX_OBSERVATIONS - 1)
    minimum_fit = _integer(raw_model.get("minimum_fit_returns"), "request.model.minimum_fit_returns", errors, minimum=2, maximum=HARD_MAX_OBSERVATIONS - 1)
    if minimum_fit > lookback:
        errors.append(Diagnostic("inconsistent_lookback", "minimum_fit_returns cannot exceed lookback_returns", "request.model.minimum_fit_returns"))
    mean_value = raw_model.get("mean")
    if mean_value not in {"zero", "constant"}:
        errors.append(Diagnostic("invalid_mean", "request.model.mean must be zero or constant", "request.model.mean"))
        mean = "zero"
    else:
        mean = str(mean_value)
    ewma_decay = _finite_number(raw_model.get("ewma_decay"), "request.model.ewma_decay", errors, minimum_exclusive=0.0, maximum_exclusive=1.0)
    calendar_days = _finite_number(raw_model.get("calendar_days_per_year"), "request.model.calendar_days_per_year", errors, minimum_exclusive=0.0)
    max_iterations = _integer(raw_model.get("garch_max_iterations"), "request.model.garch_max_iterations", errors, minimum=1, maximum=HARD_MAX_GARCH_ITERATIONS)
    optimizer_tolerance = _finite_number(raw_model.get("optimizer_tolerance"), "request.model.optimizer_tolerance", errors, minimum_exclusive=0.0)
    random_seed = _integer(raw_model.get("random_seed"), "request.model.random_seed", errors, minimum=0, maximum=2**32 - 1)

    raw_boundaries = _mapping(root.get("boundaries"), "request.boundaries", errors)
    boundary_keys = {"fit_start", "selection_start", "selection_end", "holdout_start", "holdout_end"}
    _exact_keys(raw_boundaries, boundary_keys, "request.boundaries", errors)
    fit_start = _date(raw_boundaries.get("fit_start"), "request.boundaries.fit_start", errors)
    selection_start = _date(raw_boundaries.get("selection_start"), "request.boundaries.selection_start", errors)
    selection_end = _date(raw_boundaries.get("selection_end"), "request.boundaries.selection_end", errors)
    holdout_start = _date(raw_boundaries.get("holdout_start"), "request.boundaries.holdout_start", errors)
    holdout_end = _date(raw_boundaries.get("holdout_end"), "request.boundaries.holdout_end", errors)
    if not (fit_start < selection_start <= selection_end < holdout_start <= holdout_end):
        errors.append(
            Diagnostic(
                "invalid_boundaries",
                "boundaries must satisfy fit_start < selection_start <= selection_end < holdout_start <= holdout_end",
                "request.boundaries",
            )
        )

    raw_windows = root.get("windows")
    windows: list[EvaluationWindow] = []
    if not isinstance(raw_windows, list):
        errors.append(Diagnostic("invalid_type", "request.windows must be an array", "request.windows"))
        raw_windows = []
    if not raw_windows:
        errors.append(Diagnostic("missing_windows", "at least one evaluation window is required", "request.windows"))
    if len(raw_windows) > max_origins:
        errors.append(Diagnostic("origin_limit_exceeded", f"request has {len(raw_windows)} origins; limit is {max_origins}", "request.windows"))
        raise ContractError(errors)
    seen_origins: set[date] = set()
    for index, raw in enumerate(raw_windows):
        field = f"request.windows[{index}]"
        item = _mapping(raw, field, errors)
        _exact_keys(item, {"origin", "endpoint", "split"}, field, errors)
        origin = _date(item.get("origin"), f"{field}.origin", errors)
        endpoint = _date(item.get("endpoint"), f"{field}.endpoint", errors)
        split_value = item.get("split")
        if split_value not in {"selection", "holdout"}:
            errors.append(Diagnostic("invalid_split", f"{field}.split must be selection or holdout", f"{field}.split"))
            split = "selection"
        else:
            split = str(split_value)
        if endpoint <= origin:
            errors.append(Diagnostic("invalid_horizon", f"{field}.endpoint must be after origin", field))
        if origin in seen_origins:
            errors.append(Diagnostic("duplicate_origin", "evaluation origins must be unique", f"{field}.origin"))
        seen_origins.add(origin)
        if split == "selection" and not (selection_start <= origin < endpoint <= selection_end):
            errors.append(
                Diagnostic(
                    "boundary_leakage",
                    "selection labels must remain wholly within selection_start..selection_end",
                    field,
                )
            )
        if split == "holdout" and not (holdout_start <= origin < endpoint <= holdout_end):
            errors.append(
                Diagnostic(
                    "boundary_leakage",
                    "held-out labels must remain wholly within holdout_start..holdout_end",
                    field,
                )
            )
        windows.append(EvaluationWindow(origin, endpoint, split))

    if errors:
        raise ContractError(errors)

    request_hash = canonical_sha256(document)
    return AnalysisRequest(
        analysis_id=analysis_id,
        input_id=input_id,
        input_sha256=input_sha256,
        boundaries=Boundaries(fit_start, selection_start, selection_end, holdout_start, holdout_end),
        windows=tuple(windows),
        model=ModelConfig(
            lookback,
            minimum_fit,
            mean,
            ewma_decay,
            calendar_days,
            max_iterations,
            optimizer_tolerance,
            random_seed,
        ),
        limits=Limits(max_observations, max_origins),
        sha256=request_hash,
    )
