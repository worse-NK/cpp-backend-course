"""Exercise inputs, preparation links and the revised lifecycle example.

These checks guard the reviewed structure; they do not grade teaching quality.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]


class PracticePreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {(int(p.stem[7:]) if p.stem[7:].isdigit() else p.stem[7:]):
                    json.loads(p.read_text()) for p in (ROOT / 'content').glob('station[0-9]*.json')}

    def test_all_exercises_have_resolvable_preparation(self):
        self.assertTrue(self.data)
        for n, data in self.data.items():
            validate(data, ROOT / f'content/station{n}.json')
            sections = {s['id']: s for s in data['theory']}
            for task in data['tasks']:
                self.assertTrue(task['theoryRefs'], task['title'])
                for ref in task['theoryRefs']:
                    self.assertTrue(sections[ref]['blocks'])

    def test_validator_rejects_missing_unknown_and_duplicate_refs(self):
        for refs in ([], ['missing-section'], ['destructor', 'destructor']):
            data = copy.deepcopy(self.data[0])
            data['tasks'][0]['theoryRefs'] = refs
            with self.assertRaises(ValueError):
                validate(data, ROOT / 'content/station0.json')
        data = copy.deepcopy(self.data[0])
        data['tasks'][0]['solutionFormat'] = 'html'
        with self.assertRaises(ValueError):
            validate(data, ROOT / 'content/station0.json')

    def test_reading_inputs_are_not_hidden_in_solutions(self):
        for index in (0, 6, 7, 8, 9, 10, 11, 19):
            task = self.data[6]['tasks'][index]
            self.assertIn('#include', task['code'])
            self.assertEqual(task['solutionFormat'], 'text')
            self.assertNotIn('#include', task['solution'])
        self.assertIn('300 IN NS', self.data[7]['tasks'][25]['code'])
        http = self.data[7]['tasks'][18]['code']
        self.assertIn(r'\r\n\r\nDATAGET', http)

    def test_numeric_checklists_do_not_contain_the_results(self):
        forbidden = {
            (3, 8): r'две копии|B′|A′',
            (3, 9): r'A3B2C4D',
            (8, 12): r'20,30|30,40',
            (8, 20): r'200 мс',
            (8, 21): r'20 байт|10 байт',
            (8, 22): r'14,1|9,1|35,5',
            (8, 23): r'0–180|240–420|120\+50',
            (8, 25): r'5 секунд|за 5',
        }
        for (n, i), pattern in forbidden.items():
            self.assertNotRegex(' '.join(self.data[n]['tasks'][i]['checks']), pattern)

    def test_latch_partial_startup_does_not_wait_for_missing_worker(self):
        task = self.data[6]['tasks'][9]
        prefix = '''
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <vector>
struct Metric { int value; };
std::atomic<int> processed{0};
int published = -1;
std::vector<Metric> collectFrom(const char*) { return {{1}}; }
void logNoThrow(const char*, const char*) noexcept {}
void logUnknownFailureNoThrow(const char*) noexcept {}
void doPostProcessing(const char*) { ++processed; }
void publishSnapshot(const std::vector<Metric>& snapshot) {
    published = static_cast<int>(snapshot.size());
}
'''
        code = task['code'].replace('int main() {', 'void scenario() {')
        suffix = '''
int main() {
    try { scenario(); }
    catch (const std::runtime_error&) { std::cout << "failure "; }
    std::cout << published << ' ' << processed.load();
}
'''
        for failed, expected in ((None, '3 3'), ('t2', 'failure -1 1'),
                                 ('t3', 'failure -1 2')):
            variant = code
            if failed:
                marker = '    std::jthread ' + failed
                self.assertIn(marker, variant)
                variant = variant.replace(marker, '    throw std::runtime_error("startup");\n' + marker)
            with tempfile.TemporaryDirectory(prefix='practice-latch-') as tmp:
                executable = Path(tmp) / 'example'
                subprocess.run(['g++', '-std=c++20', '-pthread', '-x', 'c++', '-',
                                '-o', str(executable)],
                               input=prefix + variant + suffix, text=True,
                               capture_output=True, check=True)
                self.assertEqual(subprocess.check_output([str(executable)],
                                                        text=True, timeout=5), expected)

    def test_const_ref_qualified_member_accepts_temporary(self):
        section = next(s for s in self.data[2]['theory'] if s['id'] == 'virtual-edge-cases')
        source = next(b['code'] for b in section['blocks']
                      if b['type'] == 'code' and 'struct Access' in b['code'])
        with tempfile.TemporaryDirectory(prefix='practice-ref-qualifier-') as tmp:
            executable = Path(tmp) / 'example'
            command = ['g++', '-std=c++20', '-x', 'c++', '-', '-o', str(executable)]
            subprocess.run(command, input=source, text=True, capture_output=True, check=True)
            self.assertEqual(subprocess.check_output([str(executable)], text=True), 'ERR')
            invalid = source.replace('// Access{}.edit();', 'Access{}.edit();')
            self.assertNotEqual(subprocess.run(command, input=invalid, text=True,
                                              capture_output=True).returncode, 0)

    def test_constructor_order_listing_is_a_standalone_program(self):
        section = next(s for s in self.data[2]['theory'] if s['id'] == 'ctor-order')
        source = next(b['code'] for b in section['blocks']
                      if b.get('caption') == 'Порядок вызовов')
        with tempfile.TemporaryDirectory(prefix='constructor-order-') as tmp:
            executable = Path(tmp) / 'example'
            result = subprocess.run(
                ['g++', '-std=c++20', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
                 '-x', 'c++', '-', '-o', str(executable)],
                input=source, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(subprocess.check_output([str(executable)], text=True, timeout=5),
                             'Base ctor\nDerived ctor\nDerived dtor\nBase dtor\n')

    def test_snapshot_tasks_reject_a_throwing_metric_contract(self):
        # These are context-dependent examples: provide declarations only and
        # verify that their compile-time condition rejects a throwing copy.
        prefix = '''
#include <vector>
struct Metric {
    int value;
    Metric(const Metric&) noexcept(false);
    Metric(Metric&&) noexcept = default;
    Metric& operator=(const Metric&) noexcept = default;
    Metric& operator=(Metric&&) noexcept = default;
};
std::vector<Metric> collectFrom(const char*);
void logNoThrow(const char*, const char*) noexcept;
void logUnknownFailureNoThrow(const char*) noexcept;
void doPostProcessing(const char*);
void publishSnapshot(const std::vector<Metric>&);
void publishSnapshotNoThrow(const std::vector<Metric>&) noexcept;
'''
        for index in (9, 10):
            task = self.data[6]['tasks'][index]
            with self.subTest(task=task['title']):
                self.assertIn('частичный вклад', task['brief'])
                self.assertIn('std::vector<Metric> metrics = collectFrom(name);', task['code'])
                self.assertIn('is_nothrow_copy_constructible_v<Metric>', task['code'])
                result = subprocess.run(
                    ['g++', '-std=c++20', '-pthread', '-fsyntax-only', '-x', 'c++', '-'],
                    input=prefix + task['code'], text=True, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('static assertion failed', result.stderr)

    def test_counter_layout_examples_support_feature_absence(self):
        blocks = [block['code'] for section in self.data[6]['theory']
                  for block in section['blocks']
                  if block['type'] == 'code' and 'alignas(counter_spacing)' in block['code']]
        self.assertEqual(len(blocks), 2)
        compilers = [tool for tool in ('g++', 'clang++') if shutil.which(tool)]
        self.assertTrue(compilers, 'At least one C++20 compiler is required')
        for compiler in compilers:
            for original in blocks:
                for fallback in (False, True):
                    with self.subTest(compiler=compiler, fallback=fallback,
                                      complete_program='int main' in original):
                        source = original
                        if fallback:
                            source = source.replace(
                                '#if defined(__cpp_lib_hardware_interference_size)',
                                '#undef __cpp_lib_hardware_interference_size\n'
                                '#if defined(__cpp_lib_hardware_interference_size)', 1)
                        flags = [compiler, '-std=c++20', '-pthread', '-Wall',
                                 '-Wextra', '-Wpedantic', '-Werror', '-x', 'c++', '-']
                        with tempfile.TemporaryDirectory(prefix='counter-layout-') as tmp:
                            executable = Path(tmp) / 'example'
                            command = flags + (['-o', str(executable)] if 'int main' in source
                                               else ['-fsyntax-only'])
                            result = subprocess.run(command, input=source, text=True,
                                                    capture_output=True, timeout=30)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            if 'int main' in source:
                                self.assertEqual(subprocess.check_output(
                                    [str(executable)], text=True, timeout=5), '2000')


if __name__ == '__main__':
    unittest.main()
