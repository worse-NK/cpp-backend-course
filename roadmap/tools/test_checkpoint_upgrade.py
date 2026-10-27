"""Dedicated five-question checkpoints, taught syntax and disjoint final exams."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from checkpoint_data import with_checkpoints, normalize_prompt
from build_stations import load_json, validate

ROOT = Path(__file__).resolve().parents[1]


class Checkpoints(unittest.TestCase):
    def test_every_module_has_five_independent_questions(self):
        actual = json.loads(subprocess.check_output(
            ["gjs", "roadmap/tools/export_final_selection.js"], cwd=ROOT.parent, text=True))
        modules, questions, assemblies = 0, 0, 0
        for path in sorted((ROOT / "content").glob("station*.json")):
            with self.subTest(station=path.stem):
                source = load_json(path)
                validate(source, path)
                original = copy.deepcopy(source)
                browser = with_checkpoints(source)
                self.assertEqual(source, original, "Resolver mutated canonical source")
                finals = actual["stations"][path.stem]["reserved"]
                final_stems = {normalize_prompt(source["quizzes"][ref["bank"]][ref["index"]]["q"])
                               for ref in finals}
                self.assertEqual(len(final_stems), 25)
                for module, entries in browser["checkpoints"].items():
                    self.assertEqual(len(entries), 5)
                    self.assertEqual(len(browser["checkpointVersion"][module]), 12)
                    modules += 1
                    questions += len(entries)
                    for question in entries:
                        self.assertNotIn(normalize_prompt(question["q"]), final_stems,
                                         "Checkpoint repeats the final exam")
                        assemblies += question.get("type") == "assemble"
        self.assertEqual(modules, 96)
        self.assertEqual(questions, 480)
        self.assertEqual(assemblies, 8)

    def test_short_or_future_checkpoints_are_rejected(self):
        source = load_json(ROOT / "content/station0.json")
        plan = load_json(ROOT / "content/checkpoints/station0.json")
        module = source["substations"][0]["id"]
        for problem in ("too-short", "bad-token", "future"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(plan)
                if problem == "too-short":
                    changed["modules"][module] = changed["modules"][module][:3]
                else:
                    inline = next(q for q in changed["modules"][module] if q.get("type") == "assemble")
                    if problem == "bad-token":
                        inline["answer"] = [999]
                    else:
                        inline["theoryRefs"] = ["destructor"]
                (Path(directory) / "station0.json").write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    with_checkpoints(source, Path(directory))

    def test_changed_content_invalidates_only_affected_checkpoint(self):
        source = load_json(ROOT / "content/station0.json")
        before = with_checkpoints(source)
        plan = load_json(ROOT / "content/checkpoints/station0.json")
        module = source["substations"][0]["id"]
        entry = next(q for q in plan["modules"][module] if "why" in q)
        entry["why"] += " Дополнительное объяснение."
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "station0.json").write_text(json.dumps(plan))
            after = with_checkpoints(source, Path(directory))
        for identifier in before["checkpoints"]:
            self.assertEqual(before["checkpointVersion"][identifier] == after["checkpointVersion"][identifier],
                             identifier != module)

    @unittest.skipUnless(shutil.which("g++"), "C++ compiler unavailable")
    def test_all_assembled_station0_programs_compile(self):
        data = with_checkpoints(load_json(ROOT / "content/station0.json"))
        for module, questions in data["checkpoints"].items():
            for question in questions:
                if question.get("type") != "assemble":
                    continue
                with self.subTest(module=module, q=question["q"]):
                    source = question["before"] + " ".join(question["tokens"][i] for i in question["answer"]) + question["after"]
                    if "int main(" not in source and "int main ()" not in source:
                        source += "\nint main() {}\n"
                    with tempfile.TemporaryDirectory(prefix="checkpoint-code-") as directory:
                        binary = str(Path(directory) / "example")
                        result = subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic-errors", "-x", "c++", "-", "-o", binary],
                                                input=source, text=True, capture_output=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr + "\n" + source)
                        run = subprocess.run([binary], capture_output=True, text=True, timeout=3)
                        self.assertEqual(run.returncode, 0, run.stderr + "\n" + source)

    def test_factory_is_taught_before_the_test_and_in_glossary(self):
        station = load_json(ROOT / "content/station0.json")
        section = next(s for s in station["theory"] if s["id"] == "valid-states-factories")
        text = json.dumps(section, ensure_ascii=False).casefold()
        for word in ("фабрик", "конструктор", "перегруз", "point"):
            self.assertIn(word, text)
        glossary = load_json(ROOT / "content/glossary.json")
        entry = next(e for e in glossary["entries"] if e["id"] == "factory-function")
        self.assertEqual(entry["learn"]["section"], section["id"])
        self.assertGreaterEqual(sum(b["type"] == "self-check" for s in station["theory"] for b in s["blocks"]), 12)
