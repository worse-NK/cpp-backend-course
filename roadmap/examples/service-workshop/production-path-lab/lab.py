#!/usr/bin/env python3
"""Local-only launcher. Credentials and bearer tokens are never printed."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
LABEL = "org.cpp-course.production-path"
HEX = re.compile(r"[0-9a-f]{64}\Z")
PROJECT = re.compile(r"course-path-[0-9a-f]{12}\Z")
SECRET_NAMES = ("admin", "api", "relay", "consumer", "broker", "alice", "bo")
RESPONSE_LIMIT = 256 * 1024  # 100 bounded titles may expand when JSON escapes controls.


def private_directory(root=None):
    root = ROOT if root is None else root
    directory = os.open(root / ".state", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(directory)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(directory)
        raise ValueError("Expected an owned 0700 .state directory")
    return directory


def read_private(name, mode=0o444, root=None):
    directory = private_directory(root)
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "r", encoding="ascii") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != mode or info.st_nlink != 1):
            raise ValueError("Unexpected private file type, owner, permissions or link count")
        value = source.read(4097)
    if len(value) > 4096:
        raise ValueError("Private file is too large")
    return value


def new_file(directory, name, value, mode):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode, dir_fd=directory)
    with os.fdopen(descriptor, "w", encoding="ascii") as target:
        os.fchmod(target.fileno(), mode)
        target.write(value)
        target.flush()
        os.fsync(target.fileno())


def init(port, root=None):
    root = ROOT if root is None else root
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a high local port (1024..65535)")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.mkdir(".state", 0o700, dir_fd=parent)  # Never overwrite existing data.
    finally:
        os.close(parent)
    directory = private_directory(root)
    try:
        config = {"version": 1, "project": "course-path-" + secrets.token_hex(6),
                  "lab_id": secrets.token_hex(32), "port": port}
        new_file(directory, "settings.json", json.dumps(config) + "\n", 0o600)
        values = {name: secrets.token_hex(32) for name in SECRET_NAMES}
        for name, value in values.items():
            new_file(directory, name + "_password", value + "\n", 0o444)
        broker = ("default_user = course_path\ndefault_vhost = course_path\n"
                  "default_pass = " + values["broker"] + "\n"
                  "listeners.tcp.default = 5672\nmax_message_size = 65536\n"
                  "vm_memory_high_watermark.absolute = 256MiB\n"
                  "disk_free_limit.absolute = 256MiB\n")
        new_file(directory, "broker.conf", broker, 0o444)
    finally:
        os.close(directory)
    return config


def configuration(root=None):
    config = json.loads(read_private("settings.json", 0o600, root))
    if (set(config) != {"version", "project", "lab_id", "port"} or type(config["version"]) is not int or config["version"] != 1
            or not PROJECT.fullmatch(config["project"]) or not HEX.fullmatch(config["lab_id"])
            or type(config["port"]) is not int or not 1024 <= config["port"] <= 65535):
        raise ValueError("Unexpected lab settings")
    for name in SECRET_NAMES:
        if not HEX.fullmatch(read_private(name + "_password", root=root).strip()):
            raise ValueError("Unexpected generated credential")
    read_private("broker.conf", root=root)
    return config


def checked_docker():
    if any(os.environ.get(name) for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")):
        raise ValueError("Refused Docker endpoint override; use the local Docker daemon")
    result = subprocess.run(["docker", "context", "inspect"], check=True, capture_output=True, text=True)
    contexts = json.loads(result.stdout)
    if (len(contexts) != 1 or contexts[0].get("Endpoints", {}).get("docker", {}).get("Host")
            != "unix:///var/run/docker.sock"):
        raise ValueError("This launcher supports only the local Unix Docker socket")


def environment(config, api_mode="api"):
    result = {key: value for key, value in os.environ.items()
              if not key.startswith(("COMPOSE_", "PATH_"))}
    result.update(PATH_PROJECT=config["project"], PATH_LAB_ID=config["lab_id"],
                  PATH_PORT=str(config["port"]), PATH_API_MODE=api_mode)
    return result


def compose(config, *arguments, capture=False, check=True, timeout=120, api_mode="api"):
    return subprocess.run(["docker", "compose", "--env-file", "/dev/null", "--project-directory", str(ROOT),
                           "--file", str(ROOT / "compose.yaml"), "--project-name", config["project"],
                           *arguments], cwd=ROOT, env=environment(config, api_mode), check=check,
                          text=True, capture_output=capture, timeout=timeout)


def require_owned(config):
    # Read the exact project; never issue a daemon-wide stop/remove/prune.
    ids = compose(config, "ps", "--all", "--quiet", capture=True).stdout.split()
    for identity in ids:
        info = json.loads(subprocess.run(["docker", "inspect", identity], check=True,
                                        capture_output=True, text=True).stdout)[0]
        labels = info.get("Config", {}).get("Labels", {})
        if labels.get(LABEL) != config["lab_id"] or labels.get("com.docker.compose.project") != config["project"]:
            raise ValueError("Container ownership label mismatch")
    for suffix in ("pgdata", "brokerdata"):
        name = config["project"] + "_" + suffix
        found = subprocess.run(["docker", "volume", "inspect", name], capture_output=True, text=True)
        if found.returncode:
            continue  # A fresh project need not have volumes yet.
        labels = json.loads(found.stdout)[0].get("Labels", {})
        if labels.get(LABEL) != config["lab_id"] or labels.get("com.docker.compose.project") != config["project"]:
            raise ValueError("Volume ownership label mismatch")
    for suffix in ("lab", "edge"):
        network = subprocess.run(["docker", "network", "inspect", config["project"] + "_" + suffix], capture_output=True, text=True)
        if network.returncode == 0:
            labels = json.loads(network.stdout)[0].get("Labels", {})
            if labels.get(LABEL) != config["lab_id"] or labels.get("com.docker.compose.project") != config["project"]:
                raise ValueError("Network ownership label mismatch")


def request(config, method, path, *, token=None, body=None, key=None, target_check=True):
    if target_check:
        status, _, _ = request(config, "GET", "/health", target_check=False)
        if status != 200:
            raise ValueError("The expected local lab is not healthy")
    headers = {}
    if token is not None:
        if not HEX.fullmatch(token):
            raise ValueError("Invalid local session file")
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body, ensure_ascii=True).encode("ascii")
    if key is not None:
        headers["Idempotency-Key"] = key
    connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=8)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(RESPONSE_LIMIT + 1)
        if len(payload) > RESPONSE_LIMIT or response.getheader("X-Course-Lab") != config["lab_id"]:
            raise ValueError("Refused unexpected local server or response")
        return response.status, json.loads(payload), dict(response.getheaders())
    finally:
        connection.close()


def login(config, user):
    password = read_private(user + "_password").strip()
    status, body, _ = request(config, "POST", "/login", body={"username": user, "password": password})
    if status != 200 or not HEX.fullmatch(body.get("token", "")):
        raise ValueError("Login failed")
    # Safe replacement within the owned 0700 directory. Reject symlink/hardlink targets.
    directory = private_directory()
    try:
        name = user + "_session"
        try:
            old = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISREG(old.st_mode) or old.st_uid != os.getuid() or old.st_nlink != 1
                    or stat.S_IMODE(old.st_mode) != 0o600):
                raise ValueError("Unexpected session target")
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass
        new_file(directory, name, body["token"] + "\n", 0o600)
    finally:
        os.close(directory)
    return body["token"]


def session(user):
    value = read_private(user + "_session", 0o600).strip()
    if not HEX.fullmatch(value):
        raise ValueError("Invalid saved session")
    return value


def wait_ready(config):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        try:
            if request(config, "GET", "/ready", target_check=False)[0] == 200:
                return
        except (OSError, ValueError, http.client.HTTPException):
            pass
        time.sleep(0.3)
    raise ValueError("API did not become ready; inspect only this project's services")


def sql(config, statement):
    # This is a local administrator probe used only by inspect and acceptance.
    # No password appears in argv, stdout, the environment or a URL.
    return compose(config, "exec", "-T", "db", "psql", "-X", "-U", "postgres", "-d", "course_path",
                   "--set=ON_ERROR_STOP=on", "-A", "-t", "-c", statement, capture=True).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "check", "build", "up", "login", "tasks", "create", "rename",
                                             "total", "logout", "relay", "consume", "api-normal", "api-crash", "inspect",
                                             "restart-db", "restart-broker", "expire-idle", "expire-absolute", "down"))
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--user", choices=("alice", "bo"), default="alice")
    parser.add_argument("--key")
    parser.add_argument("--title")
    parser.add_argument("--id", type=int)
    parser.add_argument("--version", type=int)
    parser.add_argument("--fault", action="store_true")
    parser.add_argument("--delete-data", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            config = init(args.port)
            print("Created private local settings; no credentials displayed. Project: " + config["project"])
            return 0
        config = configuration()
        if args.command == "check":
            print("Private settings valid. Local URL: http://127.0.0.1:" + str(config["port"]))
            return 0
        if args.command in ("login", "tasks", "create", "rename", "total", "logout"):
            if args.command == "login":
                login(config, args.user)
                print("Logged in as " + args.user + "; session saved privately, not displayed")
                return 0
            token = session(args.user)
            method, path, body, key = "GET", "/tasks", None, None
            if args.command == "create":
                if args.title is None or args.key is None:
                    parser.error("create requires --title and --key")
                method, body, key = "POST", {"title": args.title}, args.key
            elif args.command == "rename":
                if args.id is None or args.version is None or args.title is None:
                    parser.error("rename requires --id, --version and --title")
                method, path, body = "PUT", "/tasks/" + str(args.id), {"title": args.title, "version": args.version}
            elif args.command == "total":
                path = "/creation-total"
            elif args.command == "logout":
                method, path = "POST", "/logout"
            status, value, _ = request(config, method, path, token=token, body=body, key=key)
            print(json.dumps({"http_status": status, "body": value}, ensure_ascii=False))
            return 0 if 200 <= status < 300 else 2
        checked_docker()
        require_owned(config)
        if args.command == "build":
            compose(config, "build", "api", timeout=1200)
        elif args.command == "up":
            compose(config, "up", "--detach", "--wait", "db", "broker", timeout=180)
            compose(config, "run", "--rm", "--no-deps", "seed")
            compose(config, "up", "--detach", "--no-deps", "api")
            wait_ready(config)
            print("Ready locally on 127.0.0.1:" + str(config["port"]))
        elif args.command in ("relay", "consume"):
            service = "relay" if args.command == "relay" else "consumer"
            mode = ("relay-crash-after-confirm" if args.fault else "relay-once") if service == "relay" else (
                "consume-crash-after-effect" if args.fault else "consume-once")
            result = compose(config, "run", "--rm", "--no-deps", service, mode, check=False)
            if result.returncode:
                print("Process exited with status " + str(result.returncode) + "; a fault flag is an intentional crash")
            return result.returncode
        elif args.command in ("api-normal", "api-crash"):
            compose(config, "up", "--detach", "--no-deps", "--force-recreate", "api",
                    api_mode="api" if args.command == "api-normal" else "api-crash-after-commit")
            wait_ready(config)
        elif args.command == "inspect":
            print(sql(config, "SELECT 'tasks='||count(*) FROM course_path.tasks UNION ALL "
                      "SELECT 'outbox_pending='||count(*) FROM course_path.outbox WHERE sent_at IS NULL UNION ALL "
                      "SELECT 'outbox_sent='||count(*) FROM course_path.outbox WHERE sent_at IS NOT NULL UNION ALL "
                      "SELECT 'receipts='||count(*) FROM course_path.receipts UNION ALL "
                      "SELECT 'user_'||user_id||'_total='||total FROM course_path.creation_totals;"))
        elif args.command in ("restart-db", "restart-broker"):
            compose(config, "restart", "db" if args.command == "restart-db" else "broker")
            compose(config, "up", "--detach", "--wait", "db", "broker", timeout=180)
            wait_ready(config)
        elif args.command in ("expire-idle", "expire-absolute"):
            user = 1 if args.user == "alice" else 2
            assignment = ("last_seen_at=clock_timestamp()-interval '6 minutes'" if args.command == "expire-idle"
                          else "created_at=clock_timestamp()-interval '30 minutes',expires_at=clock_timestamp()-interval '1 minute'")
            sql(config, "UPDATE course_path.sessions SET " + assignment + " WHERE user_id=" + str(user))
            print("Administrator-only lab fault: moved this user's server-side session timestamps into the past")
        elif args.command == "down":
            compose(config, "down", "--remove-orphans", "--timeout", "8")
            if args.delete_data:
                # Re-check exact ownership AFTER containers are stopped. No glob/prune.
                require_owned(config)
                for suffix in ("pgdata", "brokerdata"):
                    name = config["project"] + "_" + suffix
                    found = subprocess.run(["docker", "volume", "inspect", name], capture_output=True)
                    if found.returncode == 0:
                        subprocess.run(["docker", "volume", "rm", name], check=True)
                print("Removed only this lab's two data volumes; this deletion is not recoverable")
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError, http.client.HTTPException):
        print("Refused or failed: check this lab's private files, local Docker and service status. No secrets displayed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
