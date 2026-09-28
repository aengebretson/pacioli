"""Pure HN-GARCSH dynamics and horizon-matched variance calculations.

The equations implemented here are from Escobar-Anel, Stentoft, and Ye
(2026), DOI 10.1002/fut.70132.  Equation numbers in docstrings refer to that
paper.  This module deliberately does not infer an unpublished pricing-kernel
formula; it implements the physical and risk-neutral dynamics printed in the
paper.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence


MODEL_VERSION = "hn-garcsh-direct-v1"
TRADING_DAYS_PER_YEAR = 252.0
MAX_HORIZON_TRADING_DAYS = 2_520

Measure = Literal["P", "Q"]


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_positive_variance(name: str, value: float) -> None:
    _require_finite(name, value)
    if value <= 0.0:
        raise ValueError(f"{name} must be strictly positive")


@dataclass(frozen=True)
class PhysicalDynamics:
    """Fixed parameters of the physical variance dynamics in Equation (5).

    ``k=1`` is the literal two-Gaussian-shock model: one return shock and one
    variance shock.  Larger integer ``k`` values retain the paper's
    non-central-chi-squared generalization.
    """

    omega: float
    beta: float
    alpha: float
    gamma1: float
    rho: float
    gamma2: float
    k: int = 1

    def __post_init__(self) -> None:
        for name in ("omega", "beta", "alpha", "gamma1", "rho", "gamma2"):
            _require_finite(name, float(getattr(self, name)))
        if self.omega < 0.0 or self.beta < 0.0:
            raise ValueError("omega and beta must be nonnegative")
        if self.alpha <= 0.0 or self.rho <= 0.0:
            raise ValueError("the direct two-shock model requires alpha and rho to be positive")
        if isinstance(self.k, bool) or not isinstance(self.k, int) or self.k < 1:
            raise ValueError("k must be a positive integer")
        if self.persistence >= 1.0:
            raise ValueError("physical persistence must be less than one")

    @property
    def innovation_intercept(self) -> float:
        """The expectation intercept ``omega + alpha + rho`` in Equation (7)."""

        return self.omega + self.alpha + self.rho

    @property
    def persistence(self) -> float:
        """Physical persistence ``p`` from Equation (9)."""

        return self.beta + self.alpha * self.gamma1**2 + self.rho * self.gamma2**2

    @property
    def long_run_variance(self) -> float:
        """Physical long-run daily variance ``mu`` from Equation (11)."""

        return self.innovation_intercept / (1.0 - self.persistence)


@dataclass(frozen=True)
class RiskPrices:
    """Constant risk prices used by the published P-to-Q transformation.

    ``lambda1`` is also the coefficient of ``h_t`` in the physical conditional
    log-return mean in Equation (1).  ``lambda2`` prices the independent
    variance shock.  They are fixed scalars in this implementation; there is no
    regime or dynamic-premium extension.
    """

    lambda1: float
    lambda2: float

    def __post_init__(self) -> None:
        _require_finite("lambda1", self.lambda1)
        _require_finite("lambda2", self.lambda2)


@dataclass(frozen=True)
class RiskNeutralDynamics:
    """Transformed quantities from Equations (6), (8), (10), and (12)."""

    gamma1_star: float
    gamma2_star: float
    persistence: float
    long_run_variance: float


@dataclass(frozen=True)
class VarianceMeasureReport:
    measure: Measure
    interval_variances: tuple[float, ...]
    cumulative_variance: float
    average_daily_variance: float
    year_fraction: float
    annualized_volatility: float


@dataclass(frozen=True)
class VariancePremiumReport:
    horizon_trading_days: int
    physical: VarianceMeasureReport
    risk_neutral: VarianceMeasureReport
    vrp_q_minus_p: float


def risk_neutral_dynamics(
    physical: PhysicalDynamics,
    risk_prices: RiskPrices,
) -> RiskNeutralDynamics:
    """Apply the explicit transformation printed after Equation (6).

    ``gamma1* = gamma1 + lambda1 + 1/2`` and
    ``gamma2* = gamma2 + lambda2``.  The finite-mean restriction ``p* < 1``
    makes Equation (12) and the VIX term structure in Equation (20) well
    defined.  Nonnegative variance coefficients and ``p,p* < 1`` are the
    implementation's sufficient numerical constraints, not a claim that the
    paper states a complete admissibility theorem.
    """

    gamma1_star = physical.gamma1 + risk_prices.lambda1 + 0.5
    gamma2_star = physical.gamma2 + risk_prices.lambda2
    persistence = (
        physical.beta
        + physical.alpha * gamma1_star**2
        + physical.rho * gamma2_star**2
    )
    if not math.isfinite(persistence) or persistence >= 1.0:
        raise ValueError("risk-neutral persistence must be finite and less than one")
    long_run_variance = physical.innovation_intercept / (1.0 - persistence)
    if not math.isfinite(long_run_variance) or long_run_variance <= 0.0:
        raise ValueError("risk-neutral long-run variance must be positive and finite")
    return RiskNeutralDynamics(
        gamma1_star=gamma1_star,
        gamma2_star=gamma2_star,
        persistence=persistence,
        long_run_variance=long_run_variance,
    )


def physical_variance_update(
    previous_variance: float,
    return_shock: float,
    variance_shocks: Sequence[float],
    physical: PhysicalDynamics,
) -> float:
    """Evaluate the pathwise physical variance recursion in Equation (5)."""

    _require_positive_variance("previous_variance", previous_variance)
    _require_finite("return_shock", return_shock)
    if len(variance_shocks) != physical.k:
        raise ValueError(f"variance_shocks must contain exactly k={physical.k} values")
    for index, shock in enumerate(variance_shocks):
        _require_finite(f"variance_shocks[{index}]", float(shock))

    root_variance = math.sqrt(previous_variance)
    return_component = physical.alpha * (
        return_shock - physical.gamma1 * root_variance
    ) ** 2
    variance_component = (physical.rho / physical.k) * math.fsum(
        (shock - physical.gamma2 * root_variance) ** 2
        for shock in variance_shocks
    )
    updated = (
        physical.omega
        + physical.beta * previous_variance
        + return_component
        + variance_component
    )
    _require_positive_variance("updated_variance", updated)
    return updated


def risk_neutral_variance_update(
    previous_variance: float,
    return_shock_star: float,
    variance_shocks_star: Sequence[float],
    physical: PhysicalDynamics,
    risk_prices: RiskPrices,
) -> float:
    """Evaluate the pathwise risk-neutral variance recursion in Equation (6)."""

    transformed = risk_neutral_dynamics(physical, risk_prices)
    _require_positive_variance("previous_variance", previous_variance)
    _require_finite("return_shock_star", return_shock_star)
    if len(variance_shocks_star) != physical.k:
        raise ValueError(f"variance_shocks_star must contain exactly k={physical.k} values")
    for index, shock in enumerate(variance_shocks_star):
        _require_finite(f"variance_shocks_star[{index}]", float(shock))

    root_variance = math.sqrt(previous_variance)
    return_component = physical.alpha * (
        return_shock_star - transformed.gamma1_star * root_variance
    ) ** 2
    variance_component = (physical.rho / physical.k) * math.fsum(
        (shock - transformed.gamma2_star * root_variance) ** 2
        for shock in variance_shocks_star
    )
    updated = (
        physical.omega
        + physical.beta * previous_variance
        + return_component
        + variance_component
    )
    _require_positive_variance("updated_variance", updated)
    return updated


def log_return_increment(
    risk_free_log_rate: float,
    variance: float,
    shock: float,
    risk_prices: RiskPrices,
    *,
    measure: Measure,
) -> float:
    """Evaluate the log-return increment under Equation (1) or Equation (3).

    Inputs are per model period.  Under P the conditional drift is
    ``r + lambda1*h``; under Q it is ``r - h/2``.
    """

    _require_finite("risk_free_log_rate", risk_free_log_rate)
    _require_positive_variance("variance", variance)
    _require_finite("shock", shock)
    if measure == "P":
        drift = risk_free_log_rate + risk_prices.lambda1 * variance
    elif measure == "Q":
        drift = risk_free_log_rate - 0.5 * variance
    else:
        raise ValueError("measure must be 'P' or 'Q'")
    return drift + math.sqrt(variance) * shock


def conditional_expected_variance(
    current_variance: float,
    physical: PhysicalDynamics,
    *,
    measure: Measure,
    risk_prices: RiskPrices | None = None,
) -> float:
    """Evaluate the affine one-step expectation in Equation (7) or (8)."""

    _require_positive_variance("current_variance", current_variance)
    if measure == "P":
        persistence = physical.persistence
    elif measure == "Q":
        if risk_prices is None:
            raise ValueError("risk_prices are required for measure='Q'")
        persistence = risk_neutral_dynamics(physical, risk_prices).persistence
    else:
        raise ValueError("measure must be 'P' or 'Q'")
    expectation = physical.innovation_intercept + persistence * current_variance
    _require_positive_variance("conditional_expected_variance", expectation)
    return expectation


def expected_variance_path(
    h_next: float,
    horizon_trading_days: int,
    physical: PhysicalDynamics,
    *,
    measure: Measure,
    risk_prices: RiskPrices | None = None,
) -> tuple[float, ...]:
    """Return ``E_t[h_{t+n}]`` for ``n=1..horizon``.

    ``h_next`` is the already filtered state ``h_{t+1}``, matching Equation
    (20).  It is not re-estimated or advanced using future information.
    """

    _require_positive_variance("h_next", h_next)
    if (
        isinstance(horizon_trading_days, bool)
        or not isinstance(horizon_trading_days, int)
        or not 1 <= horizon_trading_days <= MAX_HORIZON_TRADING_DAYS
    ):
        raise ValueError(
            f"horizon_trading_days must be an integer from 1 to {MAX_HORIZON_TRADING_DAYS}"
        )

    path = [h_next]
    for _ in range(1, horizon_trading_days):
        path.append(
            conditional_expected_variance(
                path[-1],
                physical,
                measure=measure,
                risk_prices=risk_prices,
            )
        )
    return tuple(path)


def vix_term_value_percent(
    h_next: float,
    maturity_trading_days: int,
    physical: PhysicalDynamics,
    risk_prices: RiskPrices,
) -> float:
    """Return the Equation (19)-(20) VIX proxy in percentage points."""

    path = expected_variance_path(
        h_next,
        maturity_trading_days,
        physical,
        measure="Q",
        risk_prices=risk_prices,
    )
    average_daily_variance = math.fsum(path) / maturity_trading_days
    return 100.0 * math.sqrt(TRADING_DAYS_PER_YEAR * average_daily_variance)


def _measure_report(measure: Measure, path: tuple[float, ...]) -> VarianceMeasureReport:
    cumulative = math.fsum(path)
    horizon = len(path)
    average_daily = cumulative / horizon
    year_fraction = horizon / TRADING_DAYS_PER_YEAR
    annualized_volatility = math.sqrt(cumulative / year_fraction)
    return VarianceMeasureReport(
        measure=measure,
        interval_variances=path,
        cumulative_variance=cumulative,
        average_daily_variance=average_daily,
        year_fraction=year_fraction,
        annualized_volatility=annualized_volatility,
    )


def cumulative_variance_premium(
    h_next: float,
    horizon_trading_days: int,
    physical: PhysicalDynamics,
    risk_prices: RiskPrices,
) -> VariancePremiumReport:
    """Return horizon-matched ``W_P``, ``W_Q``, and ``W_Q - W_P``.

    The returned sign follows LUCA's shared artifact contract.  It is the
    opposite of the paper's one-step ``P - Q`` convention in Equation (13).
    """

    p_path = expected_variance_path(
        h_next,
        horizon_trading_days,
        physical,
        measure="P",
    )
    q_path = expected_variance_path(
        h_next,
        horizon_trading_days,
        physical,
        measure="Q",
        risk_prices=risk_prices,
    )
    p_report = _measure_report("P", p_path)
    q_report = _measure_report("Q", q_path)
    return VariancePremiumReport(
        horizon_trading_days=horizon_trading_days,
        physical=p_report,
        risk_neutral=q_report,
        vrp_q_minus_p=q_report.cumulative_variance - p_report.cumulative_variance,
    )
