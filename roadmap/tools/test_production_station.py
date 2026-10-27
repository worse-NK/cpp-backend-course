"""Executable examples and integration contracts for station 10 (no Docker daemon)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_stations
import test_cpp_editorial_audit
import test_expanded_examples

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'content/station10.json').read_text())
EXAMPLES = ROOT / 'examples/station10'


def section(sid):
    return next(s for s in DATA['theory'] if s['id'] == sid)


class ProductionStation(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    def test_schema_and_learning_path(self):
        build_stations.validate(DATA, ROOT / 'content/station10.json')
        self.assertEqual(len(DATA['substations']), 7)
        self.assertEqual(len(DATA['theory']), 25)
        self.assertEqual(len(DATA['quizzes']['interview']), 18)
        for sub in DATA['substations']:
            self.assertEqual(sum(q['substation'] == sub['id'] for q in DATA['quizzes']['basic']), 3)
            self.assertTrue(any(t['substation'] == sub['id'] for t in DATA['tasks']))

    def test_no_templates_lost_in_html(self):
        for fragment in test_cpp_editorial_audit.prose(DATA['theory']):
            parser = test_cpp_editorial_audit.ProseParser()
            parser.feed(fragment)
            self.assertEqual(parser.unknown, [])

    def test_examples_match_text(self):
        for sid, caption, filename in [
            ('gate-final-workbook', 'Полная программа', 'main.cpp'),
            ('gate-final-workbook', 'CMakeLists.txt', 'CMakeLists.txt'),
            ('docker-build', 'Dockerfile', 'Dockerfile'),
            ('ci-example', 'Файл .github', 'check.yml'),
        ]:
            block = next(b for b in section(sid)['blocks'] if b.get('caption', '').startswith(caption))
            self.assertEqual(block['code'].strip(), (EXAMPLES / filename).read_text().strip())

    def test_debug_and_release_ctest(self):
        for config in ['Debug', 'Release']:
            with self.subTest(config=config), tempfile.TemporaryDirectory(prefix='station10-check-') as tmp:
                commands = [
                    ['cmake', '-S', str(EXAMPLES), '-B', tmp, '-DCMAKE_BUILD_TYPE=' + config],
                    ['cmake', '--build', tmp, '--parallel', '2'],
                    ['ctest', '--test-dir', tmp, '--output-on-failure', '--no-tests=error'],
                ]
                for cmd in commands:
                    result = subprocess.run(cmd, text=True, capture_output=True, timeout=45)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                run = subprocess.run([str(Path(tmp) / 'gate_check')], capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout, 'all checks passed\n')

    def test_mutations_are_detected_with_ndebug(self):
        source = (EXAMPLES / 'main.cpp').read_text()
        for old, new, message in [
            ('active_ == limit_', 'active_ > limit_', 'third rejected'),
            ('draining_ && active_ == 0', 'active_ == 0', 'idle is not stopped'),
            ('void drain() noexcept { draining_ = true; }', 'void drain() noexcept {}', 'draining is not ready'),
        ]:
            with self.subTest(mutation=old), tempfile.TemporaryDirectory(prefix='station10-mutant-') as tmp:
                binary = str(Path(tmp) / 'mutant')
                result = subprocess.run(['g++', '-std=c++20', '-DNDEBUG', '-O2', '-x', 'c++', '-', '-o', binary], input=source.replace(old, new), capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run([binary], capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 1)
                self.assertIn(message, run.stderr)

    def test_pipeline_has_failure_and_trust_boundaries(self):
        workflow = (EXAMPLES / 'check.yml').read_text()
        self.assertIn('--no-tests=error', workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn('timeout-minutes:', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('pull_request_target', workflow)
        dockerfile = (EXAMPLES / 'Dockerfile').read_text()
        self.assertIn('COPY --from=build', dockerfile)
        self.assertIn('USER 65532:65532', dockerfile)
        self.assertIn('--no-tests=error', dockerfile)


if __name__ == '__main__':
    unittest.main()
