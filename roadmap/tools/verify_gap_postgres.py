#!/usr/bin/env python3
"""Opt-in PG18 acceptance in a NEW disposable, network-isolated Docker container.

No host packages, existing databases, published ports, bind mounts, or global
settings. Run explicitly with --run. The report goes to stdout only.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
OWNER_LABEL = "org.cpp-course.gap-postgres-owner"


def command(args, *, stdin=None, timeout=45, check=True):
    result = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[-3000:]}")
    return result


def load(relative):
    return (EXAMPLES / relative).read_text()


def cases(source):
    parts = re.split(r"^-- case: ([a-z_]+)\s*$", source, flags=re.M)
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]


def json_stream(output):
    decoder = json.JSONDecoder()
    result = []
    rest = output.strip()
    while rest:
        value, end = decoder.raw_decode(rest)
        result.append(value)
        rest = rest[end:].lstrip()
    return result


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Create only a new owned disposable container")
    parser.add_argument("--image", default="postgres:18-bookworm", help="An already cached official PG18 image")
    args = parser.parse_args()
    if not args.run:
        parser.error("No action taken: pass --run for the isolated acceptance experiment")
    if args.image not in ("postgres:18", "postgres:18-bookworm"):
        parser.error("Only the named cached official PostgreSQL 18 images are accepted")
    if any(os.environ.get(key) for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")):
        raise RuntimeError("Docker context overrides are not accepted")
    endpoint = command(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]).stdout.strip()
    if endpoint != "unix:///var/run/docker.sock":
        raise RuntimeError("Only the local Docker Unix socket is accepted")
    image_id = command(["docker", "image", "inspect", "--format", "{{.Id}}", args.image]).stdout.strip()
    owner = uuid.uuid4().hex
    name = "course-gap-db-" + owner
    cid = None
    report = {
        "scope": "Fresh PG18 only; TEMP data; one session per SQL case; no HTTP/load claim",
        "image": args.image, "image_id": image_id,
        "limits": {"cpus": 1, "memory": "768m", "pids": 128, "pgdata_tmpfs": "256m", "network": "none", "published_ports": []},
        "checks": {}, "sql_sha256": {}, "cleanup_succeeded": False,
    }
    for directory in (EXAMPLES / "sql-design", EXAMPLES / "query-execution"):
        for path in sorted(directory.glob("*.sql")):
            report["sql_sha256"][str(path.relative_to(EXAMPLES))] = hashlib.sha256(path.read_bytes()).hexdigest()

    def sql(source, *, check=True):
        return command(["docker", "exec", "-i", cid, "psql", "-X", "-qAt",
                        "--set=ON_ERROR_STOP=1", "--set=VERBOSITY=sqlstate",
                        "--dbname=course_gaps"], stdin=source, timeout=60, check=check)

    def plan(source):
        parsed = json_stream(sql(source).stdout)
        assert len(parsed) == 1, parsed
        return parsed[0][0]["Plan"]

    try:
        result = command([
            "docker", "run", "--detach", "--pull=never", "--name", name,
            "--label", OWNER_LABEL + "=" + owner, "--network=none",
            "--memory=768m", "--cpus=1", "--pids-limit=128", "--cap-drop=ALL",
            "--read-only", "--user=postgres",
            "--tmpfs", "/var/lib/postgresql:rw,nosuid,nodev,noexec,size=256m,mode=1777",
            "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,noexec,size=16m,mode=1777",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777",
            "--env", "PGDATA=/var/lib/postgresql/gapdata",
            "--env", "POSTGRES_DB=course_gaps",
            "--env", "POSTGRES_HOST_AUTH_METHOD=trust", args.image,
            "postgres", "-c", "shared_buffers=32MB", "-c", "max_connections=10",
            "-c", "max_parallel_workers_per_gather=0",
        ], timeout=45)
        cid = result.stdout.strip()
        assert re.fullmatch(r"[a-f0-9]{64}", cid), "Unexpected container identifier"
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            # The entrypoint briefly starts a bootstrap server. Wait until PID 1
            # is the final postgres process, not the initializing shell.
            process = command(["docker", "exec", cid, "cat", "/proc/1/comm"], timeout=5, check=False)
            probe = command(["docker", "exec", cid, "pg_isready", "-U", "postgres", "-d", "course_gaps"], timeout=5, check=False)
            if process.stdout.strip() == "postgres" and probe.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Owned PostgreSQL did not become ready")
        version = sql("SELECT current_setting('server_version_num'),version();").stdout.strip()
        assert 180000 <= int(version.split("|", 1)[0]) < 190000, version
        report["postgresql"] = version
        report["role_scope"] = "Fresh fixture owner postgres; NOT an RLS or least-privilege test"

        model = load("sql-design/model.sql")
        observed = sql(model + "\n" + load("sql-design/observe.sql")).stdout.strip().splitlines()
        assert observed == ["1|100|7|10|Review API", "1|101|7||Unassigned", "2|100|7|20|Review website", "1|10", "1|20", "2|20"], observed
        report["checks"]["model_rows"] = observed
        invalid = {
            "duplicate_membership": ("INSERT INTO gd_member (org_id,person_id) VALUES (1,10);", "23505"),
            "cross_org_project": ("INSERT INTO gd_project VALUES (2,8,'Only South'); INSERT INTO gd_task VALUES (1,103,8,NULL,'Bad');", "23503"),
            "wrong_project_assignee": ("INSERT INTO gd_task VALUES (1,103,7,20,'Bad');", "23503"),
            "unknown_project_even_unassigned": ("INSERT INTO gd_task VALUES (1,103,999,NULL,'Bad');", "23503"),
            "delete_referenced_project": ("DELETE FROM gd_project WHERE org_id=1 AND project_id=7;", "23001"),
        }
        for key, (query, state) in invalid.items():
            failed = sql(model + "\n" + query, check=False)
            assert failed.returncode and state in failed.stderr, (key, failed.returncode, failed.stderr)
            report["checks"][key] = "rejected SQLSTATE " + state
        # A person may exist and belong to the organization, yet lack project membership.
        inactive = sql(model + "\nUPDATE gd_member SET active=false WHERE org_id=1 AND person_id=10;\n"
                       "INSERT INTO gd_task VALUES (1,104,7,10,'FK permits inactive');\n"
                       "SELECT count(*) FROM gd_task WHERE org_id=1 AND task_id=104;").stdout.strip()
        assert inactive == "1", inactive
        report["checks"]["fk_does_not_check_active"] = inactive
        history = sql(model + "\n" + load("sql-design/history.sql")).stdout.strip().splitlines()
        assert history == ["Anna New|Anna|f", "f", "0"], history
        report["checks"]["history_and_guarded_assignment"] = history

        setup = load("query-execution/joins-setup.sql")
        answer = sql(setup + "\n" + load("query-execution/join-query.sql")).stdout.strip().splitlines()
        assert answer == ["10|Anna", "11|Anna", "12|Bo"], answer
        report["checks"]["join_rows"] = answer
        expected_join = {"nested_loop": "Nested Loop", "hash_join": "Hash Join", "merge_join": "Merge Join"}
        for key, body in cases(load("query-execution/joins-plans.sql")):
            observed_plan = plan(setup + "\n" + body)
            types = [n["Node Type"] for n in nodes(observed_plan)]
            assert observed_plan["Actual Rows"] == 3, observed_plan
            assert expected_join[key] in types, types
            report["checks"][key] = {"actual_rows": 3, "nodes": [{k: n[k] for k in ("Node Type", "Actual Rows", "Actual Loops", "Join Type") if k in n} for n in nodes(observed_plan)]}

        memory_setup = load("query-execution/memory-setup.sql")
        statistics = json_stream(sql(memory_setup + "\n" + load("query-execution/statistics.sql")).stdout)
        assert len(statistics) == 3, len(statistics)
        stat_rows = []
        for key, result, expected in zip(("uniform", "skew_before_analyze", "skew_after_analyze"), statistics, (100,90010,90010)):
            p = result[0]["Plan"]
            assert p["Actual Rows"] == expected, p
            stat_rows.append({"case": key, "node": p["Node Type"], "estimated_rows": p["Plan Rows"], "actual_rows": p["Actual Rows"]})
        report["checks"]["statistics"] = stat_rows
        for key, body in cases(load("query-execution/memory-plans.sql")):
            p = plan(memory_setup + "\n" + body)
            assert p["Actual Rows"] == 100000, p
            interesting = [n for n in nodes(p) if n["Node Type"] in ("Sort", "Aggregate")]
            assert interesting, p
            fields = ("Node Type", "Strategy", "Actual Rows", "Sort Method", "Sort Space Used", "Sort Space Type", "HashAgg Batches", "Peak Memory Usage", "Disk Usage", "Temp Read Blocks", "Temp Written Blocks")
            report["checks"][key] = [{k:n[k] for k in fields if k in n} for n in interesting]
        # Also execute the public psql entry points, including their relative \ir
        # paths, in the same new container. No host directory is mounted.
        for directory in ("sql-design", "query-execution"):
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as tar:
                for file in sorted((EXAMPLES / directory).iterdir()):
                    if not file.is_file() or file.is_symlink() or file.suffix not in (".sql", ".md"):
                        raise RuntimeError("Unexpected fixture path; refusing archive")
                    payload = file.read_bytes()
                    member = tarfile.TarInfo(directory + "/" + file.name)
                    member.size = len(payload)
                    member.mode = 0o644
                    tar.addfile(member, io.BytesIO(payload))
            # Docker cp rejects a read-only rootfs even for this tmpfs. Extract
            # only our generated relative fixture names inside the container.
            copied = subprocess.run(["docker", "exec", "-i", cid, "tar", "-x", "-C", "/tmp"],
                                    input=archive.getvalue(), capture_output=True, timeout=15)
            if copied.returncode:
                raise RuntimeError("Fixture extraction failed: " + copied.stderr.decode(errors="replace")[-1000:])
            public = command(["docker", "exec", cid, "psql", "-X", "-qAt",
                              "--set=ON_ERROR_STOP=1", "--dbname=course_gaps",
                              "--file=/tmp/" + directory + "/run.sql"], timeout=90)
            report["checks"]["public_entrypoint_" + directory] = {"exit_code": public.returncode, "relative_includes": "passed"}
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    finally:
        # Resolve only our exact unique name, then verify the random ownership label.
        target = cid or name
        inspect = command(["docker", "inspect", "--format", "{{json .}}", target], timeout=10, check=False)
        if inspect.returncode == 0:
            owned = json.loads(inspect.stdout)
            if owned.get("Config", {}).get("Labels", {}).get(OWNER_LABEL) == owner:
                removed = command(["docker", "rm", "--force", "--volumes", owned["Id"]], timeout=20, check=False)
                report["cleanup_succeeded"] = removed.returncode == 0
            else:
                report["cleanup_error"] = "Ownership label mismatch; no deletion attempted"
        elif cid is None:
            report["cleanup_succeeded"] = True
        else:
            report["cleanup_error"] = "Could not inspect the exact owned container"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "passed" and report["cleanup_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
