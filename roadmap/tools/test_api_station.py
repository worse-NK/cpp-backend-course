#!/usr/bin/env python3
"""Station 8: executable examples and optional real loopback HTTP integration.

STATION8_DEPS points to official pinned httplib.h v0.59.0 and json.hpp v3.12.0.
No dependencies are downloaded by this test. No public interface is opened.
"""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

from test_expanded_examples import code, station
import test_remaining_examples


class ApiExamples(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_parse_id(self):
        self.cpp(code(8, "request-boundaries"), "1 0 0 0 0 0")

    def test_atomic_example(self):
        self.cpp(code(8, "atomic-service"), "1 1 B 0 8", flags=("-pthread",))

    def test_atomic_competitors(self):
        source = code(8, "atomic-service").split("int main()", 1)[0]
        self.cpp(source + r'''
#include <thread>
int main() {
    OneTask store;
    Update a{}, b{};
    std::jthread first([&]{a=store.replace(7,"B",false);});
    std::jthread second([&]{b=store.replace(7,"C",true);});
    first.join(); second.join();
    auto t=store.read();
    std::cout << ((a==Update::applied)+(b==Update::applied)) << ' '
              << ((a==Update::stale)+(b==Update::stale)) << ' ' << t.version;
}
''', "1 1 8", flags=("-pthread",))

    def test_invalid_update_preserves_state(self):
        source = code(8, "atomic-service").split("int main()", 1)[0]
        self.cpp(source + r'''
int main() {
    OneTask store;
    try { store.replace(7,"",true); return 1; }
    catch(const std::invalid_argument&) {}
    auto t=store.read();
    std::cout << t.title << ' ' << t.done << ' ' << t.version;
}
''', "A 0 7", flags=("-pthread",))

    def test_pagination_and_utf8_workbook(self):
        before = [10, 20, 30, 40]
        after = [5, *before]
        self.assertEqual(before[:2], [10, 20])
        self.assertEqual(after[2:4], [20, 30])
        self.assertEqual([x for x in after if x > 20][:2], [30, 40])
        self.assertEqual(len(("я" * 150).encode("utf-8")), 300)

    def test_module_coverage(self):
        d = station(8)
        self.assertEqual(len(d["substations"]), 9)
        for module in d["substations"]:
            mid = module["id"]
            with self.subTest(module=mid):
                sections = [s for s in d["theory"] if s["substation"] == mid]
                self.assertGreaterEqual(len(sections), 5)
                for s in sections:
                    self.assertTrue(any('href="https://' in b.get("html", "")
                                        for b in s["blocks"]), s["id"])
                for kind, questions in d["quizzes"].items():
                    self.assertGreaterEqual(sum(q["substation"] == mid for q in questions), 3, kind)
                self.assertGreaterEqual(sum(t["substation"] == mid for t in d["tasks"]), 2)

    def test_framing_example(self):
        self.cpp(code(8, "protobuf-file-workbook", 2), "10 10 1 1 1")

    def test_framing_prefixes_and_binary_payload(self):
        source = code(8, "protobuf-file-workbook", 2).split("int main()", 1)[0]
        self.cpp(source + r'''
int main() {
    for (std::size_t length : {0u, 6u, 256u, 1024u}) {
        std::string payload;
        for (std::size_t i=0; i<length; ++i)
            payload.push_back(static_cast<char>(i & 0xffu));
        auto bytes=frame(payload);
        for (std::size_t cut=0; cut<bytes.size(); ++cut) {
            auto part=read_record(std::string_view(bytes).substr(0,cut));
            if (part.state!=ReadState::need_more || part.consumed!=0) return 1;
        }
        auto whole=read_record(bytes);
        if (whole.state!=ReadState::ready || whole.payload!=payload ||
            whole.consumed!=bytes.size()) return 2;
    }
    auto joined=frame("first")+frame("second");
    auto first=read_record(joined);
    auto second=read_record(std::string_view(joined).substr(first.consumed));
    std::cout << (first.payload=="first" && second.payload=="second");
}
''', "1")

    def test_framing_limit_and_untrusted_length(self):
        source = code(8, "protobuf-file-workbook", 2).split("int main()", 1)[0]
        self.cpp(source + r'''
int main() {
    for (const auto& prefix : {std::string("\x00\x00\x04\x01",4),
                               std::string(4,static_cast<char>(0xff))}) {
        auto r=read_record(prefix);
        if(r.state!=ReadState::too_large || r.consumed!=0) return 1;
    }
    try { frame(std::string(1025,'x')); return 2; }
    catch(const std::length_error&) {}
    std::cout << "bounded";
}
''', "bounded")

    def test_batch_documented_response(self):
        # Tests the worked JSON, not a batch endpoint: the minimal server has none.
        exchange = code(8, "batch-projection-workbook")
        response = json.loads(exchange[exchange.index("{"):])
        results = response["results"]
        self.assertEqual([r["id"] for r in results], ["7", "9", "12"])
        self.assertEqual([r["status"] for r in results], ["ok", "not_found", "ok"])
        self.assertEqual(set(results[1]), {"id", "status"})
        for result, title in ((results[0], "A"), (results[2], "C")):
            self.assertEqual(result["task"], {"id": result["id"], "title": title})

    def test_format_cost_workbook(self):
        for rate, expected_json, expected_proto in ((100_000_000,5.46,4.78),
                                                     (10_000_000,14.1,9.1)):
            js=4+.5+12_000*8/rate*1000
            pb=4+.3+6_000*8/rate*1000
            self.assertAlmostEqual(js,expected_json)
            self.assertAlmostEqual(pb,expected_proto)
        self.assertAlmostEqual((5.46-4.78)/5.46*100,12.4542,places=3)
        self.assertAlmostEqual((14.1-9.1)/14.1*100,35.4610,places=3)
        self.assertEqual(300-80-20,200)

    def test_interview_workbooks_have_question_links(self):
        d=station(8)
        for ref in ("batch-projection-workbook", "rpc-choice-workbook",
                    "protobuf-file-workbook", "format-cost-workbook"):
            for kind, questions in d["quizzes"].items():
                with self.subTest(section=ref,kind=kind):
                    self.assertTrue(any(ref in q["theoryRefs"] for q in questions))


@unittest.skipUnless(os.environ.get("STATION8_DEPS"), "set STATION8_DEPS for pinned HTTP dependencies")
class ApiHttpIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="station8-http-")
        cls.addClassCleanup(cls.directory.cleanup)
        binary = str(Path(cls.directory.name) / "server")
        dependencies = Path(os.environ["STATION8_DEPS"])
        header = (dependencies / "httplib.h").read_text()
        if '#define CPPHTTPLIB_VERSION "0.59.0"' not in header:
            raise AssertionError("Expected cpp-httplib v0.59.0")
        jheader = (dependencies / "json.hpp").read_text()
        for field, value in (("MAJOR", 3), ("MINOR", 12), ("PATCH", 0)):
            if f"#define NLOHMANN_JSON_VERSION_{field} {value}" not in jheader:
                raise AssertionError("Expected nlohmann/json v3.12.0")
        compiled = subprocess.run(
            ["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic", "-pthread",
             "-I", str(dependencies), "-x", "c++", "-", "-o", binary],
            input=code(8, "httplib-example"), text=True, capture_output=True, timeout=90)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            cls.port = reservation.getsockname()[1]
        cls.process = subprocess.Popen([binary, str(cls.port)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise AssertionError("Local server exited before readiness")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=.1):
                    return
            except OSError:
                time.sleep(.05)
        raise AssertionError("Local server did not become ready")

    @classmethod
    def stop_server(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
        try:
            cls.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.communicate(timeout=5)

    def request(self, method, path, body=None, content_type="application/json"):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            client.request(method, path, body=body, headers={"Content-Type": content_type})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            client.close()

    def create(self, title):
        status, headers, raw = self.request("POST", "/tasks", json.dumps({"title": title, "done": False}).encode())
        self.assertEqual(status, 201)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        value = json.loads(raw)
        self.assertEqual(value["title"], title)
        self.assertIs(value["done"], False)
        self.assertEqual(value["version"], 1)
        self.assertEqual(headers["Location"], "/tasks/" + value["id"])
        status, _, raw = self.request("GET", headers["Location"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), value)
        return value["id"]

    def test_create_read_and_escaping(self):
        self.create('Задача "А" \\ новая строка\nи ещё текст')

    def test_input_boundaries(self):
        cases = [(b'{', 400), (b'[]', 422),
                 (b'{"title":"a","done":"false"}', 422),
                 (b'{"title":"a"}', 422),
                 (b'{"title":"a","done":false,"owner":"other"}', 422),
                 (b'{"title":"a","title":"b","done":false}', 400),
                 (b'{"title":"","done":false}', 422),
                 (json.dumps({"title": "я" * 150, "done": False}).encode(), 422)]
        for body, expected in cases:
            with self.subTest(body=body):
                status, headers, raw = self.request("POST", "/tasks", body)
                self.assertEqual(status, expected)
                self.assertTrue(headers["Content-Type"].startswith("application/problem+json"))
                problem = json.loads(raw)
                self.assertEqual(problem["status"], status)
                self.assertEqual(problem["type"], "about:blank")

    def test_media_type_missing_and_size(self):
        self.assertEqual(self.request("POST", "/tasks", b'{}', "text/plain")[0], 415)
        status, _, raw = self.request("GET", "/tasks/99999999")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(raw)["status"], 404)
        # Transport-generated response is deliberately not promised as Problem Details.
        self.assertEqual(self.request("POST", "/tasks", b'x' * 4097)[0], 413)

    def test_parallel_creates_unique_ids(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(self.create, [f"parallel-{i}" for i in range(24)]))
        self.assertEqual(len(set(ids)), 24)


if __name__ == "__main__":
    unittest.main()
