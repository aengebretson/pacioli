"""Bounded standard-library client for the ``luca-exact-cash`` host.

Importing this module only defines Python values. Callers must supply both the
JSON-compatible request and an explicit path to the executable.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, BinaryIO

SCHEMA_VERSION = "luca.exact-cash-cli.v1"
_RESULT_COLLECTIONS = ("operation_trace", "projections", "matches", "breaks")
_READ_CHUNK_SIZE = 64 * 1024
_HOST_CATEGORY = re.compile(br"\Aluca-exact-cash: ([a-z][a-z0-9_]{0,63}):")


class ExactCashClientError(Exception):
    """Base class for stable adapter diagnostics."""

    code = "client_error"


class InvalidLimitsError(ExactCashClientError):
    code = "invalid_limits"

    def __init__(self) -> None:
        super().__init__("exact-cash client limits must be finite and positive")


class InvalidExecutablePathError(ExactCashClientError):
    code = "invalid_executable_path"

    def __init__(self) -> None:
        super().__init__("an explicit exact-cash executable path is required")


class RequestEncodingError(ExactCashClientError):
    code = "invalid_request"

    def __init__(self) -> None:
        super().__init__("exact-cash request is not bounded UTF-8 JSON")


class RequestTooLargeError(ExactCashClientError):
    code = "request_too_large"

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"exact-cash request exceeds the {limit}-byte client limit")


class ExecutableNotFoundError(ExactCashClientError):
    code = "executable_not_found"

    def __init__(self) -> None:
        super().__init__("exact-cash executable was not found")


class ExecutableLaunchError(ExactCashClientError):
    code = "executable_launch_failed"

    def __init__(self) -> None:
        super().__init__("exact-cash executable could not be started")


class ExecutionTimeoutError(ExactCashClientError):
    code = "timeout"

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"exact-cash executable exceeded the {timeout_seconds:g}-second timeout"
        )


class OutputTooLargeError(ExactCashClientError):
    def __init__(self, stream: str, limit: int) -> None:
        self.stream = stream
        self.limit = limit
        self.code = f"{stream}_too_large"
        super().__init__(
            f"exact-cash executable {stream} exceeds the {limit}-byte client limit"
        )


class ProcessSignalError(ExactCashClientError):
    code = "signal_termination"

    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number
        super().__init__(f"exact-cash executable terminated by signal {signal_number}")


class ProcessExitError(ExactCashClientError):
    code = "nonzero_exit"

    def __init__(self, returncode: int, host_category: str | None) -> None:
        self.returncode = returncode
        self.host_category = host_category
        detail = f" with host category {host_category}" if host_category else ""
        super().__init__(
            f"exact-cash executable exited with status {returncode}{detail}"
        )


class ProcessCommunicationError(ExactCashClientError):
    code = "process_communication_failed"

    def __init__(self) -> None:
        super().__init__("exact-cash executable communication failed")


class MalformedOutputError(ExactCashClientError):
    code = "malformed_output"

    def __init__(self) -> None:
        super().__init__("exact-cash executable did not return valid UTF-8 JSON")


class UnexpectedStdoutError(ExactCashClientError):
    code = "unexpected_stdout"

    def __init__(self) -> None:
        super().__init__("exact-cash executable returned extra standard output")


class UnsupportedResultSchemaError(ExactCashClientError):
    code = "unsupported_result_schema"

    def __init__(self) -> None:
        super().__init__("exact-cash executable returned an unsupported schema")


class InvalidResultError(ExactCashClientError):
    code = "invalid_result"

    def __init__(self) -> None:
        super().__init__("exact-cash executable returned an invalid result envelope")


@dataclass(frozen=True)
class Limits:
    """Resource limits applied to one host invocation."""

    timeout_seconds: float = 10.0
    max_request_bytes: int = 1024 * 1024
    max_stdout_bytes: int = 16 * 1024 * 1024
    max_stderr_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        valid_timeout = (
            isinstance(self.timeout_seconds, (int, float))
            and not isinstance(self.timeout_seconds, bool)
            and math.isfinite(self.timeout_seconds)
            and self.timeout_seconds > 0
        )
        byte_limits = (
            self.max_request_bytes,
            self.max_stdout_bytes,
            self.max_stderr_bytes,
        )
        if not valid_timeout or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in byte_limits
        ):
            raise InvalidLimitsError


class _RequestSizeBudget:
    def __init__(self, limit: int) -> None:
        self.remaining = limit

    def consume(self, size: int, limit: int) -> None:
        if size > self.remaining:
            raise RequestTooLargeError(limit)
        self.remaining -= size


def _measure_json_string(
    value: str, budget: _RequestSizeBudget, limit: int
) -> None:
    budget.consume(1, limit)
    for character in value:
        code_point = ord(character)
        if character in {'"', "\\", "\b", "\f", "\n", "\r", "\t"}:
            size = 2
        elif code_point <= 0x1F:
            size = 6
        elif 0xD800 <= code_point <= 0xDFFF:
            raise RequestEncodingError
        elif code_point <= 0x7F:
            size = 1
        elif code_point <= 0x7FF:
            size = 2
        elif code_point <= 0xFFFF:
            size = 3
        else:
            size = 4
        budget.consume(size, limit)
    budget.consume(1, limit)


def _bounded_integer_text(value: int, maximum: int, limit: int) -> str:
    negative = value < 0
    magnitude = -value if negative else value
    digit_capacity = maximum - int(negative)
    if digit_capacity <= 0:
        raise RequestTooLargeError(limit)

    if magnitude:
        bits = magnitude.bit_length()
        maximum_digits = (bits * 30103 + 99999) // 100000
        if maximum_digits > digit_capacity and magnitude >= 10**digit_capacity:
            raise RequestTooLargeError(limit)

    text = int.__repr__(value)
    if len(text) > maximum:
        raise RequestTooLargeError(limit)
    return text


def _measure_json_value(
    value: Any,
    budget: _RequestSizeBudget,
    markers: set[int],
    limit: int,
) -> None:
    if isinstance(value, str):
        _measure_json_string(value, budget, limit)
        return
    if value is None:
        budget.consume(4, limit)
        return
    if value is True:
        budget.consume(4, limit)
        return
    if value is False:
        budget.consume(5, limit)
        return
    if isinstance(value, int):
        budget.consume(
            len(_bounded_integer_text(value, budget.remaining, limit)), limit
        )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RequestEncodingError
        budget.consume(len(float.__repr__(value)), limit)
        return

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in markers:
            raise RequestEncodingError
        markers.add(marker)
        try:
            budget.consume(1, limit)
            for index, member in enumerate(value):
                if index:
                    budget.consume(1, limit)
                _measure_json_value(member, budget, markers, limit)
            budget.consume(1, limit)
        finally:
            markers.remove(marker)
        return

    if isinstance(value, dict):
        marker = id(value)
        if marker in markers:
            raise RequestEncodingError
        markers.add(marker)
        try:
            budget.consume(1, limit)
            for index, (key, member) in enumerate(value.items()):
                if index:
                    budget.consume(1, limit)
                if isinstance(key, str):
                    key_text = key
                elif key is None:
                    key_text = "null"
                elif key is True:
                    key_text = "true"
                elif key is False:
                    key_text = "false"
                elif isinstance(key, int):
                    key_text = _bounded_integer_text(
                        key, budget.remaining, limit
                    )
                elif isinstance(key, float) and math.isfinite(key):
                    key_text = float.__repr__(key)
                else:
                    raise RequestEncodingError
                _measure_json_string(key_text, budget, limit)
                budget.consume(1, limit)
                _measure_json_value(member, budget, markers, limit)
            budget.consume(1, limit)
        finally:
            markers.remove(marker)
        return

    raise RequestEncodingError


def _serialize_request(request: Any, limit: int) -> bytes:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    encoded = bytearray()
    try:
        _measure_json_value(request, _RequestSizeBudget(limit), set(), limit)
        for fragment in encoder.iterencode(request):
            chunk = fragment.encode("utf-8")
            if len(encoded) + len(chunk) > limit:
                raise RequestTooLargeError(limit)
            encoded.extend(chunk)
    except RequestTooLargeError:
        raise
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError):
        raise RequestEncodingError from None
    return bytes(encoded)


def _read_bounded(
    stream: BinaryIO,
    name: str,
    limit: int,
    output: bytearray,
    exceeded: set[str],
    failures: set[str],
    state_lock: threading.Lock,
    state_changed: threading.Event,
) -> None:
    read = getattr(stream, "read1", stream.read)
    try:
        while True:
            remaining = limit - len(output)
            chunk = read(min(_READ_CHUNK_SIZE, remaining + 1))
            if not chunk:
                return
            if len(chunk) > remaining:
                output.extend(chunk[:remaining])
                with state_lock:
                    exceeded.add(name)
                state_changed.set()
                return
            output.extend(chunk)
    except OSError:
        with state_lock:
            failures.add(name)
        state_changed.set()
    finally:
        state_changed.set()


def _write_request(
    stream: BinaryIO,
    request: bytes,
    failures: set[str],
    state_lock: threading.Lock,
    state_changed: threading.Event,
) -> None:
    try:
        stream.write(request)
        stream.flush()
    except BrokenPipeError:
        pass
    except OSError:
        with state_lock:
            failures.add("stdin")
        state_changed.set()
    finally:
        try:
            stream.close()
        except OSError:
            pass
        state_changed.set()


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def _communicate_bounded(
    executable: str, request: bytes, limits: Limits
) -> tuple[int, bytes, bytes]:
    started_at = time.monotonic()
    try:
        process = subprocess.Popen(
            [executable],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name == "posix",
        )
    except FileNotFoundError:
        raise ExecutableNotFoundError from None
    except (OSError, ValueError):
        raise ExecutableLaunchError from None

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = bytearray()
    stderr = bytearray()
    exceeded: set[str] = set()
    failures: set[str] = set()
    state_lock = threading.Lock()
    state_changed = threading.Event()
    threads = [
        threading.Thread(
            target=_read_bounded,
            args=(
                process.stdout,
                "stdout",
                limits.max_stdout_bytes,
                stdout,
                exceeded,
                failures,
                state_lock,
                state_changed,
            ),
            daemon=True,
        ),
        threading.Thread(
            target=_read_bounded,
            args=(
                process.stderr,
                "stderr",
                limits.max_stderr_bytes,
                stderr,
                exceeded,
                failures,
                state_lock,
                state_changed,
            ),
            daemon=True,
        ),
        threading.Thread(
            target=_write_request,
            args=(process.stdin, request, failures, state_lock, state_changed),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    deadline = started_at + limits.timeout_seconds
    stop_reason: str | None = None
    while True:
        with state_lock:
            if exceeded:
                stop_reason = "output_limit"
                break
        communication_finished = not any(thread.is_alive() for thread in threads)
        if process.poll() is not None and communication_finished:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stop_reason = "timeout"
            break
        state_changed.wait(min(remaining, 0.05))
        state_changed.clear()

    if stop_reason is not None:
        _terminate(process)

    remaining = max(0.0, deadline - time.monotonic())
    if process.poll() is None and remaining:
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            pass
    for thread in threads:
        remaining = max(0.0, deadline - time.monotonic())
        if not remaining:
            break
        thread.join(timeout=remaining)

    threads_alive = any(thread.is_alive() for thread in threads)
    if not threads_alive:
        try:
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()
        except (OSError, ValueError):
            pass

    with state_lock:
        output_limits = set(exceeded)
        communication_failures = set(failures)
    if "stdout" in output_limits:
        raise OutputTooLargeError("stdout", limits.max_stdout_bytes)
    if "stderr" in output_limits:
        raise OutputTooLargeError("stderr", limits.max_stderr_bytes)
    if stop_reason == "timeout":
        raise ExecutionTimeoutError(limits.timeout_seconds)
    returncode = process.poll()
    if communication_failures or threads_alive or returncode is None:
        raise ProcessCommunicationError
    return returncode, bytes(stdout), bytes(stderr)


def _host_category(stderr: bytes) -> str | None:
    match = _HOST_CATEGORY.match(stderr)
    if match is None:
        return None
    return match.group(1).decode("ascii")


class _DuplicateMember(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateMember
        result[key] = value
    return result


def _reject_constant(_: str) -> Any:
    raise ValueError


def _parse_result(stdout: bytes) -> dict[str, Any]:
    try:
        text = stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise MalformedOutputError from None

    decoder = json.JSONDecoder(
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    start = len(text) - len(text.lstrip(" \t\r\n"))
    try:
        result, end = decoder.raw_decode(text, start)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError):
        raise MalformedOutputError from None
    if text[end:].strip(" \t\r\n"):
        raise UnexpectedStdoutError
    if not isinstance(result, dict):
        raise InvalidResultError
    if result.get("schema_version") != SCHEMA_VERSION:
        raise UnsupportedResultSchemaError
    if any(not isinstance(result.get(member), list) for member in _RESULT_COLLECTIONS):
        raise InvalidResultError
    return result


def run_exact_cash(
    request: Any,
    executable: str | os.PathLike[str],
    *,
    limits: Limits | None = None,
) -> dict[str, Any]:
    """Evaluate one explicit v1 request through the named C++ host.

    The adapter validates transport and result-envelope properties only. The
    executable remains the sole implementation of financial validation,
    reduction, and comparison arithmetic.
    """

    active_limits = limits if limits is not None else Limits()
    if not isinstance(active_limits, Limits):
        raise InvalidLimitsError
    try:
        executable_text = os.fspath(executable)
    except TypeError:
        raise InvalidExecutablePathError from None
    if (
        not isinstance(executable_text, str)
        or not executable_text
        or not os.path.dirname(executable_text)
    ):
        raise InvalidExecutablePathError

    encoded_request = _serialize_request(request, active_limits.max_request_bytes)
    returncode, stdout, stderr = _communicate_bounded(
        executable_text, encoded_request, active_limits
    )
    if returncode < 0:
        raise ProcessSignalError(-returncode)
    if returncode != 0:
        raise ProcessExitError(returncode, _host_category(stderr))
    return _parse_result(stdout)


__all__ = [
    "SCHEMA_VERSION",
    "ExactCashClientError",
    "ExecutableLaunchError",
    "ExecutableNotFoundError",
    "ExecutionTimeoutError",
    "InvalidExecutablePathError",
    "InvalidLimitsError",
    "InvalidResultError",
    "Limits",
    "MalformedOutputError",
    "OutputTooLargeError",
    "ProcessCommunicationError",
    "ProcessExitError",
    "ProcessSignalError",
    "RequestEncodingError",
    "RequestTooLargeError",
    "UnexpectedStdoutError",
    "UnsupportedResultSchemaError",
    "run_exact_cash",
]
