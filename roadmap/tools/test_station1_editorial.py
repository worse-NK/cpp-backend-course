"""Safe regression checks for the small examples added during station 1 editing.

Execution checks these examples, not the correctness of all C++ implementations
or the readability of the surrounding prose.
"""
import json
from pathlib import Path
import unittest

import test_expanded_examples

ROOT = Path(__file__).resolve().parents[1]


class StationOneEditorial(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "content/station1.json").read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}

    def code_with(self, section, marker):
        found = [b["code"] for b in self.sections[section]["blocks"]
                 if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(found), 1, (section, marker))
        return found[0]

    def test_public_section_addresses_and_progress_key_remain_stable(self):
        self.assertEqual(list(self.sections), [
            "learning-route", "from-c", "raii", "resource-taxonomy",
            "lifetime-storage", "local-object-journey", "references", "const",
            "const-and-aliases", "ownership-contracts", "new-delete",
            "smart-ptr", "smart-ptr-deep", "storage-and-construction",
            "shared-aliasing", "ownership-graph", "move", "rule-of-five",
            "copy-elision", "modern-syntax", "lambda-lifetime",
            "move-cost-model", "ownership-final-workbook",
        ])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station1_progress_v1")

    def test_stored_address_and_ownership_are_independent(self):
        fragment = self.code_with("shared-aliasing", "view(empty, &local)")
        self.check_cpp("#include <memory>\n#include <cassert>\nint main() {\n" +
                       fragment + r'''
    assert(view.get() == &local && view.use_count() == 0 && bool(view));
    assert(hidden.get() == nullptr && hidden.use_count() == 2 && !hidden);
    std::weak_ptr<int> weak = hidden;
    auto held = weak.lock();
    assert(!held && held.use_count() == 3);
    assert(!weak.expired());
    owner.reset();
    hidden.reset();
    assert(held.use_count() == 1 && !weak.expired());
    held.reset();
    assert(weak.expired());
}
''', "")

    def test_interview_applies_reference_rule_to_a_saved_copy(self):
        questions = [q for q in self.data["quizzes"]["interview"]
                     if "int snapshot = view;" in q["q"]]
        self.assertEqual(len(questions), 1)
        question = questions[0]
        self.assertEqual(question["options"][question["answer"]], "7 9")
        self.check_cpp(question["q"].split("\n\n", 1)[1], "7 9")

    def test_file_release_transfers_address_without_closing(self):
        definition = self.code_with("smart-ptr-deep", "struct FileCloser")
        fragment = self.code_with("smart-ptr-deep", "FilePtr next{file.release()}")
        # Use an anonymous temporary file, not a user's input.txt.
        fragment = fragment.replace('openFile("input.txt")', 'FilePtr{std::tmpfile()}')
        self.check_cpp(definition + r'''
#include <cassert>
#include <type_traits>
static_assert(std::is_nothrow_default_constructible_v<FileCloser>);
static_assert(std::is_nothrow_constructible_v<FilePtr, std::FILE*>);
int main() {
''' + fragment + r'''
    assert(next && !file && view == next.get());
    assert(std::fputs("ok", next.get()) >= 0);
    next.reset();
    assert(!next);
}
''', "")


if __name__ == "__main__":
    unittest.main()
