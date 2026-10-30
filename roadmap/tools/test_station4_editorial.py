"""Regression checks for station 4's examples, question programs and addresses.

Compiler runs check these concrete cases, not every language/API claim or the
readability of the chapter. Sources and editorial review remain separate checks.
"""
import json
from pathlib import Path
import unittest

from test_cpp_editorial_audit import ProseParser
import test_expanded_examples

ROOT = Path(__file__).resolve().parents[1]


class StationFourEditorial(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "content/station4.json").read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}

    def code_with(self, section, marker):
        found = [b["code"] for b in self.sections[section]["blocks"]
                 if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(found), 1, (section, marker))
        return found[0]

    def question_program(self, bank, index):
        question = self.data["quizzes"][bank][index]
        start = question["q"].find("#include")
        self.assertGreaterEqual(start, 0, (bank, index))
        return question["q"][start:]

    def test_section_addresses_and_progress_key_are_stable(self):
        self.assertEqual(list(self.sections), [
            "learning-route", "why-errors", "exceptions-vs-codes",
            "error-contracts", "failure-taxonomy", "channel-decision",
            "exceptions-basics", "exception-types", "raii-exceptions",
            "exception-timeline", "exception-object-matching",
            "catch-rethrow-context", "constructor-transaction",
            "exception-cost-and-array", "construction-cleanup",
            "exception-safety", "noexcept", "strong-guarantee-example",
            "transactional-updates", "noexcept-deep",
            "external-effects-guarantees", "practical", "expected-composition",
            "error-boundaries", "retry-idempotency", "context-and-logging",
            "reload-final-workbook", "summary",
        ])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station4_progress_v1")

    def test_self_check_cpp_notation_is_not_parsed_as_html(self):
        for section in self.sections.values():
            for index, block in enumerate(section["blocks"]):
                if block["type"] != "self-check":
                    continue
                for field in ("prompt", "answer"):
                    with self.subTest(section=section["id"], block=index, field=field):
                        parser = ProseParser()
                        parser.feed(block[field])
                        self.assertEqual(parser.unknown, [])

    def test_bounds_failure_skips_initialization_and_normal_path(self):
        self.check_cpp(self.question_program("basic", 8), "oor")

    def test_exception_ptr_retains_a_cause_after_catch(self):
        self.check_cpp(self.question_program("advanced", 4), "7")

    def test_rethrow_from_helper_uses_active_handler(self):
        self.check_cpp(self.question_program("interview", 3), "D")

    def test_ambiguous_base_does_not_match_catch(self):
        self.check_cpp(self.question_program("interview", 5), "F")

    def test_noexcept_expression_includes_argument_construction(self):
        self.check_cpp(self.question_program("interview", 8), "0")

    def test_from_chars_respects_the_explicit_end(self):
        self.check_cpp(self.question_program("interview", 9), "42 1 1")

    def test_optional_zero_differs_from_absence(self):
        self.check_cpp(self.code_with("exceptions-vs-codes", "findLimit"),
                       "0\nотсутствует")

    def test_expected_optional_three_states_use_different_branches(self):
        # The chapter marks this result type as C++23, not as part of C++20.
        fragment = self.code_with("channel-decision", "reportSearchFailure")
        source = r'''
#include <expected>
#include <iostream>
#include <optional>
struct Profile { int id; };
enum class SearchError { unavailable };
using Result = std::expected<std::optional<Profile>, SearchError>;
void reportSearchFailure(SearchError) { std::cout << "failure "; }
void reportNotFound() { std::cout << "absent "; }
void showProfile(const Profile& value) { std::cout << "profile" << value.id; }
void report(const Result& result) {
''' + fragment + r'''
}
int main() {
    report(Result{std::unexpected{SearchError::unavailable}});
    report(Result{std::optional<Profile>{}});
    report(Result{std::optional<Profile>{Profile{7}}});
}
'''
        self.check_cpp(source, "failure absent profile7", standard="c++23")

    def test_composite_invariant_can_fail_without_language_ub(self):
        question = self.data["quizzes"]["advanced"][8]
        for fact in ("capacity=5", "available=2", "reserved=3", "до 1"):
            self.assertIn(fact, question["q"])
        self.assertEqual(question["answer"], 1)
        # All integers are initialized. No container's invalid access or other
        # language precondition is violated: only this exercise's relation fails.
        self.check_cpp(r'''
#include <iostream>
int main() {
    const int capacity = 5;
    int available = 2;
    const int reserved = 3;
    try {
        available = 1;
        throw 7;
    } catch (int) {}
    std::cout << (available + reserved == capacity);
}
''', "0")

    def test_constructor_handler_cleans_then_rethrows_and_cannot_return(self):
        source = self.code_with("constructor-transaction",
                                "explicit Session(bool failSecond) try")
        self.check_cpp(source, "A B ~A ctor-catch outer")
        self.check_cpp(source.replace("session{true}", "session{false}"),
                       "A B body ~Session ~B ~A")
        self.check_cpp(source.replace("        throw;\n", ""),
                       "A B ~A ctor-catch outer")
        self.check_cpp(source.replace("        throw;", "        return;"),
                       valid=False)

    def test_new_mechanics_programs_match_their_explanations(self):
        examples = [
            ("exception-types", "int packet_size(int requested)",
             "packet size must be positive"),
            ("raii-exceptions", "std::make_unique<Buffer>()", "release caught"),
            ("catch-rethrow-context", 'std::cout << "saved ";',
             "saved load failed"),
            ("construction-cleanup", "class ScopeProbe", "caught 1 0"),
        ]
        for section, marker, output in examples:
            with self.subTest(section=section):
                self.check_cpp(self.code_with(section, marker), output)


if __name__ == "__main__":
    unittest.main()
