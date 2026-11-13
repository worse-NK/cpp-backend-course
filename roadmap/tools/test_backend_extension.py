"""Contracts for stations 11–14 within the twenty-one-station course catalogue.

Reads canonical sources and renders publication bytes in memory. The optional
GJS companion evaluates real UI components with in-memory React/storage stubs;
it neither opens a browser nor starts Docker, SDK exporters or network traffic.
"""
from collections import Counter
from html import unescape
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from build_stations import validate
from checkpoint_data import normalize_prompt, with_checkpoints
import build_publication as publication
from build_sources import render as render_sources
from build_cheatsheet import render as render_cheatsheet
from test_linux_systems import Fragment, fields

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
NEW_IDS = tuple('station' + str(n) for n in range(11, 15))
LEGACY_IDS = {
    'station0', 'station1', 'station2', 'station3', 'station4', 'station5',
    'station5-linux', 'station6', 'station7', 'station7-netlab', 'station7-traffic',
    'station8', 'station9-sql', 'station9', 'station10',
}
EXPECTED_IDS = LEGACY_IDS | set(NEW_IDS) | {'station15', 'station16'}
LEGACY_HOME_IDS = (
    'oop-basics', 'modern-cpp', 'inheritance-poly', 'stl-templates',
    'error-handling', 'build-tools', 'linux-systems', 'concurrency', 'networking',
    'linux-network-lab', 'rest-api', 'sql', 'databases', 'production', 'traffic-analysis',
)
METADATA = {
    'station11': ('messaging', 'cpp_station11_messaging.html', 33, 77, 8, 11,
                  'messaging-local-lab', 'messaging-final-workbook'),
    'station12': ('redis', 'cpp_station12_redis.html', 32, 63, 7, 9,
                  'redis-lab-guide', 'cache-race-final-workbook'),
    'station13': ('kubernetes', 'cpp_station13_kubernetes.html', 34, 72, 8, 10,
                  'lab-route', 'kubernetes-final-workbook'),
    'station14': ('observability', 'cpp_station14_observability.html', 30, 63, 7, 9,
                  'lab-map', 'observability-final-workbook'),
}
REQUIRED_DOWNLOADS = {
    'station11': {
        'CMakeLists.txt', 'README.txt', 'compose.yaml', 'delivery_model.cpp',
        'kafka_roundtrip.cpp', 'rabbit_roundtrip.cpp', 'rabbit_api.py',
    },
    'station12': {
        '.dockerignore', '.env.example', '.gitignore', 'CMakeLists.txt', 'Dockerfile',
        'README.md', 'cache_client.cpp', 'cache_model.cpp', 'compose.yaml', 'lab.py',
        'rate_limit.lua', 'redis.conf', 'release_lock.lua',
    },
    'station13': {
        '.dockerignore', '.gitignore', 'CMakeLists.txt', 'Dockerfile', 'README.txt',
        'app.cpp', 'configmap.json', 'deployment.json', 'drain_model.cpp',
        'hpa-example.json', 'kind.yaml', 'namespace.json', 'networkpolicy-example.json',
        'pdb-example.json', 'role-example.json', 'service.json', 'verify.py',
    },
    'station14': {
        '.dockerignore', '.gitignore', 'CMakeLists.txt', 'Dockerfile', 'README.txt',
        'alerts.yaml', 'app.cpp', 'collector.yaml', 'compose.yaml', 'dashboard.json',
        'dashboards.yaml', 'datasource.yaml', 'lab.py', 'metrics.hpp',
        'metrics_model.cpp', 'prometheus.yaml',
    },
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def home_data():
    page = (ROOT / 'cpp_backend_roadmap.html').read_text()
    match = re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>', page, re.S)
    if not match:
        raise AssertionError('Missing editable home data')
    return json.loads(match[1]), page


def html_links(value):
    for field in ('html', 'rule', 'prompt', 'answer'):
        for fragment in fields(value, field):
            yield from Fragment(fragment).links


class BackendExtension(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_stations = {
            path.stem: load(path) for path in (ROOT / 'content').glob('station*.json')
        }
        cls.data = {sid: cls.all_stations[sid] for sid in NEW_IDS}
        cls.resolved = {sid: with_checkpoints(data) for sid, data in cls.data.items()}
        cls.home, cls.home_page = home_data()

    def test_preserves_legacy_ids_and_unique_progress_namespaces(self):
        self.assertEqual(EXPECTED_IDS, set(self.all_stations))
        self.assertEqual(21, len(self.all_stations))
        for path_id, data in self.all_stations.items():
            self.assertEqual(path_id, data['meta']['id'])
        for field in ('id', 'storeKey', 'sourceFile'):
            values = [s['meta'][field] for s in self.all_stations.values()]
            self.assertEqual(len(values), len(set(values)), field)
        self.assertEqual(LEGACY_HOME_IDS, tuple(s['id'] for s in self.home['stages'][:15]))
        for n in range(11, 15):
            self.assertEqual(f'cpp_station{n}_progress_v1', self.data[f'station{n}']['meta']['storeKey'])
        for n in (15, 16):
            self.assertEqual(f'cpp_station{n}_progress_v1',
                             self.all_stations[f'station{n}']['meta']['storeKey'])

    def test_new_counts_checkpoints_and_disjoint_banks(self):
        totals = Counter()
        for sid, data in self.data.items():
            with self.subTest(station=sid):
                validate(data, ROOT / 'content' / (sid + '.json'))
                _, file, count, questions, modules, tasks, _, _ = METADATA[sid]
                self.assertEqual(file, data['meta']['sourceFile'])
                self.assertEqual(count, len(data['theory']))
                self.assertEqual(modules, len(data['substations']))
                self.assertEqual(tasks, len(data['tasks']))
                self.assertEqual(questions, sum(map(len, data['quizzes'].values())))
                checkpoints = self.resolved[sid]['checkpoints']
                self.assertEqual({s['id'] for s in data['substations']}, set(checkpoints))
                expected_counts = {module['id']: 5 for module in data['substations']}
                if sid == 'station11':
                    expected_counts['messaging-labs'] = 7
                self.assertEqual(expected_counts,
                                 {module: len(q) for module, q in checkpoints.items()})
                final = [q for bank in data['quizzes'].values() for q in bank]
                checks = [q for bank in checkpoints.values() for q in bank]
                normalized = [normalize_prompt(q['q']) for q in final + checks]
                self.assertEqual(len(normalized), len(set(normalized)), sid)
                order = {m['id']: i for i, m in enumerate(data['substations'])}
                sections = {s['id']: s for s in data['theory']}
                for q in final + checks:
                    for ref in q['theoryRefs']:
                        self.assertLessEqual(order[sections[ref]['substation']], order[q['substation']])
                for bank in data['quizzes'].values():
                    self.assertEqual(set(order), {q['substation'] for q in bank})
                totals.update(sections=len(data['theory']), main=len(final),
                              checkpoints=len(checks), tasks=len(data['tasks']))
        self.assertEqual(dict(sections=129, main=275, checkpoints=152, tasks=39), dict(totals))

    def test_workbooks_preparation_and_real_practice_are_reachable(self):
        for sid, data in self.data.items():
            with self.subTest(station=sid):
                by_id = {s['id']: s for s in data['theory']}
                lab, workbook = METADATA[sid][-2:]
                self.assertIn(lab, by_id)
                self.assertIn(workbook, by_id)
                self.assertTrue(any(b['type'] == 'code' and 'int main(' in b['code']
                                    for b in by_id[workbook]['blocks']))
                practices = [t for t in data['tasks'] if t['level'] == 'Практика']
                self.assertTrue(practices)
                self.assertTrue(all(t['title'].startswith('Лаборатория: ') for t in practices))
                own = 'examples/' + sid + '/'
                links = [u for u in html_links(data['theory']) if u and u.startswith(own)]
                self.assertTrue(links, sid)
                self.assertTrue(any('/README.' in u for u in links), sid)
                for url in links:
                    path = unquote(urlsplit(url).path)
                    self.assertIn(PurePosixPath(path).name, REQUIRED_DOWNLOADS[sid])
                    self.assertTrue((ROOT / path).is_file(), path)
                for module in data['substations']:
                    last = [s for s in data['theory'] if s['substation'] == module['id']][-1]
                    self.assertEqual('note', last['blocks'][-1]['type'])
                    self.assertIn('Контрольная точка', last['blocks'][-1]['html'])

    def test_home_matches_canonical_sections_and_new_group_indices(self):
        stages = self.home['stages']
        self.assertEqual(21, len(stages))
        self.assertEqual(21, len([s for s in stages if s.get('station')]))
        by_file = {d['meta']['sourceFile']: d for d in self.all_stations.values()}
        self.assertEqual(set(by_file), {s['station']['file'] for s in stages})
        self.assertEqual(list(range(1, 22)), [s['num'] for s in stages])
        for stage in stages:
            meta = stage['station']
            source = by_file[meta['file']]
            self.assertEqual(source['meta']['storeKey'], meta['storeKey'])
            self.assertEqual(len(source['theory']), meta['totalSections'])
        groups_source = self.home_page.split('const groups = [', 1)[1].split('\n    ];', 1)[0]
        groups = re.findall(r'id: "([^"]+)"[^\n]*?indices: \[([^\]]*)\]', groups_source)
        indices = {key: [int(n) for n in re.findall(r'\d+', values)] for key, values in groups}
        self.assertEqual([15, 16, 17, 18, 19, 20], indices['backend-extension'])
        flattened = [n for group in indices.values() for n in group]
        self.assertEqual(list(range(21)), sorted(flattened))
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(self.all_stations['station15']['meta']['sourceFile'],
                         stages[19]['station']['file'])
        self.assertEqual(self.all_stations['station16']['meta']['sourceFile'],
                         stages[20]['station']['file'])
        for sid, (stage_id, *_) in METADATA.items():
            stage = next(s for s in stages if s['id'] == stage_id)
            self.assertEqual(self.data[sid]['meta']['sourceFile'], stage['station']['file'])

    def test_four_cheatsheet_groups_and_resolvable_theory_anchors(self):
        data = load(ROOT / 'content/cheatsheet.json')
        groups = data['stations']
        rendered = render_cheatsheet()
        files = {d['meta']['sourceFile']: {s['id'] for s in d['theory']}
                 for d in self.all_stations.values()}
        for n in range(11, 15):
            selected = [g for g in groups if g['num'] == str(n)]
            self.assertEqual(1, len(selected))
            group = selected[0]
            self.assertGreaterEqual(len(group['sections']), 6)
            self.assertIn(f'id="station-{n}"', rendered)
            self.assertIn(self.data[f'station{n}']['meta']['sourceFile'], rendered)
            own_refs = set()
            primary_sources = set()
            for section in group['sections']:
                self.assertTrue(section['items'])
                for item in section['items']:
                    parsed = Fragment(item['rule'])
                    self.assertFalse(parsed.errors)
                    self.assertFalse(parsed.stack)
                    for link in parsed.links:
                        url = urlsplit(unescape(link))
                        if url.path in files:
                            ref = parse_qs(url.fragment).get('section', [None])[0]
                            self.assertIn(ref, files[url.path], link)
                            if url.path == self.data[f'station{n}']['meta']['sourceFile']:
                                own_refs.add(ref)
                        elif url.scheme in ('https', 'http'):
                            primary_sources.add(url.netloc)
                        elif url.path:
                            self.assertTrue((ROOT / unquote(url.path)).is_file(), link)
            self.assertGreaterEqual(len(own_refs), 10)
            self.assertTrue(primary_sources)

    def test_sources_index_is_dynamic_for_all_twenty_one_station_ids(self):
        page = render_sources()
        for sid, data in self.all_stations.items():
            self.assertIn(f'href="#{sid}"', page)
            self.assertIn(f'id="{sid}"', page)
            for section in data['theory']:
                self.assertIn(data['meta']['sourceFile'] + '#section=' + section['id'], page)
        self.assertEqual(sum(len(s['theory']) for s in self.all_stations.values()), page.count('<details>'))

    def test_component_routes_without_browser_when_gjs_available(self):
        gjs = shutil.which('gjs')
        if not gjs:
            self.skipTest('GJS unavailable; static/content/publication checks still run')
        result = subprocess.run([gjs, str(ROOT / 'tools/test_backend_extension_ui.js')],
                                cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('PASS: backend extension UI', result.stdout)


class BackendPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # collect() renders bytes only: no destination, deployment or daemon.
        cls.files, cls.stations = publication.collect()

    def test_all_new_downloads_are_explicitly_allowlisted_and_included(self):
        allowlist = set(publication.EXAMPLES)
        self.assertEqual(len(publication.EXAMPLES), len(allowlist))
        for sid, names in REQUIRED_DOWNLOADS.items():
            with self.subTest(station=sid):
                required = {sid + '/' + name for name in names}
                self.assertTrue(required <= allowlist, sorted(required - allowlist))
                for name in required:
                    target = 'roadmap/examples/' + name
                    self.assertIn(target, self.files)
                    self.assertEqual((ROOT / 'examples' / name).read_bytes(), self.files[target])

    def test_no_runtime_secrets_or_unlisted_new_lab_files_are_published(self):
        for name in self.files:
            parts = PurePosixPath(name).parts
            self.assertFalse(set(parts) & {'runtime', 'build', '__pycache__', '.git', '.aws', '.codex'})
            self.assertFalse(set(parts) & {'content', 'tools', 'tests'})
            self.assertNotIn('.env', parts)
            self.assertNotIn('users.acl', parts)
            self.assertNotIn('kubeconfig', PurePosixPath(name).name.casefold())
            for sid in NEW_IDS:
                prefix = 'roadmap/examples/' + sid + '/'
                if name.startswith(prefix):
                    self.assertIn(name[len('roadmap/examples/'):], publication.EXAMPLES)
        # A template is deliberately public; it is not a locally generated secret.
        self.assertIn('roadmap/examples/station12/.env.example', self.files)
        self.assertEqual(EXPECTED_IDS, {s['meta']['id'] for s in self.stations})

    def test_public_entry_sources_and_project_subpath_links(self):
        report = publication.check_release(self.files, self.stations)
        self.assertGreater(report['local_links_checked'], 500)
        entry = self.files['index.html'].decode()
        self.assertIn('roadmap/cpp_backend_roadmap.html', entry)
        self.assertIn('location.search + location.hash', entry)
        sources = self.files['roadmap/sources.html'].decode()
        cheat = self.files['roadmap/cpp_cheatsheet.html'].decode()
        for sid in NEW_IDS:
            meta = next(s['meta'] for s in self.stations if s['meta']['id'] == sid)
            self.assertIn('roadmap/' + meta['sourceFile'], self.files)
            self.assertIn('roadmap/generated/' + sid + '.data.js', self.files)
            self.assertIn('id="' + sid + '"', sources)
            self.assertIn('id="station-' + str(meta['number']) + '"', cheat)


if __name__ == '__main__':
    unittest.main()
