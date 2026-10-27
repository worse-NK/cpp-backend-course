#!/usr/bin/env python3
"""Private opt-in release-lab verification on its OWN bounded PostgreSQL18.

Native mode builds the actual V1/V2 sources and copies binaries into a fresh
network-none PostgreSQL container. Compose mode runs the exact public build
and configuration in a fresh private source copy with its own internal network,
read-only bootstrap bind mounts and labelled volume. Neither publishes ports
or changes host settings/existing databases. Both require normal Docker access.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import subprocess
import tarfile
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/service-workshop/release-lab"
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
LABEL = "org.cpp-backend-course.private-release-test"


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


class OwnedLab:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.token = secrets.token_hex(10)
        self.name = "course-release-verify-" + self.token
        self.identifier = None
        self.cleanup_succeeded = False
        self.admin_password = secrets.token_hex(32)
        self.app_password = secrets.token_hex(32)
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("PG") and key not in
                            ("DOCKER_HOST", "DOCKER_CONTEXT", "POSTGRES_PASSWORD", "APP_DB_PASSWORD")}
        self.environment.update(POSTGRES_PASSWORD=self.admin_password, APP_DB_PASSWORD=self.app_password)
        self.checks = []
        self.observed = []
        self.stage = "not started"
        self.last_diagnostic = None

    def diagnostic(self, output):
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        text = str(output or "")
        for secret in (self.admin_password, self.app_password):
            text = text.replace(secret, "<redacted>")
        text = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1<redacted>@", text)
        return text[-5000:]

    def run(self, arguments, *, source=None, timeout=15, expected=0, environment=None, private_output=False):
        try:
            result = subprocess.run(arguments, input=source, capture_output=True, text=True,
                                    env=environment or self.environment, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            self.last_diagnostic = self.diagnostic(error.stdout) + self.diagnostic(error.stderr)
            raise RuntimeError("Timeout during " + self.stage) from None
        if expected is not None and result.returncode != expected:
            self.last_diagnostic = self.diagnostic(result.stdout + result.stderr)
            raise RuntimeError("Private build/Docker/client command failed; arbitrary diagnostics withheld")
        if not private_output:
            require(all(secret not in result.stdout + result.stderr for secret in
                        (self.admin_password, self.app_password)), "Unexpected secret-bearing diagnostic")
        return result

    def inspect(self):
        # Inspect includes environment credentials. Consume it privately; never
        # print it or include the record in acceptance evidence.
        record = json.loads(self.run(DOCKER + ["inspect", self.identifier], private_output=True).stdout)[0]
        require(record["Id"] == self.identifier and record["Name"].lstrip("/") == self.name
                and record["Config"]["Labels"].get(LABEL) == self.token, "Owned container mismatch")
        return record

    def setup(self, binary_dir):
        image = json.loads(self.run(DOCKER + ["image", "inspect", "postgres:18"]).stdout)[0]
        require("postgres:18" in image.get("RepoTags", []), "Cached official image reference missing")
        self.image_id = image["Id"]
        result = self.run(DOCKER + [
            "run", "--detach", "--pull=never", "--name", self.name,
            "--label", LABEL + "=" + self.token, "--network", "none",
            "--cpus", "1", "--memory", "512m", "--memory-swap", "512m", "--pids-limit", "128",
            "--mount", "type=tmpfs,destination=/var/lib/postgresql,tmpfs-size=268435456",
            "--env", "POSTGRES_PASSWORD", "--env", "APP_DB_PASSWORD",
            "--env", "POSTGRES_DB=release_course", "--env", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
            self.image_id, "-c", "shared_buffers=32MB", "-c", "max_connections=20",
        ], timeout=30)
        self.identifier = result.stdout.strip()
        record = self.inspect()
        config = record["HostConfig"]
        require(config["NetworkMode"] == "none" and not config.get("PortBindings")
                and not config.get("Binds") and all(m["Type"] == "tmpfs" for m in record["Mounts"]),
                "Private DB unexpectedly has ports/network/host mounts")
        deadline = time.monotonic() + 30
        while self.run(DOCKER + ["exec", self.identifier, "pg_isready", "-h", "127.0.0.1",
                                "-U", "postgres", "-d", "release_course"], expected=None).returncode:
            require(time.monotonic() < deadline, "Private PostgreSQL did not become ready")
            time.sleep(0.1)
        self.version_num = int(self.sql("SHOW server_version_num;"))
        require(180000 <= self.version_num < 190000, "PostgreSQL18 required")
        self.version = self.sql("SELECT version();")
        for version in (1, 2):
            self.run(DOCKER + ["cp", str(binary_dir / f"release_v{version}"),
                               self.identifier + f":/tmp/release_v{version}"])
        self.sql((SOURCE / "001-initial.sql").read_text())

    def sql(self, source, *, app=False, expected=0):
        arguments = DOCKER + ["exec", "-i", "--env", "APP_DB_PASSWORD"]
        environment = self.environment.copy()
        if app:
            environment["PGPASSWORD"] = self.app_password
            arguments += ["--env", "PGPASSWORD"]
        arguments += [self.identifier, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1"]
        if app:
            arguments += ["-h", "127.0.0.1", "-U", "release_app"]
        else:
            arguments += ["-U", "postgres"]
        arguments += ["-d", "release_course"]
        return self.run(arguments, source=source, expected=expected,
                        environment=environment).stdout.strip()

    def client(self, version, *arguments, expected=0, exact=None):
        environment = self.environment.copy()
        environment.update(PGHOST="127.0.0.1", PGPORT="5432", PGUSER="release_app",
                           PGDATABASE="release_course", PGPASSWORD=self.app_password)
        result = self.run(DOCKER + ["exec", "--user", "65532:65532", "--env", "PGHOST",
            "--env", "PGPORT", "--env", "PGUSER", "--env", "PGDATABASE", "--env", "PGPASSWORD",
            self.identifier, f"/tmp/release_v{version}", *arguments], environment=environment, expected=expected)
        if exact is not None:
            require(result.stdout.strip() == exact, "Unexpected exact V1/V2 result")
        self.observed.append({"binary": f"release_v{version}", "arguments": list(arguments),
                              "exit_code": result.returncode, "stdout": result.stdout.strip(),
                              "stderr": result.stderr.strip()})
        return result

    def contracts(self):
        self.client(1, "show", exact='v1 id=1 title="Original" version=1')
        self.client(1, "rename", "1", "Before expand", exact='v1 id=1 title="Before expand" version=2')
        pre = self.client(2, "show", expected=4)
        require("SQLSTATE=42703" in pre.stderr, "V2 unexpectedly works before its column exists")
        self.checks.append("V1 reads/writes original schema; real V2 rejects missing note with SQLSTATE42703")
        self.sql((SOURCE / "002-expand-note.sql").read_text())
        self.client(1, "show", exact='v1 id=1 title="Before expand" version=2')
        self.client(2, "show", exact='v2 id=1 title="Before expand" version=2 note=NULL')
        self.client(2, "set-note", "2", "Keep this note",
                    exact='v2 id=1 title="Before expand" version=3 note="Keep this note"')
        self.client(1, "rename", "3", "Edited by old version",
                    exact='v1 id=1 title="Edited by old version" version=4')
        self.client(2, "show", exact='v2 id=1 title="Edited by old version" version=4 note="Keep this note"')
        self.checks.append("Expanded schema supports both binaries; V1 named-column update preserves V2 note")
        self.client(2, "set-note", "3", "Must not appear", expected=2,
                    exact="not_applied: absent, stale version, or version exhausted")
        require(self.sql("SELECT title,version,note FROM release_lab.tasks;") ==
                "Edited by old version|4|Keep this note", "Stale writer changed data")
        self.checks.append("Both versions share one optimistic version; stale V2 write has no effect")
        self.client(1, "rename", "4", "Rollback stays compatible",
                    exact='v1 id=1 title="Rollback stays compatible" version=5')
        require(self.sql("SELECT title,version,note FROM release_lab.tasks;") ==
                "Rollback stays compatible|5|Keep this note", "V1 rollback lost V2 data")
        require(self.sql("SELECT version FROM release_lab.schema_migrations ORDER BY version;") == "1\n2",
                "Application rollback unexpectedly changed schema history")
        self.checks.append("Switch back to V1 changes real title; optional note and expanded schema remain intact")
        self.client(2, "set-note", "5", "Forward again",
                    exact='v2 id=1 title="Rollback stays compatible" version=6 note="Forward again"')
        self.checks.append("Forward switch to V2 uses preserved schema/data and updates note to version6")
        require(self.sql("SELECT pg_get_userbyid(relowner) FROM pg_class "
                         "WHERE oid='release_lab.tasks'::regclass;") == "release_owner", "Wrong schema owner")
        require(self.sql("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles "
                         "WHERE rolname='release_app';") == "t|f|f|f", "App role is overprivileged")
        require(self.sql("SELECT pg_has_role('release_app','release_owner','MEMBER'), "
                         "has_schema_privilege('release_app','release_lab','CREATE'), "
                         "has_column_privilege('release_app','release_lab.tasks','note','SELECT'), "
                         "has_column_privilege('release_app','release_lab.tasks','note','UPDATE');") == "f|f|t|t",
                "Migration and app role boundaries differ")
        self.sql("ALTER TABLE release_lab.tasks ADD COLUMN forbidden integer;", app=True, expected=3)
        self.sql("SELECT * FROM release_lab.schema_migrations;", app=True, expected=3)
        self.sql((SOURCE / "002-expand-note.sql").read_text(), expected=3)
        require(self.sql("SELECT version FROM release_lab.schema_migrations ORDER BY version;") == "1\n2",
                "Duplicate migration altered history")
        self.checks.append("Migration owner differs from app; app cannot ALTER/read migration history; reapply fails without mutation")
        self.client(1, "set-note", "6", "not a V1 command", expected=1)
        for value in ("0", "-1", "01", "9223372036854775808"):
            self.client(1, "rename", value, "invalid", expected=1)
        self.client(1, "rename", "6", "O'Reilly", exact='v1 id=1 title="O\'Reilly" version=7')
        self.client(2, "show", exact='v2 id=1 title="O\'Reilly" version=7 note="Forward again"')
        self.checks.append("Invalid commands/versions rejected; quoted title remains parameter data and preserves note")

    def cleanup(self):
        if self.identifier is None:
            owned = self.run(DOCKER + ["ps", "-aq", "--no-trunc", "--filter", "name=^/" + self.name + "$",
                                      "--filter", "label=" + LABEL + "=" + self.token]).stdout.split()
            require(len(owned) <= 1, "Unexpected number of owned containers")
            if not owned:
                return
            self.identifier = owned[0]
        self.inspect()
        self.run(DOCKER + ["rm", "--force", self.identifier], timeout=20)
        require(not self.run(DOCKER + ["ps", "-aq", "--filter", "label=" + LABEL + "=" + self.token]).stdout.strip(),
                "Owned container remains")
        self.cleanup_succeeded = True


class OwnedComposeLab(OwnedLab):
    """Public runtime/config; optional explicitly private verified-cache recipe."""
    def __init__(self, directory, build_timeout=300, offline_cache=None):
        super().__init__(directory)
        self.build_timeout = build_timeout
        files = ("client.cpp", "CMakeLists.txt", "001-initial.sql", "002-expand-note.sql", "compose.yaml",
                 "Dockerfile", "init-db.sh", "release_lab.py", "README.md", ".dockerignore", ".gitignore")
        for filename in files:
            shutil.copy2(SOURCE / filename, self.directory / filename)
        spec = importlib.util.spec_from_file_location("private_release_settings", self.directory / "release_lab.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.init(self.directory)
        settings = helper.read_env(self.directory)
        self.name = settings["RELEASE_LAB_PROJECT"]
        self.admin_password = settings["POSTGRES_PASSWORD"]
        self.app_password = settings["APP_DB_PASSWORD"]
        for key in ("RELEASE_LAB_PROJECT", "POSTGRES_PASSWORD", "APP_DB_PASSWORD"):
            self.environment.pop(key, None)  # Real Compose reads its fresh private .env.
        self.compose = DOCKER + ["compose", "--project-directory", str(self.directory),
            "--env-file", str(self.directory / ".env"), "-f", str(self.directory / "compose.yaml")]
        self.offline_cache_sha256 = None
        if offline_cache:
            expected = re.search(r"URL_HASH SHA256=([0-9a-f]{64})", (SOURCE / "CMakeLists.txt").read_text())[1]
            require(offline_cache.stat().st_size <= 10 * 1024 * 1024, "Unexpected archive size")
            self.offline_cache_sha256 = hashlib.sha256(offline_cache.read_bytes()).hexdigest()
            require(self.offline_cache_sha256 == expected, "Offline archive differs from the public CMake pin")
            extraction = self.directory / "cache-extracted"
            with tarfile.open(offline_cache, "r:gz") as archive:
                archive.extractall(extraction, filter="data")
            roots = list(extraction.iterdir())
            require(len(roots) == 1 and roots[0].is_dir(), "Unexpected verified source archive structure")
            shutil.copytree(roots[0], self.directory / "offline-libpqxx")
            recipe = (SOURCE / "Dockerfile").read_text()
            copy = "COPY CMakeLists.txt client.cpp ./"
            configure = "RUN cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release " + "\\" + "\n"
            require(recipe.count(copy) == 1 and recipe.count(configure) == 1, "Public recipe shape changed")
            recipe = recipe.replace(copy, copy + "\nCOPY offline-libpqxx/ /opt/course-libpqxx/")
            offline_flags = ("    -DFETCHCONTENT_SOURCE_DIR_LIBPQXX=/opt/course-libpqxx " + "\\" + "\n" +
                             "    -DFETCHCONTENT_FULLY_DISCONNECTED=ON " + "\\" + "\n")
            recipe = recipe.replace(configure, configure.replace("RUN ", "RUN --network=none ", 1) + offline_flags)
            (self.directory / "Dockerfile.offline").write_text(recipe)
            override = {"services": {name: {"build": {"dockerfile": "Dockerfile.offline"}}
                                      for name in ("v1", "v2")}}
            (self.directory / "compose.offline.json").write_text(json.dumps(override))
            self.compose += ["-f", str(self.directory / "compose.offline.json")]
        self.created = False

    def public_build(self):
        """Stream stage changes; never wait silently for a complete long build."""
        arguments = self.compose + ["--progress", "plain", "build", "v1", "v2"]
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env=self.environment)
        captured = b""
        pending = b""
        last_line = "waiting for first build output"
        started = last_report = time.monotonic()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                while selector.get_map():
                    if time.monotonic() - started > self.build_timeout:
                        self.last_diagnostic = self.diagnostic(captured)
                        raise RuntimeError("Timeout during exact public Dockerfile build; last stage: " + last_line)
                    for key, _ in selector.select(timeout=1):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        captured = (captured + chunk)[-65536:]
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            last_line = self.diagnostic(line)
                            if re.match(r"#\d+ (\[|ERROR|CANCELED)", last_line) or "CMake Error" in last_line:
                                print("BUILD: " + last_line, flush=True)
                                last_report = time.monotonic()
                    if time.monotonic() - last_report > 15:
                        print("BUILD: waiting; last output: " + last_line[-400:], flush=True)
                        last_report = time.monotonic()
                process.wait(timeout=5)
                if process.returncode:
                    self.last_diagnostic = self.diagnostic(captured)
                    raise RuntimeError("Public Dockerfile build failed; inspect private diagnostic excerpt")
                print("STAGE: " + ("private offline-cache" if self.offline_cache_sha256 else "public") +
                      " Dockerfile build completed", flush=True)
            finally:
                if process.poll() is None:
                    process.kill()  # Only our exact local Docker CLI child.
                    process.wait(timeout=5)
                process.stdout.close()

    def ownership(self):
        ids = self.run(DOCKER + ["ps", "-aq", "--no-trunc", "--filter",
                               "label=com.docker.compose.project=" + self.name]).stdout.split()
        for identifier in ids:
            record = json.loads(self.run(DOCKER + ["inspect", identifier], private_output=True).stdout)[0]
            labels = record["Config"]["Labels"]
            require(labels.get("org.cpp-backend-course.release-lab") == self.name and
                    labels.get("com.docker.compose.service") in ("db", "v1", "v2"),
                    "Unexpected container in private Compose project")
            require(not record["HostConfig"].get("PortBindings"), "Public lab unexpectedly publishes a port")
            if labels.get("com.docker.compose.service") == "db":
                require(record["HostConfig"]["Memory"] == 512 * 1024 * 1024 and
                        record["HostConfig"]["NanoCpus"] == 1_000_000_000 and
                        record["HostConfig"]["PidsLimit"] == 128, "Public database resource limits differ")
        volumes = self.run(DOCKER + ["volume", "ls", "-q", "--filter",
                                    "label=com.docker.compose.project=" + self.name]).stdout.split()
        require(all(volume == self.name + "_pgdata" for volume in volumes), "Unexpected owned volume name")
        for volume in volumes:
            metadata = json.loads(self.run(DOCKER + ["volume", "inspect", volume]).stdout)[0]
            require(metadata["Labels"].get("org.cpp-backend-course.release-lab") == self.name,
                    "Owned volume custom label missing")
        networks = self.run(DOCKER + ["network", "ls", "-q", "--filter",
                                     "label=com.docker.compose.project=" + self.name]).stdout.split()
        for network in networks:
            metadata = json.loads(self.run(DOCKER + ["network", "inspect", network]).stdout)[0]
            require(metadata["Name"] == self.name + "_backend" and metadata["Internal"] is True and
                    metadata["Labels"].get("org.cpp-backend-course.release-lab") == self.name,
                    "Unexpected private Compose network")
        return ids, volumes, networks

    def setup(self, binary_dir=None):
        require(self.ownership() == ([], [], []), "Random project already exists; refusing reuse")
        # The public Compose path uses this exact official tag, not a substitute.
        image = json.loads(self.run(DOCKER + ["image", "inspect", "postgres:18-bookworm"]).stdout)[0]
        self.image_id = image["Id"]
        self.run(self.compose + ["--profile", "tools", "config", "--quiet"])
        self.created = True
        self.stage = "exact public Compose database startup"
        print("STAGE: public Compose database startup", flush=True)
        self.run(self.compose + ["up", "-d", "--wait", "--wait-timeout", "120", "db"], timeout=150)
        self.ownership()
        # Real unchanged Dockerfile, including both stages and pinned FetchContent.
        self.stage = "private offline-cache Dockerfile build" if self.offline_cache_sha256 else "exact public Dockerfile build"
        print("STAGE: " + self.stage, flush=True)
        self.public_build()
        self.version_num = int(self.sql("SHOW server_version_num;"))
        require(180000 <= self.version_num < 190000, "PostgreSQL18 required")
        self.version = self.sql("SELECT version();")
        self.checks.append("Verified-cache private recipe built exact C++ clients; public Compose runtime/schema unchanged"
            if self.offline_cache_sha256 else
            "Exact public Dockerfile built both C++ clients; exact Compose initialized a fresh labelled project")
        self.stage = "exact public Compose V1/V2 migration contracts"
        print("STAGE: compiled V1/V2 + migration/rollback contracts", flush=True)

    def sql(self, source, *, app=False, expected=0):
        environment = self.environment.copy()
        arguments = self.compose + ["exec", "-T"]
        if app:
            environment["PGPASSWORD"] = self.app_password
            arguments += ["-e", "PGPASSWORD"]
        arguments += ["db", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1"]
        if app:
            arguments += ["-h", "127.0.0.1", "-U", "release_app"]
        else:
            arguments += ["-U", "postgres"]
        arguments += ["-d", "release_course"]
        return self.run(arguments, source=source, expected=expected, environment=environment).stdout.strip()

    def client(self, version, *arguments, expected=0, exact=None):
        result = self.run(self.compose + ["run", "--rm", "--no-deps", f"v{version}", *arguments],
                          expected=expected, timeout=25)
        if exact is not None:
            require(result.stdout.strip() == exact, "Unexpected public Compose V1/V2 output")
        self.observed.append({"binary": f"release_v{version}", "arguments": list(arguments),
                              "exit_code": result.returncode, "stdout": result.stdout.strip()})
        return result

    def cleanup(self):
        if not self.created:
            return
        _, volumes, _ = self.ownership()
        self.run(self.compose + ["down", "--timeout", "10"], timeout=30)
        for volume in volumes:
            self.run(DOCKER + ["volume", "rm", volume])
        require(self.ownership() == ([], [], []), "Owned Compose resources remain")
        # Only remove the fresh owned image tag; never force-delete shared images.
        reference = self.name + "-clients:local"
        image = self.run(DOCKER + ["image", "inspect", reference], expected=None, private_output=True)
        if image.returncode == 0:
            require(reference in json.loads(image.stdout)[0].get("RepoTags", []), "Owned build image tag mismatch")
            self.run(DOCKER + ["image", "rm", reference])
        self.cleanup_succeeded = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-docker", action="store_true")
    parser.add_argument("--run-compose", action="store_true", help="Run the exact public Dockerfile/Compose flow")
    parser.add_argument("--compose-build-timeout", type=int, default=300, help="Bounded public build timeout, 30..300s")
    parser.add_argument("--offline-cache", type=Path, help="Explicit private offline recipe using a hash-verified libpqxx archive")
    parser.add_argument("--pqxx-prefix", type=Path)
    parser.add_argument("--pg-include", type=Path)
    parser.add_argument("--pg-library", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    require(args.run_docker != args.run_compose, "Choose exactly one explicit execution mode")
    require(args.run_compose or all((args.pqxx_prefix, args.pg_include, args.pg_library)),
            "Native mode requires existing libpqxx/libpq development paths")
    require(30 <= args.compose_build_timeout <= 300, "Build timeout must stay within 30..300 seconds")
    require(not args.offline_cache or args.run_compose, "Offline cache applies only to explicit Compose validation")
    require(not args.evidence or not args.evidence.exists(), "Refusing to overwrite evidence")
    files = ("client.cpp", "CMakeLists.txt", "001-initial.sql", "002-expand-note.sql", "compose.yaml",
             "Dockerfile", "init-db.sh", "release_lab.py")
    hashes = {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in files}
    with tempfile.TemporaryDirectory(prefix="course-release-verify-") as directory:
        owner = OwnedComposeLab(directory, args.compose_build_timeout, args.offline_cache) if args.run_compose else OwnedLab(directory)
        build = Path(directory) / "build"
        if not args.run_compose:
            owner.run(["cmake", "-S", str(SOURCE), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                       "-DRELEASE_USE_INSTALLED_PQXX=ON", "-DCMAKE_PREFIX_PATH=" + str(args.pqxx_prefix),
                       "-DPostgreSQL_INCLUDE_DIR=" + str(args.pg_include),
                       "-DPostgreSQL_LIBRARY=" + str(args.pg_library)], timeout=30)
            owner.run(["cmake", "--build", str(build), "--parallel", "2"], timeout=90)
        error = None
        try:
            owner.setup(build)
            owner.contracts()
        except Exception as failure:
            error = {"type": type(failure).__name__, "stage": owner.stage, "message": str(failure)}
        finally:
            owner.cleanup()
        if error is not None:
            failure_evidence = {"result": "failed", "error": error,
                "sanitized_diagnostic_excerpt": owner.last_diagnostic,
                "owned_resources_removed": owner.cleanup_succeeded,
                "source_sha256": hashes, "owned_project_or_container": owner.name,
                "limits": ["No successful Docker build or client run is claimed for this failed attempt"]}
            if args.evidence:
                with args.evidence.open("x", encoding="utf-8") as output:
                    json.dump(failure_evidence, output, ensure_ascii=False, indent=2)
                    output.write("\n")
            raise RuntimeError(error["message"] + "; owned resources removed; inspect private failed-attempt evidence")
        require(hashes == {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in files},
                "Lab source changed during verification")
        evidence = {"result": "passed", "server_version_num": owner.version_num, "postgres_version": owner.version,
            "runtime": ("offline_cache_validation" if args.offline_cache else "exact public Compose build/run")
                if args.run_compose else "native binaries in isolated PostgreSQL container",
            "offline_cache_sha256": getattr(owner, "offline_cache_sha256", None),
            "owned_project_or_container": owner.name,
            "cached_image_id": owner.image_id, "source_sha256": hashes, "checks": owner.checks,
            "observed_client_results": owner.observed, "owned_container_removed": owner.cleanup_succeeded,
            "isolation": {"network": "owned internal bridge" if args.run_compose else "none",
                          "published_ports": [], "host_mounts": "own read-only bootstrap SQL/scripts" if args.run_compose else [], "cpu": 1,
                          "memory_mib": 512, "pids": 128,
                          "database_storage": "own named volume, removed after validation" if args.run_compose else "private 256MiB tmpfs"},
            "limits": ["Actual compiled C++ V1/V2 and PostgreSQL SQL; no HTTP rolling deployment or drain",
                       ("Public multi-stage recipe's external download was NOT validated; private verified-source cache override used"
                        if args.offline_cache else "Exact public multi-stage Dockerfile and Compose flow") if args.run_compose else
                       "Native build uses existing exact libpqxx7.10.1/libpq; public Dockerfile/Compose not exercised by this mode",
                       "No public VPS/TLS, production data, host limits, broker or replication cluster"]}
        if args.evidence:
            with args.evidence.open("x", encoding="utf-8") as output:
                json.dump(evidence, output, ensure_ascii=False, indent=2)
                output.write("\n")
        for check in owner.checks:
            print("PASS: " + check)
        print("PASS: PostgreSQL18; exact compiled V1/V2; owned container removed")


if __name__ == "__main__":
    main()
