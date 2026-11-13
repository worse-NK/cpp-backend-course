"""Portable build entry points and local serving; no GUI or system install."""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_local
import course


def fixture(text=b'fixture'):
    files = {'index.html': b'<!doctype html><title>Fixture</title>',
             'roadmap/assets/test.js': text, 'README.txt': b'Fixture only'}
    manifest = {'format': 1, 'mode': 'offline-browser', 'version': 'a' * 20,
                'stationCount': 21, 'fileCount': len(files) + 1,
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in files.items()}}
    files[build_local.MANIFEST] = (json.dumps(manifest, sort_keys=True) + '\n').encode()
    return files, manifest


class OfflineContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.manifest = build_local.collect()

    def test_all_21_stations_and_runtime_are_offline(self):
        adapter = build_local.desktop_adapter()
        self.assertEqual(self.manifest['stationCount'], 21)
        self.assertEqual(self.manifest['externalRuntimeResources'], [])
        self.assertGreater(adapter.check_local(self.files), 500)
        self.assertEqual(len(self.files), self.manifest['fileCount'])
        _, stations = adapter.publication.collect()
        for data in stations:
            page = self.files['roadmap/' + data['meta']['sourceFile']]
            self.assertIn(b'station-map-joints.css', page)
            self.assertNotIn(b'https://unpkg.com/', page)

    def test_no_electron_ui_profile_api_or_source_tree(self):
        for name in ('desktop-ui.js', 'desktop.css', 'progress.html', 'desktop-meta.json',
                     'desktop-build.json', 'manifest.webmanifest', 'sw.js'):
            self.assertNotIn(name, self.files)
        for name in self.files:
            self.assertNotIn('/content/', name)
            self.assertNotIn('/tools/', name)
            self.assertFalse(name.startswith(('desktop-course/', 'icons/')))
            if name.endswith('.html'):
                self.assertNotIn(b'desktop-ui.js', self.files[name])
                self.assertNotIn(b'courseDesktop', self.files[name])
        self.assertNotIn('README.md', self.files)
        self.assertIn(b'python3 -m http.server 8000 --bind 127.0.0.1', self.files['README.txt'])

    def test_course_code_css_labs_and_licenses_are_preserved(self):
        adapter = build_local.desktop_adapter()
        original, _ = adapter.publication.collect()
        for name, data in original.items():
            if name.endswith(('.js', '.css', '.cpp', '.hpp', '.sql', '.pcap')):
                self.assertEqual(self.files[name], data, name)
        self.assertIn('roadmap/generated/sql-lab-worker.data.js', self.files)
        self.assertIn('roadmap/generated/security-sql-worker.data.js', self.files)
        for name in ('react/LICENSE-react', 'react/LICENSE-react-dom',
                     'fonts/LICENSE-Inter', 'fonts/LICENSE-JetBrainsMono'):
            self.assertIn('roadmap/vendor/desktop/' + name, self.files)
        self.assertIn('roadmap/vendor/sqljs/LICENSE', self.files)


class OutputGuards(unittest.TestCase):
    def test_owned_folder_and_zip_can_be_rebuilt_but_edits_survive(self):
        with tempfile.TemporaryDirectory(prefix='course-local-output-') as temporary:
            output = Path(temporary) / 'site'
            archive = Path(temporary) / build_local.ARCHIVE
            with patch.object(build_local, 'collect', side_effect=lambda: fixture()):
                build_local.write_site(output, archive)
                first = archive.read_bytes()
                build_local.write_site(output, archive)
                self.assertEqual(archive.read_bytes(), first)
                with zipfile.ZipFile(io.BytesIO(first)) as packed:
                    self.assertEqual(set(packed.namelist()),
                                     {'cpp-backend-course-local/' + name for name in fixture()[0]})
                payload, manifest = build_local.read_payload(output)
                self.assertEqual(payload, fixture()[0])
                self.assertEqual(manifest['mode'], 'offline-browser')
            with patch.object(build_local, 'collect', side_effect=lambda: fixture(b'updated')):
                build_local.write_site(output, archive)
                self.assertEqual((output / 'roadmap/assets/test.js').read_bytes(), b'updated')
            archive.write_bytes(b'user archive')
            before = (output / 'index.html').read_bytes()
            with patch.object(build_local, 'collect', side_effect=lambda: fixture(b'newer')):
                with self.assertRaisesRegex(ValueError, 'Unmanaged or edited local ZIP'):
                    build_local.write_site(output, archive)
            self.assertEqual(archive.read_bytes(), b'user archive')
            self.assertEqual((output / 'index.html').read_bytes(), before)
            (output / 'roadmap/assets/test.js').write_bytes(b'user edit')
            with patch.object(build_local, 'collect', side_effect=lambda: fixture()):
                with self.assertRaisesRegex(ValueError, 'Manual changes'):
                    build_local.write_site(output)
            self.assertEqual((output / 'roadmap/assets/test.js').read_bytes(), b'user edit')

    def test_unmanaged_output_paths_extra_files_and_symlinks_are_rejected(self):
        for destination in (build_local.ROOT, build_local.ROOT.parent,
                            build_local.ROOT / 'roadmap/generated/local',
                            build_local.ROOT / 'desktop-course/new'):
            with self.assertRaises(ValueError):
                build_local.write_site(destination)
        with tempfile.TemporaryDirectory(prefix='course-local-guard-') as temporary:
            output = Path(temporary) / 'site'
            with patch.object(build_local, 'collect', side_effect=lambda: fixture()):
                build_local.write_site(output)
                (output / 'private.env').write_bytes(b'do not serve or overwrite')
                with self.assertRaisesRegex(ValueError, 'Unmanaged'):
                    build_local.write_site(output)
                (output / 'private.env').unlink()
                (output / 'link').symlink_to(output / 'index.html')
                with self.assertRaisesRegex(ValueError, 'Symlinks'):
                    build_local.read_payload(output)
            for unsafe in ('../secret', '/secret', 'a//b', 'a/./b', 'a\\b', '%2e%2e/a', 'a\x00'):
                self.assertFalse(build_local.safe_name(unsafe), unsafe)

    def test_manifest_path_tampering_is_rejected_before_reading_outside(self):
        with tempfile.TemporaryDirectory(prefix='course-local-manifest-') as temporary:
            output = Path(temporary) / 'site'
            with patch.object(build_local, 'collect', side_effect=lambda: fixture()):
                build_local.write_site(output)
            manifest = json.loads((output / build_local.MANIFEST).read_text())
            manifest['files']['../private.txt'] = {'bytes': 1, 'sha256': '0' * 64}
            manifest['fileCount'] += 1
            (output / build_local.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                build_local.read_payload(output)


class Serving(unittest.TestCase):
    def test_only_canonical_payload_paths_are_accepted(self):
        self.assertEqual(course.request_name('/'), 'index.html')
        self.assertEqual(course.request_name('/roadmap/index.html?v=abc'), 'roadmap/index.html')
        for path in ('/../private', '/%2e%2e/private', '/%252e%252e/private',
                     '/roadmap/./a', '/a\\b', '//example.invalid/a', 'https://example.invalid/a',
                     '/%00x', '/a//b', 'index.html'):
            self.assertIsNone(course.request_name(path), path)

    def test_loopback_snapshot_get_head_and_denied_paths(self):
        payload, _ = fixture()
        try:
            server = course.create_server(payload, 0)
        except PermissionError as error:
            self.skipTest('Local sockets unavailable: ' + str(error))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            connection.request('GET', '/')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), payload['index.html'])
            self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
            connection.request('HEAD', '/roadmap/assets/test.js?v=123')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'')
            self.assertIn('javascript', response.getheader('Content-Type'))
            for path in ('/.git/config', '/private.env', '/roadmap/', '/%2e%2e/private', '/local-note.txt'):
                connection.request('GET', path)
                response = connection.getresponse()
                self.assertEqual(response.status, 404, path)
                response.read()
            connection.request('GET', '/', headers={'Host': 'attacker.invalid'})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class Entrypoints(unittest.TestCase):
    def test_help_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory(prefix='course-cli-cwd-') as temporary:
            result = subprocess.run([sys.executable, str(course.ROOT / 'tools/course.py'), '--help'],
                                    cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ('web', 'local', 'serve', 'desktop', 'deb', 'check'):
            self.assertIn(command, result.stdout)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                course.parser().parse_args(['serve', '--port', '0'])

    def test_existing_package_is_refused_before_a_network_fetch(self):
        with tempfile.TemporaryDirectory(prefix='course-deb-existing-') as temporary:
            metadata = json.loads((course.DESKTOP / 'app/package.json').read_text())
            target = Path(temporary) / ('cpp-backend-course-desktop_' + metadata['version'] + '_amd64.deb')
            target.write_bytes(b'existing release')
            args = course.parser().parse_args(['deb', '--output', temporary])
            with patch.object(course.sys, 'platform', 'linux'), patch.object(course.platform, 'machine', return_value='x86_64'), patch.object(course.shutil, 'which', return_value='/fixture/dpkg-deb'):
                with self.assertRaisesRegex(ValueError, 'Package already exists'):
                    course.build_deb_command(args)
            self.assertEqual(target.read_bytes(), b'existing release')

    def test_no_download_flag_fails_cleanly_for_a_missing_runtime(self):
        with tempfile.TemporaryDirectory(prefix='course-deb-offline-') as temporary:
            args = course.parser().parse_args(['deb', '--output', str(Path(temporary) / 'packages'),
                '--runtime', str(Path(temporary) / 'missing-runtime'), '--no-download'])
            with patch.object(course.sys, 'platform', 'linux'), patch.object(course.platform, 'machine', return_value='x86_64'), patch.object(course.shutil, 'which', return_value='/fixture/dpkg-deb'):
                with self.assertRaisesRegex(ValueError, 'runtime is missing'):
                    course.build_deb_command(args)
            self.assertFalse((Path(temporary) / 'packages').exists())

    def test_check_is_scoped_to_focused_python_suites(self):
        with patch.object(course.subprocess, 'run') as execute, contextlib.redirect_stdout(io.StringIO()):
            course.run_checks()
        self.assertEqual(execute.call_count, 4)
        self.assertTrue(all(call.kwargs.get('check') for call in execute.call_args_list))
        commands = ' '.join(' '.join(call.args[0]) for call in execute.call_args_list)
        self.assertNotIn('sudo', commands)
        self.assertNotIn('test_browser', commands)


if __name__ == '__main__':
    unittest.main(verbosity=2)
