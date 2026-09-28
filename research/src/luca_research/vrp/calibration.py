"""Bounded VIX-term-structure calibration for fixed HN-GARCSH dynamics."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from scipy.optimize import least_squares

from .model import (
    MAX_HORIZON_TRADING_DAYS,
    PhysicalDynamics,
    RiskPrices,
    VariancePremiumReport,
    cumulative_variance_premium,
    risk_neutral_dynamics,
    vix_term_value_percent,
)


MAX_VIX_TERM_OBSERVATIONS = 32
MAX_CALIBRATION_EVALUATIONS = 2_000
_STATIONARITY_MARGIN = 1.0e-10


@dataclass(frozen=True)
class VixTermObservation:
    """One same-cutoff VIX term observation in percentage points."""

    label: str
    maturity_trading_days: int
    value_percent: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label or len(self.label) > 128:
            raise ValueError("observation label must contain 1 to 128 characters")
        if (
            isinstance(self.maturity_trading_days, bool)
            or not isinstance(self.maturity_trading_days, int)
            or not 1 <= self.maturity_trading_days <= MAX_HORIZON_TRADING_DAYS
        ):
            raise ValueError(
                "maturity_trading_days must be a positive integer within the model horizon cap"
            )
        if not math.isfinite(self.value_percent) or self.value_percent <= 0.0:
            raise ValueError("value_percent must be positive and finite")
        if not math.isfinite(self.weight) or self.weight <= 0.0:
            raise ValueError("weight must be positive and finite")


@dataclass(frozen=True)
class CalibrationConfig:
    """Deterministic bounds and stopping rules for the one-parameter fit."""

    lambda2_lower: float
    lambda2_upper: float
    lambda2_initial: float
    max_evaluations: int = 500
    tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        for name in ("lambda2_lower", "lambda2_upper", "lambda2_initial", "tolerance"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.lambda2_lower >= self.lambda2_upper:
            raise ValueError("lambda2_lower must be less than lambda2_upper")
        if not self.lambda2_lower <= self.lambda2_initial <= self.lambda2_upper:
            raise ValueError("lambda2_initial must lie within the requested bounds")
        if (
            isinstance(self.max_evaluations, bool)
            or not isinstance(self.max_evaluations, int)
            or not 1 <= self.max_evaluations <= MAX_CALIBRATION_EVALUATIONS
        ):
            raise ValueError(
                f"max_evaluations must be an integer from 1 to {MAX_CALIBRATION_EVALUATIONS}"
            )
        if not 1.0e-14 <= self.tolerance <= 1.0e-3:
            raise ValueError("tolerance must be between 1e-14 and 1e-3")


@dataclass(frozen=True)
class TermFit:
    label: str
    maturity_trading_days: int
    observed_vix_percent: float
    model_vix_percent: float
    scaled_error: float
    weight: float


@dataclass(frozen=True)
class FitDiagnostics:
    objective_name: str
    objective_value: float
    converged: bool
    optimizer: str
    status_code: int
    message: str
    function_evaluations: int
    jacobian_evaluations: int | None
    optimality: float
    requested_lambda2_bounds: tuple[float, float]
    effective_lambda2_bounds: tuple[float, float]
    tolerance: float


@dataclass(frozen=True)
class CalibrationResult:
    """Numerical fit with fixed structure/state and a calibrated lambda2."""

    fixed_physical: PhysicalDynamics
    fixed_lambda1: float
    fixed_h_next: float
    calibrated_risk_prices: RiskPrices
    risk_neutral_persistence: float
    risk_neutral_long_run_variance: float
    observationally_equivalent_lambda2: float
    identification_branch: str
    term_fits: tuple[TermFit, ...]
    fit: FitDiagnostics
    variance_premium: VariancePremiumReport
    limitations: tuple[str, ...]


def _validate_observations(
    observations: Sequence[VixTermObservation],
) -> tuple[VixTermObservation, ...]:
    values = tuple(observations)
    if not 2 <= len(values) <= MAX_VIX_TERM_OBSERVATIONS:
        raise ValueError(
            f"VIX term structure must contain 2 to {MAX_VIX_TERM_OBSERVATIONS} observations"
        )
    maturities = [item.maturity_trading_days for item in values]
    if len(set(maturities)) != len(maturities):
        raise ValueError("VIX term maturities must be unique")
    return tuple(sorted(values, key=lambda item: item.maturity_trading_days))


def _effective_bounds(
    physical: PhysicalDynamics,
    fixed_lambda1: float,
    config: CalibrationConfig,
) -> tuple[float, float]:
    gamma1_star = physical.gamma1 + fixed_lambda1 + 0.5
    fixed_persistence = physical.beta + physical.alpha * gamma1_star**2
    remaining = 1.0 - _STATIONARITY_MARGIN - fixed_persistence
    if remaining <= 0.0:
        raise ValueError("fixed return-risk parameters leave no admissible lambda2")

    maximum_absolute_gamma2_star = math.sqrt(remaining / physical.rho)
    admissible_lower = -physical.gamma2 - maximum_absolute_gamma2_star
    admissible_upper = -physical.gamma2 + maximum_absolute_gamma2_star
    lower = max(config.lambda2_lower, admissible_lower)
    upper = min(config.lambda2_upper, admissible_upper)
    if lower >= upper:
        raise ValueError("requested lambda2 bounds contain no risk-neutral stationary values")

    turning_point = -physical.gamma2
    if lower < turning_point < upper:
        raise ValueError(
            "lambda2 bounds cross -gamma2; choose one identification branch because "
            "the VIX term objective depends on (gamma2 + lambda2)^2"
        )
    return lower, upper


def calibrate_vix_term_structure(
    physical: PhysicalDynamics,
    *,
    fixed_lambda1: float,
    h_next: float,
    observations: Sequence[VixTermObservation],
    report_horizon_trading_days: int,
    config: CalibrationConfig,
) -> CalibrationResult:
    """Fit constant ``lambda2`` with all structural quantities held fixed.

    The residual for each term is Equation (30),
    ``(VIX_market - VIX_model) / (100*sqrt(252))``.  ``weight`` may carry a
    fixed inverse residual variance, yielding the parameter-dependent part of
    Equation (31).  This is not the full joint likelihood in Equation (32): no
    returns likelihood or estimated residual variance is silently added.
    """

    if not math.isfinite(fixed_lambda1):
        raise ValueError("fixed_lambda1 must be finite")
    if not math.isfinite(h_next) or h_next <= 0.0:
        raise ValueError("h_next must be positive and finite")
    ordered_observations = _validate_observations(observations)
    lower, upper = _effective_bounds(physical, fixed_lambda1, config)
    initial = min(max(config.lambda2_initial, lower), upper)
    scale = 100.0 * math.sqrt(252.0)

    def residuals(candidate: np.ndarray) -> np.ndarray:
        risk_prices = RiskPrices(lambda1=fixed_lambda1, lambda2=float(candidate[0]))
        return np.asarray(
            [
                math.sqrt(observation.weight)
                * (
                    observation.value_percent
                    - vix_term_value_percent(
                        h_next,
                        observation.maturity_trading_days,
                        physical,
                        risk_prices,
                    )
                )
                / scale
                for observation in ordered_observations
            ],
            dtype=np.float64,
        )

    optimization = least_squares(
        residuals,
        np.asarray([initial], dtype=np.float64),
        bounds=(
            np.asarray([lower], dtype=np.float64),
            np.asarray([upper], dtype=np.float64),
        ),
        ftol=config.tolerance,
        xtol=config.tolerance,
        gtol=config.tolerance,
        max_nfev=config.max_evaluations,
        method="trf",
    )
    calibrated_lambda2 = float(optimization.x[0])
    risk_prices = RiskPrices(lambda1=fixed_lambda1, lambda2=calibrated_lambda2)
    transformed = risk_neutral_dynamics(physical, risk_prices)

    term_fits = tuple(
        TermFit(
            label=observation.label,
            maturity_trading_days=observation.maturity_trading_days,
            observed_vix_percent=observation.value_percent,
            model_vix_percent=(model_value := vix_term_value_percent(
                h_next,
                observation.maturity_trading_days,
                physical,
                risk_prices,
            )),
            scaled_error=(observation.value_percent - model_value) / scale,
            weight=observation.weight,
        )
        for observation in ordered_observations
    )
    objective_value = math.fsum(
        item.weight * item.scaled_error**2 for item in term_fits
    )
    converged = bool(optimization.success) and transformed.persistence <= 1.0 - _STATIONARITY_MARGIN
    branch = (
        "gamma2_plus_lambda2_nonnegative"
        if physical.gamma2 + calibrated_lambda2 >= 0.0
        else "gamma2_plus_lambda2_nonpositive"
    )

    return CalibrationResult(
        fixed_physical=physical,
        fixed_lambda1=fixed_lambda1,
        fixed_h_next=h_next,
        calibrated_risk_prices=risk_prices,
        risk_neutral_persistence=transformed.persistence,
        risk_neutral_long_run_variance=transformed.long_run_variance,
        observationally_equivalent_lambda2=-2.0 * physical.gamma2 - calibrated_lambda2,
        identification_branch=branch,
        term_fits=term_fits,
        fit=FitDiagnostics(
            objective_name="weighted_sum_squared_equation_30_scaled_vix_errors",
            objective_value=objective_value,
            converged=converged,
            optimizer="scipy.optimize.least_squares(method=trf)",
            status_code=int(optimization.status),
            message=str(optimization.message),
            function_evaluations=int(optimization.nfev),
            jacobian_evaluations=(
                int(optimization.njev) if optimization.njev is not None else None
            ),
            optimality=float(optimization.optimality),
            requested_lambda2_bounds=(config.lambda2_lower, config.lambda2_upper),
            effective_lambda2_bounds=(lower, upper),
            tolerance=config.tolerance,
        ),
        variance_premium=cumulative_variance_premium(
            h_next,
            report_horizon_trading_days,
            physical,
            risk_prices,
        ),
        limitations=(
            "The physical parameters, lambda1, and filtered h_next state are fixed "
            "inputs; this fit estimates only constant lambda2.",
            "A VIX term structure identifies risk-neutral persistence, not the sign "
            "of gamma2 + lambda2; the selected bounds choose one branch.",
            "The symmetric observationally equivalent lambda2 produces the same "
            "VIX term structure when otherwise admissible.",
            "This cross-sectional weighted least-squares objective is not the "
            "paper's full returns-plus-VIX joint likelihood.",
            "No parameter uncertainty, dynamic premium, regime classifier, or profitability inference is produced.",
        ),
    )
