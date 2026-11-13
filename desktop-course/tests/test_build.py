#!/usr/bin/env python3
"""Standalone content is a local, source-free clone, never a PWA."""
import json
from html import unescape
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import build_site as build


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.manifest = build.collect()

    def test_every_original_data_style_and_example_is_unchanged(self):
        original, stations = build.publication.collect()
        self.assertEqual(len(stations), 21)
        for name, content in original.items():
            if name.endswith(('.js', '.css', '.cpp', '.hpp', '.sql', '.pcap')):
                self.assertEqual(build.digest(self.files[name]), build.digest(content), name)

    def test_no_runtime_network(self):
        self.assertGreater(build.check_local(self.files), 500)
        self.assertEqual(self.manifest['externalRuntimeResources'], [])
        for name, content in self.files.items():
            if name.endswith('.html'):
                self.assertNotIn(b'https://unpkg.com', content)
                self.assertNotIn(b'rel="manifest"', content)

    def test_no_pwa_server_or_source_files(self):
        self.assertFalse(any(name in self.files for name in ('sw.js', 'manifest.webmanifest', 'pwa.js', 'offline.html')))
        for name in self.files:
            self.assertNotIn('/content/', name)
            self.assertNotIn('/tools/', name)
            self.assertFalse(name.endswith(('.deb', '.img', '.qcow2', '.env')))
        self.assertNotIn(b'serviceWorker.register', self.files['desktop-ui.js'])

    def test_complete_digest_map_and_determinism(self):
        files, manifest = build.collect()
        self.assertEqual(manifest['version'], self.manifest['version'])
        self.assertEqual(len(files), manifest['fileCount'])
        for name, metadata in manifest['files'].items():
            self.assertEqual(build.digest(files[name]), metadata['sha256'], name)
            self.assertEqual(len(files[name]), metadata['bytes'], name)

    def test_settings_and_icons(self):
        self.assertIn('progress.html', self.files)
        for size in (256, 512):
            self.assertTrue(self.files[f'icons/app-{size}.png'].startswith(b'\x89PNG'))
        self.assertIn('icons/app.svg', self.files)
        self.assertEqual(self.files['progress-core.js'], (ROOT / 'web/progress-core.js').read_bytes())

    def test_progress_metadata_fetch_is_permitted_only_on_the_settings_page(self):
        self.assertIn("fetch('desktop-meta.json')", self.files['progress-ui.js'].decode())
        self.assertIn('applicationVersion', json.loads(self.files['desktop-meta.json']))
        for name, content in self.files.items():
            if not name.endswith('.html'):
                continue
            policy = unescape(re.search(
                r'<meta[^>]*data-course-security="1"[^>]*content="([^"]+)"',
                content.decode())[1])
            directives = dict((parts[0], parts[1:]) for item in policy.split(';')
                              if (parts := item.split()))
            with self.subTest(page=name):
                self.assertEqual(directives['connect-src'],
                                 ["'self'"] if name == 'progress.html' else ["'none'"])

    def test_all_station_maps_use_the_same_production_assets_as_the_website(self):
        self.assertIn('roadmap/assets/station-map.css', self.files)
        self.assertIn('roadmap/assets/station-map-joints.css', self.files)
        _, stations = build.publication.collect()
        for station in stations:
            name = 'roadmap/' + station['meta']['sourceFile']
            page = self.files[name].decode()
            with self.subTest(station=station['meta']['id']):
                self.assertIn('station-map.css', page)
                self.assertIn('station-map-joints.css', page)
                self.assertIn('course-map', page)
                self.assertNotIn('map-preview-settings', page)
                self.assertNotIn('station0-map-preview.app.js', page)

    def test_vendor_licenses_and_pin(self):
        files = build.vendor_files()
        self.assertIn('roadmap/vendor/desktop/react/LICENSE-react', files)
        self.assertIn('roadmap/vendor/desktop/fonts/LICENSE-Inter', files)
        self.assertNotIn(b'https:', files['roadmap/vendor/desktop/fonts/fonts.css'])

    def test_output_guard(self):
        with self.assertRaises(ValueError):
            build.write_site(build.PROJECT / 'roadmap')
        with tempfile.TemporaryDirectory(prefix='desktop-build-test-') as folder:
            out = Path(folder) / 'site'
            manifest = build.write_site(out)
            self.assertEqual(manifest['version'], build.write_site(out)['version'])
            (out / 'desktop.css').write_text('user changes')
            with self.assertRaises(ValueError):
                build.write_site(out)
            self.assertEqual((out / 'desktop.css').read_text(), 'user changes')


if __name__ == '__main__':
    unittest.main(verbosity=2)
