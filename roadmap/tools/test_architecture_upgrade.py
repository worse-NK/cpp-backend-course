"""Architecture upgrade contracts. No Docker, real sockets, or host mutations.

The isolated PostgreSQL acceptance is a separate, explicitly authorized run.
These regressions cannot establish production capacity or teaching quality.
"""
import contextlib
import io
import json
from pathlib import Path
import re
import unittest
from unittest import mock

import build_stations
import verify_architecture_postgres as postgres

ROOT = Path(__file__).resolve().parents[1]
ADDED = {
    7: ('linux-packet-to-handler', 'server-queues-two-bottlenecks',
        'load-balancing-connections-requests'),
    8: ('request-execution-workbook', 'architecture-boundaries',
        'dependency-fanout-workbook', 'replica-state-workbook'),
    9: ('write-lifecycle', 'replication-path', 'replication-failover',
        'cache-race', 'cache-pressure', 'outbox-transaction', 'outbox-delivery'),
    10: ('request-budget-architecture', 'proxy-release-timeline'),
}


class ArchitectureUpgrade(unittest.TestCase):
    def setUp(self):
        self.data = {n: json.loads((ROOT / f'content/station{n}.json').read_text())
                     for n in ADDED}

    def test_new_topics_have_sources_diagrams_and_assessments(self):
        for number, refs in ADDED.items():
            data = self.data[number]
            build_stations.validate(data, ROOT / f'content/station{number}.json')
            sections = {s['id']: s for s in data['theory']}
            for ref in refs:
                section = sections[ref]
                with self.subTest(station=number, section=ref):
                    fragments = json.dumps(section, ensure_ascii=False)
                    self.assertIn('https://', fragments, 'Each case needs its cited basis')
                    self.assertGreaterEqual(len(section['blocks']), 4)
                    for bank in ('basic', 'interview'):
                        self.assertTrue(any(ref in q['theoryRefs'] for q in data['quizzes'][bank]), bank)
            # A diagram should clarify a relationship, not decorate every page.
            # Some follow-up pages deliberately use a state table or SQL instead.
            self.assertTrue(any(b['type'] in ('diagram', 'visual', 'lanes')
                                for ref in refs for b in sections[ref]['blocks']))

    def test_workshop_links_are_real_and_have_reverse_preparation(self):
        links = []
        for name in ('start', 'local', 'database', 'operate'):
            text = (ROOT / f'content/service-workshop/{name}.html').read_text()
            links += re.findall(r'href="(cpp_station\d+_[^"#]+)\#section=([a-z0-9-]+)"', text)
        targets = {data['meta']['sourceFile']: {s['id'] for s in data['theory']}
                   for data in self.data.values()}
        for file, ref in links:
            if file in targets:
                self.assertIn(ref, targets[file], (file, ref))
        self.assertTrue(any(ref == 'request-budget-architecture' for _, ref in links))
        self.assertTrue(any(ref == 'write-lifecycle' for _, ref in links))

    def test_row_lock_practice_matches_actual_readiness_query(self):
        task = next(t for t in self.data[10]['tasks'] if t['title'].startswith('Эксплуатация: health'))
        source = (ROOT / 'examples/service-workshop/storage.cpp').read_text()
        query = 'SELECT id,title,done,version FROM public.tasks LIMIT 0'
        self.assertIn(query, source)
        self.assertIn(query, task['solution'])
        self.assertIn('FOR UPDATE', task['code'])
        self.assertIn('ROLLBACK', task['solution'])
        self.assertIn('request-budget-architecture', task['theoryRefs'])

    def test_network_rss_does_not_get_a_memory_usage_definition(self):
        section = next(s for s in self.data[7]['theory'] if s['id'] == 'linux-packet-to-handler')
        html = ' '.join(b.get('html', '') for b in section['blocks'])
        self.assertIn('<code>Receive Side Scaling</code>', html)
        # Standalone inline code can receive terms. Explicitly opt out here:
        # existing glossary RSS means resident set size, not network scaling.
        self.assertIn('<code data-no-terms>RSS</code>', html)
        self.assertNotIn('один снимок tcpdump', html)

    def test_outbox_examples_are_the_actual_acceptance_inputs(self):
        listings = postgres.sql_listings()
        self.assertEqual(set(listings), {'outbox-transaction', 'outbox-delivery'})
        for ref, blocks in listings.items():
            canonical = next(s for s in self.data[9]['theory'] if s['id'] == ref)
            self.assertEqual(blocks, [b['code'] for b in canonical['blocks'] if b['type'] == 'code'])
        task = next(t for t in self.data[9]['tasks'] if 'outbox и receipt' in t['title'])
        self.assertTrue(task['title'].startswith('Лаборатория: '))

    def test_models_are_labelled_and_docker_requires_opt_in(self):
        checks = postgres.cache_models()
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(check.startswith('deterministic model:') for check in checks))
        with mock.patch.object(postgres, 'IsolatedProject') as project:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(postgres.main([]), 77)
            project.assert_not_called()
            self.assertIn('NOT RUN: real PostgreSQL/HTTP', output.getvalue())

    def test_changed_chapter_gets_a_new_cache_fingerprint(self):
        data = self.data[7]
        before = build_stations.html_for(data)
        data['meta']['subtitle'] += ' Уточнение.'
        after = build_stations.html_for(data)
        pattern = r'generated/station7\.data\.js\?v=([0-9a-f]{12})'
        self.assertNotEqual(re.search(pattern, before)[1], re.search(pattern, after)[1])
        app = r'assets/station-app\.js\?v=([0-9a-f]{12})'
        self.assertEqual(re.search(app, before)[1], re.search(app, after)[1])


if __name__ == '__main__':
    unittest.main()
