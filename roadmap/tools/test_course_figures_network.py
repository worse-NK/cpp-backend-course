"""Cross-check examples drawn in the networking and database chapters."""
from contextlib import closing
from html.parser import HTMLParser
import re
import sqlite3
import unittest

from test_reading_figures import load


class TableRows(HTMLParser):
    """Only data cells: the SQL disclosure also contains a caption and headings."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag == "td":
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td":
            self.row.append(None if self.cell == "NULL" else int(self.cell))
            self.cell = None
        if tag == "tr" and self.row:
            self.rows.append(tuple(self.row))


class NetworkAndDataFigures(unittest.TestCase):
    def test_join_matrix_and_full_disclosure_match_the_course_query(self):
        _, _, blocks, f = load("station9-sql", "sql-join-multiplication")
        setup, pairs, *_ = (b["code"] for b in blocks if b["type"] == "code")
        with closing(sqlite3.connect(":memory:")) as db:
            db.executescript(setup)
            actual = list(db.execute(pairs))
        payments = [int(c.split()[-1]) for c in f["columns"][1:]]
        drawn = [(1, int(row["label"].split()[-1]), payment, int(cell["value"]))
                 for row in f["rows"] for payment, cell in zip(payments, row["cells"])]
        self.assertEqual(drawn, [r for r in actual if r[0] == 1])
        self.assertEqual(actual[-1], (2, None, None, None))
        disclosure, = (b["html"] for b in blocks if "<details>" in b.get("html", "")
                       and "payment_id" in b["html"])
        table = TableRows()
        table.feed(disclosure)
        self.assertEqual(table.rows, actual)

    def test_endian_rows_decode_the_same_bytes(self):
        _, _, _, f = load("station7", "endian-frame-cpp20-cpp23")
        payload = bytes.fromhex("00 00 01 00")
        for row, order in zip(f["rows"], ("big", "little"), strict=True):
            self.assertEqual(bytes.fromhex(" ".join(c["value"] for c in row["cells"])), payload)
            number = int(re.search(r"([\d ]+)$", row["label"])[1].strip().replace(" ", ""))
            self.assertEqual(number, int.from_bytes(payload, order))

    def test_conntrack_reply_matches_course_endpoints_without_nat(self):
        _, _, _, f = load("station7-netlab", "netlab-conntrack-states")
        send, reply = ([c["value"] for c in row["cells"]] for row in f["rows"])
        self.assertEqual(send, ["192.0.2.10:40000", "198.51.100.10:9000"])
        self.assertEqual(reply, send[::-1])


if __name__ == "__main__":
    unittest.main()
