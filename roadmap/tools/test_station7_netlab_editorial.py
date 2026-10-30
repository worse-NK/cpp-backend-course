"""Editorial guardrails for 7Б. No privileged commands or live captures."""
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import unittest

from build_stations import validate
from test_linux_systems import Fragment, fields

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station7-netlab.json'


class NetlabEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}
        cls.checkpoints = json.loads((ROOT / 'content/checkpoints/station7-netlab.json').read_text())['modules']

    def test_schema_progress_and_section_count(self):
        validate(self.data, SOURCE)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station7_netlab_progress_v1')
        self.assertEqual(len(self.sections), 25)

    def test_original_code_and_visual_payloads_unchanged(self):
        payloads = [(s['id'], b) for s in self.data['theory'] for b in s['blocks']
                    if b['type'] not in ('text', 'note', 'self-check')]
        digest = hashlib.sha256(json.dumps(payloads, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, 'dbac2153747ae27cf8dd7b7c6b46ee2ee55c6a608ce7ab0b46a8dbb4c82ecc27')

    def test_every_section_has_explained_self_check(self):
        for section in self.sections.values():
            with self.subTest(section=section['id']):
                checks = [b for b in section['blocks'] if b['type'] == 'self-check']
                self.assertTrue(checks)
                self.assertTrue(all(len(b['prompt']) > 35 and len(b['answer']) > 110 for b in checks))

    def test_html_including_revealed_answers(self):
        for section in self.sections.values():
            for key in ('html', 'prompt', 'answer'):
                for html in fields(section, key):
                    fragment = Fragment(html)
                    self.assertEqual(fragment.errors, [], (section['id'], key))
                    self.assertEqual(fragment.stack, [], (section['id'], key))

    def test_checkpoint_is_last_and_not_final_question(self):
        final = {q['q'] for bank in self.data['quizzes'].values() for q in bank}
        for group in self.data['substations']:
            sections = [s for s in self.data['theory'] if s['substation'] == group['id']]
            self.assertIn('Контрольная точка', sections[-1]['blocks'][-1]['html'])
            questions = self.checkpoints[group['id']]
            self.assertGreaterEqual(len(questions), 5)
            for q in questions:
                self.assertNotIn('bank', q)
                self.assertNotIn(q['q'], final)

    def test_fixed_payload_is_not_unique_run_marker(self):
        section = self.sections['netlab-capture-boundaries']
        text = ' '.join(fields(section, 'html'))
        self.assertIn('не являются уникальными идентификаторами запуска', text)
        question = self.checkpoints['diagnostic-cases'][1]
        self.assertIn('одинаковую строку', question['q'])
        self.assertIn('пятёрку', question['options'][question['answer']])

    def test_documentation_prefixes_and_size_model(self):
        self.assertIn(ipaddress.ip_address('192.0.2.10'), ipaddress.ip_network('192.0.2.0/24'))
        self.assertNotIn(ipaddress.ip_address('198.51.100.10'), ipaddress.ip_network('192.0.2.0/24'))
        self.assertIn(ipaddress.ip_address('2001:db8:7:2::10'), ipaddress.ip_network('2001:db8::/32'))
        self.assertEqual(1280 - 40 - 8, 1232)
        self.assertEqual(1400 - 40 - 8, 1352)

    def test_answer_length_is_not_systematic_hint(self):
        for name, questions in self.data['quizzes'].items():
            longest = sum(len(q['options'][q['answer']]) > max(len(o) for i, o in enumerate(q['options'])
                                                               if i != q['answer']) for q in questions)
            shortest = sum(len(q['options'][q['answer']]) < min(len(o) for i, o in enumerate(q['options'])
                                                               if i != q['answer']) for q in questions)
            self.assertLess(longest / len(questions), .65, name)
            self.assertLess(shortest / len(questions), .5, name)

    def test_shell_syntax_only(self):
        result = subprocess.run(['bash', '-n', str(ROOT / 'examples/station7-netlab/network_lab.sh')],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
