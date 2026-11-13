"""Version-aware listing/runner regressions, not a proof of all course prose."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cpp_examples as runner
from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]


class EditionInfrastructure(unittest.TestCase):
    def test_listing_schema(self):
        data = json.loads((ROOT / 'content/station0.json').read_text())
        block = next(b for s in data['theory'] for b in s['blocks'] if b['type'] == 'code')
        block.update(exampleId='schema-test-listing', standard='20/23')
        validate(data, ROOT / 'content/station0.json')
        for bad in [23, '17', [], None]:
            block['standard'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate(data, ROOT / 'content/station0.json')
        block['standard'] = '23'
        duplicate = deepcopy(block)
        data['theory'][0]['blocks'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'duplicate listing'):
            validate(data, ROOT / 'content/station0.json')

    def test_capability_is_not_a_successful_skip(self):
        check = {'standard':'23', 'mode':'run', 'requires':{'__cpp_lib_generator':202207}}
        with patch.object(runner, 'invoke', side_effect=AssertionError('unsupported source must not execute')):
            status, detail = runner.check_case('unused', 'int main(){}', check, {})
        self.assertEqual(status, 'UNSUPPORTED')
        self.assertIn('__cpp_lib_generator', detail)

    def test_source_only_never_executes_undefined_behavior(self):
        with patch.object(runner, 'invoke', side_effect=AssertionError('source-only must not execute')):
            status, detail = runner.check_case('unused', 'undefined()', {'standard':'20','mode':'source-only','reason':'dangling reference'}, {})
        self.assertEqual(status, 'SOURCE_ONLY')

    def test_compile_run_fail_and_mismatching_output(self):
        for check, source, result in [
            ({'standard':'20','mode':'run','stdout':'ok\n'}, '#include <iostream>\nint main(){std::cout<<"ok\\n";}', 'PASS'),
            ({'standard':'20','mode':'compile-fail'}, 'int main(){ missing(); }', 'PASS'),
            ({'standard':'20','mode':'compile-fail'}, 'int main(){}', 'FAIL'),
            ({'standard':'20','mode':'run','stdout':'wrong'}, 'int main(){}', 'FAIL'),
        ]:
            with self.subTest(mode=check['mode'], result=result):
                self.assertEqual(runner.check_case('g++', source, check, {})[0], result)

    def test_manifest_covers_all_stable_ids(self):
        cases, indexed = runner.load_manifest()
        self.assertTrue(indexed)
        self.assertEqual(set(indexed), {c['exampleId'] for c in cases if 'exampleId' in c})
        for case in cases:
            if 'exampleId' not in case:
                continue
            standard = indexed[case['exampleId']][0]['standard']
            checked = {c['standard'] for c in case['checks'] if c['mode'] != 'source-only'}
            if standard == '20/23':
                self.assertEqual(checked, {'20','23'}, case['id'])

    def test_compiler_crash_is_not_an_expected_rejection(self):
        crashed = subprocess.CompletedProcess(['compiler'], -9, '', 'killed')
        with patch.object(runner, 'invoke', return_value=crashed):
            status, detail = runner.check_case('compiler', 'int main(){}',
                                             {'standard':'20', 'mode':'compile-fail'}, {})
        self.assertEqual(status, 'FAIL')
        self.assertIn('signal 9', detail)

    def test_preserve_existing_identities_and_code_contracts(self):
        # New content has stable listing IDs; existing indexed tests remain.
        for path in (ROOT / 'content').glob('station*.json'):
            data = json.loads(path.read_text())
            self.assertEqual(data['meta']['id'], path.stem)
            ids = {s['id'] for s in data['theory']}
            for questions in data['quizzes'].values():
                for q in questions:
                    self.assertTrue(set(q.get('theoryRefs', [])) <= ids)


if __name__ == '__main__':
    unittest.main()
