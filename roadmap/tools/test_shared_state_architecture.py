"""Check the shared-state lesson and its complete, deterministic C++20 example."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/station6/state_architecture.cpp"
CONTENT = ROOT / "content/station6.json"
EXPECTED = "old: v1 10/20\nnew: v2 30/40\nold retained: true\nold released: true\n"


class SharedStateArchitecture(unittest.TestCase):
    def compile_run(self, text, expected, compiler=None):
        compiler = compiler or shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            self.skipTest("A C++20 compiler is not installed")
        with tempfile.TemporaryDirectory(prefix="shared-state-example-") as tmp:
            binary = str(Path(tmp) / "example")
            compiled = subprocess.run(
                [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 "-pedantic", "-O2", "-pthread", "-x", "c++", "-", "-o", binary],
                input=text, capture_output=True, text=True, timeout=40)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected)

    def classes(self):
        return EXAMPLE.read_text().split("int main() {", 1)[0]

    def test_complete_example_on_available_compilers(self):
        compilers = [shutil.which(name) for name in ("g++", "clang++")]
        if not any(compilers):
            self.skipTest("A C++20 compiler is not installed")
        for compiler in filter(None, compilers):
            with self.subTest(compiler=compiler):
                self.compile_run(EXAMPLE.read_text(), EXPECTED, compiler)

    def test_invalid_update_preserves_published_version(self):
        self.compile_run(self.classes() + r'''
int main() {
    ConfigStore store;
    const auto before = store.read();
    int rejected = 0;
    try { store.increase_limits(-1); }
    catch (const std::invalid_argument&) { ++rejected; }
    try { store.increase_limits(std::numeric_limits<int>::max()); }
    catch (const std::overflow_error&) { ++rejected; }
    const auto after = store.read();
    if (rejected != 2 || before != after || after->version != 1 ||
        after->soft_limit != 10 || after->hard_limit != 20) return 1;
    std::cout << "rejected without publication\n";
}
''', "rejected without publication\n")

    def test_two_old_owners_and_two_successive_updates(self):
        self.compile_run(self.classes() + r'''
int main() {
    ConfigStore store;
    auto first = store.read();
    auto second = first;
    const std::weak_ptr<const Config> lifetime = first;
    store.increase_limits(1);
    store.increase_limits(1);
    const auto current = store.read();
    if (current->version != 3 || current->soft_limit != 12 ||
        current->hard_limit != 22 || first->version != 1) return 1;
    first.reset();
    if (lifetime.expired() || second->soft_limit != 10) return 2;
    second.reset();
    if (!lifetime.expired()) return 3;
    std::cout << "last old owner released\n";
}
''', "last old owner released\n")

    def test_two_writers_preserve_both_updates_and_reader_consistency(self):
        # A directed execution check, not proof that every scheduling is safe.
        self.compile_run(self.classes() + r'''
#include <thread>
int main() {
    ConfigStore store;
    std::atomic<int> finished{0};
    std::atomic<bool> bad{false};
    auto write = [&] {
        for (int i = 0; i != 500; ++i) store.increase_limits(1);
        finished.fetch_add(1);
    };
    {
        std::jthread first(write);
        std::jthread second(write);
        while (finished.load() != 2) {
            const auto view = store.read();
            if (view->hard_limit - view->soft_limit != 10 ||
                view->soft_limit != 9 + static_cast<int>(view->version))
                bad.store(true);
        }
    }
    const auto result = store.read();
    if (bad.load() || result->version != 1001 ||
        result->soft_limit != 1010 || result->hard_limit != 1020) return 1;
    std::cout << "both writers preserved\n";
}
''', "both writers preserved\n")

    def test_version_counter_cannot_wrap(self):
        classes = self.classes().replace(
            "Config{1, 10, 20}",
            "Config{std::numeric_limits<std::uint64_t>::max(), 10, 20}")
        self.assertNotEqual(classes, self.classes())
        self.compile_run(classes + r'''
int main() {
    ConfigStore store;
    const auto before = store.read();
    try { store.increase_limits(0); }
    catch (const std::overflow_error&) {
        if (store.read() != before) return 2;
        std::cout << "version overflow rejected\n";
        return 0;
    }
    return 1;
}
''', "version overflow rejected\n")

    def test_lesson_and_assessments_are_integrated(self):
        data = json.loads(CONTENT.read_text())
        sections = data["theory"]
        ids = [section["id"] for section in sections]
        section = sections[ids.index("shared-state-architecture")]
        self.assertEqual(section["substation"], "production-interview")
        self.assertEqual(ids[ids.index("snapshot-container-workbook") + 1], section["id"])
        route = data["readingOrder"]
        self.assertEqual(route[route.index("snapshot-container-workbook") + 1], section["id"])
        self.assertEqual(route[-1], "summary")
        codes = [block["code"].strip() for block in section["blocks"] if block["type"] == "code"]
        self.assertIn(EXAMPLE.read_text().strip(), codes)
        self.assertIn(EXPECTED.strip(), codes)
        for bank in ("basic", "interview"):
            questions = [q for q in data["quizzes"][bank]
                         if section["id"] in q.get("theoryRefs", [])]
            self.assertEqual(len(questions), 2, bank)
        labs = [task for task in data["tasks"]
                if section["id"] in task.get("theoryRefs", [])]
        self.assertEqual(len(labs), 1)
        self.assertEqual(labs[0]["level"], "Практика")
        self.assertTrue(labs[0]["title"].startswith("Лаборатория: "))


if __name__ == "__main__":
    unittest.main()
