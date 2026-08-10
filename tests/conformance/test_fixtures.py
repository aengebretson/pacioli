import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from harness import FixtureError, discover_scenarios, load_scenario  # noqa: E402


class FixtureValidationTest(unittest.TestCase):
    def test_all_registered_fixtures_are_well_formed(self):
        scenarios = discover_scenarios()
        self.assertEqual(
            {scenario.definition["name"] for scenario in scenarios},
            {"cash-deposit", "equity-buy", "equity-sell", "trade-settlement-lifecycle"},
        )
        for scenario in scenarios:
            self.assertTrue(scenario.expected)

    def test_missing_account_fails_clearly(self):
        source = discover_scenarios()[0]
        definition = copy.deepcopy(source.definition)
        del definition["inputs"][0]["account"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / definition["name"]
            directory.mkdir()
            (directory / "scenario.json").write_text(__import__("json").dumps(definition))
            with self.assertRaisesRegex(FixtureError, "account must be a non-empty string"):
                load_scenario(directory)

    def test_numeric_json_number_is_rejected(self):
        source = discover_scenarios()[0]
        definition = copy.deepcopy(source.definition)
        definition["inputs"][0]["amount"] = 1000000
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / definition["name"]
            directory.mkdir()
            (directory / "scenario.json").write_text(__import__("json").dumps(definition))
            with self.assertRaisesRegex(FixtureError, "amount must be a non-empty string"):
                load_scenario(directory)


if __name__ == "__main__":
    unittest.main()
