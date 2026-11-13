"""Optional Linux/network scope: schema, native compilation, safety guards.

Default execution does NOT start QEMU or perform host network mutations.
--run-ipc additionally runs only our own AF_UNIX parent/child examples.
--vm-evidence FILE validates a previously captured full guest console log;
it is not a substitute for starting the actual guest. A denied real run fails.
"""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

from build_stations import load_json, validate
from checkpoint_data import with_checkpoints

ROOT = Path(__file__).resolve().parents[1]
UNIX = ROOT / 'examples/unix-ipc'
NETWORK = ROOT / 'examples/network-specialization'
IDS = {
    'station5-linux': ['linux-unix-sockets', 'linux-unix-descriptor-transfer'],
    'station7-netlab': ['netlab-vlan-boundaries', 'netlab-stp-loop-recovery',
                        'netlab-ospf-route-convergence', 'netlab-bgp-policy-choice'],
}
EXPECTED = {
    'socketpair_stream': 'reply: accepted job:41\n',
    'descriptor_transfer': 'child_prefix=shared\nparent_tail=:41\nfd_cloexec=true\ncredential_uid_match=true\n',
}

class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attr = dict(attrs); href = attr.get('href', '')
        if tag == 'a' and href.startswith('examples/'):
            assert 'download' in attr, href
            assert (ROOT / href).is_file(), href

def checked(command, **kwargs):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True,
                            timeout=kwargs.pop('timeout', 30), **kwargs)
    if result.returncode:
        raise AssertionError('Command failed: ' + str(command) + '\n' + result.stdout + result.stderr)
    return result

def compile_examples(directory, standard):
    result = {}
    for name in EXPECTED:
        target = directory / (name + '-' + standard)
        checked(['g++', '-std=c++' + standard, '-Wall', '-Wextra', '-Wpedantic',
                 '-Werror', UNIX / (name + '.cpp'), '-o', target])
        result[name] = target
    return result

def run_owned(binary):
    with subprocess.Popen([binary], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, start_new_session=True) as process:
        try: out, err = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise AssertionError('Owned IPC process group exceeded 10 seconds')
        if process.returncode: raise AssertionError(out + err)
        assert not err, err
        return out

class OptionalNetworkLinux(unittest.TestCase):
    def test_canonical_schema_and_optional_boundaries(self):
        for station, ids in IDS.items():
            path = ROOT / 'content' / (station + '.json')
            data = load_json(path); validate(data, path)
            for ref in ids:
                section = next(s for s in data['theory'] if s['id'] == ref)
                self.assertIn('Необязательное', section['title'])
                self.assertGreaterEqual(len([b for b in section['blocks'] if b['type'] == 'self-check']), 2)
                self.assertTrue(any('пропуст' in b.get('html', '').lower() or 'можно' in b.get('html', '').lower()
                                    for b in section['blocks'][:2]))
                for bank in ['basic', 'advanced', 'interview']:
                    self.assertTrue(any(ref in q.get('theoryRefs', []) for q in data['quizzes'][bank]), (ref, bank))
                for block in section['blocks']:
                    for key in ['html', 'prompt', 'answer']:
                        if key in block:
                            self.assertNotIn('\\"', block[key])
                            Links().feed(block[key])

    def test_existing_checkpoints_remain_core(self):
        for station, ids in IDS.items():
            data = load_json(ROOT / 'content' / (station + '.json'))
            integrated = with_checkpoints(data)
            # Optional work does not silently become mandatory checkpoint material.
            for section in integrated['theory']:
                for block in section['blocks']:
                    if block.get('type') == 'checkpoint':
                        for question in block.get('questions', []):
                            self.assertFalse(set(ids) & set(question.get('theoryRefs', [])))
            plan = load_json(ROOT / 'content/checkpoints' / (station + '.json'))
            for entries in plan['modules'].values():
                for entry in entries:
                    if 'bank' not in entry:
                        self.assertFalse(set(ids) & set(entry.get('theoryRefs', [])))
            end = 'linux-fd-ownership' if station == 'station5-linux' else 'netlab-packet-walk'
            module = 'descriptors' if station == 'station5-linux' else 'ethernet-routing'
            sections = [s for s in data['theory'] if s.get('substation') == module]
            self.assertEqual(sections[-1]['id'], end)
            self.assertIn('Контрольная точка', sections[-1]['blocks'][-1]['html'])

    def test_native_compilation_cpp20_and_cpp23(self):
        with tempfile.TemporaryDirectory(prefix='course-unix-test-') as directory:
            for standard in ['20', '23']: compile_examples(Path(directory), standard)

    def test_guest_refuses_direct_host_execution(self):
        result = subprocess.run([sys.executable, str(NETWORK / 'guest.py')],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing:', result.stdout + result.stderr)

    def test_runner_refuses_unowned_directory(self):
        result = subprocess.run([sys.executable, str(NETWORK / 'run_vm.py'), '/tmp'],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Expected', result.stdout + result.stderr)
        source = (NETWORK / 'run_vm.py').read_text()
        self.assertIn("'-nic', 'none'", source)
        self.assertIn("'-nodefaults'", source)
        self.assertNotIn("'-drive'", source)
        self.assertNotIn("'-virtfs'", source)
        self.assertNotIn("'-fsdev'", source)

def check_evidence(path):
    console = path.read_text()
    assert 'COURSE_OPTIONAL_VM_EXIT=0' in console
    lines = [line for line in console.splitlines() if line.startswith('COURSE_OPTIONAL_EVIDENCE=')]
    assert len(lines) == 1, 'Need one actual full guest summary'
    value = json.loads(lines[0].split('=', 1)[1])
    assert set(value) == {'scope', 'kernel', 'frr', 'vlan', 'stp', 'ospf', 'bgp'}
    assert value['kernel'] == '6.8.0-142-generic'
    assert '8.4.4' in value['frr']
    vlan = value['vlan']
    assert vlan['same_vlan'] and not vlan['different_vlan']
    assert not vlan['trunk_vlan_removed'] and vlan['restored']
    stp = value['stp']
    assert stp['before']['s3']['to2'] == 'blocking'
    assert stp['after']['s3']['to2'] == 'forwarding'
    ospf = value['ospf']
    assert any(h.get('ip') == '192.0.2.2' for h in ospf['before']['nexthops'])
    assert any(h.get('ip') == '192.0.2.10' for h in ospf['after']['nexthops'])
    assert 'via 192.0.2.10' in ospf['kernel_route_after']
    for field, hop in [('before', '192.0.2.2'), ('after_withdraw', '192.0.2.6')]:
        paths = value['bgp'][field]['paths']
        best = [p for p in paths if p.get('bestpath', {}).get('overall')]
        assert len(best) == 1 and any(h.get('ip') == hop for h in best[0]['nexthops'])
    candidates = {p['peer']['peerId']: p for p in value['bgp']['before']['paths']}
    assert set(candidates) == {'192.0.2.2', '192.0.2.6'}, 'Need both valid competing candidates, not first arrival'
    assert all(p['valid'] for p in candidates.values())
    assert candidates['192.0.2.2']['locPrf'] == 200 and candidates['192.0.2.2']['aspath']['length'] == 3
    assert candidates['192.0.2.6']['locPrf'] == 100 and candidates['192.0.2.6']['aspath']['length'] == 1
    assert 'via 192.0.2.6' in value['bgp']['kernel_route_after']
    return value

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-ipc', action='store_true')
    parser.add_argument('--vm-evidence', type=Path)
    args, tests = parser.parse_known_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OptionalNetworkLinux))
    if not result.wasSuccessful(): raise SystemExit(1)
    if args.run_ipc:
        with tempfile.TemporaryDirectory(prefix='course-unix-run-') as directory:
            for standard in ['20', '23']:
                for name, binary in compile_examples(Path(directory), standard).items():
                    assert run_owned(binary) == EXPECTED[name], (name, standard)
        print('Actual own AF_UNIX stream + rights programs: PASS (C++20 and C++23)')
    else: print('Actual IPC execution: NOT RUN (use --run-ipc); compilation only is not execution evidence')
    if args.vm_evidence:
        check_evidence(args.vm_evidence)
        print('Full actual guest console evidence: PASS')
    else: print('Actual VM acceptance: NOT RUN by this invocation; no simulated result counted as PASS')
