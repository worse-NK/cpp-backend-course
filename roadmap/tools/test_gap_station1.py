"""Focused checks for object representation and type-access teaching in station 1.

Run only the three explicitly safe complete examples and a trait check.  The
commented type-punning anti-example is neither compiled nor executed.  Runtime
results supplement, rather than replace, the cited C++20/C++23 draft rules.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from build_stations import load_json, validate
from checkpoint_data import with_checkpoints


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "content/station1.json"
LOCAL_COMPILER = ROOT.parent / ".toolchains/gcc15/bin/g++-15"
COMPILER = os.environ.get("COURSE_CXX") or str(
    LOCAL_COMPILER if LOCAL_COMPILER.exists() else "g++"
)
NEW_IDS = ("object-representation-access", "representation-copy-bit-cast")
EXPECTED = {
    "s1-object-bytes-roundtrip": "7 42 42\n",
    "s1-trivially-copyable-record": "3 1 9\n",
    "s1-bit-cast-byte-pair": "3 9 7\n",
}


class RepresentationGap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(DATA_PATH)
        cls.sections = {section["id"]: section for section in cls.data["theory"]}
        cls.listings = {
            block["exampleId"]: block
            for sid in NEW_IDS for block in cls.sections[sid]["blocks"]
            if block.get("exampleId")
        }
        if shutil.which(COMPILER) is None:
            raise RuntimeError(f"C++ compiler not available: {COMPILER}")

    def check_cpp(self, source, standard, expected):
        with tempfile.TemporaryDirectory(prefix="course-representation-") as work:
            executable = str(Path(work) / "example")
            built = subprocess.run([
                COMPILER, f"-std=c++{standard}", "-O2", "-Wall", "-Wextra",
                "-Werror", "-pedantic-errors", "-x", "c++", "-", "-o", executable,
            ], input=source, text=True, capture_output=True, timeout=45)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run(
                [executable], text=True, capture_output=True, timeout=5
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def test_schema_and_position_after_storage(self):
        validate(self.data, DATA_PATH)
        order = list(self.sections)
        start = order.index("storage-and-construction")
        self.assertEqual(order[start:start + 4], [
            "storage-and-construction", *NEW_IDS, "shared-aliasing"
        ])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station1_progress_v1")
        self.assertTrue(all(self.sections[sid]["substation"] == "ownership"
                            for sid in NEW_IDS))
        for sid in NEW_IDS:
            self.assertGreaterEqual(sum(block["type"] == "self-check"
                                        for block in self.sections[sid]["blocks"]), 2)

    def test_complete_examples_in_both_language_modes(self):
        self.assertEqual(set(self.listings), set(EXPECTED))
        for identifier, output in EXPECTED.items():
            block = self.listings[identifier]
            self.assertEqual(block["standard"], "20/23")
            source = block["code"]
            if identifier == "s1-bit-cast-byte-pair":
                source += (
                    "\n#if !defined(__cpp_lib_bit_cast) || __cpp_lib_bit_cast < 201806L\n"
                    '#error "This example requires standard bit_cast support"\n'
                    "#endif\n"
                )
            for standard in ("20", "23"):
                with self.subTest(example=identifier, standard=standard):
                    self.check_cpp(source, standard, output)

    def test_trivial_copy_trait_does_not_mean_independent_ownership(self):
        source = r'''
#include <cassert>
#include <cstring>
#include <memory>
#include <type_traits>
struct View { int* p; };
struct Owner { std::unique_ptr<int> p; };
static_assert(std::is_trivially_copyable_v<View>);
static_assert(!std::is_trivially_copyable_v<Owner>);
int main() {
    int value = 4;
    View first{&value};
    View second{nullptr};
    std::memcpy(&second, &first, sizeof first);
    assert(second.p == &value);
    value = 8;
    assert(*second.p == 8);
}
'''
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.check_cpp(source, standard, "")

    def test_questions_are_appended_and_checkpoint_applies_rules(self):
        # Historical positions remain intact; each new section gets one new
        # question in every bank, plus distinct inline checkpoint applications.
        for bank, historical_length in (("basic", 20), ("advanced", 23), ("interview", 16)):
            questions = self.data["quizzes"][bank][historical_length:]
            self.assertEqual(len(questions), 2)
            for sid in NEW_IDS:
                self.assertTrue(any(sid in question["theoryRefs"] for question in questions))
        resolved = with_checkpoints(self.data)
        questions = resolved["checkpoints"]["ownership"]
        self.assertGreaterEqual(len(questions), 7)
        old_refs = [("basic", 8), ("basic", 15), ("advanced", 10),
                    ("advanced", 14), ("advanced", 20)]
        for question, (bank, index) in zip(questions, old_refs):
            self.assertEqual(question, self.data["quizzes"][bank][index])
        stems = {question["q"] for bank in self.data["quizzes"].values()
                 for question in bank}
        for question in questions[-2:]:
            self.assertNotIn(question["q"], stems)
            self.assertEqual(question["substation"], "ownership")
        for sid in NEW_IDS:
            self.assertTrue(any(sid in question["theoryRefs"] for question in questions[-2:]))

    def test_bad_type_access_is_only_a_commented_nonrunnable_fragment(self):
        blocks = [block for sid in NEW_IDS for block in self.sections[sid]["blocks"]
                  if block["type"] == "code" and "reinterpret_cast" in block["code"]]
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("exampleId", blocks[0])
        self.assertIn("Неисполняемый", blocks[0]["caption"])
        access_lines = [line for line in blocks[0]["code"].splitlines()
                        if "reinterpret_cast" in line]
        self.assertTrue(all(line.lstrip().startswith("//") for line in access_lines))


if __name__ == "__main__":
    unittest.main()
