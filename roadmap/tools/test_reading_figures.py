"""Check the boundaries illustrated on the reading page, not pixel colors."""
import copy
import sqlite3
import unittest

import build_stations


def load(station, section):
    path = build_stations.CONTENT / (station + ".json")
    data = build_stations.load_json(path)
    blocks = next(s["blocks"] for s in data["theory"] if s["id"] == section)
    figure, = (b for b in blocks if b["type"] == "reading-figure")
    return path, data, blocks, figure


class ReadingFigures(unittest.TestCase):
    def test_iterator_excludes_exactly_the_past_end_position(self):
        _, _, _, f = load("station3", "iterators")
        cells = f["rows"][0]["cells"]
        self.assertEqual([c["value"] for c in cells if c["state"] == "included"], ["10", "20", "30"])
        self.assertEqual([c["value"] for c in cells if c["state"] == "boundary"], ["end()"])

    def test_window_memberships_match_the_printed_query(self):
        _, _, blocks, f = load("station9-sql", "sql-window-frame")
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
        self.assertEqual(len(results), len(f["rows"]))
        for row, (task, owner, _, count) in zip(f["rows"], results):
            members = [int(c["value"]) for c in row["cells"] if c["state"] == "included"]
            self.assertEqual(members, [t for t, o in data if o == owner and t <= task])
            self.assertEqual(len(members), count)

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


if __name__ == "__main__":
    unittest.main()
