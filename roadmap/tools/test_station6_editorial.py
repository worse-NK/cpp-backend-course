"""Bounded, race-free execution checks for station 6's editorial examples.

This suite never executes the deliberately racy/dangling examples. A passing
run is regression evidence, not a proof of all C++ executions or performance.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_cpp_editorial_audit import ProseParser

ROOT = Path(__file__).resolve().parents[1]


class StationSixEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'content/station6.json').read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def cpp(self, source, expected=None, valid=True):
        with tempfile.TemporaryDirectory(prefix='station6-editorial-') as folder:
            executable = str(Path(folder) / 'example')
            command = ['g++', '-std=c++20', '-O1', '-g', '-Wall', '-Wextra',
                       '-pedantic', '-pthread', '-x', 'c++', '-']
            command += ['-fsyntax-only'] if expected is None else ['-o', executable]
            built = subprocess.run(command, input=source, text=True,
                                   capture_output=True, timeout=40)
            self.assertEqual(built.returncode == 0, valid, built.stderr)
            if valid and expected is not None:
                ran = subprocess.run([executable], text=True, capture_output=True,
                                     timeout=8)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                if isinstance(expected, set):
                    self.assertIn(ran.stdout.strip(), expected)
                else:
                    self.assertEqual(ran.stdout.strip(), expected)

    def source(self, section, marker):
        candidates = [b['code'] for b in self.sections[section]['blocks']
                      if b['type'] == 'code' and marker in b['code']]
        self.assertEqual(len(candidates), 1, (section, marker))
        return candidates[0]

    def test_addresses_and_progress_are_stable(self):
        self.assertEqual(list(self.sections), [
            'learning-route', 'what-is-thread', 'concurrency-vs-parallelism',
            'std-thread', 'thread-args', 'jthread', 'scheduler-cost-model',
            'race-condition', 'payload-ready-story', 'memory-locations-conflicts',
            'happens-before', 'publication-patterns', 'mutex-basics', 'mutex-types',
            'lock-wrappers', 'deadlock', 'concurrent-api', 'lock-design-review',
            'atomic', 'memory-order', 'memory-observation-workbook',
            'atomic-protocols', 'atomic-wait-ref-fences', 'spinlock-futex',
            'progress-guarantees-performance', 'spsc-ring-model', 'spsc-ring-code',
            'condition-variable', 'semaphore', 'latch-barrier', 'once-and-local',
            'stop-aware-waits', 'wait-state-workbook', 'future-promise', 'async',
            'packaged-task', 'future-state-lifecycle', 'shutdown-backpressure',
            'bounded-queue-contract', 'thread-pool-contract', 'patterns',
            'pool-sizing-overload', 'concurrency-testing',
            'interview-concurrency-method', 'practical',
            'production-concurrency-observability', 'event-loop-pool-bridge',
            'concurrent-interview-components', 'get-or-create-workbook',
            'snapshot-container-workbook', 'shared-state-architecture',
            'async-logger-workbook', 'callback-lock-order',
            'hardware-cost-reasoning', 'cache-coherence-workbook',
            'queue-final-workbook', 'summary'])
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station6_progress_v1')
        order = self.data['readingOrder']
        self.assertEqual(set(order), set(self.sections))
        self.assertEqual(len(order), len(self.sections))
        for high_level in ['mutex-basics', 'condition-variable', 'future-promise']:
            self.assertLess(order.index(high_level), order.index('happens-before'))

    def test_every_section_has_visible_reasoning_check(self):
        count = 0
        for s in self.sections.values():
            checks = [b for b in s['blocks'] if b['type'] == 'self-check']
            self.assertTrue(checks, s['id'])
            for b in checks:
                count += 1
                for field in ['prompt', 'answer']:
                    self.assertGreater(len(b[field]), 30, (s['id'], field))
                    parser = ProseParser()
                    parser.feed(b[field])
                    self.assertEqual(parser.unknown, [], (s['id'], field))
        self.assertGreaterEqual(count, 58)

    def test_cpp20_sources_are_pinned_and_barrier_boundary_is_explicit(self):
        prose = '\n'.join(b.get('html', '') for s in self.sections.values()
                          for b in s['blocks'])
        self.assertNotIn('https://eel.is/c++draft/', prose)
        self.assertNotIn('/doc/libs/latest/', prose)
        barrier = '\n'.join(b.get('html', '') for b in
                            self.sections['latch-barrier']['blocks'])
        self.assertIn('N4861', barrier)
        self.assertIn('P2588R3', barrier)
        self.assertIn('при достижении нуля', barrier)
        self.assertNotIn('если никто не вызывает <code>wait</code>, стандарт оставляет', barrier)

    def test_template_spellings_are_not_html_tags_in_theory(self):
        for section in self.sections.values():
            for block in section['blocks']:
                if 'html' in block:
                    parser = ProseParser()
                    parser.feed(block['html'])
                    self.assertEqual(parser.unknown, [], section['id'])

    def test_thread_and_destruction_outputs(self):
        self.cpp(self.source('std-thread', 'int main()'),
                 'работа в потоке\nmain завершён')
        self.cpp(self.source('jthread', 'struct Report'), 'AWDE')
        q = self.data['quizzes']['interview'][0]
        self.cpp(q['q'][q['q'].index('#include'):], {'AWDE', 'ADWE'})

    def test_explicit_reference_and_non_reference_argument(self):
        head = '#include <thread>\n#include <functional>\n#include <iostream>\n'
        self.cpp(head + '''
void increment(int& x) { ++x; }
int main() {
    int value = 0;
    std::thread worker(increment, std::ref(value));
    worker.join();
    std::cout << value;
}
''', '1')
        self.cpp(head + '''
void increment(int& x) { ++x; }
int main() { int value = 0; std::thread worker(increment, value); worker.join(); }
''', valid=False)

    def test_join_before_return_reads_result(self):
        good = self.source('happens-before', 'return values;')
        self.cpp(good + '\n#include <iostream>\nint main(){std::cout<<collect()[0];}', '42')
        # The bad copy compiles but is never executed: its race has no output oracle.
        bad = self.source('happens-before', 'return std::vector<int>(values)')
        self.cpp(bad)

    def test_cas_recomputes_from_expected(self):
        self.cpp(self.source('atomic-protocols', 'int main()'), '0 7 1 8')
        self.cpp('''
#include <atomic>
#include <iostream>
int main() {
    std::atomic<int> value{7};
    int expected=5, desired=expected+1;
    value.compare_exchange_strong(expected,desired);
    bool ok=value.compare_exchange_strong(expected,desired);
    std::cout<<ok<<' '<<value.load();
}
''', '1 6')

    def test_atomic_wait_and_ref_have_distinct_responsibilities(self):
        self.cpp(self.source('atomic-wait-ref-fences', 'std::jthread producer'), '42')
        self.cpp(self.source('atomic-wait-ref-fences', 'required_alignment'), '2 2')

    def test_call_once_exception_and_stop_predicate(self):
        self.cpp(self.source('once-and-local', 'int attempts'), '1E2')
        self.cpp(self.source('stop-aware-waits', 'std::stop_source source'), '1 1')

    def test_future_error_is_ready_and_get_is_one_shot(self):
        self.cpp(self.source('future-state-lifecycle', 'provider.set_exception'), '1 E 0')
        self.cpp('''
#include <cassert>
#include <future>
#include <iostream>
int main() {
    int calls=0;
    { auto f=std::async(std::launch::deferred,[&]{++calls;return 7;});
      assert(f.wait_for(std::chrono::milliseconds(0))==std::future_status::deferred); }
    std::cout<<calls;
}
''', '0')

    def test_semaphore_guard_restores_permission_on_exception(self):
        fragment = self.source('semaphore', 'class SemaphoreGuard')
        self.cpp('''
#include <semaphore>
#include <stdexcept>
#include <iostream>
std::counting_semaphore<3> diskLimit(3);
void performDiskRead(){ throw std::runtime_error("read"); }
''' + fragment + '''
int main() {
    try { readDisk(); } catch(const std::runtime_error&) {}
    diskLimit.acquire(); diskLimit.acquire(); diskLimit.acquire();
    diskLimit.release(3);
    std::cout<<"restored";
}
''', 'restored')

    def test_bounded_queue_closed_before_and_after_items(self):
        fragment = self.source('bounded-queue-contract', 'class IntQueue')
        self.cpp(fragment + '''
#include <cassert>
#include <iostream>
int main() {
    IntQueue<2> q;
    assert(q.push(10)&&q.push(20));
    assert(q.pop()==10); assert(q.push(30)); q.close(); q.close();
    assert(q.pop()==20);assert(q.pop()==30);assert(!q.pop());assert(!q.push(40));
    IntQueue<1> early;early.close();assert(!early.pop());assert(!early.push(0));
    std::cout<<"drained";
}
''', 'drained')

    def test_close_releases_both_sides_for_either_start_order(self):
        fragment = self.source('bounded-queue-contract', 'class IntQueue')
        self.cpp(fragment + '''
#include <cassert>
#include <latch>
#include <thread>
#include <iostream>
int main() {
    for(int iteration=0;iteration<30;++iteration) {
        IntQueue<1> full;assert(full.push(1));
        std::latch entered(1);bool accepted=true;
        std::jthread p([&]{entered.count_down();accepted=full.push(2);});
        entered.wait();full.close();p.join();assert(!accepted);assert(full.pop()==1);assert(!full.pop());
        IntQueue<1> empty;bool got=true;
        std::jthread c([&]{got=empty.pop().has_value();});
        empty.close();c.join();assert(!got);
    }
    std::cout<<"closed";
}
''', 'closed')

    def test_spsc_boundary_and_fifo_checks(self):
        source = self.source('spsc-ring-code', 'class SpscIntQueue')
        for slots in [2,4,128]:
            with self.subTest(slots=slots):
                variant=source.replace('SpscIntQueue<128> queue;', f'SpscIntQueue<{slots}> queue;')
                self.cpp(variant, 'boundary checks passed\nFIFO 100000 passed')

    def test_pool_drains_values_and_exceptions(self):
        pool = self.data['tasks'][13]['solution']
        self.cpp(pool + '''
#include <cassert>
#include <iostream>
int main() {
    ThreadPool pool(2,4);
    auto a=pool.submit([]{return 21;});
    auto b=pool.submit([]()->int{throw std::runtime_error("job");});
    pool.shutdown(true);
    assert(a.get()==21);
    try{(void)b.get();assert(false);}catch(const std::runtime_error&){}
    try{pool.submit([]{});assert(false);}catch(const std::runtime_error&){}
    std::cout<<"drained";
}
''', 'drained')

    def test_cancelled_pending_result_ready_before_running_finishes(self):
        pool = self.data['tasks'][13]['solution']
        self.cpp(pool + '''
#include <cassert>
#include <chrono>
#include <iostream>
int main() {
    ThreadPool pool(1,4);
    std::promise<void> started,release;
    auto gate=release.get_future().share();
    auto running=pool.submit([&]{started.set_value();gate.wait();return 1;});
    started.get_future().wait();
    auto pending=pool.submit([]{return 2;});
    std::jthread stopper([&]{pool.shutdown(false);});
    auto status=pending.wait_for(std::chrono::seconds(2));
    release.set_value();stopper.join();
    assert(status==std::future_status::ready);
    try{(void)pending.get();assert(false);}catch(const std::future_error& e){
        assert(e.code()==std::make_error_code(std::future_errc::broken_promise));
    }
    assert(running.get()==1);
    std::cout<<"cancelled pending";
}
''', 'cancelled pending')

    def test_partial_pool_construction_has_an_exit_path(self):
        pool = self.data['tasks'][13]['solution']
        old='for (std::size_t i = 0; i < worker_count; ++i)\n                workers_.emplace_back([this] { worker_loop(); });'
        new='for (std::size_t i = 0; i < worker_count; ++i) {\n                if(i==1) throw std::runtime_error("injected start failure");\n                workers_.emplace_back([this] { worker_loop(); });\n            }'
        self.assertIn(old,pool)
        self.cpp(pool.replace(old,new)+'''
#include <iostream>
int main(){try{ThreadPool pool(3,4);}catch(const std::runtime_error&){std::cout<<"unwound";}}
''','unwound')

    def test_snapshot_owner_lifetime_and_final_workbook(self):
        self.cpp(self.source('shared-state-architecture','struct Config'),
                 'old: v1 10/20\nnew: v2 30/40\nold retained: true\nold released: true')
        self.cpp(self.source('queue-final-workbook','class Queue'),
                 'sum: 15\npush after close: false\nempty after drain: true')


if __name__ == '__main__':
    unittest.main()
