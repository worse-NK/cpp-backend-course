"""Safe examples used in the station 2 editorial pass.

These checks compare concrete examples with their explanations. They do not
prove all language guarantees or replace the primary-source review.
"""
import json
from pathlib import Path
import unittest

import test_expanded_examples
from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]


class StationTwoEditorial(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "content/station2.json").read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}

    def code_with(self, section, marker):
        found = [b["code"] for b in self.sections[section]["blocks"]
                 if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(found), 1, (section, marker))
        return found[0]

    def test_stable_section_addresses_and_progress(self):
        self.assertEqual(list(self.sections), [
            "learning-route", "why-inherit", "inheritance-design", "protected",
            "inheritance-access", "substitution-contract", "ctor-order",
            "multiple-inheritance", "interview-lifetime", "virtual",
            "static-dynamic-view", "virtual-edge-cases", "vtable",
            "polymorphism", "abstract", "virtual-dtor", "slicing",
            "polymorphic-copy", "polymorphic-boundary", "wrappers-and-patterns",
            "nvi-interface-evolution", "rtti", "closed-open-polymorphism",
            "polymorphism-final-workbook", "summary",
        ])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station2_progress_v1")

    def test_base_reference_uses_the_existing_base_part(self):
        source = self.code_with("why-inherit", 'Dog d("Рекс")')
        definitions, calls = source.split('\nDog d(', 1)
        reference = self.code_with("why-inherit", "Animal& animal = d;")
        prefix = "#include <string>\n#include <iostream>\n" + definitions
        program = prefix + '\nint main() {\nDog d(' + calls + '\n' + reference + '\n}'
        self.check_cpp(program, "Рекс ест\nРекс гавкает\nРекс ест")
        self.check_cpp(program.replace("// animal.bark();", "animal.bark();"), valid=False)

    def test_limited_log_example_and_boundaries(self):
        definition = self.code_with("substitution-contract", "class LimitedLog")
        program = self.code_with("substitution-contract", "LimitedLog log{2};")
        self.check_cpp(definition + "\n" + program, "1 1 0 2")
        self.check_cpp(definition + r'''
#include <cassert>
int main() {
    for (std::size_t limit : {0u, 1u, 2u, 10u}) {
        LimitedLog log{limit};
        for (std::size_t count = 0; count < limit; ++count) {
            assert(log.try_append(7));
            assert(log.size() == count + 1);
        }
        for (int attempt = 0; attempt < 3; ++attempt) {
            assert(!log.try_append(9));
            assert(log.size() == limit);
        }
    }
}
''', "")

    def test_private_base_is_accessible_inside_but_not_outside(self):
        prefix = r'''
struct Base {};
class Child : private Base {
public:
    Base* base_part() { return this; }
};
'''
        self.check_cpp(prefix + "int main() { Child child; Base* p = child.base_part(); return !p; }", "")
        self.check_cpp(prefix + "int main() { Child child; Base* p = &child; }", valid=False)

    def test_typeid_evaluation_matches_the_expression_kind(self):
        self.check_cpp(self.code_with("rtti", "Base& touch(Base& object)"), "0 1")

    def test_self_check_templates_are_visible_not_html_tags(self):
        for number in (1, 2):
            data = json.loads((ROOT / f"content/station{number}.json").read_text())
            for section in data["theory"]:
                for block in section["blocks"]:
                    if block["type"] != "self-check":
                        continue
                    for field in ("prompt", "answer"):
                        with self.subTest(station=number, section=section["id"], field=field):
                            parser = ProseParser()
                            parser.feed(block[field])
                            self.assertEqual(parser.unknown, [])

    def test_qualified_interview_call_keeps_base_default_and_body(self):
        question = next(q for q in self.data["quizzes"]["interview"]
                        if "b.B::f();" in q["q"])
        self.assertEqual(question["options"][question["answer"]], "B1")
        self.check_cpp(question["q"].split("\n\n", 1)[1], "B1")

    def test_wrapper_order_changes_which_operation_is_reached(self):
        adapter = self.code_with("wrappers-and-patterns", "class PrinterAdapter")
        prefix = adapter.split("\nint main()", 1)[0]
        prefix += "\n" + self.code_with("wrappers-and-patterns", "class LoggedSender")
        prefix += "\n" + self.code_with("wrappers-and-patterns", "class GateSender")
        self.check_cpp(prefix + r'''
int main() {
    LegacyPrinter printer;
    PrinterAdapter adapter{printer};
    LoggedSender logged{adapter};
    GateSender closed{logged, false};
    std::cout << closed.send("Hi");
}
''', "0")
        self.check_cpp(prefix + r'''
int main() {
    LegacyPrinter printer;
    PrinterAdapter adapter{printer};
    GateSender closed{adapter, false};
    LoggedSender logged{closed};
    std::cout << logged.send("Hi");
}
''', "[]0")


if __name__ == "__main__":
    unittest.main()
