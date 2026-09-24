"""GARCH(1,1) fitting adapter backed by the pinned ``arch`` package."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np
from arch import arch_model


@dataclass(frozen=True)
class GarchFitResult:
    conditional_variances: tuple[float, ...]
    parameters_decimal: Mapping[str, float]
    parameters_upstream_percent: Mapping[str, float]
    convergence: Mapping[str, Any]
    log_likelihood: float
    aic: float
    bic: float


class GarchFitFailure(RuntimeError):
    def __init__(self, message: str, details: Mapping[str, Any] | None = None):
        self.details = dict(details or {})
        super().__init__(message)


def garch11_variance_forecast(
    *,
    omega: float,
    alpha: float,
    beta: float,
    last_residual_squared: float,
    last_conditional_variance: float,
    horizon: int,
) -> tuple[float, ...]:
    """Forecast a fixed-parameter GARCH(1,1) recursion for reference tests."""
    values = (omega, alpha, beta, last_residual_squared, last_conditional_variance)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("GARCH recursion inputs must be finite and nonnegative")
    if horizon < 1:
        raise ValueError("horizon must contain at least one interval")
    first = omega + alpha * last_residual_squared + beta * last_conditional_variance
    forecasts = [first]
    persistence = alpha + beta
    for _ in range(1, horizon):
        forecasts.append(omega + persistence * forecasts[-1])
    if any(not math.isfinite(value) or value <= 0.0 for value in forecasts):
        raise ValueError("GARCH recursion produced an invalid variance")
    return tuple(forecasts)


def _optimizer_details(result: Any) -> dict[str, Any]:
    optimization = result.optimization_result
    details: dict[str, Any] = {
        "convergence_flag": int(result.convergence_flag),
        "success": bool(optimization.success),
        "status": int(optimization.status),
        "message": str(optimization.message),
    }
    for name in ("nit", "nfev", "njev"):
        value = getattr(optimization, name, None)
        if value is not None:
            details[name] = int(value)
    objective = getattr(optimization, "fun", None)
    if objective is not None and math.isfinite(float(objective)):
        details["objective"] = float(objective)
    return details


def fit_garch11(
    returns: Sequence[float],
    *,
    horizon: int,
    mean: str,
    max_iterations: int,
    optimizer_tolerance: float,
) -> GarchFitResult:
    """Fit and analytically forecast GARCH(1,1) using ``arch``.

    Decimal log returns are scaled by 100 for numerical conditioning before
    fitting. Variances returned to callers are converted back to decimal-return
    squared units. No fallback estimator is used on a failed fit.
    """
    if horizon < 1:
        raise ValueError("horizon must contain at least one interval")
    values = np.asarray(tuple(returns), dtype=np.float64)
    if values.ndim != 1 or values.size < 2 or not np.all(np.isfinite(values)):
        raise ValueError("GARCH returns must be a finite one-dimensional sequence")
    upstream_mean = {"zero": "Zero", "constant": "Constant"}.get(mean)
    if upstream_mean is None:
        raise ValueError("mean convention must be zero or constant")

    scaled = values * 100.0
    model = arch_model(
        scaled,
        mean=upstream_mean,
        vol="GARCH",
        p=1,
        o=0,
        q=1,
        power=2.0,
        dist="normal",
        rescale=False,
    )
    try:
        result = model.fit(
            disp="off",
            update_freq=0,
            show_warning=False,
            tol=optimizer_tolerance,
            options={"maxiter": max_iterations},
        )
    except Exception as exc:  # upstream exposes several optimizer exception types
        raise GarchFitFailure(f"arch GARCH fit raised {type(exc).__name__}: {exc}") from exc

    convergence = _optimizer_details(result)
    if result.convergence_flag != 0 or not result.optimization_result.success:
        raise GarchFitFailure("arch GARCH optimizer did not converge", convergence)

    try:
        forecast = result.forecast(horizon=horizon, method="analytic", reindex=False)
        upstream_variances = np.asarray(forecast.residual_variance.iloc[-1], dtype=np.float64)
    except Exception as exc:
        raise GarchFitFailure(f"arch GARCH forecast raised {type(exc).__name__}: {exc}", convergence) from exc
    variances = upstream_variances / 10_000.0
    if variances.size != horizon or not np.all(np.isfinite(variances)) or np.any(variances <= 0.0):
        raise GarchFitFailure("arch GARCH forecast returned invalid conditional variances", convergence)

    upstream_parameters = {str(name): float(value) for name, value in result.params.items()}
    decimal_parameters: dict[str, float] = {}
    for name, value in upstream_parameters.items():
        if name == "mu":
            decimal_parameters[name] = value / 100.0
        elif name == "omega":
            decimal_parameters[name] = value / 10_000.0
        else:
            decimal_parameters[name] = value
    if any(not math.isfinite(value) for value in decimal_parameters.values()):
        raise GarchFitFailure("arch GARCH fit returned nonfinite parameters", convergence)

    return GarchFitResult(
        conditional_variances=tuple(float(value) for value in variances),
        parameters_decimal=decimal_parameters,
        parameters_upstream_percent=upstream_parameters,
        convergence=convergence,
        log_likelihood=float(result.loglikelihood),
        aic=float(result.aic),
        bic=float(result.bic),
    )

