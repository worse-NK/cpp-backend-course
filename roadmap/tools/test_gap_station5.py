"""Focused C++20/23 checks for the global-lifetime teaching addition.

Only known safe examples run.  The cross-TU anti-example is never compiled
or executed; the constinit rejection is checked by compilation only.
"""
from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from build_stations import load_json, validate
from checkpoint_data import with_checkpoints


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "content/station5.json"
EXAMPLES = ROOT / "examples/cpp-foundations/global-lifetime"
LOCAL_COMPILER = ROOT.parent / ".toolchains/gcc15/bin/g++-15"
COMPILER = os.environ.get("COURSE_CXX") or str(LOCAL_COMPILER if LOCAL_COMPILER.exists() else "g++")
NEW_IDS = ("global-initialization-order", "global-lifetime-workbook")
GLOBAL_OUTPUT = (
    "create first\ncreate second\nuse first\nuse second\n"
    "destroy second\ndestroy first\n"
)
PROJECT_OUTPUT = (
    "defaults: load\njournal: open\nservice: start\njournal: request\n"
    "service: port 8080\njournal: service stop\nservice: stop\n"
    "journal: close\ncheck: OK\n"
)


class GlobalLifetimeGap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(DATA_PATH)
        cls.sections = {s["id"]: s for s in cls.data["theory"]}
        cls.listings = {
            b["exampleId"]: b
            for sid in NEW_IDS for b in cls.sections[sid]["blocks"]
            if b.get("exampleId")
        }
        if shutil.which(COMPILER) is None:
            raise RuntimeError(f"C++ compiler not available: {COMPILER}")

    def call(self, args, source=None):
        return subprocess.run(args, input=source, text=True, capture_output=True, timeout=40)

    def single(self, source, standard, output=None, valid=True):
        with tempfile.TemporaryDirectory(prefix="course-global-one-") as work:
            executable = str(Path(work) / "example")
            args = [COMPILER, f"-std=c++{standard}", "-Wall", "-Wextra", "-pedantic-errors", "-x", "c++", "-"]
            args += ["-o", executable] if valid else ["-fsyntax-only"]
            built = self.call(args, source)
            if not valid:
                self.assertGreater(built.returncode, 0, built.stderr)
                self.assertRegex(built.stderr, r"constant initializer|non.constant|non-.constexpr|non-.const")
                return
            self.assertEqual(built.returncode, 0, built.stderr)
            result = self.call([executable])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, output)

    def project(self, standard, reverse=False, main_source=None, expected=PROJECT_OUTPUT):
        with tempfile.TemporaryDirectory(prefix="course-global-project-") as work:
            executable = str(Path(work) / "lifetime")
            inputs = [str(EXAMPLES / "main.cpp"), str(EXAMPLES / "runtime.cpp")]
            if reverse:
                inputs.reverse()
            args = [COMPILER, f"-std=c++{standard}", "-Wall", "-Wextra", "-pedantic-errors", "-I", str(EXAMPLES)]
            if main_source is not None:
                inputs = ["-x", "c++", "-", str(EXAMPLES / "runtime.cpp")]
            built = self.call(args + inputs + ["-o", executable], main_source)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = self.call([executable])
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(result.stdout, expected)

    def test_schema_and_reading_order(self):
        validate(self.data, DATA_PATH)
        route = self.data["readingOrder"]
        start = route.index("loader-before-main")
        self.assertEqual(route[start:start + 4], ["loader-before-main", *NEW_IDS, "abi-evolution"])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station5_progress_v1")
        self.assertEqual([m["id"] for m in self.data["substations"]], [
            "build-pipeline", "linking-abi", "cmake-targets", "workflow-repro", "linux-diagnostics"
        ])
        checkpoints = [
            (s["id"], index, b)
            for s in self.data["theory"] if s["substation"] == "linking-abi"
            for index, b in enumerate(s["blocks"])
            if "Контрольная точка 5.2." in b.get("html", "")
        ]
        self.assertEqual(len(checkpoints), 1)
        sid, index, _ = checkpoints[0]
        self.assertEqual(sid, "abi-evolution")
        self.assertEqual(index, len(self.sections[sid]["blocks"]) - 1)

    def test_downloads_equal_embedded_sources(self):
        blocks = self.sections["global-lifetime-workbook"]["blocks"]
        for filename in ("runtime.hpp", "runtime.cpp", "main.cpp"):
            block = next(b for b in blocks if b.get("caption", "").startswith(f"Полный файл {filename}:"))
            self.assertEqual(block["code"].strip(), (EXAMPLES / filename).read_text().strip())
        html = " ".join(b.get("html", "") for b in blocks)
        for filename in ("runtime.hpp", "runtime.cpp", "main.cpp", "README.txt"):
            self.assertIn(f'global-lifetime/{filename}" download', html)
            self.assertTrue((EXAMPLES / filename).is_file())
        self.assertIn(PROJECT_OUTPUT.strip(), (EXAMPLES / "README.txt").read_text())
        output = next(b["code"] for b in blocks if b.get("caption", "").startswith("Полный stdout"))
        self.assertEqual(output + "\n", PROJECT_OUTPUT)

    def test_theory_links_parse_as_actual_urls(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.hrefs = []

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    self.hrefs.append(dict(attrs).get('href', ''))

        parser = Links()
        for sid in NEW_IDS:
            for block in self.sections[sid]['blocks']:
                parser.feed(block.get('html', ''))
        self.assertGreaterEqual(len(parser.hrefs), 12)
        for href in parser.hrefs:
            self.assertNotRegex(href, r'[\\\"\s]')
            self.assertTrue(href.startswith(('https://', 'examples/')), href)
        for filename in ('runtime.hpp', 'runtime.cpp', 'main.cpp', 'README.txt'):
            self.assertIn('examples/cpp-foundations/global-lifetime/' + filename,
                          parser.hrefs)

    def test_one_translation_unit_exact_order(self):
        block = self.listings["s5-global-one-tu-order"]
        self.assertEqual(block["standard"], "20/23")
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.single(block["code"], standard, GLOBAL_OUTPUT)

    def test_one_translation_unit_self_check_swapped_definitions(self):
        source = self.listings["s5-global-one-tu-order"]["code"]
        source = source.replace(
            'Mark first{"first"};\nMark second{"second"};',
            'Mark second{"second"};\nMark first{"first"};'
        )
        expected = "create second\ncreate first\nuse first\nuse second\ndestroy first\ndestroy second\n"
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.single(source, standard, expected)

    def test_constinit_rejection_and_specific_repair(self):
        block = self.listings["s5-constinit-dynamic-rejected"]
        self.assertEqual(block["standard"], "20/23")
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.single(block["code"], standard, valid=False)
                corrected = block["code"].replace("int read_port()", "constexpr int read_port()", 1)
                self.single(corrected, standard, "")

    def test_two_translation_units_and_reversed_build_inputs(self):
        for standard in ("20", "23"):
            for reverse in (False, True):
                with self.subTest(standard=standard, reverse=reverse):
                    self.project(standard, reverse=reverse)

    def test_two_request_practice_keeps_shutdown_checks(self):
        source = (EXAMPLES / "main.cpp").read_text()
        source = source.replace("service.handle();", "service.handle();\n            service.handle();")
        source = source.replace("counters.requests == 1", "counters.requests == 2")
        source = source.replace("counters.journal_entries == 2", "counters.journal_entries == 3")
        expected = PROJECT_OUTPUT.replace(
            "service: port 8080\n", "service: port 8080\njournal: request\nservice: port 8080\n"
        )
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.project(standard, main_source=source, expected=expected)

    def test_assessment_append_only_positions_and_checkpoint_coverage(self):
        self.assertEqual([len(self.data["quizzes"][k]) for k in ("basic", "advanced", "interview")], [31, 46, 26])
        # The tooling pass appends after the complete pre-tooling banks.
        prefix = {bank: self.data["quizzes"][bank][:count] for bank, count in
                  (("basic", 25), ("advanced", 40), ("interview", 23))}
        self.assertEqual(hashlib.sha256(json.dumps(prefix, ensure_ascii=False,
                         sort_keys=True).encode()).hexdigest(),
                         "efb68d15bb593bd6d5a2011c7ae7178ea7506b5a9538979f972f6f3185bfd8b4")
        resolved = with_checkpoints(self.data)
        questions = resolved["checkpoints"]["linking-abi"]
        self.assertEqual(len(questions), 7)
        for sid in NEW_IDS:
            self.assertTrue(any(sid in q["theoryRefs"] for q in questions))
            for bank, historical_length in (("basic", 23), ("advanced", 38), ("interview", 21)):
                self.assertTrue(any(sid in q["theoryRefs"] for q in self.data["quizzes"][bank][historical_length:]))
        stems = {q["q"] for bank in self.data["quizzes"].values() for q in bank}
        for q in questions[-2:]:
            self.assertNotIn(q["q"], stems)
        tasks = [t for t in self.data["tasks"] if set(t.get("theoryRefs", [])) == set(NEW_IDS)]
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertTrue(task["title"].startswith("Лаборатория: "))
        self.assertEqual(set(task["theoryRefs"]), set(NEW_IDS))

    def test_unsafe_scheme_has_no_runnable_listing_identity(self):
        blocks = self.sections["global-initialization-order"]["blocks"]
        schemes = [b for b in blocks if "схема опасной зависимости" in b.get("caption", "")]
        self.assertEqual(len(schemes), 1)
        self.assertNotIn("exampleId", schemes[0])
        self.assertIn("НЕ инструкция к запуску", schemes[0]["caption"])
        self.assertFalse(any("extern Config config" in p.read_text() for p in EXAMPLES.glob("*.cpp")))


if __name__ == "__main__":
    unittest.main()
