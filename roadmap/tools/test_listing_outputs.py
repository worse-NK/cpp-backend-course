"""Reader-only verified outputs: source identity, scope, qualifications and deduplication."""
import copy
import json
import unittest

from build_listing_outputs import CONTENT, reading_sections
from verify_listing_outputs import checks


class ListingOutputs(unittest.TestCase):
    def raw(self, station):
        return json.loads((CONTENT / (station + ".json")).read_text())["theory"]

    def blocks(self, station, section):
        return next(s["blocks"] for s in reading_sections(station, self.raw(station))
                    if s["id"] == section)

    def test_intro_and_silent_example(self):
        intro = self.blocks("station0", "why-oop")
        screens = [b for b in intro if "verifiedOutput" in b]
        self.assertEqual([b["verifiedOutput"] for b in screens], ["1 2\n"])
        self.assertIn("int main()", screens[0]["code"])
        self.assertTrue(any(b.get("verifiedOutput") == "" for b in self.blocks("station2", "protected")))

    def test_condition_and_required_language(self):
        b = next(b for b in self.blocks("station3", "if-consteval23") if "verifiedOutput" in b)
        self.assertEqual((b["verifiedInput"], b["verifiedOutput"], b["verifiedOutputStandard"]),
                         ("7\n", "42 14\n", "23"))
        sections = reading_sections("station1", self.raw("station1"))
        for eid in ("s1-range-for-temporary23", "s1-implicit-move-reference"):
            b = next(b for s in sections for b in s["blocks"] if b.get("exampleId") == eid)
            self.assertEqual(b["verifiedOutputStandard"], "23")

    def test_multiple_outcomes_and_network_dependencies_untouched(self):
        blocks = self.blocks("station1", "copy-elision")
        named = next(b for b in blocks if "return local;" in b.get("code", "") and "int main" in b["code"])
        self.assertNotIn("verifiedOutput", named)
        for sec in self.raw("station7-netlab"):
            for b in self.blocks("station7-netlab", sec["id"]):
                self.assertNotIn("verifiedOutput", b)

    def test_moves_only_exact_authored_output_keeps_qualification_and_source(self):
        raw = self.raw("station0")
        original = copy.deepcopy(raw)
        s = next(s for s in reading_sections("station0", raw) if s["id"] == "clock-worked-example")
        self.assertEqual(raw, original)
        b = next(b for b in s["blocks"] if "verifiedOutput" in b)
        self.assertIn("восстанови", b["verifiedOutputCaption"])
        self.assertFalse(any(o.get("code") == b["verifiedOutput"].rstrip("\n") for o in s["blocks"]))
        self.assertTrue(any("g++ -std=" in o.get("code", "") for o in s["blocks"]))

    def test_pin_rejects_changed_program_instead_of_showing_stale_output(self):
        for station, marker in (("station0","int main"), ("station1","s1-implicit-move-reference")):
            raw = self.raw(station)
            if station == "station0":
                b = next(b for s in raw if s["id"] == "why-oop" for b in s["blocks"]
                         if marker in b.get("code", ""))
            else:
                b = next(b for s in raw for b in s["blocks"] if b.get("exampleId") == marker)
            b["code"] += "\n// deliberately changed"
            with self.assertRaisesRegex(ValueError, "changed"):
                reading_sections(station, raw)

    def test_every_disclosure_has_an_executable_check(self):
        paths = sorted(CONTENT.glob("station*.json"))
        runner = {(source, c["stdout"], c.get("stdin"), c["standard"])
                  for _, source, c in checks([p.stem for p in paths])}
        displayed = {(b["code"], b["verifiedOutput"], b.get("verifiedInput"), standard)
                     for p in paths for s in reading_sections(p.stem, self.raw(p.stem))
                     for b in s["blocks"] if "verifiedOutput" in b
                     for standard in b["verifiedOutputStandard"].split("/")}
        self.assertEqual(displayed, runner)
