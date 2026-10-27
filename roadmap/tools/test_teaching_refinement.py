#!/usr/bin/env python3
"""Check the refined examples and small, explicit state models.

The scheduling models do not prove a production cache/logger implementation.
POSIX checks use real descriptors; no network service or user data is touched.
"""
from collections import deque
import itertools
import os
import subprocess
import sys
import unittest

from test_expanded_examples import code, station
import test_remaining_examples


class TeachingRefinement(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_concept_program_and_rejected_result_type(self):
        source = code(3, 'sfinae-and-constraints', 2)
        self.cpp(source, '3 0')
        variant = source.replace('int main()',
            'struct Bad { std::string size() const { return "bad"; } };\nint main()')
        self.cpp(variant.replace('length(5)', 'length(Bad{})'), '3 0')

    def test_decltype_does_not_call_size(self):
        source = code(3, 'sfinae-and-constraints', 0)
        source = source[:source.index('int main()')] + r'''
int calls = 0;
struct Probe { std::size_t size() const { ++calls; return 4; } };
int main() {
    Probe p;
    auto size = length(p);
    std::cout << size << ' ' << calls;
}
'''
        self.cpp(source, '4 1')

    def test_compaction_invariant_all_small_inputs(self):
        for n in range(6):
            for values in itertools.product((0, 1, 2), repeat=n):
                a, write = list(values), 0
                for read in range(n):
                    self.assertEqual(a[:write], [x for x in values[:read] if x])
                    self.assertLessEqual(write, read)
                    if a[read]:
                        a[write] = a[read]
                        write += 1
                self.assertEqual(a[:write], [x for x in values if x])

    def test_two_sum_and_unique_window_counterexamples(self):
        def two_sum(values, target, insert_first=False):
            seen = {}
            for i, x in enumerate(values):
                if insert_first:
                    seen[x] = i
                if target-x in seen:
                    return seen[target-x], i
                seen[x] = i
        self.assertIsNone(two_sum([3], 6))
        self.assertEqual(two_sum([3, 3], 6), (0, 1))
        self.assertEqual(two_sum([3], 6, True), (0, 0))  # Deliberate bad variant.
        left, seen, windows = 0, {}, []
        for i, c in enumerate('abba'):
            if c in seen:
                left = max(left, seen[c]+1)
            seen[c] = i
            windows.append('abba'[left:i+1])
        self.assertEqual(windows, ['a', 'ab', 'b', 'ba'])

    def test_sliding_sums_and_time_boundary(self):
        for size in (1, 2, 3, 4):
            window, total = deque(), 0
            values = [2, 4, 8, 10]
            for i, value in enumerate(values):
                if len(window) == size:
                    total -= window.popleft()
                window.append(value)
                total += value
                self.assertEqual(total, sum(values[max(0,i-size+1):i+1]))
        stamps = (100, 101, 399)
        self.assertEqual(sum(100 < t <= 400 for t in stamps), 2)
        self.assertEqual(sum(100 <= t <= 400 for t in stamps), 3)

    def test_generation_model_and_wrap_counterexample(self):
        generation, common = 1, 0
        cells = {}
        def get(index):
            value, tag = cells.get(index, (0, 0))
            return value if tag == generation else common
        cells[1] = (7, generation)
        self.assertEqual(get(1), 7)
        generation, common = 2, 5
        cells[2] = (9, generation)
        self.assertEqual((get(1), get(2)), (5, 9))
        generation, common = 3, 4
        self.assertEqual((get(1), get(2)), (4, 4))
        generation, common = 1, 10  # Incorrectly reused generation.
        self.assertEqual(get(1), 7)  # Stale value reappears, not the desired 10.

    def test_pool_reservation_rollback(self):
        free, live = [2, 1, 0], set()
        first = free.pop()
        live.add(first)
        reserved = free.pop()
        free.append(reserved)  # Constructor failed: no live object to destroy.
        self.assertEqual((free, live), ([2, 1], {0}))
        live.remove(first)
        free.append(first)
        self.assertEqual((free, live), ([2, 1, 0], set()))

    @unittest.skipUnless(os.name == 'posix', 'POSIX descriptors required')
    def test_pipe_data_before_eof(self):
        reader, writer = os.pipe()
        try:
            os.set_blocking(reader, False)
            with self.assertRaises(BlockingIOError):
                os.read(reader, 10)
            os.write(writer, b'OK')
            os.close(writer)
            writer = -1
            self.assertEqual(os.read(reader, 10), b'OK')
            self.assertEqual(os.read(reader, 10), b'')
        finally:
            os.close(reader)
            if writer >= 0:
                os.close(writer)

    @unittest.skipUnless(hasattr(os, 'fork'), 'fork required')
    def test_fork_shared_offset_vs_independent_open(self):
        # Bounded subprocess: inherited file offset and private variable differ.
        source = r'''
import os, tempfile
with tempfile.TemporaryFile() as f:
    f.write(b'ABCD'); f.flush(); os.lseek(f.fileno(),0,0)
    gate_r, gate_w = os.pipe()
    count = 7
    pid = os.fork()
    if pid == 0:
        os.close(gate_w)
        os.read(gate_r,1)
        count = 9
        data = os.read(f.fileno(),2)
        os._exit(0 if data == b'CD' and count == 9 else 1)
    os.close(gate_r)
    assert os.read(f.fileno(),2) == b'AB'
    os.write(gate_w,b'x'); os.close(gate_w)
    _, status = os.waitpid(pid,0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert count == 7
with tempfile.NamedTemporaryFile() as f:
    f.write(b'ABCD'); f.flush()
    a=os.open(f.name,os.O_RDONLY); b=os.open(f.name,os.O_RDONLY)
    try:
        assert os.read(a,2)==b'AB'
        assert os.read(b,2)==b'AB'
    finally:
        os.close(a); os.close(b)
print('ok')
'''
        result = subprocess.run([sys.executable, '-c', source],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ok')

    def test_cache_schedules_distinguish_insertion_and_computation(self):
        # Model explicit interleavings, not a claim about arbitrary thread runs.
        table, calls = {}, []
        self.assertNotIn('K', table)  # A checks and unlocks.
        self.assertNotIn('K', table)  # B checks and unlocks.
        for actor in ('A', 'B'):
            calls.append(actor)
            table.setdefault('K', actor)  # Recheck + insert under common lock.
        self.assertEqual((len(table), len(calls)), (1, 2))
        pending, creators = {}, []
        for actor in ('A', 'B'):
            if 'K' not in pending:  # Atomic model step under common lock.
                pending['K'] = {'state': 'inflight', 'owner': actor}
                creators.append(actor)
        self.assertEqual(creators, ['A'])
        pending['K']['state'] = 'error'
        self.assertEqual(pending['K']['owner'], 'A')

    def test_logger_excerpt_drains_and_observes_failure(self):
        loop = code(6, 'async-logger-workbook')
        source = r'''
#include <condition_variable>
#include <deque>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
struct Sink {
    std::string seen;
    void write(const std::string& s) {
        if (s == "B") throw std::runtime_error("write failed");
        seen += s;
    }
};
struct LoggerModel {
    std::mutex mutex;
    std::condition_variable ready;
    std::deque<std::string> queue;
    bool closed = false;
    Sink sink;
    int failures = 0;
    void record_failure_noexcept() noexcept { ++failures; }
    void run() {
''' + loop + r'''
    }
};
int main() {
    LoggerModel model;
    model.queue = {"A", "B", "C"};
    model.closed = true;
    std::thread worker([&]{model.run();});
    worker.join();
    std::cout << model.sink.seen << ' ' << model.failures << ' ' << model.queue.empty();
}
'''
        self.cpp(source, 'AC 1 1', flags=('-pthread',))

    def test_network_state_models(self):
        # A fairness budget is not EAGAIN. Preserve and run ready work.
        remaining, passes = 20, []
        ready = deque(['session'])
        while ready:
            session = ready.popleft()
            amount = min(8, remaining)
            passes.append(amount)
            remaining -= amount
            if remaining:
                ready.append(session)
        self.assertEqual(passes, [8, 8, 4])
        # Either completion may be delivered first; one terminal transition.
        for order in itertools.permutations(('read', 'timer')):
            phase, outcomes = 1, []
            for event in order:
                captured_phase = 1
                if captured_phase != phase:
                    continue
                phase += 1
                outcomes.append(event)
            self.assertEqual(outcomes, [order[0]])

    def test_new_lessons_and_return_assignment_are_linked(self):
        keys = {3: ['sliding-window-workbook', 'generation-storage', 'fixed-pool-workbook'],
                6: ['get-or-create-workbook', 'async-logger-workbook', 'callback-lock-order']}
        for n, ids in keys.items():
            data = station(n)
            for key in ids:
                sec = next(s for s in data['theory'] if s['id'] == key)
                self.assertTrue(any('href=' in b.get('html','') for b in sec['blocks']))
                self.assertTrue(any(key in q['theoryRefs'] for q in data['quizzes']['advanced']))
        task = station(6)['tasks'][23]
        self.assertIn('после 7.6', task['level'])
        self.assertIn('не нужно для завершения первого прохода', task['brief'])


if __name__ == '__main__':
    unittest.main()
