#!/usr/bin/env python3
"""Regression checks for the 0.2 chapter and the ranges example (requires g++)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "content/station0.json").read_text())
SECTIONS = {item["id"]: item for item in DATA["theory"]}
QUIZZES = {
    kind: [q for q in questions if q.get("substation") == "construction-invariants"]
    for kind, questions in DATA["quizzes"].items()
}


def blocks(section):
    return [b["code"] for b in SECTIONS[section]["blocks"] if b["type"] == "code"]


class Examples(unittest.TestCase):
    def compile(self, source, expected=None, valid=True):
        with tempfile.TemporaryDirectory(prefix="cpp-chapter-") as directory:
            binary = str(Path(directory) / "example")
            command = ["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic",
                       "-x", "c++", "-"]
            command += ["-fsyntax-only"] if expected is None else ["-o", binary]
            result = subprocess.run(command, input=source, text=True,
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode == 0, valid, result.stderr)
            if valid and expected is not None:
                run = subprocess.run([binary], text=True, capture_output=True,
                                     timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), expected)

    def test_theory_output(self):
        self.compile(blocks("constructor")[0], "10 20")
        self.compile(blocks("initialization-model")[0], "low high body 10 20")

    def test_quiz_output(self):
        for kind, index, expected in [
            ("advanced", 0, "10 15"),
            ("interview", 0, "1 3 body"),
            ("interview", 2, "9 9"),
        ]:
            with self.subTest(kind=kind, index=index):
                source = QUIZZES[kind][index]["q"].split("\n\n", 1)[1]
                self.compile(source, expected)

    def test_task_output(self):
        task = next(t for t in DATA["tasks"]
                    if t["title"] == "Восстанови порядок и значения")
        self.compile(task["code"], "4 5 ready")

    def test_invariant(self):
        self.compile(blocks("invariants")[0] + """
#include <cassert>
int main() {
    Interval x{10, 20};
    assert(!x.set_bounds(30, 25));
    assert(x.low() == 10 && x.high() == 20);
    assert(x.set_bounds(30, 40));
    assert(x.low() == 30 && x.high() == 40);
    bool rejected = false;
    try { Interval invalid{20, 10}; }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
""", "")

    def test_factory_and_deleted_constructor(self):
        source = blocks("valid-states-factories")[0]
        self.compile(source + """
#include <cassert>
int main() {
    auto x = Interval::point(7);
    assert(x.low() == 7 && x.high() == 7);
}
""", "")
        self.compile(source + "\nint main() { Interval empty; }", valid=False)

    def test_initialization_and_explicit(self):
        self.compile("""
#include <cassert>
struct A { int n; A() = default; };
struct B { int n; B() {} };
struct C { int n = 7; C() = default; };
int main() {
    A a{};
    C c;
    assert(a.n == 0 && c.n == 7);
    // Deliberately do not read uninitialized members or execute UB examples.
}
""", "")
        definitions = """
struct Limit { explicit Limit(int) {} };
void consume(Limit) {}
"""
        for expression in ["consume(5);", "Limit x = 5;",
                           "Limit x = {5};", "consume({5});"]:
            with self.subTest(expression=expression):
                self.compile(definitions + "int main() {" + expression + "}",
                             valid=False)
        self.compile(definitions + """
int main() { Limit a(5); Limit b{5}; consume(Limit{5}); }
""", "")
        self.compile("int main() { int n{3.5}; }", valid=False)

    def test_const_and_reference(self):
        self.compile("""
struct A { const int n; A(int x) { n = x; } };
""", valid=False)
        self.compile("""
struct A { int& n; A(int& x) { n = x; } };
""", valid=False)

    def test_range_constraint_matches_argument(self):
        data = json.loads((ROOT / "content/station3.json").read_text())
        source = next(b["code"] for s in data["theory"] for b in s["blocks"]
                      if "long long sum(" in b.get("code", ""))
        self.compile(source + """
#include <cassert>
#include <vector>
int main() {
    std::vector<int> values{1, 2, 3, 4};
    const std::vector<int> fixed{1, 2, 3};
    auto evens = values | std::views::filter([](int x) { return x % 2 == 0; });
    assert(sum(values) == 10);
    assert(sum(fixed) == 6);
    assert(sum(evens) == 6);
    assert(sum(values | std::views::filter([](int x) { return x > 2; })) == 7);
}
""", "")
        self.compile(source + "\nint main() { sum(42); }", valid=False)


if __name__ == "__main__":
    unittest.main()
