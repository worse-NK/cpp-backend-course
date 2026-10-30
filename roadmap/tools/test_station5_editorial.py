"""Concrete regressions for station 5's editorial pass.

All writes and subprocess builds stay in a new temporary fixture. We do not run
the chapter's privilege, deletion, signal, installation or remote Git commands.
Passing runs test these examples, not every standard/API claim in the chapter.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]


class StationFiveEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'content/station5.json').read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def code(self, section, index=0):
        return [b['code'] for b in self.sections[section]['blocks']
                if b['type'] == 'code'][index]

    def command(self, directory, *args, success=True):
        result = subprocess.run(args, cwd=directory, text=True,
                                capture_output=True, timeout=40)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def files(self, directory, files):
        # Fixture data, never course source or a user's existing checkout.
        for name, value in files.items():
            target = Path(directory) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value)

    def test_addresses_and_store_key_are_stable(self):
        self.assertEqual(list(self.sections), [
            'learning-route', 'why-build', 'compilation-stages',
            'headers-sources', 'diagnose-build-stage', 'translation-units-odr',
            'incremental-build-graph', 'linkage-symbols', 'libraries-abi',
            'symbol-journey', 'loader-before-main', 'abi-evolution',
            'why-cmake', 'cmake-basics', 'cmake-configure-model',
            'cmake-libraries', 'project-structure', 'cmake-usage-requirements',
            'cmake-propagation', 'cmake-tests-install', 'git-basics',
            'git-object-model', 'build-reproducibility', 'reproducibility-chain',
            'ci-cross-build-tests', 'tooling', 'linux-basics',
            'linux-process-model', 'linux-processes-memory', 'stack-frame-object',
            'signals-and-shutdown', 'ipc-pipes-shared-memory',
            'diagnostics-production', 'diagnostic-ladder', 'profiling-evidence',
            'diagnostic-cases-workbook', 'profile-comparison-workbook',
            'build-final-workbook', 'summary'])
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station5_progress_v1')

    def test_every_section_has_a_revealable_reasoning_check(self):
        for sid, section in self.sections.items():
            checks = [b for b in section['blocks'] if b['type'] == 'self-check']
            self.assertTrue(checks, sid)
            for check in checks:
                self.assertTrue(check['prompt'].strip(), sid)
                self.assertTrue(check['answer'].strip(), sid)

    def test_self_check_cpp_notation_is_escaped_for_html(self):
        for section in self.sections.values():
            for block in section['blocks']:
                if block['type'] != 'self-check':
                    continue
                for field in ('prompt', 'answer'):
                    parser = ProseParser()
                    parser.feed(block[field])
                    self.assertEqual(parser.unknown, [], (section['id'], field))

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_metric_header_and_implementation_agree(self):
        with tempfile.TemporaryDirectory(prefix='station5-metric-') as directory:
            self.files(directory, {
                'Metric.hpp': self.code('headers-sources'),
                'Metric.cpp': self.code('headers-sources', 1),
                'main.cpp': '#include "Metric.hpp"\n#include <iostream>\n'
                            'int main(){Metric m("cpu",7.5); '
                            'std::cout<<m.name()<<" "<<m.value();}\n'})
            self.command(directory, 'g++', '-std=c++20', '-Wall', '-Wextra',
                         '-pedantic', 'Metric.cpp', 'main.cpp', '-o', 'app')
            self.assertEqual(self.command(directory, './app').stdout, 'cpu 7.5')

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_pimpl_destruction_and_moved_from_value(self):
        with tempfile.TemporaryDirectory(prefix='station5-pimpl-') as directory:
            self.files(directory, {
                'client.hpp': self.code('libraries-abi', 1),
                'client.cpp': self.code('libraries-abi', 2),
                'main.cpp': '#include "client.hpp"\n#include <iostream>\n'
                            '#include <utility>\n'
                            'int main(){Client a; std::cout<<a.value()<<" "; '
                            'Client b(std::move(a)); '
                            'std::cout<<a.value()<<" "<<b.value();}\n'})
            self.command(directory, 'g++', '-std=c++20', '-Wall', '-Wextra',
                         '-pedantic', 'client.cpp', 'main.cpp', '-o', 'app')
            self.assertEqual(self.command(directory, './app').stdout, '7 0 7')

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_inline_and_internal_functions_have_different_state_models(self):
        for qualifier, expected in [('inline', '1 2'), ('static', '1 1')]:
            with self.subTest(qualifier=qualifier):
                with tempfile.TemporaryDirectory(prefix='station5-inline-') as directory:
                    self.files(directory, {
                        'next.hpp': '#ifndef NEXT_HPP\n#define NEXT_HPP\n' + qualifier +
                                    ' int next(){static int n=0; return ++n;}\n#endif\n',
                        'left.cpp': '#include "next.hpp"\nint left(){return next();}\n',
                        'main.cpp': '#include "next.hpp"\n#include <iostream>\n'
                                    'int left(); int main(){std::cout<<left()<<" "; '
                                    'std::cout<<next();}\n'})
                    self.command(directory, 'g++', '-std=c++20', 'left.cpp',
                                 'main.cpp', '-o', 'app')
                    self.assertEqual(self.command(directory, './app').stdout, expected)

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_three_file_example_links_only_when_definition_is_supplied(self):
        code = self.code('diagnose-build-stage')
        header, implementation = code.split('// math.cpp\n')
        implementation, main = implementation.split('// main.cpp\n')
        with tempfile.TemporaryDirectory(prefix='station5-link-') as directory:
            self.files(directory, {'math.hpp': header.split('// math.hpp\n')[1],
                                   'math.cpp': implementation, 'main.cpp': main})
            for name in ('math', 'main'):
                self.command(directory, 'g++', '-std=c++20', '-c', name + '.cpp',
                             '-o', name + '.o')
            self.command(directory, 'g++', 'main.o', '-o', 'missing', success=False)
            self.command(directory, 'g++', 'main.o', 'math.o', '-o', 'app')
            self.assertEqual(self.command(directory, './app').stdout, '42')

    def core_fixture(self, directory, cmake):
        self.files(directory, {
            'CMakeLists.txt': cmake,
            'include/core.hpp': '#pragma once\nint twice(int);\n',
            'src/core.cpp': '#include "core.hpp"\nint twice(int x){return x*2;}\n',
            'src/main.cpp': '#include "core.hpp"\n'
                            'int main(){return twice(3)==6 ? 0 : 1;}\n',
            'tests/core_test.cpp': self.code('cmake-tests-install', 1)})

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('g++'),
                         'CMake and C++ compiler required')
    def test_cmake_client_and_ctest_use_the_published_core(self):
        with tempfile.TemporaryDirectory(prefix='station5-cmake-') as directory:
            self.core_fixture(directory, self.code('cmake-tests-install'))
            self.command(directory, 'cmake', '-S', '.', '-B', 'build',
                         '-DBUILD_TESTING=ON', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
            self.command(directory, 'cmake', '--build', 'build')
            run = self.command(directory, 'ctest', '--test-dir', 'build',
                               '--output-on-failure')
            self.assertIn('core.unit', run.stdout)
            commands = json.loads((Path(directory) / 'build/compile_commands.json').read_text())
            self.assertEqual(len(commands), 3)
            for item in commands:
                self.assertIn(str(Path(directory) / 'include'), item['command'])

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('g++'),
                         'CMake and C++ compiler required')
    def test_sanitizer_configuration_applies_to_all_three_compilations(self):
        with tempfile.TemporaryDirectory(prefix='station5-sanitizer-flags-') as directory:
            self.core_fixture(directory, self.code('tooling'))
            self.command(directory, 'cmake', '-S', '.', '-B', 'build',
                         '-DBUILD_TESTING=ON', '-DENABLE_SANITIZERS=ON',
                         '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
            commands = json.loads((Path(directory) / 'build/compile_commands.json').read_text())
            self.assertEqual(len(commands), 3)
            for item in commands:
                self.assertIn('-fsanitize=address,undefined', item['command'])
            # Configure observes flags; it does not claim those paths ran.

    def test_presets_describe_three_distinct_operations(self):
        preset = json.loads(self.code('build-reproducibility'))
        self.assertEqual(preset['version'], 2)
        self.assertEqual(preset['cmakeMinimumRequired']['minor'], 20)
        for key in ('configurePresets', 'buildPresets', 'testPresets'):
            self.assertEqual(preset[key][0]['name'], 'dev')
        for key in ('buildPresets', 'testPresets'):
            self.assertEqual(preset[key][0]['configurePreset'], 'dev')

    def test_percentile_and_cpu_arithmetic_are_separate(self):
        durations = [10] * 98 + [600] * 2
        self.assertEqual(durations[49], 10)
        self.assertEqual(durations[98], 600)
        self.assertEqual(sum(durations) / len(durations), 21.8)
        self.assertAlmostEqual(0.10 / 100, 0.15 / 150)
        self.assertAlmostEqual(0.20 / 200, 0.001)
        self.assertAlmostEqual((0.10 * 4) / 200, 0.002)

    def test_checkpoint_count_and_scenario_answers_are_stable(self):
        checkpoints = json.loads((ROOT / 'content/checkpoints/station5.json').read_text())
        self.assertEqual(len(checkpoints['modules']), 5)
        self.assertTrue(all(len(v) == 5 for v in checkpoints['modules'].values()))
        self.assertEqual(self.data['quizzes']['advanced'][5]['answer'], 2)
        self.assertEqual(self.data['quizzes']['advanced'][30]['answer'], 0)
        self.assertEqual(self.data['quizzes']['advanced'][34]['answer'], 1)
        self.assertEqual(self.data['quizzes']['interview'][1]['answer'], 1)
        self.assertEqual(self.data['quizzes']['interview'][9]['answer'], 0)


if __name__ == '__main__':
    unittest.main()
