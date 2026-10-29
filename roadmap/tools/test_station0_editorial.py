"""Execute the examples used to teach access, const and object identity.

These checks protect example behaviour, not the literary quality of prose.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'), 'C++20 compiler unavailable')
class StationZeroExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / 'content/station0.json').read_text())
        cls.sections = {s['id']: s for s in data['theory']}

    def code(self, sid, index=0, *, containing=None):
        candidates = [b['code'] for b in self.sections[sid]['blocks']
                      if b['type'] == 'code']
        if containing is not None:
            required = (containing,) if isinstance(containing, str) else containing
            candidates = [code for code in candidates if all(part in code for part in required)]
        return candidates[index]

    def compile(self, source, expected='', *, valid=True):
        with tempfile.TemporaryDirectory(prefix='station0-editorial-test-') as directory:
            binary = str(Path(directory) / 'example')
            args = ['g++', '-std=c++20', '-Wall', '-Wextra', '-pedantic-errors',
                    '-x', 'c++', '-', '-o', binary]
            if not valid:
                args = args[:-2] + ['-fsyntax-only']
            result = subprocess.run(args, input=source, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode == 0, valid, result.stderr)
            if valid:
                run = subprocess.run([binary], capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), expected)

    def definition(self, sid, index=0, *, containing=None):
        return self.code(sid, index, containing=containing).split('int main()', 1)[0]

    def test_first_worked_call_matches_output(self):
        self.compile(self.code('why-oop', containing='#include'), '1 2')

    def test_attempts_reject_repeated_calls_at_zero(self):
        self.compile(self.definition('why-oop', containing='#include') + r'''
#include <cassert>
int main() {
    Attempts login;
    Attempts independent;
    assert(login.remaining() == 3);
    for (int left = 2; left >= 0; --left) {
        assert(login.try_use());
        assert(login.remaining() == left);
    }
    for (int i = 0; i < 10; ++i) {
        assert(!login.try_use());
        assert(login.remaining() == 0);
    }
    assert(independent.remaining() == 3);
    const Attempts read_only;
    assert(read_only.remaining() == 3);
}
''')

    def test_closed_field_rejects_external_read_and_write(self):
        prefix = self.definition('why-oop', containing='#include')
        for expression in ('login.remaining_ = -5;', '(void)login.remaining_;'):
            with self.subTest(expression=expression):
                self.compile(prefix + 'int main() { Attempts login; ' + expression + ' }', valid=False)

    def test_const_does_not_make_mutating_method_callable(self):
        self.compile(self.definition('why-oop', containing='#include') +
                     'int main() { const Attempts login; login.try_use(); }', valid=False)

    def test_account_validates_before_changing_balance(self):
        self.compile(self.definition('encapsulation') + r'''
#include <cassert>
int main() {
    Account account;
    const int maximum = std::numeric_limits<int>::max();
    assert(!account.deposit(-1) && account.getBalance() == 0);
    assert(!account.deposit(0) && account.getBalance() == 0);
    assert(account.deposit(maximum - 5));
    assert(!account.deposit(6) && account.getBalance() == maximum - 5);
    assert(account.deposit(5) && account.getBalance() == maximum);
    assert(!account.deposit(1) && account.getBalance() == maximum);
}
''')

    def test_returned_reference_aliases_but_value_declaration_copies(self):
        self.compile(self.definition('this', containing=('#include', 'return *this;')) + r'''
#include <cassert>
int main() {
    Point original;
    Point& alias = original.setX(9);
    assert(&alias == &original);
    alias.setX(12);
    assert(original.getX() == 12);
    Point copy = original.setX(9);
    copy.setX(10);
    assert(original.getX() == 9 && copy.getX() == 10);
}
''')

    def test_interval_continuation_preserves_both_bounds_after_refusal(self):
        self.compile(self.code('invariants', 0) + '\n' +
                     self.code('invariants', 1), '0 10 20\n1 30 40')

    def test_named_factory_continuation_creates_a_single_point_interval(self):
        self.compile(self.code('valid-states-factories', 0) + '\n' +
                     self.code('valid-states-factories', 1), '10 20\n7 7')

    def test_quiz_value_initialization_uses_the_shown_defaulted_constructor(self):
        data = json.loads((ROOT / 'content/station0.json').read_text())
        question = data['quizzes']['advanced'][13]
        self.assertEqual(question['answer'], 2)
        fragment = question['q'].split('\n\n', 1)[1]
        # The uninitialized a.value is deliberately not read.
        self.compile('#include <iostream>\nint main() {\n' + fragment +
                     '\nstd::cout << b.value;\n}', '0')


if __name__ == '__main__':
    unittest.main()
