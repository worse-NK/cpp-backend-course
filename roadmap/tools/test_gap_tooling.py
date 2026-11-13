"""Safe tooling checks; optional real probes report unsupported, not PASS/skip.

Default unittest execution builds only own examples in a new temporary folder.
--integration additionally creates a core of report_before under GDB, probes
perf on its own child, and optionally uses a supplied Conan 2.22.2 executable.
It never installs tools, attaches to an existing process or changes sysctl.
An unavailable integration returns 2; a failed check returns 1.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import unittest

from build_stations import load_json, validate
from checkpoint_data import with_checkpoints


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/tooling-closed-loop"
SECTIONS = ("gdb-core-regression", "perf-cpu-wait-workbook", "conan-target-lock-workbook")


def call(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], text=True, capture_output=True,
                          timeout=kwargs.pop("timeout", 45), **kwargs)


def checked(args, **kwargs):
    result = call(args, **kwargs)
    if result.returncode:
        raise AssertionError(f"{args[0]} returned {result.returncode}: "
                             f"{(result.stdout + result.stderr)[-4000:]}")
    return result


def build_native(work):
    build = work / "build"
    checked(["cmake", "-S", SOURCE, "-B", build, "-G", "Ninja"])
    checked(["cmake", "--build", build, "--parallel", "2"])
    return build


class Downloads(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        href = values.get("href", "")
        if tag == "a" and href.startswith("examples/tooling-closed-loop/"):
            if "download" not in values:
                raise AssertionError(f"Missing download attribute: {href}")
            self.paths.append(href)


class ToolingClosedLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="course-tooling-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.build = build_native(Path(cls.temporary.name))
        cls.data = load_json(ROOT / "content/station5.json")
        cls.sections = {section["id"]: section for section in cls.data["theory"]}

    def test_schema_order_and_concluding_checkpoints(self):
        validate(self.data, ROOT / "content/station5.json")
        with_checkpoints(self.data)
        route = self.data["readingOrder"]
        for before, added, after in (
            ("ci-cross-build-tests", SECTIONS[2], "tooling"),
            ("diagnostics-production", SECTIONS[0], "stacktrace-capture"),
            ("profile-comparison-workbook", SECTIONS[1], "build-final-workbook"),
        ):
            index = route.index(before)
            self.assertEqual(route[index:index + 3], [before, added, after])
        self.assertIn("Контрольная точка 5.4.", self.sections["tooling"]["blocks"][-1]["html"])
        self.assertIn("Контрольная точка 5.5.", self.sections["summary"]["blocks"][-1]["html"])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station5_progress_v1")

    def test_fixed_program_and_registered_regression(self):
        for argument, expected in (("empty", "no tasks\n"),
                                   ("ready", "first task: 41\n"),
                                   ("--self-test", "regression: OK\n")):
            result = checked([self.build / "report_fixed", argument])
            self.assertEqual(result.stdout, expected)
        checked(["ctest", "--test-dir", self.build, "--output-on-failure"])
        # Never run the empty bad program without a debugger.
        result = checked([self.build / "report_before", "ready"])
        self.assertEqual(result.stdout, "first task: 41\n")
        self.assertEqual(result.stderr, "tasks=2\n")

    def test_workload_counts_results_and_input_bounds(self):
        expected = {"cpu": "14768256629272300802", "wait": "6213229451036900623"}
        for mode, checksum in expected.items():
            result = checked([self.build / "perf_workload", mode, "40"])
            self.assertIn(f"mode={mode} requests=40 checksum={checksum}", result.stdout)
            match = re.search(r"wall_ms=([\d.]+) cpu_ms=([\d.]+)", result.stdout)
            self.assertIsNotNone(match)
            self.assertGreater(float(match[1]), 0)
            self.assertGreaterEqual(float(match[2]), 0)
        for args in (("cpu", "101"), ("cpu", "0"), ("cpu", "-1"),
                     ("cpu", "5junk"), ("unknown", "1")):
            result = call([self.build / "perf_workload", *args])
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("checksum=", result.stdout)

    def test_new_banks_checkpoint_cases_and_practice_are_distinct(self):
        resolved = with_checkpoints(self.data)
        bank_stems = {question["q"] for bank in self.data["quizzes"].values()
                      for question in bank}
        self.assertEqual([len(self.data["quizzes"][bank]) for bank in
                          ("basic", "advanced", "interview")], [31, 46, 26])
        for section in SECTIONS:
            for bank, count in (("basic", 2), ("advanced", 2), ("interview", 1)):
                self.assertGreaterEqual(sum(section in q["theoryRefs"]
                                            for q in self.data["quizzes"][bank]), count)
            checkpoint = [q for questions in resolved["checkpoints"].values()
                          for q in questions if section in q["theoryRefs"]]
            self.assertEqual(len(checkpoint), 1)
            self.assertNotIn(checkpoint[0]["q"], bank_stems)
            tasks = [task for task in self.data["tasks"] if section in task["theoryRefs"]]
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["level"], "Практика")
            self.assertTrue(tasks[0]["title"].startswith("Лаборатория: "))

    def test_downloads_and_fixed_conan_inputs(self):
        parser = Downloads()
        for section in SECTIONS:
            for block in self.sections[section]["blocks"]:
                parser.feed(block.get("html", ""))
        self.assertGreaterEqual(len(set(parser.paths)), 14)
        for relative in parser.paths:
            self.assertTrue((ROOT / relative).is_file(), relative)
        lock = load_json(SOURCE / "conan/conan.lock.json")
        self.assertEqual(len(lock["requires"]), 1)
        self.assertIn("#f63e7a05c4cce3f812333a73a3609d33%", lock["requires"][0])
        profile = (SOURCE / "conan/profiles/linux-gcc13.txt").read_text()
        self.assertIn("compiler.version=13", profile)
        self.assertIn("compiler.cppstd=20", profile)
        requirements = (SOURCE / "conan/requirements-conan.txt").read_text()
        self.assertIn("conan==2.22.2", requirements)
        consumer = (SOURCE / "conan/app/conanfile.py").read_text()
        self.assertIn("user_presets_path = False", consumer)
        self.assertFalse((SOURCE / "conan/app/CMakeUserPresets.json").exists())


def restricted_child():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def probe_gdb(work, build):
    if not shutil.which("gdb"):
        return {"status": "UNSUPPORTED", "reason": "GDB not installed"}
    core = work / "report.core"
    executable = build / "report_before"
    base = ["gdb", "-nx", "-q", "-batch", "-iex", "set auto-load off",
            "-iex", "set debuginfod enabled off"]
    result = call(base + ["-ex", "set confirm off", "-ex", "set disable-randomization off",
                         "-ex", "run", "-ex", f"generate-core-file {core}", "-ex", "kill",
                         "--args", executable, "empty"], preexec_fn=restricted_child)
    if not core.exists():
        message = result.stdout + result.stderr
        if "Operation not permitted" in message or "Could not trace" in message:
            return {"status": "UNSUPPORTED", "reason": "ptrace denied; core not created"}
        raise AssertionError("Core not created: " + message[-1500:])
    assert core.stat().st_size > 0 and core.stat().st_mode & 0o777 == 0o600
    checked(["readelf", "-n", executable])
    inspected = checked(base + [executable, core, "-ex", "bt", "-ex",
                               "frame function first_task", "-ex", "info locals", "-ex", "list"])
    assert "SIGABRT" in inspected.stdout and "first_task" in inspected.stdout
    assert "count = 0" in inspected.stdout and "tasks.at(0)" in inspected.stdout
    checked([build / "report_fixed", "--self-test"])
    return {"status": "PASS", "core_bytes": core.stat().st_size,
            "evidence": ["SIGABRT", "first_task", "count=0", "at(0)", "fixed regression exit0"]}


def probe_perf(work, build):
    if not shutil.which("perf"):
        return {"status": "UNSUPPORTED", "reason": "perf not installed"}
    results = []
    for mode in ("cpu", "wait"):
        result = call(["perf", "stat", "-r", "3", "-e", "task-clock,context-switches,page-faults",
                       "--", build / "perf_workload", mode, "40"])
        results.append(("stat_" + mode, result))
    data = work / "cpu.perf.data"
    result = call(["perf", "record", "-e", "cpu-clock:u", "-F", "99", "-g", "--call-graph", "fp",
                   "-o", data, "--", build / "perf_workload", "cpu", "100"])
    results.append(("record", result))
    denied = [name for name, r in results if r.returncode and any(
        word in r.stderr.lower() for word in ("permission", "limited", "not permitted", "not supported"))]
    if denied:
        return {"status": "UNSUPPORTED", "unverified": denied,
                "reason": "perf events denied/unsupported; not zero counters and not a verified profile"}
    for name, result in results:
        assert result.returncode == 0, (name, result.stderr[-1500:])
    assert data.is_file() and data.stat().st_size > 0
    report = checked(["perf", "report", "--stdio", "--no-children", "-n", "-i", data])
    if "mix" not in report.stdout:
        return {"status": "UNSUPPORTED", "reason": "No usable mix sample; profile insufficient, not PASS"}
    return {"status": "PASS", "evidence": ["stat cpu/wait", "record", "report contains mix samples"]}


def probe_conan(work, executable):
    if not executable:
        return {"status": "NOT_RUN", "reason": "Supply a verified Conan 2.22.2 via --conan; no automatic installation"}
    version = checked([executable, "--version"]).stdout.strip()
    assert version == "Conan version 2.22.2", version
    compiler = checked(["/usr/bin/g++", "-dumpfullversion"]).stdout.strip()
    assert compiler.split(".")[0] == "13", "Provided profile requires /usr/bin/g++ 13"
    source = SOURCE / "conan"
    profile = source / "profiles/linux-gcc13.txt"
    lock = source / "conan.lock.json"
    env = dict(os.environ, CONAN_HOME=str(work / "home"))
    checked([executable, "export", source / "library"], env=env)
    checked([executable, "install", source / "app", "--no-remote", "--build=missing",
             "-pr:h", profile, "-pr:b", profile, "--lockfile", lock, "-of", work / "deps"], env=env)
    for name in ("build-a", "build-b"):
        build = work / name
        checked(["cmake", "-S", source / "app", "-B", build, "-G", "Ninja",
                 f"-DCMAKE_TOOLCHAIN_FILE={work / 'deps/conan_toolchain.cmake'}", "-DCMAKE_BUILD_TYPE=Release"])
        checked(["cmake", "--build", build, "--parallel", "2"])
        checked(["ctest", "--test-dir", build, "--output-on-failure"])
        assert checked([build / "task_report"]).stdout == "task:41\n"
    # Only this new owned copy is changed; canonical sources stay untouched.
    changed = work / "changed-library"
    shutil.copytree(source / "library", changed)
    changed_source = changed / "src/task_label.cpp"
    changed_source.write_text(changed_source.read_text() + "\n// negative revision fixture\n")
    negative_env = dict(os.environ, CONAN_HOME=str(work / "negative-home"))
    checked([executable, "export", changed], env=negative_env)
    denied = call([executable, "install", source / "app", "--no-remote", "--build=missing",
                   "-pr:h", profile, "-pr:b", profile, "--lockfile", lock, "-of", work / "negative-deps"],
                  env=negative_env)
    listed = checked([executable, "list", "course-task-label/1.0#*", "--format=json"], env=negative_env)
    revisions = json.loads(listed.stdout)["Local Cache"]["course-task-label/1.0"]["revisions"]
    assert revisions and "f63e7a05c4cce3f812333a73a3609d33" not in revisions, revisions
    assert denied.returncode != 0, "Old locked revision was silently replaced"
    assert "course-task-label/1.0" in denied.stderr and "No remote defined" in denied.stderr, denied.stderr[-2000:]
    assert not (source / "app/CMakeUserPresets.json").exists()
    return {"status": "PASS", "version": version, "compiler": compiler,
            "evidence": ["no-remote locked recipe", "two clean consumer builds", "CTest + exact task:41",
                         "changed revision rejected in fresh cache"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--conan", help="Explicit path to an already installed, trusted Conan 2.22.2")
    args, remaining = parser.parse_known_args()
    suite = unittest.main(argv=[sys.argv[0], *remaining], exit=False)
    if not suite.result.wasSuccessful():
        raise SystemExit(1)
    if not args.integration:
        print("Real GDB/perf/Conan probes NOT RUN by this unittest invocation; use --integration.")
        raise SystemExit(0)
    with tempfile.TemporaryDirectory(prefix="course-tooling-probe-") as temporary:
        work = Path(temporary)
        build = build_native(work)
        report = {}
        for name, probe in (("gdb", lambda: probe_gdb(work, build)),
                            ("perf", lambda: probe_perf(work, build)),
                            ("conan", lambda: probe_conan(work, args.conan))):
            try:
                report[name] = probe()
            except (AssertionError, subprocess.TimeoutExpired, OSError) as error:
                report[name] = {"status": "FAIL", "reason": str(error)[-2000:]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        statuses = [result["status"] for result in report.values()]
        raise SystemExit(1 if "FAIL" in statuses else 0 if all(s == "PASS" for s in statuses) else 2)
