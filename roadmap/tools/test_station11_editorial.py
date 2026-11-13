"""Station11 contracts and offline examples; never starts a broker/service.

Passing tests are not evidence of broker runtime, SDK availability or exhaustive
technical/editorial correctness. No sockets or Docker daemon calls are made.
"""
from collections import Counter
from html.parser import HTMLParser
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from build_stations import validate
from checkpoint_data import normalize_prompt, with_checkpoints

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / 'content/station11.json'
DATA = json.loads(DATA_PATH.read_text())
EX = ROOT / 'examples/station11'
MODULES = ['async-contract', 'delivery-contract', 'kafka-log', 'kafka-producer',
           'kafka-consumer', 'rabbitmq', 'cpp-integration', 'messaging-labs']
EXPECTED = ('delivery 0 applied total=3\nrestart 0 duplicate total=3\n'
            'delivery 1 applied total=7\nnext=2 receipts=2\n')


def section(sid):
    return next(s for s in DATA['theory'] if s['id'] == sid)


def prose(sid):
    return ' '.join(b.get('html', '') + b.get('prompt', '') + b.get('answer', '')
                    for b in section(sid)['blocks'])


class Fragment(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr'}:
            self.stack.append(tag)
        if tag == 'a':
            self.hrefs.append(dict(attrs).get('href', ''))

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError('Unbalanced fragment: ' + tag)


def helper():
    spec = importlib.util.spec_from_file_location('station11_rabbit_api', EX / 'rabbit_api.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Station11(unittest.TestCase):
    def test_schema_and_coverage(self):
        validate(DATA, DATA_PATH)
        self.assertEqual(DATA['meta']['storeKey'], 'cpp_station11_progress_v1')
        self.assertEqual(DATA['meta']['sourceFile'], 'cpp_station11_messaging.html')
        self.assertEqual([m['id'] for m in DATA['substations']], MODULES)
        self.assertEqual(len(DATA['theory']), 32)
        self.assertEqual({k: len(v) for k, v in DATA['quizzes'].items()},
                         {'basic': 32, 'advanced': 24, 'interview': 16})
        self.assertEqual(len(DATA['tasks']), 10)
        for module in MODULES:
            self.assertEqual(sum(s['substation'] == module for s in DATA['theory']), 4)
            self.assertGreaterEqual(sum(q['substation'] == module
                                        for q in DATA['quizzes']['basic']), 2)
            self.assertTrue(any(t['substation'] == module for t in DATA['tasks']))

    def test_inline_checkpoints_and_no_final_repeats(self):
        plan = json.loads((ROOT / 'content/checkpoints/station11.json').read_text())
        resolved = with_checkpoints(DATA)
        all_final = {normalize_prompt(q['q']) for qs in DATA['quizzes'].values() for q in qs}
        seen = set()
        for module in MODULES:
            self.assertEqual(len(resolved['checkpoints'][module]), 5)
            for q in plan['modules'][module]:
                self.assertNotIn('bank', q)
                stem = normalize_prompt(q['q'])
                self.assertNotIn(stem, all_final)
                self.assertNotIn(stem, seen)
                seen.add(stem)
        final = [normalize_prompt(q['q']) for qs in DATA['quizzes'].values() for q in qs]
        self.assertEqual(len(final), len(set(final)))

    def test_reading_path_self_checks_and_html(self):
        for s in DATA['theory']:
            with self.subTest(section=s['id']):
                checks = [b for b in s['blocks'] if b['type'] == 'self-check']
                self.assertTrue(checks)
                self.assertGreater(len(checks[0]['answer']), 100)
                self.assertGreater(sum(len(b.get('html', '')) for b in s['blocks']
                                       if b['type'] == 'text'), 1000)
                for b in s['blocks']:
                    for key in ('html', 'prompt', 'answer'):
                        if isinstance(b.get(key), str):
                            parser = Fragment()
                            parser.feed(b[key])
                            self.assertFalse(parser.stack)
                            for href in parser.hrefs:
                                if href.startswith('examples/station11/'):
                                    self.assertTrue((ROOT / href).is_file(), href)
                                elif href.startswith('cpp_station11_messaging.html#section='):
                                    self.assertIn(href.split('=', 1)[1],
                                                  {x['id'] for x in DATA['theory']})
        self.assertGreaterEqual(prose('learning-route').count('learning-route-link'), 9)
        for module in MODULES:
            sections = [s for s in DATA['theory'] if s['substation'] == module]
            markers = [(i, j) for i, s in enumerate(sections)
                       for j, b in enumerate(s['blocks'])
                       if b['type'] == 'note' and 'Контрольная точка' in b.get('html', '')]
            self.assertEqual(markers, [(3, len(sections[-1]['blocks']) - 1)])

    def test_no_systematic_extreme_length_answer_key(self):
        # Statistical tripwire only: it does not establish meaningful distractors.
        sets = dict(DATA['quizzes'])
        sets['checkpoints'] = [q for qs in with_checkpoints(DATA)['checkpoints'].values() for q in qs]
        for name, questions in sets.items():
            for extreme in (min, max):
                hits = 0
                for q in questions:
                    lengths = [len(re.sub('<[^>]*>', '', s)) for s in q['options']]
                    chosen = lengths[q['answer']]
                    hits += chosen == extreme(lengths) and lengths.count(chosen) == 1
                self.assertLessEqual(hits / len(questions), .5, (name, extreme.__name__, hits))
        self.assertEqual(Counter(q['answer'] for q in DATA['quizzes']['basic']),
                         Counter({0: 8, 1: 8, 2: 8, 3: 8}))

    def test_cpp_workbook_matches_download_and_output(self):
        codes = [b['code'] for b in section('messaging-final-workbook')['blocks']
                 if b['type'] == 'code']
        self.assertEqual(codes[0], (EX / 'delivery_model.cpp').read_text())
        self.assertEqual(codes[1] + '\n', EXPECTED)
        for term in ('памят', 'один поток', 'не реализует'):
            self.assertIn(term, prose('messaging-final-workbook'))

    def compile_run(self, source, expected=None, flags=()):
        if not shutil.which('g++'):
            self.skipTest('g++ unavailable')
        with tempfile.TemporaryDirectory(prefix='station11-cpp-') as temp:
            output = Path(temp) / 'model'
            build = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    *flags, '-x', 'c++', '-', '-o', str(output)],
                                   input=source, text=True, capture_output=True, timeout=40)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(output)], text=True, capture_output=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            if expected is not None:
                self.assertEqual(run.stdout, expected)

    def test_cpp_model_o0_and_o2_ndebug(self):
        source = (EX / 'delivery_model.cpp').read_text()
        for flags in (('-O0',), ('-O2', '-DNDEBUG')):
            with self.subTest(flags=flags):
                self.compile_run(source, EXPECTED, flags)

    def test_cpp_model_repeats_zero_and_overflow(self):
        source = (EX / 'delivery_model.cpp').read_text().split('int main() {')[0]
        self.compile_run(source + '''
int main() {
    Ledger value;
    if (!value.apply({"a", 7}) || value.apply({"a", 7})) return 1;
    if (!value.apply({"zero", 0}) || value.total() != 7 || value.receipt_count() != 2) return 2;
    try { value.apply({"bad", -1}); return 3; }
    catch (const std::invalid_argument&) {}
    if (value.total() != 7 || value.receipt_count() != 2) return 4;
    Ledger large;
    if (!large.apply({"max", std::numeric_limits<int>::max()})) return 5;
    try { large.apply({"overflow", 1}); return 6; }
    catch (const std::invalid_argument&) {}
    if (large.total() != std::numeric_limits<int>::max() || large.receipt_count() != 1) return 7;
}
''', '', ('-O2', '-DNDEBUG'))

    def test_parallel_frontier_is_not_maximum_completed(self):
        received = [70, 71, 72, 73]
        done, frontier, seen = set(), 0, []
        for finished in (72, 70, 73, 71):
            done.add(finished)
            while frontier < len(received) and received[frontier] in done:
                frontier += 1
            seen.append(received[frontier] if frontier < len(received) else 74)
        self.assertEqual(seen, [70, 71, 71, 74])
        self.assertEqual(1200 / (150 - 110), 30)
        self.assertEqual(6000 / (600 - 400), 30)

    def test_safe_compose_source_and_offline_config(self):
        text = (EX / 'compose.yaml').read_text()
        self.assertEqual(len(re.findall(r'image: [^\n]+@sha256:[a-f0-9]{64}', text)), 2)
        self.assertEqual(re.findall(r'"127\.0\.0\.1:(\d+):\d+"', text),
                         ['29092', '25672', '25673'])
        for forbidden in ('privileged:', '/var/run/docker.sock', 'network_mode: host', 'container_name:'):
            self.assertNotIn(forbidden, text)
        self.assertIn('COURSE11_RABBIT_PASSWORD:?', text)
        instructions = (EX / 'README.txt').read_text()
        for guard in ('test -z "${DOCKER_HOST-}"', 'test -z "${DOCKER_CONTEXT-}"',
                      "docker context inspect --format '{{.Endpoints.docker.Host}}'",
                      'unix:///', 'ssh://', 'tcp://', 'Не выполняй unset',
                      'Не меняй рабочий context'):
            self.assertIn(guard, instructions)
        if not shutil.which('docker'):
            self.skipTest('Docker CLI absent; no daemon operation attempted')
        env = dict(os.environ, COURSE11_RABBIT_PASSWORD='offline-validation-not-a-real-secret')
        proc = subprocess.run(['docker', 'compose', '-f', str(EX / 'compose.yaml'),
                               '-p', 'course11-offline-config-test', 'config', '--quiet'],
                              env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_helper_routes_and_modes_without_network(self):
        api = helper()
        for action, method, ending, mode in (
                ('peek', 'POST', '/get', 'ack_requeue_true'),
                ('take', 'POST', '/get', 'ack_requeue_false'),
                ('publish', 'POST', '/publish', None)):
            with self.subTest(action=action), patch.object(api, 'request') as call, patch('sys.stdout', io.StringIO()):
                call.return_value = {'routed': True} if action == 'publish' else []
                api.main([action])
                args = call.call_args.args
                self.assertEqual(args[0], method)
                self.assertTrue(args[1].endswith(ending))
                if mode:
                    self.assertEqual(args[2]['ackmode'], mode)
                else:
                    self.assertEqual(args[2]['routing_key'], 'orders.created')
        with patch.object(api, 'request', return_value=None) as call, patch('sys.stdout', io.StringIO()):
            api.main(['setup'])
            self.assertEqual(call.call_count, 3)
            self.assertTrue(all(c.args[0] != 'DELETE' for c in call.call_args_list))
        with patch.dict(os.environ, {'COURSE11_RABBIT_PASSWORD': ''}), patch.object(api.urllib.request, 'build_opener') as build:
            with self.assertRaises(ValueError):
                api.request('GET', 'queues/course11/course11.audit')
            build.assert_not_called()
        with self.assertRaises(ValueError):
            api.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid/')

    def test_version_boundaries_are_written(self):
        poison = prose('rabbit-poison-dead-letter')
        for word in ('4.3', 'basic.nack', 'acquired-count', 'at-least-once', 'reject-publish'):
            self.assertIn(word, poison)
        self.assertIn('false', prose('kafka-producer-idempotence'))
        self.assertIn('2.12.1', prose('kafka-producer-idempotence'))
        self.assertIn('SQL', prose('kafka-transactions-scope'))
        self.assertIn('метаданные', prose('kafka-failures-kraft'))
        self.assertIn('ELR', prose('kafka-failures-kraft'))
        self.assertIn('по умолчанию', prose('kafka-failures-kraft'))
        self.assertIn('no_ack=true', prose('rabbit-redelivery-lab'))
        self.assertIn('не', prose('messaging-local-lab'))
        self.assertEqual(sum(t['title'].startswith('Лаборатория: ')
                             for t in DATA['tasks'] if t['level'] == 'Практика'), 3)

    def test_cheatsheet_group_and_section_anchors(self):
        catalog = json.loads((ROOT / 'content/cheatsheet.json').read_text())
        group = next(g for g in catalog['stations'] if g['num'] == '11')
        self.assertEqual(group['num'], '11')
        self.assertEqual(len(group['sections']), 8)
        ids = {s['id'] for s in DATA['theory']}
        for s in group['sections']:
            for item in s['items']:
                parser = Fragment()
                parser.feed(item['rule'])
                self.assertFalse(parser.stack)
                self.assertTrue(any(u.startswith('https://') for u in parser.hrefs)
                                or 'Инструкция' in item['rule'])
                for href in parser.hrefs:
                    if href.startswith('cpp_station11_messaging.html#section='):
                        self.assertIn(href.split('=', 1)[1], ids)


if __name__ == '__main__':
    unittest.main()
