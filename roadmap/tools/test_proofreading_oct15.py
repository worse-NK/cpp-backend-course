"""Regressions for manually proofread course examples."""
import json
import sqlite3
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Proofreading(unittest.TestCase):
    def test_count_includes_zero_but_not_null(self):
        with sqlite3.connect(":memory:") as db:
            result = db.execute("WITH sample(v) AS (VALUES (0),(5),(NULL)) "
                                "SELECT count(*), count(v) FROM sample").fetchone()
            self.assertEqual(result, (3, 2))

    def test_window_frame_keeps_rows_and_counts_prefix(self):
        with sqlite3.connect(":memory:") as db:
            rows = db.execute("WITH tasks(id,owner_id) AS (VALUES (10,1),(11,1)) "
                              "SELECT id, count(*) OVER (PARTITION BY owner_id "
                              "ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING "
                              "AND CURRENT ROW) FROM tasks ORDER BY id").fetchall()
            self.assertEqual(rows, [(10, 1), (11, 2)])

    def test_closed_collector_does_not_start_pending_command_before_stop(self):
        data = json.loads((ROOT / "content/station6.json").read_text())
        source = next(t["solution"] for t in data["tasks"]
                      if "class PeriodicCollector" in t.get("solution", ""))
        # Reproduce the state between accepting_=false and request_stop(),
        # without relying on a probabilistic thread schedule.
        source = source.replace(
            ': worker_([this](std::stop_token st) { run(st); }) {}',
            ': worker_() {}')
        source = source.replace('public:', '''public:
    void test_closed_state() {
        commands_.emplace_back();
        accepting_ = false;
        run(std::stop_token{});
    }
''')
        self.run_cpp('''
#include <thread>
#include <mutex>
#include <condition_variable>
#include <deque>
#include <iostream>
struct Command {};
int executed = 0;
void execute(Command&, std::stop_token) { ++executed; throw 1; }
void record_worker_failure_noexcept() noexcept {}
''' + source + '''
int main() {
    PeriodicCollector collector;
    collector.test_closed_state();
    std::cout << executed;
}
''', "0")

    def test_stream_badbit_mask_preserves_input_exception(self):
        self.run_cpp("""
#include <iostream>
#include <istream>
#include <new>
#include <streambuf>
struct FailingBuffer : std::streambuf {
    int_type underflow() override { throw std::bad_alloc{}; }
};
int main() {
    FailingBuffer first, second;
    std::istream silent(&first), propagating(&second);
    int value = 0;
    silent >> value;
    std::cout << silent.bad() << ' ';
    propagating.exceptions(std::ios::badbit);
    try { propagating >> value; }
    catch (const std::bad_alloc&) { std::cout << "bad_alloc"; }
}
""", "1 bad_alloc")

    def test_vector_bool_proxy_is_not_a_snapshot(self):
        data = json.loads((ROOT / "content/station3.json").read_text())
        section = next(s for s in data["theory"] if s["id"] == "vector")
        source = next(b["code"] for b in section["blocks"]
                      if b.get("caption") == "auto может сохранить посредник, а не независимое значение")
        self.run_cpp(source, "1 0")

    def test_unsigned_intermediate_and_final_result_are_different_contracts(self):
        self.run_cpp("""
#include <iostream>
#include <limits>
int main() {
    unsigned long long value = std::numeric_limits<unsigned long long>::max();
    value *= 2ULL; // математическое произведение не представимо
    value *= 0ULL;
    value += 7ULL;
    std::cout << value;
}
""", "7")

    def station2_code(self, section_id, caption):
        data = json.loads((ROOT / "content/station2.json").read_text())
        section = next(s for s in data["theory"] if s["id"] == section_id)
        return next(b["code"] for b in section["blocks"]
                    if b.get("caption") == caption)

    def test_pure_virtual_destructor_definition(self):
        self.run_cpp(self.station2_code(
            "virtual-dtor", "Чисто виртуальный деструктор с определением"), "DB")

    def test_protected_object_restriction(self):
        source = self.station2_code(
            "protected", "protected не открывает поле любого объекта базы")
        self.run_cpp(source, "")
        invalid = source.replace("// base.value = 3;", "base.value = 3;")
        self.assertNotEqual(invalid, source)
        compiled = subprocess.run(
            ["g++", "-std=c++20", "-x", "c++", "-", "-fsyntax-only"],
            input=invalid, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(compiled.returncode, 0)
        self.assertIn("protected", compiled.stderr)

    def run_cpp(self, source, expected):
        with tempfile.TemporaryDirectory(prefix="proofreading-") as tmp:
            binary = str(Path(tmp) / "check")
            compiled = subprocess.run(
                ["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic",
                 "-x", "c++", "-", "-o", binary], input=source,
                text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([binary], text=True, capture_output=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, expected)

    def test_complete_member_order_question(self):
        data = json.loads((ROOT / "content/station0.json").read_text())
        question = data["quizzes"]["advanced"][10]
        source = question["q"].split("\n\n", 1)[1]
        self.run_cpp(source, question["options"][question["answer"]])

    def test_null_alias_can_retain_ownership_after_lock(self):
        self.run_cpp("""
#include <iostream>
#include <memory>
int main() {
    auto owner = std::make_shared<int>(42);
    std::shared_ptr<int> alias(owner, nullptr);
    std::weak_ptr<int> weak = alias;
    auto held = weak.lock();
    owner.reset();
    alias.reset();
    std::cout << bool(held) << ' ' << held.use_count() << ' ' << weak.expired();
}
""", "0 1 0")

    def test_explicit_this_capture_is_not_object_copy(self):
        self.run_cpp("""
#include <iostream>
struct Item {
    int value = 1;
    auto observe() { return [this] { return value; }; }
    auto snapshot() { return [*this] { return value; }; }
};
int main() {
    Item item;
    auto observe = item.observe();
    auto snapshot = item.snapshot();
    item.value = 7;
    std::cout << observe() << ' ' << snapshot();
}
""", "7 1")


if __name__ == "__main__":
    unittest.main()
