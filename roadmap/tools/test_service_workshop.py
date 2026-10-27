#!/usr/bin/env python3
"""Service workshop regression tests; no Docker daemon or privileged commands.

Run: python3 -m unittest discover -s roadmap/tools -p test_service_workshop.py -v
HTTP socket restrictions are explicit unittest skips, not successful acceptance.
The standalone verifier exits 77 when local sockets are unavailable.
Set SERVICE_WORKSHOP_DEPS to pre-fetched, verified dependency sources containing
cpp-httplib-0.59.0/ and json/ to also build and run the native tests offline.
"""

from __future__ import annotations

import contextlib
import errno
from html import unescape
from html.parser import HTMLParser
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.request
from urllib.parse import parse_qs, urlsplit

import verify_service_workshop as verify


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/service-workshop"


def run(command, *, cwd=None, env=None, timeout=60):
    return subprocess.run([str(value) for value in command], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=timeout)


class VerifierSafety(unittest.TestCase):
    def test_loopback_only_and_no_credential_urls(self):
        for url in ("http://127.0.0.1:8123", "http://127.0.0.2:8123/", "http://[::1]:8123"):
            with self.subTest(url=url):
                self.assertTrue(verify.loopback_url(url).startswith("http://"))
        for url in ("https://127.0.0.1:8123", "http://localhost:8123", "http://example.org:8123",
                    "http://0.0.0.0:8123", "http://192.168.1.2:8123", "http://127.0.0.1",
                    "http://user:password@127.0.0.1:8123", "http://127.0.0.1:8123/api",
                    "http://127.0.0.1:8123/?query=x", "http://127.0.0.1:8123/#fragment",
                    "http://127.0.0.1:0", "file:///tmp/workshop", "http://[::]:8123"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                verify.loopback_url(url)

    def test_unavailable_socket_is_not_success(self):
        with mock.patch.object(verify.socket, "socket", side_effect=PermissionError(errno.EPERM, "blocked")):
            with self.assertRaises(verify.NetworkUnavailable):
                verify.unused_loopback_port()
        with mock.patch.object(verify, "verify_native", side_effect=verify.NetworkUnavailable("blocked")):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(verify.main([]), 77)
        self.assertIn("UNAVAILABLE", stderr.getvalue())

    def test_external_mutation_needs_explicit_authorization(self):
        with mock.patch.object(verify, "verify_http") as acceptance:
            for arguments in (("--base-url", "http://127.0.0.1:8123"),
                              ("--base-url", "http://127.0.0.1:8123", "--fresh-service")):
                with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        verify.main(list(arguments))
                    self.assertEqual(error.exception.code, 2)
            acceptance.assert_not_called()

    def test_fresh_store_gate_precedes_mutation(self):
        client = mock.Mock()
        client.request.return_value = verify.Response(200, {}, b'{"status":"ok"}')
        with mock.patch.object(verify, "list_tasks", return_value=[{"id": 77}]):
            with self.assertRaisesRegex(verify.ContractFailure, "initially empty"):
                verify.verify_http(client)
        self.assertTrue(all(call.args[0] == "GET" for call in client.request.call_args_list))

    def test_no_redirect_or_implicit_content_type(self):
        self.assertIsNone(verify._NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org"))
        request = urllib.request.Request("http://127.0.0.1:8123/tasks", data=b"{}")
        request.add_unredirected_header("Content-type", "application/x-www-form-urlencoded")
        request.omit_content_type = True
        verify._OmitContentType().http_request(request)
        self.assertFalse(request.has_header("Content-type"))
        with mock.patch.dict(os.environ, {"http_proxy": "http://unrelated.example:8123",
                                           "HTTP_PROXY": "http://unrelated.example:8123", "no_proxy": ""}):
            client = verify.Client("http://127.0.0.1:49123", "a" * 64)
        self.assertTrue(all(not handler.proxies for handler in client.opener.handlers
                            if isinstance(handler, urllib.request.ProxyHandler)),
                        "loopback acceptance must ignore ambient proxy settings")

    def test_response_is_strict_json_and_task_ids_are_not_booleans(self):
        for data in (b'{"x":1,"x":2}', b'NaN', b'"\xff"', b'{'):
            with self.subTest(data=data), self.assertRaises(verify.ContractFailure):
                verify.Response(200, {}, data).json()
        response = verify.Response(200, {"content-type": "application/json", "etag": '"v1"'},
                                   b'{"id":true,"title":"x","done":false,"version":1}')
        with self.assertRaisesRegex(verify.ContractFailure, "id must"):
            verify.task_response(response, 200, "test")

    def test_postgres_requires_separate_explicit_disposable_database(self):
        environment = {"PGHOST": "127.0.0.1", "PGPORT": "5432", "PGDATABASE": "course_workshop_verify_unit",
                       "PGUSER": "course_app", "PGPASSWORD": "not-printed"}
        self.assertEqual(verify.postgres_environment(environment, True), environment)
        with self.assertRaises(ValueError):
            verify.postgres_environment(environment, False)
        for key, value in (("PGDATABASE", "course_tasks"), ("PGDATABASE", "course_workshop_verify_x dbname=prod"),
                           ("PGHOST", "db.example.org"), ("PGPASSWORD", ""), ("PGPORT", "5432 host=prod")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify.postgres_environment({**environment, key: value}, True)

    def test_transformed_put_response_has_no_validator_and_get_requires_it(self):
        body = b'{"id":1,"title":"x","done":true,"version":2}'
        headers = {"content-type": "application/json"}
        response = verify.Response(200, headers, body)
        self.assertEqual(verify.task_response(response, 200, "PUT", validator=False)["version"], 2)
        for extra in ({"etag": '"v2"'}, {"last-modified": "Sun, 25 Oct 2026 12:00:00 GMT"}):
            with self.subTest(extra=extra), self.assertRaisesRegex(verify.ContractFailure, "must not return"):
                verify.task_response(verify.Response(200, {**headers, **extra}, body), 200, "PUT", validator=False)
        with self.assertRaisesRegex(verify.ContractFailure, "incorrect ETag"):
            verify.task_response(response, 200, "GET")
        self.assertEqual(verify.task_response(verify.Response(200, {**headers, "etag": '"v2"'}, body),
                                             200, "GET")["version"], 2)

    def test_owns_exact_child_and_never_inherits_app_or_pg_settings(self):
        with mock.patch.object(verify, "unused_loopback_port", return_value=49123):
            server = verify.NativeServer(Path("/bin/true"), "a" * 64)
        child = mock.Mock()
        child.poll.return_value = None
        child.wait.return_value = 0
        server.client.request = mock.Mock(return_value=verify.Response(200, {}, b"{}"))
        try:
            with mock.patch.dict(os.environ, {"APP_STORAGE": "postgres", "APP_BIND": "0.0.0.0",
                                               "PGPASSWORD": "inherited-secret", "PGSERVICE": "production"}):
                with mock.patch.object(verify.subprocess, "Popen", return_value=child) as popen:
                    server.start()
            options = popen.call_args.kwargs
            self.assertEqual(popen.call_args.args[0], ["/usr/bin/true"] if Path("/bin/true").resolve() == Path("/usr/bin/true") else [str(Path("/bin/true").resolve())])
            self.assertEqual(options["env"]["APP_STORAGE"], "memory")
            self.assertEqual(options["env"]["APP_BIND"], "127.0.0.1")
            self.assertNotIn("PGPASSWORD", options["env"])
            self.assertNotIn("PGSERVICE", options["env"])
            server.stop()
            child.terminate.assert_called_once_with()
            child.wait.assert_called_once_with(timeout=8)
            child.kill.assert_not_called()
        finally:
            server.close()

    def test_forced_cleanup_is_bounded_and_secret_logs_are_rejected(self):
        with mock.patch.object(verify, "unused_loopback_port", return_value=49123):
            server = verify.NativeServer(Path("/bin/true"), "b" * 64)
        child = mock.Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired(["owned-child"], 8), 0]
        server.process = child
        try:
            server.stop()
            child.kill.assert_called_once_with()
            self.assertEqual(child.wait.call_args_list, [mock.call(timeout=8), mock.call(timeout=5)])
            path = Path(server.directory.name) / "secret.log"
            path.write_text("Bearer " + server.token)
            server.log_paths.append(path)
            with self.assertRaisesRegex(verify.ContractFailure, "secret") as error:
                server.check_logs()
            self.assertNotIn(server.token, str(error.exception))
            path.write_text("request completed status=200\n")
            server.check_logs()
        finally:
            server.close()


@unittest.skipUnless(os.environ.get("SERVICE_WORKSHOP_DEPS"),
                     "set SERVICE_WORKSHOP_DEPS to run the offline native build/HTTP checks")
class NativeService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="workshop-native-build-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.build = Path(cls.directory.name)
        dependencies = Path(os.environ["SERVICE_WORKSHOP_DEPS"]).resolve()
        httplib = dependencies / "cpp-httplib-0.59.0"
        json_source = dependencies / "json"
        if not (httplib / "httplib.h").is_file() or not (json_source / "CMakeLists.txt").is_file():
            raise AssertionError("SERVICE_WORKSHOP_DEPS must contain cpp-httplib-0.59.0/ and json/")
        for command in (["cmake", "-S", EXAMPLE, "-B", cls.build, "-DCMAKE_BUILD_TYPE=Release", "-DCOURSE_WITH_POSTGRES=OFF",
                         "-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DFETCHCONTENT_SOURCE_DIR_HTTPLIB=" + str(httplib),
                         "-DFETCHCONTENT_SOURCE_DIR_JSON=" + str(json_source)],
                        ["cmake", "--build", cls.build, "--parallel", "2"],
                        ["ctest", "--test-dir", cls.build, "--output-on-failure", "--no-tests=error"]):
            result = run(command, timeout=120)
            if result.returncode:
                raise AssertionError("native build/CTest failed:\n" + result.stdout + result.stderr)
        cls.binary = cls.build / "course_tasks"

    def test_native_build_and_ctest_exist(self):
        self.assertTrue(self.binary.is_file())

    def test_owned_memory_http_and_restart(self):
        try:
            checks = verify.verify_native(self.binary, capacity=True)
        except verify.NetworkUnavailable as error:
            self.skipTest(str(error))
        self.assertGreaterEqual(len(checks), 9)
        self.assertTrue(any("restart" in check for check in checks))
        self.assertTrue(any("1000" in check for check in checks))

    def test_invalid_configuration_fails_before_listening_without_secret_output(self):
        base = {key: value for key, value in os.environ.items() if not key.startswith(("APP_", "PG"))}
        valid = {"APP_TOKEN": "c" * 64, "APP_STORAGE": "memory", "APP_BIND": "127.0.0.1", "APP_PORT": "8123"}
        cases = ({"APP_TOKEN": ""}, {"APP_TOKEN": "not-a-token"}, {"APP_PORT": "0"},
                 {"APP_PORT": "65536"}, {"APP_PORT": "8080junk"}, {"APP_STORAGE": "typo"},
                 {"APP_BIND": "localhost"})
        for invalid in cases:
            with self.subTest(invalid=invalid):
                result = run([self.binary], env={**base, **valid, **invalid}, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(valid["APP_TOKEN"], result.stdout + result.stderr)
                self.assertNotIn("not-a-token", result.stdout + result.stderr)


class WorkshopArtifacts(unittest.TestCase):
    def test_files_have_real_project_and_operational_artifacts(self):
        for filename in ("CMakeLists.txt", "app.cpp", "storage.hpp", "storage.cpp", "schema.sql", "Dockerfile",
                         "compose.yaml", "compose.https.yaml", "Caddyfile", ".dockerignore", ".gitignore",
                         "init-db.sh", "lab.py", "README.md"):
            with self.subTest(filename=filename):
                self.assertTrue((EXAMPLE / filename).is_file(), filename)

    def test_build_is_pinned_and_postgres_is_optional(self):
        cmake = (EXAMPLE / "CMakeLists.txt").read_text()
        self.assertIn("COURSE_WITH_POSTGRES", cmake)
        self.assertIn("OFF", cmake)
        self.assertIn("course_tasks", cmake)
        self.assertIn("CMAKE_CXX_STANDARD 20", cmake)
        self.assertIn("FetchContent", cmake)
        self.assertEqual(cmake.count("URL_HASH SHA256="), 3)
        self.assertIn("v0.59.0", cmake)
        self.assertIn("v3.12.0", cmake)
        self.assertIn("7.10.1", cmake)
        self.assertNotIn("file(DOWNLOAD", cmake)
        self.assertNotIn("execute_process(COMMAND curl", cmake)

    def test_container_trust_boundaries(self):
        dockerfile = (EXAMPLE / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"(?m)^FROM\s+\S+\s+AS\s+\S+")
        self.assertRegex(dockerfile, r"(?m)^COPY\s+--from=")
        self.assertRegex(dockerfile, r"(?m)^USER\s+(?!root(?:\s|$)|0(?::0)?(?:\s|$))\S+")
        self.assertIn("COURSE_WITH_POSTGRES=ON", dockerfile)
        compose = (EXAMPLE / "compose.yaml").read_text()
        self.assertIn("127.0.0.1:8080:8080", compose)
        self.assertIn("/health/ready", compose + dockerfile)
        self.assertIn("internal: true", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges", compose)
        for forbidden in ("privileged: true", "/var/run/docker.sock", "network_mode: host", "0.0.0.0:8080"):
            self.assertNotIn(forbidden, compose)
        self.assertNotRegex(compose, r"(?m)^\s*-\s*[\"']?(?:5432|127\.0\.0\.1:5432):5432")
        overlay = (EXAMPLE / "compose.https.yaml").read_text()
        self.assertIn("Caddyfile", overlay)
        self.assertNotIn("privileged: true", overlay)

    def test_secrets_and_builds_cannot_enter_source_or_image_context(self):
        for filename in (".dockerignore", ".gitignore"):
            data = (EXAMPLE / filename).read_text()
            for pattern in (".env", ".secrets", "build"):
                with self.subTest(filename=filename, pattern=pattern):
                    self.assertIn(pattern, data)
            for pattern in (".secrets*/", "backups/", "*.dump"):
                with self.subTest(filename=filename, private_pattern=pattern):
                    self.assertIn(pattern, data)
        schema = (EXAMPLE / "schema.sql").read_text()
        self.assertIn("version", schema)
        self.assertRegex(schema, r"(?i)CHECK\s*\(")
        bootstrap = (EXAMPLE / "init-db.sh").read_text()
        self.assertIn("ON_ERROR_STOP", bootstrap)
        self.assertNotRegex(bootstrap, r"(?i)\bGRANT\s+ALL\b")

    def helper(self, *arguments, cwd, env=None):
        return run(["python3", Path(cwd) / "lab.py", *arguments], cwd=cwd, env=env, timeout=20)

    def copy_fixture(self, destination):
        # Temporary isolated source fixture, never the real project's secrets.
        for source in EXAMPLE.iterdir():
            if source.is_file() and source.name not in (".env",) and not source.name.endswith((".tar.gz", ".log")):
                shutil.copy2(source, Path(destination) / source.name)

    def test_helper_secret_generation_refusal_and_source_allowlist(self):
        with tempfile.TemporaryDirectory(prefix="workshop-helper-") as tmp:
            self.copy_fixture(tmp)
            result = self.helper("init", cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env_file = Path(tmp) / ".env"
            curl_file = Path(tmp) / ".secrets/client.curl"
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(curl_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(curl_file.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn('noproxy = "127.0.0.1,localhost,::1"', curl_file.read_text())
            data = env_file.read_text()
            entries = dict(line.split("=", 1) for line in data.splitlines() if line and not line.startswith("#"))
            self.assertEqual(set(entries), {"APP_TOKEN", "POSTGRES_PASSWORD", "APP_DB_PASSWORD"})
            self.assertEqual(len(set(entries.values())), 3)
            for value in entries.values():
                self.assertRegex(value, r"^[0-9a-f]{64}$")
                self.assertNotIn(value, result.stdout + result.stderr)
            before = env_file.read_bytes()
            repeated = self.helper("init", cwd=tmp)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(env_file.read_bytes(), before)
            checked = self.helper("check-env", cwd=tmp)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            for value in entries.values():
                self.assertNotIn(value, checked.stdout + checked.stderr)
            (Path(tmp) / "build").mkdir()
            (Path(tmp) / "build/fake-binary").write_text("must not ship")
            (Path(tmp) / "not-allowlisted.txt").write_text("private notes")
            for private_path in (".secrets-vm/client.curl", ".secrets-vps/client.curl", "backups/sensitive.dump"):
                private = Path(tmp) / private_path
                private.parent.mkdir()
                private.write_text(next(iter(entries.values())))
            archive = Path(tmp) / "source.tar.gz"
            packed = self.helper("pack", "--output", archive.name, cwd=tmp)
            self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
            with tarfile.open(archive, "r:gz") as source_archive:
                members = source_archive.getmembers()
                self.assertTrue(any(item.name.endswith("CMakeLists.txt") for item in members))
                for item in members:
                    self.assertFalse(item.issym() or item.islnk())
                    self.assertNotIn("..", Path(item.name).parts)
                    self.assertFalse(Path(item.name).is_absolute())
                    self.assertNotIn(".env", Path(item.name).parts)
                    self.assertNotIn(".secrets", Path(item.name).parts)
                    self.assertNotIn("build", Path(item.name).parts)
                    self.assertNotIn("not-allowlisted.txt", item.name)
                    if item.isfile():
                        body = source_archive.extractfile(item).read()
                        for value in entries.values():
                            self.assertNotIn(value.encode(), body)
            original = archive.read_bytes()
            self.assertNotEqual(self.helper("pack", "--output", archive.name, cwd=tmp).returncode, 0)
            self.assertEqual(archive.read_bytes(), original)

    def test_helper_does_not_follow_secret_or_archive_symlinks(self):
        for relative in (".env", ".secrets", ".secrets/client.curl"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(prefix="workshop-symlink-") as tmp:
                self.copy_fixture(tmp)
                target = Path(tmp) / "unrelated"
                target.write_text("preserve this")
                link = Path(tmp) / relative
                link.parent.mkdir(exist_ok=True)
                link.parent.chmod(0o700)
                link.symlink_to(target)
                self.assertNotEqual(self.helper("init", cwd=tmp).returncode, 0)
                self.assertEqual(target.read_text(), "preserve this")
        with tempfile.TemporaryDirectory(prefix="workshop-archive-link-") as tmp:
            self.copy_fixture(tmp)
            target = Path(tmp) / "unrelated"
            target.write_text("preserve this")
            output = Path(tmp) / "source.tar.gz"
            output.symlink_to(target)
            self.assertNotEqual(self.helper("pack", "--output", output.name, cwd=tmp).returncode, 0)
            self.assertEqual(target.read_text(), "preserve this")

    def test_source_symlink_and_invalid_env_are_refused_without_disclosure(self):
        with tempfile.TemporaryDirectory(prefix="workshop-source-link-") as tmp:
            self.copy_fixture(tmp)
            source = Path(tmp) / "app.cpp"
            source.unlink()
            target = Path(tmp) / "private"
            target.write_text("private-value-do-not-read")
            source.symlink_to(target)
            result = self.helper("pack", "--output", "source.tar.gz", cwd=tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("private-value-do-not-read", result.stdout + result.stderr)
            self.assertFalse((Path(tmp) / "source.tar.gz").exists())
        with tempfile.TemporaryDirectory(prefix="workshop-invalid-env-") as tmp:
            self.copy_fixture(tmp)
            self.assertEqual(self.helper("init", cwd=tmp).returncode, 0)
            path = Path(tmp) / ".env"
            valid = path.read_text()
            token = valid.splitlines()[0].partition("=")[2]
            for contents, mode in ((valid + valid.splitlines()[0] + "\n", 0o600),
                                   (valid + "UNEXPECTED=" + token + "\n", 0o600),
                                   (valid.replace(token, "wrong-value-secret"), 0o600),
                                   (valid, 0o644)):
                path.write_text(contents)
                path.chmod(mode)
                result = self.helper("check-env", cwd=tmp)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(token, result.stdout + result.stderr)
                self.assertNotIn("wrong-value-secret", result.stdout + result.stderr)

    def test_helper_native_launch_is_memory_loopback_and_without_admin_credentials(self):
        specification = importlib.util.spec_from_file_location("workshop_lab_for_test", EXAMPLE / "lab.py")
        helper = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(helper)
        with tempfile.TemporaryDirectory(prefix="workshop-native-helper-") as tmp:
            fixture = Path(tmp)
            helper.init_secrets(fixture)
            binary = fixture / "build/course_tasks"
            binary.parent.mkdir()
            binary.write_text("fixture, not executed")
            binary.chmod(0o700)
            with mock.patch.dict(os.environ, {"APP_STORAGE": "postgres", "APP_BIND": "0.0.0.0",
                                               "PGPASSWORD": "admin-secret", "PGSERVICE": "production",
                                               "POSTGRES_PASSWORD": "admin-secret", "APP_DB_PASSWORD": "db-secret"}):
                with mock.patch.object(helper.subprocess, "run", return_value=mock.Mock(returncode=0)) as launch:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(helper.run_native(fixture, 49123), 0)
            self.assertEqual(launch.call_args.args, ([str(binary)],))
            options = launch.call_args.kwargs
            self.assertFalse(options.get("shell", False))
            self.assertEqual(options["env"]["APP_STORAGE"], "memory")
            self.assertEqual(options["env"]["APP_BIND"], "127.0.0.1")
            self.assertEqual(options["env"]["APP_PORT"], "49123")
            for key in ("PGPASSWORD", "PGSERVICE", "POSTGRES_PASSWORD", "APP_DB_PASSWORD"):
                self.assertNotIn(key, options["env"])


class _WorkshopMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []
        self.chapter_ids = []
        self.commands = 0
        self.command_locations = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        for attribute in ("href", "src"):
            if attribute in values:
                self.links.append(values[attribute])
        if tag == "article" and "workshop-chapter" in values.get("class", "").split():
            self.chapter_ids.append(values.get("id"))
        if tag == "div" and "command" in values.get("class", "").split():
            self.commands += 1
        if "command-place" in values.get("class", "").split():
            self.command_locations += 1


class WorkshopPublication(unittest.TestCase):
    def chapter_commands(self, chapter):
        fragment = (ROOT / "content/service-workshop" / (chapter + ".html")).read_text()
        markup = _WorkshopMarkup()
        markup.feed(fragment)
        matches = re.findall(
            r'<div class="command([^"]*)"><div class="command-place">(.*?)</div><pre><code>(.*?)</code></pre></div>',
            fragment, re.S)
        self.assertEqual(len(matches), markup.commands, "every command must have an explicit location and code block")
        return [(classes.split(), unescape(label), unescape(code)) for classes, label, code in matches]

    @unittest.skipUnless(shutil.which("bash"), "bash is needed for parse-only command syntax checks")
    def test_all_copyable_shell_blocks_parse_without_execution(self):
        route = json.loads((ROOT / "content/service-workshop/route.json").read_text())
        count = 0
        for chapter in route["chapters"]:
            for index, (_, label, code) in enumerate(self.chapter_commands(chapter["id"])):
                with self.subTest(chapter=chapter["id"], block=index, context=label):
                    # -n reads syntax only. Clean environment and disabled startup
                    # profiles also prevent BASH_ENV or user shell setup running.
                    result = subprocess.run(["bash", "--noprofile", "--norc", "-n"],
                                            input=code + "\n", capture_output=True, text=True,
                                            env={"PATH": os.defpath, "LANG": "C.UTF-8"}, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    count += 1
        self.assertGreater(count, 30)

    def test_vm_ssh_setup_is_guest_console_and_aliases_remain_consistent(self):
        commands = self.chapter_commands("vm")
        setup = [(classes, label, code) for classes, label, code in commands if "apt install openssh-server" in code]
        self.assertEqual(len(setup), 1)
        classes, label, code = setup[0]
        self.assertIn("remote", classes)
        self.assertIn("Linux-VM", label)
        self.assertIn("консоль", label)
        self.assertIn("до первого SSH", label)
        self.assertNotIn("Локальный компьютер", label)
        self.assertIn("sudo systemctl enable --now ssh", code)
        self.assertIn("ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub", code)
        vm_assignments = [value for _, _, code in commands for value in re.findall(r"^VM_HOST=(\S+)$", code, re.M)]
        self.assertGreaterEqual(len(vm_assignments), 2)
        self.assertEqual(set(vm_assignments), {"course-vm"})
        fragment = (ROOT / "content/service-workshop/vm.html").read_text()
        configs = [unescape(value) for value in re.findall(r'<pre class="file-list"><code>(.*?)</code></pre>', fragment, re.S)]
        self.assertEqual(len(configs), 1)
        self.assertTrue(configs[0].startswith("Host course-vm\n"))
        self.assertIn("HostName 192.168.56.101", configs[0])
        self.assertIn("User learner", configs[0])
        self.assertIn("Port 22", configs[0])
        self.assertTrue(all("HostName " not in code and "Host course-vm" not in code for _, _, code in commands),
                        "SSH configuration is file content, not an executable/copy-command block")
        vps = (ROOT / "content/service-workshop/vps.html").read_text()
        self.assertIn("<code>VM_HOST=course-vps</code>", vps)
        self.assertNotIn("VM_HOST=course-vm", vps)
        vps_assignments = [value for _, _, code in self.chapter_commands("vps")
                           for value in re.findall(r"^VPS_HOST=(\S+)$", code, re.M)]
        self.assertEqual(vps_assignments, ["course-vps"])

    def test_home_bonus_entry_is_separate_from_course_stations(self):
        home = (ROOT / "cpp_backend_roadmap.html").read_text()
        match = re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>', home, re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        entries = [item for item in data["bonusFiles"] if item["file"] == "service_workshop.html"]
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["label"].strip())
        self.assertIn("Linux", entries[0]["desc"])
        self.assertFalse(any(stage.get("station", {}).get("file") == "service_workshop.html" for stage in data["stages"]))

    def test_nine_stages_and_fresh_generated_page(self):
        import build_service_workshop

        route = json.loads((ROOT / "content/service-workshop/route.json").read_text())
        expected = ["start", "local", "http", "database", "workload", "release", "vm", "vps", "operate"]
        self.assertEqual([item["id"] for item in route["chapters"]], expected)
        rendered = build_service_workshop.render()
        self.assertTrue((ROOT / "service_workshop.html").read_text() == rendered,
                        "regenerate the published workshop after editing its source")
        markup = _WorkshopMarkup()
        markup.feed(rendered)
        self.assertEqual(markup.chapter_ids, expected)
        self.assertEqual(len(markup.ids), len(set(markup.ids)), "duplicate HTML IDs")
        self.assertGreater(markup.commands, 10)
        self.assertEqual(markup.command_locations, markup.commands,
                         "every copyable command must name its execution environment")
        stations = {}
        for source in (ROOT / "content").glob("station*.json"):
            station = json.loads(source.read_text())
            stations[station["meta"]["sourceFile"]] = {section["id"] for section in station["theory"]}
        for href in markup.links:
            with self.subTest(href=href):
                parts = urlsplit(href)
                self.assertNotIn(parts.scheme, ("javascript", "data", "file"))
                if not parts.scheme and not parts.netloc:
                    if parts.path:
                        self.assertTrue((ROOT / parts.path).is_file(), "broken local workshop link")
                        self.assertNotIn(".env", Path(parts.path).parts)
                        self.assertNotIn(".secrets", Path(parts.path).parts)
                        section = parse_qs(parts.fragment).get("section", [])
                        if section:
                            self.assertIn(parts.path, stations, "section= used outside a course station")
                            self.assertEqual(len(section), 1)
                            self.assertIn(section[0], stations[parts.path], "unknown station theory section")
                    elif parts.fragment:
                        self.assertIn(parts.fragment, markup.ids, "broken workshop anchor")

    def test_renderer_rejects_unsafe_or_duplicate_ids_and_escapes_metadata(self):
        import build_service_workshop

        with tempfile.TemporaryDirectory(prefix="workshop-renderer-") as tmp:
            source = Path(tmp)
            chapter = {"id": "safe", "title": "<script>bad</script>",
                       "context": '"quoted" <value>', "lead": "<img>"}
            route = source / "route.json"
            (source / "safe.html").write_text("<p>Fixture chapter.</p>")
            with mock.patch.object(build_service_workshop, "SOURCE", source):
                route.write_text(json.dumps({"chapters": [chapter]}))
                rendered = build_service_workshop.render()
                self.assertNotIn("<script>bad</script>", rendered)
                self.assertIn("&lt;script&gt;bad&lt;/script&gt;", rendered)
                self.assertIn("&lt;img&gt;", rendered)
                for chapters in ([chapter, chapter], [{**chapter, "id": "../escape"}],
                                 [{**chapter, "id": 'bad\" onclick=\"x'}]):
                    route.write_text(json.dumps({"chapters": chapters}))
                    with self.subTest(chapters=chapters), self.assertRaises(ValueError):
                        build_service_workshop.render()

    def test_browser_only_navigates_and_copies_text(self):
        script = (ROOT / "assets/service-workshop.js").read_text()
        self.assertIn("navigator.clipboard.writeText(pre.textContent)", script)
        self.assertIn("hashchange", script)
        self.assertIn("aria-current", script)
        for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket(", "eval(", "new Function", "innerHTML", "document.write"):
            self.assertNotIn(forbidden, script)

    def test_transfer_and_backup_commands_are_guarded(self):
        source = ROOT / "content/service-workshop"
        scp_blocks = []
        for name in ("vm", "vps"):
            fragment = (source / (name + ".html")).read_text()
            blocks = [unescape(block) for block in re.findall(r"<pre><code>(.*?)</code></pre>", fragment, re.S)]
            for block in blocks:
                if "scp " not in block:
                    continue
                scp_blocks.append(block)
                lines = block.splitlines()
                for index, line in enumerate(lines):
                    if line.startswith("scp "):
                        self.assertGreater(index, 0, "scp needs a successful preceding preparation command")
                        self.assertTrue(lines[index - 1].rstrip().endswith("&&"), "do not copy after failed preparation")
                if ".secrets-" in block:
                    directories = [line for line in lines if line.startswith("mkdir ")]
                    self.assertEqual(len(directories), 1)
                    self.assertRegex(directories[0], r"^mkdir -m 700 \.secrets-(?:vm|vps) &&$")
                    self.assertIn("chmod 600 ", block)
                else:
                    self.assertTrue(block.startswith("python3 lab.py pack &&\n"))
                    self.assertIn("'mkdir -m 700 course-workshop-upload' &&\nscp ", block)
        self.assertEqual(len(scp_blocks), 3)
        operate = (source / "operate.html").read_text()
        blocks = [unescape(block) for block in re.findall(r"<pre><code>(.*?)</code></pre>", operate, re.S)]
        dump = next(block for block in blocks if " pg_dump " in block)
        self.assertTrue(dump.startswith("mkdir -m 700 backups &&\n(\n"))
        self.assertLess(dump.index("umask 077"), dump.index(" pg_dump "))
        self.assertLess(dump.index("set -C"), dump.index(" pg_dump "))
        self.assertIn("-Fc --no-owner --no-acl > backups/", dump)
        restore = next(block for block in blocks if "pg_restore -U" in block)
        self.assertIn("-d course_tasks_restore_check --exit-on-error --single-transaction", restore)
        self.assertNotRegex(restore, r"pg_restore[\s\S]*?-d course_tasks(?:\s|$)[\s\S]*?--exit-on-error")
        self.assertNotIn("--clean", restore)

    def test_reference_index_includes_all_chapters_and_citations(self):
        import build_sources

        rendered = build_sources.render()
        self.assertTrue((ROOT / "sources.html").read_text() == rendered, "sources.html needs regeneration")
        index = _WorkshopMarkup()
        index.feed(rendered)
        self.assertEqual(index.ids.count("service-workshop"), 1)
        route = json.loads((ROOT / "content/service-workshop/route.json").read_text())
        for chapter in route["chapters"]:
            self.assertIn("service_workshop.html#" + chapter["id"], index.links)
            fragment = _WorkshopMarkup()
            fragment.feed((ROOT / "content/service-workshop" / (chapter["id"] + ".html")).read_text())
            for href in fragment.links:
                if urlsplit(href).scheme in ("http", "https"):
                    self.assertIn(href, index.links, "workshop citation missing from the generated source index")
        self.assertIn("не означает, что инструкция была развёрнута на публичном VPS", rendered)

    def test_reference_generator_reads_new_fragment_links_and_escapes_labels(self):
        import build_sources

        with tempfile.TemporaryDirectory(prefix="workshop-source-index-") as tmp:
            fixture = Path(tmp)
            fragments = fixture / "content/service-workshop"
            fragments.mkdir(parents=True)
            (fixture / "content/visual-labs.json").write_text('{"labs":[]}')
            (fragments / "route.json").write_text(json.dumps({"chapters": [{"id": "fixture", "title": "<new chapter>"}]}))
            (fragments / "fixture.html").write_text(
                '<a href="https://example.org/new?a=1&amp;b=2">A &amp; B</a>'
                '<a href="https://example.org/new?a=1&amp;b=2">Duplicate</a>')
            with mock.patch.object(build_sources, "ROOT", fixture):
                rendered = build_sources.render()
            self.assertIn('href="service_workshop.html#fixture"', rendered)
            self.assertIn("&lt;new chapter&gt;", rendered)
            self.assertEqual(rendered.count('href="https://example.org/new?a=1&amp;b=2"'), 1)
            self.assertIn(">A &amp; B</a>", rendered)

    @unittest.skipUnless(shutil.which("gjs"), "gjs is needed for the shared station component checks")
    def test_shared_station_entries_exist_only_for_api_postgres_and_production(self):
        harness = r'''
const GLib = imports.gi.GLib, ByteArray = imports.byteArray;
const source = ByteArray.toString(GLib.file_get_contents(ARGV[0])[1]);
const start=source.indexOf('  function ServiceWorkshopEntry('), end=source.indexOf('  function Theory(');
if(start<0 || end<=start) throw new Error('shared workshop components missing');
const fragment=source.slice(start,end);
function check(value,message) {if(!value) throw new Error(message);}
function nodes(node) {return !node || typeof node!=='object' ? [] : [node,...(node.children||[]).flatMap(nodes)];}
const React={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),
  useState:initial=>[typeof initial==='function'?initial():initial,()=>{}]};
const expected={station8:'local',station9:'database',station10:'vm'};
const ids=['station0','station1','station2','station3','station4','station5','station5-linux','station6',
  'station7','station7-netlab','station8','station9-sql','station9','station10'];
for(const id of ids) {
  const meta={id,number:id.startsWith('station9')?9:0,logo:id};
  const window={matchMedia:()=>({matches:true}),COURSE_LABS:[]};
  const components=new Function('React','window','meta',
    'var h=React.createElement,useState=React.useState,theory=[]; function isWorkbook(){return false;}'+
    fragment+';return {ServiceWorkshopEntry,SubstationNav};')(React,window,meta);
  const card=components.ServiceWorkshopEntry();
  const nav=components.SubstationNav({items:[],store:{},active:'',view:'theory'});
  const targets=nodes(nav).filter(n=>n.type==='a' && (n.props.href||'').startsWith('service_workshop.html'));
  if(expected[id]) {
    const href='service_workshop.html#'+expected[id];
    const cardLinks=nodes(card).filter(n=>n.type==='a');
    check(cardLinks.length===1 && cardLinks[0].props.href===href,'correct workshop card target for '+id);
    check(targets.length===1 && targets[0].props.href===href,'correct sidebar workshop target for '+id);
    check(cardLinks[0].props.rel.includes('noopener') && targets[0].props.rel.includes('noopener'),'safe new tab for '+id);
  } else {
    check(card===null && targets.length===0,'no workshop entry in unrelated station '+id);
  }
}
print('PASS: shared card/sidebar only in 8, 9B and 10; 9A and other stations unaffected');
'''
        result = run(["gjs", "-c", harness, ROOT / "assets/station-app.js"], timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_publication_includes_only_allowlisted_workshop_sources(self):
        import build_publication

        files, _ = build_publication.collect()
        for path in ("roadmap/service_workshop.html", "roadmap/assets/service-workshop.css", "roadmap/assets/service-workshop.js"):
            self.assertTrue(path in files, "publication is missing " + path)
        prefix = "roadmap/examples/service-workshop/"
        names = {name[len(prefix):] for name in files if name.startswith(prefix)}
        expected = {"CMakeLists.txt", "app.cpp", "storage.hpp", "storage.cpp", "tests.cpp", "schema.sql", "Dockerfile",
                    "compose.yaml", "compose.https.yaml", "Caddyfile", "init-db.sh", "lab.py", "load.py", "README.md",
                    ".dockerignore", ".gitignore"}
        expected.update("release-lab/" + name for name in (
            "CMakeLists.txt", "Dockerfile", "client.cpp", "001-initial.sql", "002-expand-note.sql",
            "init-db.sh", "compose.yaml", "release_lab.py", "README.md", ".dockerignore", ".gitignore"))
        self.assertEqual(names, expected)
        for name in files:
            self.assertFalse(set(Path(name).parts) & {".env", ".secrets", "build", "__pycache__"})
            self.assertNotIn("content/service-workshop", name)
            self.assertNotIn("tools/verify_service_workshop", name)
        self.assertTrue(files["roadmap/service_workshop.html"] == (ROOT / "service_workshop.html").read_bytes(),
                        "published workshop differs from the checked-in generated page")

    @unittest.skipUnless(shutil.which("gjs"), "gjs is needed for the offline JavaScript DOM contract")
    def test_browser_hash_navigation_skip_link_and_copy_runtime(self):
        harness = r'''
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const source = ByteArray.toString(GLib.file_get_contents(ARGV[0])[1]);
function check(value, message) { if (!value) throw new Error(message); }
function world(hash, mobile=false, withMedia=true) {
  const objects = Object.create(null), events = {}, copies = [], timers = [];
  const viewport = {matches:mobile, events:{}, addEventListener(name,handler) {this.events[name]=handler;}};
  const contents = {open:true};
  const chapters = ['start','local','http','database','workload','release','vm','vps','operate'].map(id => {
    const item = {id, hidden:false, focused:0, scrolled:0,
      closest: () => item, querySelector: () => ({textContent:'Title '+id}),
      focus: () => { item.focused++; }, scrollIntoView: () => { item.scrolled++; }};
    objects[id] = item; return item;
  });
  const links = chapters.map(chapter => ({hash:'#'+chapter.id, attributes:{},
    setAttribute(key,value) {this.attributes[key]=value;}, removeAttribute(key) {delete this.attributes[key];}}));
  objects['workshop-status'] = {textContent:''};
  objects['workshop-contents'] = contents;
  objects['workshop-main'] = {closest: () => null, scrollIntoView: () => {}};
  objects['http-detail'] = {closest: () => chapters[2], scrolled:0,
    scrollIntoView() {this.scrolled++;}};
  const parent = {buttons:[], querySelector:() => ({textContent:'Local terminal'}),
    appendChild(button) {this.buttons.push(button);}};
  const pre = {textContent:'printf "safe $VALUE"\nsecond line\n', parentNode:parent};
  const document = {title:'', querySelectorAll: selector => selector === '.workshop-chapter' ? chapters :
      selector === '.workshop-contents nav a' ? links : selector === '.command pre' ? [pre] : [],
    getElementById: id => objects[id] || null,
    createElement: () => ({textContent:'', attributes:{}, handlers:{},
      setAttribute(key,value) {this.attributes[key]=value;},
      addEventListener(name,handler) {this.handlers[name]=handler;}})};
  const location = {hash};
  const window = {isSecureContext:true, scrollTo:() => {}, addEventListener:(name,handler) => {events[name]=handler;}};
  if(withMedia) window.matchMedia=query => {
    check(query === '(max-width: 780px)', 'contents follows the documented mobile breakpoint');
    return viewport;
  };
  const navigator = {clipboard:{writeText:text => {copies.push(text); return {then:ok => ok()};}}};
  new Function('document','location','window','navigator','setTimeout', source)(
      document, location, window, navigator, callback => timers.push(callback));
  return {objects,chapters,links,parent,pre,document,location,window,navigator,events,copies,timers,viewport,contents};
}
function selected(w, id) {
  check(w.chapters.filter(c => !c.hidden).map(c => c.id).join() === id, 'exactly one active chapter: '+id);
  check(w.links.filter(l => l.attributes['aria-current'] === 'page').map(l => l.hash).join() === '#'+id,
        'active chapter accessibility state: '+id);
}
let w = world('#http-detail');
selected(w,'http');
check(w.contents.open === true, 'desktop contents starts expanded');
check(w.objects['http-detail'].scrolled === 1, 'nested deep link scrolls into selected chapter');
check(w.document.title.startsWith('Title http'), 'title follows active chapter');
w.location.hash='#vm'; w.events.hashchange(); selected(w,'vm');
check(w.objects.vm.focused === 1, 'chapter navigation moves keyboard focus');
w.location.hash='#workload'; w.events.hashchange(); selected(w,'workload');
w.location.hash='#release'; w.events.hashchange(); selected(w,'release');
w.location.hash='#vm'; w.events.hashchange(); selected(w,'vm');
w.location.hash='#workshop-main'; w.events.hashchange(); selected(w,'vm');
w.location.hash='#not-a-chapter'; w.events.hashchange(); selected(w,'start');
w.location.hash='#%E0%A4%A'; w.events.hashchange(); selected(w,'start');
check(w.parent.buttons.length === 1, 'one copy action per command');
const button = w.parent.buttons[0];
check(button.attributes['aria-label'].includes('Local terminal'), 'copy action names command location');
button.handlers.click();
check(w.copies.length === 1 && w.copies[0] === w.pre.textContent, 'copy only literal displayed text');
check(button.textContent === 'Скопировано', 'copy success feedback');
w.window.isSecureContext=false; button.handlers.click();
check(w.copies.length === 1, 'insecure contexts do not attempt clipboard writes');
check(button.textContent === 'Выделите текст', 'manual copy fallback');
w.window.isSecureContext=true;
w.navigator.clipboard={writeText:() => ({then:(ok,fail) => fail(new Error('denied'))})};
button.handlers.click(); check(button.textContent === 'Выделите текст', 'denied clipboard fallback');
const mobile = world('#http',true);
selected(mobile,'http');
check(mobile.contents.open === false, 'mobile contents starts collapsed');
mobile.contents.open=true;
check(mobile.contents.open === true, 'mobile reader can manually expand contents');
mobile.location.hash='#database'; mobile.events.hashchange(); selected(mobile,'database');
check(mobile.contents.open === false, 'mobile chapter navigation closes contents');
mobile.viewport.matches=false; mobile.viewport.events.change();
check(mobile.contents.open === true, 'crossing to desktop expands contents');
mobile.viewport.matches=true; mobile.viewport.events.change();
check(mobile.contents.open === false, 'crossing back to mobile collapses contents');
mobile.parent.buttons[0].handlers.click();
check(mobile.copies[0] === mobile.pre.textContent, 'responsive contents does not change literal copying');
const fallback = world('#vm',false,false); selected(fallback,'vm');
check(fallback.contents.open === true, 'navigation works when matchMedia is unavailable');
print('PASS: deep links, hash routing, skip-link context, responsive contents, focus and literal copy fallback');
'''
        result = run(["gjs", "-c", harness, ROOT / "assets/service-workshop.js"], timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
