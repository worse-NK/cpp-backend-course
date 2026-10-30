"""Station 10 editorial contracts; no Docker, cloud jobs or load requests.

These checks protect examples and selected explanations, not all teaching quality.
"""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from checkpoint_data import with_checkpoints
from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'content/station10.json').read_text())
IDS = '''learning-route test-contract test-levels test-dependencies gtest-ctest
sanitizers-coverage reproducible-build container-model docker-build
docker-network-data ci-model ci-example ci-artifacts health-drain
release-compatibility overload-limits signals metrics-slo capacity-experiment
capacity-local-lab incident-security project-story request-budget-architecture
proxy-release-timeline gate-final-workbook'''.split()


def section(sid):
    return next(s for s in DATA['theory'] if s['id'] == sid)


def prose(sid):
    return ' '.join(b.get('html', '') + b.get('prompt', '') + b.get('answer', '')
                    for b in section(sid)['blocks'])


class BalancedHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr'}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError('Unbalanced HTML: ' + tag)


class Station10Editorial(unittest.TestCase):
    def compile_run(self, source, expected):
        if not shutil.which('g++'):
            self.skipTest('g++ unavailable')
        with tempfile.TemporaryDirectory(prefix='station10-editorial-') as temp:
            binary = Path(temp) / 'check'
            build = subprocess.run(['g++', '-std=c++20', '-DNDEBUG', '-O2',
                                    '-x', 'c++', '-', '-o', str(binary)],
                                   input=source, text=True, capture_output=True,
                                   timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True,
                                 timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, expected)

    def test_identifiers_and_source_schema(self):
        validate(DATA, ROOT / 'content/station10.json')
        self.assertEqual([s['id'] for s in DATA['theory']], IDS)
        self.assertEqual(DATA['meta']['storeKey'], 'cpp_station10_progress_v1')
        self.assertEqual(len(DATA['substations']), 7)
        self.assertEqual(len(DATA['tasks']), 10)
        self.assertEqual({k: len(v) for k, v in DATA['quizzes'].items()},
                         {'basic': 21, 'advanced': 13, 'interview': 18})

    def test_original_code_and_visual_payload_order(self):
        expected = {
            'code': (16, '2f5a842b470c52ae8516f86161ec722923f170fa6ab2d5506b62c2f484fbd7c7'),
            'diagram': (16, 'e4b96e2ea3a69c30cccca42d7d236020eea9d3e7288471a1ca5d61580d984ae9'),
            'lab': (1, '39369db963fe72c4daf492d39154442589ba740ee8bbc6ba82f2e25388d714cc'),
        }
        for kind, (count, digest) in expected.items():
            items = [(s['id'], b['code'] if kind == 'code' else b)
                     for s in DATA['theory'] for b in s['blocks']
                     if b['type'] == kind]
            with self.subTest(kind=kind):
                self.assertEqual(len(items), count)
                actual = hashlib.sha256(json.dumps(
                    items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                self.assertEqual(actual, digest)
        task_codes = [t.get('code') for t in DATA['tasks']]
        self.assertEqual(hashlib.sha256(json.dumps(task_codes, ensure_ascii=False)
                                       .encode()).hexdigest(),
                         '4c636cb05ee2090cb582be350bfb4aeb7e4590e7ccd06c17774b9b6d322a82cd')

    def test_answers_can_be_revealed_in_every_section(self):
        for s in DATA['theory']:
            checks = [b for b in s['blocks'] if b['type'] == 'self-check']
            with self.subTest(section=s['id']):
                self.assertTrue(checks)
                for b in checks:
                    self.assertGreater(len(b['prompt']), 35)
                    self.assertGreater(len(b['answer']), 80)
                for b in s['blocks']:
                    for key in ('html', 'prompt', 'answer'):
                        if isinstance(b.get(key), str):
                            parser = BalancedHTML()
                            parser.feed(b[key])
                            self.assertEqual(parser.stack, [], (s['id'], key))

    def test_module_markers_are_last_after_self_checks(self):
        for module in DATA['substations']:
            sections = [s for s in DATA['theory']
                        if s['substation'] == module['id']]
            markers = [(i, j) for i, s in enumerate(sections)
                       for j, b in enumerate(s['blocks'])
                       if b['type'] == 'note'
                       and 'Контрольная точка' in b.get('html', '')]
            self.assertEqual(markers,
                             [(len(sections)-1, len(sections[-1]['blocks'])-1)],
                             module['id'])

    def test_checkpoint_refs_and_distinct_prompts(self):
        resolved = with_checkpoints(DATA)
        seen = set()
        for module, questions in resolved['checkpoints'].items():
            self.assertEqual(len(questions), 5, module)
            for q in questions:
                stem = ' '.join(q['q'].casefold().split())
                self.assertNotIn(stem, seen)
                seen.add(stem)
                self.assertEqual(q['substation'], module)
        for bank, qs in DATA['quizzes'].items():
            self.assertEqual(len({q['q'] for q in qs}), len(qs), bank)
            for q in qs:
                self.assertTrue(q['theoryRefs'])
                self.assertTrue(set(q['theoryRefs']) <= set(IDS))
                self.assertEqual(len(q['options']), len(set(q['options'])))
                self.assertIn(q['answer'], range(len(q['options'])))

    def test_no_systematic_extreme_length_key(self):
        # A warning guard, never proof of plausible distractors or readability.
        for bank, qs in DATA['quizzes'].items():
            for extreme in (min, max):
                hits = 0
                for q in qs:
                    lengths = [len(re.sub('<[^>]+>', '', o)) for o in q['options']]
                    value = extreme(lengths)
                    hits += lengths[q['answer']] == value and lengths.count(value) == 1
                self.assertLessEqual(hits / len(qs), .5,
                                     (bank, extreme.__name__, hits))

    def test_fatal_assertion_scope_and_empty_tests(self):
        p = prose('gtest-ctest')
        for term in ('текущая функция', 'помощник', '--no-tests=error', 'не скачивает'):
            self.assertIn(term, p)
        q = DATA['quizzes']['advanced'][4]
        self.assertIn('неуспешен', q['q'])
        self.assertIn('helper', q['options'][q['answer']])

    def test_deadline_boundary_is_executable(self):
        code = next(b['code'] for b in section('test-dependencies')['blocks']
                    if b['type'] == 'code')
        self.compile_run(code + '''
#include <iostream>
int main() {
  using Clock = std::chrono::steady_clock;
  auto deadline = Clock::time_point{} + std::chrono::seconds(3);
  std::cout << expired(deadline - std::chrono::nanoseconds(1), deadline) << ' '
            << expired(deadline, deadline) << ' '
            << expired(deadline + std::chrono::nanoseconds(1), deadline);
}
''', '0 1 1')

    def test_gate_table_for_multiple_limits_with_ndebug(self):
        source = (ROOT / 'examples/station10/main.cpp').read_text()
        source = '#define main original_station10_main\n' + source + '\n#undef main\n'
        source += '''
int main() {
  for (std::size_t n : {1u, 2u, 7u}) {
    Gate g(n);
    check(g.ready() && !g.stopped(), "idle is not stopped");
    for (std::size_t i=0; i<n; ++i) {
      check(g.enter()==Admission::accepted, "accept below boundary");
      check(g.active()==i+1, "count accepted exactly");
    }
    check(g.enter()==Admission::full && g.active()==n, "full unchanged");
    g.drain(); g.drain();
    check(!g.ready(), "not ready after drain");
    check(g.enter()==Admission::draining && g.active()==n, "drain priority");
    for (std::size_t left=n; left>0; --left) {
      g.finish();
      check(g.active()==left-1, "finish count");
      check(g.stopped()==(left==1), "stopped only after last finish");
    }
    bool caught=false;
    try { g.finish(); } catch (const std::logic_error&) { caught=true; }
    check(caught && g.active()==0, "unmatched finish preserves zero");
  }
  std::cout << "limits 1 2 7 passed";
}
'''
        self.compile_run(source, 'limits 1 2 7 passed')

    def test_budget_and_weighted_statistics(self):
        self.assertEqual(sum([20, 75, 105, 20, 10, 30]), 260)
        self.assertEqual(300 - sum([20, 75, 105]), 100)
        self.assertEqual(260 - 20 + 10, 250)
        self.assertEqual(260 + 80, 340)
        self.assertAlmostEqual((900+10)/(1000+10)*100, 90.0990099009901)
        self.assertEqual(1_000_000 // 1000 - 600, 400)
        self.assertIn('100 мс', DATA['quizzes']['basic'][0]['options'][1])
        self.assertIn('не формула p99', prose('overload-limits'))

    def test_sources_have_versions_and_scope(self):
        self.assertIn('/v1.17.0/', prose('gtest-ctest'))
        self.assertIn('/v3.28/', prose('gtest-ctest'))
        self.assertIn('18.1.8', prose('sanitizers-coverage'))
        self.assertIn('GCC 14.3', prose('sanitizers-coverage'))
        self.assertIn('28.0.0', prose('docker-network-data'))
        self.assertIn('N4861', prose('gate-final-workbook'))
        self.assertIn('между последовательными чтениями', prose('proxy-release-timeline'))

    def test_lab_is_not_claimed_to_measure_production(self):
        text = prose('capacity-local-lab')
        for phrase in ('не создаёт сервер', 'не отключай', 'dropped_iterations',
                       'целевое', 'локальный'):
            self.assertIn(phrase, text.casefold())
        self.assertIn('не реализует выпуск без разрыва', DATA['tasks'][7]['solution'])
        self.assertIn('не реализуются', prose('release-compatibility'))


if __name__ == '__main__':
    unittest.main()
