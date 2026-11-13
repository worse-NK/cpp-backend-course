#!/usr/bin/env python3
"""Isolated Redis lab helper: guarded Docker actions, no global cleanup.

init creates new local credentials/configuration; check connects only to
127.0.0.1 and touches exact keys below the generated run prefix.
The small RESP2 implementation is a bounded teaching test tool, not a
production Redis client and not an implementation of Sentinel/Cluster.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
LABEL_STATION = 'io.cpp-course.station'
LABEL_RUN = 'io.cpp-course.run-id'
ACL_COMMANDS = ('+ping +echo +get +set +del +incr +pttl +ttl +expire +pexpire '
                '+hset +hget +hgetall +lpush +lrange +sadd +smembers +zadd +zrange '
                '+multi +exec +discard +watch +unwatch +eval +evalsha +script|load '
                '+memory|usage +info +slowlog|get +latency|latest +dbsize +client|setname')


class RedisError(Exception):
    pass


def wire(args):
    encoded = [a if isinstance(a, bytes) else str(a).encode('utf-8') for a in args]
    return (b'*' + str(len(encoded)).encode() + b'\r\n' + b''.join(
        b'$' + str(len(a)).encode() + b'\r\n' + a + b'\r\n' for a in encoded))


def read_reply(stream, depth=0, budget=None):
    if budget is None:
        budget = [2 * 1024 * 1024, 1024]  # Whole reply: bytes and nodes, not per branch.
    budget[1] -= 1
    if budget[1] < 0:
        raise ValueError('RESP total node limit')
    if depth > 8:
        raise ValueError('RESP nesting limit')
    line = stream.readline(4097)
    budget[0] -= len(line)
    if budget[0] < 0:
        raise ValueError('RESP total byte limit')
    if not line or len(line) > 4096 or not line.endswith(b'\r\n'):
        raise ValueError('incomplete or excessive RESP line')
    kind, value = line[:1], line[1:-2]
    if kind == b'+':
        return value
    if kind == b'-':
        return RedisError(value.decode('utf-8', errors='replace'))
    if kind == b':':
        return int(value)
    if kind in (b'$', b'*'):
        length = int(value)
        if length == -1:
            return None
        limit = 1024 * 1024 if kind == b'$' else 256
        if length < 0 or length > limit:
            raise ValueError('RESP length limit')
        if kind == b'*':
            return [read_reply(stream, depth+1, budget) for _ in range(length)]
        if length + 2 > budget[0]:
            raise ValueError('RESP total byte limit')
        budget[0] -= length + 2
        data = stream.read(length+2)
        if len(data) != length+2 or data[-2:] != b'\r\n':
            raise ValueError('incomplete RESP bulk')
        return data[:-2]
    raise ValueError('unsupported RESP2 type')


def environment():
    path = ROOT / '.env'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Run python3 lab.py init in this lab directory first')
    values = {}
    if path.stat().st_size > 2048:
        raise ValueError('unexpected .env size')
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        if key in values:
            raise ValueError('duplicate .env variable')
        values[key] = value
    required = {'COURSE12_PROJECT', 'COURSE12_RUN_ID', 'COURSE12_PASSWORD', 'COURSE12_PORT'}
    if set(values) != required:
        raise ValueError('unexpected .env format; never source it as shell code')
    if not re.fullmatch(r'[0-9a-f]{16}', values['COURSE12_RUN_ID']):
        raise ValueError('invalid lab identifier')
    if values['COURSE12_PROJECT'] != 'course12-' + values['COURSE12_RUN_ID']:
        raise ValueError('project/identifier mismatch')
    if not re.fullmatch(r'[0-9a-f]{64}', values['COURSE12_PASSWORD']):
        raise ValueError('invalid generated credential')
    if (not re.fullmatch(r'[1-9][0-9]{3,4}', values['COURSE12_PORT']) or
            not 1024 <= int(values['COURSE12_PORT']) <= 65535):
        raise ValueError('invalid local port')
    owner = ROOT / 'runtime/owner.json'
    acl = ROOT / 'runtime/users.acl'
    if ((ROOT / 'runtime').is_symlink() or owner.is_symlink() or acl.is_symlink()
            or not owner.is_file() or not acl.is_file() or owner.stat().st_size > 4096
            or acl.stat().st_size > 8192):
        raise ValueError('missing or unsafe ownership files; use a new isolated lab directory')
    digest = hashlib.sha256(values['COURSE12_PASSWORD'].encode()).hexdigest()
    expected = {'version': 1, 'directory': str(ROOT), 'project': values['COURSE12_PROJECT'],
                'run_id': values['COURSE12_RUN_ID'], 'port': values['COURSE12_PORT'],
                'password_sha256': digest}
    if json.loads(owner.read_text()) != expected:
        raise ValueError('ownership file does not match this directory and .env')
    expected_acl = f'user default reset on #{digest} ~course12:{values["COURSE12_RUN_ID"]}:* {ACL_COMMANDS}\n'
    if acl.read_text() != expected_acl:
        raise ValueError('ACL does not match the generated lab identity')
    return values


def initialize(port):
    if not 1024 <= port <= 65535:
        raise ValueError('choose a port in 1024..65535')
    runtime, env_path = ROOT / 'runtime', ROOT / '.env'
    if ROOT.is_symlink() or runtime.is_symlink() or env_path.exists() or env_path.is_symlink():
        raise ValueError('Refusing to overwrite existing or symlinked lab state')
    if runtime.exists() and any(runtime.iterdir()):
        raise ValueError('runtime is not empty; use a new isolated lab directory')
    run_id, password = secrets.token_hex(8), secrets.token_hex(32)
    runtime.mkdir(exist_ok=True)
    digest = hashlib.sha256(password.encode()).hexdigest()
    acl = f'user default reset on #{digest} ~course12:{run_id}:* {ACL_COMMANDS}\n'
    (runtime / 'users.acl').write_text(acl)
    os.chmod(runtime / 'users.acl', 0o644)  # Hash only; Redis container UID can read it.
    raw = (f'COURSE12_PROJECT=course12-{run_id}\nCOURSE12_RUN_ID={run_id}\n'
           f'COURSE12_PASSWORD={password}\nCOURSE12_PORT={port}\n')
    owner = {'version': 1, 'directory': str(ROOT), 'project': 'course12-' + run_id,
             'run_id': run_id, 'port': str(port), 'password_sha256': digest}
    owner_fd = os.open(runtime / 'owner.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(owner_fd, 'w') as output:
        json.dump(owner, output, indent=2)
        output.write('\n')
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(raw)
    print(f'Created isolated project course12-{run_id}; loopback port {port}.')
    print('Credentials remain in .env; do not publish .env or runtime/.')
    print('Next: python3 lab.py compose config')
    print('Then: python3 lab.py compose up')


def child_environment(values):
    # --env-file alone does NOT override exported shell variables.
    result = {k: v for k, v in os.environ.items()
              if not k.startswith(('DOCKER_', 'COMPOSE_', 'COURSE12_'))}
    return {**result, **values}


def docker_output(prefix, args, env):
    result = subprocess.run([*prefix, *args], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        # Inspect can contain credentials; neither stdout nor the full argv is logged.
        raise ValueError('Docker preflight failed; check local daemon access and the lab README')
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError('excessive Docker inspection response')
    return result.stdout


def local_docker(values):
    env = child_environment(values)
    contexts = json.loads(docker_output(['docker'], ['context', 'inspect'], env))
    if not isinstance(contexts, list) or len(contexts) != 1:
        raise ValueError('expected one local Docker context')
    endpoint = contexts[0].get('Endpoints', {}).get('docker', {}).get('Host', '')
    if (not isinstance(endpoint, str) or not endpoint.startswith('unix:///')
            or any(c.isspace() for c in endpoint) or '?' in endpoint or '#' in endpoint):
        raise ValueError('this lab requires a local Unix-socket Docker context, not TCP/SSH')
    return ['docker', '--host', endpoint], env


def project_resources(values, prefix, env):
    """Read-only preflight, including name collisions without Compose labels."""
    project = values['COURSE12_PROJECT']
    expected = {LABEL_STATION: '12', LABEL_RUN: values['COURSE12_RUN_ID'],
                'com.docker.compose.project': project}
    containers = []
    for kind, target in (('container', None), ('volume', project + '_redis-data'),
                         ('network', project + '_default')):
        listing = ['ps', '-aq'] if kind == 'container' else [kind, 'ls', '--quiet']
        listing += ['--filter', 'label=com.docker.compose.project=' + project]
        names = docker_output(prefix, listing, env).split()
        if target:
            # A foreign resource with our exact generated name may have NO labels.
            all_names = docker_output(prefix, [kind, 'ls', '--format', '{{.Name}}'], env).split()
            if target in all_names:
                names.append(target)
        names = sorted(set(names))
        if len(names) > 64 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', n) for n in names):
            raise ValueError('unexpected Docker project resource inventory')
        if not names:
            continue
        objects = json.loads(docker_output(prefix, [kind, 'inspect', *names], env))
        if not isinstance(objects, list) or len(objects) != len(names):
            raise ValueError('incomplete Docker ownership inspection')
        for item in objects:
            labels = (item.get('Config', {}).get('Labels') if kind == 'container'
                      else item.get('Labels')) or {}
            if any(labels.get(k) != v for k, v in expected.items()):
                raise ValueError('project/name collision: refusing to touch resources without this lab identity')
            if kind == 'container':
                if labels.get('com.docker.compose.service') not in {'redis', 'client'}:
                    raise ValueError('unexpected service in this lab project')
                containers.append(item)
    return containers


def require_redis_container(values):
    prefix, env = local_docker(values)
    objects = project_resources(values, prefix, env)
    servers = [c for c in objects if c['Config']['Labels'].get('com.docker.compose.service') == 'redis']
    if len(servers) != 1:
        raise ValueError('expected exactly one owned Redis container; start it through lab.py compose up')
    server = servers[0]
    ports = server.get('NetworkSettings', {}).get('Ports', {}).get('6379/tcp')
    expected_ports = [{'HostIp': '127.0.0.1', 'HostPort': values['COURSE12_PORT']}]
    if (not server.get('State', {}).get('Running') or ports != expected_ports
            or server.get('Config', {}).get('Image') != 'redis:8.2.11-alpine'):
        raise ValueError('owned Redis is not running on the exact generated loopback port/image')
    if not any(m.get('Type') == 'volume' and m.get('Name') == values['COURSE12_PROJECT'] + '_redis-data'
               and m.get('Destination') == '/data' for m in server.get('Mounts', [])):
        raise ValueError('Redis does not use the expected owned data volume')


def compose_action(action):
    values = environment()
    actions = {'config': ['config', '--quiet'],
               'up': ['up', '--wait', '--wait-timeout', '45', 'redis'],
               'ps': ['ps'], 'restart': ['restart', 'redis'],
               'client': ['--profile', 'tools', 'run', '--build', '--rm', 'client'],
               'down': ['down']}
    if action not in actions:
        raise ValueError('unsupported lab Compose action')
    if action == 'config':
        prefix, env = ['docker'], child_environment(values)  # Client-side, no daemon.
    else:
        prefix, env = local_docker(values)
        project_resources(values, prefix, env)  # Never silently adopt a collision.
    command = [*prefix, 'compose', '--project-directory', str(ROOT),
               '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'compose.yaml'),
               '-p', values['COURSE12_PROJECT'], *actions[action]]
    budget = 600 if action == 'client' else 180
    return subprocess.run(command, cwd=ROOT, env=env, timeout=budget, check=False).returncode


class Client:
    def __init__(self, values):
        self.sock = socket.create_connection(('127.0.0.1', int(values['COURSE12_PORT'])), timeout=2)
        self.sock.settimeout(2)
        self.stream = self.sock.makefile('rb')
        try:
            self.call('AUTH', values['COURSE12_PASSWORD'])
        except Exception:
            self.close()
            raise

    def call(self, *args):
        self.sock.sendall(wire(args))
        reply = read_reply(self.stream)
        if isinstance(reply, RedisError):
            raise reply
        return reply

    def close(self):
        self.stream.close()
        self.sock.close()


def check():
    values = environment()
    require_redis_container(values)  # Read-only Docker evidence before any Redis write.
    prefix = 'course12:' + values['COURSE12_RUN_ID'] + ':'
    client = Client(values)
    peer = None
    keys = [prefix + name for name in ('probe', 'tx', 'other', 'watch', 'limit', 'lease')]
    def expect(label, got, expected):
        if got != expected:
            raise AssertionError(f'{label}: expected {expected!r}, got {got!r}')
        print('PASS:', label)
    try:
        expect('PING', client.call('PING'), b'PONG')
        server = client.call('INFO', 'server')
        if b'redis_version:8.2.11\r\n' not in server:
            raise ValueError('Expected the pinned Redis 8.2.11 lab server')
        for key in keys:
            client.call('DEL', key)
        probe, tx, other, watched, limit, lease = keys
        expect('missing is nil, not empty bytes', client.call('GET', probe), None)
        client.call('SET', probe, b'')
        expect('empty value exists', client.call('GET', probe), b'')
        client.call('SET', probe, b'A\x00B', 'PX', 5000)
        expect('binary payload', client.call('GET', probe), b'A\x00B')
        ttl = client.call('PTTL', probe)
        if not 0 < ttl <= 5000:
            raise AssertionError('Expected a positive, unrenewed 5-second TTL')
        client.call('PEXPIRE', probe, 0)
        expect('explicit expiry removes key', client.call('PTTL', probe), -2)
        client.call('SET', tx, 'abc')
        client.call('MULTI')
        client.call('INCR', tx)
        client.call('SET', other, 'done')
        results = client.call('EXEC')
        if len(results) != 2 or not isinstance(results[0], RedisError) or results[1] != b'OK':
            raise AssertionError('Expected a per-command EXEC error followed by success')
        expect('runtime error did not roll back the other command', client.call('GET', other), b'done')
        client.call('SET', watched, 1)
        client.call('WATCH', watched)
        peer = Client(values)
        peer.call('INCR', watched)
        client.call('MULTI')
        client.call('SET', watched, 100)
        expect('WATCH conflict aborts EXEC', client.call('EXEC'), None)
        expect('conflicting writer preserved', client.call('GET', watched), b'2')
        script = (ROOT / 'rate_limit.lua').read_text()
        for expected in (1, 1, 1, 0):
            reply = client.call('EVAL', script, 1, limit, 3, 30000)
            expect('fixed-window admission', reply[0], expected)
        client.call('SET', lease, 'new-owner', 'PX', 30000)
        release = (ROOT / 'release_lock.lua').read_text()
        expect('late owner cannot delete new lease', client.call('EVAL', release, 1, lease, 'old-owner'), 0)
        expect('current owner can release', client.call('EVAL', release, 1, lease, 'new-owner'), 1)
        client.call('SET', prefix + 'persist', values['COURSE12_RUN_ID'])
        print('Completed against this local lab instance. No DB flush or Docker cleanup was performed.')
    finally:
        # An I/O failure can leave the context unusable: do not blindly retry
        # commands. Remaining exact lab keys expire or stay in this lab volume.
        if peer:
            peer.close()
        client.close()


def inspect():
    values = environment()
    require_redis_container(values)
    client = Client(values)
    try:
        key = 'course12:' + values['COURSE12_RUN_ID'] + ':persist'
        marker = client.call('GET', key)
        if marker != values['COURSE12_RUN_ID'].encode():
            raise AssertionError('The marker from the earlier check is missing')
        info = client.call('INFO', 'persistence').decode()
        selected = [line for line in info.splitlines() if line.startswith(
            ('aof_enabled:', 'aof_last_write_status:', 'rdb_last_bgsave_status:'))]
        print('PASS: the earlier run marker is present')
        print('\n'.join(selected))
    finally:
        client.close()


def run_binary(name):
    path = ROOT / 'build' / name
    if not path.is_file():
        raise ValueError('Build the requested binary first; see README.md')
    if name == 'cache_model':
        return subprocess.run([str(path)], check=False).returncode
    values = environment()
    require_redis_container(values)
    values['COURSE12_HOST'] = '127.0.0.1'
    return subprocess.run([str(path)], env={**os.environ, **values}, check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    init = commands.add_parser('init')
    init.add_argument('--port', type=int, default=16379)
    commands.add_parser('check')
    commands.add_parser('inspect')
    commands.add_parser('client')
    commands.add_parser('model')
    compose = commands.add_parser('compose')
    compose.add_argument('operation', choices=('config', 'up', 'ps', 'client', 'restart', 'down'))
    args = parser.parse_args()
    try:
        if args.action == 'init':
            initialize(args.port)
        elif args.action == 'check':
            check()
        elif args.action == 'inspect':
            inspect()
        elif args.action == 'compose':
            return compose_action(args.operation)
        else:
            return run_binary('cache_client' if args.action == 'client' else 'cache_model')
    except (OSError, ValueError, AssertionError, RedisError, subprocess.TimeoutExpired) as error:
        # Redis errors contain command/type diagnostics, not AUTH arguments.
        print('Lab failed:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
