#!/usr/bin/env python3
"""Private, opt-in architecture checks on an OWN disposable PostgreSQL18 project.

Default runs deterministic cache models only; --run-docker explicitly authorizes
creating an isolated Compose project, compiling its app and mutating its DBs.
No main course project, host settings, firewall, public ports or unrelated Docker
resources are used. Docker access is fixed to the local Unix socket. SQL code is
read from station9.json rather than maintained as a second teaching listing.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

import verify_service_workshop as http

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/service-workshop'
SQL_SOURCE = ROOT / 'content/station9.json'
COPY_FILES = ('CMakeLists.txt', 'app.cpp', 'storage.hpp', 'storage.cpp', 'tests.cpp',
              'schema.sql', 'Dockerfile', 'compose.yaml', 'init-db.sh', 'lab.py', '.dockerignore')
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def cache_models():
    """Logical interleavings only: no Redis process or network is claimed."""
    database, cache = 1, None
    reader_loaded = database
    database = 2                       # writer COMMIT
    cache = None                       # writer invalidation
    cache = reader_loaded              # delayed reader fills obsolete V1
    require(cache == 1 and database == 2, 'naive stale resurrection was not reproduced')

    database, generation, cache = 1, 0, None
    reader_generation, reader_loaded = generation, database
    database = 2                       # writer COMMIT
    generation += 1                    # atomic cache-side invalidation/fence
    cache = None
    if reader_generation == generation:
        cache = reader_loaded
    require(cache is None, 'generation fence accepted stale reader')
    cache = database                   # retried reader sees current committed V2
    require(cache == 2, 'fenced retry failed')
    return [
        'deterministic model: delayed reader resurrects V1 after V2 COMMIT + invalidation',
        'deterministic model: persistent generation fence rejects stale installation',
    ]


def sql_listings():
    data = json.loads(SQL_SOURCE.read_text(encoding='utf-8'))
    result = {}
    for section in data['theory']:
        if section['id'] in ('outbox-transaction', 'outbox-delivery'):
            code = [block['code'] for block in section['blocks'] if block.get('type') == 'code']
            require(len(code) == 2, 'expected exactly schema + transaction in each outbox section')
            result[section['id']] = code
    require(len(result) == 2, 'stable outbox sections missing')
    for schema, transaction in result.values():
        require('CREATE TABLE' in schema and transaction.count('COMMIT;') == 1,
                'unexpected outbox listing structure')
    return result


class IsolatedProject:
    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix='course-architecture-pg18-'))
        self.suffix = secrets.token_hex(5)
        self.name = 'course-arch-verify-' + self.suffix
        self.database = 'course_arch_verify_' + self.suffix
        self.port = http.unused_loopback_port()
        self.environment = {key: value for key, value in os.environ.items()
                            if key not in ('APP_TOKEN', 'POSTGRES_PASSWORD', 'APP_DB_PASSWORD',
                                           'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'DOCKER_CONTEXT', 'DOCKER_HOST')
                            and not key.startswith('PG')}
        self.compose = DOCKER + ['compose', '--project-directory', str(self.directory),
                                  '-p', self.name, '-f', str(self.directory / 'compose.yaml'),
                                  '-f', str(self.directory / 'compose.test.json')]
        self.values = {}
        self.created = False
        self.checks = []
        self.timings = {}

    def command(self, arguments, *, sql_input=None, timeout=30, allow_failure=False):
        result = subprocess.run(arguments, input=sql_input, capture_output=True, text=True,
                                env=self.environment, timeout=timeout)
        if result.returncode and not allow_failure:
            # Do not echo arbitrary output: subprocess errors could contain secrets.
            raise RuntimeError('isolated subprocess failed; diagnostic output withheld')
        return result

    def output(self, arguments, **options):
        return self.command(arguments, **options).stdout.strip()

    def db_arguments(self, database=None):
        return self.compose + ['exec', '-T', 'db', 'psql', '-X', '-qAt',
                               '-v', 'ON_ERROR_STOP=1', '-U', 'postgres',
                               '-d', database or self.database]

    def sql(self, source, database=None):
        return self.output(self.db_arguments(database), sql_input=source, timeout=8)

    def ownership(self):
        """Inspect only exact project labels; refuse unexpected targets."""
        ids = self.output(DOCKER + ['ps', '-aq', '--filter',
                                    'label=com.docker.compose.project=' + self.name]).split()
        for identifier in ids:
            record = json.loads(self.output(DOCKER + ['inspect', identifier]))[0]
            require(record['Config']['Labels']['com.docker.compose.project'] == self.name,
                    'container project label mismatch')
            require(record['Name'].lstrip('/') in (self.name + '-app-1', self.name + '-db-1'),
                    'unexpected container in owned project')
        volumes = self.output(DOCKER + ['volume', 'ls', '-q', '--filter',
                                        'label=com.docker.compose.project=' + self.name]).split()
        require(all(value == self.name + '_pgdata' for value in volumes),
                'unexpected volume in owned project')
        return ids, volumes

    def setup(self):
        ids, volumes = self.ownership()
        require(not ids and not volumes, 'random test project already exists; refusing reuse')
        for name in COPY_FILES:
            shutil.copy2(SOURCE / name, self.directory / name)
        compose_path = self.directory / 'compose.yaml'
        text = compose_path.read_text()
        require(text.count('127.0.0.1:8080:8080') == 1, 'expected loopback publication missing')
        compose_path.write_text(text.replace('127.0.0.1:8080:8080',
                                             f'127.0.0.1:{self.port}:8080'))
        limits = {'services': {'app': {'cpus': '1.0', 'mem_limit': '256m'},
                               'db': {'cpus': '1.0', 'mem_limit': '512m', 'pids_limit': 128}}}
        (self.directory / 'compose.test.json').write_text(json.dumps(limits))
        self.command(['python3', str(self.directory / 'lab.py'), 'init'])
        spec = importlib.util.spec_from_file_location('private_architecture_lab', self.directory / 'lab.py')
        lab = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lab)
        self.values = lab.read_env(self.directory)
        self.command(self.compose + ['config', '--quiet'])
        self.created = True  # Partial creation on a failed up still needs scoped cleanup.
        print('BUILD: ' + self.name + '; loopback port ' + str(self.port), flush=True)
        result = self.command(self.compose + ['up', '--build', '-d', '--wait',
                                               '--wait-timeout', '180'], timeout=300, allow_failure=True)
        build_log = result.stdout + result.stderr
        require(all(value not in build_log for value in self.values.values()), 'secret in build output')
        (self.directory / 'build.log').write_text(build_log)
        require(result.returncode == 0, 'isolated build/up failed; inspect private build.log')
        self.ownership()
        self.command(self.compose + ['exec', '-T', 'db', 'createdb', '-U', 'postgres',
                                      '--template=template0', self.database])
        version = int(self.sql('SHOW server_version_num;'))
        require(180000 <= version < 190000, 'this test requires real PostgreSQL18')
        self.server_version_num = version
        self.client = http.Client(f'http://127.0.0.1:{self.port}', self.values['APP_TOKEN'])
        self.checks.append('fresh PostgreSQL18 + bounded own Compose project + newly built app healthy')

    def sql_contracts(self, listings):
        sender_schema, sender = listings['outbox-transaction']
        self.sql(sender_schema)
        self.sql(sender.replace('COMMIT;', 'ROLLBACK;', 1))
        require(self.sql('SELECT done,version FROM outbox_demo_tasks;') == 'f|1',
                'sender rollback changed business row')
        require(self.sql('SELECT count(*) FROM outbox_demo_events;') == '0', 'sender rollback left event')
        self.sql(sender)  # Deliberately ignore committed response, then reconcile/retry.
        require(self.sql('SELECT done,version FROM outbox_demo_tasks;') == 't|2', 'sender commit missing')
        require(self.sql('SELECT task_id,task_version,sent_at IS NULL FROM outbox_demo_events;') == '10|2|t',
                'sender event does not match committed business version')
        require(self.sql("SELECT payload=jsonb_build_object('task_id',10,'version',2,'done',true) "
                         "FROM outbox_demo_events;") == 't', 'sender JSON payload differs from committed row')
        self.sql(sender)
        require(self.sql('SELECT count(*) FROM outbox_demo_events;') == '1', 'sender retry duplicated event')
        self.checks.append('actual sender listing: task+event rollback together; commit and expected-version retry yield one event')
        self.checks.append('unknown-result recovery MODEL: ignore successful SQL reply, read primary and retry same expected version; no network fault injected')

        receiver_schema, receiver = listings['outbox-delivery']
        self.sql(receiver_schema)
        self.sql(receiver.replace('COMMIT;', 'ROLLBACK;', 1))
        require(self.sql('SELECT completed FROM inbox_demo_totals;') == '0', 'receiver rollback left effect')
        require(self.sql('SELECT count(*) FROM inbox_demo_receipts;') == '0', 'receiver rollback left receipt')
        for attempt in range(2):
            require(self.sql(receiver) == '1', 'receiver first/duplicate result differs')
        require(self.sql('SELECT count(*) FROM inbox_demo_receipts;') == '1', 'duplicate receipt appeared')
        self.sql('TRUNCATE inbox_demo_receipts; UPDATE inbox_demo_totals SET completed=0 WHERE id=1;')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.sql(receiver), range(2)))
        require(results == ['1', '1'], 'concurrent duplicate receiver results differ')
        require(self.sql('SELECT completed FROM inbox_demo_totals;') == '1', 'concurrent duplicate doubled effect')
        require(self.sql('SELECT count(*) FROM inbox_demo_receipts;') == '1', 'concurrent dedupe failed')
        self.checks.append('actual receiver listing: rollback undoes receipt+effect; sequential and concurrent duplicate event42 produce one effect')

    def row_lock(self):
        task = http.create_task(self.client, 'owned-row-lock-boundary')
        application = 'course_arch_row_lock_' + self.suffix
        holder = subprocess.Popen(self.db_arguments('course_tasks'), stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=self.environment)
        try:
            holder.stdin.write("SET application_name='" + application + "';\nBEGIN;\n"
                "SET LOCAL idle_in_transaction_session_timeout='10s';\n"
                "SELECT id FROM public.tasks WHERE id=" + str(task['id']) + " FOR UPDATE;\n")
            holder.stdin.flush()
            deadline = time.monotonic() + 3
            while self.sql("SELECT count(*) FROM pg_stat_activity WHERE application_name='" +
                          application + "' AND state='idle in transaction';", 'course_tasks') != '1':
                require(holder.poll() is None and time.monotonic() < deadline, 'row lock was not acquired')
                time.sleep(0.05)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                started = time.monotonic()
                pending = pool.submit(self.client.request, 'PUT', '/tasks/' + str(task['id']),
                                      http.payload('must-time-out'), headers={'If-Match': '"v1"'})
                deadline = time.monotonic() + 1.5
                while self.sql("SELECT count(*) FROM pg_stat_activity WHERE datname='course_tasks' "
                              "AND wait_event_type='Lock' AND query LIKE 'SELECT version FROM public.tasks%';",
                              'course_tasks') != '1':
                    require(time.monotonic() < deadline, 'PUT lock wait was not observed')
                    time.sleep(0.05)
                probe = http.Client(self.client.base_url, self.values['APP_TOKEN'])
                for path in ('/health/live', '/health/ready'):
                    http.expect(probe.request('GET', path, authorization=None), 200, 'parallel probe ' + path)
                observed = http.task_response(probe.request('GET', '/tasks/' + str(task['id'])), 200,
                                              'parallel plain SELECT')
                require(observed == task, 'uncommitted blocked update became visible')
                response = pending.result(timeout=8)
                elapsed = time.monotonic() - started
                http.expect(response, 503, 'statement_timeout while waiting for row lock')
                require(response.json() == {'error': 'service_unavailable'}, 'DB error detail leaked')
                require(2.5 <= elapsed <= 7.5, 'row-lock timeout outside bounded expected window')
                self.timings['row_lock_put_seconds'] = round(elapsed, 3)
            holder.stdin.write('ROLLBACK;\n')
            holder.stdin.close()
            holder.stdin = None
            holder.communicate(timeout=3)
            require(holder.returncode == 0, 'owned lock session did not roll back cleanly')
            require(http.task_response(self.client.request('GET', '/tasks/' + str(task['id'])), 200,
                                       'after lock rollback') == task, 'timed-out PUT changed task')
            updated = http.task_response(self.client.request('PUT', '/tasks/' + str(task['id']),
                http.payload('retry-after-lock-release', True), headers={'If-Match': '"v1"'}),
                200, 'retry PUT', validator=False)
            require(updated['version'] == 2, 'successful retry did not increment once')
            require(http.task_response(self.client.request('GET', '/tasks/' + str(task['id'])),
                200, 'GET actual validator after retry') == updated, 'GET after retry differs')
            http.delete_task(self.client, updated)
        finally:
            if holder.poll() is None:
                try:
                    holder.communicate('ROLLBACK;\n' if holder.stdin else None, timeout=3)
                except (subprocess.TimeoutExpired, ValueError):
                    holder.kill()  # Our exact local docker-exec child only.
                    holder.communicate(timeout=3)
        self.checks.append('owned row lock: ~3s PUT503; simultaneous live/ready/GET200; rollback leaves v1; retryPUT200 no validator; GET returns v2 ETag')

    def finish_logs(self):
        logs = self.output(self.compose + ['logs', '--no-color', 'app'])
        require(all(value not in logs for value in self.values.values()), 'credential appeared in app logs')
        require('must-time-out' not in logs and 'retry-after-lock-release' not in logs, 'task body appeared in logs')
        (self.directory / 'app-sanitized.log').write_text(logs)
        require(http.list_tasks(self.client) == [], 'owned app database was not left empty')

    def cleanup(self):
        if self.created:
            _, volumes = self.ownership()
            self.command(self.compose + ['down', '--timeout', '10'], timeout=45)
            for volume in volumes:
                self.command(DOCKER + ['volume', 'rm', volume])
            ids, volumes = self.ownership()
            require(not ids and not volumes, 'owned containers or volume remain')
            networks = self.output(DOCKER + ['network', 'ls', '-q', '--filter',
                                             'label=com.docker.compose.project=' + self.name])
            require(not networks, 'owned project network remains')
        # Generated credentials only, exact paths; keep harmless logs/scripts.
        for path in (self.directory / '.env', self.directory / '.secrets/client.curl'):
            if path.exists():
                path.unlink()
        private_directory = self.directory / '.secrets'
        if private_directory.exists():
            private_directory.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-docker', action='store_true', help='explicitly authorize OWN disposable Docker/SQL/HTTP tests')
    parser.add_argument('--check-capacity', action='store_true', help='also run 1000-task app capacity checks')
    parser.add_argument('--evidence', type=Path, help='new private JSON evidence file (never overwrite)')
    args = parser.parse_args(argv)
    checks = cache_models()
    for check in checks:
        print('PASS: ' + check, flush=True)
    if not args.run_docker:
        print('NOT RUN: real PostgreSQL/HTTP tests require explicit --run-docker')
        return 77
    if args.evidence and args.evidence.exists():
        parser.error('evidence file already exists; choose a new filename')
    project = IsolatedProject()
    success, error, cleaned = False, None, False
    try:
        listings = sql_listings()
        project.setup()
        project.sql_contracts(listings)
        project.checks += http.verify_http(project.client, capacity=args.check_capacity)
        project.row_lock()
        project.finish_logs()
        checks += project.checks
        success = True
    except Exception as exc:
        # Only explicitly safe messages; subprocess output/env values stay private.
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            project.cleanup()
            cleaned = True
        except Exception as exc:
            success = False
            error = 'scoped cleanup failed: ' + type(exc).__name__
    report = {
        'result': 'passed' if success else 'failed', 'checks': checks,
        'project': project.name, 'directory': str(project.directory),
        'server_version_num': getattr(project, 'server_version_num', None),
        'timings': project.timings, 'owned_resources_removed': cleaned,
        'source_sha256': {name: hashlib.sha256((project.directory / name).read_bytes()).hexdigest()
                          for name in ('app.cpp', 'storage.cpp', 'CMakeLists.txt')
                          if (project.directory / name).is_file()},
        'station9_sha256': hashlib.sha256(SQL_SOURCE.read_bytes()).hexdigest(),
        'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sql_code_sha256': {name: [hashlib.sha256(code.encode()).hexdigest() for code in values]
                           for name, values in (listings.items() if 'listings' in locals() else [])},
        'scope': ['real single-node PostgreSQL18 SQL and app checks',
                  'lost COMMIT response is reconciliation MODEL, not actual transport fault injection',
                  'cache interleavings are deterministic models, no real Redis or failover',
                  'no replication cluster, broker, VPS, DNS, TLS or host configuration changes'],
        'error': error,
    }
    report_path = args.evidence or project.directory / 'report.json'
    with report_path.open('x', encoding='utf-8') as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write('\n')
    for check in project.checks:
        print('PASS: ' + check, flush=True)
    print('Evidence: ' + str(report_path), flush=True)
    print('Cleanup: ' + ('exact owned resources removed' if cleaned else 'NEEDS ATTENTION'), flush=True)
    if not success:
        print('FAIL: ' + str(error), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
