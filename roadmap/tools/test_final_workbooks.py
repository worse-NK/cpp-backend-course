"""Executable contracts for the final worked problems of stations 1–8.

Sources are extracted from the textbook, not maintained as a second code copy.
Undefined behaviour examples are never executed.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_expanded_examples


IDS = {
    1: 'ownership-final-workbook', 2: 'polymorphism-final-workbook',
    3: 'frequency-final-workbook', 4: 'reload-final-workbook',
    5: 'build-final-workbook', 6: 'queue-final-workbook',
    7: 'framing-final-workbook', 8: 'api-update-final-workbook',
}


def section(number):
    return next(s for s in test_expanded_examples.station(number)['theory']
                if s['id'] == IDS[number])


def program(number):
    return next(b['code'] for b in section(number)['blocks']
                if b.get('caption', '').startswith('Полная программа'))


def core(number):
    return program(number).split('int main()', 1)[0]


class FinalWorkbooks(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    def test_complete_programs_match_printed_output(self):
        for n in (1, 2, 3, 4, 6, 7, 8):
            with self.subTest(station=n):
                output = next(b['code'].strip() for b in section(n)['blocks']
                              if b.get('caption') == 'Ожидаемый вывод полной программы')
                # Compile every threaded example with the documented flag.
                self.run_cpp(program(n), output)

    def run_cpp(self, source, expected='OK'):
        with tempfile.TemporaryDirectory(prefix='roadmap-final-example-') as directory:
            binary = str(Path(directory) / 'example')
            result = subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra',
                                     '-pedantic', '-pthread', '-x', 'c++', '-', '-o', binary],
                                    input=source, text=True, capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run([binary], text=True, capture_output=True, timeout=8)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.strip(), expected)

    def test_ownership_transfer_chain(self):
        self.run_cpp(core(1) + r'''
int main() {
    auto owner = std::make_unique<Job>(7);
    auto next = std::move(owner);
    if (owner || !next) return 1;
    bool ok = submit(std::move(next));
    if (!ok || owner || next) return 2;
    auto rejected = std::make_unique<Job>(-1);
    if (submit(std::move(rejected)) || rejected) return 3;
}
''', 'create 7\nrun 7\ndestroy 7\ncreate -1\ndestroy -1')

    def test_unique_owner_cannot_be_copied(self):
        self.check_cpp(program(1).replace('submit(std::move(owner))', 'submit(owner)'),
                       valid=False)

    def test_virtual_call_in_base_destructor(self):
        source = program(2).replace('virtual ~Base() { std::cout << "Base destructor\\n"; }',
                                   'virtual ~Base() { std::cout << "Base destructor\\n"; run(); }')
        self.run_cpp(source, 'before scope\nBase constructor\nBase run\nMember constructor\n'
                     'Derived constructor\nready\nDerived run\nDerived destructor\n'
                     'Member destructor\nBase destructor\nBase run\nafter scope')

    def test_override_detects_signature_mismatch(self):
        self.check_cpp(program(2).replace('void run() const override', 'void run() override'),
                       valid=False)
        self.check_cpp(program(2).replace('virtual ~Base()', '~Base()'), valid=False)

    def test_frequency_ties_and_boundaries(self):
        self.run_cpp(core(3) + r'''
int main() {
    const std::vector<int> input{500,404,500,404,401};
    if (top_codes(input,2) != std::vector<Frequency>{{404,2},{500,2}}) return 1;
    if (top_codes(input,10) != std::vector<Frequency>{{404,2},{500,2},{401,1}}) return 2;
    if (top_codes({7,7,7},3) != std::vector<Frequency>{{7,3}}) return 3;
    if (!top_codes({},8).empty() || !top_codes(input,0).empty()) return 4;
    if (input != std::vector<int>{500,404,500,404,401}) return 5;
    std::cout << "OK";
}
''')

    def test_reload_errors_leave_original_intact(self):
        self.run_cpp(core(4) + r'''
int main() {
    Config config;
    for (const char* bad : {"", "0", "65536", "-1", "+1", " 80", "80x",
                            "999999999999999999999999999999999999"}) {
        try { config.reload({"8080", bad}); return 1; }
        catch (const std::invalid_argument&) {}
        if (config.ports() != std::vector<int>{80,443}) return 2;
    }
    config.reload({"00080", "65535", "80"});
    if (config.ports() != std::vector<int>{80,65535,80}) return 3;
    config.reload({});
    if (!config.ports().empty()) return 4;
    std::cout << "OK";
}
''')

    def test_multifile_manual_and_cmake_builds(self):
        with tempfile.TemporaryDirectory(prefix='roadmap-build-workbook-') as directory:
            root = Path(directory)
            for b in section(5)['blocks']:
                if b.get('caption', '').startswith('Полный файл · '):
                    (root / b['caption'].split(' · ')[1]).write_text(b['code'])
            def command(args, valid=True):
                r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=40)
                self.assertEqual(r.returncode == 0, valid, r.stdout + r.stderr)
                return r
            for name in ('main', 'percent'):
                command(['g++', '-std=c++20', '-Wall', '-Wextra', '-pedantic',
                         '-c', name + '.cpp', '-o', name + '.o'])
            command(['g++', 'main.o', '-o', 'broken'], valid=False)
            command(['g++', 'main.o', 'percent.o', '-o', 'manual'])
            expected = '-5 -> 0\n35 -> 35\n140 -> 100'
            self.assertEqual(command(['./manual']).stdout.strip(), expected)
            command(['cmake', '-S', '.', '-B', 'build', '-G', 'Unix Makefiles'])
            command(['cmake', '--build', 'build'])
            self.assertEqual(command(['./build/example']).stdout.strip(), expected)
            # A different overload is not the missing definition.
            p = root / 'percent.cpp'
            p.write_text(p.read_text().replace('int clamp_percent(int value)',
                                               'int clamp_percent(int& value)'))
            command(['g++', '-std=c++20', '-c', 'percent.cpp', '-o', 'wrong.o'])
            command(['g++', 'main.o', 'wrong.o', '-o', 'wrong'], valid=False)

    def test_queue_close_drain_and_fifo(self):
        self.run_cpp(core(6) + r'''
int main() {
    Queue empty;
    empty.close(); empty.close();
    if (empty.push(1) || empty.pop()) return 1;
    Queue tail;
    tail.push(10); tail.push(20); tail.close();
    if (tail.pop() != 10 || tail.pop() != 20 || tail.pop()) return 2;
    Queue queue;
    bool correct = true;
    int count = 0;
    std::jthread worker([&] {
        while (auto value = queue.pop()) {
            if (*value != count) correct = false;
            ++count;
        }
    });
    CloseOnExit guard{queue};
    for (int i = 0; i < 2000; ++i) queue.push(i);
    queue.close(); worker.join();
    if (!correct || count != 2000) return 3;
    std::cout << "OK";
}
''')

    def test_queue_close_releases_producer_and_consumer(self):
        # The latch establishes that the operation is about to be called;
        # either close-before-wait or close-during-wait must be safe.
        self.run_cpp(core(6) + r'''
#include <latch>
int main() {
    Queue full;
    full.push(1); full.push(2);
    std::latch started(1);
    bool accepted = true;
    std::jthread producer([&] { started.count_down(); accepted = full.push(3); });
    started.wait(); full.close(); producer.join();
    if (accepted || full.pop()!=1 || full.pop()!=2 || full.pop()) return 1;
    Queue empty;
    std::latch ready(1);
    bool has_value = true;
    std::jthread consumer([&] { ready.count_down(); has_value = empty.pop().has_value(); });
    ready.wait(); empty.close(); consumer.join();
    if (has_value) return 2;
    std::cout << "OK";
}
''')

    def test_parser_every_partition_and_binary_payload(self):
        self.run_cpp(core(7) + r'''
#include <vector>
int main() {
    const std::string bytes("\x00\x03" "ABC\x00\x00\x00\x01" "Z",10);
    const std::vector<std::string> expected{"ABC", "", "Z"};
    // Every possible boundary between neighbouring bytes: 2^9 partitions.
    for (unsigned mask = 0; mask < (1u << 9); ++mask) {
        FrameParser p;
        std::vector<std::string> got;
        std::size_t begin = 0;
        for (std::size_t end = 1; end <= bytes.size(); ++end) {
            if (end != bytes.size() && !(mask & (1u << (end-1)))) continue;
            auto chunk = std::string_view(bytes).substr(begin, end-begin);
            for (unsigned char byte : chunk)
                if (auto message = p.push(byte)) got.push_back(*message);
            begin = end;
        }
        p.finish();
        if (got != expected) return 1;
    }
    FrameParser binary;
    binary.push(0); binary.push(2); binary.push(0);
    auto message = binary.push(255);
    if (!message || message->size()!=2 || (*message)[0]!=0 ||
        static_cast<unsigned char>((*message)[1])!=255) return 2;
    binary.finish();
    FrameParser max;
    max.push(0); max.push(8);
    for (int i=0;i<8;++i) {
        auto value=max.push('x');
        if (bool(value)!=(i==7)) return 3;
    }
    max.finish();
    std::cout << "OK";
}
''')

    def test_parser_incomplete_and_oversized(self):
        self.run_cpp(core(7) + r'''
int main() {
    const std::string frame("\x00\x02" "AB",4);
    for (std::size_t length=1; length<frame.size(); ++length) {
        FrameParser parser;
        for (std::size_t i=0;i<length;++i) parser.push(frame[i]);
        try { parser.finish(); return 1; }
        catch (const std::runtime_error& e) {
            if (std::string(e.what())!="truncated frame") return 2;
        }
    }
    FrameParser oversized;
    oversized.push(0);
    try { oversized.push(9); return 3; }
    catch (const std::runtime_error& e) {
        if (std::string(e.what())!="frame too large") return 4;
    }
    try { oversized.push(0); return 5; }
    catch (const std::runtime_error&) {}
    FrameParser fresh; fresh.finish();
    std::cout << "OK";
}
''')

    def test_update_rejections_and_concurrent_competitors(self):
        self.run_cpp(core(8) + r'''
#include <thread>
int main() {
    Store store;
    if (store.replace(7,"",true)!=Update::invalid ||
        store.replace(7,std::string(41,'x'),true)!=Update::invalid) return 1;
    if (store.read().version!=7 || store.read().title!="A") return 2;
    Update x{}, y{};
    std::jthread a([&] { x=store.replace(7,"B",false); });
    std::jthread b([&] { y=store.replace(7,"A",true); });
    a.join(); b.join();
    if ((x==Update::applied)+(y==Update::applied)!=1) return 3;
    if ((x==Update::stale)+(y==Update::stale)!=1) return 4;
    auto result=store.read();
    if (result.version!=8) return 5;
    if (x==Update::applied && (result.title!="B" || result.done)) return 6;
    if (y==Update::applied && (result.title!="A" || !result.done)) return 7;
    if (store.replace(7,"C",false)!=Update::stale || store.read().version!=8) return 8;
    std::cout << "OK";
}
''')

    def test_sections_are_in_final_module_and_linked(self):
        for n, id in IDS.items():
            with self.subTest(station=n):
                d = test_expanded_examples.station(n)
                ids = [s['id'] for s in d['theory']]
                self.assertIn(id, ids[-2:])
                self.assertEqual(section(n)['substation'], d['substations'][-1]['id'])
                self.assertIn('#section='+id, json.dumps(d['theory'][0], ensure_ascii=False))
                self.assertTrue(any(b['type']=='visual' for b in section(n)['blocks']))
                if 'readingOrder' in d:
                    self.assertEqual(d['readingOrder'][-2:], [id, 'summary'])


if __name__ == '__main__':
    unittest.main()
