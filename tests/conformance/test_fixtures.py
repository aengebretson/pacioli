import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from harness import FixtureError, discover_scenarios, load_scenario  # noqa: E402


class FixtureValidationTest(unittest.TestCase):
    def _load_with_expected_cash(self, document):
        source = Path(__file__).parent / "cash-deposit"
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / source.name
        shutil.copytree(source, directory)
        (directory / "expected_cash.json").write_text(json.dumps(document))
        return load_scenario(directory)

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

    def test_timestamp_based_expected_projection_is_valid(self):
        scenario = self._load_with_expected_cash({"as_of": "2026-01-05T09:00:00Z", "cash": []})
        self.assertEqual(scenario.expected["effective"]["cash"]["as_of"], "2026-01-05T09:00:00Z")

    def test_date_based_expected_projection_is_valid(self):
        scenario = self._load_with_expected_cash({"as_of_date": "2026-01-05", "cash": []})
        self.assertEqual(scenario.expected["effective"]["cash"]["as_of_date"], "2026-01-05")

    def test_expected_projection_rejects_both_temporal_anchors(self):
        with self.assertRaisesRegex(FixtureError, "exactly one of as_of or as_of_date"):
            self._load_with_expected_cash(
                {"as_of": "2026-01-05T09:00:00Z", "as_of_date": "2026-01-05", "cash": []}
            )

    def test_expected_projection_rejects_missing_temporal_anchor(self):
        with self.assertRaisesRegex(FixtureError, "exactly one of as_of or as_of_date"):
            self._load_with_expected_cash({"cash": []})

    def test_expected_projection_rejects_malformed_as_of_date(self):
        with self.assertRaisesRegex(FixtureError, "as_of_date must be an ISO 8601 date"):
            self._load_with_expected_cash({"as_of_date": "2026-02-30", "cash": []})


if __name__ == "__main__":
    unittest.main()
