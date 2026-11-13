"""Offline verification of REAL retained captures, not a synthetic PCAP generator.

The VM itself is a separate, explicit integration run. These tests never create
namespaces, sockets or host network rules.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from build_stations import validate
from checkpoint_data import with_checkpoints
from test_linux_systems import Fragment

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples/tcp-observation'


def checksum(data):
    if len(data) % 2:
        data += b'\0'
    value = sum(struct.unpack('!' + str(len(data) // 2) + 'H', data))
    while value >> 16:
        value = (value & 65535) + (value >> 16)
    return value


def packets(raw):
    assert struct.unpack_from('<IHH', raw) == (0xa1b2c3d4, 2, 4)
    assert struct.unpack_from('<I', raw, 20)[0] == 1  # real Ethernet
    offset = 24
    while offset < len(raw):
        sec, micros, captured, original = struct.unpack_from('<IIII', raw, offset)
        offset += 16
        assert sec > 0 and 0 <= micros < 1000000 and captured == original
        assert offset + captured <= len(raw)
        yield raw[offset:offset + captured]
        offset += captured
    assert offset == len(raw)


class TCPObservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((EXAMPLES / 'captures/report.json').read_text())

    def test_four_real_scenarios_and_provenance(self):
        self.assertIn('Real packets', self.report['scope'])
        self.assertFalse(self.report['environment']['external_nic'])
        self.assertEqual(self.report['environment']['kernel'], '6.8.0-142-generic')
        self.assertEqual([s['name'] for s in self.report['scenarios']],
                         ['baseline', 'delay', 'loss', 'slow-reader'])
        for name in ('kernel_sha256', 'initrd_sha256'):
            self.assertRegex(self.report[name], r'^[0-9a-f]{64}$')

    def test_every_retained_frame_checksums_headers_and_manifest(self):
        for scenario in self.report['scenarios']:
            capture = scenario['capture'][0]
            raw = (EXAMPLES / 'captures' / capture['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), capture['sha256'])
            self.assertEqual(len(raw), capture['bytes'])
            self.assertEqual(capture['socket_drops'], 0)
            self.assertEqual(capture['window_seconds'], 4)
            count = zero = 0
            for frame in packets(raw):
                self.assertEqual(frame[12:14], b'\x08\x00')
                ip = frame[14:]
                ihl = (ip[0] & 15) * 4
                self.assertEqual(ip[0] >> 4, 4)
                self.assertEqual(ip[9], 6)
                self.assertEqual(checksum(ip[:ihl]), 65535)
                self.assertEqual(len(ip), int.from_bytes(ip[2:4], 'big'))
                tcp = ip[ihl:]
                self.assertIn(9100, struct.unpack('!HH', tcp[:4]))
                pseudo = ip[12:20] + b'\x00\x06' + len(tcp).to_bytes(2, 'big')
                self.assertEqual(checksum(pseudo + tcp), 65535,
                                 'Disable checksum offload in the guest; do not rewrite captured bytes')
                zero += tcp[14:16] == b'\0\0'
                count += 1
            self.assertEqual(count, capture['packets'])
            self.assertEqual(zero, capture['zero_windows'])

    def test_loss_evidence_and_application_success_are_distinct(self):
        loss = next(s for s in self.report['scenarios'] if s['name'] == 'loss')
        self.assertGreater(loss['client']['total_retrans'], 0)
        self.assertGreater(sum(q['drops'] for q in loss['qdisc']), 0)
        self.assertEqual(loss['capture'][0]['repeated_exact_ranges'], 0)
        for s in self.report['scenarios'][:3]:
            self.assertEqual(s['client']['sent'], 256 * 1024)
            self.assertEqual(s['client']['sha256'], s['server'][0]['sha256'])
            self.assertEqual(s['server'][0]['received'], 256 * 1024)
        slow = self.report['scenarios'][3]
        self.assertGreater(slow['capture'][0]['zero_windows'], 0)
        self.assertGreater(slow['server'][0]['eagain'], 0)
        self.assertEqual(slow['client']['received'], 2 * 1024 * 1024)
        self.assertEqual(slow['client']['sha256'], hashlib.sha256(b'x' * (2 * 1024 * 1024)).hexdigest())

    def test_public_builder_and_runner_do_not_depend_on_private_tools(self):
        builder = (EXAMPLES / 'build_vm.py').read_text()
        runner = (EXAMPLES / 'run_vm.py').read_text()
        self.assertNotIn('from build_netlab_vm', builder)
        self.assertIn("'--no-user-config'", runner.replace("'-no-user-config'", "'--no-user-config'"))
        self.assertIn("'-nic','none'", runner)
        for disallowed in ("'-drive'", "'-virtfs'", "'hostfwd'", "'sudo'"):
            self.assertNotIn(disallowed, builder + runner)
        for script in ('build_vm.py', 'run_vm.py'):
            result = subprocess.run([sys.executable, str(EXAMPLES / script), str(EXAMPLES)],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Expected', result.stderr)
        init = (EXAMPLES / 'guest_init.sh').read_text()
        self.assertLess(init.index('[ "$$" = "1" ]'), init.index('mount -t proc'))
        program = (EXAMPLES / 'experiment.py').read_text()
        for guard in ('os.getppid()!=1', "course_gap_acceptance=1", "{\'lo\'}",
                      "'tx','off','rx','off'", 'assert dropped==0'):
            self.assertIn(guard, program)

    def test_learning_material_is_integrated_and_has_no_final_checkpoint_copy(self):
        for name, section_id in [('station7-netlab', 'netlab-tcp-loss-slow-reader'),
                                 ('station7-traffic', 'traffic-real-tcp-evidence')]:
            path = ROOT / 'content' / (name + '.json')
            data = json.loads(path.read_text())
            validate(data, path)
            resolved = with_checkpoints(data)
            section = next(s for s in data['theory'] if s['id'] == section_id)
            for b in section['blocks']:
                for field in ('html', 'prompt', 'answer'):
                    fragment = Fragment(b.get(field, ''))
                    self.assertEqual(fragment.errors, [])
                    self.assertEqual(fragment.stack, [])
            self.assertTrue(any(b['type'] == 'self-check' for b in section['blocks']))
            bank = {q['q'] for questions in data['quizzes'].values() for q in questions}
            for questions in resolved['checkpoints'].values():
                for q in questions:
                    if section_id in q['theoryRefs']:
                        self.assertNotIn(q['q'], bank)
            task = next(t for t in data['tasks'] if section_id in t['theoryRefs'])
            self.assertTrue(task['title'].startswith('Лаборатория: '))
            self.assertGreaterEqual(len(task['checks']), 4)


if __name__ == '__main__':
    unittest.main()
