"""Structural integration regressions for the security station, entirely offline.

These tests read canonical/public sources and render release bytes in memory.
They do not run C++ programs, browsers, fuzzers, Docker, services or requests,
and do not write a release directory. Passing checks establishes the tested
structure and links, not the correctness of every source claim, prose clarity,
semantic uniqueness of questions, or security of a deployed application.
The separate native/model/UI tests and editorial review retain those scopes.
"""
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

import build_publication as publication
from build_stations import html_for, load_json, validate
from checkpoint_data import normalize_prompt, with_checkpoints
from test_linux_systems import Fragment, fields


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content/station15.json"
PAGE = "cpp_station15_security.html"
MODULES = (
    "security-model", "identity-lifecycle", "authorization-policy",
    "untrusted-input", "network-trust", "resource-abuse", "secure-delivery",
    "cpp-security", "security-review",
)
SECTION_COUNTS = (4, 6, 4, 5, 5, 4, 5, 5, 4)
LAB_ENTRIES = {
    ("access-laboratory", "security", "access"),
    ("sql-injection-laboratory", "security-sql", "sql"),
    ("transport-laboratory", "security", "tls"),
    ("outbound-laboratory", "security", "outbound"),
    ("abuse-laboratory", "overload", "bounded"),
}
DOWNLOADS = {
    "README.txt", "CMakeLists.txt", "access_policy.cpp", "access_policy_test.cpp",
    "frame_parser.hpp", "frame_parser_test.cpp", "frame_fuzz.cpp",
    "verify_security_evidence.py", "outbound-policy.example.json",
    "network-evidence.example.json", "delivery-policy.example.json",
    "release-evidence.example.json",
}
STATION_IDS = {f"station{n}" for n in range(17)} | {
    "station5-linux", "station7-netlab", "station7-traffic", "station9-sql",
}


def is_workbook(section):
    """Match the shared UI's separate worked-example destination."""
    return bool(re.search(r"(?:-final-workbook|clock-worked-example)$", section["id"]))


def home_data():
    source = (ROOT / "cpp_backend_roadmap.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script id="roadmap-data" type="application/json">(.*?)</script>',
        source, re.S,
    )
    if not match:
        raise AssertionError("Missing editable roadmap-data in the home page")
    return json.loads(match[1]), source


def generated_data():
    source = (ROOT / "generated/station15.data.js").read_text(encoding="utf-8")
    match = re.fullmatch(r"window\.STATION_DATA\s*=\s*(.*);\s*", source, re.S)
    if not match:
        raise AssertionError("Unexpected station15 data wrapper; do not eval generated JS")
    return json.loads(match[1])


class SecurityStationContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(SOURCE)
        cls.resolved = with_checkpoints(cls.data)
        cls.sections = {s["id"]: s for s in cls.data["theory"]}
        cls.main_questions = [q for bank in cls.data["quizzes"].values() for q in bank]
        cls.check_questions = [q for bank in cls.resolved["checkpoints"].values() for q in bank]

    def test_canonical_schema_metadata_and_reading_order(self):
        validate(self.data, SOURCE)
        meta = self.data["meta"]
        self.assertEqual("station15", meta["id"])
        self.assertEqual(15, meta["number"])
        self.assertEqual("cpp_station15_progress_v1", meta["storeKey"])
        self.assertEqual(PAGE, meta["sourceFile"])
        self.assertEqual(42, len(self.sections))
        self.assertIn('endian-modernization-regression', self.sections)
        self.assertEqual(MODULES, tuple(m["id"] for m in self.data["substations"]))
        self.assertEqual(tuple(f"15.{n}" for n in range(1, 10)),
                         tuple(m["label"] for m in self.data["substations"]))
        self.assertEqual(dict(zip(MODULES, SECTION_COUNTS)),
                         dict(Counter(s["substation"] for s in self.data["theory"])))
        route = self.data.get("readingOrder", list(self.sections))
        self.assertEqual(set(self.sections), set(route))
        self.assertEqual(len(self.sections), len(route))
        self.assertEqual("learning-route", route[0])
        self.assertEqual("security-final-workbook", route[-1])
        order = {module: index for index, module in enumerate(MODULES)}
        route_groups = [order[self.sections[sid]["substation"]] for sid in route]
        self.assertEqual(sorted(route_groups), route_groups)

    def test_separate_banks_and_at_least_five_distinct_checkpoints_per_module(self):
        self.assertEqual({"basic":39, "advanced":40, "interview":20},
                         {kind:len(bank) for kind, bank in self.data["quizzes"].items()})
        expected = {"basic":4, "advanced":4, "interview":2}
        for kind, bank in self.data["quizzes"].items():
            with self.subTest(bank=kind):
                counts = {m:expected[kind] for m in MODULES}
                counts['cpp-security'] += {'basic': 1, 'advanced': 2, 'interview': 1}[kind]
                counts['identity-lifecycle'] += {'basic': 2, 'advanced': 2, 'interview': 1}[kind]
                self.assertEqual(counts,
                                 dict(Counter(q["substation"] for q in bank)))
        self.assertEqual(set(MODULES), set(self.resolved["checkpoints"]))
        expected_checkpoints = {module: 5 for module in MODULES}
        expected_checkpoints['identity-lifecycle'] = 7
        self.assertEqual(expected_checkpoints,
                         {module: len(qs) for module, qs in self.resolved["checkpoints"].items()})
        all_questions = self.main_questions + self.check_questions
        self.assertEqual(146, len(all_questions))
        prompts = [normalize_prompt(q["q"]) for q in all_questions]
        self.assertEqual(len(prompts), len(set(prompts)),
                         "Checkpoint and final/interview stems must not repeat")
        self.assertEqual(set(MODULES), set(self.resolved["checkpointVersion"]))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{12}", version)
                            for version in self.resolved["checkpointVersion"].values()))

    def test_question_references_exist_and_do_not_require_later_modules(self):
        order = {module:index for index, module in enumerate(MODULES)}
        for question in self.main_questions + self.check_questions:
            with self.subTest(question=question["q"]):
                self.assertTrue(question["theoryRefs"])
                self.assertEqual(len(question["theoryRefs"]), len(set(question["theoryRefs"])))
                for ref in question["theoryRefs"]:
                    self.assertIn(ref, self.sections)
                    self.assertLessEqual(order[self.sections[ref]["substation"]],
                                         order[question["substation"]])
        # The worked example lives in the station ending, after chapter checks.
        # A short chapter check must be answerable before that separate page.
        for question in self.check_questions:
            self.assertTrue(all(not is_workbook(self.sections[ref])
                                for ref in question["theoryRefs"]), question["q"])

    def test_resolver_does_not_mutate_canonical_and_generated_data_are_current(self):
        before = json.dumps(self.data, ensure_ascii=False, sort_keys=True)
        self.assertEqual(self.resolved, with_checkpoints(self.data))
        self.assertEqual(before, json.dumps(self.data, ensure_ascii=False, sort_keys=True))
        self.assertEqual(self.resolved, generated_data())
        self.assertEqual(html_for(self.resolved), (ROOT / PAGE).read_text(encoding="utf-8"))

    def test_each_section_has_self_check_and_linked_source_note(self):
        for sid, section in self.sections.items():
            with self.subTest(section=sid):
                checks = [b for b in section["blocks"] if b["type"] == "self-check"]
                self.assertTrue(checks, "Missing expandable learning check")
                self.assertTrue(all(b["prompt"].strip() and b["answer"].strip() for b in checks))
                source_links = []
                for block in section["blocks"]:
                    if block["type"] == "note":
                        source_links.extend(href for href in Fragment(block["html"]).links
                                            if href and urlsplit(href).scheme == "https")
                self.assertTrue(source_links, "Missing linked source note (presence only, not source audit)")
        for html in fields(self.data["theory"], "html"):
            fragment = Fragment(html)
            self.assertFalse(fragment.errors, fragment.errors)
            self.assertFalse(fragment.stack, fragment.stack)

    def test_module_checkpoint_follows_last_normal_theory_section(self):
        for module in MODULES:
            sections = [s for s in self.data["theory"]
                        if s["substation"] == module and not is_workbook(s)]
            with self.subTest(module=module):
                self.assertTrue(sections)
                last = sections[-1]["blocks"][-1]
                self.assertEqual("note", last["type"])
                self.assertIn("Контрольная точка", last["html"])

    def test_five_laboratory_blocks_have_exact_catalog_entries(self):
        catalog = load_json(ROOT / "content/visual-labs.json")["labs"]
        by_id = {lab["id"]:lab for lab in catalog}
        blocks = [(section["id"], block["lab"], block["scenario"])
                  for section in self.data["theory"] for block in section["blocks"]
                  if block["type"] == "lab"]
        self.assertEqual(5, len(blocks))
        self.assertEqual(LAB_ENTRIES, set(blocks))
        entries = []
        for lab in catalog:
            for entry in lab["entries"]:
                if entry["station"] == "station15":
                    entries.append((entry["section"], lab["id"], entry["scenario"]))
        self.assertEqual(5, len(entries))
        self.assertEqual(LAB_ENTRIES, set(entries))
        for section, lab_id, scenario in blocks:
            with self.subTest(lab=lab_id, scenario=scenario):
                lab = by_id[lab_id]
                self.assertTrue((ROOT / lab["file"]).is_file())
                self.assertEqual(1, sum(e["station"] == "station15"
                                       and e["section"] == section and e["scenario"] == scenario
                                       for e in lab["entries"]))

    def test_native_downloads_workbook_and_real_practice(self):
        directory = ROOT / "examples/station15"
        self.assertEqual(12, len(DOWNLOADS))
        for name in DOWNLOADS:
            path = directory / name
            with self.subTest(download=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertGreater(path.stat().st_size, 0)
        workbook = self.sections["security-final-workbook"]
        sources = [block["code"] for block in workbook["blocks"] if block["type"] == "code"]
        self.assertIn((directory / "access_policy.cpp").read_text(encoding="utf-8"), sources)
        self.assertTrue(any("int main(" in code for code in sources))
        self.assertFalse(any("__ACCESS_POLICY_FULL_SOURCE__" in code for code in sources))
        practices = [task for task in self.data["tasks"] if task["level"] == "Практика"]
        self.assertEqual(11, len(practices))
        self.assertEqual(set(MODULES), {task["substation"] for task in practices})
        self.assertTrue(all(t["title"].startswith("Лаборатория: ") for t in practices))
        self.assertTrue(all(len(t.get("checks", [])) >= 2 and t["solution"].strip()
                            for t in practices))
        for task in practices:
            self.assertTrue(set(task["theoryRefs"]) <= set(self.sections), task["title"])

    def test_home_has_twenty_one_ready_stations_with_current_counts_and_progress(self):
        home, page = home_data()
        all_stations = {path.stem:load_json(path)
                        for path in (ROOT / "content").glob("station*.json")}
        self.assertEqual(STATION_IDS, set(all_stations))
        stages = home["stages"]
        self.assertEqual(21, len(stages))
        self.assertEqual(list(range(1, 22)), [stage["num"] for stage in stages])
        self.assertTrue(all(stage.get("station") for stage in stages))
        by_file = {data["meta"]["sourceFile"]:data for data in all_stations.values()}
        self.assertEqual(set(by_file), {stage["station"]["file"] for stage in stages})
        for stage in stages:
            metadata = stage["station"]
            source = by_file[metadata["file"]]
            self.assertEqual(len(source["theory"]), metadata["totalSections"])
            self.assertEqual(source["meta"]["storeKey"], metadata["storeKey"])
        self.assertEqual("security", stages[-2]["id"])
        self.assertEqual(PAGE, stages[-2]["station"]["file"])
        self.assertEqual(42, stages[-2]["station"]["totalSections"])
        self.assertEqual("distributed-systems", stages[-1]["id"])
        self.assertEqual("cpp_station16_distributed_systems.html", stages[-1]["station"]["file"])
        for field in ("id", "storeKey", "sourceFile"):
            values = [data["meta"][field] for data in all_stations.values()]
            self.assertEqual(len(values), len(set(values)), field)
        groups = page.split("const groups = [", 1)[1].split("\n    ];", 1)[0]
        indices = {group:[int(n) for n in re.findall(r"\d+", raw)] for group, raw in
                   re.findall(r'id:\s*"([^"]+)"[^\n]*?indices:\s*\[([^\]]*)\]', groups)}
        self.assertEqual([15, 16, 17, 18, 19, 20], indices["backend-extension"])
        flattened = [index for group in indices.values() for index in group]
        self.assertEqual(list(range(21)), sorted(flattened))
        self.assertEqual(len(flattened), len(set(flattened)))


class SecurityPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # collect() returns bytes; deliberately do not call write_release().
        cls.files, cls.stations = publication.collect()

    def test_station_and_twelve_downloads_are_in_allowlisted_release_bytes(self):
        expected = {"station15/" + name for name in DOWNLOADS}
        allowed = {name for name in publication.EXAMPLES if name.startswith("station15/")}
        self.assertEqual(expected, allowed)
        self.assertEqual(len(publication.EXAMPLES), len(set(publication.EXAMPLES)))
        for name in expected:
            published = "roadmap/examples/" + name
            self.assertIn(published, self.files)
            self.assertEqual((ROOT / "examples" / name).read_bytes(), self.files[published])
        self.assertIn("roadmap/" + PAGE, self.files)
        self.assertIn("roadmap/generated/station15.data.js", self.files)
        self.assertIn("roadmap/security_sql_demo.html", self.files)
        self.assertIn("roadmap/security_labs.html", self.files)
        for name in self.files:
            path = PurePosixPath(name)
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertFalse({"authoring", ".git", "__pycache__", "content", "tools", "tests"}
                             & set(path.parts), name)
            self.assertNotIn(path.name, {".env", "private.env", "credentials.json"}, name)
        own = {name.removeprefix("roadmap/examples/station15/") for name in self.files
               if name.startswith("roadmap/examples/station15/")}
        self.assertEqual(DOWNLOADS, own)

    def test_release_link_and_privacy_guards_run_without_writing_or_network(self):
        checks = publication.check_release(self.files, self.stations)
        self.assertGreater(checks["local_links_checked"], 0)
        self.assertEqual(STATION_IDS, {data["meta"]["id"] for data in self.stations})
        # A successful guard run means the checked paths/references passed the
        # existing heuristics. It is not a universal secret scan or source audit.


if __name__ == "__main__":
    unittest.main()
