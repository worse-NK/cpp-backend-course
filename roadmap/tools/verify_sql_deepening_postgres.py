#!/usr/bin/env python3
"""Private opt-in execution of the exact 9A examples on cached PostgreSQL18.

Reuses the existing test assertions rather than maintaining new expected rows.
Only its own fresh labelled container is created/deleted. It has no network,
published ports, host mounts or persistent database volume. No image is pulled.
This is not a PostgreSQL plan, isolation or performance benchmark.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import unittest

import test_sql_architecture_deepening as teaching


ROOT = Path(__file__).resolve().parents[1]
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
LABEL = "org.cpp-backend-course.private-sql-validation"
NULL = "__PRIVATE_COURSE_SQL_NULL__"
ENVIRONMENT = {key: value for key, value in os.environ.items()
               if key not in ("DOCKER_HOST", "DOCKER_CONTEXT") and not key.startswith("PG")}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(arguments, *, source=None, timeout=15, allow_failure=False):
    result = subprocess.run(arguments, input=source, capture_output=True, text=True,
                            env=ENVIRONMENT, timeout=timeout)
    if result.returncode and not allow_failure:
        raise RuntimeError("Private Docker/psql command failed; no credentials or environment printed")
    return result


class Result:
    def __init__(self, output):
        records = list(csv.reader(io.StringIO(output)))
        self.description = records[0] if records else None
        self.rows = [tuple(self.value(value) for value in row) for row in records[1:]]

    @staticmethod
    def value(value):
        if value == NULL:
            return None
        if value.lstrip("-").isdigit():
            return int(value)
        return value

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, owner, schema):
        self.owner = owner
        self.schema = schema
        owner.psql(f'CREATE SCHEMA "{schema}";')

    def execute(self, source):
        output = self.owner.psql(f'SET search_path TO "{self.schema}";\n' + source)
        result = Result(output)
        self.owner.executions.append({
            "schema": self.schema,
            "sql_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "rows": result.rows if result.description is not None else None,
        })
        return result

    def close(self):
        # All schemas are isolated to the database inside the owned disposable
        # container. They disappear with its tmpfs, not a shared database.
        pass


class IsolatedPostgres:
    def __init__(self):
        self.token = secrets.token_hex(12)
        self.name = "course-sql9a-verify-" + self.token
        self.identifier = None
        self.executions = []
        self.schemas = 0
        self.cleanup_succeeded = False

    def inspect(self):
        record = json.loads(command(DOCKER + ["inspect", self.identifier]).stdout)[0]
        require(record["Id"] == self.identifier, "Owned container ID mismatch")
        require(record["Name"].lstrip("/") == self.name, "Owned container name mismatch")
        require(record["Config"]["Labels"].get(LABEL) == self.token, "Ownership label mismatch")
        return record

    def psql(self, source):
        return command(DOCKER + ["exec", "-i", self.identifier, "psql", "-X", "--csv", "-q",
                                  "-P", "null=" + NULL, "-v", "ON_ERROR_STOP=1", "-U", "postgres",
                                  "-d", "postgres"], source=source).stdout

    def setup(self):
        # Inspect a local reference and pin its cached ID. --pull=never also
        # makes an unexpected missing local image fail rather than access a registry.
        image = json.loads(command(DOCKER + ["image", "inspect", "postgres:18"]).stdout)[0]
        require("postgres:18" in image.get("RepoTags", []), "Cached official image tag missing")
        self.image_id = image["Id"]
        self.image_digests = image.get("RepoDigests", [])
        require(not command(DOCKER + ["ps", "-aq", "--filter", "name=^/" + self.name + "$"],
                            allow_failure=False).stdout.strip(), "Random owned name already exists")
        result = command(DOCKER + [
            "run", "--detach", "--pull=never", "--name", self.name,
            "--label", LABEL + "=" + self.token,
            "--network", "none", "--cpus", "1.0", "--memory", "512m",
            "--memory-swap", "512m", "--pids-limit", "128",
            "--mount", "type=tmpfs,destination=/var/lib/postgresql,tmpfs-size=268435456",
            "--env", "POSTGRES_HOST_AUTH_METHOD=trust", self.image_id,
            "-c", "max_connections=20", "-c", "shared_buffers=32MB", "-c", "fsync=on",
        ], timeout=30)
        self.identifier = result.stdout.strip()
        require(len(self.identifier) == 64 and all(c in "0123456789abcdef" for c in self.identifier),
                "Docker did not return a full owned container ID")
        record = self.inspect()
        config = record["HostConfig"]
        require(config["NetworkMode"] == "none" and not config.get("PortBindings"),
                "Owned container unexpectedly has network/ports")
        require(not config.get("Binds") and all(mount["Type"] == "tmpfs" for mount in record["Mounts"]),
                "Owned container unexpectedly has host or persistent mounts")
        require(config["Memory"] == 512 * 1024 * 1024 and config["NanoCpus"] == 1_000_000_000,
                "Owned resource bounds differ")
        deadline = time.monotonic() + 30
        while True:
            ready = command(DOCKER + ["exec", self.identifier, "pg_isready", "-U", "postgres"],
                            allow_failure=True, timeout=5)
            if ready.returncode == 0:
                break
            require(time.monotonic() < deadline, "Owned PostgreSQL did not become ready")
            time.sleep(0.1)
        self.version_num = int(self.psql("SHOW server_version_num;").strip().splitlines()[-1])
        require(180000 <= self.version_num < 190000, "Actual database is not PostgreSQL18")
        self.version = Result(self.psql("SELECT version();")).fetchall()[0][0]

    def connection(self):
        self.schemas += 1
        return Connection(self, "case_" + str(self.schemas))

    def cleanup(self):
        if self.identifier is None:
            # A failed/timed-out docker run can have created its container
            # before returning an ID. Resolve only our exact random name AND
            # ownership token before deciding that no cleanup is necessary.
            owned = command(DOCKER + ["ps", "-aq", "--no-trunc", "--filter",
                                       "name=^/" + self.name + "$", "--filter",
                                       "label=" + LABEL + "=" + self.token]).stdout.split()
            require(len(owned) <= 1, "Unexpected number of exact owned containers")
            if not owned:
                return
            self.identifier = owned[0]
        self.inspect()  # Exact ID/name/label validation before the only deletion.
        command(DOCKER + ["rm", "--force", self.identifier], timeout=20)
        remaining = command(DOCKER + ["ps", "-aq", "--filter", "label=" + LABEL + "=" + self.token])
        require(not remaining.stdout.strip(), "Owned labelled container remains")
        self.cleanup_succeeded = True


def listing_hashes():
    data = json.loads(teaching.SOURCE.read_text(encoding="utf-8"))
    result = {}
    for section in data["theory"]:
        if section["id"] in (teaching.JOIN_ID, teaching.WINDOW_ID):
            result[section["id"]] = [
                hashlib.sha256(block["code"].encode()).hexdigest()
                for block in section["blocks"] if block["type"] == "code"
            ]
    task = next(task for task in data["tasks"] if task["title"] == teaching.PRACTICE_TITLE)
    result[teaching.PRACTICE_TITLE] = {
        key: hashlib.sha256(task[key].encode()).hexdigest() for key in ("code", "solution")
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-docker", action="store_true", help="Run only the owned bounded disposable DB")
    parser.add_argument("--evidence", type=Path, help="Create a NEW private JSON evidence file")
    args = parser.parse_args()
    require(args.run_docker, "Explicit --run-docker is required")
    if args.evidence:
        require(not args.evidence.exists(), "Refusing to overwrite existing evidence")
    owner = IsolatedPostgres()
    hashes = listing_hashes()
    names = [
        "test_exact_join_listings_and_reported_results",
        "test_only_payment_branch_does_not_require_tasks",
        "test_only_task_branch_empty_inputs_and_equal_user_names",
        "test_exact_window_listings_and_reported_results",
        "test_frame_comparisons_do_not_silently_change_window_order",
        "test_partition_isolation_and_peer_input_reordering",
        "test_practice_setup_and_exact_solution_are_runnable",
    ]

    class PostgreSQLTeachingCases(teaching.SqlArchitectureDeepeningTest):
        def connect(self):
            connection = owner.connection()
            self.addCleanup(connection.close)
            return connection

    result = None
    try:
        owner.setup()
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite(PostgreSQLTeachingCases(name) for name in names))
        require(result.wasSuccessful(), "Exact teaching SQL assertions failed on PostgreSQL18")
        require(hashes == listing_hashes(), "Canonical SQL changed during validation")
    finally:
        owner.cleanup()
    evidence = {
        "status": "PASS", "postgres_version": owner.version,
        "server_version_num": owner.version_num, "cached_image_id": owner.image_id,
        "cached_image_digests": owner.image_digests, "container_name": owner.name,
        "ownership_label": LABEL, "cleanup_succeeded": owner.cleanup_succeeded,
        "limits": {"network": "none", "published_ports": [], "host_mounts": [],
                   "database_storage": "private 256MiB tmpfs", "cpu": 1, "memory_mib": 512,
                   "pids": 128, "new_image_pulls": False},
        "source": str(teaching.SOURCE.relative_to(ROOT.parent)),
        "source_sha256": hashlib.sha256(teaching.SOURCE.read_bytes()).hexdigest(),
        "exact_listing_sha256": hashes,
        "expectations_source": "roadmap/tools/test_sql_architecture_deepening.py",
        "expectations_sha256": hashlib.sha256(Path(teaching.__file__).read_bytes()).hexdigest(),
        "passed_test_names": names, "tests_run": result.testsRun,
        "executed_statement_count": len(owner.executions), "executions": owner.executions,
        "limitations": [
            "Exact listing execution and selected edge cases, not a proof of every possible SQL input",
            "No PostgreSQL execution-plan, concurrent-isolation or performance assertions",
            "The ROWS tie comparison asserts its ordered count multiset, not an unspecified peer identity",
            "Local trust authentication is confined to an owned network-none disposable container",
        ],
    }
    if args.evidence:
        with args.evidence.open("x", encoding="utf-8") as output:
            json.dump(evidence, output, ensure_ascii=False, indent=2)
            output.write("\n")
    print(f"PASS: actual PostgreSQL{owner.version_num}; {result.testsRun} reused SQL cases; "
          f"{len(owner.executions)} statements; owned container removed")


if __name__ == "__main__":
    main()
