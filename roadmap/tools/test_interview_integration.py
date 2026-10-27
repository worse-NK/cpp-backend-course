#!/usr/bin/env python3
"""Regressions for the interview-bank integration (C++20 unless noted).

Compile chapter examples, reject specified invalid variants, and check small
algorithm/OS models. This is not a load test, a benchmark, or a proof of prose.
"""
import os
import unittest
from collections import OrderedDict

from test_expanded_examples import code, station
import test_remaining_examples


class InterviewIntegration(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_complete_chapter_programs(self):
        cases = [
            (1, "storage-and-construction", 0, "C 7 D"),
            (1, "shared-aliasing", 0, "42 1"),
            (3, "constant-evaluation", 0, "8 10 7"),
            (3, "constant-evaluation", 1, "7 7"),
            (3, "sfinae-and-constraints", 0, "3 0"),
            (3, "sfinae-and-constraints", 1, "count range"),
            (3, "callables-and-invoke", 0, "14"),
            (3, "interview-algorithm-invariants", 0, "5 3\n3 4 5"),
            (4, "exception-cost-and-array", 0, "C0 C1 C2 D1 D0 caught 3"),
        ]
        for n, key, index, output in cases:
            with self.subTest(station=n, section=key, index=index):
                self.cpp(code(n, key, index), output, flags=("-Werror=multichar",))

    def test_constant_evaluation_failures(self):
        source = code(3, "constant-evaluation")
        self.cpp(source.replace("fixed(5)", "fixed(counter)"), valid=False)
        self.cpp(source.replace("constinit int counter", "constinit const int counter"), valid=False)
        branch = code(3, "constant-evaluation", 1)
        self.cpp(branch.replace("if constexpr", "if"), valid=False)

    def test_substitution_vs_body_and_overload(self):
        source = code(3, "sfinae-and-constraints")
        self.cpp(source.replace("decltype(x.size(), std::size_t{})", "std::size_t"), valid=False)
        constructors = code(3, "sfinae-and-constraints", 1)
        self.cpp(constructors.replace("template<std::input_iterator It>", "template<class It>"),
                 "rangerange")

    def test_aliasing_empty_owner(self):
        self.cpp(r'''
#include <iostream>
#include <memory>
int main() {
    int value = 7;
    std::shared_ptr<int> p(std::shared_ptr<int>{}, &value);
    std::cout << bool(p) << ' ' << p.use_count() << ' ' << *p;
}
''', "1 0 7")

    def test_array_new_failure_cleanup(self):
        source = code(4, "exception-cost-and-array")
        self.cpp(source.replace("X values[4];", "auto p = new X[4]; delete[] p;"),
                 "C0 C1 C2 D1 D0 caught 3")

    def test_move_only_callable_rejected(self):
        self.cpp(r'''
#include <functional>
#include <memory>
int main() {
    auto f = [p = std::make_unique<int>(7)]() { return *p; };
    std::function<int()> wrapped = std::move(f);
}
''', valid=False)

    def test_every_nth_contract(self):
        source = code(6, "concurrent-interview-components")
        self.cpp(source + r'''
#include <iostream>
int main() {
    EveryNth n(3);
    for (int i = 0; i != 6; ++i) std::cout << n.select();
    try { EveryNth invalid(0); }
    catch (const std::invalid_argument&) { std::cout << " rejected"; }
}
''', "001001 rejected", flags=("-pthread",))
        self.cpp(source + r'''
#include <atomic>
#include <iostream>
#include <thread>
#include <vector>
int main() {
    EveryNth n(3);
    std::atomic<int> selected{0};
    {
        std::vector<std::jthread> workers;
        for (int t = 0; t != 4; ++t)
            workers.emplace_back([&] {
                for (int i = 0; i != 150; ++i)
                    if (n.select()) selected.fetch_add(1, std::memory_order_relaxed);
            });
    }
    std::cout << selected.load();
}
''', "200", flags=("-pthread",))

    def test_spin_mutex_small_contention(self):
        # A smoke test, not a proof of fairness or lock-free progress.
        self.cpp(code(6, "spinlock-futex") + r'''
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
int main() {
    SpinMutex mutex;
    int total = 0;
    {
        std::vector<std::jthread> workers;
        for (int t = 0; t != 3; ++t)
            workers.emplace_back([&] {
                for (int i = 0; i != 1000; ++i) {
                    std::lock_guard lock(mutex);
                    ++total;
                }
            });
    }
    std::cout << total;
}
''', "3000", flags=("-pthread",))

    def test_layout_model_not_universal_abi(self):
        def layout(fields, alignment):
            offset, positions = 0, []
            for size, align in fields:
                offset = (offset + align - 1) // align * align
                positions.append(offset)
                offset += size
            return positions, (offset + alignment - 1) // alignment * alignment
        self.assertEqual(layout([(1, 1), (4, 4), (1, 1)], 4), ([0, 4, 8], 12))
        self.assertEqual(layout([(4, 4), (1, 1), (1, 1)], 4), ([0, 4, 5], 8))
        self.cpp("struct Empty {}; static_assert(sizeof(Empty)>0); int main(){}", "")

    def test_container_contracts(self):
        self.cpp(r'''
#include <deque>
#include <vector>
#include <iostream>
int main() {
    std::deque<int> d{7};
    int& ref = d.front();
    d.push_back(8);
    std::vector<int> v(20);
    auto capacity = v.capacity();
    v.clear(); v.reserve(0);
    std::cout << ref << ' ' << v.empty() << ' ' << (v.capacity() == capacity);
}
''', "7 1 1")

    def test_lru_and_window_models(self):
        cache = OrderedDict()
        for key in "AB":
            cache[key] = key
        cache.move_to_end("A")
        cache["C"] = "C"
        cache.popitem(last=False)
        self.assertEqual(list(reversed(cache)), ["C", "A"])
        self.assertEqual(sum(400 - 300 < t <= 400 for t in (100, 101, 399)), 2)
        values = [2, 4, 8, 10]
        self.assertEqual([sum(values[max(0, i - 2):i + 1]) for i in range(4)],
                         [2, 6, 14, 22])
        a, index = [1, 4, 6, 8, 11], 2
        candidates = [v for i, v in enumerate(a) if i != index]
        self.assertEqual(sorted(candidates, key=lambda v: (abs(v - a[index]), -v))[:3],
                         [8, 4, 11])

    @unittest.skipUnless(os.name == "posix", "POSIX pipe required")
    def test_pipe_duplicate_writer_delays_eof(self):
        reader, writer = os.pipe()
        duplicate = os.dup(writer)
        try:
            os.set_blocking(reader, False)
            os.close(writer)
            writer = -1
            with self.assertRaises(BlockingIOError):
                os.read(reader, 1)
            os.close(duplicate)
            duplicate = -1
            self.assertEqual(os.read(reader, 1), b"")
        finally:
            for fd in (reader, writer, duplicate):
                if fd >= 0:
                    os.close(fd)

    def test_new_topics_have_questions_and_sources(self):
        keys = {
            0: ["object-layout"],
            1: ["storage-and-construction", "shared-aliasing"],
            2: ["wrappers-and-patterns"],
            3: ["constant-evaluation", "sfinae-and-constraints", "callables-and-invoke",
                "sequence-container-topology", "lru-window-generations",
                "interview-algorithm-invariants", "interview-sequence-workbook"],
            4: ["exception-cost-and-array"],
            5: ["linux-processes-memory", "signals-and-shutdown", "ipc-pipes-shared-memory",
                "ci-cross-build-tests", "profiling-evidence"],
            6: ["spinlock-futex", "concurrent-interview-components", "hardware-cost-reasoning"],
            7: ["fibers-coroutines-threads", "udp-rtp-reliability", "http-cookies"],
        }
        for n, ids in keys.items():
            data = station(n)
            for key in ids:
                with self.subTest(station=n, section=key):
                    section = next(s for s in data["theory"] if s["id"] == key)
                    self.assertTrue(any("href=" in b.get("html", "") for b in section["blocks"]))
                    self.assertTrue(any(key in q["theoryRefs"] for q in data["quizzes"]["advanced"]))


if __name__ == "__main__":
    unittest.main()
