#!/usr/bin/env python3
"""Executable/model regressions for completing chapters 6 and 7.
No UB or intentional deadlock is executed. Boost architecture sketches are
reviewed against the official contracts, not claimed to be compiled here.
"""
import re
import unittest

from test_expanded_examples import code, station
import test_remaining_examples


class BackendCompletion(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_queue_sequence_and_wrap(self):
        source = code(6, "bounded-queue-contract", 1)
        main = r"""
#include <iostream>
int main() {
    IntQueue<2> q;
    q.push(10); q.push(20);
    std::cout << *q.pop() << ' ';
    q.push(30); q.close(); q.close();
    std::cout << *q.pop() << ' ' << *q.pop() << ' '
              << q.pop().has_value() << ' ' << q.push(40);
}
"""
        self.cpp(source + main, "10 20 30 0 0", flags=("-pthread",))
        self.cpp(source + "\nint main(){IntQueue<0> q;}", valid=False,
                 flags=("-pthread",))

    def test_queue_concurrent_drain(self):
        source = code(6, "bounded-queue-contract", 1)
        main = r"""
#include <iostream>
#include <thread>
#include <vector>
int main() {
    IntQueue<3> q;
    int total = 0;
    std::jthread consumer([&] {
        while (auto item = q.pop()) total += *item;
    });
    {
        std::vector<std::jthread> producers;
        for (int p = 0; p != 4; ++p)
            producers.emplace_back([&] {
                for (int i = 0; i != 100; ++i) q.push(1);
            });
    }
    q.close();
    consumer.join(); // publish total before reading it
    std::cout << total << ' ' << q.pop().has_value();
}
"""
        self.cpp(source + main, "400 0", flags=("-pthread",))

    def test_queue_close_producer_and_consumer(self):
        source = code(6, "bounded-queue-contract", 1)
        # Correct whether close runs before or after either worker reaches wait.
        main = r"""
#include <iostream>
#include <thread>
int main() {
    IntQueue<1> full, empty;
    full.push(7);
    bool accepted = true, got_item = true;
    std::jthread producer([&] { accepted = full.push(8); });
    std::jthread consumer([&] { got_item = empty.pop().has_value(); });
    full.close(); empty.close();
    producer.join(); consumer.join();
    std::cout << accepted << ' ' << got_item << ' '
              << *full.pop() << ' ' << full.pop().has_value();
}
"""
        self.cpp(source + main, "0 0 7 0", flags=("-pthread",))

    def test_stop_wait_predicate_wins(self):
        source = code(6, "stop-aware-waits", -1)
        self.cpp(source, "1 1", flags=("-pthread",))
        self.cpp(source.replace("return true;", "return false;"),
                 "0 1", flags=("-pthread",))

    def test_packaged_task_example(self):
        self.cpp(code(6, "packaged-task"), "42", flags=("-pthread",))

    def test_deferred_wait_and_get(self):
        self.cpp(r"""
#include <chrono>
#include <future>
#include <iostream>
#include <thread>
int main() {
    int calls = 0;
    const auto caller = std::this_thread::get_id();
    auto f = std::async(std::launch::deferred, [&] {
        ++calls;
        return std::this_thread::get_id() == caller;
    });
    auto status = f.wait_for(std::chrono::milliseconds(0));
    std::cout << calls << ' ' << (status == std::future_status::deferred) << ' ';
    auto same_thread = f.get();
    std::cout << same_thread << ' ' << calls << ' ' << f.valid();
}
""", "0 1 1 1 0", flags=("-pthread",))

    def test_send_all_offsets_and_interruption(self):
        source = code(7, "partial-io-eof")
        prelude = r"""
#include <cerrno>
#include <cstddef>
#include <iostream>
#include <span>
#include <string>
#include <sys/socket.h>
std::string accepted;
int calls = 0;
ssize_t model_send(int, const void* data, std::size_t length, int) {
    ++calls;
    if (calls == 2) { errno = EINTR; return -1; }
    std::size_t n = calls == 1 ? 3 : (calls == 3 ? 2 : length);
    if (n > length) n = length;
    accepted.append(static_cast<const char*>(data), n);
    return static_cast<ssize_t>(n);
}
"""
        main = r"""
int main() {
    const std::string input = "ABCDEFGH";
    auto bytes = std::as_bytes(std::span(input.data(), input.size()));
    std::cout << send_all(1, bytes) << ' ' << accepted << ' ' << calls;
}
"""
        model = prelude + source.replace("::send(", "::model_send(") + main
        self.cpp(model, "1 ABCDEFGH 4")
        self.cpp(model.replace("errno = EINTR", "errno = EAGAIN"), "0 ABC 2")

    def test_queue_arithmetic_and_network_examples(self):
        self.assertEqual(1 / (.2 + .8 / 4), 2.5)
        capacity = 4 / .020
        self.assertEqual(capacity, 200)
        self.assertEqual(500 / (300 - capacity), 5)
        self.assertEqual(1500 - 20 - 32, 1448)
        self.assertEqual(min(12000, 8000) - 6000, 2000)
        self.assertEqual(900 + 1 + 10, 911)
        self.assertEqual(70 - 30 - 10, 30)
        self.assertEqual(len(b'{"value": 42}'), 13)

    def test_every_module_has_new_reasoning_questions(self):
        # The October 2 workbook occupies authored positions 50..65 in both
        # banks. Positions are retained when wording or the transfer example
        # is revised; the former first prompt is not a permanent identifier.
        starts = {6: 50, 7: 50}
        for n in (6, 7):
            data = station(n)
            all_questions = data["quizzes"]["advanced"]
            start = starts[n]
            questions = all_questions[start:start + 16]
            self.assertEqual(len(questions), 16)
            for module in data["substations"]:
                # The October 2 workbook predates the new introductory access
                # chapter. Its separate questions/coverage are guarded by
                # test_network_foundations and test_station_assessment.js.
                if n == 7 and module["id"] == "remote-access":
                    continue
                with self.subTest(station=n, module=module["id"]):
                    self.assertEqual(sum(q["substation"] == module["id"]
                                         for q in questions), 2)

    def test_no_http_prerequisite_in_asio_session(self):
        data = station(7)
        s = next(s for s in data["theory"]
                 if s["id"] == "asio-coroutine-session-design")
        source = next(b["code"] for b in s["blocks"] if b["type"] == "code")
        self.assertIn("framed_echo", source)
        self.assertNotIn("beast::", source)
        self.assertNotIn("http::", source)
        http = code(7, "beast-http-server")
        self.assertLess(http.index("parser.body_limit("), http.index("http::async_read("))

    def test_same_stream_for_all_chunkings(self):
        # Independent model of the new one-byte length protocol. Its limit
        # applies before body accumulation; it is not a Boost integration test.
        def decode(chunks, eof=False):
            pending = bytearray()
            out = []
            for chunk in chunks:
                pending.extend(chunk)
                while pending:
                    length = pending[0]
                    if not 1 <= length <= 64:
                        raise ValueError("invalid frame size")
                    if len(pending) < length + 1:
                        break
                    out.append(bytes(pending[1:length + 1]))
                    del pending[:length + 1]
            if eof and pending:
                raise ValueError("truncated frame")
            return out, bytes(pending)
        wire = bytes.fromhex("02 41 42 01 43")
        for mask in range(1 << (len(wire) - 1)):
            boundaries = [0] + [i for i in range(1, len(wire))
                                if mask & (1 << (i - 1))] + [len(wire)]
            chunks = [wire[a:b] for a, b in zip(boundaries, boundaries[1:])]
            self.assertEqual(decode(chunks, eof=True), ([b"AB", b"C"], b""))
        for bad in [bytes([0]), bytes([65]), bytes.fromhex("02 41")]:
            with self.assertRaises(ValueError):
                decode([bad], eof=True)
        self.assertEqual(decode([bytes([64]) + b"x" * 64], eof=True),
                         ([b"x" * 64], b""))


if __name__ == "__main__":
    unittest.main()
