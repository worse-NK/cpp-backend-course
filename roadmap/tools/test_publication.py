"""Distribution safety and project-subpath checks; no deployment or live browser."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import build_publication as public


class Publication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.stations = public.collect()

    def test_full_course_and_no_private_source_tree(self):
        self.assertEqual(len(self.stations), 15)
        self.assertIn('station5-linux', {s['meta']['id'] for s in self.stations})
        self.assertIn('station7-netlab', {s['meta']['id'] for s in self.stations})
        self.assertIn('station7-traffic', {s['meta']['id'] for s in self.stations})
        self.assertIn('index.html', self.files)
        self.assertIn('.nojekyll', self.files)
        for station in self.stations:
            self.assertIn('roadmap/' + station['meta']['sourceFile'], self.files)
            self.assertIn('roadmap/generated/' + station['meta']['id'] + '.data.js', self.files)
        for name in self.files:
            self.assertFalse(set(Path(name).parts) &
                             {'content', 'tools', 'tests', '__pycache__', '.git', '.aws', '.codex'})
            self.assertNotIn('REVIEW', name)
            self.assertNotIn('CHECKLIST', name)
        self.assertIn('roadmap/vendor/sqljs/LICENSE', self.files)
        self.assertIn('roadmap/examples/station9/verify.py', self.files)

    def test_links_and_runtime_dependency_disclosure(self):
        result = public.check_release(self.files, self.stations)
        self.assertGreater(result['local_links_checked'], 500)
        self.assertTrue(any('unpkg.com/react@18.3.1' in url
                            for url in result['external_runtime_resources']))
        self.assertIn('unpkg.com', self.files['README.md'].decode())
        self.assertIn('roadmap/cpp_backend_roadmap.html', self.files['index.html'].decode())
        self.assertIn('location.search + location.hash', self.files['index.html'].decode())

    def test_missing_learner_download_is_rejected(self):
        files = dict(self.files)
        del files['roadmap/examples/interview_gaps/capacity.js']
        with self.assertRaisesRegex(ValueError, 'Missing published target'):
            public.check_release(files, self.stations)

    def test_only_exact_synthetic_traffic_is_publishable(self):
        name = 'roadmap/examples/traffic-analysis/traffic_http_ok.pcap'
        self.assertIn(name, self.files)
        files = dict(self.files)
        changed = bytearray(files[name])
        changed[-1] ^= 1
        files[name] = bytes(changed)
        with self.assertRaisesRegex(ValueError, 'Synthetic teaching capture differs'):
            public.check_release(files, self.stations)

    def test_absolute_resource_path_is_rejected_on_project_pages(self):
        files = dict(self.files)
        files['index.html'] += b'<script src="/assets/site.js"></script>'
        with self.assertRaisesRegex(ValueError, 'Root URL breaks project Pages'):
            public.check_release(files, self.stations)

    def test_invalid_theory_anchor_is_rejected(self):
        stations = copy.deepcopy(self.stations)
        stations[0]['theory'][0]['blocks'].append({
            'type': 'text', 'html': '<a href="cpp_station0_oop_basics.html#section=not-a-section">test</a>'})
        with self.assertRaisesRegex(ValueError, 'Unknown theory section'):
            public.check_release(self.files, stations)

    def test_private_paths_are_rejected_without_printing_them(self):
        files = dict(self.files)
        files['README.md'] += b'\nfile:///home/example/private.txt'
        with self.assertRaisesRegex(ValueError, 'Potential private path'):
            public.check_release(files, self.stations)

    def test_reproducible_zip_matches_only_release_files(self):
        with tempfile.TemporaryDirectory(prefix='cpp-course-publish-') as work:
            out = Path(work) / 'github-pages'
            first = public.write_release(out)
            archive = Path(work) / public.ARCHIVE_NAME
            with zipfile.ZipFile(archive) as packed:
                self.assertEqual(set(packed.namelist()), {'github-pages/' + p for p in self.files})
                for name, data in self.files.items():
                    self.assertEqual((out / name).read_bytes(), data)
                    self.assertEqual(packed.read('github-pages/' + name), data)
            second = public.write_release(out)
            self.assertEqual(first['archive_sha256'], second['archive_sha256'])
            self.assertEqual(first['file_count'], len(self.files))
            self.assertTrue((Path(work) / public.INSTRUCTIONS_NAME).is_file())
            report = json.loads((Path(work) / public.MANIFEST_NAME).read_text())
            self.assertEqual(report['archive_sha256'], public.digest(archive.read_bytes()))

    def test_manually_edited_release_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='cpp-course-publish-') as work:
            out = Path(work) / 'github-pages'
            public.write_release(out)
            page = out / 'index.html'
            page.write_text('user edit')
            with self.assertRaisesRegex(ValueError, 'edited manually'):
                public.write_release(out)
            self.assertEqual(page.read_text(), 'user edit')

    def test_unmanaged_folder_is_not_cleaned_or_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='cpp-course-publish-') as work:
            out = Path(work) / 'github-pages'
            out.mkdir()
            user_file = out / 'notes.txt'
            user_file.write_text('keep me')
            with self.assertRaisesRegex(ValueError, 'Unmanaged files'):
                public.write_release(out)
            self.assertEqual(user_file.read_text(), 'keep me')
        with tempfile.TemporaryDirectory(prefix='cpp-course-publish-') as work:
            user_file = Path(work) / 'keep.txt'
            user_file.write_text('keep me')
            (Path(work) / public.INSTRUCTIONS_NAME).symlink_to(user_file)
            with self.assertRaisesRegex(ValueError, 'Unsafe output file'):
                public.write_release(Path(work) / 'github-pages')
            self.assertEqual(user_file.read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
