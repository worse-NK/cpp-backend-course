"""Public source inventory and non-destructive repository sync regressions."""
from pathlib import Path
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
        self.assertEqual(len(stations), 15)
        self.assertEqual(checkpoints, {
            name.replace('roadmap/content/', 'roadmap/content/checkpoints/', 1)
            for name in stations
        })
        for name in ('cheatsheet.json', 'glossary.json', 'visual-labs.json',
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
                     'roadmap/tools/build_stations.py',
                     'roadmap/tools/build_sql_lab.py',
                     'roadmap/tools/checkpoint_data.py',
                     'roadmap/tools/validate_materials.py',
                     'roadmap/tools/test_publication.py',
                     'roadmap/tools/sync_repository.py',
                     'roadmap/tools/test_repository_sync.py'):
            self.assertTrue(name in self.files, 'Missing repository source: ' + name)
            self.assertIsInstance(self.files[name], bytes)
        self.assertIn('Редактирование и сборка', self.files['README.md'].decode('utf-8'))

    def test_private_reports_and_generated_caches_are_excluded(self):
        for name in self.files:
            parts = Path(name).parts
            self.assertFalse(set(parts) & {'.git', '.aws', '.codex', '.agents',
                                          '__pycache__', 'node_modules'})
            self.assertNotIn('REVIEW', name)
            self.assertNotIn('CHECKLIST', name)
            self.assertNotIn('PLAN.md', name)
            self.assertFalse(name.endswith(('.pyc', '.pyo', '.docx', '.zip', '.deb')))
            self.assertNotIn('course-completion-', name)
            self.assertNotIn('network-lab-acceptance-', name)
            self.assertNotIn('publication-manifest.json', name)
        self.assertTrue('index.html' in self.files)
        self.assertTrue('roadmap/cpp_backend_roadmap.html' in self.files)

    def test_deployment_remains_source_free(self):
        files, _ = publication.collect()
        for name in files:
            self.assertFalse(set(Path(name).parts) & {'content', 'tools', '__pycache__'})
        self.assertTrue('roadmap/content/station0.json' in self.files)
        self.assertFalse('roadmap/content/station0.json' in files)


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
