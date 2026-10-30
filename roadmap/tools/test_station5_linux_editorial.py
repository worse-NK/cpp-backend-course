"""Regressions for the explanatory Linux pass, not a proof of OS portability.

Only the two short, trusted programs added by this pass are executed here.
They print argv or start /bin/true; they do not change host settings, inspect
another user's process, capture traffic, or generate load. Larger existing
examples are covered by test_linux_systems and test_memory_loader_deepening.
"""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

from build_stations import validate
from test_linux_systems import Fragment

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content/station5-linux.json"


class LinuxEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}
        cls.compiler = shutil.which("g++")

    def html(self, sid):
        return " ".join(b.get("html", "") + " " + b.get("answer", "")
                        for b in self.sections[sid]["blocks"])

    def program(self, sid, marker):
        values = [b["code"] for b in self.sections[sid]["blocks"]
                  if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(values), 1)
        return values[0]

    def compile_and_run(self, source, args=(), name="example"):
        if platform.system() != "Linux" or not self.compiler:
            self.skipTest("This program targets Linux and needs g++")
        with tempfile.TemporaryDirectory(prefix="course-linux-editorial-") as folder:
            executable = Path(folder) / name
            built = subprocess.run(
                [self.compiler, "-std=c++20", "-Wall", "-Wextra", "-Wpedantic",
                 "-Werror", "-x", "c++", "-", "-o", str(executable)],
                input=source, text=True, capture_output=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            return subprocess.run(["./" + name, *args], cwd=folder,
                                  text=True, capture_output=True, timeout=5)

    def test_schema_and_stable_progress_identity(self):
        validate(self.data, SOURCE)
        self.assertEqual(self.data["meta"]["storeKey"],
                         "cpp_station5_linux_progress_v1")
        self.assertEqual(len(self.sections), 28)
        self.assertEqual([len(v) for v in self.data["quizzes"].values()],
                         [22, 12, 24])

    def test_every_section_has_an_answer_bearing_self_check(self):
        count = 0
        for sid, section in self.sections.items():
            checks = [b for b in section["blocks"] if b["type"] == "self-check"]
            self.assertTrue(checks, sid)
            count += len(checks)
            for check in checks:
                with self.subTest(section=sid):
                    self.assertTrue(check["prompt"].strip())
                    self.assertTrue(check["answer"].strip())
                    for field in ("prompt", "answer"):
                        fragment = Fragment(check[field])
                        self.assertEqual(fragment.errors, [])
                        self.assertEqual(fragment.stack, [])
        self.assertGreaterEqual(count, 42)

    def test_argv_example_preserves_argument_boundaries(self):
        source = self.program("linux-launch-environment", "int main(int argc")
        run = self.compile_and_run(source, ["--format", "json", "daily report.txt"],
                                   "report")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout,
                         "argc = 4\n0: [./report]\n1: [--format]\n"
                         "2: [json]\n3: [daily report.txt]\n")

    def test_spawn_example_collects_status_instead_of_treating_pid_as_exit(self):
        if not Path("/bin/true").is_file():
            self.skipTest("/bin/true is not installed")
        source = self.program("linux-fork-exec-wait", "char* environment[]")
        self.assertIn("std::strerror(error)", source)
        self.assertIn("WIFEXITED(status)", source)
        run = self.compile_and_run(source)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "exit = 0\n")

    def test_blocking_and_failed_execution_are_different_events(self):
        html = self.html("linux-process-supervision")
        for term in ("процесс", "готов", "Type=exec", "Type=notify", "127"):
            self.assertIn(term, html)
        self.assertIn("/man/256/systemd.service.html", html)

    def test_close_warning_distinguishes_linux_and_posix_2024(self):
        html = self.html("linux-error-and-interruption")
        for term in ("Linux", "POSIX.1-2024", "EINTR", "EINPROGRESS"):
            self.assertIn(term, html)
        self.assertIn("pubs.opengroup.org/onlinepubs/9799919799/functions/close.html", html)

    def test_durability_sources_are_versioned_and_separate_flush_from_fsync(self):
        html = self.html("linux-file-durability")
        self.assertIn("/6.6/admin-guide/mm/concepts.html#page-cache", html)
        self.assertIn("/n4861/ostream.unformatted#7", html)
        self.assertNotIn("/latest/", html)

    def test_overcommit_link_uses_actual_66_document_location(self):
        html = self.html("linux-memory-pressure")
        self.assertIn("/6.6/mm/overcommit-accounting.html", html)
        self.assertNotIn("admin-guide/mm/overcommit-accounting", html)
        self.assertIn("memory.high", html)
        self.assertIn("memory.max", html)

    def test_page_arithmetic_and_shared_memory_cost_are_explicit_models(self):
        address, size = 8197, 4096
        self.assertEqual(divmod(address, size), (2, 5))
        self.assertEqual(493 + 7 + 7, 507)
        self.assertEqual(493 * 4 / 2 + 7 * 4, 1014)
        self.assertIn("модел", self.html("linux-page-fault-metrics").lower())
        self.assertIn("TLB", self.html("linux-address-space"))

    def test_five_questions_each_without_future_thread_join(self):
        data = json.loads((ROOT / "content/checkpoints/station5-linux.json").read_text())
        self.assertEqual(len(data["modules"]), 6)
        for questions in data["modules"].values():
            self.assertEqual(len(questions), 5)
            for question in questions:
                self.assertNotIn("join", question.get("q", ""))

    def test_revised_assessments_use_distinct_applications(self):
        advanced = self.data["quizzes"]["advanced"][5]
        interview = self.data["quizzes"]["interview"][18]
        self.assertIn("FD_CLOEXEC", advanced["why"])
        self.assertIn("ещё выполняет расчёт", interview["q"])
        self.assertIn("waitpid", interview["options"][interview["answer"]])
        self.assertIn("а не завершение всей программы", interview["why"])

    def test_no_privilege_or_settings_change_in_new_short_programs(self):
        for sid, marker in (("linux-launch-environment", "int main(int argc"),
                            ("linux-fork-exec-wait", "char* environment[]")):
            source = self.program(sid, marker)
            for operation in ("::kill(", "::setrlimit(", "::mount(",
                              "::setuid(", "::system(", "::popen("):
                self.assertNotIn(operation, source)


if __name__ == "__main__":
    unittest.main()
