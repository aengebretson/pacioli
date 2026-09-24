import math
import unittest

import numpy as np
from arch import arch_model

from luca_research.garch import fit_garch11, garch11_variance_forecast


def deterministic_returns(count=140):
    return tuple(
        0.0003 + 0.009 * math.sin(index * 0.63) + 0.004 * math.cos(index * 0.19)
        for index in range(count)
    )


class GarchAdapterTests(unittest.TestCase):
    def test_fixed_parameter_forecast_matches_independent_recursion(self):
        actual = garch11_variance_forecast(
            omega=0.1,
            alpha=0.2,
            beta=0.7,
            last_residual_squared=4.0,
            last_conditional_variance=2.0,
            horizon=3,
        )
        expected_first = 0.1 + 0.2 * 4.0 + 0.7 * 2.0
        expected_second = 0.1 + 0.9 * expected_first
        expected_third = 0.1 + 0.9 * expected_second
        np.testing.assert_allclose(actual, [expected_first, expected_second, expected_third], rtol=0.0, atol=1e-15)

    def test_fitted_adapter_matches_pinned_upstream_output(self):
        returns = deterministic_returns()
        actual = fit_garch11(
            returns,
            horizon=8,
            mean="zero",
            max_iterations=500,
            optimizer_tolerance=1e-8,
        )

        scaled = np.asarray(returns) * 100.0
        model = arch_model(
            scaled,
            mean="Zero",
            vol="GARCH",
            p=1,
            o=0,
            q=1,
            power=2.0,
            dist="normal",
            rescale=False,
        )
        upstream = model.fit(
            disp="off",
            update_freq=0,
            show_warning=False,
            tol=1e-8,
            options={"maxiter": 500},
        )
        expected = np.asarray(
            upstream.forecast(horizon=8, method="analytic", reindex=False).residual_variance.iloc[-1]
        ) / 10_000.0

        np.testing.assert_allclose(actual.conditional_variances, expected, rtol=1e-12, atol=1e-15)
        for name, value in upstream.params.items():
            self.assertAlmostEqual(actual.parameters_upstream_percent[name], float(value), places=12)
        self.assertTrue(actual.convergence["success"])
        self.assertEqual(actual.convergence["convergence_flag"], 0)

    def test_constant_mean_is_fitted_and_converted_to_decimal_units(self):
        actual = fit_garch11(
            deterministic_returns(),
            horizon=3,
            mean="constant",
            max_iterations=500,
            optimizer_tolerance=1e-8,
        )
        self.assertIn("mu", actual.parameters_decimal)
        self.assertAlmostEqual(
            actual.parameters_decimal["mu"],
            actual.parameters_upstream_percent["mu"] / 100.0,
            places=15,
        )


if __name__ == "__main__":
    unittest.main()
