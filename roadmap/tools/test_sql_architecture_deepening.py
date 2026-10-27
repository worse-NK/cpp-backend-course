"""Execute the exact teaching SQL for JOIN multiplicity and window frames.

These tests use SQLite's in-memory engine for the documented common SQL
subset.  They do not claim to test PostgreSQL isolation, plans, or execution.
"""

import json
import re
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path

from build_stations import validate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content/station9-sql.json"
JOIN_ID = "sql-join-multiplication"
WINDOW_ID = "sql-window-peers"
PRACTICE_TITLE = "Лаборатория: две сводки и равное время событий"


def run_script(connection, script):
    """Run trusted course statements and retain each result, including empty ones."""
    results = []
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            cursor = connection.execute(pending)
            if cursor.description is not None:
                results.append(cursor.fetchall())
            pending = ""
    if pending.strip():
        cursor = connection.execute(pending)
        if cursor.description is not None:
            results.append(cursor.fetchall())
    return results


class SqlArchitectureDeepeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sqlite3.sqlite_version_info < (3, 25, 0):
            raise unittest.SkipTest("The documented SQL requires SQLite window functions (3.25+)")
        cls.data = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.sections = {section["id"]: section for section in cls.data["theory"]}

    def connect(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        self.addCleanup(connection.close)
        return connection

    def code_blocks(self, section_id):
        return [block["code"] for block in self.sections[section_id]["blocks"]
                if block["type"] == "code"]

    def prepared_join(self):
        connection = self.connect()
        run_script(connection, self.code_blocks(JOIN_ID)[0])
        return connection

    def test_source_schema_positions_and_final_checkpoints(self):
        validate(self.data, SOURCE)
        ids = [section["id"] for section in self.data["theory"]]
        self.assertEqual(ids[ids.index("join-shapes") + 1], JOIN_ID)
        self.assertEqual(ids[ids.index("sql-window-frame") + 1], WINDOW_ID)
        for group, last_id, predecessor in [
            ("aggregation", JOIN_ID, "join-shapes"),
            ("windows", WINDOW_ID, "sql-window-frame"),
        ]:
            grouped = [section for section in self.data["theory"] if section["substation"] == group]
            self.assertEqual(grouped[-1]["id"], last_id)
            self.assertIn("Контрольная точка", grouped[-1]["blocks"][-1]["html"])
            self.assertNotIn("Контрольная точка", self.sections[predecessor]["blocks"][-1].get("html", ""))

    def test_exact_join_listings_and_reported_results(self):
        setup, pairs, wrong, distinct, corrected = self.code_blocks(JOIN_ID)
        connection = self.connect()
        self.assertEqual(run_script(connection, setup), [])
        self.assertEqual(run_script(connection, pairs), [[
            (1, 10, 101, 100), (1, 10, 102, 100), (1, 10, 103, 300),
            (1, 11, 101, 100), (1, 11, 102, 100), (1, 11, 103, 300),
            (2, None, None, None),
        ]])
        self.assertEqual(run_script(connection, wrong), [[(1, 6, 6, 1000), (2, 0, 0, None)]])
        self.assertEqual(run_script(connection, distinct), [[(1, 2, 3, 400), (2, 0, 0, None)]])
        self.assertEqual(run_script(connection, corrected), [[
            (1, "Анна", 2, 3, 500), (2, "Борис", 0, 0, 0),
        ]])

    def test_only_payment_branch_does_not_require_tasks(self):
        connection = self.prepared_join()
        connection.execute("INSERT INTO join_demo_payments VALUES (104, 2, 50)")
        self.assertEqual(run_script(connection, self.code_blocks(JOIN_ID)[-1]), [[
            (1, "Анна", 2, 3, 500), (2, "Борис", 0, 1, 50),
        ]])

    def test_only_task_branch_empty_inputs_and_equal_user_names(self):
        corrected = self.code_blocks(JOIN_ID)[-1]
        connection = self.prepared_join()
        connection.execute("DELETE FROM join_demo_payments")
        connection.execute("INSERT INTO join_demo_users VALUES (3, 'Анна')")
        connection.execute("INSERT INTO join_demo_tasks VALUES (12, 3)")
        self.assertEqual(run_script(connection, corrected), [[
            (1, "Анна", 2, 0, 0), (2, "Борис", 0, 0, 0), (3, "Анна", 1, 0, 0),
        ]])
        connection.execute("DELETE FROM join_demo_tasks")
        self.assertEqual(run_script(connection, corrected), [[
            (1, "Анна", 0, 0, 0), (2, "Борис", 0, 0, 0), (3, "Анна", 0, 0, 0),
        ]])

    def test_exact_window_listings_and_reported_results(self):
        expected = [
            [(1, 600, 10, 30, 30), (2, 600, 20, 30, 30), (3, 601, 5, 35, 35)],
            [(600, 2, 1), (600, 2, 2), (601, 3, 3)],
            [(1, 10, 10), (2, 30, 30), (3, 35, 35)],
            [(1, 10, 5), (2, 20, 5), (3, 5, 5)],
        ]
        blocks = self.code_blocks(WINDOW_ID)
        self.assertEqual(len(blocks), len(expected))
        for index, (sql, rows) in enumerate(zip(blocks, expected)):
            with self.subTest(listing=index + 1):
                self.assertEqual(run_script(self.connect(), sql), [rows])

    def test_frame_comparisons_do_not_silently_change_window_order(self):
        expected_keys = ["at_minute", "at_minute", "at_minute, id", "at_minute, id"]
        for sql, keys in zip(self.code_blocks(WINDOW_ID), expected_keys):
            orders = re.findall(r"PARTITION BY owner_id ORDER BY ([^\n]+)", sql)
            self.assertEqual(orders, [keys, keys])
        same_order_comparison = self.code_blocks(WINDOW_ID)[1]
        selection = same_order_comparison.split("SELECT", 1)[1].split("FROM events", 1)[0]
        self.assertNotRegex(selection, r"\bid\b")
        self.assertIn("ORDER BY at_minute, rows_size", same_order_comparison)
        last_value = self.code_blocks(WINDOW_ID)[-1]
        self.assertEqual(last_value.count("ROWS BETWEEN UNBOUNDED PRECEDING"), 2)

    def test_partition_isolation_and_peer_input_reordering(self):
        values = "VALUES (1, 1, 600, 10), (2, 1, 600, 20), (3, 1, 601, 5)"
        reverse = "VALUES (3, 1, 601, 5), (2, 1, 600, 20), (1, 1, 600, 10)"
        for sql in self.code_blocks(WINDOW_ID):
            self.assertIn(values, sql)
            self.assertEqual(run_script(self.connect(), sql), run_script(self.connect(), sql.replace(values, reverse)))
        another_owner = values + ", (4, 2, 600, 7)"
        totals = run_script(self.connect(), self.code_blocks(WINDOW_ID)[0].replace(values, another_owner))[0]
        self.assertEqual({row[0]: row[-2:] for row in totals}, {
            1: (30, 30), 2: (30, 30), 3: (35, 35), 4: (7, 7),
        })
        last = run_script(self.connect(), self.code_blocks(WINDOW_ID)[-1].replace(values, another_owner))[0]
        self.assertEqual({row[0]: row[-2:] for row in last}, {
            1: (10, 5), 2: (20, 5), 3: (5, 5), 4: (7, 7),
        })

    def test_two_basic_and_two_interview_questions_trace_each_new_section(self):
        for section_id in (JOIN_ID, WINDOW_ID):
            for kind in ("basic", "interview"):
                relevant = [question for question in self.data["quizzes"][kind]
                            if section_id in question["theoryRefs"]]
                self.assertEqual(len(relevant), 2, (section_id, kind))
                self.assertTrue(all(question["why"].strip() for question in relevant))

    def test_practice_setup_and_exact_solution_are_runnable(self):
        task = next(task for task in self.data["tasks"] if task["title"] == PRACTICE_TITLE)
        self.assertEqual(task["level"], "Практика")
        self.assertTrue(task["title"].startswith("Лаборатория: "))
        self.assertEqual(set(task["theoryRefs"]), {JOIN_ID, WINDOW_ID})
        connection = self.connect()
        results = run_script(connection, task["code"] + "\n" + task["solution"])
        self.assertEqual(results, [
            [(1, 1, 600, 10), (2, 1, 600, 20), (3, 1, 601, 5)],
            [(1, "Анна", 2, 3, 500), (2, "Борис", 0, 0, 0)],
            [(1, 10, 5), (2, 30, 5), (3, 35, 5)],
        ])

    @unittest.skipUnless(shutil.which("gjs"), "GJS is needed to execute the vendored browser SQL engine")
    def test_exact_listings_on_actual_vendored_sqljs_engine(self):
        # This is a JS unit test, not browser automation.  It executes the same
        # offline SQLite code and SQL adapter that the trainer bundles.
        expected = {
            "join": [
                [[1, 10, 101, 100], [1, 10, 102, 100], [1, 10, 103, 300],
                 [1, 11, 101, 100], [1, 11, 102, 100], [1, 11, 103, 300],
                 [2, None, None, None]],
                [[1, 6, 6, 1000], [2, 0, 0, None]],
                [[1, 2, 3, 400], [2, 0, 0, None]],
                [[1, "Анна", 2, 3, 500], [2, "Борис", 0, 0, 0]],
            ],
            "windows": [
                [[1, 600, 10, 30, 30], [2, 600, 20, 30, 30], [3, 601, 5, 35, 35]],
                [[600, 2, 1], [600, 2, 2], [601, 3, 3]],
                [[1, 10, 10], [2, 30, 30], [3, 35, 35]],
                [[1, 10, 5], [2, 20, 5], [3, 5, 5]],
            ],
            "practice": [
                [[1, 1, 600, 10], [2, 1, 600, 20], [3, 1, 601, 5]],
                [[1, "Анна", 2, 3, 500], [2, "Борис", 0, 0, 0]],
                [[1, 10, 5], [2, 30, 5], [3, 35, 5]],
            ],
        }
        script = """
const GLib = imports.gi.GLib, BA = imports.byteArray;
const read = p => BA.toString(GLib.file_get_contents(p)[1]);
const data = JSON.parse(read('roadmap/content/station9-sql.json'));
const init = new Function(read('roadmap/vendor/sqljs/sql-asm.js') + ';return initSqlJs;')();
new Function(read('roadmap/assets/sql-lab-core.js'))();
const expected = EXPECTED_JSON;
function compare(got, want, label) {
    if (JSON.stringify(got) !== JSON.stringify(want))
        throw new Error(label + ': ' + JSON.stringify(got));
}
init().then(SQL => {
    const blocks = id => data.theory.find(s => s.id === id).blocks.filter(b => b.type === 'code');
    let db = SqlLab.seed(SQL, false);
    try {
        const join = blocks('sql-join-multiplication');
        SqlLab.execute(db, join[0].code);
        join.slice(1).forEach((b, i) => compare(SqlLab.execute(db, b.code)[0].values, expected.join[i], 'join ' + i));
    } finally { db.close(); }
    blocks('sql-window-peers').forEach((b, i) => {
        db = SqlLab.seed(SQL, false);
        try { compare(SqlLab.execute(db, b.code)[0].values, expected.windows[i], 'window ' + i); }
        finally { db.close(); }
    });
    db = SqlLab.seed(SQL, false);
    try {
        const task = data.tasks.find(t => t.title === 'Лаборатория: две сводки и равное время событий');
        compare(SqlLab.execute(db, task.code + '\\n' + task.solution).map(r => r.values), expected.practice, 'practice');
        print('PASS: exact course SQL on vendored SQLite ' + SqlLab.execute(db, 'SELECT sqlite_version();')[0].values[0][0]);
    } finally { db.close(); }
}).catch(error => { printerr(error.stack || error); imports.system.exit(1); });
""".replace("EXPECTED_JSON", json.dumps(expected, ensure_ascii=False))
        result = subprocess.run(
            [shutil.which("gjs"), "-c", script], cwd=ROOT.parent,
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: exact course SQL on vendored SQLite", result.stdout)


if __name__ == "__main__":
    unittest.main()
