#!/usr/bin/env python3
"""Executable examples and address arithmetic from the 6–7 editorial pass."""
import copy
from pathlib import Path
import build_stations
import ipaddress
import unittest

from test_expanded_examples import code, station
import test_remaining_examples


class BackendDeepening(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_cas_values_and_stale_desired(self):
        self.cpp(code(6, "atomic-protocols", 1), "0 7 1 8", flags=("-pthread",))
        question = next(q for q in station(6)["quizzes"]["advanced"]
                        if "desired" in q["q"] and "\n\n" in q["q"])
        self.assertIn("desired", question["q"])
        snippet = question["q"].split("\n\n", 1)[1]
        self.cpp("#include <atomic>\n#include <iostream>\nint main(){\n" +
                 snippet + "\nstd::cout << ok << ' ' << value.load();\n}",
                 "1 6", flags=("-pthread",))

    def test_reservation_limit(self):
        source = code(6, "atomic-protocols", 2)
        source += """
#include <array>
#include <iostream>
#include <thread>
int main() {
    std::atomic<int> used{0};
    std::array<int, 8> accepted{};
    {
        std::array<std::jthread, 8> workers;
        for (std::size_t i = 0; i < workers.size(); ++i)
            workers[i] = std::jthread([&, i] { accepted[i] = try_reserve(used, 3); });
    }
    int total = 0;
    for (int result : accepted) total += result;
    std::cout << used.load() << ' ' << total << ' ' << try_reserve(used, 3);
}
"""
        self.cpp(source, "3 3 0", flags=("-pthread",))
        self.cpp(source.replace("try_reserve(used, 3)", "try_reserve(used, 1)"),
                 "1 1 0", flags=("-pthread",))

    def test_wait_and_atomic_ref(self):
        source = code(6, "atomic-wait-ref-fences", 0)
        self.cpp(source, "42", flags=("-pthread",))
        # Publish before wait; no old notification needs to be remembered.
        already_ready = source.replace("std::jthread producer([&] {", "auto produce = [&] {")
        already_ready = already_ready.replace("        state.notify_one();", "")
        already_ready = already_ready.replace("    });", "    };\n    produce();")
        self.cpp(already_ready, "42", flags=("-pthread",))
        self.cpp(code(6, "atomic-wait-ref-fences", 1), "2 2", flags=("-pthread",))
        # Do not run a wait with unchanged value or a mixed-access atomic_ref case:
        # those are not expected-output tests.

    def test_shards_and_future_exception(self):
        self.cpp(code(6, "progress-guarantees-performance"), "2000", flags=("-pthread",))
        self.cpp(code(6, "future-state-lifecycle"), "1 E 0", flags=("-pthread",))

    def test_network_workbook(self):
        for prefix, network, broadcast, hosts in [
            (24, "192.168.10.0", "192.168.10.255", 254),
            (26, "192.168.10.64", "192.168.10.127", 62),
            (28, "192.168.10.64", "192.168.10.79", 14),
        ]:
            with self.subTest(prefix=prefix):
                subnet = ipaddress.ip_interface(f"192.168.10.73/{prefix}").network
                self.assertEqual(str(subnet.network_address), network)
                self.assertEqual(str(subnet.broadcast_address), broadcast)
                self.assertEqual(len(list(subnet.hosts())), hosts)
        question = next(q for q in station(7)["quizzes"]["advanced"]
                        if "192.168.10.64 и 192.168.10.79" in q["options"])
        self.assertIn("/28", question["q"])
        self.assertEqual(question["options"][question["answer"]],
                         "192.168.10.64 и 192.168.10.79")
        routes = [ipaddress.ip_network(p) for p in
                  ("10.0.0.0/8", "10.20.0.0/16", "10.20.30.0/24")]
        destination = ipaddress.ip_address("10.20.30.9")
        selected = max((p for p in routes if destination in p), key=lambda p: p.prefixlen)
        self.assertEqual(str(selected), "10.20.30.0/24")
        self.assertEqual(len(list(ipaddress.ip_network("192.0.2.0/31").hosts())), 2)


    def test_lanes_modes(self):
        data = station(7)
        section = next(s for s in data["theory"] if s["id"] == "ethernet-neighbor")
        block = next(b for b in section["blocks"] if b["type"] == "lanes")
        self.assertEqual(block["mode"], "fields")
        build_stations.validate(data, Path("station7.json"))
        for mode in ("timeline", None):
            variant = copy.deepcopy(data)
            target = next(s for s in variant["theory"] if s["id"] == "ethernet-neighbor")
            lane = next(b for b in target["blocks"] if b["type"] == "lanes")
            if mode is None:
                del lane["mode"]  # Existing timeline blocks remain valid.
            else:
                lane["mode"] = mode
            build_stations.validate(variant, Path("station7.json"))
        block["mode"] = "typo"
        with self.assertRaisesRegex(ValueError, "mode"):
            build_stations.validate(data, Path("station7.json"))


if __name__ == "__main__":
    unittest.main()
