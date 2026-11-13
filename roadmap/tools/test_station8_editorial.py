"""Regressions for the readable HTTP/API chapter and its bounded examples.

No public socket, credentials, remote service or administrative command is used.
Arithmetic below checks the stated teaching models, not measured service latency.
Payload hashes protect the code/diagrams retained in the editorial-only pass.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from build_stations import validate
from checkpoint_data import normalize_prompt, with_checkpoints
from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]
IDS = '''learning-route api-client-server resource-representation rest-constraints
task-contract method-semantics create-read replace-patch status-contracts
content-negotiation operation-resource request-boundaries json-domain
validation-pipeline problem-details error-boundaries expected-input-http-cpp23
framework-choice
handler-layers httplib-example threading-lifetime request-execution-workbook
middleware-chain framework-checkpoint lost-update conditional-update
cache-validation retry-uncertainty idempotency-state retry-budget-workbook
atomic-service identity-permissions tenant-scope session-token
identity-lifecycle-workbook browser-origin cors-csrf security-limits
openapi-contract openapi-operation-workbook compatibility compatibility-rollout
pagination collection-filters batch-projection-workbook versioning
architecture-boundaries rpc-grpc protobuf-evolution grpc-call-workbook
rpc-choice-workbook dependency-fanout-workbook protobuf-file-workbook
format-cost-workbook streaming-choice sse-reconnect websocket-contract
event-recovery-workbook webhooks observations contract-tests framework-limits
replica-state-workbook project-review api-final-workbook
api-update-final-workbook summary'''.split()


class StationEightEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / 'content/station8.json'
        cls.data = json.loads(cls.path.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def prose(self, sid):
        section = self.sections[sid]
        return section['lead'] + ' '.join(
            b.get('html', '') + ' ' + b.get('prompt', '') + ' ' + b.get('answer', '')
            for b in section['blocks'])

    def code(self, sid, index=0):
        return [b['code'] for b in self.sections[sid]['blocks']
                if b['type'] == 'code'][index]

    def test_structure_progress_and_prerequisites(self):
        validate(self.data, self.path)
        self.assertEqual(list(self.sections), IDS)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station8_progress_v1')
        self.assertEqual(len(self.data['substations']), 9)
        self.assertEqual([len(self.data['quizzes'][k]) for k in
                          ('basic', 'advanced', 'interview')], [57, 66, 53])
        self.assertEqual(len(self.data['tasks']), 32)

    def test_original_code_and_visual_payload_order(self):
        # Keep the original 34-listing snapshot strict.  The later C++23
        # addition has a separate payload contract below, not a silent skip.
        original = [s for s in self.data['theory']
                    if s['id'] != 'expected-input-http-cpp23']
        code = [(s['id'], b['code']) for s in original
                for b in s['blocks'] if b['type'] == 'code']
        visual = [(s['id'], b) for s in original
                  for b in s['blocks'] if b['type'] in
                  ('visual', 'diagram', 'lab', 'lanes', 'exchange')]
        def digest(value):
            return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(len(code), 34)
        self.assertEqual(digest(code),
                         'd7090e7770dd8a3fec06d76667050a465496010d537e1c1d04db17429f333152')
        # 2026-11-05: all 66 blocks were compared structurally with the
        # pre-stage course-gap baseline, with no differences.  This rebases
        # the outdated visual hash; it does not reconstruct an unavailable
        # earlier snapshot or excuse future visual payload changes.
        self.assertEqual(len(visual), 66)
        self.assertEqual(digest(visual),
                         'd507eff0500a0b4830adad0cf2425975045c25e4629c76e91f4b04fd1d2ed4d7')

    def test_cpp23_addition_has_a_separate_strict_payload_contract(self):
        section = self.sections['expected-input-http-cpp23']
        blocks = [b for b in section['blocks'] if b['type'] == 'code']
        self.assertEqual(len(blocks), 6)
        self.assertEqual([b.get('standard') for b in blocks[:5]], ['23'] * 5)
        listings = [b for b in blocks if 'exampleId' in b]
        self.assertEqual([b['exampleId'] for b in listings], ['s8-expected-http'])
        self.assertEqual(listings[0]['code'].strip(),
                         (ROOT / 'examples/cpp23/s8-expected-http.cpp').read_text().strip())
        payload = [b['code'] for b in blocks]
        self.assertEqual(hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest(),
                         '814b3283f1f2a8c1404c53c07af686f2c69de77f2f09251edd541a425f3afb90')
        self.assertFalse(any(b['type'] in ('visual', 'diagram', 'lab', 'lanes', 'exchange')
                             for b in section['blocks']))

    def test_each_section_has_a_revealable_reasoning_check(self):
        for sid, section in self.sections.items():
            with self.subTest(section=sid):
                checks = [b for b in section['blocks'] if b['type'] == 'self-check']
                self.assertTrue(checks)
                for check in checks:
                    self.assertTrue(check['prompt'].strip())
                    self.assertTrue(check['answer'].strip())
                    for name in ('prompt', 'answer'):
                        parser = ProseParser()
                        parser.feed(check[name])
                        self.assertEqual(parser.unknown, [], (sid, name))

    def test_checkpoint_refs_are_valid_and_have_five_questions(self):
        checkpoints = with_checkpoints(self.data)['checkpoints']
        self.assertEqual(set(checkpoints),
                         {m['id'] for m in self.data['substations']})
        selected = set()
        for module, questions in checkpoints.items():
            self.assertGreaterEqual(len(questions), 5, module)
            for question in questions:
                # Resolution validates both stable bank references and
                # independently authored inline questions without mutating
                # their canonical banks.  No bank/index shape is assumed.
                key = normalize_prompt(question['q'])
                self.assertNotIn(key, selected)
                selected.add(key)
                self.assertEqual(question['substation'], module)
                self.assertTrue(question['theoryRefs'])

    def test_choices_do_not_have_one_dominant_length_shortcut(self):
        # A warning threshold, not a claim that choices are equally plausible.
        for kind, questions in self.data['quizzes'].items():
            for extreme in (min, max):
                hits = 0
                for q in questions:
                    sizes = [len(re.sub('<[^>]+>', '', o)) for o in q['options']]
                    target = extreme(sizes)
                    hits += sizes[q['answer']] == target and sizes.count(target) == 1
                self.assertLessEqual(hits / len(questions), .5,
                                     (kind, extreme.__name__, hits))

    def test_http_excerpt_not_presented_as_complete_wire_request(self):
        self.assertIn('сокращённая иллюстрация', self.prose('content-negotiation'))
        self.assertIn('обрамление опущены', self.sections['resource-representation']['blocks'][1]['caption'])
        self.assertIn('архитектурный стиль', self.sections['rest-constraints']['lead'])

    def test_independent_workbook_contracts_are_explicit(self):
        self.assertIn('40 байтами', self.prose('api-update-final-workbook'))
        self.assertIn('200', self.prose('api-update-final-workbook'))
        self.assertIn('Update::invalid', self.prose('api-update-final-workbook'))
        self.assertIn('другой ограниченный пример', self.prose('openapi-operation-workbook'))
        self.assertIn('не является', self.prose('protobuf-file-workbook'))
        self.assertNotIn('Completedd', json.dumps(self.data, ensure_ascii=False))

    def test_retry_and_fanout_budget_examples(self):
        work_deadline = 600 - 50
        after_two = 180 + 60 + 180
        self.assertEqual(after_two, 420)
        self.assertEqual(work_deadline - after_two - 120, 10)
        self.assertLess(work_deadline - after_two - 120, 50)
        self.assertEqual(15 + 40 + 60 + 140 + 10, 265)
        self.assertEqual(15 + 40 + max(60, 140) + 10, 205)
        self.assertEqual(55 + max(60, 80) + 10, 145)
        self.assertEqual(230 - 55, 175)

    def test_cache_age_and_percentile_examples(self):
        request_time, response_time, date, age, now = 100, 102, 80, 20, 130
        initial_age = max(max(0, response_time - date), age + response_time - request_time)
        self.assertEqual(initial_age + now - response_time, 50)
        self.assertFalse(20 + 40 < 60)  # Equality is not freshness.
        observations = [10] * 1000 + [1000] * 10
        self.assertEqual(observations[math.ceil(.99 * len(observations)) - 1], 10)
        self.assertEqual((10 + 1000) / 2, 505)
        self.assertNotEqual(10, 505)

    def test_complete_snapshot_and_queue_are_different_models(self):
        version = 8
        applied = []
        for new in (8, 10, 9):
            if new > version:
                version = new
                applied.append(new)
        self.assertEqual(applied, [10])
        self.assertEqual(200 / (120 - 80), 5)
        self.assertAlmostEqual(1000 * 200 * 1024 / 1024 ** 2, 195.3125)

    @unittest.skipUnless(shutil.which('g++'), 'g++ required')
    def test_final_core_validates_before_version_without_partial_update(self):
        # Complete source as given, with main replaced by a focused caller.
        source = self.code('api-update-final-workbook', 2).split('int main()', 1)[0]
        source += r'''
int main() {
    Store store;
    if (store.replace(7, std::string(41, 'x'), true) != Update::invalid) return 1;
    if (store.replace(7, "B", false) != Update::applied) return 2;
    if (store.replace(7, "", true) != Update::invalid) return 3;
    if (store.replace(7, "C", true) != Update::stale) return 4;
    auto t=store.read();
    std::cout << t.title << ' ' << t.done << ' ' << t.version;
}
'''
        with tempfile.TemporaryDirectory(prefix='station8-editorial-') as directory:
            binary = Path(directory) / 'core'
            build = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra',
                                    '-pedantic', '-pthread', '-x', 'c++', '-',
                                    '-o', str(binary)], input=source, text=True,
                                   capture_output=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, 'B 0 8')


if __name__ == '__main__':
    unittest.main()
