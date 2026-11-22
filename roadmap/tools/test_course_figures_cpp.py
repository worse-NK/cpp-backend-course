"""Check values and ownership relationships shown in the C++/Linux reader."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_reading_figures import load


class CourseFiguresCpp(unittest.TestCase):
    def test_subspan_keeps_the_same_two_positions(self):
        _, _, _, figure = load("station3", "non-owning-vocabulary")
        before, after = (row["cells"] for row in figure["rows"])
        self.assertEqual([int(c["value"]) for c in before], [1, 2, 3, 4])
        self.assertEqual([int(c["value"]) for c in after], [1, 9, 3, 4])
        for row, expected_sum in ((before, 5), (after, 12)):
            positions = [i for i, c in enumerate(row) if c["state"] == "included"]
            self.assertEqual(positions, [1, 2])
            self.assertEqual(sum(int(row[i]["value"]) for i in positions), expected_sum)

    def test_distinct_descriptors_share_only_the_duplicated_offset(self):
        _, _, _, figure = load("station5-linux", "linux-fd-open-description", "reading-scene")
        self.assertEqual(figure["columns"], ["Прочитано", "first и same", "independent"])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "letters"
            path.write_bytes(b"ABC")
            with path.open("rb", buffering=0) as first, path.open("rb", buffering=0) as independent:
                with os.fdopen(os.dup(first.fileno()), "rb", buffering=0) as same:
                    observed = []
                    for stream in (first, same, independent):
                        byte = stream.read(1).decode("ascii")
                        self.assertEqual(first.tell(), same.tell())
                        observed.append([byte, str(first.tell()), str(independent.tell())])
        self.assertEqual(len(figure["frames"]), len(observed) + 1)
        for frame, (byte, a, b) in zip(figure["frames"], [["—", "0", "0"], *observed]):
            self.assertEqual(frame["values"],
                             [byte, f"{a} · перед {'ABC'[int(a)]}", f"{b} · перед {'ABC'[int(b)]}"])

    def test_deadlock_snapshot_has_a_wait_cycle_without_running_it(self):
        _, _, _, figure = load("station6", "deadlock")
        a, b = figure["rows"]
        held_a, waiting_a = (cell["value"] for cell in a["cells"])
        held_b, waiting_b = (cell["value"] for cell in b["cells"])
        self.assertNotEqual(held_a, held_b)
        self.assertEqual((waiting_a, waiting_b), (held_b, held_a))


if __name__ == "__main__":
    unittest.main()
