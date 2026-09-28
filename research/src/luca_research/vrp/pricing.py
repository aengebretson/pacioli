"""Controlled Monte Carlo pricing under the documented risk-neutral dynamics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from .model import (
    MAX_HORIZON_TRADING_DAYS,
    PhysicalDynamics,
    RiskPrices,
    cumulative_variance_premium,
    risk_neutral_dynamics,
)


MAX_PRICING_PATHS = 500_000
MAX_PRICING_HORIZON = min(MAX_HORIZON_TRADING_DAYS, 756)
_NORMAL_975 = 1.959963984540054


@dataclass(frozen=True)
class EuropeanOptionInputs:
    """Forward-style inputs for one European call/put pair."""

    contract_id: str
    forward: float
    strike: float
    discount_factor: float
    horizon_trading_days: int
    settlement: str
    contract_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.contract_id, str) or not self.contract_id:
            raise ValueError("contract_id must be nonempty")
        for name in ("forward", "strike", "discount_factor", "contract_multiplier"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if self.discount_factor > 1.5:
            raise ValueError("discount_factor exceeds the bounded research domain")
        if (
            isinstance(self.horizon_trading_days, bool)
            or not isinstance(self.horizon_trading_days, int)
            or not 1 <= self.horizon_trading_days <= MAX_PRICING_HORIZON
        ):
            raise ValueError(
                f"horizon_trading_days must be an integer from 1 to {MAX_PRICING_HORIZON}"
            )
        if self.settlement not in {"cash", "physical"}:
            raise ValueError("settlement must be 'cash' or 'physical'")


@dataclass(frozen=True)
class MonteCarloPricingConfig:
    path_counts: tuple[int, ...] = (20_000, 80_000)
    seed: int = 101

    def __post_init__(self) -> None:
        if not self.path_counts:
            raise ValueError("path_counts must be nonempty")
        previous = 0
        for count in self.path_counts:
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count < 2_000
                or count > MAX_PRICING_PATHS
                or count % 2 != 0
                or count <= previous
            ):
                raise ValueError(
                    "path_counts must be strictly increasing even integers from 2,000 "
                    f"to {MAX_PRICING_PATHS}"
                )
            previous = count
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")


@dataclass(frozen=True)
class PriceStatistic:
    value: float
    standard_error: float
    confidence_interval_95: tuple[float, float]


@dataclass(frozen=True)
class PricingCheckpoint:
    path_count: int
    call: PriceStatistic
    put: PriceStatistic
    straddle: PriceStatistic
    discounted_terminal_mean: PriceStatistic
    put_call_parity_target: float
    put_call_parity_residual: float
    put_call_parity_residual_standard_error: float
    put_call_parity_residual_z_score: float
    martingale_forward_residual: float
    martingale_forward_residual_standard_error: float


@dataclass(frozen=True)
class OptionPricingResult:
    inputs: EuropeanOptionInputs
    config: MonteCarloPricingConfig
    h_next: float
    checkpoints: tuple[PricingCheckpoint, ...]
    approximate_black_benchmark: dict[str, float | str]
    method: str
    random_generator: str
    antithetic_variates: bool
    limitations: tuple[str, ...]

    @property
    def final(self) -> PricingCheckpoint:
        return self.checkpoints[-1]


def _antithetic_statistic(values: np.ndarray) -> PriceStatistic:
    if values.size % 2:
        raise ValueError("antithetic samples must contain complete pairs")
    pair_means = values.reshape(-1, 2).mean(axis=1)
    value = float(np.mean(values))
    standard_error = float(
        np.std(pair_means, ddof=1) / math.sqrt(int(pair_means.size))
    )
    half_width = _NORMAL_975 * standard_error
    return PriceStatistic(
        value=value,
        standard_error=standard_error,
        confidence_interval_95=(value - half_width, value + half_width),
    )


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _black_benchmark(
    inputs: EuropeanOptionInputs,
    total_variance: float,
) -> dict[str, float | str]:
    if not math.isfinite(total_variance) or total_variance <= 0.0:
        raise ValueError("total_variance must be positive and finite")
    root_variance = math.sqrt(total_variance)
    d1 = math.log(inputs.forward / inputs.strike) / root_variance + 0.5 * root_variance
    d2 = d1 - root_variance
    call = inputs.discount_factor * (
        inputs.forward * _normal_cdf(d1) - inputs.strike * _normal_cdf(d2)
    )
    put = call - inputs.discount_factor * (inputs.forward - inputs.strike)
    return {
        "label": "approximate_lognormal_expected_cumulative_variance_benchmark_not_model_price",
        "total_variance": total_variance,
        "call": call,
        "put": put,
        "straddle": call + put,
    }


def price_european_options_monte_carlo(
    physical: PhysicalDynamics,
    risk_prices: RiskPrices,
    *,
    h_next: float,
    inputs: EuropeanOptionInputs,
    config: MonteCarloPricingConfig = MonteCarloPricingConfig(),
) -> OptionPricingResult:
    """Price a European call, put, and straddle by direct Q simulation.

    ``forward`` is the deterministic-carry forward for the option maturity.
    Each path evolves ``S_T/F_0`` with increments ``-h/2 + sqrt(h) z*`` and
    evolves variance with Equation (6), including independently simulated
    auxiliary variance shocks.  The same terminal paths price all payoffs.
    """

    if not math.isfinite(h_next) or h_next <= 0.0:
        raise ValueError("h_next must be positive and finite")
    transformed = risk_neutral_dynamics(physical, risk_prices)
    maximum_paths = config.path_counts[-1]
    half_paths = maximum_paths // 2
    generator = np.random.Generator(np.random.PCG64(config.seed))
    variance = np.full(maximum_paths, h_next, dtype=np.float64)
    log_forward_ratio = np.zeros(maximum_paths, dtype=np.float64)

    for _ in range(inputs.horizon_trading_days):
        return_half = generator.standard_normal(half_paths)
        return_shocks = np.stack((return_half, -return_half), axis=1).reshape(-1)
        variance_half = generator.standard_normal((half_paths, physical.k))
        variance_shocks = np.stack((variance_half, -variance_half), axis=1).reshape(
            maximum_paths, physical.k
        )
        roots = np.sqrt(variance)
        log_forward_ratio += -0.5 * variance + roots * return_shocks
        return_component = physical.alpha * (
            return_shocks - transformed.gamma1_star * roots
        ) ** 2
        variance_component = (physical.rho / physical.k) * np.sum(
            (variance_shocks - transformed.gamma2_star * roots[:, None]) ** 2,
            axis=1,
        )
        variance = (
            physical.omega
            + physical.beta * variance
            + return_component
            + variance_component
        )
        if (
            not np.all(np.isfinite(variance))
            or np.any(variance <= 0.0)
            or not np.all(np.isfinite(log_forward_ratio))
        ):
            raise FloatingPointError("risk-neutral simulation left the finite domain")

    if np.any(log_forward_ratio > 700.0):
        raise FloatingPointError("terminal price exponent exceeds the finite domain")
    terminal = inputs.forward * np.exp(log_forward_ratio)
    checkpoints: list[PricingCheckpoint] = []
    parity_target = inputs.discount_factor * (inputs.forward - inputs.strike)
    for path_count in config.path_counts:
        selected = terminal[:path_count]
        call_payoffs = (
            inputs.discount_factor
            * np.maximum(selected - inputs.strike, 0.0)
            * inputs.contract_multiplier
        )
        put_payoffs = (
            inputs.discount_factor
            * np.maximum(inputs.strike - selected, 0.0)
            * inputs.contract_multiplier
        )
        terminal_discounted = (
            inputs.discount_factor * selected * inputs.contract_multiplier
        )
        call = _antithetic_statistic(call_payoffs)
        put = _antithetic_statistic(put_payoffs)
        straddle = _antithetic_statistic(call_payoffs + put_payoffs)
        terminal_statistic = _antithetic_statistic(terminal_discounted)
        scaled_parity_target = parity_target * inputs.contract_multiplier
        expected_discounted_forward = (
            inputs.discount_factor * inputs.forward * inputs.contract_multiplier
        )
        checkpoints.append(
            PricingCheckpoint(
                path_count=path_count,
                call=call,
                put=put,
                straddle=straddle,
                discounted_terminal_mean=terminal_statistic,
                put_call_parity_target=scaled_parity_target,
                put_call_parity_residual=call.value - put.value - scaled_parity_target,
                put_call_parity_residual_standard_error=terminal_statistic.standard_error,
                put_call_parity_residual_z_score=(
                    (call.value - put.value - scaled_parity_target)
                    / terminal_statistic.standard_error
                    if terminal_statistic.standard_error > 0.0
                    else 0.0
                ),
                martingale_forward_residual=(
                    terminal_statistic.value - expected_discounted_forward
                ),
                martingale_forward_residual_standard_error=terminal_statistic.standard_error,
            )
        )

    expected_variance = cumulative_variance_premium(
        h_next,
        inputs.horizon_trading_days,
        physical,
        risk_prices,
    ).risk_neutral.cumulative_variance
    black = _black_benchmark(inputs, expected_variance)
    if inputs.contract_multiplier != 1.0:
        for name in ("call", "put", "straddle"):
            black[name] = float(black[name]) * inputs.contract_multiplier

    return OptionPricingResult(
        inputs=inputs,
        config=config,
        h_next=h_next,
        checkpoints=tuple(checkpoints),
        approximate_black_benchmark=black,
        method="direct_antithetic_monte_carlo_under_documented_Q_dynamics",
        random_generator="numpy.random.PCG64",
        antithetic_variates=True,
        limitations=(
            "Monte Carlo confidence intervals describe sampling error only, not parameter, state, contract, forward, or rate uncertainty.",
            "The pricing calculation conditions on the supplied h_next point state; it does not integrate the physical filter's state distribution.",
            "The Black values are an approximate benchmark using expected cumulative variance, not a price from the GARCSH terminal distribution.",
        ),
    )


def option_pricing_result_asdict(result: OptionPricingResult) -> dict[str, object]:
    """Return a JSON-compatible representation without changing numeric values."""

    value = asdict(result)
    value["final"] = asdict(result.final)
    return value
