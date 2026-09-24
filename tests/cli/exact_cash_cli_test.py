#!/usr/bin/env python3

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

if len(sys.argv) != 3:
    raise RuntimeError("expected CLI executable and fixture directory")
EXECUTABLE = pathlib.Path(sys.argv[1]).resolve()
FIXTURE_ROOT = pathlib.Path(sys.argv[2]).resolve()
del sys.argv[1:]


class ExactCashCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = EXECUTABLE
        cls.fixture_root = FIXTURE_ROOT
        cls.base_bytes = (cls.fixture_root / "valid-mismatch.json").read_bytes()
        cls.base = json.loads(cls.base_bytes.decode("utf-8"))

    def invoke(self, data, *arguments):
        return subprocess.run(
            [str(self.executable), *arguments],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def request_bytes(self, document):
        return (json.dumps(document, separators=(",", ":"), ensure_ascii=False) + "\n").encode()

    def valid(self, document):
        request = self.request_bytes(document)
        first = self.invoke(request)
        second = self.invoke(request)
        self.assertEqual(first.returncode, 0, first.stderr.decode(errors="replace"))
        self.assertEqual(second.returncode, 0, second.stderr.decode(errors="replace"))
        self.assertEqual(first.stderr, b"")
        self.assertEqual(second.stderr, b"")
        self.assertEqual(first.stdout, second.stdout)
        self.assertTrue(first.stdout.endswith(b"\n"))
        return json.loads(first.stdout)

    def invalid(self, data, category):
        result = self.invoke(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertTrue(
            result.stderr.startswith(f"luca-exact-cash: {category}:".encode()),
            result.stderr.decode(errors="replace"),
        )

    def observation(self, account, amount, source):
        result = copy.deepcopy(self.base["observations"][0])
        result["account"] = account
        result["amount"] = amount
        result["provenance"]["source_record_ids"] = [source]
        return result

    def partial(self, account, amount, event, source):
        result = copy.deepcopy(self.base["partials"][0])
        result["account"] = account
        result["amount"] = amount
        result["source_event_ids"] = [event]
        result["source_record_ids"] = [source]
        return result

    def test_integrated_mismatch_and_named_file_input(self):
        first = self.invoke(self.base_bytes)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "request.json"
            path.write_bytes(self.base_bytes)
            second = self.invoke(b"", "--input", str(path))
        self.assertEqual(first.returncode, 0, first.stderr.decode(errors="replace"))
        self.assertEqual(second.returncode, 0, second.stderr.decode(errors="replace"))
        self.assertEqual(first.stdout, second.stdout)

        result = json.loads(first.stdout)
        self.assertEqual(result["schema_version"], "luca.exact-cash-cli.v1")
        self.assertEqual(
            [entry["operation_id"] for entry in result["operation_trace"]],
            ["reduce.cash.exact", "compare.cash.exact"],
        )
        self.assertEqual(result["summary"]["amount_mismatch"], 1)
        self.assertEqual(result["projections"][0]["amount"], "800.000000")
        self.assertEqual(
            result["projections"][0]["source_event_ids"],
            ["cash-event-1", "cash-event-2", "cash-event-3"],
        )
        cash_break = result["breaks"][0]
        self.assertEqual(cash_break["kind"], "amount_mismatch")
        self.assertEqual(cash_break["expected_amount"], "800.000000")
        self.assertEqual(cash_break["observed_amount"], "790.000000")
        self.assertEqual(cash_break["difference"], "-10.000000")
        self.assertEqual(
            cash_break["projection_evidence"]["source_record_ids"],
            ["source.cash.1", "source.cash.2", "source.cash.3"],
        )
        self.assertEqual(
            cash_break["observation_evidence"]["provenance"]["source_record_ids"],
            ["observation.bank.1"],
        )

    def test_exact_missing_and_unexpected(self):
        exact = copy.deepcopy(self.base)
        exact["observations"][0]["amount"] = "800.000000"
        exact_result = self.valid(exact)
        self.assertEqual(exact_result["summary"]["exact"], 1)
        self.assertEqual(exact_result["breaks"], [])
        self.assertEqual(exact_result["matches"][0]["kind"], "exact")
        self.assertEqual(
            exact_result["matches"][0]["projection_evidence"]["source_event_ids"],
            ["cash-event-1", "cash-event-2", "cash-event-3"],
        )
        self.assertEqual(
            exact_result["matches"][0]["observation_evidence"]["provenance"]
            ["source_record_ids"],
            ["observation.bank.1"],
        )

        missing = copy.deepcopy(self.base)
        missing["observations"] = []
        missing_result = self.valid(missing)
        self.assertEqual(missing_result["summary"]["missing_observation"], 1)
        self.assertEqual(missing_result["breaks"][0]["kind"], "missing_observation")
        self.assertIsNotNone(missing_result["breaks"][0]["projection_evidence"])
        self.assertIsNone(missing_result["breaks"][0]["observation_evidence"])

        unexpected = copy.deepcopy(self.base)
        unexpected["partials"] = []
        unexpected_result = self.valid(unexpected)
        self.assertEqual(unexpected_result["summary"]["unexpected_observation"], 1)
        self.assertEqual(unexpected_result["breaks"][0]["kind"], "unexpected_observation")
        self.assertIsNone(unexpected_result["breaks"][0]["projection_evidence"])
        self.assertIsNotNone(unexpected_result["breaks"][0]["observation_evidence"])

    def test_complete_keys_and_breaks_are_deterministically_ordered(self):
        document = copy.deepcopy(self.base)
        document["partials"] = [
            self.partial("z-account", "7.000000", "event-z", "source-z"),
            self.partial("m-account", "5.000000", "event-m", "source-m"),
        ]
        document["observations"] = [
            self.observation("m-account", "4.000000", "observation-m"),
            self.observation("a-account", "9.000000", "observation-a"),
        ]
        result = self.valid(document)
        self.assertEqual(
            [(item["account"], item["currency"]) for item in result["projections"]],
            [("m-account", "USD"), ("z-account", "USD")],
        )
        self.assertEqual(
            [(item["account"], item["kind"]) for item in result["breaks"]],
            [
                ("a-account", "unexpected_observation"),
                ("m-account", "amount_mismatch"),
                ("z-account", "missing_observation"),
            ],
        )

        document["partials"].reverse()
        document["observations"].reverse()
        reordered = self.valid(document)
        self.assertEqual(result, reordered)

    def test_exact_decimal_boundaries(self):
        document = copy.deepcopy(self.base)
        document["partials"] = [
            self.partial(
                "maximum", "9223372036854.775807", "maximum-event", "maximum-source"
            ),
            self.partial(
                "minimum", "-9223372036854.775808", "minimum-event", "minimum-source"
            ),
        ]
        document["observations"] = [
            self.observation("minimum", "-9223372036854.775808", "minimum-observation"),
            self.observation("maximum", "9223372036854.775807", "maximum-observation"),
        ]
        result = self.valid(document)
        self.assertEqual(result["summary"]["exact"], 2)
        self.assertEqual(result["breaks"], [])
        self.assertEqual(
            [item["account"] for item in result["matches"]], ["maximum", "minimum"]
        )
        self.assertEqual(
            [item["amount"] for item in result["projections"]],
            ["9223372036854.775807", "-9223372036854.775808"],
        )

    def test_incompatible_context_duplicate_lineage_and_duplicate_keys(self):
        incompatible = copy.deepcopy(self.base)
        incompatible["observations"][0]["as_of"] = "2026-06-05T23:59:58Z"
        self.invalid(self.request_bytes(incompatible), "observation_time_mismatch")

        duplicate_lineage = copy.deepcopy(self.base)
        duplicate_lineage["partials"][1]["source_event_ids"] = ["cash-event-1"]
        self.invalid(self.request_bytes(duplicate_lineage), "duplicate_event_lineage")

        duplicate_key = copy.deepcopy(self.base)
        duplicate_key["observations"].append(copy.deepcopy(duplicate_key["observations"][0]))
        duplicate_key["observations"][1]["provenance"]["source_record_ids"] = [
            "observation.bank.2"
        ]
        self.invalid(self.request_bytes(duplicate_key), "duplicate_key")

    def test_invalid_provenance_and_overflow(self):
        provenance = copy.deepcopy(self.base)
        provenance["observations"][0]["provenance"]["source_record_ids"] = [
            "observation.bank.1",
            "observation.bank.1",
        ]
        self.invalid(self.request_bytes(provenance), "invalid_provenance")

        overflow = copy.deepcopy(self.base)
        overflow["partials"] = [
            self.partial("overflow", "9223372036854.775807", "maximum", "maximum-source"),
            self.partial("overflow", "0.000001", "plus-one", "plus-one-source"),
        ]
        overflow["observations"] = []
        self.invalid(self.request_bytes(overflow), "amount_overflow")

        comparison_overflow = copy.deepcopy(self.base)
        comparison_overflow["partials"] = [
            self.partial("overflow", "-9223372036854.775808", "minimum", "minimum-source")
        ]
        comparison_overflow["observations"] = [
            self.observation("overflow", "9223372036854.775807", "maximum-observation")
        ]
        self.invalid(self.request_bytes(comparison_overflow), "amount_overflow")

    def test_noncanonical_decimals_and_unsupported_versions(self):
        for amount in ["800", "0800.000000", "+1.000000", "1e0", "-0.000000"]:
            with self.subTest(amount=amount):
                document = copy.deepcopy(self.base)
                document["partials"][0]["amount"] = amount
                self.invalid(self.request_bytes(document), "invalid_decimal")

        unsupported_schema = copy.deepcopy(self.base)
        unsupported_schema["schema_version"] = "luca.exact-cash-cli.v2"
        self.invalid(self.request_bytes(unsupported_schema), "unsupported_schema_version")

        unsupported_operation = copy.deepcopy(self.base)
        unsupported_operation["operations"]["reduction"]["operation_version"] = "2"
        self.invalid(self.request_bytes(unsupported_operation), "unsupported_version")

        unsupported_policy = copy.deepcopy(self.base)
        unsupported_policy["operations"]["comparison"]["policy"]["version"] = "2"
        self.invalid(self.request_bytes(unsupported_policy), "unsupported_version")

    def test_closed_and_bounded_json(self):
        unknown = copy.deepcopy(self.base)
        unknown["host_job_id"] = "hidden-runtime-metadata"
        self.invalid(self.request_bytes(unknown), "unknown_member")

        hostile_name = "host\njob\rid\x1b\x00"
        hostile_unknown = copy.deepcopy(self.base)
        hostile_unknown[hostile_name] = "hidden-runtime-metadata"
        unknown_result = self.invoke(self.request_bytes(hostile_unknown))
        self.assertNotEqual(unknown_result.returncode, 0)
        self.assertEqual(unknown_result.stdout, b"")
        self.assertEqual(
            unknown_result.stderr,
            b"luca-exact-cash: unknown_member: $ contains an unknown member\n",
        )

        duplicate = self.base_bytes.replace(
            b'"schema_version": "luca.exact-cash-cli.v1",',
            b'"schema_version": "luca.exact-cash-cli.v1",\n'
            b'  "schema_version": "luca.exact-cash-cli.v1",',
            1,
        )
        self.invalid(duplicate, "duplicate_member")

        hostile_member = b'"host\\njob\\rid\\u001b\\u0000":null'
        hostile_duplicate = b"{" + hostile_member + b"," + hostile_member + b"}"
        duplicate_result = self.invoke(hostile_duplicate)
        self.assertNotEqual(duplicate_result.returncode, 0)
        self.assertEqual(duplicate_result.stdout, b"")
        self.assertEqual(
            duplicate_result.stderr,
            b"luca-exact-cash: duplicate_member: duplicate JSON member\n",
        )

        malformed = (self.fixture_root / "malformed.json").read_bytes()
        self.invalid(malformed, "invalid_json")
        self.invalid(self.base_bytes + b" trailing", "invalid_json")
        self.invalid(self.base_bytes.replace(b"fund-a", b"fund-\xff", 1), "invalid_utf8")
        self.invalid(b"[" * 18 + b"null" + b"]" * 18, "nesting_limit_exceeded")
        self.invalid(b" " * (1048576 + 1), "input_too_large")

        too_many = copy.deepcopy(self.base)
        too_many["partials"] = [None] * 4097
        self.invalid(self.request_bytes(too_many), "count_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
