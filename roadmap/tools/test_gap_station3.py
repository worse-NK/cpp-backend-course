"""Focused C++20/23 checks for the eight station 3 foundations added in 2026-11.

Compilation is evidence for this GCC/libstdc++ toolchain, not a proof of the
normative claims. No network, real sleeps, or intentionally undefined runs.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
STATION = ROOT / "roadmap/content/station3.json"
CHECKPOINTS = ROOT / "roadmap/content/checkpoints/station3.json"
EXPECTED = {
    "s3-signed-size": "false true\nreject\n20\nreject\n",
    "s3-checked-narrowing": "2500000000\nfalse 7\ntrue 42\n",
    "s3-adl-call": "job\nint\n",
    "s3-adl-swap": "custom\n2 1\n4 3\n",
    "s3-pack-fold": "0 9\n7 ready\n",
    "s3-template-specialization": "value pointer void pointer\noverload template template\n",
    "s3-chrono-units": "2500 ms\n1 2\n1500\n",
    "s3-chrono-deadline": "70 10 0\n",
}
NEW_IDS = [
    "numeric-sizes-conversions", "numeric-intermediate-narrowing",
    "lookup-adl", "adl-customization", "parameter-packs-fold",
    "template-specialization-choices", "chrono-types-units",
    "chrono-deadline-clock",
]


class Station3FoundationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(STATION.read_text())
        cls.blocks = {b["exampleId"]: b
                      for s in cls.data["theory"] for b in s["blocks"]
                      if b.get("exampleId") in EXPECTED}
        pinned = ROOT / ".toolchains/gcc15/bin/g++-15"
        cls.compiler = str(pinned) if pinned.is_file() else shutil.which("g++")

    def compile_source(self, source, standard, expected=None):
        if self.compiler is None:
            self.skipTest("C++ compiler is not available")
        with tempfile.TemporaryDirectory(prefix="course-s3-foundations-") as tmp:
            source_file = Path(tmp) / "example.cpp"
            source_file.write_text(source)
            binary = Path(tmp) / "example"
            result = subprocess.run(
                [self.compiler, f"-std=c++{standard}", "-Wall", "-Wextra",
                 "-pedantic-errors", "-O2", str(source_file), "-o", str(binary)],
                capture_output=True, text=True, timeout=45)
            if expected is None:
                self.assertNotEqual(result.returncode, 0, "Expected an ill-formed program")
                return
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, expected)

    def test_full_programs_cxx20_and_cxx23(self):
        self.assertEqual(set(self.blocks), set(EXPECTED))
        for standard in ("20", "23"):
            for example_id, expected in EXPECTED.items():
                with self.subTest(standard=standard, example_id=example_id):
                    block = self.blocks[example_id]
                    self.assertEqual(block["standard"], "20/23")
                    self.compile_source(block["code"], standard, expected)

    def test_self_check_type_pattern_and_rounding(self):
        source = self.blocks["s3-template-specialization"]["code"]
        source = source.split("int main() {", 1)[0]
        source += ('\nint main() {\n'
                   '  std::cout << Kind<const int*>::name() << " "\n'
                   '            << Kind<int* const>::name() << "\\n";\n}\n')
        duration = ('#include <chrono>\n#include <iostream>\n'
                    'int main() { using namespace std::chrono;\n'
                    'using namespace std::chrono_literals;\n'
                    'std::cout << duration_cast<seconds>(-1500ms).count() << " "\n'
                    '<< floor<seconds>(-1500ms).count() << " "\n'
                    '<< ceil<seconds>(-1500ms).count() << "\\n"; }\n')
        for standard in ("20", "23"):
            with self.subTest(standard=standard, case="cv-pointer"):
                self.compile_source(source, standard, "pointer value\n")
            with self.subTest(standard=standard, case="negative-rounding"):
                self.compile_source(duration, standard, "-1 -2 -1\n")

    def test_qualified_swap_bypasses_hidden_friend(self):
        source = self.blocks["s3-adl-swap"]["code"].replace(
            "    using std::swap;\n    swap(a, b);", "    std::swap(a, b);")
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.compile_source(source, standard, "2 1\n4 3\n")

    def test_integer_conversion_and_deadline_boundaries(self):
        narrow = self.blocks["s3-checked-narrowing"]["code"].split("int main() {", 1)[0]
        narrow += ('int main() {\n'
                   'static_assert(std::numeric_limits<int>::digits == 31);\n'
                   'std::cout << static_cast<int>(2500000000LL) << "\\n";\n'
                   'int result=9; std::cout << std::boolalpha\n'
                   '<< to_int(2147483647LL,result) << " " << result << "\\n";\n'
                   'result=9; std::cout << to_int(2147483648LL,result)\n'
                   '<< " " << result << "\\n"; }\n')
        deadline = self.blocks["s3-chrono-deadline"]["code"].split("int main() {", 1)[0]
        deadline += ('int main() { Point deadline{100ms};\n'
                     'std::cout << remaining(Point{99ms},deadline).count() << " "\n'
                     '<< remaining(Point{100ms},deadline).count() << " "\n'
                     '<< remaining(Point{101ms},deadline).count() << "\\n"; }\n')
        for standard in ("20", "23"):
            with self.subTest(standard=standard, case="integer-limits"):
                self.compile_source(narrow, standard, "-1794967296\ntrue 2147483647\nfalse 9\n")
            with self.subTest(standard=standard, case="deadline-equality"):
                self.compile_source(deadline, standard, "1 0 0\n")

    def test_rejected_programs_are_compile_checks_not_ub_runs(self):
        original_adl = self.blocks["s3-adl-call"]["code"]
        cases = {
            "qualified-adl": original_adl.replace("    process(job);", "    ::process(job);"),
            "no-integer-swap-fallback": self.blocks["s3-adl-swap"]["code"].replace(
                "    using std::swap;\n", ""),
            "hidden-friend-qualified": self.blocks["s3-adl-swap"]["code"].replace(
                "    swap(a, b);", "    domain::swap(a, b);"),
            "empty-unary-plus": self.blocks["s3-pack-fold"]["code"].replace(
                "(0LL + ... + values)", "(... + values)"),
            "narrowing-variable": ('#include <limits>\nint main() {\n'
                                   'static_assert(std::numeric_limits<int>::digits == 31);\n'
                                   'long long raw=42; int result{raw}; (void)result; }\n'),
            "partial-function": ('template<class T> int f(T) { return 0; }\n'
                                 'template<class T> int f<T*>(T*) { return 1; }\n'
                                 'int main() { return 0; }\n'),
            "coarse-implicit-duration": ('#include <chrono>\nint main() {\n'
                                         'std::chrono::seconds s = std::chrono::milliseconds{1500};\n'
                                         '(void)s; }\n'),
            "cross-clock-difference": ('#include <chrono>\nint main() {\n'
                                       'auto d = std::chrono::system_clock::now() - '
                                       'std::chrono::steady_clock::now(); (void)d; }\n'),
        }
        for standard in ("20", "23"):
            for name, source in cases.items():
                with self.subTest(standard=standard, case=name):
                    self.compile_source(source, standard)

    def test_new_sections_are_progressive_and_referenced(self):
        sections = {s["id"]: s for s in self.data["theory"]}
        for section_id in NEW_IDS:
            with self.subTest(section=section_id):
                section = sections[section_id]
                self.assertGreaterEqual(sum(b["type"] == "self-check"
                                            for b in section["blocks"]), 1)
                self.assertTrue(any(b.get("exampleId") in EXPECTED for b in section["blocks"]))
                self.assertIn("n4861/", section["blocks"][-1]["html"])
        ids = list(sections)
        self.assertLess(ids.index("numeric-intermediate-narrowing"), ids.index("map-set"))
        self.assertLess(ids.index("parameter-packs-fold"), ids.index("callables-and-invoke"))
        self.assertLess(ids.index("chrono-deadline-clock"), ids.index("sliding-window-workbook"))

    def test_new_questions_cover_theory_without_repeating_checkpoint_stems(self):
        sections = {s["id"]: s for s in self.data["theory"]}
        plan = json.loads(CHECKPOINTS.read_text())
        new_bank_questions = []
        # Existing bank entries are preserved; only these suffixes are authored here.
        for bank, start, delta in (("basic", 26, 8), ("advanced", 51, 8), ("interview", 20, 4)):
            added = self.data["quizzes"][bank][start:]
            self.assertEqual(len(added), delta)
            new_bank_questions.extend(added)
            for question in added:
                self.assertEqual(len(question["options"]), 4)
                self.assertIn(question["answer"], range(4))
                self.assertTrue(set(question["theoryRefs"]) & set(NEW_IDS))
                for reference in question["theoryRefs"]:
                    self.assertIn(reference, sections)
        new_stems = {q["q"].strip().casefold() for q in new_bank_questions}
        self.assertEqual(len(new_stems), len(new_bank_questions))
        added_checkpoint_counts = {
            "containers-cost": (5, 2),
            "templates-generic": (8, 4),
            "vocabulary-design": (6, 2),
        }
        seen = set()
        for module, (start, delta) in added_checkpoint_counts.items():
            added = plan["modules"][module][start:]
            self.assertEqual(len(added), delta)
            for question in added:
                self.assertEqual(question["substation"], module)
                self.assertNotIn(question["q"].strip().casefold(), new_stems)
                for reference in question["theoryRefs"]:
                    self.assertEqual(sections[reference]["substation"], module)
                    seen.add(reference)
        self.assertEqual(seen, set(NEW_IDS))

    def test_new_html_has_no_accidental_attribute_escaping(self):
        for section in self.data["theory"]:
            if section["id"] not in NEW_IDS + ["learning-route"]:
                continue
            for block in section["blocks"]:
                for key in ("html", "answer"):
                    self.assertNotIn('\\"', block.get(key, ""), section["id"])


if __name__ == "__main__":
    unittest.main()
