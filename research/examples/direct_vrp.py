"""Labelled synthetic demonstration of the direct HN-GARCSH VRP API.

This fixture is generated from the model itself.  It is not an empirical SPX
or VIX calibration and must not be interpreted as evidence of profitability.
"""

from __future__ import annotations

import hashlib
import json

from luca_research.vrp import (
    ArtifactMetadata,
    CalibrationConfig,
    EuropeanOptionInputs,
    MonteCarloPricingConfig,
    OPTION_PRICING_RESULT_SCHEMA,
    PhysicalDynamics,
    RiskPrices,
    VixTermObservation,
    build_calibration_artifact,
    calibrate_vix_term_structure,
    option_pricing_result_asdict,
    price_european_options_monte_carlo,
    vix_term_value_percent,
)


def main() -> int:
    physical = PhysicalDynamics(
        omega=1.0e-7,
        beta=0.03,
        alpha=1.0e-6,
        gamma1=700.0,
        rho=1.0e-6,
        gamma2=650.0,
        k=1,
    )
    fixed_lambda1 = 1.0
    synthetic_truth = RiskPrices(lambda1=fixed_lambda1, lambda2=12.0)
    h_next = 0.18**2 / 252.0

    synthetic_terms = [
        {
            "label": label,
            "maturity_trading_days": maturity,
            "value_percent": vix_term_value_percent(
                h_next,
                maturity,
                physical,
                synthetic_truth,
            ),
        }
        for label, maturity in (
            ("SYNTHETIC_VIX9D_PROXY", 6),
            ("SYNTHETIC_VIX_1M_PROXY", 21),
            ("SYNTHETIC_VIX3M_PROXY", 63),
            ("SYNTHETIC_VIX6M_PROXY", 126),
            ("SYNTHETIC_VIX1Y_PROXY", 252),
        )
    ]
    observations = tuple(VixTermObservation(**item) for item in synthetic_terms)
    result = calibrate_vix_term_structure(
        physical,
        fixed_lambda1=fixed_lambda1,
        h_next=h_next,
        observations=observations,
        report_horizon_trading_days=21,
        config=CalibrationConfig(
            lambda2_lower=0.0,
            lambda2_upper=30.0,
            lambda2_initial=5.0,
            max_evaluations=200,
            tolerance=1.0e-12,
        ),
    )

    synthetic_document = {
        "classification": "synthetic_illustration",
        "generator": "research/examples/direct_vrp.py",
        "physical": physical.__dict__,
        "fixed_lambda1": fixed_lambda1,
        "synthetic_truth_lambda2": synthetic_truth.lambda2,
        "h_next": h_next,
        "terms": synthetic_terms,
    }
    canonical = json.dumps(
        synthetic_document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    metadata = ArtifactMetadata(
        run_id="direct-vrp-synthetic-example-v1",
        dataset_id="direct-vrp-self-generated-synthetic-v1",
        dataset_sha256=hashlib.sha256(canonical).hexdigest(),
        dataset_classification="synthetic_illustration",
        input_cutoff_utc="2000-01-03T21:00:00Z",
        availability_time_utc="2000-01-03T21:00:00Z",
        state_as_of_utc="2000-01-03T21:00:00Z",
        state_availability_time_utc="2000-01-03T21:00:00Z",
    )
    artifact = build_calibration_artifact(metadata, result)
    pricing = price_european_options_monte_carlo(
        physical,
        result.calibrated_risk_prices,
        h_next=h_next,
        inputs=EuropeanOptionInputs(
            contract_id="synthetic-forward-atm-21d",
            forward=5_000.0,
            strike=5_000.0,
            discount_factor=1.0,
            horizon_trading_days=21,
            settlement="cash",
        ),
        config=MonteCarloPricingConfig(path_counts=(10_000, 40_000), seed=101),
    )
    artifact["option_pricing_illustration"] = {
        "schema_version": OPTION_PRICING_RESULT_SCHEMA,
        **option_pricing_result_asdict(pricing),
        "input_classification": "synthetic_assumed_forward_strike_and_discount_factor",
    }
    print(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result.fit.converged and pricing.final.path_count == 40_000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
