"""Offline Redis chapter checks. Never starts Docker or contacts a Redis server.

Passing these checks is not a live Redis/hiredis integration result. Compilation
of the dependency-free model and RESP fixture tests cover only their boundaries.
"""
from collections import Counter
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, unquote

from build_stations import validate
from checkpoint_data import with_checkpoints, normalize_prompt
from test_linux_systems import Fragment, fields

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station12.json'
EXAMPLES = ROOT / 'examples/station12'
EXPECTED = ('TTL-only: 100, origin: 120\nold fill accepted: false\n'
            'reloaded: 120\nat expiry: false\n')
LAB_FILES = {'cache_model.cpp', 'cache_client.cpp', 'CMakeLists.txt',
             'redis.conf', 'compose.yaml', 'Dockerfile', 'rate_limit.lua',
             'release_lock.lua', '.dockerignore', '.gitignore',
             '.env.example', 'lab.py', 'README.md'}


def helper():
    spec = importlib.util.spec_from_file_location('redis_lab12', EXAMPLES / 'lab.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RedisContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.resolved = with_checkpoints(cls.data)
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def test_schema_and_assessment_counts(self):
        validate(self.data, SOURCE)
        self.assertEqual(32, len(self.sections))
        self.assertEqual(7, len(self.data['substations']))
        self.assertEqual({'basic': 28, 'advanced': 21, 'interview': 14},
                         {k: len(v) for k, v in self.data['quizzes'].items()})
        self.assertEqual({5}, {len(v) for v in self.resolved['checkpoints'].values()})
        self.assertEqual(9, len(self.data['tasks']))
        for group in self.data['substations']:
            module = group['id']
            for bank in self.data['quizzes'].values():
                self.assertGreaterEqual(sum(q['substation'] == module for q in bank), 2)
            sections = [s for s in self.data['theory'] if s['substation'] == module]
            self.assertIn('Контрольная точка', sections[-1]['blocks'][-1]['html'])
            self.assertEqual('note', sections[-1]['blocks'][-1]['type'])

    def test_self_checks_and_balanced_html(self):
        for section in self.data['theory']:
            checks = [b for b in section['blocks'] if b['type'] == 'self-check']
            self.assertEqual(1, len(checks), section['id'])
            self.assertGreater(len(checks[0]['answer']), 100, section['id'])
        for field in ('html', 'prompt', 'answer'):
            for html in fields(self.data['theory'], field):
                parsed = Fragment(html)
                self.assertFalse(parsed.errors, (field, parsed.errors))
                self.assertFalse(parsed.stack, (field, parsed.stack))

    def test_independent_prompts_and_no_future_quiz_refs(self):
        all_questions = [q for bank in self.data['quizzes'].values() for q in bank]
        all_questions += [q for cp in self.resolved['checkpoints'].values() for q in cp]
        prompts = [normalize_prompt(q['q']) for q in all_questions]
        self.assertEqual(len(prompts), len(set(prompts)))
        order = {g['id']: i for i, g in enumerate(self.data['substations'])}
        for q in all_questions:
            for ref in q['theoryRefs']:
                self.assertLessEqual(order[self.sections[ref]['substation']], order[q['substation']])
            self.assertEqual(len(q['options']), len(set(q['options'])))
            # A mechanical warning boundary, not proof of distractor quality.
            answer_len = len(q['options'][q['answer']])
            other_max = max(len(v) for i, v in enumerate(q['options']) if i != q['answer'])
            self.assertLess(answer_len, other_max * 1.8, q['q'])
        for bank in self.data['quizzes'].values():
            positions = Counter(q['answer'] for q in bank)
            self.assertEqual({0, 1, 2}, set(positions))

    def test_code_matches_downloads_and_links(self):
        for section_id, filename in (
                ('cache-race-final-workbook', 'cache_model.cpp'),
                ('lua-fixed-window', 'rate_limit.lua'),
                ('lease-vs-lock', 'release_lock.lua')):
            expected = (EXAMPLES / filename).read_text()
            codes = [b['code'] for b in self.sections[section_id]['blocks'] if b['type'] == 'code']
            self.assertIn(expected, codes)
        self.assertEqual(LAB_FILES, {p.name for p in EXAMPLES.iterdir() if p.is_file()})
        downloads = set()
        for html in fields(self.data['theory'], 'html'):
            for href in Fragment(html).links:
                if not href:
                    continue
                parsed = urlsplit(href)
                if parsed.path.startswith('examples/station12/'):
                    name = unquote(parsed.path).split('/')[-1]
                    downloads.add(name)
                    self.assertIn(name, LAB_FILES)
                    self.assertTrue((EXAMPLES / name).is_file())
        self.assertTrue({'README.md', 'cache_model.cpp', 'cache_client.cpp',
                         'CMakeLists.txt', 'compose.yaml', 'lab.py'} <= downloads)
        labs = [t for t in self.data['tasks'] if t['level'] == 'Практика']
        self.assertEqual(3, len(labs))
        self.assertTrue(all(t['title'].startswith('Лаборатория: ') for t in labs))

    def test_explicit_safety_contracts(self):
        compose = (EXAMPLES / 'compose.yaml').read_text()
        self.assertIn('redis:8.2.11-alpine', compose)
        self.assertIn('127.0.0.1:${COURSE12_PORT', compose)
        self.assertIn('COURSE12_PROJECT:?', compose)
        self.assertNotIn('container_name:', compose)
        self.assertNotIn('privileged:', compose)
        self.assertIn('gcc:14.4.0-trixie', (EXAMPLES / 'Dockerfile').read_text())
        self.assertIn('GIT_TAG v1.3.0', (EXAMPLES / 'CMakeLists.txt').read_text())
        for ignore in ('.gitignore', '.dockerignore'):
            content = (EXAMPLES / ignore).read_text()
            self.assertIn('.env', content)
            self.assertIn('runtime', content)
        config = (EXAMPLES / 'redis.conf').read_text()
        self.assertIn('protected-mode yes', config)
        self.assertIn('maxmemory-policy noeviction', config)
        cli = (EXAMPLES / 'cache_client.cpp').read_text()
        self.assertIn('redisCommandArgv', cli)
        self.assertIn('reply->len', cli)
        self.assertIn('redisSetTimeout', cli)
        self.assertNotIn('FLUSHDB', cli)
        self.assertNotIn('FLUSHALL', cli)

    def test_arithmetic_and_protocol_models(self):
        self.assertEqual(340000000, 800000 * (45 + 280 + 100))
        self.assertAlmostEqual(324.2492676, 340000000 / 1024**2, places=5)
        self.assertEqual(50, 100000 / (100000 * .02))
        self.assertEqual(20, 40000 / (40000 * .05))
        self.assertEqual(12, (60 // 15) * 3)
        self.assertEqual(4, 7 // 2 + 1)
        self.assertEqual(3, 5 // 2 + 1)
        # Fixed-window admits only its first N calls; not a rolling-window proof.
        current, decisions = 0, []
        for _ in range(4):
            accepted = current < 3
            current += accepted
            decisions.append(int(accepted))
        self.assertEqual([1, 1, 1, 0], decisions)
        self.assertEqual(3, current)


class RedisOfflineCode(unittest.TestCase):
    def test_dependency_free_cpp_and_expiry_boundaries(self):
        compiler = shutil.which('g++')
        if not compiler:
            self.skipTest('g++ unavailable; C++ model not compiled')
        with tempfile.TemporaryDirectory(prefix='course12-cpp-') as temporary:
            binary = Path(temporary) / 'cache_model'
            compile_result = subprocess.run([
                compiler, '-std=c++20', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
                str(EXAMPLES / 'cache_model.cpp'), '-o', str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, compile_result.returncode, compile_result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(EXPECTED, result.stdout)

    def test_hiredis_integration_is_not_claimed_offline(self):
        self.skipTest('Docker/Redis runtime and network dependency build require the separate lab environment; not run by this suite')

    def test_resp_fixtures(self):
        lab = helper()
        self.assertEqual(b'*2\r\n$3\r\nGET\r\n$3\r\nA\x00B\r\n', lab.wire(('GET', b'A\0B')))
        fixtures = [(b'$0\r\n\r\n', b''), (b'$-1\r\n', None),
                    (b'*-1\r\n', None), (b':-2\r\n', -2),
                    (b'+OK\r\n', b'OK'), (b'$3\r\nA\0B\r\n', b'A\0B')]
        for wire, expected in fixtures:
            self.assertEqual(expected, lab.read_reply(io.BytesIO(wire)))
        nested = lab.read_reply(io.BytesIO(b'*2\r\n-ERR bad\r\n+OK\r\n'))
        self.assertIsInstance(nested[0], lab.RedisError)
        self.assertEqual(b'OK', nested[1])
        for bad in (b'', b'$-2\r\n', b'$1048577\r\n', b'*257\r\n',
                    b'$3\r\na\r\n', b'%0\r\n', b'+OK\n'):
            with self.assertRaises(ValueError):
                lab.read_reply(io.BytesIO(bad))
        with self.assertRaisesRegex(ValueError, 'node limit'):
            lab.read_reply(io.BytesIO(b'*2\r\n+OK\r\n+OK\r\n'), budget=[1024, 2])
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            lab.read_reply(io.BytesIO(b'$3\r\nabc\r\n'), budget=[8, 5])

    def test_safe_initialization_and_acl_without_any_connection(self):
        lab = helper()
        with tempfile.TemporaryDirectory(prefix='course12-config-') as temporary:
            lab.ROOT = Path(temporary)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                lab.initialize(16379)
            values = lab.environment()
            secret = values['COURSE12_PASSWORD']
            self.assertNotIn(secret, output.getvalue())
            acl = (lab.ROOT / 'runtime/users.acl').read_text()
            self.assertNotIn(secret, acl)
            self.assertIn('~course12:' + values['COURSE12_RUN_ID'] + ':*', acl)
            for forbidden in ('+@all', '+flushdb', '+flushall', '+config', '+shutdown'):
                self.assertNotIn(forbidden, acl.casefold())
            self.assertEqual(0o600, stat.S_IMODE((lab.ROOT / '.env').stat().st_mode))
            original = (lab.ROOT / '.env').read_bytes()
            with self.assertRaises(ValueError):
                lab.initialize(16379)
            self.assertEqual(original, (lab.ROOT / '.env').read_bytes())
            compose = shutil.which('docker')
            if compose:
                # config is client-side parsing only: never up/run/restart/build.
                shutil.copy(EXAMPLES / 'compose.yaml', lab.ROOT / 'compose.yaml')
                with patch.dict(os.environ, {'COMPOSE_PROJECT_NAME': 'not-this-lab',
                                             'COURSE12_PROJECT': 'not-this-lab',
                                             'COURSE12_PASSWORD': 'not-this-secret',
                                             'DOCKER_HOST': 'ssh://not-this-engine'}):
                    self.assertEqual(0, lab.compose_action('config'))

    def test_compose_values_override_shell_and_config_does_not_inspect_daemon(self):
        lab = helper()
        values = {'COURSE12_PROJECT': 'course12-0123456789abcdef',
                  'COURSE12_RUN_ID': '0123456789abcdef', 'COURSE12_PASSWORD': 'a' * 64,
                  'COURSE12_PORT': '16379'}
        hostile = {'COURSE12_PROJECT': 'foreign', 'COURSE12_PASSWORD': 'wrong',
                   'COURSE12_PORT': '9999', 'COMPOSE_PROJECT_NAME': 'foreign',
                   'COMPOSE_FILE': '/unrelated.yaml', 'DOCKER_HOST': 'ssh://foreign',
                   'DOCKER_CONTEXT': 'production'}
        with patch.dict(os.environ, hostile), patch.object(lab, 'environment', return_value=values), \
                patch.object(lab.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(lab.compose_action('config'), 0)
            command = run.call_args.args[0]
            env = run.call_args.kwargs['env']
            self.assertEqual(command[0:2], ['docker', 'compose'])
            self.assertEqual(command[command.index('-p') + 1], values['COURSE12_PROJECT'])
            self.assertEqual(command[-2:], ['config', '--quiet'])
            self.assertEqual(env['COURSE12_PASSWORD'], values['COURSE12_PASSWORD'])
            self.assertEqual(env['COURSE12_PORT'], '16379')
            self.assertFalse(any(k.startswith(('DOCKER_', 'COMPOSE_')) for k in env))
            self.assertNotIn(values['COURSE12_PASSWORD'], ' '.join(command))
            self.assertEqual(run.call_count, 1)

    def test_remote_context_is_rejected_before_engine_calls(self):
        lab = helper()
        for endpoint in ('tcp://127.0.0.1:2375', 'ssh://host', 'npipe:////./pipe/docker_engine'):
            response = json.dumps([{'Endpoints': {'docker': {'Host': endpoint}}}])
            with self.subTest(endpoint=endpoint), patch.object(lab, 'docker_output', return_value=response) as output:
                with self.assertRaises(ValueError):
                    lab.local_docker({})
                self.assertEqual(output.call_count, 1)

    def test_foreign_project_and_unlabelled_name_collision_never_reach_compose(self):
        lab = helper()
        values = {'COURSE12_PROJECT': 'course12-0123456789abcdef',
                  'COURSE12_RUN_ID': '0123456789abcdef'}
        for collision in ('container', 'volume', 'network'):
            def inventory(prefix, args, env):
                if args[:2] == ['ps', '-aq']:
                    return 'abc123' if collision == 'container' else ''
                if args[:2] == ['container', 'inspect']:
                    return json.dumps([{'Config': {'Labels': {'com.docker.compose.project': values['COURSE12_PROJECT']}}}])
                if args[:2] in (['volume', 'ls'], ['network', 'ls']):
                    kind = args[0]
                    if '--format' in args and kind == collision:
                        return values['COURSE12_PROJECT'] + ('_redis-data' if kind == 'volume' else '_default')
                    return ''
                if args[1] == 'inspect':
                    return json.dumps([{'Labels': {}}])
                raise AssertionError(args)
            with self.subTest(collision=collision), patch.object(lab, 'environment', return_value=values), \
                    patch.object(lab, 'local_docker', return_value=(['docker', '--host', 'unix:///tmp/test.sock'], {})), \
                    patch.object(lab, 'docker_output', side_effect=inventory), patch.object(lab.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'collision'):
                    lab.compose_action('down')
                run.assert_not_called()

    def test_wrong_published_port_fails_before_redis_auth_or_writes(self):
        lab = helper()
        values = {'COURSE12_PROJECT': 'course12-0123456789abcdef',
                  'COURSE12_RUN_ID': '0123456789abcdef', 'COURSE12_PORT': '16379'}
        container = {'Config': {'Image': 'redis:8.2.11-alpine', 'Labels': {
                         'com.docker.compose.service': 'redis'}}, 'State': {'Running': True},
                     'NetworkSettings': {'Ports': {'6379/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '9999'}]}}}
        with patch.object(lab, 'environment', return_value=values), \
                patch.object(lab, 'local_docker', return_value=(['docker'], {})), \
                patch.object(lab, 'project_resources', return_value=[container]), patch.object(lab, 'Client') as client:
            with self.assertRaisesRegex(ValueError, 'loopback'):
                lab.check()
            client.assert_not_called()

    def test_modified_env_is_not_adopted_as_another_project(self):
        lab = helper()
        with tempfile.TemporaryDirectory(prefix='course12-owner-') as temporary:
            lab.ROOT = Path(temporary)
            with contextlib.redirect_stdout(io.StringIO()):
                lab.initialize(16379)
            original = (lab.ROOT / '.env').read_text()
            (lab.ROOT / '.env').write_text(original.replace('COURSE12_PORT=16379', 'COURSE12_PORT=16380'))
            with self.assertRaisesRegex(ValueError, 'ownership'):
                lab.environment()

    def test_symlink_and_port_guards(self):
        lab = helper()
        with tempfile.TemporaryDirectory(prefix='course12-guards-') as temporary:
            lab.ROOT = Path(temporary)
            for port in (0, 637, 65536):
                with self.assertRaises(ValueError):
                    lab.initialize(port)
            target = lab.ROOT / 'do-not-change'
            target.mkdir()
            (lab.ROOT / 'runtime').symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                lab.initialize(16379)
            self.assertFalse(list(target.iterdir()))


if __name__ == '__main__':
    unittest.main()
