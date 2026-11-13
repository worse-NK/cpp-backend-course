#!/usr/bin/env python3
"""Explicit local integration test. Creates a fresh stand, never uses an existing project."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import lab


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-local-docker", action="store_true", required=True)
    parser.add_argument("--image", help="Reuse this exact local image instead of rebuilding (recorded in report)")
    parser.add_argument("--report", type=Path, required=True, help="Private JSON evidence, not course content")
    args = parser.parse_args(argv)
    lab.checked_docker()
    original_root = lab.ROOT
    temporary = Path(tempfile.mkdtemp(prefix="course-path-acceptance-"))
    stand = temporary / "lab"
    shutil.copytree(original_root, stand, ignore=shutil.ignore_patterns(".state", "build", "__pycache__"))
    lab.ROOT = stand
    checks = []
    issued_tokens = set()
    config = None
    report = {"profile": "local_integration_not_production_security_audit", "checks": checks,
              "host_ports": "API bound only to 127.0.0.1; no DB/broker host ports", "cleanup_succeeded": False,
              "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in original_root.iterdir() if path.is_file()},
              "limits": ["One PostgreSQL and one RabbitMQ node; no failover or power-loss test",
                         "HTTP loopback only, no TLS or brute-force defense",
                         "No exactly-once transport claim; receipt+effect atomic in PostgreSQL",
                         "Faults are explicit process exits at the three documented boundaries"]}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        print("PASS " + name, flush=True)

    def call(method, path, token=None, body=None, key=None):
        return lab.request(config, method, path, token=token, body=body, key=key)

    def login(user):
        token = lab.login(config, user)
        issued_tokens.add(token)
        return token

    def raw_request(method, path, body, token, key="invalid-input", content_type="application/json"):
        connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=8)
        try:
            connection.request(method, path, body=body, headers={"Content-Type": content_type,
                "Authorization": "Bearer " + token, "Idempotency-Key": key})
            response = connection.getresponse()
            response.read(lab.RESPONSE_LIMIT + 1)
            if response.getheader("X-Course-Lab") != config["lab_id"]:
                raise ValueError("Unexpected lab response")
            return response.status
        finally:
            connection.close()

    def task_count():
        return int(lab.sql(config, "SELECT count(*) FROM course_path.tasks"))

    def worker(service, mode, expected=0):
        result = lab.compose(config, "run", "--rm", "--no-deps", service, mode, capture=True, check=False, timeout=40)
        check(mode + " exit=" + str(expected), result.returncode == expected)
        if expected == 0:
            lines = result.stdout.strip().splitlines()
            return json.loads(lines[-1])
        return None

    def api_mode(mode):
        lab.compose(config, "up", "--detach", "--no-deps", "--force-recreate", "api", capture=True, api_mode=mode)
        lab.wait_ready(config)

    def totals(token):
        status, body, _ = call("GET", "/creation-total", token)
        check("creation total authenticated HTTP 200", status == 200)
        return body["total"]

    failure = None
    try:
        config = lab.init(free_port(), root=stand)
        report["project"] = config["project"]
        if args.image:
            inspect = subprocess.run(["docker", "image", "inspect", args.image], check=True,
                                     capture_output=True, text=True)
            image = json.loads(inspect.stdout)[0]
            report["prebuilt_image"] = {"reference": args.image, "id": image["Id"]}
            subprocess.run(["docker", "tag", image["Id"], "course-production-path:" + config["lab_id"]], check=True)
        else:
            lab.compose(config, "build", "api", timeout=1200)
        lab.compose(config, "up", "--detach", "--wait", "db", "broker", capture=True, timeout=180)
        lab.compose(config, "run", "--rm", "--no-deps", "seed", capture=True)
        lab.compose(config, "up", "--detach", "--no-deps", "api", capture=True)
        lab.wait_ready(config)
        report["postgres_version"] = lab.sql(config, "SELECT version()")
        report["rabbitmq_version"] = lab.compose(config, "exec", "-T", "broker", "rabbitmqctl", "version", capture=True).stdout.strip()
        report["sodium_version"] = lab.compose(config, "run", "--rm", "--no-deps", "--entrypoint", "dpkg-query", "api",
                                                "-W", "-f=${Version}", "libsodium23", capture=True).stdout.strip()

        check("anonymous tasks rejected", call("GET", "/tasks")[0] == 401)
        check("wrong password rejected", call("POST", "/login", body={"username": "alice", "password": "wrong"})[0] == 401)
        alice, bo = login("alice"), login("bo")
        check("password verifiers use library Argon2id format", lab.sql(config,
              "SELECT bool_and(password_verifier LIKE '$argon2id$%') FROM course_path.users") == "t")
        status, first, _ = call("POST", "/tasks", alice, {"title": "Alice first"}, "create-a")
        check("authenticated create commits task and outbox", status == 201 and first["version"] == 1 and task_count() == 1
              and lab.sql(config, "SELECT count(*) FROM course_path.outbox WHERE sent_at IS NULL") == "1")
        status, replay, headers = call("POST", "/tasks", alice, {"title": "Alice first"}, "create-a")
        check("same command returns original response without second row", status == 201 and replay == first and task_count() == 1
              and headers.get("Idempotent-Replay") == "true")
        check("same key different payload conflicts", call("POST", "/tasks", alice, {"title": "Other"}, "create-a")[0] == 409)
        status, bo_task, _ = call("POST", "/tasks", bo, {"title": "Bo first"}, "create-a")
        check("command key scoped to authenticated user", status == 201 and bo_task["id"] != first["id"] and task_count() == 2)
        foreign = "/tasks/" + str(first["id"])
        check("foreign read does not disclose task", call("GET", foreign, bo)[0] == 404)
        check("foreign update denied atomically", call("PUT", foreign, bo, {"title": "Stolen", "version": 1})[0] == 404
              and call("GET", foreign, alice)[1]["title"] == "Alice first")
        check("owner_id in body cannot establish identity", call("POST", "/tasks", bo,
                {"title": "Spoofed", "owner_id": 1}, "spoof")[0] == 400 and task_count() == 2)
        check("duplicate JSON fields rejected without creation", raw_request("POST", "/tasks",
              b'{"title":"A","title":"B"}', alice) == 400 and task_count() == 2)
        check("invalid UTF-8 rejected without creation", raw_request("POST", "/tasks",
              b'{"title":"\xff"}', alice) == 400 and task_count() == 2)
        check("wrong content type rejected", raw_request("POST", "/tasks", b'{"title":"A"}', alice,
              content_type="text/plain") == 415)
        check("out of signed range version rejected before SQL write", call("PUT", foreign, alice,
              {"title": "Out of range", "version": 18446744073709551615})[0] == 400
              and call("GET", foreign, alice)[1] == first)
        check("stale version conflicts", call("PUT", foreign, alice, {"title": "Changed", "version": 7})[0] == 409)
        status, changed, _ = call("PUT", foreign, alice, {"title": "Alice renamed", "version": 1})
        check("owner changes only own task and increments version", status == 200 and changed["version"] == 2)
        check("replaying create does not undo later update", call("POST", "/tasks", alice,
              {"title": "Alice first"}, "create-a")[1] == first and call("GET", foreign, alice)[1] == changed)
        check("consumer effect not synchronous with HTTP commit", totals(alice) == 0 and totals(bo) == 0)

        check("first relay publication confirmed", worker("relay", "relay-once")["status"] == "broker_confirmed")
        check("second relay publication confirmed", worker("relay", "relay-once")["status"] == "broker_confirmed")
        lab.compose(config, "restart", "broker", capture=True)
        lab.compose(config, "up", "--detach", "--wait", "broker", capture=True, timeout=180)
        check("first event survived broker restart", worker("consumer", "consume-once")["status"] == "effect_committed")
        check("second event survived broker restart", worker("consumer", "consume-once")["status"] == "effect_committed")
        check("persistent per-user totals after two events", totals(alice) == 1 and totals(bo) == 1)

        api_mode("api-crash-after-commit")
        lost_response = False
        try:
            call("POST", "/tasks", alice, {"title": "Commit before crash"}, "after-commit")
        except (OSError, http.client.HTTPException):
            lost_response = True
        api_mode("api")
        check("API process actually exited after commit before response", lost_response and task_count() == 3)
        status, recovered, _ = call("POST", "/tasks", alice, {"title": "Commit before crash"}, "after-commit")
        check("retry after unknown result finds the same command", status == 201 and task_count() == 3
              and call("GET", "/tasks/" + str(recovered["id"]), alice)[0] == 200)

        worker("relay", "relay-crash-after-confirm", 87)
        check("relay crash leaves unsent marker after broker accepted", lab.sql(config,
              "SELECT count(*) FROM course_path.outbox WHERE sent_at IS NULL") == "1")
        check("relay retry republishes same event", worker("relay", "relay-once")["status"] == "broker_confirmed")
        first_delivery = worker("consumer", "consume-once")
        duplicate = worker("consumer", "consume-once")
        check("duplicate publication has one receipt and one effect", first_delivery["status"] == "effect_committed"
              and duplicate["status"] == "duplicate" and duplicate["event_id"] == first_delivery["event_id"] and totals(alice) == 2)

        check("fourth task created", call("POST", "/tasks", alice, {"title": "Effect before ack"}, "after-effect")[0] == 201)
        worker("relay", "relay-once")
        worker("consumer", "consume-crash-after-effect", 88)
        check("receipt and effect committed before consumer died", totals(alice) == 3 and lab.sql(config,
              "SELECT count(*) FROM course_path.receipts") == "4")
        duplicate = worker("consumer", "consume-once")
        check("broker redelivery after consumer crash does not repeat effect", duplicate["status"] == "duplicate"
              and duplicate["redelivered"] is True and totals(alice) == 3)

        old_alice = alice
        alice = login("alice")
        check("new login invalidates former session", alice != old_alice and call("GET", "/tasks", old_alice)[0] == 401)
        check("logout revokes session on server", call("POST", "/logout", alice)[0] == 200 and call("GET", "/tasks", alice)[0] == 401)
        alice = login("alice")
        lab.sql(config, "UPDATE course_path.sessions SET created_at=clock_timestamp()-interval '30 minutes', "
                       "expires_at=clock_timestamp()-interval '1 minute' WHERE user_id=1")
        check("absolute expiry enforced on server", call("GET", "/tasks", alice)[0] == 401)
        alice = login("alice")
        lab.sql(config, "UPDATE course_path.sessions SET last_seen_at=clock_timestamp()-interval '6 minutes' WHERE user_id=1")
        check("idle expiry enforced on server", call("GET", "/tasks", alice)[0] == 401)
        alice = login("alice")

        lab.compose(config, "restart", "db", capture=True)
        lab.compose(config, "up", "--detach", "--wait", "db", capture=True, timeout=180)
        lab.wait_ready(config)
        check("database restart preserves session receipt and effect", totals(alice) == 3
              and lab.sql(config, "SELECT count(*) FROM course_path.receipts") == "4")
        lab.compose(config, "stop", "broker", capture=True)
        check("HTTP accepts obligation while broker is unavailable", call("POST", "/tasks", alice,
              {"title": "Broker temporarily down"}, "broker-down")[0] == 201)
        worker("relay", "relay-once", 1)
        check("broker outage does not erase pending obligation", lab.sql(config,
              "SELECT count(*) FROM course_path.outbox WHERE sent_at IS NULL") == "1" and totals(alice) == 3)
        lab.compose(config, "up", "--detach", "--wait", "broker", capture=True, timeout=180)
        worker("relay", "relay-once")
        check("delivery resumes after broker recovery", worker("consumer", "consume-once")["status"] == "effect_committed"
              and totals(alice) == 4)
        check("task for consumer DB outage created", call("POST", "/tasks", alice,
              {"title": "Receiver database down"}, "consumer-db-down")[0] == 201)
        worker("relay", "relay-once")
        lab.compose(config, "stop", "db", capture=True)
        worker("consumer", "consume-once", 1)
        lab.compose(config, "up", "--detach", "--wait", "db", capture=True, timeout=180)
        lab.wait_ready(config)
        check("database failure before effect does not acknowledge delivery", worker("consumer", "consume-once")["status"] == "effect_committed"
              and totals(alice) == 5 and lab.sql(config, "SELECT count(*) FROM course_path.receipts") == "6")
        check("API is not schema owner and cannot change receipts", lab.sql(config,
              "SELECT (SELECT nspowner<>(SELECT oid FROM pg_roles WHERE rolname='path_api') "
              "FROM pg_namespace WHERE nspname='course_path') AND NOT "
              "has_table_privilege('path_api','course_path.receipts','INSERT')") == "t")
        forbidden = lab.compose(config, "exec", "-T", "db", "psql", "-X", "-U", "postgres", "-d", "course_path",
                                "--set=ON_ERROR_STOP=on", "-c", "SET ROLE path_api; INSERT INTO course_path.receipts(consumer,event_id) "
                                "VALUES('unauthorized',repeat('0',64));", capture=True, check=False)
        check("actual API-role SQL mutation of receipts is denied", forbidden.returncode != 0
              and lab.sql(config, "SELECT count(*) FROM course_path.receipts WHERE consumer='unauthorized'") == "0")
        raw_tokens = issued_tokens | {lab.session("alice"), lab.session("bo")}
        all_secrets = raw_tokens | {lab.read_private(name + "_password").strip() for name in lab.SECRET_NAMES}
        logs = lab.compose(config, "logs", "--no-color", capture=True).stdout
        check("generated passwords and bearer tokens absent from service logs", not any(secret in logs for secret in all_secrets))
        hashes = lab.sql(config, "SELECT string_agg(token_digest,',') FROM course_path.sessions")
        check("session table contains digests not raw bearer tokens", not any(token in hashes for token in raw_tokens))
        check("remaining queue has no ready event", worker("consumer", "consume-once")["status"] == "empty")
        existing = call("GET", "/tasks", alice)[1]
        large_title = "\x01" * 200  # Valid title bytes; each is six JSON characters on output.
        for index in range(100 - len(existing)):
            status, _, _ = call("POST", "/tasks", alice, {"title": large_title}, "large-list-" + str(index))
            if status != 201:
                raise AssertionError("large list fixture creation")
        status, large, _ = call("GET", "/tasks", alice)
        check("helper accepts full 100-row list with maximally escaped bounded titles", status == 200 and len(large) == 100
              and sum(row["title"] == large_title for row in large) == 100 - len(existing)
              and len(json.dumps(large).encode()) > 8192)
        report["result"] = "pass"
    except Exception as error:
        # Static class/name only: never print HTTP bodies, headers, SQL values or credentials.
        failure = error
        report["result"] = "fail"
        report["failure_class"] = type(error).__name__
        if isinstance(error, AssertionError):
            report["failed_check"] = str(error)
        print("Acceptance failed: " + type(error).__name__, file=sys.stderr)
    finally:
        if config is not None:
            try:
                lab.require_owned(config)
                lab.compose(config, "down", "--remove-orphans", "--volumes", "--timeout", "8", capture=True, timeout=90)
                remaining = subprocess.run(["docker", "ps", "--all", "--quiet", "--filter", "label=" + lab.LABEL + "=" + config["lab_id"]],
                                           check=True, capture_output=True, text=True).stdout.strip()
                volumes = subprocess.run(["docker", "volume", "ls", "--quiet", "--filter", "label=" + lab.LABEL + "=" + config["lab_id"]],
                                         check=True, capture_output=True, text=True).stdout.strip()
                networks = subprocess.run(["docker", "network", "ls", "--quiet", "--filter", "label=" + lab.LABEL + "=" + config["lab_id"]],
                                          check=True, capture_output=True, text=True).stdout.strip()
                report["cleanup_succeeded"] = not remaining and not volumes and not networks
            except Exception as error:
                report["cleanup_failure"] = type(error).__name__
            report["retained_private_directory"] = str(temporary)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
    return 0 if failure is None and report["cleanup_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
