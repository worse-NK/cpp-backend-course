"""Editorial and offline byte checks for 7В; no live captures or host traffic."""
import hashlib
import json
from pathlib import Path
import unittest

from build_stations import validate
from test_linux_systems import Fragment, fields
from test_traffic_examples import read_capture, layers

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station7-traffic.json'
EXAMPLES = ROOT / 'examples/traffic-analysis'


class TrafficEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}
        cls.checkpoints = json.loads((ROOT / 'content/checkpoints/station7-traffic.json').read_text())['modules']

    def test_schema_progress_and_sections(self):
        validate(self.data, SOURCE)
        self.assertEqual(len(self.sections), 25)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station7_traffic_progress_v1')

    def test_code_and_visuals_are_preserved(self):
        payloads = [(s['id'], b) for s in self.data['theory'] for b in s['blocks']
                    if b['type'] not in ('text', 'note', 'self-check')]
        digest = hashlib.sha256(json.dumps(payloads, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, 'a0762211ad4dc3802d130dd9bed963f077520d5093085674020ee770e5ad3df4')

    def test_self_checks_and_html(self):
        for section in self.sections.values():
            with self.subTest(section=section['id']):
                checks = [b for b in section['blocks'] if b['type'] == 'self-check']
                self.assertTrue(checks)
                self.assertTrue(all(len(b['prompt']) > 35 and len(b['answer']) > 110 for b in checks))
                for key in ('html', 'prompt', 'answer'):
                    for html in fields(section, key):
                        fragment = Fragment(html)
                        self.assertEqual(fragment.errors, [])
                        self.assertEqual(fragment.stack, [])

    def test_checkpoint_five_unique_questions_no_final_bank_aliases(self):
        final = {q['q'] for bank in self.data['quizzes'].values() for q in bank}
        seen = set()
        for group, questions in self.checkpoints.items():
            self.assertGreaterEqual(len(questions), 5)
            for q in questions:
                self.assertNotIn('bank', q)
                self.assertNotIn(q['q'], final)
                self.assertNotIn(q['q'], seen)
                seen.add(q['q'])
                self.assertTrue(q['theoryRefs'])
                self.assertTrue(set(q['theoryRefs']) <= self.sections.keys())
            last = [s for s in self.data['theory'] if s['substation'] == group][-1]
            self.assertIn('Контрольная точка', last['blocks'][-1]['html'])

    def test_numeric_body_and_frame_offsets(self):
        frames = read_capture(EXAMPLES / 'traffic_http_ok.pcap')
        request = layers(frames[3])
        response = layers(frames[5])
        self.assertEqual(len(request['payload']), 62)
        self.assertEqual(len(response['payload']), 105)
        self.assertEqual(frames[3]['raw'][34:38], bytes.fromhex('9c401f90'))
        self.assertEqual(frames[3]['raw'][54:57], b'GET')
        headers, body = response['payload'].split(b'\r\n\r\n', 1)
        self.assertIn(b'Content-Length: 15', headers)
        self.assertEqual(body, b'{"status":"ok"}')
        self.assertEqual(len(body), 15)

    def test_both_http_intervals_and_identical_bytes(self):
        regular = read_capture(EXAMPLES / 'traffic_http_ok.pcap')
        delayed = read_capture(EXAMPLES / 'traffic_http_delay.pcap')
        self.assertEqual([f['raw'] for f in regular], [f['raw'] for f in delayed])
        first = regular[5]['relative_us'] - regular[3]['relative_us']
        second = delayed[5]['relative_us'] - delayed[3]['relative_us']
        self.assertEqual((first, second, second - first, second // first), (50000, 500000, 450000, 10))

    def test_dns_pairing_prerequisites_and_sequence_wrap_are_taught(self):
        dns = ' '.join(fields(self.sections['traffic-dns-conversation'], 'html'))
        self.assertIn('адреса и порты', dns)
        self.assertIn('тип и класс', dns)
        self.assertIn('rfc5452', dns)
        seq = ' '.join(fields(self.sections['traffic-tcp-sequence-ledger'], 'html'))
        self.assertIn('по модулю 2³²', seq)
        window = ' '.join(fields(self.sections['traffic-tcp-window-boundaries'], 'html'))
        self.assertIn('cwnd', window)
        self.assertIn('внутреннее окно отправителя', window)

    def test_answer_lengths_not_systematic_hint(self):
        groups = list(self.data['quizzes'].items()) + list(self.checkpoints.items())
        for name, questions in groups:
            shortest = longest = 0
            for q in questions:
                chosen = len(q['options'][q['answer']])
                other = [len(o) for i, o in enumerate(q['options']) if i != q['answer']]
                longest += chosen > max(other)
                shortest += chosen < min(other)
            self.assertLess(longest / len(questions), .7, name + ':longest')
            self.assertLess(shortest / len(questions), .7, name + ':shortest')


if __name__ == '__main__':
    unittest.main()
