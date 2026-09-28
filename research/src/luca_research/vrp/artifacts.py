"""Versioned, JSON-compatible artifacts for the direct VRP candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import re
from typing import Any, Literal, Mapping, Sequence

from .calibration import CalibrationResult
from .estimation import FilterDiagnostics, PhysicalEstimationResult
from .market import VixCutoffJoin
from .model import MODEL_VERSION, TRADING_DAYS_PER_YEAR, risk_neutral_dynamics
from .pricing import OptionPricingResult, option_pricing_result_asdict


RESULT_SCHEMA = "luca.direct-vrp-result.v1"
OPTION_PRICING_SCHEMA = "luca.hn-garcsh-option-pricing-input.v1"
EMPIRICAL_RESULT_SCHEMA = "luca.direct-vrp-empirical-result.v1"
OPTION_PRICING_RESULT_SCHEMA = "luca.hn-garcsh-option-pricing-result.v1"
DatasetClassification = Literal[
    "synthetic_illustration",
    "exploratory_historical",
    "unexamined_evaluation",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _nonempty(name: str, value: str, *, maximum: int = 256) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must contain 1 to {maximum} characters")


def _utc_datetime(name: str, value: str) -> datetime:
    _nonempty(name, value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must include a UTC offset")
    return parsed


@dataclass(frozen=True)
class ArtifactMetadata:
    run_id: str
    dataset_id: str
    dataset_sha256: str
    dataset_classification: DatasetClassification
    input_cutoff_utc: str
    availability_time_utc: str
    state_as_of_utc: str
    state_availability_time_utc: str

    def __post_init__(self) -> None:
        _nonempty("run_id", self.run_id)
        _nonempty("dataset_id", self.dataset_id)
        if not isinstance(self.dataset_sha256, str) or not _SHA256.fullmatch(
            self.dataset_sha256
        ):
            raise ValueError("dataset_sha256 must be a lowercase SHA-256 hex digest")
        if self.dataset_classification not in {
            "synthetic_illustration",
            "exploratory_historical",
            "unexamined_evaluation",
        }:
            raise ValueError("unsupported dataset_classification")
        cutoff = _utc_datetime("input_cutoff_utc", self.input_cutoff_utc)
        availability = _utc_datetime("availability_time_utc", self.availability_time_utc)
        state_as_of = _utc_datetime("state_as_of_utc", self.state_as_of_utc)
        state_availability = _utc_datetime(
            "state_availability_time_utc", self.state_availability_time_utc
        )
        if availability < cutoff:
            raise ValueError("availability_time_utc cannot precede input_cutoff_utc")
        if state_availability < state_as_of:
            raise ValueError("state availability cannot precede state as-of time")


def _dependency_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unavailable"


def _variance_report(result: CalibrationResult) -> dict[str, Any]:
    report = result.variance_premium
    return {
        "horizon": {
            "trading_days": report.horizon_trading_days,
            "year_fraction_252": report.physical.year_fraction,
        },
        "physical": {
            "measure": "P",
            "interval_variances_decimal_return_squared": list(
                report.physical.interval_variances
            ),
            "W_P_decimal_return_squared": report.physical.cumulative_variance,
            "average_daily_variance": report.physical.average_daily_variance,
            "annualized_volatility_decimal": report.physical.annualized_volatility,
        },
        "risk_neutral": {
            "measure": "Q",
            "interval_variances_decimal_return_squared": list(
                report.risk_neutral.interval_variances
            ),
            "W_Q_decimal_return_squared": report.risk_neutral.cumulative_variance,
            "average_daily_variance": report.risk_neutral.average_daily_variance,
            "annualized_volatility_decimal": report.risk_neutral.annualized_volatility,
        },
        "vrp": {
            "value_decimal_return_squared": report.vrp_q_minus_p,
            "sign_convention": "W_Q_minus_W_P",
            "paper_equation_13_sign_convention": "P_minus_Q_one_step",
        },
    }


def build_option_pricing_contract(
    metadata: ArtifactMetadata,
    result: CalibrationResult,
) -> dict[str, Any]:
    """Return model-side inputs and the market fields needed by the Q pricer."""

    transformed = risk_neutral_dynamics(
        result.fixed_physical,
        result.calibrated_risk_prices,
    )
    return {
        "schema_version": OPTION_PRICING_SCHEMA,
        "run_id": metadata.run_id,
        "dataset": {
            "dataset_id": metadata.dataset_id,
            "content_sha256": metadata.dataset_sha256,
            "classification": metadata.dataset_classification,
        },
        "input_cutoff_utc": metadata.input_cutoff_utc,
        "availability_time_utc": metadata.availability_time_utc,
        "status": "model_ready_contract_inputs_required",
        "ready_for_option_pricing": False,
        "not_ready_reason": "exact contract, forward, discount factor, and horizon inputs are not part of this model-only contract",
        "available_pricing_method": "controlled Monte Carlo under the published risk-neutral dynamics",
        "model_version": MODEL_VERSION,
        "model_state": {
            "h_next": result.fixed_h_next,
            "units": "decimal_return_squared_per_trading_day",
            "as_of_utc": metadata.state_as_of_utc,
            "availability_time_utc": metadata.state_availability_time_utc,
            "provenance": "caller_supplied_filtered_state",
        },
        "physical_dynamics": asdict(result.fixed_physical),
        "physical_properties": {
            "p": result.fixed_physical.persistence,
            "mu": result.fixed_physical.long_run_variance,
        },
        "risk_prices": asdict(result.calibrated_risk_prices),
        "risk_neutral_dynamics": asdict(transformed),
        "required_contract_inputs": [
            "root and exact option symbol",
            "put_or_call",
            "strike",
            "expiration_and_settlement_timestamp_utc",
            "settlement_style_and_exchange_calendar_provenance",
            "contract_multiplier",
        ],
        "required_market_inputs": [
            "spot_or_forward_with_source_event_and_receive_times",
            "discount_curve_at_the_common_information_cutoff",
            "dividend_or_carry_convention",
        ],
        "required_output_fields": [
            "call_put_and_straddle_theoretical_values",
            "put_call_parity_residual",
            "Monte_Carlo_standard_errors_and_convergence_checkpoints",
            "pricing_convention",
            "model_state_availability_time_utc",
            "warnings_and_exclusions",
        ],
        "prohibited_fallbacks": [
            "arbitrary_volatility_multiplier",
            "silent_Black_forecast_price_substitution",
            "discrete_VIX_regime_substitution",
        ],
        "warnings": [
            "Research floating-point model inputs; not an authoritative accounting value.",
            "Cumulative expected variance alone does not determine the option-price distribution; use the full Q path dynamics.",
        ],
        "exclusions": [
            "no_price_without_explicit_contract_forward_discount_and_horizon_inputs"
        ],
    }


def build_calibration_artifact(
    metadata: ArtifactMetadata,
    result: CalibrationResult,
) -> dict[str, Any]:
    """Build a deterministic JSON-compatible direct-model result artifact."""

    warnings = [
        "Research floating-point output; not an authoritative accounting value.",
        "Trading-day horizons require an upstream exchange-calendar mapping for an exact option settlement interval.",
        "The exact pricing-kernel equation is not reproduced in the accessible "
        "2026 article; pricing uses its explicitly published Q dynamics directly.",
    ]
    if metadata.dataset_classification == "synthetic_illustration":
        warnings.append(
            "Synthetic illustration only: do not interpret the fit or premium as empirical evidence or profitability."
        )
    if not result.fit.converged:
        warnings.append("The bounded optimizer did not report a converged admissible fit.")

    return {
        "schema_version": RESULT_SCHEMA,
        "run_id": metadata.run_id,
        "dataset": {
            "dataset_id": metadata.dataset_id,
            "content_sha256": metadata.dataset_sha256,
            "classification": metadata.dataset_classification,
        },
        "timing": {
            "input_cutoff_utc": metadata.input_cutoff_utc,
            "availability_time_utc": metadata.availability_time_utc,
            "state_as_of_utc": metadata.state_as_of_utc,
            "state_availability_time_utc": metadata.state_availability_time_utc,
        },
        "model": {
            "model_version": MODEL_VERSION,
            "name": "direct_two_shock_HN_GARCSH",
            "source": {
                "citation": (
                    "Escobar-Anel, Stentoft, and Ye (2026), The Role of Variance "
                    "Risk Premium in Derivative Pricing: Modeling, Estimation and Impact"
                ),
                "doi": "10.1002/fut.70132",
                "implemented_equations": [1, 3, 5, 6, 7, 8, 9, 10, 11, 12, 19, 20, 30],
                "unresolved_exact_source_components": [
                    "pricing-kernel equation (not printed in the accessible article)",
                    "complete primary-paper admissibility theorem (not printed in the accessible article)",
                ],
            },
            "mean_and_drift_convention": {
                "physical_log_return": "r + lambda1*h + sqrt(h)*z1",
                "risk_neutral_log_return": "r - 0.5*h + sqrt(h)*z1_star",
                "risk_free_rate": "continuously_compounded_per_model_period",
            },
            "physical_dynamics": asdict(result.fixed_physical),
            "physical_properties": {
                "p": result.fixed_physical.persistence,
                "mu": result.fixed_physical.long_run_variance,
            },
            "fixed_pricing_parameter": {"lambda1": result.fixed_lambda1},
            "calibrated_pricing_parameter": {
                "lambda2": result.calibrated_risk_prices.lambda2
            },
            "risk_neutral_transformation": {
                "gamma1_star": result.fixed_physical.gamma1
                + result.fixed_lambda1
                + 0.5,
                "gamma2_star": result.fixed_physical.gamma2
                + result.calibrated_risk_prices.lambda2,
                "p_star": result.risk_neutral_persistence,
                "mu_star": result.risk_neutral_long_run_variance,
            },
            "admissibility": {
                "status": "sufficient_implementation_constraints_not_primary_theorem",
                "constraints": [
                    "omega>=0, beta>=0, alpha>0, rho>0, integer k>=1",
                    "physical persistence p<1",
                    "risk-neutral persistence p_star<1 with numerical margin 1e-10 during calibration",
                    "filtered h_next>0",
                ],
            },
            "state": {
                "h_next": result.fixed_h_next,
                "units": "decimal_return_squared_per_trading_day",
                "role": "fixed_caller_supplied_filtered_state",
            },
        },
        "calibration": {
            "target": "VIX_term_structure",
            "parameter_fitted": "lambda2_constant",
            "objective": asdict(result.fit),
            "identification": {
                "selected_branch": result.identification_branch,
                "observationally_equivalent_lambda2": result.observationally_equivalent_lambda2,
            },
            "term_fits": [asdict(item) for item in result.term_fits],
        },
        "variance_premium": _variance_report(result),
        "units": {
            "variance": "decimal_return_squared",
            "daily_variance": "decimal_return_squared_per_trading_day",
            "VIX": "percentage_points",
            "annualizer_trading_days": TRADING_DAYS_PER_YEAR,
        },
        "runtime_dependencies": {
            "numpy": _dependency_version("numpy"),
            "scipy": _dependency_version("scipy"),
        },
        "option_pricing_contract": build_option_pricing_contract(metadata, result),
        "warnings": warnings,
        "exclusions": (
            ["empirical_calibration_not_run_without_qualified_historical_VIX_terms"]
            if metadata.dataset_classification == "synthetic_illustration"
            else []
        ),
        "limitations": list(result.limitations),
    }


def build_empirical_artifact(
    metadata: ArtifactMetadata,
    physical_estimation: PhysicalEstimationResult,
    cutoff_filter: FilterDiagnostics,
    pricing_calibration: CalibrationResult,
    vix_join: VixCutoffJoin,
    option_pricing: OptionPricingResult,
    *,
    sample_boundaries: Mapping[str, Any],
    heldout_diagnostics: Mapping[str, Any],
    input_provenance: Sequence[Mapping[str, Any]],
    contract_and_market_inputs: Mapping[str, Any],
    extra_limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the app-facing empirical model, surface, and pricing artifact."""

    if pricing_calibration.fixed_physical != physical_estimation.physical:
        raise ValueError("pricing calibration must use the fitted physical dynamics")
    if pricing_calibration.fixed_lambda1 != physical_estimation.lambda1:
        raise ValueError("pricing calibration must use the fitted lambda1")
    if pricing_calibration.fixed_h_next != cutoff_filter.h_next_mean:
        raise ValueError("pricing calibration must use the cutoff filter mean h_next")
    if option_pricing.h_next != cutoff_filter.h_next_mean:
        raise ValueError("option pricing must use the cutoff filter mean h_next")
    joined_labels = {item.label for item in vix_join.observations}
    calibrated_labels = {item.label for item in pricing_calibration.term_fits}
    if joined_labels != calibrated_labels:
        raise ValueError("pricing calibration terms must equal included VIX join terms")

    included_count = sum(item.status == "included" for item in vix_join.entries)
    excluded_count = len(vix_join.entries) - included_count
    complete = (
        physical_estimation.fit.converged
        and pricing_calibration.fit.converged
        and included_count >= 2
    )
    physical = physical_estimation.physical
    transformed = risk_neutral_dynamics(
        physical, pricing_calibration.calibrated_risk_prices
    )
    warnings = [
        "Retrospective exploratory research only; the daily files do not prove contemporaneous historical receipt.",
        "Research floating-point values are not authoritative accounting values or executable signals.",
        "No option print is present, so the theoretical value is not a trade score or evidence of profitability.",
        "No order is submitted by this package or artifact.",
    ]
    if not complete:
        warnings.append("At least one bounded fit did not report convergence or sufficient joined terms.")

    return {
        "schema_version": EMPIRICAL_RESULT_SCHEMA,
        "status": "complete" if complete else "partial",
        "run_id": metadata.run_id,
        "dataset": {
            "dataset_id": metadata.dataset_id,
            "content_sha256": metadata.dataset_sha256,
            "classification": metadata.dataset_classification,
            "inputs": [dict(item) for item in input_provenance],
        },
        "timing": {
            "historical_information_cutoff_utc": vix_join.information_cutoff_utc,
            "retrospective_input_cutoff_utc": metadata.input_cutoff_utc,
            "retrospective_input_availability_utc": metadata.availability_time_utc,
            "state_as_of_utc": metadata.state_as_of_utc,
            "state_input_availability_utc": metadata.state_availability_time_utc,
            "vix_close_time_assumption": vix_join.assumed_close_time,
            "mode": "retrospective_replay_not_live",
        },
        "sample_boundaries": dict(sample_boundaries),
        "physical_estimation": {
            "measure": "P",
            "parameters": asdict(physical),
            "lambda1": physical_estimation.lambda1,
            "properties": {
                "p": physical.persistence,
                "mu": physical.long_run_variance,
                "innovation_intercept": physical.innovation_intercept,
            },
            "fit": asdict(physical_estimation.fit),
            "configuration": asdict(physical_estimation.config),
            "in_sample_filter": {
                "observation_count": physical_estimation.filter.observation_count,
                "log_likelihood": physical_estimation.filter.log_likelihood,
                "average_log_likelihood": physical_estimation.filter.average_log_likelihood,
                "particle_count": physical_estimation.filter.particle_count,
                "seed": physical_estimation.filter.seed,
            },
            "heldout_diagnostics": dict(heldout_diagnostics),
            "latent_variance_shock": {
                "treatment": cutoff_filter.latent_variance_shock_treatment,
                "substituted_by_expectation": False,
            },
            "cutoff_state": {
                "selected_h_next": cutoff_filter.h_next_mean,
                "selection": "posterior_particle_mean",
                "median": cutoff_filter.h_next_median,
                "p05": cutoff_filter.h_next_p05,
                "p95": cutoff_filter.h_next_p95,
                "units": "decimal_return_squared_per_trading_day",
                "particle_count": cutoff_filter.particle_count,
                "seed": cutoff_filter.seed,
            },
            "limitations": list(physical_estimation.limitations),
        },
        "vix_cutoff_join": {
            "cutoff_date": vix_join.cutoff_date,
            "exact_date_required": vix_join.exact_date_required,
            "included_count": included_count,
            "excluded_count": excluded_count,
            "entries": [asdict(item) for item in vix_join.entries],
            "limitations": list(vix_join.limitations),
        },
        "pricing_calibration": {
            "measure": "Q",
            "parameter_fitted": "lambda2_constant",
            "risk_prices": asdict(pricing_calibration.calibrated_risk_prices),
            "risk_neutral_dynamics": asdict(transformed),
            "fit": asdict(pricing_calibration.fit),
            "identification": {
                "selected_branch": pricing_calibration.identification_branch,
                "observationally_equivalent_lambda2": pricing_calibration.observationally_equivalent_lambda2,
            },
            "term_fits": [asdict(item) for item in pricing_calibration.term_fits],
            "surface_relative_interpretation": (
                "observed_minus_model VIX term errors are surface-relative diagnostics, "
                "not aggregate VRP or option trade richness"
            ),
            "limitations": list(pricing_calibration.limitations),
        },
        "aggregate_variance_premium": _variance_report(pricing_calibration),
        "option_pricing": {
            "schema_version": OPTION_PRICING_RESULT_SCHEMA,
            **option_pricing_result_asdict(option_pricing),
            "contract_and_market_input_provenance": dict(contract_and_market_inputs),
            "interpretation": (
                "research theoretical value under full simulated Q dynamics; no market print comparison"
            ),
        },
        "measure_distinctions": {
            "aggregate_VRP": "horizon-matched W_Q minus W_P in decimal-return-squared units",
            "surface_relative_richness": "term-specific observed VIX close minus fitted model VIX in percentage points",
            "option_theoretical_value": "discounted Q expectation of call, put, or straddle payoff under simulated terminal distribution",
            "trade_score": "not available because no eligible option print and event-time quote are supplied",
        },
        "units": {
            "variance": "decimal_return_squared",
            "daily_variance": "decimal_return_squared_per_trading_day",
            "VIX": "percentage_points",
            "option_value": "index_points_times_contract_multiplier",
            "annualizer_trading_days": TRADING_DAYS_PER_YEAR,
        },
        "runtime_dependencies": {
            "numpy": _dependency_version("numpy"),
            "scipy": _dependency_version("scipy"),
        },
        "warnings": warnings,
        "exclusions": [
            "no_option_print_or_event_time_NBBO_available_for_scoring",
            "no_intraday_VIX_vintage_or_receive_timestamp_available",
            "no_live_provider_coverage_or_permission_claim",
            "no_order_submission",
        ],
        "limitations": [
            *physical_estimation.limitations,
            *vix_join.limitations,
            *pricing_calibration.limitations,
            *option_pricing.limitations,
            *extra_limitations,
        ],
    }
