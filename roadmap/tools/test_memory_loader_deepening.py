"""Execute trusted course examples in owned temporary directories, no root/network.

The wrong-architecture case remains an explicit diagnostic model; this suite
does not install an emulator, change binfmt handlers, or run foreign binaries.
"""
import errno
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def section(number, sid):
    return next(s for s in json.loads((ROOT / f'content/station{number}.json').read_text())['theory']
                if s['id'] == sid)


class MemoryAndLoader(unittest.TestCase):
    def test_embedded_examples_match_downloads(self):
        for number, sid, names in [(3, 'request-memory-arena', ['request_arena.cpp']),
                                   (5, 'loader-before-main', ['loader_probe.cpp', 'loader_value.cpp'])]:
            code = [b['code'].strip() for b in section(number, sid)['blocks'] if b['type'] == 'code']
            for name in names:
                self.assertIn((ROOT / f'examples/station{number}' / name).read_text().strip(), code)

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_checked_library_resets_initial_buffer_after_release(self):
        # N4861 alone did not settle this; the lesson cites LWG 3120 as well.
        source = '''#include <cstddef>
#include <memory_resource>
#include <new>
int main() {
  alignas(std::max_align_t) std::byte buffer[4096];
  std::pmr::monotonic_buffer_resource r(buffer, sizeof buffer, std::pmr::null_memory_resource());
  try {
    (void)r.allocate(3000);
    r.release();
    (void)r.allocate(3000);
  } catch (const std::bad_alloc&) { return 1; }
}
'''
        with tempfile.TemporaryDirectory(prefix='course-arena-reset-') as directory:
            binary = Path(directory) / 'probe'
            build = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    '-x', 'c++', '-', '-o', str(binary)], input=source,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(subprocess.run([str(binary)], timeout=5).returncode, 0)

    @unittest.skipUnless(shutil.which('g++'), 'g++ is required')
    def test_arena_budget_and_reuse(self):
        with tempfile.TemporaryDirectory(prefix='course-arena-') as directory:
            binary = Path(directory) / 'arena'
            source = (ROOT / 'examples/station3/request_arena.cpp').read_text()
            build = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    '-x', 'c++', '-', '-o', str(binary)], input=source,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, 'items=8 sum=28\nbudget exceeded\nitems after failure=8\nnew request items=1\n')

            # Execute the proposed exercise solution, not a dangling-view mutant.
            exercise = source.replace('    {\n        std::pmr::vector<int> ids',
                                      '    std::vector<int> result;\n    {\n        std::pmr::vector<int> ids', 1)
            exercise = exercise.replace('        std::cout << "items="',
                                        '        result.assign(ids.begin(), ids.end());\n        std::cout << "items="', 1)
            exercise = exercise.replace('    arena.release();', '    arena.release();\n    std::cout << "persistent sum=" << std::accumulate(result.begin(), result.end(), 0) << \'\\n\';', 1)
            build = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    '-x', 'c++', '-', '-o', str(binary)], input=exercise,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('persistent sum=28\n', run.stdout)

    @unittest.skipUnless(platform.system() == 'Linux' and shutil.which('g++') and shutil.which('readelf'),
                         'Linux, g++ and readelf are required')
    def test_actual_loader_success_missing_library_and_interpreter(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('LD_')}
        env['LC_ALL'] = 'C'
        with tempfile.TemporaryDirectory(prefix='course-loader-') as directory:
            directory = Path(directory)
            def run(args):
                return subprocess.run([str(x) for x in args], cwd=directory, env=env,
                                      capture_output=True, text=True, timeout=30)
            library = directory / 'libcourse_value.so'
            library_build = run(['g++', '-std=c++20', '-fPIC', '-shared',
                                 ROOT / 'examples/station5/loader_value.cpp',
                                 '-Wl,-soname,libcourse_value.so', '-o', library])
            self.assertEqual(library_build.returncode, 0, library_build.stderr)
            binary = directory / 'loader_probe'
            base = ['g++', '-std=c++20', ROOT / 'examples/station5/loader_probe.cpp',
                    '-L' + str(directory), '-lcourse_value', '-Wl,--enable-new-dtags,-rpath,$ORIGIN']
            build = run(base + ['-o', binary])
            self.assertEqual(build.returncode, 0, build.stderr)
            dynamic = run(['readelf', '-dW', binary])
            self.assertEqual(dynamic.returncode, 0, dynamic.stderr)
            self.assertIn('libcourse_value.so', dynamic.stdout)
            self.assertIn('(RUNPATH)', dynamic.stdout)
            self.assertIn('$ORIGIN', dynamic.stdout)
            good = run([binary])
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout, 'main: 42\n')

            library.rename(directory / 'libcourse_value.hidden')
            missing = run([binary])
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(missing.stdout, '')
            self.assertIn('libcourse_value.so', missing.stderr)
            (directory / 'libcourse_value.hidden').rename(library)
            restored = run([binary])
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(restored.stdout, 'main: 42\n')

            no_interpreter = directory / 'no_interpreter'
            absent = directory / 'absent-course-loader'
            self.assertFalse(absent.exists())
            build = run(base + ['-Wl,--dynamic-linker=' + str(absent), '-o', no_interpreter])
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertTrue(no_interpreter.is_file())
            headers = run(['readelf', '-lW', no_interpreter])
            self.assertIn(str(absent), headers.stdout)
            with self.assertRaises(OSError) as error:
                run([no_interpreter])
            self.assertEqual(error.exception.errno, errno.ENOENT)


if __name__ == '__main__':
    unittest.main()
