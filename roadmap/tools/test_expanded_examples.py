#!/usr/bin/env python3
"""Regression checks for worked examples in stations 0-5."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def station(number):
    return json.loads((ROOT / f"content/station{number}.json").read_text())


def code(number, section, index=0):
    item = next(s for s in station(number)["theory"] if s["id"] == section)
    return [b["code"] for b in item["blocks"] if b["type"] == "code"][index]


class ExpandedExamples(unittest.TestCase):
    def check_cpp(self, source, output=None, valid=True, standard="c++20"):
        with tempfile.TemporaryDirectory(prefix="roadmap-example-") as directory:
            binary = str(Path(directory) / "example")
            command = ["g++", f"-std={standard}", "-Wall", "-Wextra", "-pedantic", "-x", "c++", "-"]
            command += ["-fsyntax-only"] if output is None else ["-o", binary]
            result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode == 0, valid, result.stderr)
            if valid and output is not None:
                run = subprocess.run([binary], capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), output)

    def test_worked_outputs(self):
        cases = [
            (0, "encapsulation", "100"),
            (0, "object-state-identity", "2 9\n8 5"),
            (0, "destructor", "+outer +first +second -second -first after -outer"),
            (0, "special-members-intro", "make copy make assign drop1 drop1 drop1"),
            (0, "equality-operators", "1 0 0"),
            (1, "resource-taxonomy", "0"),
            (1, "const-and-aliases", "9"),
            (1, "lambda-lifetime", "11 12"),
            (1, "move-cost-model", "move copy"),
            (2, "static-dynamic-view", "D1 D2 B1"),
            (2, "nvi-interface-evolution", "0 hello 1"),
            (3, "allocation-containers", "0 10 2"),
            (3, "algorithm-pipeline", "60"),
            (3, "ranges-lifetime", "cat bat"),
            (4, "exception-object-matching", "inner parse"),
        ]
        for number, section, output in cases:
            with self.subTest(station=number, section=section):
                self.check_cpp(code(number, section), output)

    def test_gradual_explanations(self):
        cases = [
            (0, "methods", 0, "1 0"),
            (0, "static-friend", 0, "0 2 2"),
            (0, "static-friend", 1, "(2, 5)"),
            (1, "move", 0, "1 0 7"),
            (1, "move", 1, "LR"),
            (2, "multiple-inheritance", 0, "1 2"),
            (2, "multiple-inheritance", 1,
             "Root42 Left Right Diamond ~Diamond ~Right ~Left ~Root"),
            (2, "virtual-dtor", 0, "DMB"),
            (2, "virtual-dtor", 1, ""),
            (3, "algorithms", 0, "8 1"),
            (3, "algorithms", 1, "3 3 20 20"),
            (3, "iterator-categories-ranges", 0, "1 1"),
            (3, "iterator-categories-ranges", 1, "a b"),
            (4, "exception-timeline", 0, "+O +A +B -B -A caught after -O"),
            (4, "noexcept-deep", 0, "0 0 1"),
            (4, "noexcept-deep", 2, "CM"),
        ]
        for number, section, index, expected in cases:
            with self.subTest(station=number, section=section, index=index):
                self.check_cpp(code(number, section, index), expected)

    def test_gradual_variants(self):
        lamp = code(0, "methods") + "\n" + code(0, "methods", 1)
        self.check_cpp(lamp)
        self.check_cpp(lamp.replace("// lamp.turnOn();", "lamp.turnOn();"), valid=False)
        diamond = code(2, "multiple-inheritance", 1)
        self.check_cpp(diamond.replace("Root(42), ", ""), valid=False)
        self.check_cpp(diamond.replace("Diamond d;", "Left d;"), "Root1 Left ~Left ~Root")
        destructor = code(2, "virtual-dtor")
        shared = destructor.replace("virtual ~Base", "~Base").replace(" override", "")
        shared = shared.replace("unique_ptr<Base>", "shared_ptr<Base>").replace("make_unique<Derived>", "make_shared<Derived>")
        self.check_cpp(shared, "DMB")
        inaccessible = code(2, "virtual-dtor", 1).replace("// delete view;", "delete view;")
        self.check_cpp(inaccessible, valid=False)
        linked = code(3, "iterator-categories-ranges")
        self.check_cpp(linked.replace("// std::sort(linked", "std::sort(linked"), valid=False)
        move = code(4, "noexcept-deep", 2)
        self.check_cpp(move.replace("noexcept(false)", "noexcept"), "MM")
        self.check_cpp(move.replace("Item(const Item&) { std::cout << 'C'; }", "Item(const Item&) = delete;"), "MM")
        wrapper = code(4, "noexcept-deep", 1)
        self.check_cpp(wrapper + "\nint main(){int a=0,b=3; static_assert(noexcept(assign_from(a,b))); assign_from(a,b); return a==3 ? 0 : 1;}", "")
        self.check_cpp(code(1, "raii", 1))

    def test_rethrow_variant(self):
        self.check_cpp(code(4, "exception-object-matching").replace("throw;", "throw error;"), "inner runtime")

    def test_template_deduction(self):
        source = code(3, "template-compilation")
        self.check_cpp(source + "\nint main(){larger(2,5.0);}", valid=False)
        self.check_cpp(source + "\nint main(){return larger<double>(2,5.0)==5 ? 0 : 1;}", "")
        reservable = code(3, "template-compilation", 1)
        self.check_cpp(reservable + "\n#include <vector>\nint main(){std::vector<int> v; prepare(v,10);}", "")
        self.check_cpp(reservable + "\n#include <list>\nint main(){std::list<int> v; prepare(v,10);}", valid=False)

    def test_expected_parser_cpp23(self):
        self.check_cpp(code(4, "expected-composition") + """
#include <cassert>
#include <string>
int main() {
    assert(parse_int("42").value() == 42);
    assert(parse_int("").error() == ParseError::empty);
    assert(parse_int("12x").error() == ParseError::trailing);
    assert(parse_int("+7").error() == ParseError::invalid);
    assert(parse_int(" 7").error() == ParseError::invalid);
    assert(parse_int(std::string(100, '9')).error() == ParseError::out_of_range);
}
""", "", standard="c++23")

    def test_new_quiz_programs(self):
        cases = [
            (0, "object-model", 0, "7 5"),
            (0, "lifecycle-value", 0, "XBA"),
            (1, "lifetime-raii", 0, "RGM"),
            (1, "borrowing-const", 0, "9"),
            (1, "ownership", 0, "0 1"),
            (1, "value-semantics", 0, "MC"),
            (1, "value-semantics", 1, "4 5 4"),
            (2, "subobjects-lifecycle", 0, "BMDdmb"),
            (2, "virtual-dispatch", 0, "D1"),
            (2, "virtual-dispatch", 1, "BD"),
            (2, "interfaces-ownership", 1, "1 2"),
            (3, "templates-generic", 2, "LR"),
            (3, "vocabulary-design", 0, "cat bat"),
        ]
        for number, substation, index, expected in cases:
            with self.subTest(station=number, substation=substation, index=index):
                questions = [q for q in station(number)["quizzes"]["interview"] if q["substation"] == substation]
                self.check_cpp(questions[index]["q"].split("\n\n", 1)[1], expected)

    def test_invalid_override(self):
        questions = [q for q in station(2)["quizzes"]["interview"] if q["substation"] == "virtual-dispatch"]
        self.check_cpp(questions[2]["q"].split("\n\n", 1)[1], valid=False)

    def test_cmake_public_requirements(self):
        fixture = ROOT / "tests/build_example"
        chapter = next(s for s in station(5)["theory"] if s["id"] == "cmake-tests-install")
        blocks = [b["code"] for b in chapter["blocks"] if b["type"] == "code"]
        self.assertEqual((fixture / "CMakeLists.txt").read_text(), blocks[0] + "\n\n" + blocks[3] + "\n")
        self.assertEqual((fixture / "tests/core_test.cpp").read_text(), blocks[1] + "\n")
        with tempfile.TemporaryDirectory(prefix="roadmap-build-") as directory:
            build = Path(directory) / "build"
            for command in [
                ["cmake", "-S", str(fixture), "-B", str(build),
                 "-DBUILD_TESTING=ON", "-DCMAKE_INSTALL_LIBDIR=lib"],
                ["cmake", "--build", str(build)],
                ["ctest", "--test-dir", str(build), "--output-on-failure", "--no-tests=error"],
            ]:
                result = subprocess.run(command, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = subprocess.run([str(build / "app")], text=True, capture_output=True, timeout=5)
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout.strip(), "42")
            result = subprocess.run(
                ["g++", "-std=c++20", "-I", str(fixture / "include"),
                 str(fixture / "src/main.cpp"), "-o", str(build / "missing-core")],
                text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("undefined reference", result.stderr)
            staged = Path(directory) / "installed"
            result = subprocess.run(
                ["cmake", "--install", str(build), "--prefix", str(staged)],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            relocated = Path(directory) / "relocated"
            staged.rename(relocated)
            targets = relocated / "lib/cmake/Lesson/LessonTargets.cmake"
            self.assertTrue(targets.is_file())
            self.assertNotIn(str(fixture), targets.read_text())
            consumer = Path(directory) / "consumer"
            for command in [
                ["cmake", "-S", str(ROOT / "tests/installed_consumer"), "-B", str(consumer),
                 f"-DLESSON_TARGETS={targets}"],
                ["cmake", "--build", str(consumer)],
            ]:
                result = subprocess.run(command, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(consumer / "consumer")], text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "42")


if __name__ == "__main__":
    unittest.main()
