"""Linux architecture cases: bounded models and a private mmap example.

No cgroup settings, affinity, host services or network resources are modified.
The executable owns a newly created /tmp directory and two tiny data files.
"""
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from build_stations import load_json, validate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content/station5-linux.json"
EXAMPLE = ROOT / "examples/station5-linux/mapped_generation.cpp"
NEW_IDS = {"linux-cpu-quota-workbook", "linux-mapped-generations"}
OUTPUT = ("R1 before: generation-1\n"
          "R2 after: generation-2\n"
          "R1 still: generation-1\n")


def html_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "html":
                yield child
            elif isinstance(child, (dict, list)):
                yield from html_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from html_fields(child)


class Fragment(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href", ""))


class LinuxArchitectureContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(SOURCE)
        cls.sections = {section["id"]: section for section in cls.data["theory"]}

    def test_schema_placement_and_end_checkpoints(self):
        validate(self.data, SOURCE)
        order = list(self.sections)
        self.assertEqual(order[order.index("linux-mmap-sharing") + 1],
                         "linux-mapped-generations")
        self.assertEqual(order[order.index("linux-limits-isolation") + 1],
                         "linux-cpu-quota-workbook")
        for index, group in enumerate(self.data["substations"], 1):
            sections = [s for s in self.data["theory"]
                        if s["substation"] == group["id"]]
            checkpoints = [(s, block) for s in sections for block in s["blocks"]
                           if "Контрольная точка" in block.get("html", "")]
            self.assertEqual(len(checkpoints), 1, group["id"])
            self.assertIs(checkpoints[0][0], sections[-1])
            self.assertIs(checkpoints[0][1], sections[-1]["blocks"][-1])
            self.assertIn(f"5Б.{index}", checkpoints[0][1]["html"])

    def test_new_cases_have_visible_assessment_sources_and_figures(self):
        for sid in NEW_IDS:
            section = self.sections[sid]
            with self.subTest(section=sid):
                for bank in ("basic", "interview"):
                    self.assertEqual(sum(sid in q["theoryRefs"]
                                         for q in self.data["quizzes"][bank]), 2)
                self.assertTrue(any(b["type"] in ("diagram", "visual", "lanes")
                                    for b in section["blocks"]))
                prose = " ".join(html_fields(section))
                self.assertIn("https://", prose)
                self.assertNotRegex(prose, r"href=\"[^\"]*\s[^\"]*\"")
                self.assertNotRegex(prose, r"\d,\s+\d")
        self.assertTrue(any(t["title"].startswith("Лаборатория: ")
                            and "linux-mapped-generations" in t["theoryRefs"]
                            for t in self.data["tasks"]))

    def test_reading_route_links_to_both_cases(self):
        route = self.sections["learning-route"]
        links = [url for html in html_fields(route) for url in Fragment(html).links]
        for sid in NEW_IDS:
            self.assertTrue(any(url.endswith("#section=" + sid) for url in links))

    def test_full_listing_is_identical_to_downloadable_source(self):
        listing = [b["code"] for b in self.sections["linux-mapped-generations"]["blocks"]
                   if b["type"] == "code" and "int main(" in b["code"]]
        self.assertEqual(listing, [EXAMPLE.read_text()])
        source = listing[0]
        self.assertIn('"/tmp/course-mapped-generation-XXXXXX"', source)
        self.assertIn("::mkdtemp", source)
        self.assertIn("::fstat(file.get()", source)
        self.assertIn("O_EXCL", source)
        self.assertIn("::renameat", source)
        self.assertIn("::fsync(workspace.get())", source)
        self.assertNotIn("O_TRUNC", source)
        self.assertNotIn("MAP_FIXED", source)
        self.assertNotIn("argv", source)
        self.assertNotIn("std::thread", source)

    def test_quota_arithmetic_and_synthetic_counter_deltas(self):
        quota, period, threads = 50000, 100000, 2
        self.assertEqual(Fraction(quota, period), Fraction(1, 2))
        self.assertEqual(quota / threads / 1000, 25)
        self.assertEqual((period - 30000) / 1000, 70)
        self.assertEqual(Fraction(quota * 100, 8 * period), Fraction(25, 4))
        first = {"usage_usec": 1000000, "nr_periods": 100, "nr_throttled": 40}
        later = {"usage_usec": 1500000, "nr_periods": 110, "nr_throttled": 50}
        self.assertEqual(later["usage_usec"] - first["usage_usec"], 500000)
        self.assertEqual(later["nr_periods"] - first["nr_periods"], 10)
        self.assertEqual(later["nr_throttled"] - first["nr_throttled"], 10)
        prose = " ".join(html_fields(self.sections["linux-cpu-quota-workbook"]))
        self.assertIn("не точный прогноз", prose)
        self.assertIn("не измеряет длительность", prose)
        codes = "\n".join(b["code"] for b in
                          self.sections["linux-cpu-quota-workbook"]["blocks"]
                          if b["type"] == "code")
        self.assertIn("50000 100000", codes)
        self.assertNotRegex(codes, r"sudo|tee\s|echo\s|>\s*/|taskset")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("g++"),
                     "The runnable example requires Linux and a C++20 compiler")
class MappedGenerationExecutable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="course-mapped-tests-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binaries = []
        profiles = [("g++", "debug", ["-O0", "-g"]),
                    ("g++", "release", ["-O2", "-DNDEBUG"])]
        if shutil.which("clang++"):
            profiles.append(("clang++", "ubsan", ["-O1", "-fsanitize=undefined",
                                                  "-fno-sanitize-recover=all"]))
        for compiler, label, options in profiles:
            target = Path(cls.directory.name) / label
            command = [compiler, "-std=c++20", "-Wall", "-Wextra", "-Wpedantic",
                       "-Werror", *options, str(EXAMPLE), "-o", str(target)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(f"Compilation failed: {command}\n{result.stderr}")
            cls.binaries.append(target)

    def test_readers_keep_different_immutable_generations(self):
        for binary in self.binaries:
            with self.subTest(profile=binary.name):
                result = subprocess.run([str(binary)], stdin=subprocess.DEVNULL,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, OUTPUT)
                self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
