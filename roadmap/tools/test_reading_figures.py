"""Check the boundaries illustrated on the reading page, not pixel colors."""
import copy
import re
import sqlite3
import unittest

import build_stations


def load(station, section, kind="reading-figure"):
    path = build_stations.CONTENT / (station + ".json")
    data = build_stations.load_json(path)
    blocks = next(s["blocks"] for s in data["theory"] if s["id"] == section)
    figure, = (b for b in blocks if b["type"] == kind)
    return path, data, blocks, figure


class ReadingFigures(unittest.TestCase):
    def test_iterator_excludes_exactly_the_past_end_position(self):
        _, _, blocks, f = load("station3", "iterators", "reading-scene")
        self.assertEqual(f["columns"], ["10", "20", "30", "end()"])
        self.assertTrue(any("{10, 20, 30}" in b.get("code", "") for b in blocks))
        self.assertEqual([r["focus"] for r in f["frames"]], [[0], [1], [2], [3]])
        for pos, row in enumerate(f["frames"]):
            self.assertEqual([i for i, value in enumerate(row["values"]) if value == "it здесь"], [pos])
            if pos < 3:
                self.assertEqual(row["values"][-1], "граница")
        boundary = f["frames"][-1]
        self.assertEqual(boundary["code"], "it != v.end()")
        self.assertIn("не читает *it", boundary["note"])

    def test_window_memberships_match_the_printed_query(self):
        _, _, blocks, f = load("station9-sql", "sql-window-frame", "reading-scene")
        sql, = (b["code"] for b in blocks if b["type"] == "code")
        # This standard ROWS example is also executable on the course's SQLite engine.
        db = sqlite3.connect(":memory:")
        try:
            db.execute("create table tasks (id integer primary key, owner_id integer)")
            data = [(10, 1), (11, 1), (12, 2)]
            db.executemany("insert into tasks values (?, ?)", data)
            results = list(db.execute(sql))
        finally:
            db.close()
        self.assertEqual(f["columns"], [f"Задача {task} · владелец {owner}" for task, owner in data])
        self.assertEqual(len(results), len(f["frames"]))
        for row, (task, owner, total, count) in zip(f["frames"], results):
            self.assertEqual(row["label"], f"Текущая задача {task}")
            positions = [i for i, (t, o) in enumerate(data) if o == owner and t <= task]
            self.assertEqual(row["focus"], positions)
            self.assertEqual([i for i, c in enumerate(row["values"]) if c == "В рамке"], positions)
            self.assertEqual(len(positions), count)
            for alias, value in (("all_tasks", total), ("tasks_so_far", count)):
                self.assertEqual(re.findall(rf"\b{alias} = (\d+)", row["note"]), [str(value)])

    def test_restart_points_are_positions_not_last_completed_records(self):
        _, _, _, f = load("station11", "kafka-consumer-positions")
        marks = [[c["value"] for c in r["cells"] if c["state"] == "boundary"] for r in f["rows"]]
        self.assertEqual(marks, [["40"], ["41"]])

    def test_storage_lifetime_depends_on_what_is_replaced(self):
        _, _, _, f = load("station13", "filesystem-lifetimes")
        surviving = [[c["value"] for c in r["cells"] if c["state"] == "included"] for r in f["rows"]]
        self.assertEqual(surviving, [["Слой контейнера", "emptyDir"], ["emptyDir"], []])

    def test_missing_cell_text_and_unaligned_rows_are_rejected(self):
        path, data, _, f = load("station13", "filesystem-lifetimes")
        original = copy.deepcopy(f)
        f["rows"][1]["cells"][0]["note"] = ""
        with self.assertRaisesRegex(ValueError, "non-empty"):
            build_stations.validate(data, path)
        f["rows"] = original["rows"]
        f["rows"][0]["cells"].pop()
        with self.assertRaisesRegex(ValueError, "aligned cells"):
            build_stations.validate(data, path)

    def test_layouts_require_matching_axes_only_for_tables(self):
        path, data, _, f = load("station13", "filesystem-lifetimes")
        headers = ["Событие"] + [c["value"] for c in f["rows"][0]["cells"]]
        for layout in ("compare", "flow"):
            f["layout"] = layout
            build_stations.validate(data, path)
            f["columns"] = headers
            with self.assertRaisesRegex(ValueError, "expected keys"):
                build_stations.validate(data, path)
            del f["columns"]
        f["layout"] = "matrix"
        with self.assertRaisesRegex(ValueError, "expected keys"):
            build_stations.validate(data, path)
        for invalid in ([], headers[:-1], headers + ["лишнее"]):
            f["columns"] = invalid
            with self.assertRaisesRegex(ValueError, "axis"):
                build_stations.validate(data, path)
        f["columns"] = headers
        build_stations.validate(data, path)
        f["layout"] = "typo"
        with self.assertRaisesRegex(ValueError, "layout"):
            build_stations.validate(data, path)

    def test_time_chart_uses_real_nested_intervals_and_validates_its_axis(self):
        path = build_stations.CONTENT / "station14.json"
        data = build_stations.load_json(path)
        section = next(s for s in data["theory"] if s["id"] == "trace-tree")
        chart, = (b for b in section["blocks"] if b["type"] == "time-chart")
        ranges = [(i["start"], i["end"]) for i in chart["intervals"]]
        self.assertEqual([end-start for start, end in ranges], [250, 210, 180])
        self.assertEqual(ranges[0], (0, chart["duration"]))
        for (a, b), (c, d) in zip(ranges, ranges[1:]):
            self.assertTrue(a <= c < d <= b)
        for a, b in ((20, 20), (-1, 20), (1, 251), (True, 5), (0, 1.5)):
            chart["intervals"][0].update(start=a, end=b)
            with self.assertRaisesRegex(ValueError, "time axis"):
                build_stations.validate(data, path)


if __name__ == "__main__":
    unittest.main()
