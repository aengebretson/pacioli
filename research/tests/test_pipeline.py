import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from luca_research import run_analysis
from luca_research.cli import MAX_REQUEST_JSON_BYTES, _load_json
from luca_research.contracts import parse_close_input
from luca_research.garch import GarchFitFailure


ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.request = fixture("synthetic_request.json")
        self.input_document = fixture("synthetic_spx_like.json")

    def test_end_to_end_uses_common_origins_and_explicit_calendar_horizons(self):
        artifact = run_analysis(self.request, self.input_document)
        self.assertEqual(artifact["status"], "complete")
        self.assertEqual(len(artifact["evaluation_records"]), 2)
        self.assertEqual(artifact["fit_failures"], [])
        self.assertEqual(artifact["exclusions"], [])
        self.assertEqual(
            artifact["configuration"]["host_agreement_tolerances"]["absolute"],
            1e-12,
        )
        for record in artifact["evaluation_records"]:
            self.assertEqual(record["horizon"]["calendar_days"], 29)
            self.assertEqual(record["horizon"]["interval_count"], 21)
            self.assertEqual(set(record["forecasts"]), {"historical", "ewma", "garch_1_1"})
            for model in ("historical", "ewma", "garch_1_1"):
                self.assertEqual(len(record["forecasts"][model]["interval_variances_decimal_squared"]), 21)
                self.assertEqual(record["forecasts"][model]["fit"]["availability_cutoff"], record["origin"])
        for split in ("all", "selection", "holdout"):
            counts = {
                values["origin_count"]
                for values in artifact["metrics"][split]["models"].values()
            }
            self.assertEqual(len(counts), 1)

    def test_future_close_perturbation_does_not_change_earlier_forecast(self):
        request = copy.deepcopy(self.request)
        request["windows"] = [request["windows"][0]]
        baseline = run_analysis(request, self.input_document)
        self.assertEqual(baseline["status"], "complete")

        perturbed_input = copy.deepcopy(self.input_document)
        origin = request["windows"][0]["origin"]
        for observation in perturbed_input["observations"]:
            if observation["date"] > origin:
                observation["close"] *= 1.01
        normalized = parse_close_input(perturbed_input, max_observations=1000)
        request["input"]["sha256"] = normalized.sha256
        perturbed = run_analysis(request, perturbed_input)

        self.assertEqual(perturbed["status"], "complete")
        self.assertNotEqual(baseline["inputs"][0]["sha256"], perturbed["inputs"][0]["sha256"])
        self.assertEqual(
            baseline["evaluation_records"][0]["forecasts"]["garch_1_1"]["fit"]["available_input_prefix"],
            perturbed["evaluation_records"][0]["forecasts"]["garch_1_1"]["fit"]["available_input_prefix"],
        )
        baseline_forecasts = copy.deepcopy(baseline["evaluation_records"][0]["forecasts"])
        perturbed_forecasts = copy.deepcopy(perturbed["evaluation_records"][0]["forecasts"])
        for model in baseline_forecasts:
            del baseline_forecasts[model]["losses"]
            del perturbed_forecasts[model]["losses"]
        self.assertEqual(baseline_forecasts, perturbed_forecasts)
        self.assertNotEqual(
            baseline["evaluation_records"][0]["realized_proxy"],
            perturbed["evaluation_records"][0]["realized_proxy"],
        )
        self.assertNotEqual(
            baseline["evaluation_records"][0]["forecasts"]["garch_1_1"]["losses"],
            perturbed["evaluation_records"][0]["forecasts"]["garch_1_1"]["losses"],
        )

    def test_garch_failure_excludes_origin_for_every_model_without_fallback(self):
        with patch(
            "luca_research.pipeline.fit_garch11",
            side_effect=GarchFitFailure("deliberate failure", {"status": 9}),
        ):
            artifact = run_analysis(self.request, self.input_document)

        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["evaluation_records"], [])
        self.assertEqual(artifact["metrics"], {})
        self.assertEqual(len(artifact["fit_failures"]), 2)
        self.assertTrue(all(item["reason"] == "garch_fit_failure" for item in artifact["exclusions"]))
        self.assertTrue(all(item["applies_to"] == ["historical", "ewma", "garch_1_1"] for item in artifact["exclusions"]))

    def test_callable_is_deterministic_and_cli_artifact_agrees_exactly(self):
        expected = run_analysis(self.request, self.input_document)
        self.assertEqual(expected, run_analysis(self.request, self.input_document))
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "luca_research",
                    "--request",
                    str(ROOT / "fixtures" / "synthetic_request.json"),
                    "--input",
                    str(ROOT / "fixtures" / "synthetic_spx_like.json"),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            actual = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)

    def test_cli_serialized_input_read_is_bounded_before_json_decode(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            request_path = Path(temporary_directory) / "oversized-request.json"
            request_path.write_bytes(b" " * (MAX_REQUEST_JSON_BYTES + 1))

            with self.assertRaisesRegex(
                ValueError,
                rf"exceeds the {MAX_REQUEST_JSON_BYTES}-byte serialized input limit",
            ):
                _load_json(
                    request_path,
                    "request",
                    max_bytes=MAX_REQUEST_JSON_BYTES,
                )

    def test_input_hash_mismatch_is_a_structured_error(self):
        changed = copy.deepcopy(self.input_document)
        changed["observations"][10]["close"] += 1.0
        artifact = run_analysis(self.request, changed)
        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["errors"][0]["code"], "input_hash_mismatch")
        self.assertEqual(artifact["evaluation_records"], [])

    def test_malformed_input_is_a_structured_error(self):
        changed = copy.deepcopy(self.input_document)
        changed["observations"][10]["close"] = 0.0
        artifact = run_analysis(self.request, changed)
        self.assertEqual(artifact["status"], "failed")
        self.assertIn("number_out_of_range", {error["code"] for error in artifact["errors"]})
        self.assertEqual(artifact["evaluation_records"], [])

    def test_extreme_positive_finite_closes_do_not_underflow_log_return(self):
        changed = copy.deepcopy(self.input_document)
        changed["observations"][-2]["close"] = 1e300
        changed["observations"][-1]["close"] = 1e-300
        normalized = parse_close_input(changed, max_observations=1000)
        request = copy.deepcopy(self.request)
        request["input"]["sha256"] = normalized.sha256

        artifact = run_analysis(request, changed)

        self.assertEqual(artifact["status"], "complete")
        self.assertTrue(
            math.isfinite(
                math.log(changed["observations"][-1]["close"])
                - math.log(changed["observations"][-2]["close"])
            )
        )

    def test_oversized_integer_close_is_a_structured_cli_failure(self):
        changed = copy.deepcopy(self.input_document)
        changed["observations"][0]["close"] = 10**400
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "input.json"
            output_path = Path(temporary_directory) / "result.json"
            input_path.write_text(json.dumps(changed), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "luca_research",
                    "--request",
                    str(ROOT / "fixtures" / "synthetic_request.json"),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr)
            artifact = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(artifact["status"], "failed")
        self.assertIn(
            "number_not_representable",
            {error["code"] for error in artifact["errors"]},
        )

    def test_overlapping_horizon_labels_are_flagged_as_dependent(self):
        request = copy.deepcopy(self.request)
        request["windows"].insert(
            1,
            {"origin": "2024-06-03", "endpoint": "2024-07-02", "split": "selection"},
        )
        artifact = run_analysis(request, self.input_document)
        self.assertEqual(artifact["status"], "complete")
        self.assertIn(
            "overlapping_horizons_dependent",
            {warning["code"] for warning in artifact["warnings"]},
        )


if __name__ == "__main__":
    unittest.main()
