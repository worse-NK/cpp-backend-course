"""HTTPS lesson entry points and local runtime contracts, not rendered-pixel QA."""
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest
from urllib.parse import urlsplit

from build_https_journey import render
from build_visual_labs import load_catalog


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ENTRIES = {
    ('station7', 'url-to-service'): ('normal', 'start'),
    ('station7', 'dns-resolution'): ('cached', 'dns'),
    ('station7', 'tcp-stream-handshake'): ('normal', 'tcp'),
    ('station7', 'tls13-handshake'): ('bad-cert', 'tls'),
}


class RuntimeResources(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.resources = []
        self.ids = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'script' and attrs.get('src'):
            self.resources.append(attrs['src'])
        elif tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.resources.append(attrs['href'])


class HttpsJourneyIntegration(unittest.TestCase):
    def test_catalog_entries_match_exact_section_blocks(self):
        labs = load_catalog()['labs']
        lab = next(item for item in labs if item['id'] == 'https-journey')
        self.assertEqual(lab['file'], 'https_journey_lab.html')
        self.assertEqual(lab['scenarios'], ['normal', 'cached', 'bad-cert'])
        entries = {(entry['station'], entry['section']): (entry['scenario'], entry['phase'])
                   for entry in lab['entries']}
        self.assertEqual(entries, EXPECTED_ENTRIES)
        self.assertEqual(len(lab['entries']), len(EXPECTED_ENTRIES))
        blocks = {}
        for path in sorted((ROOT / 'content').glob('station*.json')):
            data = json.loads(path.read_text())
            for section in data['theory']:
                matching = [block for block in section['blocks']
                            if block.get('type') in {'lab', 'lab-ref'} and block.get('lab') == lab['id']]
                if matching:
                    self.assertEqual(len(matching), 1, (path.name, section['id']))
                    blocks[(data['meta']['id'], section['id'])] = matching[0]['scenario']
                    self.assertEqual(matching[0]['type'], 'lab' if section['id'] == 'url-to-service' else 'lab-ref')
        self.assertEqual(blocks, {key: value[0] for key, value in EXPECTED_ENTRIES.items()})

    def test_generated_page_has_only_existing_local_runtime_resources(self):
        expected = render()
        self.assertEqual((ROOT / 'https_journey_lab.html').read_bytes(), expected)
        page = RuntimeResources(expected.decode())
        self.assertEqual(len(page.ids), len(set(page.ids)), 'Duplicate IDs break return/control wiring')
        self.assertIn('return-to-section', page.ids)
        self.assertIn('return-to-theory', page.ids)
        self.assertIn('generated/visual-labs.data.js', page.resources)
        for resource in page.resources:
            parsed = urlsplit(resource)
            self.assertFalse(parsed.scheme or parsed.netloc or parsed.path.startswith('/'), resource)
            self.assertTrue((ROOT / parsed.path).is_file(), resource)
        self.assertNotIn('Пилот нового формата', expected.decode())

    def test_https_model_and_controller_regressions(self):
        for name in ('test_https_journey_model.js', 'test_https_journey_ui.js'):
            with self.subTest(suite=name):
                run = subprocess.run(['gjs', str(ROOT / 'tools' / name)], cwd=ROOT.parent,
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertIn('PASS:', run.stdout)


if __name__ == '__main__':
    unittest.main()
