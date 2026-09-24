"""Unattended verification for the optional volatility research package."""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "requirements.lock"
EXPECTED_PIP_VERSION = "26.0.1"
EXPECTED_PACKAGE_VERSION = "0.1.0"
DEFAULT_MAX_SYNTHETIC_SECONDS = 30.0


class VerificationError(RuntimeError):
    """Raised when a required verification condition is not met."""


def _locked_versions() -> dict[str, str]:
    locked: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        LOCK_PATH.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
        if match is None:
            raise VerificationError(
                f"{LOCK_PATH}:{line_number} is not an exact name==version pin"
            )
        name, expected = match.groups()
        if name in locked:
            raise VerificationError(f"duplicate requirement in lock: {name}")
        locked[name] = expected
    if not locked:
        raise VerificationError(f"no requirements found in {LOCK_PATH}")
    return locked


def _installed_versions(locked: dict[str, str]) -> dict[str, str]:
    expected = {
        "pip": EXPECTED_PIP_VERSION,
        "luca-research": EXPECTED_PACKAGE_VERSION,
        **locked,
    }
    installed: dict[str, str] = {}
    mismatches: list[str] = []
    for name, expected_version in expected.items():
        try:
            actual_version = version(name)
        except PackageNotFoundError:
            mismatches.append(f"{name}: missing (expected {expected_version})")
            continue
        installed[name] = actual_version
        if actual_version != expected_version:
            mismatches.append(
                f"{name}: installed {actual_version}, expected {expected_version}"
            )
    if mismatches:
        raise VerificationError("version mismatch: " + "; ".join(mismatches))
    return installed


def _run(command: list[str], *, cwd: Path) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        raise VerificationError(
            f"command failed with exit {completed.returncode}: "
            f"{' '.join(command)}\n{output}"
        )
    return completed, elapsed


def _test_summary(output: str) -> tuple[int, list[str], list[str]]:
    match = re.search(r"Ran (\d+) tests? in [0-9.]+s", output)
    if match is None or "\nOK\n" not in f"\n{output}\n":
        raise VerificationError("unittest output did not contain a successful summary")
    lines = [line for line in output.splitlines() if line.strip()]
    test_count = int(match.group(1))
    passed_tests = [line.removesuffix(" ... ok") for line in lines if line.endswith(" ... ok")]
    if len(passed_tests) != test_count:
        raise VerificationError(
            f"unittest reported {test_count} tests but listed {len(passed_tests)} passes"
        )
    return test_count, passed_tests, lines[-4:]


def _synthetic_comparison(max_seconds: float) -> dict[str, Any]:
    from luca_research import run_analysis

    request_path = ROOT / "fixtures" / "synthetic_request.json"
    input_path = ROOT / "fixtures" / "synthetic_spx_like.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    input_document = json.loads(input_path.read_text(encoding="utf-8"))

    api_started = time.perf_counter()
    api_artifact = run_analysis(request, input_document)
    api_seconds = time.perf_counter() - api_started
    if api_artifact.get("status") != "complete":
        raise VerificationError(
            f"synthetic callable API returned {api_artifact.get('status')!r}"
        )

    with tempfile.TemporaryDirectory(prefix="luca-volatility-verify-") as temporary:
        output_path = Path(temporary) / "result.json"
        completed, cli_seconds = _run(
            [
                sys.executable,
                "-m",
                "luca_research",
                "--request",
                str(request_path),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ],
            cwd=ROOT,
        )
        if completed.stdout or completed.stderr:
            raise VerificationError("successful CLI unexpectedly wrote to stdout or stderr")
        cli_artifact = json.loads(output_path.read_text(encoding="utf-8"))

    if cli_artifact != api_artifact:
        raise VerificationError("synthetic CLI and callable API artifacts differ")
    total_seconds = api_seconds + cli_seconds
    if total_seconds > max_seconds:
        raise VerificationError(
            f"synthetic API+CLI runtime {total_seconds:.6f}s exceeded "
            f"the {max_seconds:.6f}s verification budget"
        )
    return {
        "api_seconds": round(api_seconds, 6),
        "artifacts_exactly_equal": True,
        "cli_seconds": round(cli_seconds, 6),
        "evaluation_origin_count": len(api_artifact["evaluation_records"]),
        "max_api_plus_cli_seconds": max_seconds,
        "status": api_artifact["status"],
        "total_seconds": round(total_seconds, 6),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify luca-research in an isolated, exactly pinned environment."
    )
    parser.add_argument(
        "--max-synthetic-seconds",
        default=DEFAULT_MAX_SYNTHETIC_SECONDS,
        type=float,
        help="maximum wall time for one callable and one CLI synthetic analysis",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.prefix == sys.base_prefix:
        raise VerificationError("verification must run inside a virtual environment")
    if not (args.max_synthetic_seconds > 0.0):
        raise VerificationError("--max-synthetic-seconds must be positive")

    locked = _locked_versions()
    installed = _installed_versions(locked)
    pip_check, pip_check_seconds = _run(
        [sys.executable, "-m", "pip", "check"], cwd=ROOT
    )
    tests, test_seconds = _run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
    )
    test_count, passed_tests, test_output_tail = _test_summary(
        tests.stdout + tests.stderr
    )
    synthetic = _synthetic_comparison(args.max_synthetic_seconds)

    result = {
        "environment": {
            "executable": sys.executable,
            "isolated_virtual_environment": True,
            "python": platform.python_version(),
            "versions": installed,
        },
        "pip_check": {
            "elapsed_seconds": round(pip_check_seconds, 6),
            "output": pip_check.stdout.strip(),
        },
        "status": "passed",
        "synthetic_cli_api_comparison": synthetic,
        "unit_tests": {
            "count": test_count,
            "elapsed_seconds": round(test_seconds, 6),
            "output_tail": test_output_tail,
            "passed": passed_tests,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
