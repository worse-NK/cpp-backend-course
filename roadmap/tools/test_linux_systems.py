"""Regression checks for the introductory Linux systems station (5Б).

Structure and arithmetic models run without Linux. The two complete, trusted
course examples are compiled only on Linux with g++, in a temporary directory.
They neither change system settings nor signal another existing process: the
signal example raises SIGTERM only in itself. No course shell command is run.

These checks protect examples, references, assessment coverage and explicit
scope boundaries; they cannot establish prose accuracy or replace review
against Linux man-pages, POSIX and kernel documentation.
"""

from collections import Counter
from fractions import Fraction
from html import unescape
from html.parser import HTMLParser
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from build_stations import load_json, validate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content/station5-linux.json"
EXAMPLES = ROOT / "examples/station5-linux"
GROUPS = (
    "os-boundary", "processes", "descriptors", "files-storage", "memory",
    "signals-limits",
)
FULL_EXAMPLES = {
    "linux-process-final-workbook": "pipe_capture.cpp",
    "linux-safe-signal-delivery": "signal_wait.cpp",
}
PRIMARY_HOSTS = {
    "man7.org", "docs.kernel.org", "kernel.org", "www.kernel.org",
    "isocpp.github.io", "www.freedesktop.org", "www.gnu.org", "gnu.org",
    "pubs.opengroup.org", "en.cppreference.com", "strace.io",
    "timsong-cpp.github.io",  # Versioned HTML of the openly available C++ draft.
}


def fields(value, name):
    """Yield one field recursively, including text inside visual blocks."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == name and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from fields(child, name)
    elif isinstance(value, list):
        for child in value:
            yield from fields(child, name)


class Fragment(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.links = []
        self.stack = []
        self.errors = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attributes):
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == "a":
            self.links.append(dict(attributes).get("href"))

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append((tag, tuple(self.stack)))
        else:
            self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def prose(value):
    return " ".join(" ".join(Fragment(html).text)
                    for html in fields(value, "html"))


def numeric_values(text):
    """Numbers in lesson answers; allow typographic thousands separators."""
    matches = re.findall(r"\d+(?:[ \u00a0\u202f]\d{3})*", unescape(text))
    return [int(re.sub(r"\s", "", value)) for value in matches]


class LinuxStationContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_json(SOURCE)
        cls.sections = {section["id"]: section for section in cls.data["theory"]}
        cls.questions = [question for bank in cls.data["quizzes"].values()
                         for question in bank]

    def test_station_schema_and_six_group_reading_route(self):
        validate(self.data, SOURCE)
        self.assertEqual(len(self.sections), 28)
        self.assertEqual(tuple(group["id"] for group in self.data["substations"]),
                         GROUPS)
        route = self.data.get("readingOrder", list(self.sections))
        positions = {group: index for index, group in enumerate(GROUPS)}
        actual = [positions[self.sections[sid]["substation"]] for sid in route]
        self.assertEqual(actual, sorted(actual), "Reading groups must not jump backwards")
        self.assertEqual(route[0], "learning-route")
        self.assertEqual(route[-1], "linux-process-final-workbook")
        for section in self.sections.values():
            with self.subTest(section=section["id"]):
                self.assertGreaterEqual(len(section["blocks"]), 8)

    def test_each_group_has_primary_sources_and_an_end_checkpoint(self):
        for index, group in enumerate(GROUPS, 1):
            with self.subTest(group=group):
                sections = [section for section in self.sections.values()
                            if section["substation"] == group]
                source_notes = [block for section in sections for block in section["blocks"]
                                if block["type"] == "note"
                                and "Первичные источники" in prose(block)]
                self.assertTrue(source_notes, "A group needs explicit source notes")
                urls = [link for block in source_notes
                        for html in fields(block, "html")
                        for link in Fragment(html).links]
                self.assertTrue(urls)
                for url in urls:
                    parts = urlsplit(url)
                    self.assertEqual(parts.scheme, "https", url)
                    self.assertIn(parts.hostname, PRIMARY_HOSTS, url)
                last = sections[-1]["blocks"][-1]
                self.assertEqual(last["type"], "note")
                self.assertEqual(last["kind"], "key")
                self.assertRegex(prose(last), rf"Контрольная\s+точка\s+5Б\.{index}\b")

    def test_balanced_prose_and_real_local_link_targets(self):
        stations = [load_json(path) for path in (ROOT / "content").glob("station*.json")]
        anchors = {data["meta"]["sourceFile"]: {s["id"] for s in data["theory"]}
                   for data in stations}
        for section in self.sections.values():
            for html in fields(section, "html"):
                with self.subTest(section=section["id"], fragment=html[:60]):
                    fragment = Fragment(html)
                    self.assertEqual(fragment.errors, [])
                    self.assertEqual(fragment.stack, [])
                    for link in fragment.links:
                        self.assertIsNotNone(link)
                        self.assertNotRegex(link, r"[\s\\\"<>]")
                        parts = urlsplit(link)
                        if parts.scheme or parts.netloc:
                            self.assertEqual(parts.scheme, "https", link)
                            continue
                        target = unquote(parts.path)
                        if target in anchors:
                            if parts.fragment.startswith("section="):
                                sid = unquote(parts.fragment.removeprefix("section="))
                                self.assertIn(sid, anchors[target], link)
                        elif not target:
                            if parts.fragment.startswith("section="):
                                self.assertIn(parts.fragment.removeprefix("section="),
                                              self.sections, link)
                        else:
                            path = (ROOT / target).resolve()
                            self.assertTrue(path.is_relative_to(ROOT.resolve()), link)
                            self.assertTrue(path.is_file(), link)

    def test_complete_embedded_programs_equal_downloadable_sources(self):
        for section_id, filename in FULL_EXAMPLES.items():
            with self.subTest(example=filename):
                source = (EXAMPLES / filename).read_text(encoding="utf-8")
                blocks = [block["code"] for block in self.sections[section_id]["blocks"]
                          if block["type"] == "code" and "int main(" in block["code"]]
                self.assertEqual(blocks, [source], "Complete code must not drift from its source")
        workbook_links = [link for html in fields(self.sections["linux-process-final-workbook"],
                                                  "html")
                          for link in Fragment(html).links]
        self.assertIn("examples/station5-linux/pipe_capture.cpp", workbook_links)

    def test_assessments_cover_every_group_and_teaching_section(self):
        self.assertGreaterEqual(len(self.questions), 50)
        for kind, bank in self.data["quizzes"].items():
            counts = Counter(question["substation"] for question in bank)
            with self.subTest(bank=kind):
                self.assertEqual(set(counts), set(GROUPS))
                self.assertTrue(all(count > 0 for count in counts.values()))
        covered = {ref for question in self.questions for ref in question["theoryRefs"]}
        covered.update(ref for task in self.data["tasks"] for ref in task["theoryRefs"])
        self.assertTrue(set(self.sections) - {"learning-route"} <= covered)
        tasks_by_group = Counter(task["substation"] for task in self.data["tasks"])
        self.assertEqual(set(tasks_by_group), set(GROUPS))
        for task in self.data["tasks"]:
            with self.subTest(task=task["title"]):
                self.assertGreaterEqual(len(task["checks"]), 3)
                self.assertTrue(task["hints"])
                self.assertTrue(task["solution"])
                self.assertNotIn("options", task)
                self.assertNotIn("answer", task)

    def test_scope_notes_distinguish_linux_user_space_and_kernel_work(self):
        # Editorial guardrails, not an automated proof that every claim is qualified.
        intro = prose(self.sections["learning-route"])
        self.assertIn("Linux", intro)
        self.assertRegex(intro, r"не.{0,100}(?:гарант|обещ)")
        self.assertIn("POSIX", intro)
        self.assertRegex(intro, r"user\s+space")
        self.assertRegex(intro, r"модул\w*\s+ядра")
        limits = prose(self.sections["linux-limits-isolation"])
        self.assertRegex(limits, r"контейнер.{0,150}не.{0,100}отдельн.{0,40}ядр")
        self.assertRegex(limits, r"виртуальн\w*\s+машин")

    def test_virtual_page_example_uses_division_and_remainder(self):
        codes = list(fields(self.sections["linux-address-space"], "code"))
        model = next(code for code in codes if "virtual address:" in code)
        address = re.search(r"virtual address:\s*(0x[0-9a-fA-F]+)\s*=\s*(\d+)", model)
        size = re.search(r"page size:\s*(\d+)", model)
        page = re.search(r"page number:[^\n]*=\s*(\d+)", model)
        offset = re.search(r"offset:[^\n]*=\s*(\d+)", model)
        self.assertTrue(all((address, size, page, offset)))
        value, decimal = int(address[1], 16), int(address[2])
        page_size = int(size[1])
        self.assertEqual((value, page_size), (0x3123, 4096))
        self.assertEqual(value, decimal)
        self.assertEqual(divmod(value, page_size), (int(page[1]), int(offset[1])))
        self.assertEqual((int(page[1]), int(offset[1])), (3, 0x123))

    def test_copy_on_write_model_does_not_double_count_shared_pages(self):
        # Identifiers represent physical pages, not Python objects measured as RAM.
        parent = list(range(500))
        child = parent.copy()
        for index in range(7):
            child[index] = 500 + index
        shared = set(parent) & set(child)
        unique_pages = len(set(parent) | set(child))
        sum_rss_pages = len(parent) + len(child)
        self.assertEqual((len(shared), unique_pages, sum_rss_pages), (493, 507, 1000))
        pss_kib = (Fraction(len(shared), 2) + len(parent) - len(shared)) * 4
        self.assertEqual(pss_kib, 1014)
        questions = [question for question in self.questions
                     if "linux-page-fault-metrics" in question["theoryRefs"]]
        count_question = next(question for question in questions
                              if "500" in question["q"] and "RSS" in question["q"]
                              and "уникаль" in question["q"])
        self.assertEqual(numeric_values(count_question["options"][count_question["answer"]]),
                         [unique_pages, sum_rss_pages])
        pss_question = next(question for question in questions
                            if "PSS" in question["q"] and "493" in question["q"])
        self.assertEqual(numeric_values(pss_question["options"][pss_question["answer"]]),
                         [int(pss_kib)])

    def test_umask_example_is_bit_clearing_not_subtraction(self):
        question = next(question for question in self.questions
                        if "umask" in question["q"] and "0666" in question["q"])
        inputs = re.findall(r"\b0[0-7]{3}\b", question["q"])
        self.assertEqual(inputs, ["0666", "0027"])
        requested, mask = map(lambda value: int(value, 8), inputs)
        expected = requested & ~mask
        self.assertEqual(expected, 0o640)
        answer = question["options"][question["answer"]]
        self.assertEqual(re.findall(r"\b0[0-7]{3}\b", answer), [f"{expected:04o}"])
        self.assertNotEqual(expected, requested - mask)

    def test_pipe_checksum_model_matches_the_actual_writer(self):
        source = (EXAMPLES / "pipe_capture.cpp").read_text(encoding="utf-8")
        row = re.search(r'constexpr\s+char\s+row\[\]\s*=\s*"([^"\n]+)";', source)
        count = re.search(r"const\s+int\s+count\s*=\s*empty\s*\?\s*0\s*:\s*(\d+)", source)
        self.assertIsNotNone(row)
        self.assertIsNotNone(count)
        # The deliberately simple example literal uses ASCII and one \n escape.
        payload = row[1].encode("ascii").decode("unicode_escape").encode("ascii")
        copies = int(count[1])
        self.assertEqual((len(payload), sum(payload), copies), (6, 345, 40000))
        self.assertEqual((len(payload) * copies, sum(payload) * copies),
                         (240000, 13800000))

    def test_publication_sketch_opens_a_writable_private_temporary_file(self):
        # O_CREAT alone does not select writing: O_RDONLY has value zero.
        # The lesson is a protocol sketch, not a filesystem durability experiment.
        sketch = next(code for code in fields(self.sections["linux-file-durability"], "code")
                      if "O_CREAT" in code and "O_EXCL" in code)
        self.assertRegex(sketch, r"O_(?:WRONLY|RDWR)")
        self.assertIn("0600", sketch)


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("g++"),
                     "Complete POSIX/Linux examples require Linux and g++")
class LinuxExamplePrograms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="course-linux-systems-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binaries = {}
        for profile, flags in (("debug", ["-O0", "-g"]),
                               ("release", ["-O2", "-DNDEBUG"])):
            for name in ("pipe_capture", "signal_wait"):
                binary = Path(cls.directory.name) / f"{name}-{profile}"
                command = ["g++", "-std=c++20", "-Wall", "-Wextra", "-Wpedantic",
                           "-Werror", *flags, str(EXAMPLES / f"{name}.cpp"),
                           "-o", str(binary)]
                result = subprocess.run(command, text=True, capture_output=True, timeout=30)
                if result.returncode:
                    raise AssertionError(f"Compilation failed: {command}\n{result.stderr}")
                cls.binaries[profile, name] = binary

    def run_example(self, profile, name, *arguments):
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        return subprocess.run([str(self.binaries[profile, name]), *arguments],
                              stdin=subprocess.DEVNULL, text=True, capture_output=True,
                              timeout=10, env=environment, restore_signals=True)

    def test_mmap_fragment_is_valid_cpp_with_checked_inputs(self):
        data = load_json(SOURCE)
        section = next(s for s in data["theory"] if s["id"] == "linux-mmap-sharing")
        fragment = next(code for code in fields(section, "code") if "::mmap(" in code)
        # Supply only the inputs/headers documented in the caption. Syntax only:
        # no mapping, file access or memory-pressure experiment is performed.
        source = ("#include <sys/mman.h>\n#include <cstddef>\n#include <cerrno>\n"
                  "#include <system_error>\nvoid example(int fd, std::size_t length) {\n"
                  + fragment + "\n(void)bytes;\n}\n")
        result = subprocess.run(
            ["g++", "-std=c++20", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
             "-fsyntax-only", "-x", "c++", "-"],
            input=source, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("const int error = errno;", fragment)
        self.assertIn("static_cast<const unsigned char*>", fragment)

    def test_capture_normal_output_and_child_success(self):
        for profile in ("debug", "release"):
            with self.subTest(profile=profile):
                result = self.run_example(profile, "pipe_capture")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 "bytes=240000 checksum=13800000\nchild_exit=0\n")
                self.assertEqual(result.stderr, "")

    def test_empty_output_can_be_a_success(self):
        for profile in ("debug", "release"):
            with self.subTest(profile=profile):
                result = self.run_example(profile, "pipe_capture", "--empty")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "bytes=0 checksum=0\nchild_exit=0\n")
                self.assertEqual(result.stderr, "")

    def test_complete_output_does_not_hide_child_failure(self):
        for profile in ("debug", "release"):
            with self.subTest(profile=profile):
                result = self.run_example(profile, "pipe_capture", "--fail")
                self.assertEqual(result.stdout,
                                 "bytes=240000 checksum=13800000\nchild_exit=7\n")
                self.assertEqual(result.returncode, 2)
                self.assertNotEqual(result.returncode, 7,
                                    "Parent reports its own contract, not the child's code")
                self.assertEqual(result.stderr, "")

    @unittest.skipUnless(platform.libc_ver()[0] == "glibc",
                         "Direct missing-executable error is the checked glibc behavior")
    def test_missing_executable_is_a_launch_error_on_glibc(self):
        for profile in ("debug", "release"):
            with self.subTest(profile=profile):
                result = self.run_example(profile, "pipe_capture", "--missing")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("posix_spawn", result.stderr)

    def test_unknown_flags_and_extra_arguments_are_rejected(self):
        for profile in ("debug", "release"):
            for arguments in (("--does-not-exist",), ("--empty", "extra")):
                with self.subTest(profile=profile, arguments=arguments):
                    result = self.run_example(profile, "pipe_capture", *arguments)
                    self.assertEqual(result.returncode, 64)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "")

    def test_signal_is_self_sent_and_consumed_in_normal_code(self):
        source = (EXAMPLES / "signal_wait.cpp").read_text(encoding="utf-8")
        self.assertRegex(source, r"::raise\(\s*SIGTERM\s*\)")
        self.assertNotRegex(source, r"::(?:kill|killpg|tgkill)\s*\(")
        for profile in ("debug", "release"):
            with self.subTest(profile=profile):
                result = self.run_example(profile, "signal_wait")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 "received SIGTERM\ncleanup in normal code\n")
                self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
