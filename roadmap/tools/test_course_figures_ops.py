"""Compare worked figures with the lesson's Dockerfile, arithmetic and example histories."""
from fractions import Fraction
import json
from pathlib import Path
import re
import unittest

from test_reading_figures import load


def percentage(label):
    return Fraction(label.strip("≈ %").replace(",", "."))


class OperationsFigures(unittest.TestCase):
    def test_each_request_phase_consumes_the_original_budget(self):
        _, _, _, scene = load("station10", "request-budget-architecture", "reading-scene")
        axis = scene["axis"]
        self.assertEqual(axis, {"min": 0, "max": 300, "unit": "мс"})
        previous = axis["min"]
        for row in scene["frames"]:
            start, end = row["span"]
            self.assertEqual(start, previous)
            self.assertGreater(end, start)
            self.assertEqual(row["values"], [f"{end - start} мс", f"{axis['max'] - end} мс"])
            previous = end
        self.assertEqual(scene["frames"][3]["span"], [200, 220])  # SQL itself
        self.assertEqual(previous, 260)

    def test_kafka_commit_position_advances_only_over_a_finished_prefix(self):
        _, _, _, scene = load("station11", "kafka-parallel-frontier", "reading-scene")
        offsets = [int(col.split()[-1]) for col in scene["columns"][:-1]]
        self.assertEqual(offsets, [100, 101, 102])
        finished = set()
        snapshots = [set(), {102}, {100, 102}, {100, 101, 102}]
        self.assertEqual(len(scene["frames"]), len(snapshots))
        for row, expected in zip(scene["frames"], snapshots):
            states, displayed_next = row["values"][:-1], int(row["values"][-1])
            self.assertLessEqual(set(states), {"В работе", "Готова"})
            now = {offset for offset, state in zip(offsets, states) if state == "Готова"}
            self.assertEqual(now, expected)
            self.assertLessEqual(finished, now)
            self.assertEqual(displayed_next, next((n for n in offsets if n not in now), offsets[-1] + 1))
            finished = now

    def test_classic_histogram_counts_inclusive_cumulative_buckets(self):
        _, _, _, scene = load("station14", "histogram-buckets", "reading-scene")
        self.assertEqual(scene["columns"], ["≤ 0,1 с", "≤ 0,3 с", "≤ 1 с", "+Inf"])
        # Integer milliseconds, including two values right on a boundary.
        observations, prior = [], [0] * 4
        groups = [[50, 100], [120], [300, 800]]
        self.assertEqual(len(scene["frames"]), len(groups))
        for row, more in zip(scene["frames"], groups):
            observations.extend(more)
            counts = [sum(x <= bound for x in observations) for bound in [100, 300, 1000, float("inf")]]
            self.assertEqual(list(map(int, row["values"])), counts)
            if prior[-1]:
                self.assertEqual(row["focus"], [i for i in range(4) if counts[i] != prior[i]])
            prior = counts

    def test_only_named_artifact_crosses_stage_boundary(self):
        _, _, blocks, figure = load("station10", "docker-build")
        dockerfile, = (b["code"] for b in blocks if b["type"] == "code")
        _, second = dockerfile.split("FROM debian:bookworm-slim AS runtime")
        (source, dest), = re.findall(r"^COPY --from=build (\S+) (\S+)$", second, re.M)
        build, copy, runtime = figure["rows"][0]["cells"]
        self.assertEqual([build["value"], copy["value"], runtime["value"]],
                         ["build", "COPY --from=build", "runtime"])
        self.assertIn(source.split("/")[-1], copy["note"])
        self.assertIn(dest.rsplit("/", 1)[0], runtime["note"])
        self.assertIn("libstdc++6", second)
        self.assertIn("libstdc++6", runtime["note"])

    def test_wait_threshold_and_illustrated_receipts(self):
        _, _, blocks, f = load("station12", "replica-ack-wait")
        commands, = (b["code"] for b in blocks if b["type"] == "code")
        write, wait = commands.splitlines()
        wanted, timeout = map(int, wait.split()[1:])
        self.assertGreater(timeout, 0)
        primary, *replicas = f["rows"][0]["cells"]
        version = write.split()[-1]
        self.assertTrue(primary["value"].endswith(version))
        self.assertEqual(sum(c["value"].endswith(version) for c in replicas), wanted)
        self.assertTrue(any(c["state"] == "outside" for c in replicas))

    def test_global_error_fraction_is_weighted_by_requests(self):
        _, _, _, f = load("station14", "weighted-errors")
        totals, rates = [], []
        for row in f["rows"]:
            count, rate = (c["value"] for c in row["cells"])
            bad, all_requests = tuple(map(int, count.replace("\u202f", "").split(" из ")))
            totals.append((bad, all_requests))
            rates.append(percentage(rate))
            # The displayed percentages are rounded to at most three decimals.
            self.assertLessEqual(abs(rates[-1] - Fraction(bad * 100, all_requests)),
                                 Fraction(1, 2000))
        self.assertEqual(totals[-1], tuple(map(sum, zip(*totals[:-1]))))
        self.assertEqual(sum(rates[:-1]) / 2, percentage("5,05%"))
        self.assertNotEqual(rates[-1], sum(rates[:-1]) / 2)

    def test_redis_transaction_maps_each_queued_command_to_its_own_reply(self):
        _, _, blocks, figure = load("station12", "multi-exec-errors")
        script, = (b["code"] for b in blocks if b["type"] == "code")
        setup, begin, increment, marker, execute, read = [line.split() for line in script.splitlines()]
        self.assertEqual((begin, execute), (["MULTI"], ["EXEC"]))
        self.assertEqual(increment, ["INCR", setup[1]])
        with self.assertRaises(ValueError):
            int(setup[2])  # The illustrated INCR cannot parse this counter as an integer.
        self.assertEqual(read, ["GET", marker[1]])
        (queued1, failed), (queued2, saved) = [r["cells"] for r in figure["rows"]]
        self.assertEqual([queued1["value"], queued2["value"]], ["QUEUED", "QUEUED"])
        self.assertIn(setup[2], failed["note"])
        self.assertEqual(failed["state"], "outside")
        self.assertEqual(saved["value"], "OK")
        self.assertIn(marker[2], saved["note"])

    def test_quorum_counterexample_matches_shared_member_and_max_rule(self):
        _, _, _, f = load("station16", "quorum-intersections")
        shared, = re.findall(r"узел ([A-E])", f["columns"][2])
        members, results = [], []
        for row in f["rows"]:
            other, common, result = [c["value"] for c in row["cells"]]
            readings = {node: int(v) for node, v in re.findall(r"([A-E]): v(\d+)", other)}
            readings[shared] = int(common.removeprefix("v"))
            members.append(set(readings))
            self.assertEqual(len(readings), 3)
            self.assertEqual(result, f"v{max(readings.values())}")
            results.append(result)
        self.assertEqual(set.intersection(*members), {"C"})
        self.assertEqual(results, ["v2", "v1"])

    def test_outbox_marker_alone_cannot_distinguish_the_two_crashes(self):
        _, _, _, f = load("station11", "outbox-integration")
        before, after = [r["cells"] for r in f["rows"]]
        self.assertEqual(before[0]["value"], after[0]["value"])
        self.assertIn("NULL", before[0]["value"])
        self.assertIn("0 публикаций", before[1]["value"])
        self.assertIn("1 публикация", after[1]["value"])

    def test_trace_durations_match_the_three_spans_in_the_worked_example(self):
        path = Path(__file__).resolve().parents[1] / "content/station14.json"
        section, = (s for s in json.loads(path.read_text())["theory"] if s["id"] == "trace-tree")
        chart, = (b for b in section["blocks"] if b["type"] == "time-chart")
        spans = chart["intervals"]
        self.assertEqual(chart["duration"], 250)
        self.assertEqual([s["end"] - s["start"] for s in spans], [250, 210, 180])
        for parent, child in zip(spans, spans[1:]):
            self.assertLessEqual(parent["start"], child["start"])
            self.assertLessEqual(child["end"], parent["end"])


if __name__ == "__main__":
    unittest.main()
