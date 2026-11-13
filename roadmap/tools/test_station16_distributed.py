"""Focused checks for station 16; no cluster, real payment, or host changes."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from build_stations import validate
from checkpoint_data import with_checkpoints, normalize_prompt

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "content/station16.json"
EXAMPLES = ROOT / "examples/station16"
LOCAL_CXX = ROOT.parent / ".toolchains/gcc15/bin/g++-15"
CXX = os.environ.get("COURSE_CXX", str(LOCAL_CXX) if LOCAL_CXX.exists() else "g++")
EXPECTED = "fresh: yes\nstale: no\noverlap: yes\nnew_then_old: no\nall checks passed\n"


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


class DistributedStation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}
        cls.resolved = with_checkpoints(cls.data)
        cls.cpp = (EXAMPLES / "history_checker.cpp").read_text()

    def test_schema_and_complete_banks(self):
        validate(self.data, DATA_PATH)
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station16_progress_v1")
        self.assertEqual(len(self.data["theory"]), 21)
        self.assertEqual(len(self.data["substations"]), 7)
        self.assertEqual({k: len(v) for k, v in self.data["quizzes"].items()},
                         {"basic": 25, "advanced": 14, "interview": 15})
        self.assertEqual(self.data["readingOrder"], [s["id"] for s in self.data["theory"]])

    def test_one_last_checkpoint_per_module(self):
        for index, module in enumerate(self.data["substations"], 1):
            sections = [s for s in self.data["theory"] if s["substation"] == module["id"]]
            checkpoints = [(s["id"], i) for s in sections
                           for i, b in enumerate(s["blocks"])
                           if "Контрольная точка 16." in b.get("html", "")]
            self.assertEqual(checkpoints, [(sections[-1]["id"],
                                           len(sections[-1]["blocks"]) - 1)])
            self.assertIn(f"Контрольная точка 16.{index}.",
                          sections[-1]["blocks"][-1]["html"])

    def test_five_independent_checkpoint_items(self):
        final_stems = {normalize_prompt(q["q"]) for q in self.data["quizzes"]["basic"]}
        checkpoint_stems = []
        for module, questions in self.resolved["checkpoints"].items():
            self.assertEqual(len(questions), 5, module)
            checkpoint_stems.extend(normalize_prompt(q["q"]) for q in questions)
            for q in questions:
                self.assertEqual(q["substation"], module)
                self.assertEqual(len(q["options"]), 4)
        self.assertEqual(len(checkpoint_stems), len(set(checkpoint_stems)))
        self.assertFalse(final_stems.intersection(checkpoint_stems))

    def test_all_options_and_stems_are_well_formed(self):
        all_questions = [q for bank in self.data["quizzes"].values() for q in bank]
        self.assertEqual(len({normalize_prompt(q["q"]) for q in all_questions}), 54)
        for q in all_questions:
            self.assertEqual(len(q["options"]), 4)
            self.assertEqual(len(set(q["options"])), 4)
            self.assertIs(type(q["answer"]), int)
            self.assertIn(q["answer"], range(4))
            self.assertTrue(q["why"].strip())

    def test_local_links_and_real_html_attributes(self):
        other = {}
        for file in (ROOT / "content").glob("station*.json"):
            data = json.loads(file.read_text())
            other[data["meta"]["sourceFile"]] = {s["id"] for s in data["theory"]}
        parser = AnchorParser()
        for section in self.data["theory"]:
            for block in section["blocks"]:
                parser.feed(block.get("html", ""))
                parser.feed(block.get("answer", ""))
        self.assertGreater(len(parser.links), 50)
        for link in parser.links:
            href = link.get("href", "")
            self.assertNotRegex(href, r'[\\\s"]')
            url = urlsplit(href)
            if url.scheme:
                self.assertEqual(url.scheme, "https")
                continue
            if url.path.startswith("examples/"):
                self.assertTrue((ROOT / url.path).is_file(), href)
                self.assertIn("download", link)
            elif url.path == "distributed_lab.html":
                self.assertIn(parse_qs(url.fragment).get("scenario", [None])[0],
                              ("lost-reply", "stale-read", "workflow-recovery"))
            else:
                ids = other.get(url.path, set()) if url.path else set(self.sections)
                target = parse_qs(url.fragment).get("section", [None])[0]
                self.assertIn(target, ids, href)

    def test_embedded_cpp_matches_download_and_output(self):
        blocks = self.sections["distributed-final-workbook"]["blocks"]
        block = next(b for b in blocks if b.get("exampleId") == "s16-history-checker")
        self.assertEqual(block["standard"], "20/23")
        self.assertEqual(block["code"].strip(), self.cpp.strip())
        self.assertEqual(next(b["code"] for b in blocks
                              if b.get("caption") == "Ожидаемый вывод") + "\n", EXPECTED)

    def compile_run(self, source, standard):
        with tempfile.TemporaryDirectory(prefix="course-s16-check-") as path:
            executable = str(Path(path) / "history")
            built = subprocess.run(
                [CXX, f"-std=c++{standard}", "-Wall", "-Wextra", "-Wpedantic",
                 "-Werror", "-O2", "-x", "c++", "-", "-o", executable],
                input=source, text=True, capture_output=True, timeout=45,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([executable], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return result.stdout

    def test_safe_cpp20_and_cpp23_exact_output(self):
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.assertEqual(self.compile_run(self.cpp, standard), EXPECTED)

    def test_cpp_boundaries_and_extra_histories(self):
        prefix = self.cpp.split("int main() {", 1)[0]
        harness = r"""
int main() {
    using V = std::vector<Operation>;
    const auto rejects = [](const V& ops) {
        try { (void)is_linearizable(ops); }
        catch (const std::invalid_argument&) { return true; }
        return false;
    };
    if (!rejects({{Kind::read, 0, -1, 2}}) ||
        !rejects({{Kind::read, 0, 4, 3}}) ||
        !rejects({{Kind::write, 1, 0, 2}, {Kind::read, 1, 2, 3}})) return 1;
    V nine;
    for (int i = 0; i != 9; ++i) nine.push_back({Kind::read, 0, 2*i, 2*i+1});
    if (!rejects(nine)) return 2;
    V eight(nine.begin(), nine.begin() + 8);
    if (!is_linearizable(eight) || !is_linearizable({})) return 3;
    if (!is_linearizable({{Kind::write, 2, 0, 1}, {Kind::read, 2, 2, 3},
                          {Kind::write, 3, 4, 5}})) return 4;
    if (is_linearizable({{Kind::write, 2, 0, 1}, {Kind::read, 0, 2, 3}})) return 5;
    if (!is_linearizable({{Kind::write, 1, 0, 10}, {Kind::write, 2, 2, 8},
                          {Kind::read, 1, 3, 4}, {Kind::read, 2, 5, 6}})) return 6;
    std::cout << "extra checks passed\n";
}
"""
        for standard in ("20", "23"):
            with self.subTest(standard=standard):
                self.assertEqual(self.compile_run(prefix + harness, standard),
                                 "extra checks passed\n")

    def test_actual_process_restart_model_and_report(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "workflow_recovery.py")],
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("all checks passed\n"))
        report = json.JSONDecoder().raw_decode(result.stdout[result.stdout.index("{"):])[0]
        self.assertEqual(report["scope"], "local-sqlite-model-no-network")
        self.assertEqual(report["unknown_outcome"]["state"], "pay_pending")
        self.assertEqual(report["unknown_outcome"]["payments"], 1)
        self.assertEqual(report["after_recovery"],
                         {"state": "paid", "payment_id": 1, "payments": 1, "total": 2500})
        self.assertEqual(report["after_recovery"], report["after_repeat"])
        self.assertIs(report["changed_amount_rejected"], True)

    def test_example_rejects_unrequested_arguments(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "workflow_recovery.py"), "/nonexistent/work-data"],
            text=True, capture_output=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without arguments", result.stderr)

    def test_task_calculations_run_without_network(self):
        for title in ("вычислить причинные", "измерить изменение"):
            task = next(t for t in self.data["tasks"] if title in t["title"])
            result = subprocess.run([sys.executable, "-c", task["code"]],
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            if title.startswith("вычислить"):
                self.assertEqual(result.stdout, "send_A 2\nindependent_C 1\nreceive_B 8\n")
                result2 = subprocess.run([sys.executable, "-c", task["code"].replace("b = 7", "b = 1")],
                                         text=True, capture_output=True, timeout=10)
                self.assertEqual(result2.returncode, 0, result2.stderr)
                self.assertEqual(result2.stdout, "send_A 2\nindependent_C 1\nreceive_B 3\n")
            else:
                rows = result.stdout.strip().splitlines()
                self.assertEqual(len(rows), 102)
                moved = sum(row.split(",")[1] != row.split(",")[2] for row in rows[1:-1])
                self.assertEqual(rows[-1], f"# moved={moved}")
                self.assertGreater(moved, 0)
                self.assertLess(moved, 100)

    def test_every_task_produces_artifact_and_has_scope(self):
        self.assertEqual({t["substation"] for t in self.data["tasks"]},
                         {s["id"] for s in self.data["substations"]})
        for task in self.data["tasks"]:
            self.assertTrue(task["title"].startswith("Лаборатория: "))
            self.assertGreaterEqual(len(task["checks"]), 4)
            self.assertTrue(task["notes"].strip())

    def test_primary_source_coverage_and_non_placeholder_text(self):
        for section in self.data["theory"]:
            body = " ".join(b.get("html", "") for b in section["blocks"])
            self.assertNotIn("будут дополнены", body)
            self.assertNotIn("TODO", body)
            if section["id"] not in {"learning-route", "summary"}:
                self.assertIn("Основания и границы", body)
                self.assertIn('href="https://', body)
        # Preserve the explicit limits that the worked example does not check.
        worked = json.dumps(self.sections["distributed-final-workbook"], ensure_ascii=False)
        self.assertIn("завершённые", worked)
        self.assertIn("не поддерживает", worked)
        self.assertIn("восьми", worked)


if __name__ == "__main__":
    unittest.main()
