"""Inventory, validation and exercise-specific invariants of the inline edition."""
import copy
import json
import unittest

from build_stations import CONTENT, validate_scene


ROUTES = {
    "station0": ("why-oop", "struct-to-class", "constructor", "special-members-intro"),
    "station1": ("smart-ptr", "smart-ptr-deep"), "station2": ("slicing",), "station3": ("iterators",),
    "station4": ("exception-safety",), "station5": ("ipc-pipes-shared-memory",),
    "station5-linux": ("linux-fd-open-description",), "station6": ("spsc-ring-model",),
    "station7": ("level-edge-triggered",), "station7-netlab": ("netlab-bridge-learning",),
    "station7-traffic": ("traffic-wireshark-three-panes",), "station8": ("conditional-update",),
    "station9-sql": ("sql-window-frame",), "station9": ("cache-race",), "station10": ("request-budget-architecture",),
    "station11": ("kafka-parallel-frontier",), "station12": ("eviction-and-expiry",),
    "station13": ("service-and-endpoints",), "station14": ("histogram-buckets",),
    "station15": ("identity-revocation-timeline",), "station16": ("raft-log-commit",),
}
SCROLL = {"smart-ptr", "smart-ptr-deep", "ipc-pipes-shared-memory", "spsc-ring-model", "conditional-update",
          "cache-race", "kafka-parallel-frontier"}


class ReadingScenes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenes = {}
        cls.found = {}
        for path in CONTENT.glob("station*.json"):
            station = json.loads(path.read_text())
            ids = []
            for section in station["theory"]:
                for index, b in enumerate(section["blocks"]):
                    if b["type"] == "reading-scene":
                        if b["id"] in cls.scenes or index == 0:
                            raise AssertionError(f"Duplicate scene or missing introduction: {section['id']}")
                        validate_scene(b, section["id"], str(path))
                        cls.scenes[b["id"]] = b
                        ids.append(b["id"])
            cls.found[path.stem] = tuple(ids)

    def test_all_named_lessons_exactly_once(self):
        self.assertEqual(self.found, ROUTES)
        self.assertEqual({k for k, b in self.scenes.items() if b["mode"] == "scroll"}, SCROLL)

    def test_owners_and_remainders(self):
        owners = self.scenes["smart-ptr"]["frames"]
        self.assertEqual([f.get("edges", []) for f in owners], [[[0,2]], [[0,2]], [[1,2]], []])
        self.assertEqual([f["values"][2] for f in owners[:3]], ["5"] * 3)
        shared = self.scenes["smart-ptr-deep"]["frames"]
        self.assertEqual([len([e for e in f.get("edges", []) if len(e) == 2]) for f in shared], [1,2,2,1,0,0])
        self.assertEqual([f["values"] for f in self.scenes["why-oop"]["frames"]], [["1","0","true"], ["0","0","false"]])

    def test_console_is_distinct_from_number_of_owners(self):
        shared = self.scenes["smart-ptr-deep"]["frames"]
        self.assertEqual([f["output"] for f in shared], ["","","2","2 1","2 1 destroy","2 1 destroy 1 0"])

    def test_failed_conditional_write_leaves_the_accepted_edit(self):
        frames = self.scenes["conditional-update"]["frames"]
        self.assertEqual(frames[0]["values"], ["Черновик · v7"]*3)
        self.assertEqual([f["values"][1] for f in frames[2:]], ["На проверке · v8"]*3)
        self.assertEqual(frames[-1]["code"], "412 Precondition Failed")

    def test_validation_rejects_misaligned_cells_links_and_ranges(self):
        for key, value in (("values",["only one"]), ("focus",[True]), ("focus",[0,0]), ("edges",[[0,99]]),
                           ("edges",[[0,0]]), ("edges",[[0,1,"typo"]]), ("span",[4,3])):
            block=copy.deepcopy(self.scenes["smart-ptr"])
            block["frames"][0][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                validate_scene(block, block["id"], "test")
        block=copy.deepcopy(self.scenes["request-budget-architecture"])
        block["frames"][0]["span"][1] = 400
        with self.assertRaises(ValueError):
            validate_scene(block, block["id"], "test")
