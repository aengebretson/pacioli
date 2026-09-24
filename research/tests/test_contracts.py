import copy
import json
import math
from pathlib import Path
import unittest

from luca_research.contracts import ContractError, parse_close_input, parse_request


ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


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


if __name__ == "__main__":
    unittest.main()

