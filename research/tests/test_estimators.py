import math
import unittest

from luca_research.estimators import (
    annualize_cumulative_variance,
    ewma_variance,
    historical_variance,
    qlike,
    realized_close_variance,
)


class EstimatorKnownValueTests(unittest.TestCase):
    def test_historical_zero_and_constant_mean_units(self):
        zero_variance, zero_mean = historical_variance([0.1, -0.2], "zero")
        constant_variance, constant_mean = historical_variance([0.1, -0.2], "constant")

        self.assertAlmostEqual(zero_variance, 0.025)
        self.assertEqual(zero_mean, 0.0)
        self.assertAlmostEqual(constant_mean, -0.05)
        self.assertAlmostEqual(constant_variance, 0.045)

    def test_ewma_recursion_uses_first_innovation_as_initial_variance(self):
        variance, mean = ewma_variance([0.1, -0.2], 0.5, "zero")
        self.assertEqual(mean, 0.0)
        self.assertAlmostEqual(variance, 0.5 * 0.1**2 + 0.5 * 0.2**2)

    def test_cumulative_realized_variance_and_calendar_annualization(self):
        realized = realized_close_variance([0.01, -0.02, 0.03])
        self.assertAlmostEqual(realized, 0.0014)
        annualized = annualize_cumulative_variance(
            realized, horizon_calendar_days=30, calendar_days_per_year=365.2425
        )
        self.assertAlmostEqual(annualized, 0.0014 * 365.2425 / 30.0)

    def test_qlike_known_value(self):
        self.assertAlmostEqual(qlike(0.04, 0.05), math.log(0.04) + 1.25)


if __name__ == "__main__":
    unittest.main()
