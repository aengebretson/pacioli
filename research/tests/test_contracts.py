import copy
import json
import math
from pathlib import Path
import unittest

from luca_research.contracts import ContractError, parse_close_input, parse_request


ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class UnreadableMembers(list):
    """A sized array whose members must not be inspected."""

    def __iter__(self):
        raise AssertionError("array members were iterated")

    def __getitem__(self, key):
        raise AssertionError(f"array member {key!r} was accessed")


class ContractTests(unittest.TestCase):
    def test_synthetic_contracts_validate_and_hash(self):
        request_document = fixture("synthetic_request.json")
        request = parse_request(request_document)
        input_data = parse_close_input(
            fixture("synthetic_spx_like.json"), max_observations=request.limits.max_observations
        )
        self.assertEqual(input_data.sha256, request.input_sha256)
        self.assertEqual(len(input_data.observations), 180)

    def test_rejects_nonfinite_nonpositive_duplicate_and_ambiguous_input(self):
        base = {
            "schema_version": "luca.normalized-close.v1",
            "input_id": "bad-input",
            "close_unit": "index_points",
            "observations": [
                {"date": "2024-01-01", "close": 100.0},
                {"date": "2024-01-02", "close": 101.0},
                {"date": "2024-01-03", "close": 102.0},
            ],
        }
        cases = []
        nonfinite = copy.deepcopy(base)
        nonfinite["observations"][1]["close"] = math.nan
        cases.append((nonfinite, "nonfinite_number"))
        nonpositive = copy.deepcopy(base)
        nonpositive["observations"][1]["close"] = 0.0
        cases.append((nonpositive, "number_out_of_range"))
        duplicate = copy.deepcopy(base)
        duplicate["observations"][2]["date"] = "2024-01-02"
        cases.append((duplicate, "duplicate_date"))
        no_unit = copy.deepcopy(base)
        del no_unit["close_unit"]
        cases.append((no_unit, "ambiguous_unit"))

        for document, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ContractError) as caught:
                    parse_close_input(document, max_observations=10)
                self.assertIn(expected_code, {item.code for item in caught.exception.diagnostics})

    def test_rejects_selection_label_crossing_holdout_boundary(self):
        request = fixture("synthetic_request.json")
        request["windows"][0]["endpoint"] = "2024-07-16"
        with self.assertRaises(ContractError) as caught:
            parse_request(request)
        self.assertIn("boundary_leakage", {item.code for item in caught.exception.diagnostics})

    def test_rejects_limits_above_hard_caps(self):
        request = fixture("synthetic_request.json")
        request["limits"]["max_origins"] = 101
        with self.assertRaises(ContractError) as caught:
            parse_request(request)
        self.assertIn("invalid_integer", {item.code for item in caught.exception.diagnostics})

    def test_observation_limit_is_rejected_before_member_processing(self):
        document = fixture("synthetic_spx_like.json")
        document["observations"] = UnreadableMembers([None, None, None, None])

        with self.assertRaises(ContractError) as caught:
            parse_close_input(document, max_observations=3)

        self.assertEqual(
            [item.code for item in caught.exception.diagnostics],
            ["observation_limit_exceeded"],
        )

    def test_observations_at_limit_receive_normal_member_validation(self):
        document = fixture("synthetic_spx_like.json")
        document["observations"] = document["observations"][:3]
        document["observations"][2]["close"] = "not-a-number"

        with self.assertRaises(ContractError) as caught:
            parse_close_input(document, max_observations=3)

        self.assertIn(
            "invalid_number",
            {item.code for item in caught.exception.diagnostics},
        )

    def test_origin_limit_is_rejected_before_member_processing(self):
        request = fixture("synthetic_request.json")
        request["limits"]["max_origins"] = 1
        request["windows"] = UnreadableMembers([None, None])

        with self.assertRaises(ContractError) as caught:
            parse_request(request)

        self.assertEqual(
            [item.code for item in caught.exception.diagnostics],
            ["origin_limit_exceeded"],
        )

    def test_origins_at_limit_receive_normal_member_validation(self):
        request = fixture("synthetic_request.json")
        request["limits"]["max_origins"] = len(request["windows"])
        request["windows"][1]["origin"] = "not-a-date"

        with self.assertRaises(ContractError) as caught:
            parse_request(request)

        self.assertIn(
            "invalid_date",
            {item.code for item in caught.exception.diagnostics},
        )

    def test_rejects_number_not_representable_as_binary64(self):
        document = fixture("synthetic_spx_like.json")
        document["observations"][0]["close"] = 10**400

        with self.assertRaises(ContractError) as caught:
            parse_close_input(document, max_observations=1000)

        self.assertIn(
            "number_not_representable",
            {item.code for item in caught.exception.diagnostics},
        )


if __name__ == "__main__":
    unittest.main()
