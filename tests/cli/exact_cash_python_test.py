#!/usr/bin/env python3

import copy
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

if len(sys.argv) != 4:
    raise RuntimeError(
        "expected CLI executable, fixture directory, and Python adapter directory"
    )
EXECUTABLE = pathlib.Path(sys.argv[1]).resolve()
FIXTURE_ROOT = pathlib.Path(sys.argv[2]).resolve()
PYTHON_ROOT = pathlib.Path(sys.argv[3]).resolve()
del sys.argv[1:]

sys.path.insert(0, str(PYTHON_ROOT))
from luca_exact_cash import (  # noqa: E402
    ExecutableNotFoundError,
    ExecutionTimeoutError,
    InvalidExecutablePathError,
    InvalidResultError,
    Limits,
    MalformedOutputError,
    OutputTooLargeError,
    ProcessExitError,
    ProcessSignalError,
    RequestEncodingError,
    RequestTooLargeError,
    UnexpectedStdoutError,
    UnsupportedResultSchemaError,
    run_exact_cash,
)


class ExactCashPythonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = EXECUTABLE
        cls.fixture_root = FIXTURE_ROOT
        cls.python_root = PYTHON_ROOT
        cls.base_bytes = (cls.fixture_root / "valid-mismatch.json").read_bytes()
        cls.base = json.loads(cls.base_bytes.decode("utf-8"))

    def helper(self, directory, name, source):
        path = pathlib.Path(directory) / name
        path.write_text(
            f"#!{sys.executable}\n{textwrap.dedent(source)}",
            encoding="utf-8",
        )
        path.chmod(0o700)
        return path

    def assert_host_error(self, request, category):
        with self.assertRaises(ProcessExitError) as caught:
            run_exact_cash(request, self.executable)
        self.assertEqual(caught.exception.code, "nonzero_exit")
        self.assertEqual(caught.exception.returncode, 1)
        self.assertEqual(caught.exception.host_category, category)
        return caught.exception

    def test_mismatch_matches_direct_host_and_repeated_calls(self):
        direct = subprocess.run(
            [str(self.executable)],
            input=self.base_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr.decode(errors="replace"))
        self.assertEqual(direct.stderr, b"")

        first = run_exact_cash(self.base, self.executable)
        second = run_exact_cash(self.base, self.executable)
        self.assertEqual(first, second)
        self.assertEqual(first, json.loads(direct.stdout))
        self.assertEqual(first["schema_version"], "luca.exact-cash-cli.v1")
        self.assertEqual(first["summary"]["amount_mismatch"], 1)
        self.assertEqual(first["projections"][0]["amount"], "800.000000")
        self.assertEqual(first["breaks"][0]["difference"], "-10.000000")

    def test_exact_missing_and_unexpected_preserve_host_results(self):
        exact = copy.deepcopy(self.base)
        exact["observations"][0]["amount"] = "800.000000"
        exact_result = run_exact_cash(exact, self.executable)
        self.assertEqual(exact_result["summary"]["exact"], 1)
        self.assertEqual(exact_result["breaks"], [])
        self.assertEqual(exact_result["matches"][0]["kind"], "exact")

        missing = copy.deepcopy(self.base)
        missing["observations"] = []
        missing_result = run_exact_cash(missing, self.executable)
        self.assertEqual(missing_result["summary"]["missing_observation"], 1)
        self.assertEqual(
            missing_result["breaks"][0]["kind"], "missing_observation"
        )

        unexpected = copy.deepcopy(self.base)
        unexpected["partials"] = []
        unexpected_result = run_exact_cash(unexpected, self.executable)
        self.assertEqual(unexpected_result["summary"]["unexpected_observation"], 1)
        self.assertEqual(
            unexpected_result["breaks"][0]["kind"], "unexpected_observation"
        )

    def test_invalid_and_overflow_are_safe_host_diagnostics(self):
        invalid = copy.deepcopy(self.base)
        invalid["partials"][0]["amount"] = "800"
        invalid_error = self.assert_host_error(invalid, "invalid_decimal")

        overflow = copy.deepcopy(self.base)
        overflow["partials"] = [
            copy.deepcopy(self.base["partials"][0]),
            copy.deepcopy(self.base["partials"][1]),
        ]
        overflow["partials"][0]["amount"] = "9223372036854.775807"
        overflow["partials"][0]["source_event_ids"] = ["maximum"]
        overflow["partials"][0]["source_record_ids"] = ["maximum-source"]
        overflow["partials"][1]["amount"] = "0.000001"
        overflow["partials"][1]["source_event_ids"] = ["plus-one"]
        overflow["partials"][1]["source_record_ids"] = ["plus-one-source"]
        overflow["observations"] = []
        overflow_error = self.assert_host_error(overflow, "amount_overflow")

        for error in (invalid_error, overflow_error):
            diagnostic = str(error)
            self.assertNotIn("observation.bank.1", diagnostic)
            self.assertNotIn("source.cash.1", diagnostic)
            self.assertFalse(hasattr(error, "stdout"))
            self.assertFalse(hasattr(error, "stderr"))

    def test_import_has_no_client_side_effects(self):
        program = f"""
            import importlib
            import os
            import shutil
            import socket
            import subprocess
            import sys
            from unittest import mock

            def forbidden(*args, **kwargs):
                raise AssertionError("import attempted a forbidden operation")

            sys.path.insert(0, {str(self.python_root)!r})
            with mock.patch.object(subprocess, "Popen", forbidden), \\
                 mock.patch.object(shutil, "which", forbidden), \\
                 mock.patch.object(socket, "socket", forbidden), \\
                 mock.patch.object(os, "getenv", forbidden):
                module = importlib.import_module("luca_exact_cash")
            assert module.SCHEMA_VERSION == "luca.exact-cash-cli.v1"
        """
        result = subprocess.run(
            [sys.executable, "-I", "-c", textwrap.dedent(program)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout, b"")

    def test_explicit_path_is_not_interpreted_by_a_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            metacharacter_path = pathlib.Path(directory) / "exact-cash; exit 97"
            shutil.copy2(self.executable, metacharacter_path)
            result = run_exact_cash(self.base, metacharacter_path)
        self.assertEqual(result["summary"]["amount_mismatch"], 1)

        with self.assertRaises(InvalidExecutablePathError) as caught:
            run_exact_cash(self.base, "luca-exact-cash")
        self.assertEqual(caught.exception.code, "invalid_executable_path")

    def test_timeout_missing_executable_and_signal_are_typed(self):
        with tempfile.TemporaryDirectory() as directory:
            sleeper = self.helper(
                directory,
                "sleeper",
                """
                import time
                time.sleep(2)
                """,
            )
            with self.assertRaises(ExecutionTimeoutError) as timeout:
                run_exact_cash(
                    {}, sleeper, limits=Limits(timeout_seconds=0.05)
                )
            self.assertEqual(timeout.exception.code, "timeout")

            missing = pathlib.Path(directory) / "missing-executable"
            with self.assertRaises(ExecutableNotFoundError) as not_found:
                run_exact_cash({}, missing)
            self.assertEqual(not_found.exception.code, "executable_not_found")

            if os.name == "posix":
                signaled = self.helper(
                    directory,
                    "signaled",
                    """
                    import os
                    import signal
                    os.kill(os.getpid(), signal.SIGTERM)
                    """,
                )
                with self.assertRaises(ProcessSignalError) as terminated:
                    run_exact_cash({}, signaled)
                self.assertEqual(terminated.exception.code, "signal_termination")
                self.assertEqual(terminated.exception.signal_number, signal.SIGTERM)

    @unittest.skipUnless(os.name == "posix", "process-group semantics require POSIX")
    def test_timeout_covers_descendants_that_inherit_output_pipes(self):
        with tempfile.TemporaryDirectory() as directory:
            survivor_marker = pathlib.Path(directory) / "descendant-survived"
            inherited_pipes = self.helper(
                directory,
                "inherited-pipes",
                f"""
                import os
                import pathlib
                import time

                if os.fork() == 0:
                    time.sleep(0.4)
                    pathlib.Path({str(survivor_marker)!r}).write_text("survived")
                    os._exit(0)
                os._exit(0)
                """,
            )
            started_at = time.monotonic()
            with self.assertRaises(ExecutionTimeoutError) as timeout:
                run_exact_cash(
                    {},
                    inherited_pipes,
                    limits=Limits(timeout_seconds=0.2),
                )
            elapsed = time.monotonic() - started_at

            self.assertEqual(timeout.exception.code, "timeout")
            self.assertLess(elapsed, 1.0)
            time.sleep(0.5)
            self.assertFalse(survivor_marker.exists())

    def test_nonzero_diagnostic_does_not_expose_tool_output(self):
        secret = "observation-secret-with-complete-lineage"
        with tempfile.TemporaryDirectory() as directory:
            failure = self.helper(
                directory,
                "failure",
                f"""
                import sys
                sys.stderr.write(
                    "luca-exact-cash: fixture_failure: {secret}\\n"
                )
                raise SystemExit(7)
                """,
            )
            with self.assertRaises(ProcessExitError) as caught:
                run_exact_cash(self.base, failure)
        self.assertEqual(caught.exception.returncode, 7)
        self.assertEqual(caught.exception.host_category, "fixture_failure")
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(hasattr(caught.exception, "stderr"))

    def test_malformed_extra_and_invalid_result_envelopes_are_typed(self):
        valid_envelope = {
            "schema_version": "luca.exact-cash-cli.v1",
            "operation_trace": [],
            "projections": [],
            "matches": [],
            "breaks": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            malformed = self.helper(
                directory,
                "malformed",
                """
                import sys
                sys.stdout.buffer.write(b"not-json")
                """,
            )
            with self.assertRaises(MalformedOutputError) as malformed_error:
                run_exact_cash({}, malformed)
            self.assertEqual(malformed_error.exception.code, "malformed_output")

            encoded_envelope = json.dumps(valid_envelope)
            extra = self.helper(
                directory,
                "extra",
                f"""
                import sys
                sys.stdout.write({encoded_envelope!r} + "\\nextra\\n")
                """,
            )
            with self.assertRaises(UnexpectedStdoutError) as unexpected:
                run_exact_cash({}, extra)
            self.assertEqual(unexpected.exception.code, "unexpected_stdout")

            wrong_schema = copy.deepcopy(valid_envelope)
            wrong_schema["schema_version"] = "luca.exact-cash-cli.v2"
            schema = self.helper(
                directory,
                "wrong-schema",
                f"""
                import sys
                sys.stdout.write({json.dumps(wrong_schema)!r})
                """,
            )
            with self.assertRaises(UnsupportedResultSchemaError) as unsupported:
                run_exact_cash({}, schema)
            self.assertEqual(
                unsupported.exception.code, "unsupported_result_schema"
            )

            missing_collection = copy.deepcopy(valid_envelope)
            del missing_collection["breaks"]
            invalid = self.helper(
                directory,
                "invalid-result",
                f"""
                import sys
                sys.stdout.write({json.dumps(missing_collection)!r})
                """,
            )
            with self.assertRaises(InvalidResultError) as invalid_result:
                run_exact_cash({}, invalid)
            self.assertEqual(invalid_result.exception.code, "invalid_result")

    def test_request_stdout_and_stderr_limits_are_enforced(self):
        with self.assertRaises(RequestTooLargeError) as request_limit:
            run_exact_cash(
                {"payload": "too large"},
                self.executable,
                limits=Limits(max_request_bytes=8),
            )
        self.assertEqual(request_limit.exception.code, "request_too_large")

        very_large_scalar = "x" * (4 * 1024 * 1024)
        with mock.patch.object(
            json.encoder,
            "encode_basestring",
            side_effect=AssertionError("over-limit scalar reached JSON encoding"),
        ):
            with self.assertRaises(RequestTooLargeError) as scalar_limit:
                run_exact_cash(
                    {"payload": very_large_scalar},
                    self.executable,
                    limits=Limits(max_request_bytes=64),
                )
        self.assertEqual(scalar_limit.exception.code, "request_too_large")

        with self.assertRaises(RequestEncodingError) as encoding_error:
            run_exact_cash({"value": float("nan")}, self.executable)
        self.assertEqual(encoding_error.exception.code, "invalid_request")

        with tempfile.TemporaryDirectory() as directory:
            large_stdout = self.helper(
                directory,
                "large-stdout",
                """
                import sys
                sys.stdout.buffer.write(b"x" * 257)
                """,
            )
            with self.assertRaises(OutputTooLargeError) as stdout_limit:
                run_exact_cash(
                    {}, large_stdout, limits=Limits(max_stdout_bytes=256)
                )
            self.assertEqual(stdout_limit.exception.code, "stdout_too_large")
            self.assertEqual(stdout_limit.exception.stream, "stdout")

            large_stderr = self.helper(
                directory,
                "large-stderr",
                """
                import sys
                sys.stderr.buffer.write(b"x" * 257)
                """,
            )
            with self.assertRaises(OutputTooLargeError) as stderr_limit:
                run_exact_cash(
                    {}, large_stderr, limits=Limits(max_stderr_bytes=256)
                )
            self.assertEqual(stderr_limit.exception.code, "stderr_too_large")
            self.assertEqual(stderr_limit.exception.stream, "stderr")


if __name__ == "__main__":
    unittest.main()
