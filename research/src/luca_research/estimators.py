"""Small deterministic variance baselines and metric helpers."""

from __future__ import annotations

import math
from typing import Sequence


def fitted_mean(returns: Sequence[float], convention: str) -> float:
    if convention == "zero":
        return 0.0
    if convention != "constant":
        raise ValueError("mean convention must be zero or constant")
    if not returns:
        raise ValueError("at least one return is required")
    return math.fsum(returns) / len(returns)


def historical_variance(returns: Sequence[float], convention: str) -> tuple[float, float]:
    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    mean = fitted_mean(returns, convention)
    squared = [(value - mean) ** 2 for value in returns]
    denominator = len(returns) if convention == "zero" else len(returns) - 1
    variance = math.fsum(squared) / denominator
    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError("historical variance is not strictly positive and finite")
    return variance, mean


def ewma_variance(returns: Sequence[float], decay: float, convention: str) -> tuple[float, float]:
    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    if not 0.0 < decay < 1.0:
        raise ValueError("EWMA decay must be between zero and one")
    mean = fitted_mean(returns, convention)
    innovations = [(value - mean) ** 2 for value in returns]
    variance = innovations[0]
    for innovation in innovations[1:]:
        variance = decay * variance + (1.0 - decay) * innovation
    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError("EWMA variance is not strictly positive and finite")
    return variance, mean


def flat_variance_forecast(one_step_variance: float, horizon: int) -> tuple[float, ...]:
    if not math.isfinite(one_step_variance) or one_step_variance <= 0.0:
        raise ValueError("one-step variance must be strictly positive and finite")
    if horizon < 1:
        raise ValueError("horizon must contain at least one interval")
    return (one_step_variance,) * horizon


def realized_close_variance(future_returns: Sequence[float]) -> float:
    if not future_returns:
        raise ValueError("realized horizon must contain at least one return")
    result = math.fsum(value * value for value in future_returns)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("realized variance must be nonnegative and finite")
    return result


def annualize_cumulative_variance(
    cumulative_variance: float, *, horizon_calendar_days: int, calendar_days_per_year: float
) -> float:
    if not math.isfinite(cumulative_variance) or cumulative_variance < 0.0:
        raise ValueError("cumulative variance must be nonnegative and finite")
    if horizon_calendar_days < 1:
        raise ValueError("calendar horizon must be positive")
    if not math.isfinite(calendar_days_per_year) or calendar_days_per_year <= 0.0:
        raise ValueError("calendar days per year must be positive and finite")
    return cumulative_variance * calendar_days_per_year / horizon_calendar_days


def qlike(forecast_variance: float, realized_variance: float) -> float:
    if not math.isfinite(forecast_variance) or forecast_variance <= 0.0:
        raise ValueError("forecast variance must be strictly positive and finite")
    if not math.isfinite(realized_variance) or realized_variance < 0.0:
        raise ValueError("realized variance must be nonnegative and finite")
    return math.log(forecast_variance) + realized_variance / forecast_variance


def squared_variance_error(forecast_variance: float, realized_variance: float) -> float:
    difference = forecast_variance - realized_variance
    return difference * difference

