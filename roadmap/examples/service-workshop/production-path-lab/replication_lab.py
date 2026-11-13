#!/usr/bin/env python3
"""Fresh local PG18 experiment: receive/replay, fenced manual promotion, base-backup rebuild."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

import lab

LABEL = "org.cpp-course.pg-recovery"
IMAGE = "postgres:18-bookworm"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-local-docker", action="store_true", required=True)
    parser.add_argument("--interactive", action="store_true", help="Pause between phases; Enter continues, Ctrl-C cleans up")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    lab.checked_docker()
    if args.report.exists():
        raise ValueError("The report must be a new file")
    if not args.report.parent.is_dir():
        raise ValueError("The report's parent directory must already exist")
    project = "course-pg-recovery-" + secrets.token_hex(6)
    temporary = Path(tempfile.mkdtemp(prefix=project + "-"))
    containers, volumes, networks, checks = [], [], [], []
    report = {"project": project, "checks": checks, "cleanup_succeeded": False,
              "limits": ["Single local Docker host, no host ports, new internal network and volumes",
                         "Asynchronous replication; replay deliberately paused, timestamps are not a latency benchmark",
                         "Manual verified stop+network isolation before promotion, not automatic production fencing",
                         "Rebuild is a fresh physical base backup, not pg_rewind, PITR or proof of zero data loss"],
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def docker(*command, check=True, timeout=60, stdin=None):
        return subprocess.run(["docker", *command], check=check, input=stdin, text=True,
                              capture_output=True, timeout=timeout)

    def owned(kind, identity):
        info = json.loads(docker(kind, "inspect", identity).stdout)[0] if kind != "container" else json.loads(docker("inspect", identity).stdout)[0]
        labels = info.get("Config", {}).get("Labels", {}) if kind == "container" else info.get("Labels", {})
        if labels.get(LABEL) != project:
            raise ValueError("Resource ownership mismatch")
        return info

    def check(name, condition, **facts):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, **facts})
        print("PASS " + name + (": " + json.dumps(facts, ensure_ascii=False) if facts else ""), flush=True)

    def pause(title):
        print("\n" + title, flush=True)
        if args.interactive:
            input("Enter — продолжить; Ctrl-C — завершить с очисткой своего стенда: ")

    def sql(node, statement, check=True):
        result = docker("exec", "--interactive", node, "psql", "-X", "-q", "-U", "postgres", "-d", "postgres",
                        "--set=ON_ERROR_STOP=on", "-A", "-t", stdin=statement + "\n", check=check)
        return result.stdout.strip() if check else result

    def wait_for(node, query, expected, seconds=40):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = sql(node, query, check=False)
            if result.returncode == 0 and result.stdout.strip() == expected:
                return result.stdout.strip()
            time.sleep(0.2)
        raise AssertionError("bounded wait: " + node.rsplit("-", 1)[-1])

    def volume(suffix):
        name = project + "-" + suffix
        docker("volume", "create", "--label", LABEL + "=" + project, name)
        volumes.append(name)
        return name

    def run_node(suffix, data_volume, *, peer=None, slot=None):
        name = project + "-" + suffix
        common = ["run", "--detach", "--name", name, "--label", LABEL + "=" + project,
                  "--network", project, "--network-alias", suffix, "--read-only", "--cpus", "0.75", "--memory", "384m",
                  "--pids-limit", "80", "--shm-size", "64m", "--security-opt", "no-new-privileges:true",
                  "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,size=8m", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
                  "--mount", "type=volume,source=" + data_volume + ",target=/var/lib/postgresql",
                  "--mount", "type=bind,source=" + str(temporary / "admin_password") + ",target=/run/secrets/admin_password,readonly",
                  "--mount", "type=bind,source=" + str(temporary / "hba.conf") + ",target=/run/secrets/hba.conf,readonly",
                  "--mount", "type=bind,source=" + str(temporary / "replication.pgpass") + ",target=/run/secrets/replication.pgpass,readonly",
                  "--env", "PGDATA=/var/lib/postgresql/18/docker", "--env", "POSTGRES_PASSWORD_FILE=/run/secrets/admin_password"]
        settings = ["postgres", "-c", "hba_file=/run/secrets/hba.conf", "-c", "wal_level=replica",
                    "-c", "max_wal_senders=5", "-c", "max_replication_slots=3", "-c", "wal_keep_size=64MB",
                    "-c", "max_slot_wal_keep_size=128MB", "-c", "shared_buffers=32MB"]
        if peer is None:
            command = [*common, IMAGE, *settings]
        else:
            # Only fixed aliases and fixed slot names are interpolated. Password is
            # copied from the mounted file; never placed in argv or conninfo.
            if peer not in ("primary", "standby") or slot not in ("initial_slot", "rebuilt_slot"):
                raise ValueError("Unexpected fixed peer")
            script = ("set -eu; install -d -o postgres -g postgres -m 0700 /var/lib/postgresql/18; "
                      "install -o postgres -g postgres -m 0600 /run/secrets/replication.pgpass /var/lib/postgresql/replication.pgpass; "
                      "gosu postgres pg_basebackup -D \"$PGDATA\" -R -X stream -C -S " + slot + " -c fast "
                      "--dbname='host=" + peer + " user=path_repl passfile=/var/lib/postgresql/replication.pgpass connect_timeout=3'; "
                      "exec docker-entrypoint.sh \"$@\"")
            command = [*common, "--entrypoint", "sh", IMAGE, "-c", script, "sh", *settings]
        identity = docker(*command).stdout.strip()
        containers.append(identity)
        # pg_isready alone can see the initialization server; require PID1 postgres.
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            ready = docker("exec", name, "sh", "-c", "test \"$(cat /proc/1/comm)\" = postgres && pg_isready -q -U postgres", check=False)
            if ready.returncode == 0:
                return name
            info = owned("container", identity)
            if not info["State"]["Running"]:
                raise AssertionError("node start: " + suffix)
            time.sleep(0.3)
        raise AssertionError("node readiness: " + suffix)

    error = None
    try:
        image = json.loads(docker("image", "inspect", IMAGE).stdout)[0]
        report["image_id"] = image["Id"]
        admin, replication_password = secrets.token_hex(32), secrets.token_hex(32)
        for name, content in (("admin_password", admin + "\n"),
                              ("replication.pgpass", "*:5432:replication:path_repl:" + replication_password + "\n"),
                              ("hba.conf", "local all all trust\nhost all all all scram-sha-256\nhost replication path_repl all scram-sha-256\n")):
            fd = os.open(temporary / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
            with os.fdopen(fd, "w") as target:
                os.fchmod(target.fileno(), 0o444)
                target.write(content)
        docker("network", "create", "--internal", "--label", LABEL + "=" + project, project)
        networks.append(project)
        pause("1. Новая основная база и начальная задача")
        primary = run_node("primary", volume("primary-data"))
        report["postgres_version"] = sql(primary, "SELECT version();")
        sql(primary, "CREATE ROLE path_repl LOGIN REPLICATION PASSWORD '" + replication_password + "';\n"
                     "CREATE TABLE recovery_tasks(id integer PRIMARY KEY,title text NOT NULL);\n"
                     "INSERT INTO recovery_tasks VALUES(1,'Before replication');")
        check("primary stores initial task", sql(primary, "SELECT count(*) FROM recovery_tasks;") == "1")
        standby = run_node("standby", volume("standby-data"), peer="primary", slot="initial_slot")
        wait_for(standby, "SELECT pg_is_in_recovery();", "t")
        wait_for(standby, "SELECT count(*) FROM recovery_tasks;", "1")
        readonly = sql(standby, "INSERT INTO recovery_tasks VALUES(99,'must not write');", check=False)
        check("standby is a real read-only recovery server", readonly.returncode != 0)

        pause("2. Намеренно останавливаем применение WAL, но не его получение")
        sql(standby, "SELECT pg_wal_replay_pause();")
        wait_for(standby, "SELECT pg_get_wal_replay_pause_state();", "paused")
        sql(primary, "INSERT INTO recovery_tasks VALUES(2,'Committed while replay paused');")
        target_lsn = sql(primary, "SELECT pg_current_wal_flush_lsn();")
        if not re.fullmatch(r"[0-9A-F]+/[0-9A-F]+", target_lsn):
            raise ValueError("Unexpected LSN")
        wait_for(standby, "SELECT pg_last_wal_receive_lsn()>='" + target_lsn + "'::pg_lsn;", "t")
        received, replayed = sql(standby, "SELECT pg_last_wal_receive_lsn(),pg_last_wal_replay_lsn();").split("|")
        check("received and flushed WAL does not imply visible row", sql(primary, "SELECT count(*) FROM recovery_tasks;") == "2"
              and sql(standby, "SELECT count(*) FROM recovery_tasks;") == "1", primary_rows=2, standby_rows=1,
              target_lsn=target_lsn, receive_lsn=received, replay_lsn=replayed)
        sql(standby, "SELECT pg_wal_replay_resume();")
        wait_for(standby, "SELECT count(*) FROM recovery_tasks;", "2")
        check("replay catches up after resume", sql(standby, "SELECT pg_last_wal_replay_lsn()>='" + target_lsn + "'::pg_lsn;") == "t")

        pause("3. Останавливаем и отключаем старую primary, затем вручную повышаем standby")
        primary_id = owned("container", primary)["Id"]
        docker("stop", "--time", "8", primary_id)
        check("old primary process stopped before promotion", not owned("container", primary_id)["State"]["Running"])
        docker("network", "disconnect", project, primary_id)
        check("old primary detached from the only lab network", not owned("container", primary_id)["NetworkSettings"]["Networks"])
        check("manual promotion completed", sql(standby, "SELECT pg_promote(true,15);") == "t")
        sql(standby, "INSERT INTO recovery_tasks VALUES(3,'Written on promoted server');")
        check("promoted node accepts new writes", sql(standby, "SELECT pg_is_in_recovery();") == "f"
              and sql(standby, "SELECT count(*) FROM recovery_tasks;") == "3")

        pause("4. Старая база вернулась только в сетевой изоляции: она не стала репликой сама")
        docker("start", primary_id)
        wait_for(primary, "SELECT 1;", "1")
        check("old node still considers itself primary but cannot serve lab clients", sql(primary, "SELECT pg_is_in_recovery();") == "f"
              and not owned("container", primary_id)["NetworkSettings"]["Networks"]
              and not owned("container", primary_id)["HostConfig"].get("PortBindings"), old_rows=int(sql(primary, "SELECT count(*) FROM recovery_tasks;")),
              current_rows=int(sql(standby, "SELECT count(*) FROM recovery_tasks;")))
        docker("stop", "--time", "8", primary_id)

        pause("5. Не запускаем старые файлы как replica: разворачиваем свежий physical base backup")
        rebuilt = run_node("rebuilt", volume("rebuilt-data"), peer="standby", slot="rebuilt_slot")
        wait_for(rebuilt, "SELECT count(*) FROM recovery_tasks;", "3")
        check("fresh base backup follows promoted primary", sql(rebuilt, "SELECT pg_is_in_recovery();") == "t"
              and sql(rebuilt, "SELECT title FROM recovery_tasks WHERE id=3;") == "Written on promoted server")
        sql(standby, "INSERT INTO recovery_tasks VALUES(4,'After rebuild');")
        wait_for(rebuilt, "SELECT count(*) FROM recovery_tasks;", "4")
        check("rebuilt standby streams subsequent writes", sql(rebuilt, "SELECT string_agg(id::text,',' ORDER BY id) FROM recovery_tasks;") == "1,2,3,4")
        report["result"] = "pass"
    except BaseException as failure:
        error = failure
        report["result"] = "fail"
        report["failure_class"] = type(failure).__name__
        if isinstance(failure, AssertionError):
            report["failed_check"] = str(failure)
        print("Stopped: " + type(failure).__name__ + "; cleaning up only this experiment", file=sys.stderr)
    finally:
        failures = []
        for identity in reversed(containers):
            try:
                owned("container", identity)
                docker("rm", "--force", identity)
            except Exception:
                failures.append("container")
        for identity in reversed(volumes):
            try:
                owned("volume", identity)
                docker("volume", "rm", identity)
            except Exception:
                failures.append("volume")
        for identity in reversed(networks):
            try:
                owned("network", identity)
                docker("network", "rm", identity)
            except Exception:
                failures.append("network")
        report["cleanup_succeeded"] = not failures
        report["cleanup_failures"] = failures
        report["retained_private_directory"] = str(temporary)
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
        print("Only this experiment's disposable database volumes were removed; report retained", flush=True)
    return 0 if error is None and report["cleanup_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
