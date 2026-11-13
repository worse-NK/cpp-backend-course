#!/usr/bin/env python3
"""Packaging invariants; fixtures are not executable apps or system installs."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load('package_desktop_test', ROOT / 'build_deb.py')
fetch = load('fetch_desktop_test', ROOT / 'fetch_runtime.py')


class Fixture:
    def __init__(self, root):
        self.root = root
        self.site, self.runtime, self.app, self.icons = [root / name for name in ('site', 'runtime', 'app', 'icons')]
        for directory in (self.site, self.runtime, self.app, self.icons):
            directory.mkdir()
        self.metadata = {'format': 1, 'version': '0123456789abcdef1234', 'files': {}}
        for name, data in {'index.html': b'<!doctype html><title>Fixture</title>', 'hello.js': b'1;'}.items():
            (self.site / name).write_bytes(data)
            self.metadata['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (self.site / 'desktop-build.json').write_text(json.dumps(self.metadata))
        runtime_files = {'electron': b'\x7fELF-fixture', 'chrome-sandbox': b'fixture-not-executable',
                         'LICENSE': b'fixture-license', 'LICENSES.chromium.html': b'fixture-notices'}
        self.runtime_meta = {'version': '45.2.3', 'archive_sha256': fetch.ARCHIVE_SHA256, 'files': {}}
        for name, data in runtime_files.items():
            (self.runtime / name).write_bytes(data)
            self.runtime_meta['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                                'executable': name in ('electron', 'chrome-sandbox')}
        (self.runtime / 'runtime-manifest.json').write_text(json.dumps(self.runtime_meta))
        for name in ('main.cjs', 'preload.cjs', 'security.cjs'):
            (self.app / name).write_text('// packaging fixture only\n')
        (self.app / 'package.json').write_text(json.dumps({'name': pack.PACKAGE, 'version': '1.0.0', 'main': 'main.cjs'}))
        (self.icons / 'app-512.png').write_bytes((ROOT / 'icons/app-512.png').read_bytes())
        (self.icons / 'app.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.fetcher = SimpleNamespace(VERSION='45.2.3', verify_runtime=lambda directory: self.runtime_meta)


class PackagingTests(unittest.TestCase):
    def test_cli_version_tracks_stable_application_metadata(self):
        metadata = json.loads((ROOT / 'app/package.json').read_text())
        self.assertEqual(pack.application_version(), metadata['version'])
        self.assertEqual(metadata['name'], pack.PACKAGE)
        self.assertEqual(metadata['desktopName'], pack.PACKAGE + '.desktop')
        self.assertEqual(metadata['main'], 'main.cjs')

    def test_reviewed_real_runtime_is_available_and_valid(self):
        runtime = ROOT / '.toolchain/electron-45.2.3-linux-x64'
        if not runtime.exists():
            self.skipTest('download the reviewed Electron runtime first')
        report = fetch.verify_runtime(runtime)
        self.assertEqual(report['archive_sha256'], fetch.ARCHIVE_SHA256)
        self.assertEqual(report['version'], '45.2.3')
        self.assertIn('LICENSES.chromium.html', report['files'])

    def test_native_launcher_is_not_a_browser_or_sandbox_bypass(self):
        source = (ROOT / 'linux' / pack.PACKAGE).read_text()
        self.assertIn('exec /opt/cpp-backend-course-desktop/course-backend', source)
        self.assertNotIn('--no-sandbox', source)
        self.assertNotIn('xdg-open', source)
        self.assertNotIn('python', source)
        for key in ('ELECTRON_RUN_AS_NODE', 'NODE_OPTIONS', 'NODE_PATH'):
            self.assertIn(key, source)
        subprocess.run(['sh', '-n', str(ROOT / 'linux' / pack.PACKAGE)], check=True)

    def test_site_integrity_traversal_extra_and_symlink(self):
        with tempfile.TemporaryDirectory(prefix='desktop-site-integrity-') as folder:
            fixture = Fixture(Path(folder))
            manifest, payload = pack.site_payload(fixture.site)
            self.assertEqual(len(payload), 3)
            (fixture.site / 'hello.js').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'differs from manifest'):
                pack.site_payload(fixture.site)
            (fixture.site / 'hello.js').write_bytes(b'1;')
            (fixture.site / 'user.txt').write_text('do not package')
            with self.assertRaisesRegex(ValueError, 'Unmanaged'):
                pack.site_payload(fixture.site)
            (fixture.site / 'user.txt').unlink()
            (fixture.site / 'hello.js').unlink()
            (fixture.site / 'hello.js').symlink_to(fixture.site / 'index.html')
            with self.assertRaisesRegex(ValueError, 'Symbolic links'):
                pack.site_payload(fixture.site)
            for unsafe in ('../x', '/x', 'a//b', 'a/./b', 'a\\b', '%2e%2e/a', 'a\x00'):
                self.assertFalse(pack.safe_name(unsafe), unsafe)

    def test_runtime_map_tamper_is_rejected_before_copying(self):
        with tempfile.TemporaryDirectory(prefix='desktop-runtime-tamper-') as folder:
            directory = Path(folder)
            manifest = {'format': 1, 'version': fetch.VERSION, 'archive_sha256': fetch.ARCHIVE_SHA256,
                        'platform': 'linux-x64', 'files': {'electron': {'sha256': '0' * 64, 'bytes': 3}}}
            (directory / fetch.MANIFEST).write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'file map differs'):
                fetch.verify_runtime(directory)

    def test_published_checksum_must_match_independent_pin(self):
        self.assertEqual(fetch.published_digest(fetch.ARCHIVE_SHA256 + ' *' + fetch.ARCHIVE), fetch.ARCHIVE_SHA256)
        with self.assertRaises(ValueError):
            fetch.published_digest('0' * 64 + ' ' + fetch.ARCHIVE)
        with self.assertRaises(ValueError):
            fetch.published_digest(fetch.ARCHIVE_SHA256 + ' other.zip')

    def test_archive_rejects_escape_and_symlink_members(self):
        with tempfile.TemporaryDirectory(prefix='desktop-zip-safety-') as folder:
            folder = Path(folder)
            for index, name in enumerate(('../escape', '/escape', 'folder\\escape', 'link')):
                archive = folder / ('bad' + str(index) + '.zip')
                with zipfile.ZipFile(archive, 'w') as packed:
                    entry = zipfile.ZipInfo(name)
                    if name == 'link':
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    packed.writestr(entry, 'payload')
                checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
                sums = folder / 'sums'
                sums.write_text(checksum + ' ' + fetch.ARCHIVE)
                with patch.object(fetch, 'ARCHIVE_SHA256', checksum):
                    with self.assertRaisesRegex(ValueError, 'Unsafe ZIP'):
                        fetch.extract_verified(archive, folder / ('out' + str(index)), sums)
                self.assertFalse((folder / ('out' + str(index))).exists())
            self.assertFalse((folder.parent / 'escape').exists())

    @unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb required')
    def test_package_metadata_modes_layout_and_licenses(self):
        with tempfile.TemporaryDirectory(prefix='desktop-package-fixture-') as folder:
            fixture = Fixture(Path(folder))
            with patch.object(pack, 'module', return_value=fixture.fetcher):
                report = pack.build(fixture.site, fixture.runtime, fixture.root / 'out', '1.0.0', fixture.app, fixture.icons)
            artifact = fixture.root / 'out' / report['package']
            control = subprocess.check_output(['dpkg-deb', '--field', str(artifact)], text=True)
            self.assertIn('Architecture: amd64', control)
            self.assertIn('Conflicts: cpp-backend-course-offline', control)
            dependencies = next(line for line in control.splitlines() if line.startswith('Depends:'))
            self.assertNotIn('python', dependencies)
            self.assertNotIn('chromium', dependencies)
            self.assertNotIn('nodejs', dependencies)
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), report['sha256'])
            data = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(data)) as packed:
                members = {entry.name.removeprefix('./'): entry for entry in packed.getmembers()}
                base = 'opt/' + pack.PACKAGE + '/'
                sandbox = members[base + 'chrome-sandbox']
                self.assertEqual((sandbox.uid, sandbox.gid, sandbox.mode), (0, 0, 0o4755))
                self.assertEqual(members[base + 'course-backend'].mode, 0o755)
                self.assertIn(base + 'resources/app/main.cjs', members)
                self.assertIn(base + 'resources/app/site/index.html', members)
                self.assertIn(base + 'resources/app/icons/app-512.png', members)
                self.assertIn(base + 'LICENSE', members)
                self.assertIn(base + 'LICENSES.chromium.html', members)
                self.assertIn('usr/share/applications/' + pack.PACKAGE + '.desktop', members)
                self.assertFalse(any('/offline-course/' in name or name.endswith('launcher.py') for name in members))
            controls = subprocess.check_output(['dpkg-deb', '--ctrl-tarfile', str(artifact)])
            with tarfile.open(fileobj=io.BytesIO(controls)) as packed:
                self.assertFalse(any(entry.name.split('/')[-1] in ('preinst', 'postinst', 'prerm', 'postrm') for entry in packed.getmembers()))

    def test_refuses_overwrite_and_wrong_app_version(self):
        with tempfile.TemporaryDirectory(prefix='desktop-release-guards-') as folder:
            fixture = Fixture(Path(folder))
            fixture.app.joinpath('package.json').write_text('{"main":"main.cjs","version":"2.0.0"}')
            with patch.object(pack, 'module', return_value=fixture.fetcher):
                with self.assertRaisesRegex(ValueError, 'package.json'):
                    pack.build(fixture.site, fixture.runtime, fixture.root / 'out', '1.0.0', fixture.app, fixture.icons)
            output = fixture.root / 'out'
            output.mkdir(exist_ok=True)
            target = output / (pack.PACKAGE + '_1.0.0_amd64.deb')
            target.write_text('user artifact')
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                pack.build(fixture.site, fixture.runtime, output, '1.0.0', fixture.app, fixture.icons)
            self.assertEqual(target.read_text(), 'user artifact')


if __name__ == '__main__':
    unittest.main(verbosity=2)
