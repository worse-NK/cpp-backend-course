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
ROUTE = (
    ('storage', ('learning-route', 'storage')),
    ('transactions', ('transactions',)),
    ('concurrent-update', ('concurrent-update',)),
    ('isolation', ('isolation',)),
    ('indexes', ('indexes', 'index-decisions', 'storage-maintenance',
                 'physical-join-workbook', 'query-memory-spill-lab')),
    ('cpp-storage', ('cpp-storage',)),
    ('pool', ('pool',)),
    ('evolution', ('evolution', 'durability-limits', 'write-lifecycle')),
    ('design', ('design', 'schema-history-boundaries', 'parking-final-workbook')),
    ('replication', ('replication-path', 'replication-failover', 'postgres-recovery-real-lab')),
    ('cache', ('cache-race', 'cache-pressure')),
    ('delivery', ('outbox-transaction', 'outbox-delivery')),
)
# Older snapshots cover the original sections; additions retain their own hash.
ADDED_IDS = {'physical-join-workbook', 'query-memory-spill-lab',
             'schema-history-boundaries', 'postgres-recovery-real-lab'}


class DatabaseEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}
        cls.checkpoints = json.loads((ROOT / 'content/checkpoints/station9.json').read_text())['modules']

    def test_schema_ids_and_progress(self):
        validate(self.data, SOURCE)
        self.assertEqual([m['id'] for m in self.data['substations']], [m for m, _ in ROUTE])
        self.assertEqual([(s['substation'], s['id']) for s in self.data['theory']],
                         [(module, lesson) for module, lessons in ROUTE for lesson in lessons])
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station9_progress_v1')

    def test_nonprose_payloads_and_order_preserved(self):
        items = [(s['id'], b) for s in self.data['theory'] for b in s['blocks']
                 if b['type'] not in ('text', 'note', 'self-check')]
        original, additions = [], []
        for sid, block in items:
            group = additions if sid in ADDED_IDS or block['type'] in ('reading-figure', 'reading-scene') else original
            group.append((sid, block))
        for payload, size, expected in (
            (original, 22, 'eac8563695ef98b07b12346bbd5c4ae0590c223637930c6840238961f2a3bd01'),
            (additions, 12, 'fa108962f497e5477fd54273eb89c6043dc67b3beda969761e1d06a5de19aa19'),
        ):
            self.assertEqual(len(payload), size)
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            self.assertEqual(digest, expected)

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
        blocks = self.sections['storage-maintenance']['blocks']
        examples = [i for i, b in enumerate(blocks) if b['type'] == 'reading-figure' and
                    any(c['value'] == 'all-visible = 1' for row in b['rows'] for c in row['cells'])]
        self.assertEqual(len(examples), 1)
        intro = ' '.join(b['html'] for b in blocks[:examples[0]] if b['type'] == 'text')
        for term in ('INCLUDE', r'карт\w* видимости', 'all-visible', r'страниц\w*'):
            self.assertRegex(intro, term)  # Teach terms before the diagram or its solution.
        for bank, subject, ref, correct in (
            ('advanced', 'Две транзакции RR снимают', 'isolation', 'Обе фиксации'),
            ('advanced', 'UNIQUE(digest)', 'index-decisions', 'разные строки'),
            ('interview', 'Гарантированы ли нулевые', 'storage-maintenance', 'видимость'),
        ):
            with self.subTest(subject=subject):
                question, = (q for q in self.data['quizzes'][bank] if subject in q['q'])
                self.assertEqual(question['theoryRefs'], [ref])
                self.assertIn(correct, question['options'][question['answer']])

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
