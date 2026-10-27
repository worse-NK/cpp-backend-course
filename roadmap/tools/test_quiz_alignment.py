#!/usr/bin/env python3
"""Check quiz prerequisites and executable examples changed during alignment."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_stations
import test_remaining_examples
from test_expanded_examples import code, station


class QuizAlignment(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_all_station_mappings(self):
        for path in sorted((Path(__file__).resolve().parents[1] / "content").glob("station[0-9]*.json")):
            number = path.stem.removeprefix("station")
            with self.subTest(station=number):
                data = station(number)
                build_stations.validate(data, Path(f"station{number}.json"))
                for questions in data["quizzes"].values():
                    for question in questions:
                        self.assertTrue(question["theoryRefs"])

    def test_bad_references_rejected(self):
        for refs in (None, [], "methods", ["missing"], ["methods", "methods"], [42]):
            with self.subTest(refs=refs):
                data = copy.deepcopy(station(0))
                question = data["quizzes"]["basic"][0]
                if refs is None:
                    del question["theoryRefs"]
                else:
                    question["theoryRefs"] = refs
                with self.assertRaisesRegex(ValueError, "theoryRefs"):
                    build_stations.validate(data, Path("station0.json"))

    def test_future_prerequisite_rejected(self):
        data = copy.deepcopy(station(0))
        data["quizzes"]["basic"][0]["theoryRefs"] = ["destructor"]
        with self.assertRaisesRegex(ValueError, "later substation"):
            build_stations.validate(data, Path("station0.json"))

    def test_replacement_quiz_programs(self):
        for number, index, output in [(0, 4, "ABBXA"), (0, 11, "123321"),
                                      (4, 13, "I"), (4, 14, "ABaC")]:
            with self.subTest(station=number, question=index):
                source = station(number)["quizzes"]["advanced"][index]["q"].split("\n\n", 1)[1]
                self.cpp(source, output)
        owned = station(1)["quizzes"]["advanced"][11]["q"].split("\n\n", 1)[1]
        self.cpp(owned, "Aa")
        raw = station(1)["quizzes"]["advanced"][12]["q"].split("\n\n", 1)[1]
        self.cpp(raw)  # Deliberate leak: compile, do not execute.
        counter = station(0)["quizzes"]["advanced"][2]["q"].split("\n\n", 1)[1]
        self.cpp(counter + "\nint main(){return c.value() == 7 ? 0 : 1;}", "")
        self.cpp(counter + "\nint main(){c.reset();}", valid=False)

    def test_optional_argument_evaluation(self):
        source = code(3, "modern-tools", -1)
        self.cpp(source, "fallback 7")
        self.cpp(source.replace("= 7;", "= std::nullopt;"), "fallback 99")
        lazy = source.replace("value.value_or(fallback())", "(value ? *value : fallback())")
        self.cpp(lazy, "7")
        self.cpp(lazy.replace("= 7;", "= std::nullopt;"), "fallback 99")

    def test_map_equivalence(self):
        source = code(3, "map-set", -1)
        self.cpp(source, "1 0 10")
        both_fields = source.replace("return a.last < b.last;",
            "return a.last < b.last || (a.last == b.last && a.id < b.id);")
        self.cpp(both_fields, "2 1 20")

    def test_from_chars_no_match(self):
        self.cpp("""
#include <charconv>
#include <iostream>
#include <string_view>
int main() {
    std::string_view input = "abc";
    int value = 17;
    auto result = std::from_chars(input.data(), input.data() + input.size(), value);
    std::cout << (result.ec == std::errc::invalid_argument) << ' '
              << (result.ptr == input.data()) << ' ' << value;
}
""", "1 1 17")

    def test_gitignore_does_not_untrack(self):
        with tempfile.TemporaryDirectory(prefix="roadmap-gitignore-") as directory:
            root = Path(directory)
            def git(*args):
                result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            git("init", "-q")
            (root / "build").mkdir()
            (root / "build/old.o").write_text("already staged\n")
            git("add", "build/old.o")
            (root / ".gitignore").write_text("build/\n")
            (root / "build/new.o").write_text("new output\n")
            git("add", ".")
            self.assertIn("build/old.o", git("ls-files"))
            self.assertNotIn("build/new.o", git("ls-files"))
            self.assertIn("build/new.o", git("check-ignore", "build/new.o"))


    def test_thread_lifetime_traces(self):
        for index, expected in [(1, "AWDE"), (11, "1E2")]:
            source = station(6)["quizzes"]["advanced"][index]["q"].split("\n\n", 1)[1]
            self.cpp(source, expected, flags=("-pthread",))
        # Compile UB examples only: executing them cannot validate the diagnosis.
        bad = station(6)["quizzes"]["advanced"][13]["q"].split("\n\n", 1)[1]
        self.cpp(bad, flags=("-pthread",))
        good = code(6, "happens-before", -1)
        good += "\n#include <iostream>\nint main(){ std::cout << collect().at(0); }"
        for flags in [("-pthread",), ("-pthread", "-fno-elide-constructors")]:
            self.cpp(good, "42", flags=flags)
        # Putting report after worker removes the join-before-report ordering.
        variant = station(6)["quizzes"]["advanced"][1]["q"].split("\n\n", 1)[1]
        variant = variant.replace("        Report report;\n", "")
        variant = variant.replace("std::jthread worker([] { std::cout << 'W'; });",
                                  "std::jthread worker([] { std::cout << 'W'; });\n        Report report;")
        self.cpp(variant, {"ADWE", "AWDE"}, flags=("-pthread",))

    def test_parser_chunk_boundaries(self):
        import re
        # An independent incremental decoder for the exact bytes in the exercises.
        def decode(chunks, width):
            pending = bytearray()
            messages = []
            for chunk in chunks:
                pending.extend(chunk)
                while len(pending) >= width:
                    length = int.from_bytes(pending[:width], "big")
                    if length > 1024:
                        raise ValueError("oversized frame")
                    if len(pending) < width + length:
                        break
                    messages.append(bytes(pending[width:width + length]))
                    del pending[:width + length]
            return messages, bytes(pending)
        basic = station(7)["quizzes"]["basic"][16]["q"]
        chunks = [bytes.fromhex(s) for s in re.findall(r"\[([0-9A-Fa-f ]+)\]", basic)]
        self.assertEqual(decode(chunks, 1), ([b"AB", b"C"], b""))
        wire = b"".join(chunks)
        for split in range(len(wire) + 1):
            self.assertEqual(decode([wire[:split], wire[split:]], 1), ([b"AB", b"C"], b""))
        self.assertEqual(decode([bytes([b]) for b in wire], 1), ([b"AB", b"C"], b""))
        interview = station(7)["quizzes"]["interview"][10]["q"]
        wire = bytes.fromhex(re.search(r"\[([0-9A-Fa-f ]+)\]", interview).group(1))
        for split in range(len(wire) + 1):
            self.assertEqual(decode([wire[:split], wire[split:]], 4),
                             ([b"abc"], bytes.fromhex("00 00 00 02 78")))
        self.assertEqual(decode([wire, b"y"], 4), ([b"abc", b"xy"], b""))
        self.assertEqual(decode([bytes(4)], 4), ([b""], b""))
        with self.assertRaises(ValueError):
            decode([(1025).to_bytes(4, "big")], 4)

    def test_references_required_in_backend_stations(self):
        for number in (6, 7):
            data = copy.deepcopy(station(number))
            del data["quizzes"]["basic"][0]["theoryRefs"]
            with self.assertRaisesRegex(ValueError, "theoryRefs"):
                build_stations.validate(data, Path(f"station{number}.json"))
        for number, target in [(6, "summary"), (7, "http2-http3-deep")]:
            data = copy.deepcopy(station(number))
            data["quizzes"]["basic"][0]["theoryRefs"] = [target]
            with self.assertRaisesRegex(ValueError, "later substation"):
                build_stations.validate(data, Path(f"station{number}.json"))


if __name__ == "__main__":
    unittest.main()
