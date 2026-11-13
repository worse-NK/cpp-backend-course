"""Focused structure/model checks; actual PostgreSQL is opt-in in verify_gap_postgres.

The SQLite tests cover only the explicitly compatible model.sql subset. They do
not establish PostgreSQL locking, SQLSTATE, planner, or memory behavior.
"""
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import unittest

from build_stations import validate
from checkpoint_data import with_checkpoints
from verify_gap_postgres import cases

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
NEW_IDS = {
    "station9-sql": ["sql-relationship-design"],
    "station9": ["physical-join-workbook", "query-memory-spill-lab", "schema-history-boundaries"],
}
MIRRORED = {
    "sql-design/model.sql": ("station9-sql", "sql-relationship-design"),
    "sql-design/history.sql": ("station9", "schema-history-boundaries"),
    "query-execution/joins-setup.sql": ("station9", "physical-join-workbook"),
    "query-execution/join-query.sql": ("station9", "physical-join-workbook"),
    "query-execution/memory-setup.sql": ("station9", "query-memory-spill-lab"),
    "query-execution/statistics.sql": ("station9", "query-memory-spill-lab"),
}


class DatabaseGapChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {name: json.loads((ROOT / "content" / (name + ".json")).read_text())
                    for name in NEW_IDS}

    def sqlite_model(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript((EXAMPLES / "sql-design/model.sql").read_text())
        return db

    def test_canonical_schema_and_checkpoint_resolution(self):
        for name, data in self.data.items():
            with self.subTest(station=name):
                validate(data, ROOT / "content" / (name + ".json"))
                resolved = with_checkpoints(data)
                self.assertTrue(all(len(qs) >= 5 for qs in resolved["checkpoints"].values()))
                self.assertEqual(len({s["id"] for s in data["theory"]}), len(data["theory"]))

    def test_complete_listings_match_downloads(self):
        for relative, (station, section_id) in MIRRORED.items():
            with self.subTest(source=relative):
                section = next(s for s in self.data[station]["theory"] if s["id"] == section_id)
                codes = [b["code"] for b in section["blocks"] if b["type"] == "code"]
                self.assertIn((EXAMPLES / relative).read_text(), codes)

    def test_progressive_placement_sources_and_self_checks(self):
        for station, new_ids in NEW_IDS.items():
            data = self.data[station]
            ids = [s["id"] for s in data["theory"]]
            for sid in new_ids:
                section = next(s for s in data["theory"] if s["id"] == sid)
                self.assertGreaterEqual(sum(b["type"] == "self-check" for b in section["blocks"]), 2)
                source_notes = [b.get("html", "") for b in section["blocks"] if "postgresql.org/docs/18/" in b.get("html", "")]
                self.assertTrue(source_notes, sid)
                for block in section["blocks"]:
                    self.assertNotIn('\\"', block.get("html", ""), sid)
            if station == "station9-sql":
                self.assertLess(ids.index("tables"), ids.index("sql-relationship-design"))
                self.assertLess(ids.index("sql-relationship-design"), ids.index("sql-select-basics"))
                last = next(s for s in data["theory"] if s["substation"] == "tables" and s["id"] == "sql-relationship-design")
            else:
                self.assertLess(ids.index("storage-maintenance"), ids.index("physical-join-workbook"))
                self.assertLess(ids.index("physical-join-workbook"), ids.index("query-memory-spill-lab"))
                self.assertLess(ids.index("query-memory-spill-lab"), ids.index("cpp-storage"))
                self.assertLess(ids.index("design"), ids.index("schema-history-boundaries"))
                last = next(s for s in data["theory"] if s["id"] == "query-memory-spill-lab")
            self.assertIn("Контрольная точка", last["blocks"][-1]["html"])

    def test_new_assessments_are_appended_and_not_duplicate_stems(self):
        expected = {"station9-sql": {"basic": (29,2), "advanced": (8,2), "interview": (10,0)},
                    "station9": {"basic": (29,4), "advanced": (15,4), "interview": (22,3)}}
        # Later, independently reviewed work appends after this phase's stable
        # slices. Keep its exact count and provenance explicit instead of letting
        # new questions silently weaken the original fifteen-question contract.
        later_refs = {
            "station9-sql": {"basic": [], "advanced": [], "interview": []},
            "station9": {
                "basic": ["schema-history-boundaries"] * 2 + ["postgres-recovery-real-lab"] * 2,
                "advanced": ["schema-history-boundaries"] * 2 + ["postgres-recovery-real-lab"] * 2,
                "interview": ["postgres-recovery-real-lab"],
            },
        }
        total = 0
        for station, banks in expected.items():
            new_stems = set()
            for bank, (start, delta) in banks.items():
                entries = self.data[station]["quizzes"][bank]
                followup = later_refs[station][bank]
                self.assertEqual(len(entries), start + delta + len(followup))
                appended = entries[start:start + delta]
                total += len(appended)
                for entry in appended:
                    self.assertEqual(len(entry["options"]), 4)
                    self.assertTrue(set(entry["theoryRefs"]) & set(NEW_IDS[station]))
                    self.assertNotIn(entry["q"], new_stems)
                    new_stems.add(entry["q"])
                for entry, expected_ref in zip(entries[start + delta:], followup):
                    self.assertEqual(len(entry["options"]), 4)
                    self.assertIn(expected_ref, entry["theoryRefs"])
                    self.assertNotIn(entry["q"], new_stems)
                    new_stems.add(entry["q"])
            plan = json.loads((ROOT / "content/checkpoints" / (station + ".json")).read_text())
            for questions in plan["modules"].values():
                for entry in questions:
                    if "q" in entry:
                        self.assertNotIn(entry["q"], new_stems)
        self.assertEqual(total, 15)

    def test_compatible_sql_subset_model_rows(self):
        db = self.sqlite_model()
        self.assertEqual(db.execute("SELECT org_id,task_id,project_id,assignee_id,title FROM gd_task ORDER BY org_id,task_id").fetchall(),
                         [(1,100,7,10,"Review API"),(1,101,7,None,"Unassigned"),(2,100,7,20,"Review website")])
        self.assertEqual(db.execute("SELECT org_id,person_id FROM gd_member ORDER BY 1,2").fetchall(), [(1,10),(1,20),(2,20)])

    def test_compatible_sql_subset_foreign_keys_and_practice(self):
        db = self.sqlite_model()
        for query in (
            "INSERT INTO gd_member(org_id,person_id) VALUES(1,10)",
            "INSERT INTO gd_task VALUES(1,103,7,20,'Not a project member')",
            "INSERT INTO gd_task VALUES(1,103,999,NULL,'Missing project')",
            "DELETE FROM gd_project WHERE org_id=1 AND project_id=7",
        ):
            with self.subTest(query=query), self.assertRaises(sqlite3.IntegrityError):
                db.execute(query)
        db.execute("INSERT INTO gd_project_member VALUES(1,7,20)")
        db.execute("INSERT INTO gd_task VALUES(1,105,7,20,'Assigned to Bo')")
        self.assertEqual(db.execute("SELECT assignee_id FROM gd_task WHERE org_id=1 AND task_id=105").fetchone(), (20,))

    def test_prepared_join_models_agree_without_claiming_postgres_plan(self):
        people = [(1,"Anna"),(2,"Bo"),(4,"Dee")]
        tasks = [(10,1),(11,1),(12,2),(13,3)]
        nested = [(tid,name) for tid,owner in tasks for person,name in people if owner == person]
        mapping = dict(people)
        hashed = [(tid,mapping[owner]) for tid,owner in tasks if owner in mapping]
        merged = []
        ordered_people = sorted(people)
        position = 0
        for tid,owner in sorted(tasks, key=lambda t:t[1]):
            while position < len(ordered_people) and ordered_people[position][0] < owner:
                position += 1
            if position < len(ordered_people) and ordered_people[position][0] == owner:
                merged.append((tid,ordered_people[position][1]))
        self.assertEqual(nested, [(10,"Anna"),(11,"Anna"),(12,"Bo")])
        self.assertEqual(hashed, nested)
        self.assertEqual(merged, nested)
        self.assertEqual(len(tasks) * len(people), 12)

    def test_distribution_arithmetic_and_experiment_queries(self):
        uniform = sum(n % 1000 == 42 for n in range(1,100001))
        skew = sum((42 if n <= 90000 else n % 1000) == 42 for n in range(1,100001))
        self.assertEqual((uniform, skew), (100, 90010))
        join_cases = cases((EXAMPLES / "query-execution/joins-plans.sql").read_text())
        self.assertEqual([name for name,_ in join_cases], ["nested_loop","hash_join","merge_join"])
        queries = [body[body.index("SELECT "):body.index("COMMIT;")].strip() for _,body in join_cases]
        self.assertEqual(len(set(queries)), 1)
        memory = dict(cases((EXAMPLES / "query-execution/memory-plans.sql").read_text()))
        self.assertIn("work_mem='64kB'", memory["sort_small"])
        self.assertIn("work_mem='256kB'", memory["hash_small"])
        self.assertIn("work_mem='32MB'", memory["sort_large"])
        self.assertIn("work_mem='32MB'", memory["hash_large"])
        for source in memory.values():
            self.assertIn("SET LOCAL statement_timeout='20s'", source)
            self.assertIn("BEGIN;", source)
            self.assertIn("COMMIT;", source)

    def test_verifier_is_opt_in_and_owns_its_cleanup(self):
        verifier = ROOT / "tools/verify_gap_postgres.py"
        run = subprocess.run([sys.executable, str(verifier)], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("No action taken", run.stderr)
        source = verifier.read_text()
        for guard in ("--network=none", "--pull=never", "--read-only", "--cap-drop=ALL", "OWNER_LABEL", 'owned["Id"]'):
            self.assertIn(guard, source)
        self.assertNotIn("--privileged", source)
        self.assertNotIn("--network=host", source)
        self.assertNotIn('"-p"', source)
        for path in EXAMPLES.glob("sql-design/*.sql"):
            for match in re.finditer(r"CREATE\s+(?:(TEMP)\s+)?TABLE", path.read_text(), re.I):
                self.assertTrue(match.group(1), path)


if __name__ == "__main__":
    unittest.main()
