#!/usr/bin/env python3
"""Safe Task API load-client tests: mocks plus owned ephemeral loopback fixtures.

Run: python3 -m unittest discover -s roadmap/tools -p test_workshop_load.py -v
Socket permission failures are explicit skips, not accepted network results.
Set WORKSHOP_LOAD_BINARY to a previously built course_tasks to also exercise
the real C++ memory service. Nothing contacts a non-loopback address or Docker.
"""

from __future__ import annotations

import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/service-workshop"
SPEC = importlib.util.spec_from_file_location("workshop_load_under_test", EXAMPLE / "load.py")
load = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = load
SPEC.loader.exec_module(load)
TOKEN = "a" * 64
TASK = {"id": 1, "title": "A private task title", "done": False, "version": 1}
BODY = json.dumps([TASK]).encode("utf-8")


def client_file(root: Path, token: str = TOKEN) -> Path:
    directory = root / ".secrets"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    path = directory / "client.curl"
    path.write_text(f'header = "Authorization: Bearer {token}"\n'
                    'noproxy = "127.0.0.1,localhost,::1"\n'
                    'connect-timeout = 2\nmax-time = 5\nfail-with-body\nsilent\nshow-error\n',
                    encoding="ascii")
    os.chmod(path, 0o600)
    return path


@contextlib.contextmanager
def own_server(respond=None):
    observations = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_GET(self):
            observations.append((self.path, self.headers.get("Authorization"),
                                 self.headers.get("Connection")))
            if respond:
                respond(self)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except PermissionError as error:
        raise unittest.SkipTest("loopback fixture UNAVAILABLE: sockets denied, not verified") from error
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield load.Target("127.0.0.1", server.server_port), observations
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def one(target, *, timeout=0.5, limit=1024 * 1024):
    return load.request_once(target, TOKEN, timeout, limit, time.monotonic() + timeout + 1)


class LoadSafety(unittest.TestCase):
    def test_only_literal_loopback_origins_and_unprivileged_ports(self):
        for value in ("http://127.0.0.1:8080", "http://127.0.0.2:8080/", "http://[::1]:8080"):
            self.assertEqual(load.loopback_target(value).port, 8080)
        for value in ("http://localhost:8080", "https://127.0.0.1:8080", "http://127.0.0.1",
                      "http://127.0.0.1:80", "http://127.0.0.1:65536", "http://0.0.0.0:8080",
                      "http://192.168.1.2:8080", "http://example.org:8080", "file:///tmp/file",
                      "http://user:secret@127.0.0.1:8080", "http://127.0.0.1:8080/tasks",
                      "http://127.0.0.1:8080/?x=1", "http://127.0.0.1:8080/#",
                      "http://127.0.0.1:8080\\@example.org", "http://[::ffff:127.0.0.1]:8080",
                      "http://[::1%lo]:8080", "http://127.0.0.1:8080\n", "http://127.1:8080"):
            with self.subTest(value=value), self.assertRaises(load.Refused):
                load.loopback_target(value)

    def test_private_generated_config_and_no_symlinks_or_hardlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = client_file(root)
            self.assertEqual(load.read_token(path), TOKEN)
            for mode in (0o644, 0o400, 0o666):
                os.chmod(path, mode)
                with self.subTest(mode=mode), self.assertRaises(load.Refused):
                    load.read_token(path)
            os.chmod(path, 0o600)
            alias = root / ".secrets/alias"
            os.link(path, alias)
            with self.assertRaises(load.Refused):
                load.read_token(path)
            alias.unlink()
            alias.symlink_to(path.name)
            with self.assertRaises(OSError):
                load.read_token(alias)
            linked = root / "linked"
            linked.symlink_to(path.parent, target_is_directory=True)
            with self.assertRaises(OSError):
                load.read_token(linked / "client.curl")
            nested = root / "ancestor"
            nested.symlink_to(root, target_is_directory=True)
            with self.assertRaises(OSError):
                load.read_token(nested / ".secrets/client.curl")
            os.chmod(path.parent, 0o755)
            with self.assertRaises(load.Refused):
                load.read_token(path)

    def test_invalid_secret_format_never_reaches_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = client_file(Path(temporary))
            for contents in (f'header = "Authorization: Bearer {TOKEN}"\n' * 2,
                             'header = "Authorization: Bearer secret-that-must-not-leak"\n',
                             "url = https://example.org\n", "\xff", "x" * 4097):
                path.write_bytes(contents.encode("latin1"))
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    self.assertEqual(load.main(["--client-config", str(path)]), 2)
                self.assertNotIn("secret-that-must-not-leak", stderr.getvalue())
                self.assertNotIn(TOKEN, stderr.getvalue())

    def test_exact_json_contract_and_no_boolean_ids(self):
        load.validate_tasks(BODY)
        load.validate_tasks(b"[]")
        invalid = (b'{"tasks":[]}', b'[NaN]', b'[{"id":1,"id":2}]', b'"\xff"', b'{',
                   json.dumps([{**TASK, "id": True}]).encode(),
                   json.dumps([{**TASK, "version": False}]).encode(),
                   json.dumps([{**TASK, "id": 0}]).encode(),
                   json.dumps([{**TASK, "version": 2 ** 63}]).encode(),
                   json.dumps([{**TASK, "done": 0}]).encode(),
                   json.dumps([{**TASK, "title": ""}]).encode(),
                   json.dumps([{**TASK, "title": "\0"}]).encode(),
                   json.dumps([{**TASK, "title": "я" * 101}]).encode(),
                   json.dumps([{**TASK, "extra": 1}]).encode(),
                   json.dumps([TASK, TASK]).encode(),
                   json.dumps([TASK] * 1001).encode())
        for body in invalid:
            with self.subTest(body=body[:50]), self.assertRaises(load.InvalidResponse):
                load.validate_tasks(body)

    def test_percentiles_have_sample_count_compatible_nearest_rank(self):
        self.assertEqual(load.percentiles([]), {"p50": None, "p95": None, "p99": None})
        self.assertEqual(load.percentiles([10, 1, 4, 2]), {"p50": 2, "p95": 10, "p99": 10})

    def test_closed_concurrency_has_bounded_workers_and_total_not_per_worker(self):
        active = peak = calls = 0
        lock = threading.Lock()

        def fake(*_):
            nonlocal active, peak, calls
            with lock:
                active += 1
                peak = max(peak, active)
                calls += 1
            time.sleep(0.002)
            with lock:
                active -= 1
            return load.Sample("valid", 200, 1)

        result = load.run_phase("test", load.Target("127.0.0.1", 8080), TOKEN,
                                workers=3, requests=17, timeout=1, max_response=1024,
                                deadline=time.monotonic() + 3, request_function=fake)
        self.assertEqual(calls, 17)
        self.assertLessEqual(peak, 3)
        self.assertEqual(result["completed"], 17)
        self.assertEqual(result["valid_tasks_responses"], 17)
        self.assertEqual(result["all_latency_samples"], 17)

    def test_deadline_stops_new_requests_and_wrong_token_stops_load(self):
        fake = mock.Mock(return_value=load.Sample("valid", 200, 1))
        result = load.run_phase("test", load.Target("127.0.0.1", 8080), TOKEN,
                                workers=2, requests=20, timeout=1, max_response=1024,
                                deadline=time.monotonic() - 1, request_function=fake)
        fake.assert_not_called()
        self.assertEqual(result["not_started"], 20)
        denied = mock.Mock(return_value=load.Sample("auth_401", 401, 1))
        result = load.run_phase("test", load.Target("127.0.0.1", 8080), TOKEN,
                                workers=1, requests=20, timeout=1, max_response=1024,
                                deadline=time.monotonic() + 1, request_function=denied)
        self.assertEqual(result["outcomes"], {"auth_401": 1})
        self.assertEqual(result["not_started"], 19)

    def test_socket_denial_is_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = client_file(Path(temporary))
            with mock.patch.object(load.http.client.HTTPConnection, "connect", side_effect=PermissionError):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    status = load.main(["--client-config", str(path), "--json"])
            report = json.loads(stdout.getvalue())
            self.assertEqual(status, 1)
            self.assertFalse(report["ok"])
            self.assertEqual(report["phases"][0]["valid_tasks_responses"], 0)
            self.assertGreater(report["phases"][0]["outcomes"].get("transport", 0), 0)

    def test_interruption_does_not_dispatch_the_rest_of_the_scenario(self):
        interrupted = mock.Mock(side_effect=KeyboardInterrupt)
        with self.assertRaises(KeyboardInterrupt):
            load.run_phase("test", load.Target("127.0.0.1", 8080), TOKEN,
                           workers=2, requests=400, timeout=1, max_response=1024,
                           deadline=time.monotonic() + 3, request_function=interrupted)
        self.assertLessEqual(interrupted.call_count, 2)

    def test_cli_rejects_unbounded_or_nonfinite_settings(self):
        for arguments in (["--workers", "9"], ["--requests", "401"], ["--max-runtime", "61"],
                          ["--timeout", "nan"], ["--timeout", "inf"], ["--timeout", "0"],
                          ["--max-response-bytes", "3000000"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    load.main(arguments)
                self.assertEqual(error.exception.code, 2)


class OwnedLoopback(unittest.TestCase):
    def test_real_http_auth_json_and_safe_report_ignore_proxy_environment(self):
        with tempfile.TemporaryDirectory() as temporary, own_server() as (target, observations):
            path = client_file(Path(temporary))
            environment = {"http_proxy": "http://unrelated.invalid:9999", "HTTP_PROXY": "http://unrelated.invalid:9999",
                           "ALL_PROXY": "http://unrelated.invalid:9999", "no_proxy": ""}
            with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = load.main(["--base-url", target.url, "--client-config", str(path),
                                    "--warmup", "1", "--baseline-requests", "2", "--requests", "7",
                                    "--recovery-requests", "2", "--json"])
            text = stdout.getvalue()
            report = json.loads(text)
            self.assertEqual(status, 0)
            self.assertTrue(report["ok"])
            self.assertEqual([phase["phase"] for phase in report["phases"]],
                             ["warmup", "baseline", "load", "recovery"])
            self.assertEqual([phase["completed"] for phase in report["phases"]], [1, 2, 7, 2])
            self.assertEqual(len(observations), 12)
            self.assertTrue(all(value == ("/tasks", "Bearer " + TOKEN, "close") for value in observations))
            self.assertNotIn(TOKEN, text)
            self.assertNotIn(TASK["title"], text)

    def test_401_503_other_status_and_invalid_200_are_distinct(self):
        for status, body, expected in ((401, b'{"error":"unauthorized"}', "auth_401"),
                                       (503, b'{"error":"service_unavailable"}', "unavailable_503"),
                                       (404, b'{}', "http_other"),
                                       (200, b'{"status":"ok"}', "invalid_response")):
            def respond(handler, status=status, body=body):
                handler.send_response(status)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)
            with self.subTest(status=status), own_server(respond) as (target, _):
                sample = one(target)
                self.assertEqual(sample.outcome, expected)
                self.assertEqual(sample.status, status)

    def test_redirect_is_not_followed_or_leaked_to_other_origin(self):
        def respond(handler):
            handler.send_response(302)
            handler.send_header("Location", "http://unrelated.invalid:9999/collect")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
        with own_server(respond) as (target, observations):
            sample = one(target)
            self.assertEqual(sample.outcome, "redirect")
            self.assertEqual(len(observations), 1)

    def test_oversized_chunked_and_wrong_content_type_are_refused(self):
        for headers, body in (([("Content-Length", "99999")], b""),
                               ([("Transfer-Encoding", "chunked")], b"0\r\n\r\n"),
                               ([("Content-Length", "2"), ("Content-Type", "text/html")], b"[]"),
                               ([("Content-Length", "2"), ("Content-Encoding", "gzip")], b"[]"),
                               ([("Content-Length", "2"), ("X-Large", "x" * (16 * 1024))], b"[]")):
            def respond(handler, headers=headers, body=body):
                handler.send_response(200)
                for name, value in headers:
                    handler.send_header(name, value)
                handler.end_headers()
                handler.wfile.write(body)
            with self.subTest(headers=headers), own_server(respond) as (target, _):
                self.assertEqual(one(target, limit=1024).outcome, "invalid_response")

    def test_total_deadline_bounds_slow_header_and_slow_body_not_only_idle_timeout(self):
        for slow_headers in (True, False):
            def respond(handler, slow_headers=slow_headers):
                try:
                    if slow_headers:
                        handler.connection.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                    else:
                        handler.send_response(200)
                        handler.send_header("Content-Type", "application/json")
                        handler.send_header("Content-Length", "1000")
                        handler.end_headers()
                    for _ in range(30):
                        handler.connection.sendall(b" ")
                        time.sleep(0.04)
                except OSError:
                    pass
            with self.subTest(slow_headers=slow_headers), own_server(respond) as (target, _):
                start = time.monotonic()
                sample = one(target, timeout=0.15)
                self.assertEqual(sample.outcome, "timeout")
                self.assertLess(time.monotonic() - start, 0.8)

    def test_scenario_deadline_bounds_inflight_io_and_reports_unstarted_requests(self):
        def respond(handler):
            try:
                handler.connection.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                for _ in range(30):
                    handler.connection.sendall(b" ")
                    time.sleep(0.04)
            except OSError:
                pass
        with own_server(respond) as (target, _):
            start = time.monotonic()
            result = load.run_phase("load", target, TOKEN, workers=2, requests=40,
                                    timeout=2, max_response=1024, deadline=start + 0.15)
            self.assertLess(time.monotonic() - start, 0.8)
            self.assertTrue(result["deadline_reached"])
            self.assertEqual(result["valid_tasks_responses"], 0)
            self.assertEqual(result["outcomes"], {"timeout": 2})
            self.assertEqual(result["not_started"], 38)


@unittest.skipUnless(os.environ.get("WORKSHOP_LOAD_BINARY"),
                     "set WORKSHOP_LOAD_BINARY to test the actual C++ service; mock HTTP is not native acceptance")
class NativeTaskAPI(unittest.TestCase):
    def test_real_task_service_accepts_authenticated_read_only_phases(self):
        import verify_service_workshop as verify
        try:
            server = verify.NativeServer(Path(os.environ["WORKSHOP_LOAD_BINARY"]), TOKEN)
        except verify.NetworkUnavailable as error:
            self.skipTest("native loopback UNAVAILABLE: " + str(error))
        with tempfile.TemporaryDirectory() as temporary:
            path = client_file(Path(temporary))
            try:
                server.start()
                response = server.client.request("POST", "/tasks", verify.payload("Load fixture"))
                self.assertEqual(response.status, 201)
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    status = load.main(["--base-url", server.client.base_url, "--client-config", str(path),
                                        "--requests", "20", "--json"])
                report = json.loads(stdout.getvalue())
                self.assertEqual(status, 0)
                self.assertEqual(report["planned_requests"], 44)
                self.assertTrue(all(phase["valid_tasks_responses"] == phase["requested"]
                                    for phase in report["phases"]))
                after = server.client.request("GET", "/tasks").json()
                self.assertEqual(len(after), 1)
                self.assertEqual(after[0]["version"], 1)
                self.assertEqual(after[0]["title"], "Load fixture")
            finally:
                server.stop()
                server.check_logs()
                server.close()


if __name__ == "__main__":
    unittest.main()
