"""Bounded simulated-likelihood estimation of the physical GARCSH model.

The independent variance innovation is latent when only close-to-close returns
are observed.  This module integrates it with a seeded bootstrap particle
filter.  It never substitutes the innovation's conditional expectation into
the state recursion.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np
from scipy.optimize import minimize

from .model import PhysicalDynamics


MAX_RETURN_OBSERVATIONS = 10_000
MAX_PARTICLES = 2_048
MAX_PHYSICAL_EVALUATIONS = 2_000
_LOG_2PI = math.log(2.0 * math.pi)


@dataclass(frozen=True)
class PhysicalEstimationConfig:
    """Resource bounds and reproducibility controls for the particle fit."""

    particle_count: int = 96
    seed: int = 17
    max_evaluations: int = 400
    tolerance: float = 1.0e-5
    minimum_persistence: float = 0.20
    maximum_persistence: float = 0.999
    minimum_long_run_variance: float = 1.0e-7
    maximum_long_run_variance: float = 1.0e-2
    lambda1_lower: float = -20.0
    lambda1_upper: float = 20.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.particle_count, bool)
            or not isinstance(self.particle_count, int)
            or not 16 <= self.particle_count <= MAX_PARTICLES
        ):
            raise ValueError(f"particle_count must be an integer from 16 to {MAX_PARTICLES}")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if (
            isinstance(self.max_evaluations, bool)
            or not isinstance(self.max_evaluations, int)
            or not 20 <= self.max_evaluations <= MAX_PHYSICAL_EVALUATIONS
        ):
            raise ValueError(
                f"max_evaluations must be an integer from 20 to {MAX_PHYSICAL_EVALUATIONS}"
            )
        for name in (
            "tolerance",
            "minimum_persistence",
            "maximum_persistence",
            "minimum_long_run_variance",
            "maximum_long_run_variance",
            "lambda1_lower",
            "lambda1_upper",
        ):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if not 1.0e-10 <= self.tolerance <= 1.0e-2:
            raise ValueError("tolerance must be between 1e-10 and 1e-2")
        if not 0.0 < self.minimum_persistence < self.maximum_persistence < 1.0:
            raise ValueError("persistence bounds must satisfy 0 < lower < upper < 1")
        if not (
            0.0
            < self.minimum_long_run_variance
            < self.maximum_long_run_variance
        ):
            raise ValueError("long-run variance bounds must be positive and ordered")
        if self.lambda1_lower >= self.lambda1_upper:
            raise ValueError("lambda1 bounds must be ordered")


@dataclass(frozen=True)
class FilterDiagnostics:
    observation_count: int
    log_likelihood: float
    average_log_likelihood: float
    predictive_variances: tuple[float, ...]
    standardized_residuals: tuple[float, ...]
    log_likelihood_contributions: tuple[float, ...]
    h_next_mean: float
    h_next_median: float
    h_next_p05: float
    h_next_p95: float
    particle_count: int
    seed: int
    latent_variance_shock_treatment: str


@dataclass(frozen=True)
class PhysicalFitDiagnostics:
    objective_name: str
    objective_value: float
    converged: bool
    optimizer: str
    status_code: int
    message: str
    function_evaluations: int
    iterations: int
    tolerance: float
    parameterization: str
    gamma1_branch: str
    gamma2_identification_branch: str
    likelihood_replication_seeds: tuple[int, ...]
    likelihood_replication_average_log_likelihoods: tuple[float, ...]
    likelihood_replication_standard_deviation: float


@dataclass(frozen=True)
class PhysicalEstimationResult:
    physical: PhysicalDynamics
    lambda1: float
    fit: PhysicalFitDiagnostics
    filter: FilterDiagnostics
    config: PhysicalEstimationConfig
    limitations: tuple[str, ...]


def _validated_returns(values: Sequence[float]) -> np.ndarray:
    result = np.asarray(tuple(values), dtype=np.float64)
    if result.ndim != 1 or not 40 <= result.size <= MAX_RETURN_OBSERVATIONS:
        raise ValueError(
            f"returns must contain 40 to {MAX_RETURN_OBSERVATIONS} observations"
        )
    if not np.all(np.isfinite(result)):
        raise ValueError("returns must all be finite")
    return result


def _validated_rates(values: Sequence[float] | float, count: int) -> np.ndarray:
    if isinstance(values, (int, float)) and not isinstance(values, bool):
        if not math.isfinite(float(values)):
            raise ValueError("risk_free_log_rates must be finite")
        return np.full(count, float(values), dtype=np.float64)
    result = np.asarray(tuple(values), dtype=np.float64)
    if result.ndim != 1 or result.size != count or not np.all(np.isfinite(result)):
        raise ValueError("risk_free_log_rates must be finite and match returns")
    return result


def _softmax_with_baseline(first: float, second: float) -> tuple[float, float, float]:
    maximum = max(0.0, first, second)
    baseline = math.exp(-maximum)
    first_exp = math.exp(first - maximum)
    second_exp = math.exp(second - maximum)
    total = baseline + first_exp + second_exp
    return baseline / total, first_exp / total, second_exp / total


def _decode_parameters(candidate: np.ndarray) -> tuple[PhysicalDynamics, float]:
    long_run_variance = math.exp(float(candidate[0]))
    persistence = float(candidate[1])
    omega_share, alpha_share, rho_share = _softmax_with_baseline(
        float(candidate[2]), float(candidate[3])
    )
    beta_share, gamma1_share, gamma2_share = _softmax_with_baseline(
        float(candidate[4]), float(candidate[5])
    )

    innovation_intercept = long_run_variance * (1.0 - persistence)
    omega = innovation_intercept * omega_share
    alpha = innovation_intercept * alpha_share
    rho = innovation_intercept * rho_share
    beta = persistence * beta_share
    gamma1 = math.sqrt(persistence * gamma1_share / alpha)
    gamma2 = math.sqrt(persistence * gamma2_share / rho)
    return (
        PhysicalDynamics(
            omega=omega,
            beta=beta,
            alpha=alpha,
            gamma1=gamma1,
            rho=rho,
            gamma2=gamma2,
            k=1,
        ),
        float(candidate[6]),
    )


def _common_random_numbers(
    count: int,
    particles: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    generator = np.random.Generator(np.random.PCG64(seed))
    variance_shocks = generator.standard_normal((count, particles))
    resampling_offsets = generator.random(count)
    return variance_shocks, resampling_offsets


def _particle_filter(
    returns: np.ndarray,
    rates: np.ndarray,
    physical: PhysicalDynamics,
    lambda1: float,
    *,
    particle_count: int,
    seed: int,
    capture: bool,
) -> FilterDiagnostics:
    variance_shocks, offsets = _common_random_numbers(
        int(returns.size), particle_count, seed
    )
    particles = np.full(particle_count, physical.long_run_variance, dtype=np.float64)
    locations = np.arange(particle_count, dtype=np.float64)
    log_likelihood = 0.0
    predictive_variances: list[float] = []
    standardized_residuals: list[float] = []
    contributions: list[float] = []

    for index, (observed_return, rate) in enumerate(zip(returns, rates, strict=True)):
        if (
            not np.all(np.isfinite(particles))
            or np.any(particles <= 0.0)
            or np.any(particles > 1.0)
        ):
            raise FloatingPointError("particle variance left the finite numerical domain")

        predictive = float(np.mean(particles))
        innovations = observed_return - rate - lambda1 * particles
        log_weights = -0.5 * (
            _LOG_2PI + np.log(particles) + innovations * innovations / particles
        )
        maximum = float(np.max(log_weights))
        relative = np.exp(log_weights - maximum)
        relative_sum = float(np.sum(relative))
        if not math.isfinite(relative_sum) or relative_sum <= 0.0:
            raise FloatingPointError("particle observation weights collapsed")
        contribution = maximum + math.log(relative_sum / particle_count)
        log_likelihood += contribution
        weights = relative / relative_sum

        if capture:
            predictive_variances.append(predictive)
            mean = rate + lambda1 * predictive
            standardized_residuals.append(
                float((observed_return - mean) / math.sqrt(predictive))
            )
            contributions.append(contribution)

        cumulative = np.cumsum(weights)
        positions = (locations + offsets[index]) / particle_count
        selected = np.searchsorted(cumulative, positions, side="right")
        selected = np.minimum(selected, particle_count - 1)
        previous = particles[selected]
        return_shocks = (
            observed_return - rate - lambda1 * previous
        ) / np.sqrt(previous)
        root_previous = np.sqrt(previous)
        particles = (
            physical.omega
            + physical.beta * previous
            + physical.alpha
            * (return_shocks - physical.gamma1 * root_previous) ** 2
            + physical.rho
            * (variance_shocks[index] - physical.gamma2 * root_previous) ** 2
        )

    if not np.all(np.isfinite(particles)) or np.any(particles <= 0.0):
        raise FloatingPointError("final particle state is invalid")
    quantiles = np.quantile(particles, [0.05, 0.5, 0.95])
    return FilterDiagnostics(
        observation_count=int(returns.size),
        log_likelihood=log_likelihood,
        average_log_likelihood=log_likelihood / int(returns.size),
        predictive_variances=tuple(predictive_variances),
        standardized_residuals=tuple(standardized_residuals),
        log_likelihood_contributions=tuple(contributions),
        h_next_mean=float(np.mean(particles)),
        h_next_median=float(quantiles[1]),
        h_next_p05=float(quantiles[0]),
        h_next_p95=float(quantiles[2]),
        particle_count=particle_count,
        seed=seed,
        latent_variance_shock_treatment=(
            "seeded_bootstrap_particle_filter_integrating_independent_standard_normal_shock"
        ),
    )


def filter_physical_returns(
    returns: Sequence[float],
    physical: PhysicalDynamics,
    *,
    lambda1: float,
    risk_free_log_rates: Sequence[float] | float = 0.0,
    particle_count: int = 256,
    seed: int = 29,
) -> FilterDiagnostics:
    """Filter ``h`` through returns without re-estimating any parameter."""

    validated_returns = _validated_returns(returns)
    rates = _validated_rates(risk_free_log_rates, int(validated_returns.size))
    if not math.isfinite(lambda1):
        raise ValueError("lambda1 must be finite")
    if (
        isinstance(particle_count, bool)
        or not isinstance(particle_count, int)
        or not 16 <= particle_count <= MAX_PARTICLES
    ):
        raise ValueError(f"particle_count must be an integer from 16 to {MAX_PARTICLES}")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    return _particle_filter(
        validated_returns,
        rates,
        physical,
        lambda1,
        particle_count=particle_count,
        seed=seed,
        capture=True,
    )


def summarize_filter_segment(
    filtered: FilterDiagnostics,
    returns: Sequence[float],
    *,
    start_index: int,
    end_index_exclusive: int,
) -> dict[str, float | int]:
    """Summarize a predeclared filter segment without refitting the model."""

    values = np.asarray(tuple(returns), dtype=np.float64)
    if values.ndim != 1 or values.size != filtered.observation_count:
        raise ValueError("returns must match the captured filter observations")
    if not 0 <= start_index < end_index_exclusive <= values.size:
        raise ValueError("segment indexes are invalid")
    predictive = np.asarray(
        filtered.predictive_variances[start_index:end_index_exclusive],
        dtype=np.float64,
    )
    selected_returns = values[start_index:end_index_exclusive]
    residuals = np.asarray(
        filtered.standardized_residuals[start_index:end_index_exclusive],
        dtype=np.float64,
    )
    contributions = filtered.log_likelihood_contributions[
        start_index:end_index_exclusive
    ]
    realized = residuals * residuals * predictive
    qlike = np.log(predictive) + realized / predictive
    centered = residuals - float(np.mean(residuals))
    residual_std = float(np.std(residuals, ddof=0))
    residual_kurtosis = (
        float(np.mean(centered**4) / residual_std**4)
        if residual_std > 0.0
        else 0.0
    )
    return {
        "observation_count": int(selected_returns.size),
        "log_likelihood": math.fsum(contributions),
        "average_log_likelihood": math.fsum(contributions) / selected_returns.size,
        "mean_qlike_using_squared_innovation_proxy": float(np.mean(qlike)),
        "rmse_daily_variance_vs_squared_innovation_proxy": float(
            math.sqrt(float(np.mean((predictive - realized) ** 2)))
        ),
        "standardized_residual_mean": float(np.mean(residuals)),
        "standardized_residual_std_ddof0": residual_std,
        "standardized_residual_kurtosis_non_excess": residual_kurtosis,
    }


def estimate_physical_dynamics(
    returns: Sequence[float],
    *,
    risk_free_log_rates: Sequence[float] | float = 0.0,
    config: PhysicalEstimationConfig = PhysicalEstimationConfig(),
) -> PhysicalEstimationResult:
    """Estimate P parameters by bounded simulated maximum likelihood.

    The parameterization makes the innovation-intercept shares and persistence
    shares sum exactly, so every optimizer evaluation has positive coefficients
    and finite ``p < 1``.  Positive ``gamma1`` selects the equity-leverage
    branch.  Positive ``gamma2`` is an explicit identification convention:
    return-only likelihood is invariant to its sign because the latent normal
    variance shock is symmetric.
    """

    validated_returns = _validated_returns(returns)
    rates = _validated_rates(risk_free_log_rates, int(validated_returns.size))
    sample_variance = max(float(np.var(validated_returns, ddof=0)), 1.0e-6)
    sample_mean = float(np.mean(validated_returns - rates))
    initial = np.asarray(
        [
            math.log(
                min(
                    max(sample_variance, config.minimum_long_run_variance),
                    config.maximum_long_run_variance,
                )
            ),
            0.95,
            math.log(6.0),
            math.log(3.0),
            math.log(0.5),
            math.log(1.0 / 6.0),
            min(
                max(sample_mean / sample_variance, config.lambda1_lower),
                config.lambda1_upper,
            ),
        ],
        dtype=np.float64,
    )
    bounds = (
        (math.log(config.minimum_long_run_variance), math.log(config.maximum_long_run_variance)),
        (config.minimum_persistence, config.maximum_persistence),
        (-6.0, 6.0),
        (-6.0, 6.0),
        (-6.0, 6.0),
        (-6.0, 6.0),
        (config.lambda1_lower, config.lambda1_upper),
    )

    def objective(candidate: np.ndarray) -> float:
        try:
            physical, lambda1 = _decode_parameters(candidate)
            filtered = _particle_filter(
                validated_returns,
                rates,
                physical,
                lambda1,
                particle_count=config.particle_count,
                seed=config.seed,
                capture=False,
            )
            return -filtered.average_log_likelihood
        except (FloatingPointError, OverflowError, ValueError):
            return 1.0e6

    optimization = minimize(
        objective,
        initial,
        method="Powell",
        bounds=bounds,
        options={
            "maxfev": config.max_evaluations,
            "xtol": config.tolerance,
            "ftol": config.tolerance,
        },
    )
    physical, lambda1 = _decode_parameters(np.asarray(optimization.x, dtype=np.float64))
    filtered = _particle_filter(
        validated_returns,
        rates,
        physical,
        lambda1,
        particle_count=config.particle_count,
        seed=config.seed,
        capture=True,
    )
    replication_seeds = (config.seed, config.seed + 1, config.seed + 2)
    replication_likelihoods = tuple(
        _particle_filter(
            validated_returns,
            rates,
            physical,
            lambda1,
            particle_count=config.particle_count,
            seed=seed,
            capture=False,
        ).average_log_likelihood
        for seed in replication_seeds
    )
    converged = bool(optimization.success) and math.isfinite(float(optimization.fun))
    return PhysicalEstimationResult(
        physical=physical,
        lambda1=lambda1,
        fit=PhysicalFitDiagnostics(
            objective_name="negative_average_seeded_particle_log_likelihood",
            objective_value=float(optimization.fun),
            converged=converged,
            optimizer="scipy.optimize.minimize(method=Powell)",
            status_code=int(optimization.status),
            message=str(optimization.message),
            function_evaluations=int(optimization.nfev),
            iterations=int(optimization.nit),
            tolerance=config.tolerance,
            parameterization=(
                "long_run_variance_and_simplex_shares_for_innovation_intercept_and_persistence"
            ),
            gamma1_branch="gamma1_nonnegative_equity_leverage_branch",
            gamma2_identification_branch="gamma2_nonnegative_latent_shock_branch",
            likelihood_replication_seeds=replication_seeds,
            likelihood_replication_average_log_likelihoods=replication_likelihoods,
            likelihood_replication_standard_deviation=float(
                np.std(np.asarray(replication_likelihoods), ddof=1)
            ),
        ),
        filter=filtered,
        config=config,
        limitations=(
            "The likelihood is a bounded seeded particle approximation, not an exact closed-form likelihood.",
            "The return-only likelihood cannot identify the sign of gamma2; the nonnegative branch is imposed.",
            "Daily close returns weakly identify lambda1 and separate innovation allocations; parameter uncertainty is not estimated.",
            "The filtered h_next distribution integrates the latent variance shock, but downstream pricing uses its reported mean unless a consumer propagates state uncertainty.",
        ),
    )
