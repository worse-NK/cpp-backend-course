"""Public source inventory and non-destructive repository sync regressions."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

import build_publication as publication
import sync_repository as repository


class RepositoryInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = repository.collect_repository_files()

    def test_editable_station_and_checkpoint_sources_are_complete(self):
        stations = {name for name in self.files
                    if name.startswith('roadmap/content/station') and name.endswith('.json')}
        checkpoints = {name for name in self.files
                       if name.startswith('roadmap/content/checkpoints/station')
                       and name.endswith('.json')}
        expected={'roadmap/content/'+p.name
                  for p in (publication.ROOT/'content').glob('station*.json')}
        self.assertEqual(stations, expected)
        self.assertTrue({'roadmap/content/station'+str(i)+'.json'
                         for i in range(11,15)} <= stations)
        self.assertEqual(checkpoints, {
            name.replace('roadmap/content/', 'roadmap/content/checkpoints/', 1)
            for name in stations
        })
        for name in ('cheatsheet.json', 'glossary.json', 'visual-labs.json', 'cpp-examples.json',
                     'service-workshop/route.json', 'service-workshop/start.html',
                     'service-workshop/release.html'):
            self.assertTrue('roadmap/content/' + name in self.files, name)

    def test_build_inputs_and_validation_tools_are_included(self):
        for name in ('roadmap/assets/sql-lab-worker.js',
                     'roadmap/vendor/sqljs/sql-asm.js',
                     'roadmap/vendor/sqljs/LICENSE',
                     'roadmap/vendor/sqljs/README.md',
                     'README.md',
                     'roadmap/tools/build_publication.py',
                     'roadmap/tools/build_stations.py', 'roadmap/tools/cpp_examples.py',
                     'roadmap/tools/course_theme.py',
                     'roadmap/tools/build_sql_lab.py',
                     'roadmap/tools/checkpoint_data.py',
                     'roadmap/tools/validate_materials.py',
                     'roadmap/tools/test_publication.py',
                     'roadmap/tools/sync_repository.py',
                     'roadmap/tools/test_repository_sync.py'):
            self.assertTrue(name in self.files, 'Missing repository source: ' + name)
            self.assertIsInstance(self.files[name], bytes)
        self.assertIn('tools/course.py', self.files['README.md'].decode('utf-8'))
        self.assertIn('docs/BUILDING.md', self.files['README.md'].decode('utf-8'))

    def test_desktop_build_inputs_and_pinned_vendor_assets_are_complete(self):
        for name in repository.DESKTOP_SOURCES:
            target = 'desktop-course/' + name
            self.assertIn(target, self.files)
            self.assertEqual(self.files[target], (publication.ROOT.parent / target).read_bytes())
        for size in repository.ICON_SIZES:
            self.assertTrue(self.files[f'desktop-course/icons/app-{size}.png'].startswith(b'\x89PNG'))
        lock = json.loads(self.files['desktop-course/vendor/ORIGIN.json'])
        for name, expected in lock['files'].items():
            with self.subTest(vendor=name):
                self.assertEqual(hashlib.sha256(self.files['desktop-course/vendor/' + name]).hexdigest(), expected)
        self.assertNotIn('desktop-course/icons/contact-sheet.png', self.files)
        self.assertFalse(any(name.startswith(('desktop-course/release/', 'desktop-course/.toolchain/'))
                             for name in self.files))

    def test_repository_docs_and_entrypoints_are_not_web_distribution_docs(self):
        for name in repository.PROJECT_SOURCES:
            self.assertIn(name, self.files)
            self.assertEqual(self.files[name], (publication.ROOT.parent / name).read_bytes())
        public_files, _ = publication.collect()
        self.assertEqual(public_files['README.md'], publication.PUBLIC_README.encode())
        self.assertEqual(self.files['README.md'], (publication.ROOT.parent / 'README.md').read_bytes())
        self.assertNotEqual(self.files['README.md'], public_files['README.md'])

    def test_private_reports_and_generated_caches_are_excluded(self):
        for name in self.files:
            parts = Path(name).parts
            self.assertFalse(set(parts) & {'.git', '.aws', '.codex', '.agents',
                                          '__pycache__', 'node_modules', '.toolchain',
                                          'release', 'backups', 'userData'})
            self.assertNotIn('REVIEW', name)
            self.assertNotIn('CHECKLIST', name)
            self.assertNotIn('PLAN.md', name)
            self.assertFalse(name.endswith(('.pyc', '.pyo', '.docx', '.zip', '.deb')))
            self.assertNotIn('course-completion-', name)
            self.assertNotIn('network-lab-acceptance-', name)
            self.assertNotIn('publication-manifest.json', name)
        self.assertTrue('index.html' in self.files)
        self.assertTrue('roadmap/cpp_backend_roadmap.html' in self.files)

    def test_cpp_and_cmake_regression_fixtures_are_complete(self):
        fixtures = {
            'build_example/CMakeLists.txt',
            'build_example/include/core.hpp',
            'build_example/src/core.cpp',
            'build_example/src/main.cpp',
            'build_example/tests/core_test.cpp',
            'installed_consumer/CMakeLists.txt',
            'installed_consumer/main.cpp',
            'odr_example/left.cpp',
            'odr_example/main.cpp',
            'odr_example/math.hpp',
            'pimpl_example/client.cpp',
            'pimpl_example/client.hpp',
            'pimpl_example/main.cpp',
        }
        names = {name for name in self.files if name.startswith('roadmap/tests/')}
        self.assertEqual(names, {'roadmap/tests/' + name for name in fixtures})
        for name in names:
            self.assertIsInstance(self.files[name], bytes)

    def test_deployment_remains_source_free(self):
        files, _ = publication.collect()
        for name in files:
            self.assertFalse(set(Path(name).parts) & {'content', 'tools', 'tests', '__pycache__'})
        self.assertTrue('roadmap/content/station0.json' in self.files)
        self.assertFalse('roadmap/content/station0.json' in files)

    @unittest.skipUnless(shutil.which('git'), 'requires Git')
    def test_reviewed_tcp_captures_are_not_silently_ignored(self):
        captures = [
            'roadmap/examples/tcp-observation/captures/' + name
            for name in ('baseline.pcap', 'delay.pcap', 'loss.pcap', 'slow-reader.pcap')
        ]
        for name in captures:
            self.assertIn(name, self.files)
        with tempfile.TemporaryDirectory(prefix='course-capture-ignore-') as work:
            destination = Path(work)
            subprocess.run(['git', 'init', '-q', str(destination)], check=True)
            (destination / '.gitignore').write_bytes(self.files['.gitignore'])
            result = subprocess.run(
                ['git', '-C', str(destination), 'check-ignore', '--no-index', '--stdin'],
                input='\n'.join(captures).encode() + b'\n',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 1,
                             'Reviewed captures ignored by Git: ' + result.stdout.decode())
            self.assertEqual(result.stdout, b'')


class RepositorySourceSafety(unittest.TestCase):
    def fixture(self, project):
        names = {'desktop-course/' + name for name in repository.DESKTOP_SOURCES}
        names.update(f'desktop-course/icons/app-{size}.png' for size in repository.ICON_SIZES)
        for name in names:
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'public source fixture\n')
        files = {'react/react.production.min.js': b'/* pinned fixture */\n',
                 'react/LICENSE-react': b'Fixture license\n',
                 'fonts/font-0.ttf': b'font-fixture'}
        for name, data in files.items():
            path = project / 'desktop-course/vendor' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        lock = project / 'desktop-course/vendor/ORIGIN.json'
        lock.write_text(json.dumps({'format': 1, 'files': {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        }}))
        return lock, files

    def test_source_reader_rejects_unsafe_paths_and_missing_inputs(self):
        with tempfile.TemporaryDirectory(prefix='course-project-sources-') as work:
            project = Path(work)
            for name in ('../private.txt', '/etc/passwd', '.git/config',
                         'a/../private.txt', 'a\\private.txt', './readme.txt', ''):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    repository.project_source_bytes(project, name)
            with self.assertRaisesRegex(ValueError, 'Required repository source is missing'):
                repository.project_source_bytes(project, 'README.md')

    def test_pinned_sources_exclude_neighboring_runtime_and_private_files(self):
        with tempfile.TemporaryDirectory(prefix='course-desktop-sources-') as work:
            project = Path(work)
            self.fixture(project)
            for name in ('release/personal.json', 'release/backups/profile.tar.gz',
                         '.toolchain/electron', 'app/.env', 'vendor/credentials.json',
                         'icons/contact-sheet.png'):
                path = project / 'desktop-course' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'not a public source')
            files = repository.collect_desktop_sources(project)
            self.assertEqual(set(files),
                {'desktop-course/' + name for name in repository.DESKTOP_SOURCES}
                | {f'desktop-course/icons/app-{size}.png' for size in repository.ICON_SIZES}
                | {'desktop-course/vendor/' + name for name in (
                    'ORIGIN.json', 'react/react.production.min.js', 'react/LICENSE-react', 'fonts/font-0.ttf')})

    def test_vendor_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='course-desktop-vendor-hash-') as work:
            project = Path(work)
            self.fixture(project)
            (project / 'desktop-course/vendor/react/react.production.min.js').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Desktop vendor hash mismatch'):
                repository.collect_desktop_sources(project)

    def test_vendor_lock_cannot_select_private_files_or_traversal_paths(self):
        for name in ('../app/main.cjs', '/etc/passwd', 'react/../private.js',
                     'fonts/.env', 'fonts/credentials.json', 'other/file.js',
                     'react\\private.js', './react/file.js'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='course-vendor-path-') as work:
                project = Path(work)
                lock, _ = self.fixture(project)
                value = json.loads(lock.read_text())
                value['files'][name] = '0' * 64
                lock.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'Unsafe desktop vendor entry'):
                    repository.collect_desktop_sources(project)

    def test_vendor_lock_format_and_digest_are_validated(self):
        for value in ([], {'format': 2, 'files': {}}, {'format': 1, 'files': {}},
                      {'format': 1, 'files': []},
                      {'format': 1, 'files': {'react/file.js': 'not-a-sha256'}}):
            with self.subTest(value=value), tempfile.TemporaryDirectory(prefix='course-vendor-format-') as work:
                project = Path(work)
                lock, _ = self.fixture(project)
                lock.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    repository.collect_desktop_sources(project)

    def test_source_reader_refuses_file_parent_and_lock_symlinks(self):
        for target in ('desktop-course/app/main.cjs', 'desktop-course/vendor/ORIGIN.json',
                       'desktop-course/vendor/react'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='course-source-link-') as work:
                project = Path(work)
                self.fixture(project)
                path = project / target
                moved = project / ('outside-' + path.name)
                path.rename(moved)
                try:
                    path.symlink_to(moved, target_is_directory=moved.is_dir())
                except (NotImplementedError, OSError) as error:
                    self.skipTest('symlinks unavailable: ' + str(error))
                with self.assertRaisesRegex(ValueError, 'Symlink'):
                    repository.collect_desktop_sources(project)

    def test_source_privacy_gate_keeps_header_only_tests_but_rejects_material(self):
        harmless = {'test.py': b'header = "-----BEGIN ' + b'OPENSSH PRIVATE KEY-----"\n'}
        repository.check_repository_source_privacy(harmless)
        for data in ((b'ghp_' + b'A' * 36),
                     (b'github_pat_' + b'A' * 50),
                     (b'AKIA' + b'A' * 16),
                     (b'-----BEGIN ' + b'PRIVATE KEY-----\n' + b'A' * 128
                      + b'\n-----END ' + b'PRIVATE KEY-----'),
                     (b'-----BEGIN ' + b'PRIVATE KEY-----\\n' + b'A' * 128
                      + b'\\n-----END ' + b'PRIVATE KEY-----'),
                     b'SQLite format 3\0private fixture'):
            with self.subTest(length=len(data)), self.assertRaisesRegex(ValueError, 'Potential credential or private database'):
                repository.check_repository_source_privacy({'fixture.txt': data})
        with self.assertRaisesRegex(ValueError, 'Potential private workspace path'):
            repository.check_repository_source_privacy({'fixture.txt': str(publication.ROOT.parent).encode()})


@unittest.skipUnless(shutil.which('git'), 'requires Git')
class RepositorySync(unittest.TestCase):
    def git(self, destination, *arguments):
        result = subprocess.run(
            ['git', '-C', str(destination), '-c',
             'core.hooksPath=' + str(destination / '.git' / 'course-empty-hooks'),
             '-c', 'commit.gpgsign=false', '-c', 'user.name=Course Sync Test',
             '-c', 'user.email=course-sync-test@example.invalid', *arguments],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        return result.stdout

    def checkout(self, parent, files):
        destination = parent / 'checkout'
        destination.mkdir()
        self.git(destination, 'init', '-q')
        for name, content in files.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.git(destination, 'add', '--all')
        self.git(destination, 'commit', '--quiet', '--allow-empty', '-m', 'Fixture')
        return destination

    def symlink(self, target, link, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest('symlinks unavailable: ' + str(error))

    def test_clean_updates_new_files_and_identical_noop_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory(prefix='course-repository-sync-') as work:
            destination = self.checkout(Path(work), {
                'tracked.txt': b'old\n', 'obsolete-but-user-owned.txt': b'keep tracked\n',
            })
            unrelated = destination / 'notes.txt'
            unrelated.write_bytes(b'keep untracked\n')
            files = {'tracked.txt': b'new\n', 'nested/new.txt': b'new source\n'}
            self.assertEqual(repository.sync_repository(destination, files), 2)
            self.assertEqual((destination / 'tracked.txt').read_bytes(), b'new\n')
            self.assertEqual((destination / 'nested/new.txt').read_bytes(), b'new source\n')
            self.assertEqual(repository.sync_repository(destination, files), 0)
            self.assertEqual(unrelated.read_bytes(), b'keep untracked\n')
            self.assertEqual((destination / 'obsolete-but-user-owned.txt').read_bytes(),
                             b'keep tracked\n')
            self.assertEqual(self.git(destination, 'show', ':tracked.txt'), b'old\n')

    def test_every_conflict_is_validated_before_any_write(self):
        for conflict in ('unstaged', 'staged', 'untracked'):
            with self.subTest(conflict=conflict):
                with tempfile.TemporaryDirectory(prefix='course-repository-conflict-') as work:
                    initial = {'a-clean.txt': b'original\n'}
                    if conflict != 'untracked':
                        initial['z-conflict.txt'] = b'committed\n'
                    destination = self.checkout(Path(work), initial)
                    target = destination / 'z-conflict.txt'
                    target.write_bytes(b'user changes\n')
                    if conflict == 'staged':
                        self.git(destination, 'add', '--', 'z-conflict.txt')
                    before_status = self.git(destination, 'status', '--porcelain=v1', '-z')
                    before_index = self.git(destination, 'ls-files', '--stage', '-z')
                    files = {'a-clean.txt': b'would change\n',
                             'new/source.txt': b'would create\n',
                             'z-conflict.txt': b'generated replacement\n'}
                    with self.assertRaises(ValueError):
                        repository.sync_repository(destination, files)
                    self.assertEqual((destination / 'a-clean.txt').read_bytes(), b'original\n')
                    self.assertEqual(target.read_bytes(), b'user changes\n')
                    self.assertFalse((destination / 'new').exists())
                    self.assertEqual(self.git(destination, 'status', '--porcelain=v1', '-z'),
                                     before_status)
                    self.assertEqual(self.git(destination, 'ls-files', '--stage', '-z'),
                                     before_index)

    def test_identical_dirty_staged_and_untracked_files_are_noops(self):
        with tempfile.TemporaryDirectory(prefix='course-repository-identical-') as work:
            destination = self.checkout(Path(work), {
                'dirty.txt': b'original\n', 'staged.txt': b'original\n',
            })
            files = {'dirty.txt': b'current\n', 'staged.txt': b'current\n',
                     'untracked.txt': b'current\n'}
            for name, content in files.items():
                (destination / name).write_bytes(content)
            self.git(destination, 'add', '--', 'staged.txt')
            before_status = self.git(destination, 'status', '--porcelain=v1', '-z')
            before_index = self.git(destination, 'ls-files', '--stage', '-z')
            self.assertEqual(repository.sync_repository(destination, files), 0)
            self.assertEqual(self.git(destination, 'status', '--porcelain=v1', '-z'), before_status)
            self.assertEqual(self.git(destination, 'ls-files', '--stage', '-z'), before_index)

    def test_index_optimization_flags_do_not_hide_conflicting_user_edits(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                with tempfile.TemporaryDirectory(prefix='course-repository-index-flags-') as work:
                    destination = self.checkout(Path(work), {
                        'a-clean.txt': b'original\n', 'z-conflict.txt': b'committed\n',
                    })
                    self.git(destination, 'update-index', flag, '--', 'z-conflict.txt')
                    (destination / 'z-conflict.txt').write_bytes(b'user changes\n')
                    before_flags = self.git(destination, 'ls-files', '-v', '-z')
                    with self.assertRaises(ValueError):
                        repository.sync_repository(destination, {
                            'a-clean.txt': b'would change\n',
                            'z-conflict.txt': b'generated replacement\n',
                        })
                    self.assertEqual((destination / 'a-clean.txt').read_bytes(), b'original\n')
                    self.assertEqual((destination / 'z-conflict.txt').read_bytes(), b'user changes\n')
                    self.assertEqual(self.git(destination, 'ls-files', '-v', '-z'), before_flags)

    def test_conflicting_file_and_parent_targets_are_refused_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix='course-repository-parent-target-') as work:
            destination = self.checkout(Path(work), {'a-clean.txt': b'original\n'})
            with self.assertRaises(ValueError):
                repository.sync_repository(destination, {
                    'a-clean.txt': b'would change\n',
                    'new': b'would become a file\n',
                    'new/child.txt': b'cannot have a file as its parent\n',
                })
            self.assertEqual((destination / 'a-clean.txt').read_bytes(), b'original\n')
            self.assertFalse((destination / 'new').exists())

    def test_requires_existing_git_checkout(self):
        with tempfile.TemporaryDirectory(prefix='course-repository-required-') as work:
            root = Path(work)
            existing = root / 'plain-directory'
            existing.mkdir()
            for destination in (existing, root / 'missing-directory'):
                with self.subTest(destination=destination.name):
                    with self.assertRaises(ValueError):
                        repository.sync_repository(destination, {'new.txt': b'new\n'})
                    self.assertFalse((destination / 'new.txt').exists())
            self.assertFalse((root / 'missing-directory').exists())

    def test_symlink_destination_and_ancestor_are_refused(self):
        with tempfile.TemporaryDirectory(prefix='course-repository-links-') as work:
            root = Path(work)
            destination = self.checkout(root, {'tracked.txt': b'original\n'})
            linked_checkout = root / 'linked-checkout'
            self.symlink(destination, linked_checkout, directory=True)
            linked_parent = root / 'linked-parent'
            self.symlink(root, linked_parent, directory=True)
            for candidate in (linked_checkout, linked_parent / destination.name):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        repository.sync_repository(candidate, {'tracked.txt': b'changed\n'})
            self.assertEqual((destination / 'tracked.txt').read_bytes(), b'original\n')

    def test_symlink_targets_and_parents_are_refused_before_writing(self):
        for kind in ('target', 'dangling-target', 'parent'):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory(prefix='course-repository-target-link-') as work:
                    root = Path(work)
                    destination = self.checkout(root, {'a-clean.txt': b'original\n'})
                    outside = root / 'outside'
                    outside.mkdir()
                    (outside / 'file.txt').write_bytes(b'outside must stay\n')
                    if kind == 'parent':
                        self.symlink(outside, destination / 'linked', directory=True)
                        name = 'linked/file.txt'
                    else:
                        target = outside / ('missing.txt' if kind == 'dangling-target' else 'file.txt')
                        self.symlink(target, destination / 'z-linked.txt')
                        name = 'z-linked.txt'
                    with self.assertRaises(ValueError):
                        repository.sync_repository(destination, {
                            'a-clean.txt': b'would change\n', name: b'generated\n',
                        })
                    self.assertEqual((destination / 'a-clean.txt').read_bytes(), b'original\n')
                    self.assertEqual((outside / 'file.txt').read_bytes(), b'outside must stay\n')
                    self.assertFalse((outside / 'missing.txt').exists())


if __name__ == '__main__':
    unittest.main()
