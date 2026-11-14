"""Network lab source/build/package contracts, not browser or pixel QA."""
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlsplit

from build_network_labs import LABS, render_all
from build_visual_labs import load_catalog
import build_publication as publication
from web_security import validate_files

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
EXPECTED = {'tcp-delivery', 'packetpath', 'network-setup', 'vpn-tunnels'}
MODEL_FILES = {'tcp-delivery':'network-tcp-model.js', 'packetpath':'network-routing-model.js',
               'network-setup':'network-config-model.js', 'vpn-tunnels':'network-vpn-model.js'}


class RuntimeResources(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.resources = []
        self.ids = []
        self.labels = []
        self.controls = []
        self.csp = []
        self.feed(source)

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'script' and attrs.get('src'):
            self.resources.append(attrs['src'])
        elif tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.resources.append(attrs['href'])
        elif tag == 'meta' and attrs.get('http-equiv', '').lower() == 'content-security-policy':
            self.csp.append(attrs.get('content', ''))
        elif tag == 'label' and attrs.get('for'):
            self.labels.append(attrs['for'])
        if tag in ('input', 'select'):
            self.controls.append(attrs)


class NetworkLabsIntegration(unittest.TestCase):
    def test_catalog_has_one_primary_node_and_exact_authored_references(self):
        catalog = {lab['id']: lab for lab in load_catalog()['labs']}
        self.assertEqual(set(LABS), EXPECTED)
        stations = {path.stem: json.loads(path.read_text())
                    for path in sorted((ROOT / 'content').glob('station*.json'))}
        for lab_id in sorted(EXPECTED):
            with self.subTest(lab=lab_id):
                lab = catalog[lab_id]
                self.assertEqual(lab['file'], LABS[lab_id][0])
                self.assertTrue(lab['entries'])
                self.assertEqual(sum(entry.get('primary') is True for entry in lab['entries']), 1,
                                 'One canonical map node per laboratory, not per reference')
                self.assertTrue(all(isinstance(entry.get('primary'), bool) for entry in lab['entries']))
                expected = {(entry['station'], entry['section']): entry for entry in lab['entries']}
                self.assertEqual(len(expected), len(lab['entries']), 'No duplicate entry contexts')
                actual = {}
                for station_id, station in stations.items():
                    for section in station['theory']:
                        matching = [block for block in section['blocks']
                                    if block.get('lab') == lab_id and block.get('type') in ('lab', 'lab-ref')]
                        if not matching:
                            continue
                        self.assertEqual(len(matching), 1, (lab_id, station_id, section['id']))
                        actual[(station_id, section['id'])] = matching[0]
                self.assertEqual(set(actual), set(expected), 'Catalog and actual theory entry points agree')
                for key, entry in expected.items():
                    block = actual[key]
                    self.assertEqual(block['type'], 'lab' if entry['primary'] else 'lab-ref', key)
                    self.assertEqual(block['scenario'], entry['scenario'], key)
                    self.assertIn(entry['scenario'], lab['scenarios'])
                    if 'phase' in entry:
                        self.assertIsInstance(entry['phase'], str)
                        self.assertTrue(entry['phase'], 'An optional start phase must be nonempty')

    def test_all_generated_pages_match_source_and_have_local_resources(self):
        pages = render_all()
        self.assertEqual(len(pages), 4)
        for name, content in pages.items():
            with self.subTest(page=name):
                self.assertEqual((ROOT / name).read_bytes(), content, 'Generated page is stale')
                parser = RuntimeResources(content.decode())
                self.assertEqual(len(parser.ids), len(set(parser.ids)), 'Duplicate control IDs')
                self.assertEqual(len(parser.csp), 1, 'Exactly one generated CSP')
                self.assertIn("default-src 'none'", parser.csp[0])
                self.assertTrue({'return-to-section', 'return-to-theory', 'network-lab-config',
                                 'mechanism-panels', 'step-title', 'announcement'} <= set(parser.ids))
                self.assertIn('generated/visual-labs.data.js', parser.resources)
                self.assertIn('assets/network-labs.js', parser.resources)
                for model in MODEL_FILES.values():
                    self.assertIn('assets/' + model, parser.resources)
                for resource in parser.resources:
                    parsed = urlsplit(resource)
                    self.assertFalse(parsed.scheme or parsed.netloc or parsed.path.startswith('/'), resource)
                    self.assertTrue((ROOT / parsed.path).is_file(), resource)
                for control in parser.controls:
                    self.assertTrue(control.get('aria-label') or control.get('id') in parser.labels,
                                    'Native control requires an accessible label')
                self.assertNotIn('user-scalable=no', content.decode())
                self.assertNotIn('{{', content.decode())

    def test_models_and_controller_contracts(self):
        for name in ('test_network_tcp_model.js', 'test_network_config_model.js',
                     'test_network_routing_model.js', 'test_network_vpn_model.js', 'test_network_labs_ui.js'):
            with self.subTest(suite=name):
                run = subprocess.run(['gjs', str(ROOT / 'tools' / name)], cwd=PROJECT,
                                     capture_output=True, text=True, timeout=120)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertRegex(run.stdout, r'(?i)(?:PASS:|checks\s+passed|checks.*?passed)')
                self.assertNotIn('DEVELOPMENT --available', run.stdout)

    def test_publication_and_offline_builder_include_the_same_runtime(self):
        # collect() produces in-memory payloads: no deployment, apt, browser or
        # replacement of the user's existing local/desktop build is performed.
        public_files, stations = publication.collect()
        publication.check_release(public_files, stations)
        validate_files(public_files, mode='web')
        spec = importlib.util.spec_from_file_location('_network_lab_local_builder', PROJECT / 'tools/build_local.py')
        local_builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = local_builder
        spec.loader.exec_module(local_builder)
        local_files, manifest = local_builder.collect()
        self.assertEqual(manifest['externalRuntimeResources'], [])
        self.assertEqual(manifest['mode'], 'offline-browser')
        self.assertGreater(local_builder.desktop_adapter().check_local(local_files), 0)
        runtime = ['network-labs.js', 'network-labs.css', *MODEL_FILES.values()]
        for _, (filename, _, _) in LABS.items():
            name = 'roadmap/' + filename
            self.assertIn(name, public_files)
            self.assertIn(name, local_files)
            for files in (public_files, local_files):
                parser = RuntimeResources(files[name].decode())
                self.assertFalse(any(urlsplit(resource).scheme or urlsplit(resource).netloc
                                     for resource in parser.resources), name)
        for asset in runtime:
            name = 'roadmap/assets/' + asset
            self.assertEqual(public_files[name], (ROOT / 'assets' / asset).read_bytes(), name)
            self.assertEqual(local_files[name], public_files[name], name)
        for files in (public_files, local_files):
            self.assertNotIn('roadmap/templates/network_lab.html', files)
            self.assertNotIn('roadmap/tools/test_network_labs_ui.js', files)


if __name__ == '__main__':
    unittest.main()
