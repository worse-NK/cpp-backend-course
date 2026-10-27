#!/usr/bin/env python3
"""Black-box acceptance checks for the disposable service-workshop service.

Default: launch our own native memory server, exercise HTTP on literal loopback,
restart it, and check that memory data was lost. Nothing is downloaded and no
Docker, firewall, systemd, sudo, or unrelated process is touched.

An existing loopback service is accepted ONLY with --fresh-service. This is a
destructive acceptance test: it requires an initially empty task collection.
Use a dedicated, disposable instance, never a user's running service.

PostgreSQL is opt-in: --storage postgres --disposable-postgres, PGDATABASE must
start with course_workshop_verify_, and all PG* connection variables must be
set explicitly. Provision the empty database and schema separately. We do not
create, drop, migrate, or stop a database.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import errno
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY = ROOT / "examples/service-workshop/build/course_tasks"
MAX_BODY = 4096
MAX_TASKS = 1000


class ContractFailure(RuntimeError):
    """An observed result differs from the documented HTTP contract."""


class NetworkUnavailable(RuntimeError):
    """The execution environment forbids a local socket; not a passing test."""


def require(condition: bool, message: str) -> None:
    # Not assert: checks must also run under python -O.
    if not condition:
        raise ContractFailure(message)


def loopback_url(value: str) -> str:
    """Accept only HTTP literal loopback authorities, never DNS or credentials."""
    try:
        parts = urllib.parse.urlsplit(value)
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError as exc:
        raise ValueError("base URL must contain a literal loopback address") from exc
    if (parts.scheme != "http" or not address.is_loopback or
            parts.username is not None or parts.password is not None or
            parts.path not in ("", "/") or parts.query or parts.fragment or
            port is None or not 1 <= port <= 65535):
        raise ValueError("use http://127.0.0.1:PORT (or http://[::1]:PORT) only")
    return urllib.parse.urlunsplit(("http", parts.netloc, "", "", ""))


def unused_loopback_port() -> int:
    """Reserve a kernel-selected port briefly; startup still checks bind races."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            return int(reservation.getsockname()[1])
    except OSError as exc:
        if exc.errno in (errno.EPERM, errno.EACCES):
            raise NetworkUnavailable(
                "loopback socket binding is forbidden in this environment; "
                "HTTP acceptance was NOT run") from exc
        raise


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must never carry the bearer token to another authority.
        return None


class _OmitContentType(urllib.request.BaseHandler):
    # Run after AbstractHTTPHandler's request processing has inserted its
    # implicit form media type. This makes the missing-header check literal.
    handler_order = 600

    def http_request(self, request):
        if getattr(request, "omit_content_type", False):
            request.remove_header("Content-type")
        return request


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-JSON constant")


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        except (UnicodeError, ValueError) as exc:
            raise ContractFailure("response is not strict UTF-8 JSON") from exc


class Client:
    def __init__(self, base_url: str, token: str):
        self.base_url = loopback_url(base_url)
        self.token = token
        self.wrong_token = secrets.token_hex(32)
        # Ignore HTTP_PROXY etc.; these requests must remain on loopback.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect(), _OmitContentType())

    def request(self, method: str, path: str, body: bytes | None = None,
                *, content_type: str | None = "application/json",
                authorization: str | None = "default",
                headers: dict[str, str] | None = None) -> Response:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("request path must remain on the selected origin")
        fields = dict(headers or {})
        if authorization == "default":
            fields["Authorization"] = "Bearer " + self.token
        elif authorization is not None:
            fields["Authorization"] = authorization
        if content_type is not None:
            fields["Content-Type"] = content_type
        request = urllib.request.Request(self.base_url + path, data=body,
                                         headers=fields, method=method)
        request.omit_content_type = content_type is None
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(1024 * 1024 + 1)
            require(len(raw) <= 1024 * 1024, "response exceeded the acceptance limit")
            return Response(response.status, {key.lower(): value for key, value in response.headers.items()}, raw)


def payload(title: str = "acceptance", done: bool = False) -> bytes:
    return json.dumps({"title": title, "done": done}, ensure_ascii=False).encode("utf-8")


def expect(response: Response, status: int, label: str) -> Response:
    require(response.status == status, f"{label}: expected HTTP {status}, got {response.status}")
    return response


def task_response(response: Response, status: int, label: str, *, validator: bool = True) -> dict:
    expect(response, status, label)
    require(response.headers.get("content-type", "").split(";", 1)[0].strip() == "application/json",
            label + ": expected JSON media type")
    value = response.json()
    require(isinstance(value, dict) and set(value) == {"id", "title", "done", "version"},
            label + ": expected exact task representation")
    require(type(value["id"]) is int and 0 < value["id"] <= 2**63 - 1,
            label + ": id must be a positive signed-64-bit JSON integer")
    require(type(value["version"]) is int and value["version"] >= 1,
            label + ": version must be a positive JSON integer")
    require(type(value["title"]) is str and type(value["done"]) is bool,
            label + ": incorrect task types")
    if validator:
        require(response.headers.get("etag") == f'"v{value["version"]}"', label + ": incorrect ETag")
    else:
        require("etag" not in response.headers and "last-modified" not in response.headers,
                label + ": transformed PUT must not return a validator")
    return value


def list_tasks(client: Client) -> list[dict]:
    response = expect(client.request("GET", "/tasks"), 200, "list tasks")
    require(response.headers.get("content-type", "").split(";", 1)[0].strip() == "application/json",
            "list tasks: expected JSON media type")
    value = response.json()
    require(type(value) is list, "GET /tasks must return a JSON array")
    require(all(type(item) is dict and type(item.get("id")) is int for item in value),
            "GET /tasks returned a malformed item")
    ids = [item["id"] for item in value]
    require(ids == sorted(set(ids)), "GET /tasks must have unique IDs in ascending order")
    return value


def create_task(client: Client, title: str = "acceptance", done: bool = False) -> dict:
    response = client.request("POST", "/tasks", payload(title, done))
    value = task_response(response, 201, "create task")
    require(value["title"] == title and value["done"] is done and value["version"] == 1,
            "POST must preserve fields and start at version 1")
    require(response.headers.get("location") == f'/tasks/{value["id"]}', "incorrect Location")
    return value


def delete_task(client: Client, value: dict) -> None:
    response = expect(client.request("DELETE", f'/tasks/{value["id"]}',
                                    headers={"If-Match": f'"v{value["version"]}"'}),
                      204, "delete task")
    require(response.body == b"", "204 DELETE must not contain a response body")


def verify_http(client: Client, *, capacity: bool = False) -> list[str]:
    """Mutating checks; caller must explicitly own a fresh disposable service."""
    for path in ("/health/live", "/health/ready"):
        response = expect(client.request("GET", path, authorization=None), 200, path)
        require(response.json() == {"status": "ok"}, path + ": incorrect healthy body")
    # Crucial safety gate: never clear a collection belonging to someone else.
    require(list_tasks(client) == [], "refusing mutation: acceptance requires an initially empty disposable service")
    checks = ["unauthenticated liveness/readiness; initially empty store"]

    original = create_task(client, 'Задача "A" \\ строка\nещё', True)
    path = f'/tasks/{original["id"]}'
    read = task_response(client.request("GET", path), 200, "read created task")
    require(read == original and list_tasks(client) == [original], "create/read/list disagree")
    for method, endpoint, body in (("GET", "/tasks", None), ("GET", path, None),
                                   ("POST", "/tasks", payload()), ("PUT", path, payload()),
                                   ("DELETE", path, None)):
        for auth in (None, "Bearer " + client.wrong_token, "Basic invalid"):
            rejected = expect(client.request(method, endpoint, body, authorization=auth,
                                             headers={"If-Match": '"v1"'}), 401, "unauthorized " + method)
            require(rejected.headers.get("www-authenticate") == "Bearer", "401 must advertise Bearer authentication")
    require(list_tasks(client) == [original], "unauthorized mutation changed state")
    checks.append("bearer authorization for every task operation")

    bad_json = (b'', b'{', b'{"title":"a","title":"b","done":false}',
                b'{"title":"a","done":false,"done":true}',
                b'{"title":"a","done":NaN}',
                b'{"title":"a","done":false} trailing', b'{"title":"\xff","done":false}')
    invalid_values = ([], None, {}, {"title": "a"}, {"done": False},
                      {"title": "a", "done": False, "owner": "other"},
                      {"title": 1, "done": False}, {"title": None, "done": False},
                      {"title": "a", "done": 0}, {"title": "a", "done": "false"},
                      {"title": "a", "done": None}, {"title": "", "done": False},
                      {"title": "я" * 101, "done": False}, {"title": "a\x00b", "done": False})
    for method, endpoint in (("POST", "/tasks"), ("PUT", path)):
        for body in bad_json:
            expect(client.request(method, endpoint, body, headers={"If-Match": '"v1"'}),
                   400, method + " malformed JSON")
        for value in invalid_values:
            body = json.dumps(value, ensure_ascii=False).encode()
            expect(client.request(method, endpoint, body, headers={"If-Match": '"v1"'}),
                   422, method + " invalid schema")
        for media_type in (None, "text/plain", "application/jsonp"):
            expect(client.request(method, endpoint, payload(), content_type=media_type,
                                  headers={"If-Match": '"v1"'}), 415, method + " unsupported media type")
        expect(client.request(method, endpoint, b"x" * (MAX_BODY + 1),
                              headers={"If-Match": '"v1"'}), 413, method + " body limit")
    require(list_tasks(client) == [original], "rejected input changed state")
    boundary = create_task(client, "я" * 100)
    delete_task(client, boundary)
    exact = payload("exact-body-limit")
    exact_response = client.request("POST", "/tasks", exact + b" " * (MAX_BODY - len(exact)))
    exact_value = task_response(exact_response, 201, "exact 4096-byte body")
    delete_task(client, exact_value)
    checks.append("strict JSON/schema/UTF-8/media type and 4096-byte body boundary")

    for method, body in (("PUT", payload("updated")), ("DELETE", None)):
        expect(client.request(method, path, body), 428, method + " missing If-Match")
        for tag in ("v1", 'W/"v1"', '"v0"', '"v01"', '"v-1"', '*', '"v1", "v2"',
                    '"v9223372036854775808"'):
            expect(client.request(method, path, body, headers={"If-Match": tag}),
                   400, method + " malformed If-Match")
        expect(client.request(method, path, body, headers={"If-Match": '"v2"'}),
               412, method + " stale If-Match")
        expect(client.request(method, "/tasks/9223372036854775807", body,
                              headers={"If-Match": '"v1"'}), 412, method + " absent target")
    require(list_tasks(client) == [original], "failed precondition changed state")
    updated = task_response(client.request("PUT", path, payload("updated", False),
                                          headers={"If-Match": '"v1"'}), 200, "replace task", validator=False)
    require(updated == {**original, "title": "updated", "done": False, "version": 2},
            "replacement must increment version exactly once")
    require(task_response(client.request("GET", path), 200, "read actual PUT representation") == updated,
            "GET after PUT must return the committed representation and its validator")
    expect(client.request("PUT", path, payload("stale"), headers={"If-Match": '"v1"'}),
           412, "old version after replacement")
    delete_task(client, updated)
    expect(client.request("GET", path), 404, "deleted task")
    checks.append("ETag/If-Match syntax, absent/stale/missing conditions, replacement and deletion")

    for bad_id in ("0", "01", "-1", "abc", "1junk", "9223372036854775808"):
        expect(client.request("GET", "/tasks/" + bad_id), 400, "noncanonical task ID")
    expect(client.request("GET", "/tasks/9223372036854775807"), 404, "missing task")
    expect(client.request("GET", "/not-a-workshop-route"), 404, "unknown route")
    # In native mode the final log check verifies paths, query values and request
    # bodies are not logged, as well as checking the Authorization header.
    expect(client.request("GET", "/private-" + client.token), 404, "private unknown path")
    expect(client.request("GET", "/not-a-workshop-route?private=" + client.token), 404, "private query")
    private_body = create_task(client, client.token)
    delete_task(client, private_body)
    checks.append("canonical IDs and unknown routes")

    competitors = 8
    target = create_task(client, "race")
    barrier = threading.Barrier(competitors)
    def update(index):
        barrier.wait(timeout=10)
        return client.request("PUT", f'/tasks/{target["id"]}', payload(f"winner-{index}"),
                              headers={"If-Match": '"v1"'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=competitors) as executor:
        results = list(executor.map(update, range(competitors)))
    require(sorted(response.status for response in results) == [200] + [412] * (competitors - 1),
            "concurrent same-version PUTs must have exactly one winner")
    winner = task_response(next(response for response in results if response.status == 200), 200, "race winner", validator=False)
    require(winner["version"] == 2, "concurrent replacement incremented version more than once")
    require(task_response(client.request("GET", f'/tasks/{target["id"]}'), 200, "read race winner") == winner,
            "committed state differs from the successful racing response")
    delete_task(client, winner)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        created = list(executor.map(lambda index: create_task(client, f"parallel-{index}"), range(18)))
    require(len({item["id"] for item in created}) == len(created), "parallel creation reused IDs")
    require(list_tasks(client) == sorted(created, key=lambda item: item["id"]), "parallel create/list disagree")
    for item in created:
        delete_task(client, item)
    checks.append("concurrent optimistic updates and unique parallel creation")

    if capacity:
        created = [create_task(client, f"capacity-{index}") for index in range(MAX_TASKS)]
        expect(client.request("POST", "/tasks", payload("over-capacity")), 503, "bounded task capacity")
        require(len(list_tasks(client)) == MAX_TASKS, "capacity rejection changed collection size")
        delete_task(client, created.pop())
        replacement = create_task(client, "capacity-after-delete")
        delete_task(client, replacement)
        for item in created:
            delete_task(client, item)
        checks.append("1000-task capacity and recovery after deletion")
    require(list_tasks(client) == [], "acceptance left unexpected task data")
    return checks


def postgres_environment(environ: dict[str, str], disposable: bool) -> dict[str, str]:
    names = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    if not disposable:
        raise ValueError("postgres requires --disposable-postgres and a dedicated test database")
    if any(not environ.get(name) for name in names):
        raise ValueError("postgres requires explicit PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD")
    database = environ["PGDATABASE"]
    if not database.startswith("course_workshop_verify_") or not database.isascii() or not all(
            character.isalnum() or character == "_" for character in database):
        raise ValueError("PGDATABASE must be a dedicated course_workshop_verify_* database")
    host = environ["PGHOST"]
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.startswith("/") and "\x00" not in host
    if not loopback:
        raise ValueError("acceptance PostgreSQL must use literal loopback or a local Unix socket directory")
    if not environ["PGPORT"].isdigit() or not 1 <= int(environ["PGPORT"]) <= 65535:
        raise ValueError("PGPORT must be a valid numeric port")
    return {name: environ[name] for name in names}


class NativeServer:
    """Own exactly one Popen child, never processes found by name or port."""
    def __init__(self, binary: Path, token: str, *, storage: str = "memory",
                 pg_environment: dict[str, str] | None = None):
        self.binary = Path(binary).resolve()
        self.token = token
        self.storage = storage
        self.pg_environment = pg_environment or {}
        self.port = unused_loopback_port()
        self.client = Client(f"http://127.0.0.1:{self.port}", token)
        self.process: subprocess.Popen | None = None
        self.forced_shutdown = False
        self.exit_codes: list[int] = []
        self.directory = tempfile.TemporaryDirectory(prefix="service-workshop-acceptance-")
        self.log_paths: list[Path] = []
        self._log = None

    def start(self) -> None:
        require(self.process is None, "cannot start a second server child")
        require(self.binary.is_file() and os.access(self.binary, os.X_OK), "build/course_tasks executable is missing")
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("APP_", "PG"))}
        environment.update(self.pg_environment)
        environment.update(APP_TOKEN=self.token, APP_BIND="127.0.0.1", APP_PORT=str(self.port), APP_STORAGE=self.storage)
        log_path = Path(self.directory.name) / f"server-{len(self.log_paths)}.log"
        self.log_paths.append(log_path)
        self._log = log_path.open("wb")
        try:
            self.process = subprocess.Popen([str(self.binary)], env=environment,
                                             stdin=subprocess.DEVNULL, stdout=self._log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                require(self.process.poll() is None, "owned server exited before readiness (inspect its private acceptance log)")
                try:
                    response = self.client.request("GET", "/health/ready", authorization=None)
                    if response.status == 200:
                        return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.05)
            raise ContractFailure("owned server did not become ready within 15 seconds")
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        process = self.process
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.forced_shutdown = True
                    process.kill()
                    process.wait(timeout=5)
                self.exit_codes.append(process.returncode)
        finally:
            self.process = None
            if self._log is not None:
                self._log.close()
                self._log = None

    def check_logs(self) -> None:
        sensitive = (self.token, self.client.wrong_token, self.pg_environment.get("PGPASSWORD", ""))
        for path in self.log_paths:
            data = path.read_bytes()
            require(not any(secret.encode() in data for secret in sensitive if secret),
                    "server logs leaked an authentication or database secret (log omitted)")

    def close(self) -> None:
        try:
            self.stop()
            self.check_logs()
        finally:
            self.directory.cleanup()


def verify_native(binary: Path, *, storage: str = "memory", capacity: bool = False,
                  pg_environment: dict[str, str] | None = None) -> list[str]:
    server = NativeServer(binary, secrets.token_hex(32), storage=storage, pg_environment=pg_environment)
    try:
        server.start()
        checks = verify_http(server.client, capacity=capacity)
        survivor = create_task(server.client, "restart-sentinel")
        server.stop()
        server.start()
        after_restart = list_tasks(server.client)
        if storage == "memory":
            require(after_restart == [], "memory storage unexpectedly persisted across process restart")
            checks.append("owned process restart clears volatile memory")
        else:
            require(after_restart == [survivor], "PostgreSQL did not preserve the task across process restart")
            delete_task(server.client, survivor)
            checks.append("PostgreSQL survives owned process restart; sentinel removed")
        server.stop()
        server.check_logs()
        require(not server.forced_shutdown, "owned server did not stop after SIGTERM within eight seconds")
        require(all(code == 0 for code in server.exit_codes), "owned server did not shut down cleanly")
        checks.append("graceful owned child shutdown and secret-free server logs")
        return checks
    finally:
        server.close()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--binary", type=Path, default=DEFAULT_BINARY, help="native course_tasks executable")
    target.add_argument("--base-url", help="existing literal-loopback HTTP service; requires --fresh-service")
    parser.add_argument("--fresh-service", action="store_true", help="explicitly authorize destructive tests of an existing empty disposable service")
    parser.add_argument("--token-env", help="environment variable containing the existing service token (never an argv token)")
    parser.add_argument("--storage", choices=("memory", "postgres"), default="memory")
    parser.add_argument("--disposable-postgres", action="store_true", help="authorize a separately provisioned course_workshop_verify_* database")
    parser.add_argument("--check-capacity", action="store_true", help="also exercise the full 1000-task bound")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.base_url:
            if not args.fresh_service or not args.token_env:
                parser.error("--base-url requires --fresh-service and --token-env NAME")
            if args.storage != "memory" or args.disposable_postgres:
                parser.error("external mode does not select storage or authorize database access")
            token = os.environ.get(args.token_env, "")
            if len(token) != 64 or any(character not in "0123456789abcdefABCDEF" for character in token):
                parser.error("token environment variable must contain 64 hex characters")
            checks = verify_http(Client(args.base_url, token), capacity=args.check_capacity)
            checks.append("NOT RUN: external process restart and private log inspection")
        else:
            if args.fresh_service or args.token_env:
                parser.error("--fresh-service/--token-env apply only with --base-url")
            if args.disposable_postgres and args.storage != "postgres":
                parser.error("--disposable-postgres requires --storage postgres")
            pg_environment = (postgres_environment(dict(os.environ), args.disposable_postgres)
                              if args.storage == "postgres" else None)
            checks = verify_native(args.binary, storage=args.storage,
                                   capacity=args.check_capacity, pg_environment=pg_environment)
        for check in checks:
            print(("" if check.startswith("NOT RUN:") else "PASS: ") + check)
        return 0
    except NetworkUnavailable as exc:
        print("UNAVAILABLE: " + str(exc), file=sys.stderr)
        return 77
    except (ContractFailure, OSError, ValueError, urllib.error.URLError) as exc:
        # Error text never includes request headers, bodies, env values or logs.
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
