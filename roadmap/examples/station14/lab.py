#!/usr/bin/env python3
"""Own local Compose lab only. No sudo, pruning, arbitrary URLs or auto-install."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent


def config():
    path = ROOT / '.env'
    if path.is_symlink() or not path.is_file():
        raise SystemExit('Run python3 lab.py init in this directory first.')
    entries = [line.split('=', 1) for line in path.read_text().splitlines()
               if line and not line.startswith('#')]
    if any(len(item) != 2 for item in entries):
        raise SystemExit('Invalid local .env format; regenerate it in a new lab directory.')
    values = dict(entries)
    if len(entries) != 3 or set(values) != {'COURSE_LAB_ID', 'COMPOSE_PROJECT_NAME', 'COURSE_GRAFANA_PASSWORD'}:
        raise SystemExit('Expected only the three generated keys; refusing duplicates or overrides.')
    run = values.get('COURSE_LAB_ID', '')
    if not re.fullmatch(r'[a-f0-9]{12}', run):
        raise SystemExit('Invalid local lab ID; do not use an unrelated .env.')
    if values.get('COMPOSE_PROJECT_NAME') != 'course-station14-' + run:
        raise SystemExit('Refusing an unrelated Compose project name.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{30,}', values.get('COURSE_GRAFANA_PASSWORD', '')):
        raise SystemExit('Expected the locally generated Grafana password.')
    return values


def docker(*args, endpoint=None, environment=None):
    client = ['docker'] + (['--host', endpoint] if endpoint else [])
    result = subprocess.run([*client, *args], cwd=ROOT, text=True,
                            capture_output=True, timeout=180, env=environment)
    if result.returncode:
        raise SystemExit('Docker command failed; do not add sudo or change daemon permissions.\n'
                         + result.stderr)
    return result.stdout


def local_engine():
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise SystemExit('Refusing Docker environment overrides; use a dedicated local lab VM.')
    contexts = json.loads(docker('context', 'inspect'))
    endpoint = contexts[0].get('Endpoints', {}).get('docker', {}).get('Host', '')
    if not endpoint.startswith('unix:///'):
        raise SystemExit('This helper only accepts a local Unix Docker socket, not SSH/TCP contexts.')
    return endpoint


def owned(values, endpoint=None):
    project = values['COMPOSE_PROJECT_NAME']
    names = docker('ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project, endpoint=endpoint).split()
    for item in names:
        info = json.loads(docker('inspect', item, endpoint=endpoint))[0]
        labels = info['Config'].get('Labels') or {}
        if labels.get('org.cpp-course.station') != '14' or labels.get('org.cpp-course.run') != values['COURSE_LAB_ID']:
            raise SystemExit('Ownership labels do not match. No changes performed.')
    for resource in ('volume', 'network'):
        names = docker(resource, 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project, endpoint=endpoint).split()
        for item in names:
            labels = json.loads(docker(resource, 'inspect', item, endpoint=endpoint))[0].get('Labels') or {}
            if labels.get('org.cpp-course.station') != '14' or labels.get('org.cpp-course.run') != values['COURSE_LAB_ID']:
                raise SystemExit('Resource ownership does not match. No changes performed.')


def compose_environment(values):
    # Compose gives shell interpolation precedence over --env-file. Pin these
    # exact validated values explicitly, including the password returned above.
    return {**os.environ, **values}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Unexpected redirect: only local lab endpoints are allowed')


def request(path, run):
    if not path.startswith('/') or '\r' in path or '\n' in path:
        raise ValueError('Invalid path')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open('http://127.0.0.1:18140' + path, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        if (response.headers.get('X-Course-Lab') != 'station14' or
                response.headers.get('X-Course-Lab-Run') != run):
            raise SystemExit('This port is not this local lab run. Refusing traffic.')
        return response.status, response.read(4096), response.headers.get('X-Course-Trace-Id', '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    for name in ('start', 'stop', 'status', 'logs', 'check', 'credentials'):
        sub.add_parser(name)
    fault = sub.add_parser('pause')
    fault.add_argument('service', choices=('worker', 'collector'))
    resume = sub.add_parser('resume')
    resume.add_argument('service', choices=('worker', 'collector'))
    purge = sub.add_parser('purge')
    purge.add_argument('--confirm-project', required=True)
    load = sub.add_parser('traffic')
    load.add_argument('--mode', choices=('normal', 'slow', 'error'), default='normal')
    load.add_argument('--count', type=int, default=40)
    load.add_argument('--rate', type=float, default=2)
    args = parser.parse_args()
    if args.command == 'init':
        path = ROOT / '.env'
        run = secrets.token_hex(6)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write('COMPOSE_PROJECT_NAME=course-station14-' + run + '\n'
                       'COURSE_LAB_ID=' + run + '\n'
                       'COURSE_GRAFANA_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
        print('Created private local .env; it is not a course download or Git file.')
        return
    values = config()
    if args.command == 'credentials':
        print('Local Grafana only: http://127.0.0.1:13014 ; user course')
        print(values['COURSE_GRAFANA_PASSWORD'])
        return
    if args.command == 'traffic':
        if not 1 <= args.count <= 300 or not 0.1 <= args.rate <= 5:
            raise SystemExit('Use 1..300 requests and 0.1..5 requests/second.')
        request('/healthz', values['COURSE_LAB_ID'])
        counts = Counter()
        for _ in range(args.count):
            started = time.monotonic()
            code, _, trace = request('/work?mode=' + args.mode, values['COURSE_LAB_ID'])
            counts[code] += 1
            print('status=', code, 'trace_id=', trace, flush=True)
            time.sleep(max(0, 1 / args.rate - (time.monotonic() - started)))
        print('Completed responses:', dict(counts))
        return
    if args.command == 'check':
        code, _, _ = request('/healthz', values['COURSE_LAB_ID'])
        print('API health HTTP', code, '(not proof of exporter success).')
        print('Grafana http://127.0.0.1:13014 ; Prometheus http://127.0.0.1:19014')
        print('Jaeger http://127.0.0.1:16614 ; allow two scrapes before rate queries.')
        return
    endpoint = local_engine()
    owned(values, endpoint)
    environment = compose_environment(values)
    prefix = ['compose', '--project-name', values['COMPOSE_PROJECT_NAME'],
              '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'compose.yaml')]
    actions = {
        'start': ['up', '--build', '-d'], 'stop': ['down'],
        'status': ['ps'], 'logs': ['logs', '--no-color', '--tail', '100'],
        'pause': ['stop', getattr(args, 'service', '')],
        'resume': ['up', '-d', getattr(args, 'service', '')]
    }
    if args.command == 'purge':
        if args.confirm_project != values['COMPOSE_PROJECT_NAME']:
            raise SystemExit('Confirmation must equal the exact project in local .env.')
        actions['purge'] = ['down', '--volumes']
    if args.command == 'start':
        # Let the reader see the first dependency build; never start a daemon.
        subprocess.run(['docker', '--host', endpoint, *(prefix + actions[args.command])], cwd=ROOT,
                       check=True, timeout=1800, env=environment)
    else:
        print(docker(*(prefix + actions[args.command]), endpoint=endpoint, environment=environment))


if __name__ == '__main__':
    main()
