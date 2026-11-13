"""Secret-scanner boundaries; synthetic credentials exist only in temp fixtures."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('course_secret_check', Path(__file__).with_name('check_secrets.py'))
secrets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(secrets)


class SecretCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='course-secrets-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_binary_hash_and_symlink_are_checked_before_execution(self):
        binary = self.root / 'gitleaks'
        binary.write_bytes(b'fixture')
        with self.assertRaises(ValueError):
            secrets.checked_binary(binary)
        with patch.object(secrets, 'BINARY_SHA256', secrets.sha256(b'fixture')):
            self.assertEqual(secrets.checked_binary(binary), binary)
            link = self.root / 'link'
            link.symlink_to(binary)
            with self.assertRaises(ValueError):
                secrets.checked_binary(link)

    def packed(self, regular=True):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            entry = tarfile.TarInfo('gitleaks')
            if regular:
                entry.size = len(b'fixture')
                archive.addfile(entry, io.BytesIO(b'fixture'))
            else:
                entry.type = tarfile.SYMTYPE
                entry.linkname = '/outside'
                archive.addfile(entry)
        return output.getvalue()

    def test_download_hash_and_member_type_are_checked(self):
        for regular in (True, False):
            packed = self.packed(regular)
            output = self.root / str(regular)
            with patch.object(secrets, 'urlopen', return_value=io.BytesIO(packed)), \
                    patch.object(secrets.platform, 'system', return_value='Linux'), \
                    patch.object(secrets.platform, 'machine', return_value='x86_64'), \
                    patch.object(secrets, 'ARCHIVE_SHA256', secrets.sha256(packed)), \
                    patch.object(secrets, 'BINARY_SHA256', secrets.sha256(b'fixture')):
                if regular:
                    binary = secrets.fetch_binary(output)
                    self.assertEqual(binary.read_bytes(), b'fixture')
                    self.assertTrue(binary.stat().st_mode & stat.S_IXUSR)
                else:
                    with self.assertRaises(ValueError):
                        secrets.fetch_binary(output)

    def test_wrong_download_digest_leaves_no_executable(self):
        with patch.object(secrets, 'urlopen', return_value=io.BytesIO(b'wrong bytes')), \
                self.assertRaises(ValueError):
            secrets.fetch_binary(self.root)
        self.assertFalse((self.root / ('gitleaks-' + secrets.VERSION)).exists())

    def test_snapshot_rejects_escape_and_symlinks(self):
        destination = self.root / 'snapshot'
        destination.mkdir()
        for name in (b'../outside', b'.git/config', b'/outside'):
            with self.subTest(name=name), patch.object(secrets, 'git', return_value=name + b'\0'), self.assertRaises(ValueError):
                secrets.snapshot(self.root, destination)
        source = self.root / 'link'
        source.symlink_to(destination)
        with patch.object(secrets, 'git', return_value=b'link\0'), self.assertRaises(ValueError):
            secrets.snapshot(self.root, destination)

    def test_snapshot_uses_tracked_and_nonignored_files_only(self):
        repository = self.root / 'repository'
        repository.mkdir()
        (repository / 'ordinary.txt').write_text('ordinary')
        (repository / 'not-selected.txt').write_text('not selected')
        destination = self.root / 'snapshot'
        destination.mkdir()
        with patch.object(secrets, 'git', return_value=b'ordinary.txt\0deleted.txt\0') as inspect:
            self.assertEqual(secrets.snapshot(repository, destination), 1)
        self.assertEqual(inspect.call_args.args[1:], ('ls-files', '--cached', '--others', '--exclude-standard', '-z'))
        self.assertEqual({path.name for path in destination.iterdir()}, {'ordinary.txt'})

    def test_reviewed_exception_requires_exact_fixture_bytes_and_location(self):
        path = self.root / secrets.FIXTURE
        path.parent.mkdir(parents=True)
        path.write_bytes(b'fixture')
        finding = {'RuleID': 'private-key', 'StartLine': 368, 'Commit': ''}
        self.assertFalse(secrets.reviewed_header_only(finding, secrets.FIXTURE, self.root, 'dir'))
        with patch.object(secrets, 'FIXTURE_CURRENT_SHA256', secrets.sha256(b'fixture')):
            self.assertTrue(secrets.reviewed_header_only(finding, secrets.FIXTURE, self.root, 'dir'))
            self.assertFalse(secrets.reviewed_header_only(finding, 'another.py', self.root, 'dir'))
            self.assertFalse(secrets.reviewed_header_only({**finding, 'StartLine': 369}, secrets.FIXTURE, self.root, 'dir'))
            self.assertFalse(secrets.reviewed_header_only({**finding, 'RuleID': 'other'}, secrets.FIXTURE, self.root, 'dir'))
        historical = {'RuleID': 'private-key', 'StartLine': 357, 'Commit': secrets.FIXTURE_COMMIT}
        with patch.object(secrets, 'git', return_value=b'fixture'), \
                patch.object(secrets, 'FIXTURE_HISTORY_SHA256', secrets.sha256(b'fixture')):
            self.assertTrue(secrets.reviewed_header_only(historical, secrets.FIXTURE, self.root, 'git'))
            self.assertFalse(secrets.reviewed_header_only({**historical, 'Commit': 'b' * 40}, secrets.FIXTURE, self.root, 'git'))

    def test_scanner_is_redacted_and_cannot_inherit_ignore_configuration(self):
        def execute(command, **kwargs):
            report = Path(command[command.index('--report-path') + 1])
            report.write_text('[]')
            self.assertEqual(kwargs['stdout'], secrets.subprocess.DEVNULL)
            self.assertEqual(kwargs['stderr'], secrets.subprocess.DEVNULL)
            self.assertNotIn('GITLEAKS_CONFIG', kwargs['env'])
            self.assertIn('--redact=100', command)
            self.assertIn('--ignore-gitleaks-allow', command)
            self.assertIn('--log-opts=--all --full-history', command)
            return type('Result', (), {'returncode': 0})()
        with patch.dict(os.environ, {'GITLEAKS_CONFIG': 'untrusted'}), \
                patch.object(secrets.subprocess, 'run', side_effect=execute):
            self.assertEqual(secrets.run_scanner(Path('/fixture/gitleaks'), 'git', self.root, self.root), [])

    def test_scanner_failure_is_not_a_clean_result(self):
        result = type('Result', (), {'returncode': 2})()
        with patch.object(secrets.subprocess, 'run', return_value=result), self.assertRaises(ValueError):
            secrets.run_scanner(Path('/fixture/gitleaks'), 'git', self.root, self.root)

    def test_shallow_history_is_refused(self):
        with patch.object(secrets, 'git', side_effect=[str(self.root).encode(), b'true']), self.assertRaises(ValueError):
            secrets.scan(self.root, Path('/fixture/gitleaks'))

    def test_failure_message_never_prints_raw_exception_or_secret(self):
        output = io.StringIO()
        with patch.object(secrets, 'checked_binary', side_effect=ValueError('private fixture diagnostic')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(secrets.main(['--binary', '/fixture/gitleaks']), 2)
        self.assertNotIn('private fixture diagnostic', output.getvalue())

    def test_workflow_is_read_only_and_fetches_complete_history(self):
        workflow = (secrets.ROOT / '.github/workflows/secret-scan.yml').read_text()
        self.assertIn('permissions:\n  contents: read', workflow)
        self.assertIn('  push:', workflow)
        self.assertIn('  pull_request:', workflow)
        self.assertIn('fetch-depth: 0', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('pull_request_target', workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('${{ secrets.', workflow)
        self.assertIn('--self-test', workflow)


if __name__ == '__main__':
    unittest.main()
