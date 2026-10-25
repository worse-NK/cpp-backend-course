#!/usr/bin/env python3
"""Bounded, read-only load experiment for your own loopback Task API (Linux).

Python 3.10+, standard library only. No shell, DNS, proxies or redirects.
The private client.curl file is parsed as data, never passed to curl/executed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import sys
import threading
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
MAX_TASKS = 1000
MAX_NUMBER = (1 << 63) - 1
DEFAULT_MAX_RESPONSE = 1024 * 1024
MAX_RESPONSE_HEADERS = 16 * 1024


class Refused(Exception):
    """Only static, non-secret diagnostics belong in this exception."""


class InvalidResponse(Exception):
    pass


class _HeaderBudgetReader:
    """Bound readline allocations while HTTPResponse parses status + headers."""

    def __init__(self, source):
        self.source = source
        self.remaining = MAX_RESPONSE_HEADERS
        self.enabled = True

    def readline(self, limit=-1):
        if not self.enabled:
            return self.source.readline(limit)
        limit = min(limit, self.remaining + 1) if limit >= 0 else self.remaining + 1
        result = self.source.readline(limit)
        self.remaining -= len(result)
        if self.remaining < 0:
            raise InvalidResponse
        return result

    def __getattr__(self, name):
        return getattr(self.source, name)


class _BoundedResponse(http.client.HTTPResponse):
    def __init__(self, *arguments, **options):
        super().__init__(*arguments, **options)
        self.fp = _HeaderBudgetReader(self.fp)

    def begin(self):
        super().begin()
        self.fp.enabled = False


@dataclass(frozen=True)
class Target:
    host: str
    port: int

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"


@dataclass(frozen=True)
class Sample:
    outcome: str
    status: int | None
    elapsed_ms: float


def loopback_target(value: str) -> Target:
    """Accept an origin, not a general URL: literal loopback + explicit port."""
    try:
        if (not value.isascii() or any(character.isspace() for character in value)
                or any(character in value for character in "\\%?#")):
            raise ValueError
        parsed = urlsplit(value)
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
        if (parsed.scheme != "http" or not address.is_loopback
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or port is None
                or not 1024 <= port <= 65535):
            raise ValueError
        return Target(str(address), port)
    except ValueError as error:
        raise Refused("use only http://127.0.0.1:PORT or http://[::1]:PORT; "
                      "an explicit port from 1024 to 65535 is required") from error


def read_token(path: Path) -> str:
    """No symlink components, private parent, owned single-link regular file."""
    absolute = path.absolute()
    if ".." in absolute.parts or not absolute.name:
        raise Refused("client config path must not contain parent traversal")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in absolute.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise Refused("client config must be inside an owned 0700 private directory")
        descriptor = os.open(absolute.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
                raise Refused("client config must be an owned single-link regular 0600 file")
            content = source.read(4097)
    finally:
        os.close(directory)
    if len(content) > 4096:
        raise Refused("client config exceeds the 4096-byte limit")
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeError as error:
        raise Refused("client config must have the generated ASCII format") from error
    # Do not interpret general curl configuration. These are precisely the
    # non-secret lines produced by lab.py; none are executed by this program.
    harmless = {
        'noproxy = "127.0.0.1,localhost,::1"', "connect-timeout = 2", "max-time = 5",
        "fail-with-body", "silent", "show-error",
    }
    tokens = []
    for line in lines:
        match = re.fullmatch(r'header = "Authorization: Bearer ([0-9a-f]{64})"', line)
        if match:
            tokens.append(match.group(1))
        elif line not in harmless:
            raise Refused("client config must have the format generated by lab.py init")
    if len(tokens) != 1:
        raise Refused("client config must contain exactly one generated Bearer header")
    return tokens[0]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidResponse
        result[key] = value
    return result


def _invalid_constant(_: str) -> None:
    raise InvalidResponse


def validate_tasks(body: bytes) -> None:
    """Validate the exact GET /tasks contract, never print task contents."""
    try:
        tasks = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        if type(tasks) is not list or len(tasks) > MAX_TASKS:
            raise InvalidResponse
        previous = 0
        for task in tasks:
            if type(task) is not dict or set(task) != {"id", "title", "done", "version"}:
                raise InvalidResponse
            if (type(task["id"]) is not int or not previous < task["id"] <= MAX_NUMBER
                    or type(task["version"]) is not int or not 1 <= task["version"] <= MAX_NUMBER
                    or type(task["done"]) is not bool or type(task["title"]) is not str
                    or "\0" in task["title"] or not 1 <= len(task["title"].encode("utf-8")) <= 200):
                raise InvalidResponse
            previous = task["id"]
    except (ValueError, UnicodeError, RecursionError) as error:
        raise InvalidResponse from error


def _interrupt(connected: socket.socket) -> None:
    # A socket timeout is not a total deadline: a slow peer can periodically
    # supply another byte. Shut down this request's socket at its total deadline.
    # Never close a different/reused file descriptor or another worker's socket.
    try:
        connected.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def request_once(target: Target, token: str, timeout: float, max_response: int,
                 global_deadline: float) -> Sample:
    start = time.monotonic()
    deadline = min(global_deadline, start + timeout)
    status = None
    timer = None
    connection = http.client.HTTPConnection(target.host, target.port,
                                             timeout=max(0.001, deadline - start))
    connection.response_class = _BoundedResponse
    outcome = "transport"
    try:
        if deadline <= time.monotonic():
            raise TimeoutError
        connection.connect()
        # HTTPConnection uses the literal target directly: no proxy environment
        # and no redirect handler. One connection per request, no hidden retries.
        connected = connection.sock
        if connected is None or time.monotonic() >= deadline:
            raise TimeoutError
        connected.settimeout(max(0.001, deadline - time.monotonic()))
        timer = threading.Timer(max(0, deadline - time.monotonic()), _interrupt,
                                args=(connected,))
        timer.daemon = True
        timer.start()
        connection.request("GET", "/tasks", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json", "Accept-Encoding": "identity",
            "Connection": "close",
        })
        with connection.getresponse() as response:
            status = response.status
            if 300 <= status <= 399:
                return Sample("redirect", status, (time.monotonic() - start) * 1000)
            lengths = response.headers.get_all("Content-Length", [])
            encodings = response.headers.get_all("Content-Encoding", [])
            # The workshop sends Content-Length, not a streaming/chunked list.
            # Refuse other framing instead of letting it bypass byte budgets.
            if (response.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1
                    or not re.fullmatch(r"[0-9]{1,9}", lengths[0])
                    or int(lengths[0]) > max_response
                    or (encodings and encodings != ["identity"])):
                raise InvalidResponse
            length = int(lengths[0])
            body = response.read(length + 1)
            if len(body) != length or time.monotonic() >= deadline:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                raise InvalidResponse
            if status == 200:
                types = response.headers.get_all("Content-Type", [])
                if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
                    raise InvalidResponse
                validate_tasks(body)
                outcome = "valid"
            elif status == 401:
                outcome = "auth_401"
            elif status == 503:
                outcome = "unavailable_503"
            else:
                outcome = "http_other"
    except InvalidResponse:
        outcome = "timeout" if time.monotonic() >= deadline else "invalid_response"
    except (TimeoutError, socket.timeout):
        outcome = "timeout"
    except (http.client.HTTPException, OSError):
        outcome = "timeout" if time.monotonic() >= deadline else "transport"
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()
    return Sample(outcome, status, (time.monotonic() - start) * 1000)


def percentiles(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(values)
    return {f"p{percentile}": (round(ordered[math.ceil(percentile / 100 * len(ordered)) - 1], 3)
                                if ordered else None)
            for percentile in (50, 95, 99)}


def run_phase(name: str, target: Target, token: str, *, workers: int, requests: int,
              timeout: float, max_response: int, deadline: float,
              request_function=request_once) -> dict[str, object]:
    start = time.monotonic()
    lock = threading.Lock()
    stop = threading.Event()
    next_request = 0
    samples: list[Sample] = []

    def worker() -> None:
        nonlocal next_request
        while not stop.is_set() and time.monotonic() < deadline:
            with lock:
                if next_request >= requests or stop.is_set():
                    return
                next_request += 1
            sample = request_function(target, token, timeout, max_response, deadline)
            with lock:
                samples.append(sample)
            # Wrong credentials, another service or a redirect are not a reason
            # to keep sending load. Already in-flight requests finish boundedly.
            if sample.outcome in {"auth_401", "invalid_response", "redirect", "http_other"}:
                stop.set()

    # Submit only one loop per worker; no unbounded queue of request futures.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker) for _ in range(workers)]
        try:
            for future in futures:
                future.result()
        except BaseException:
            # In particular, Ctrl-C must stop dispatch, not merely wait while
            # workers continue the rest of the scenario behind the user's back.
            stop.set()
            raise
    elapsed = time.monotonic() - start
    outcomes = Counter(sample.outcome for sample in samples)
    statuses = Counter(str(sample.status) for sample in samples if sample.status is not None)
    valid = outcomes.get("valid", 0)
    return {
        "phase": name, "workers": workers, "requested": requests,
        "completed": len(samples), "not_started": requests - len(samples),
        "valid_tasks_responses": valid, "outcomes": dict(sorted(outcomes.items())),
        "http_statuses": dict(sorted(statuses.items())), "elapsed_s": round(elapsed, 6),
        "valid_responses_per_s": round(valid / elapsed, 3) if elapsed else 0.0,
        "all_latency_samples": len(samples),
        "all_latency_ms": percentiles([sample.elapsed_ms for sample in samples]),
        "valid_latency_samples": valid,
        "valid_latency_ms": percentiles([sample.elapsed_ms for sample in samples
                                         if sample.outcome == "valid"]),
        "deadline_reached": time.monotonic() >= deadline,
    }


def bounded_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("expected an integer") from error
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"expected {minimum}..{maximum}")
        return number
    return parse


def bounded_float(minimum: float, maximum: float):
    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("expected a finite number") from error
        if not math.isfinite(number) or not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"expected {minimum}..{maximum}")
        return number
    return parse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080",
                        help="literal loopback origin only; never a public URL")
    parser.add_argument("--client-config", type=Path, default=ROOT / ".secrets/client.curl",
                        help="private generated client.curl; no token argument exists")
    parser.add_argument("--phase", choices=("all", "baseline", "load", "recovery"), default="all")
    parser.add_argument("--workers", type=bounded_int(1, 8), default=4,
                        help="closed-concurrency workers for load (1..8), not fixed RPS")
    parser.add_argument("--requests", type=bounded_int(1, 400), default=40,
                        help="total requests in load, not requests per worker")
    parser.add_argument("--baseline-requests", type=bounded_int(1, 50), default=10)
    parser.add_argument("--recovery-requests", type=bounded_int(1, 50), default=10)
    parser.add_argument("--warmup", type=bounded_int(0, 20), default=4,
                        help="separately reported warm-up; never merged into measured phases")
    parser.add_argument("--timeout", type=bounded_float(0.05, 5), default=2.0,
                        help="per-request total I/O deadline in seconds")
    parser.add_argument("--max-runtime", type=bounded_float(0.1, 60), default=30.0,
                        help="whole-scenario I/O budget, including pauses, at most 60 seconds")
    parser.add_argument("--max-response-bytes", type=bounded_int(1024, 2 * 1024 * 1024),
                        default=DEFAULT_MAX_RESPONSE)
    parser.add_argument("--json", action="store_true", help="safe aggregate JSON, no payloads or secrets")
    arguments = parser.parse_args(argv)
    try:
        target = loopback_target(arguments.base_url)
        token = read_token(arguments.client_config)
        plan = []
        if arguments.warmup:
            plan.append(("warmup", 1, arguments.warmup))
        for name, workers, requests in (("baseline", 1, arguments.baseline_requests),
                                         ("load", arguments.workers, arguments.requests),
                                         ("recovery", 1, arguments.recovery_requests)):
            if arguments.phase in ("all", name):
                plan.append((name, workers, requests))
        if sum(requests for _, _, requests in plan) > 500:
            raise Refused("the complete scenario must not exceed 500 requests")
        deadline = time.monotonic() + arguments.max_runtime
        phases = []
        aborted = False
        for name, workers, requests in plan:
            if time.monotonic() >= deadline:
                aborted = True
                break
            if phases:
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
            result = run_phase(name, target, token, workers=workers, requests=requests,
                               timeout=arguments.timeout, max_response=arguments.max_response_bytes,
                               deadline=deadline)
            phases.append(result)
            outcomes = result["outcomes"]
            if (any(outcomes.get(reason, 0) for reason in
                    ("auth_401", "invalid_response", "redirect", "http_other"))
                    or (name == "warmup" and result["valid_tasks_responses"] != requests)):
                aborted = True
                break
        ok = (not aborted and len(phases) == len(plan)
              and all(result["valid_tasks_responses"] == result["requested"] for result in phases))
        report = {"target": target.url, "method": "GET", "path": "/tasks",
                  "model": "closed concurrency; new TCP connection per request; no retries",
                  "per_request_timeout_s": arguments.timeout,
                  "max_runtime_s": arguments.max_runtime,
                  "max_response_bytes": arguments.max_response_bytes,
                  "max_response_header_bytes": MAX_RESPONSE_HEADERS,
                  "planned_requests": sum(requests for _, _, requests in plan),
                  "phases": phases, "aborted": aborted, "ok": ok}
        if arguments.json:
            print(json.dumps(report, sort_keys=True, allow_nan=False))
        else:
            print(f"GET {target.url}/tasks — closed concurrency; a new TCP connection per request")
            print("No retries or redirects. Warm-up is separate. Percentiles use nearest rank;")
            print("with fewer than 100 samples p99 is effectively an extreme, not a reliable tail estimate.")
            for result in phases:
                print(f"\n{result['phase']}: workers={result['workers']} "
                      f"completed={result['completed']}/{result['requested']} "
                      f"valid={result['valid_tasks_responses']} not_started={result['not_started']}")
                print("  outcomes=" + json.dumps(result["outcomes"], sort_keys=True))
                print("  HTTP statuses=" + json.dumps(result["http_statuses"], sort_keys=True))
                print(f"  valid responses/s={result['valid_responses_per_s']}; "
                      f"elapsed={result['elapsed_s']}s")
                print(f"  all latency ms (n={result['all_latency_samples']}): "
                      + json.dumps(result["all_latency_ms"]))
                print(f"  valid latency ms (n={result['valid_latency_samples']}): "
                      + json.dumps(result["valid_latency_ms"]))
            print("\nPASS: all planned responses matched GET /tasks" if ok else
                  "\nNOT PASS: inspect counts/statuses; do not report errors or skipped requests as throughput")
        return 0 if ok else 1
    except KeyboardInterrupt:
        print("Stopped; only this client's bounded in-flight requests are awaited.", file=sys.stderr)
        return 130
    except Refused as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        # Exception strings can include attacker-controlled paths/config bytes.
        print("Refused: check private config ownership, permissions and regular-file format; "
              "secret values are not displayed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
