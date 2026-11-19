"""Teaching/link regressions for 7Б; not a privileged Linux-network acceptance test."""
from collections import Counter
from html import unescape
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from build_stations import load_json, validate
from test_linux_systems import Fragment, fields, prose


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station7-netlab.json'
EXAMPLES = ROOT / 'examples/station7-netlab'
GROUPS = ('lab-environment', 'ethernet-routing', 'firewall-policy',
          'ipv6-path', 'nat-observation', 'diagnostic-cases')
EXTENDED_TOPICS = {
    'netlab-vlan-boundaries', 'netlab-stp-loop-recovery',
    'netlab-ospf-route-convergence', 'netlab-bgp-policy-choice',
    'netlab-tcp-loss-slow-reader',
}


class NetworkLabContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(SOURCE)
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def test_schema_and_gradual_reading_order(self):
        validate(self.data, SOURCE)
        self.assertGreaterEqual(len(self.sections), 30)
        self.assertTrue(EXTENDED_TOPICS <= self.sections.keys())
        self.assertEqual(tuple(g['id'] for g in self.data['substations']), GROUPS)
        self.assertEqual(next(iter(self.sections)), 'learning-route')
        self.assertEqual(list(self.sections)[-1], 'netlab-udp-final-workbook')
        positions = {g: i for i, g in enumerate(GROUPS)}
        order = [positions[s['substation']] for s in self.sections.values()]
        self.assertEqual(order, sorted(order))

    def test_sources_and_checkpoint_at_end_of_each_group(self):
        for number, group in enumerate(GROUPS, 1):
            with self.subTest(group=group):
                sections = [s for s in self.sections.values() if s['substation'] == group]
                for section in sections:
                    self.assertGreaterEqual(len(section['blocks']), 8)
                    urls = [url for html in fields(section, 'html') for url in Fragment(html).links]
                    if section['id'] != 'learning-route':  # Navigation points back to sourced prerequisite lessons.
                        self.assertTrue(any(url.startswith('https://') for url in urls), section['id'])
                notes = [b for s in sections for b in s['blocks'] if b['type'] == 'note']
                self.assertTrue(any('Первичные источники' in prose(b) for b in notes))
                last = sections[-1]['blocks'][-1]
                self.assertEqual(last['type'], 'note')
                self.assertEqual(last['kind'], 'key')
                self.assertRegex(prose(last), rf'Контрольная\s+точка\s+7Б\.{number}\b')

    def test_html_and_all_local_destinations(self):
        stations = [load_json(p) for p in (ROOT / 'content').glob('station*.json')]
        anchors = {d['meta']['sourceFile']: {s['id'] for s in d['theory']} for d in stations}
        for section in self.sections.values():
            for html in fields(section, 'html'):
                with self.subTest(section=section['id'], fragment=html[:50]):
                    fragment = Fragment(html)
                    self.assertEqual(fragment.errors, [])
                    self.assertEqual(fragment.stack, [])
                    for link in fragment.links:
                        self.assertNotRegex(link, r'[\s\\"<>]')
                        p = urlsplit(link)
                        if p.scheme:
                            self.assertEqual(p.scheme, 'https')
                        elif p.path in anchors:
                            if p.fragment.startswith('section='):
                                self.assertIn(unquote(p.fragment[8:]), anchors[p.path])
                        elif p.path:
                            target = (ROOT / unquote(p.path)).resolve()
                            self.assertTrue(target.is_relative_to(ROOT.resolve()))
                            self.assertTrue(target.is_file(), link)

    def test_full_program_is_exactly_the_download(self):
        workbook = self.sections['netlab-udp-final-workbook']
        source = (EXAMPLES / 'udp_probe.cpp').read_text()
        full = [b['code'] for b in workbook['blocks'] if b['type'] == 'code' and 'int main(' in b['code']]
        self.assertEqual(full, [source])
        links = [url for html in fields(workbook, 'html') for url in Fragment(html).links]
        for filename in ('udp_probe.cpp', 'filter.nft', 'block.nft', 'snat.nft', 'dnat.nft', 'trace.nft'):
            self.assertIn('examples/station7-netlab/' + filename, links)

    def test_authored_assessments_cover_every_taught_section(self):
        questions = [q for bank in self.data['quizzes'].values() for q in bank]
        # Lower bounds guard against losing material without rejecting a new,
        # properly integrated lesson just because the station grew.
        for bank, minimum in {'basic': 28, 'advanced': 22, 'interview': 25}.items():
            bank_questions = self.data['quizzes'][bank]
            self.assertGreaterEqual(len(bank_questions), minimum, bank)
            self.assertTrue(EXTENDED_TOPICS <= {r for q in bank_questions for r in q['theoryRefs']}, bank)
        basic_counts = Counter(q['substation'] for q in self.data['quizzes']['basic'])
        for group in GROUPS:
            minimum = {'ethernet-routing': 11, 'diagnostic-cases': 5}.get(group, 3)
            self.assertGreaterEqual(basic_counts[group], minimum, group)
        covered = {r for q in questions for r in q['theoryRefs']}
        covered.update(r for t in self.data['tasks'] for r in t['theoryRefs'])
        self.assertTrue(set(self.sections) - {'learning-route'} <= covered)
        self.assertGreaterEqual(len(self.data['tasks']), 9)
        self.assertTrue(EXTENDED_TOPICS <= {r for t in self.data['tasks'] for r in t['theoryRefs']})
        self.assertEqual({t['substation'] for t in self.data['tasks']}, set(GROUPS))
        for task in self.data['tasks']:
            self.assertEqual(task['level'], 'Практика')
            self.assertTrue(task['title'].startswith('Лаборатория: '))
            self.assertNotIn('options', task)
            self.assertTrue(task['hints'] and task['checks'] and task['solution'])

    def test_nft_examples_are_scoped_alternatives_not_global_cleanup(self):
        # Static guard, NOT a substitute for nft -c or a VM traffic test.
        for mode in ('filter', 'block', 'snat', 'dnat', 'trace'):
            with self.subTest(mode=mode):
                text = (EXAMPLES / (mode + '.nft')).read_text()
                rules = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
                self.assertEqual(re.findall(r'\btable\s+(\w+)\s+(\w+)\s*\{', rules), [('inet', 'course7')])
                self.assertNotRegex(rules, r'\b(?:flush|delete)\b')
                self.assertIn('hook forward', rules)
                self.assertIn('policy drop', rules)
                self.assertIn('meta l4proto { icmp, ipv6-icmp } counter accept', rules)
                if mode == 'block':
                    self.assertNotRegex(rules, r'udp dport 9000.*accept')
                else:
                    self.assertIn('iifname "br-lan" oifname "wan0"', rules)
                    self.assertIn('ip daddr 198.51.100.10', rules)
                self.assertEqual('snat ip to' in rules, mode == 'snat')
                self.assertEqual('dnat ip to' in rules, mode == 'dnat')
                self.assertEqual('meta nftrace set 1' in rules, mode == 'trace')

    def test_capture_commands_support_the_fields_explained(self):
        codes = list(fields(self.sections['netlab-packet-walk'], 'code'))
        captures = [code for code in codes if 'tcpdump' in code]
        self.assertTrue(captures)
        for command in '\n'.join(captures).splitlines():
            if 'tcpdump' in command:
                self.assertIn('ip netns exec nl7-router tcpdump', command)
                self.assertRegex(command, r'\s-v\s')  # TTL is not printed by the default IP summary.

    def test_mtu_math_in_the_question_matches_headers(self):
        q = next(q for q in self.data['quizzes']['advanced'] if 'payload UDP 1400' in q['q'])
        answer = q['options'][q['answer']]
        self.assertIn(str(40 + 8 + 1400), answer)
        self.assertIn(str(1400 - 40 - 8), answer)

    def test_lab_entries_match_catalog_and_course_sections(self):
        catalog = json.loads((ROOT / 'content/visual-labs.json').read_text())
        lab = next(l for l in catalog['labs'] if l['id'] == 'packetpath')
        actual = [(s['id'], b['scenario'], b['type']) for s in self.sections.values()
                  for b in s['blocks'] if b['type'] in ('lab', 'lab-ref') and b['lab'] == 'packetpath']
        expected = [(e['section'], e['scenario'], 'lab' if e['primary'] else 'lab-ref')
                    for e in lab['entries'] if e['station'] == 'station7-netlab']
        self.assertCountEqual(actual, expected)
        # One map node; the IPv6 lesson opens PMTU directly without showing the
        # map node a second time or falling back to the default routing scenario.
        self.assertEqual([item for item in actual if item[2] == 'lab'],
                         [('netlab-packet-walk', 'routed', 'lab')])
        self.assertIn(('netlab-ipv6-pmtu', 'pmtu6', 'lab-ref'), actual)
        self.assertTrue({scenario for _, scenario, _ in actual} <= set(lab['scenarios']))


if __name__ == '__main__':
    unittest.main()
