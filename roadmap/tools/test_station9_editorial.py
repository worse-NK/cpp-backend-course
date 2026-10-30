"""Station 9Б editorial guards and stated-model arithmetic; not a PG runtime test."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from fractions import Fraction

from build_stations import validate
from test_linux_systems import Fragment, fields

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station9.json'
IDS = ('learning-route', 'storage', 'transactions', 'concurrent-update', 'isolation',
       'indexes', 'index-decisions', 'storage-maintenance', 'cpp-storage', 'pool',
       'evolution', 'durability-limits', 'write-lifecycle', 'design',
       'parking-final-workbook', 'replication-path', 'replication-failover',
       'cache-race', 'cache-pressure', 'outbox-transaction', 'outbox-delivery')


class DatabaseEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}
        cls.checkpoints = json.loads((ROOT / 'content/checkpoints/station9.json').read_text())['modules']

    def test_schema_ids_and_progress(self):
        validate(self.data, SOURCE)
        self.assertEqual(tuple(self.sections), IDS)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station9_progress_v1')
        self.assertEqual(len(self.data['substations']), 12)

    def test_nonprose_payloads_and_order_preserved(self):
        original = [(s['id'], b) for s in self.data['theory'] for b in s['blocks']
                    if b['type'] not in ('text', 'note', 'self-check')]
        digest = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, 'eac8563695ef98b07b12346bbd5c4ae0590c223637930c6840238961f2a3bd01')

    def test_real_cpp_listing_matches_download_without_stubs(self):
        for sid, filename in [('cpp-storage', 'main.cpp'), ('parking-final-workbook', 'parking.cpp')]:
            blocks = self.sections[sid]['blocks']
            source = (ROOT / 'examples/station9' / filename).read_text().strip()
            self.assertIn(source, [b['code'] for b in blocks if b['type'] == 'code'])

    def test_nested_figures_preserved_as_whole_elements(self):
        figures = [(s['id'], figure) for s in self.data['theory'] for b in s['blocks']
                   for figure in re.findall(r'<figure\b.*?</figure>', b.get('html', ''), re.S)]
        self.assertEqual(len(figures), 6)
        digest = hashlib.sha256(json.dumps(figures, ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(digest, '7aaa62332c5166b9c60ea1a85718d208756508c146e1679b56e0d0d32777555b')

    def test_every_fragment_balanced_including_revealed_answer(self):
        for section in self.sections.values():
            checks = [b for b in section['blocks'] if b['type'] == 'self-check']
            self.assertTrue(checks, section['id'])
            self.assertTrue(all(len(b['prompt']) > 40 and len(b['answer']) > 130 for b in checks))
            for key in ('html', 'prompt', 'answer'):
                for html in fields(section, key):
                    parser = Fragment(html)
                    self.assertEqual(parser.errors, [], (section['id'], key))
                    self.assertEqual(parser.stack, [], (section['id'], key))

    def test_all_checkpoints_independent_and_teachable(self):
        final = {q['q'] for bank in self.data['quizzes'].values() for q in bank}
        module_order = {m['id']: i for i, m in enumerate(self.data['substations'])}
        section_order = {sid: module_order[s['substation']] for sid, s in self.sections.items()}
        self.assertEqual(set(self.checkpoints), {m['id'] for m in self.data['substations']})
        for module, questions in self.checkpoints.items():
            self.assertGreaterEqual(len(questions), 5)
            for q in questions:
                self.assertNotIn('bank', q)
                self.assertNotIn(q['q'], final)
                self.assertTrue(q['theoryRefs'])
                self.assertTrue(set(q['theoryRefs']) <= self.sections.keys())
                self.assertTrue(all(section_order[ref] <= module_order[module]
                                    for ref in q['theoryRefs']), (module, q['q']))

    def test_postgres_not_confused_with_browser_sqlite(self):
        intro = ' '.join(fields(self.sections['learning-route'], 'html'))
        self.assertIn('PostgreSQL 18', intro)
        self.assertIn('SQLite', intro)
        self.assertIn('не воспроизводит', intro)
        cpp = ' '.join(fields(self.sections['cpp-storage'], 'html'))
        self.assertIn('7.10.1', cpp)

    def test_write_skew_and_visibility_map_taught_before_assessment(self):
        isolation = ' '.join(fields(self.sections['isolation'], 'html'))
        self.assertIn('write skew', isolation)
        self.assertIn('перекос записи', isolation)
        maintenance = ' '.join(fields(self.sections['storage-maintenance'], 'html'))
        self.assertIn('all-visible', maintenance)
        self.assertIn('INCLUDE', maintenance)
        self.assertEqual(self.data['quizzes']['advanced'][8]['theoryRefs'], ['index-decisions'])

    def test_stated_arithmetic_not_claimed_pg_execution(self):
        # These calculations validate the numbers in the teaching scenarios only.
        self.assertEqual(20 * 10, 200)
        self.assertEqual(1000 * 86400, 86400000)
        self.assertEqual(sum(n % 1000 == 42 for n in range(1, 100001)), 100)
        self.assertEqual(1000000 * (1 - Fraction(99, 100)), 10000)
        self.assertEqual(1000000 // 10000, 100)

    def test_all_answer_positions_and_lengths_remain_usable(self):
        groups = list(self.data['quizzes'].items()) + list(self.checkpoints.items())
        for name, questions in groups:
            longest = shortest = 0
            positions = set()
            for q in questions:
                self.assertTrue(0 <= q['answer'] < len(q['options']))
                positions.add(q['answer'])
                actual = len(q['options'][q['answer']])
                other = [len(o) for i, o in enumerate(q['options']) if i != q['answer']]
                longest += actual > max(other)
                shortest += actual < min(other)
            self.assertGreater(len(positions), 1, name)
            self.assertLess(longest / len(questions), .7, name + ':longest')
            self.assertLess(shortest / len(questions), .7, name + ':shortest')


if __name__ == '__main__':
    unittest.main()
