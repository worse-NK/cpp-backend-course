#!/usr/bin/env python3
"""Guard selected teaching dependencies, not the readability of prose."""
import json
from pathlib import Path
import unittest

CONTENT = Path(__file__).resolve().parents[1] / "content"

# Only pedagogically important edges: unrelated sections may still move.
BEFORE = {
    '7-traffic': [('learning-route', 'traffic-wireshark-three-panes'),
                  ('traffic-filter-pipeline', 'traffic-stream-follow'),
                  ('traffic-tcp-sequence-ledger', 'traffic-tcp-retransmission-evidence')],
    '7-netlab': [('netlab-isolation-boundary', 'netlab-build-observe'),
                 ('netlab-bridge-learning', 'netlab-route-next-hop'),
                 ('netlab-hooks-local-forward', 'netlab-conntrack-states'),
                 ('netlab-ipv6-addresses', 'netlab-ra-slaac'),
                 ('netlab-routing-without-nat', 'netlab-snat-reply'),
                 ('netlab-dnat-filter', 'netlab-diagnostic-ladder'),
                 ('netlab-failure-recovery', 'netlab-udp-final-workbook')],
    10: [('metrics-slo', 'capacity-experiment'), ('capacity-experiment', 'capacity-local-lab'),
         ('test-contract', 'test-levels'), ('container-model', 'docker-network-data')],
    9: [
        ('storage', 'transactions'), ('transactions', 'concurrent-update'),
        ('concurrent-update', 'isolation'),
        ('indexes', 'index-decisions'), ('index-decisions', 'storage-maintenance'),
        ('cpp-storage', 'pool'), ('evolution', 'durability-limits'),
        ('design', 'parking-final-workbook'),
    ],
    0: [
        ("object-state-identity", "methods"),
        ("methods", "this"),
        ("constructor", "initialization-model"),
        ("invariants", "valid-states-factories"),
    ],
    1: [
        ("raii", "resource-taxonomy"),
        ("raii", "lifetime-storage"),
        ("references", "const"),
        ("const", "ownership-contracts"),
        ("smart-ptr", "smart-ptr-deep"),
        ("move", "rule-of-five"),
        ("rule-of-five", "copy-elision"),
        ("modern-syntax", "lambda-lifetime"),
    ],
    2: [
        ("ctor-order", "multiple-inheritance"),
        ("ctor-order", "interview-lifetime"),
        ("virtual", "static-dynamic-view"),
        ("static-dynamic-view", "virtual-edge-cases"),
        ("virtual-dtor", "polymorphic-copy"),
    ],
    3: [
        ("vector", "allocation-containers"),
        ("allocation-containers", "invalidation-erasure"),
        ("map-set", "unordered-contract"),
        ("iterators", "algorithms"),
        ("interview-sequence-workbook", "bit-mask-workbook"),
        ("bit-mask-workbook", "subtree-sets-workbook"),
        ("subtree-sets-workbook", "graph-copy-workbook"),
        ("graph-copy-workbook", "rle-workbook"),
        ("templates", "template-compilation"),
        ("template-compilation", "templates-deep"),
        ("non-owning-vocabulary", "ranges-lifetime"),
        ("template-compilation", "sfinae-and-constraints"),
        ("lru-window-generations", "sliding-window-workbook"),
        ("sliding-window-workbook", "generation-storage"),
        ("generation-storage", "fixed-pool-workbook"),
    ],
    4: [
        ("exceptions-basics", "exception-timeline"),
        ("exception-timeline", "exception-object-matching"),
        ("exception-object-matching", "constructor-transaction"),
        ("exception-timeline", "construction-cleanup"),
        ("exception-safety", "strong-guarantee-example"),
        ("noexcept", "strong-guarantee-example"),
        ("strong-guarantee-example", "transactional-updates"),
        ("noexcept", "noexcept-deep"),
    ],
    6: [
        ("std-thread", "jthread"),
        ("memory-locations-conflicts", "happens-before"),
        ("atomic", "memory-order"),
        ("memory-order", "memory-observation-workbook"),
        ("stop-aware-waits", "wait-state-workbook"),
        ("get-or-create-workbook", "snapshot-container-workbook"),
        ("hardware-cost-reasoning", "cache-coherence-workbook"),
        ("condition-variable", "stop-aware-waits"),
        ("future-promise", "future-state-lifecycle"),
        ("bounded-queue-contract", "thread-pool-contract"),
        ("future-state-lifecycle", "get-or-create-workbook"),
        ("condition-variable", "async-logger-workbook"),
        ("get-or-create-workbook", "async-logger-workbook"),
        ("async-logger-workbook", "callback-lock-order"),
    ],
    7: [
        ("learning-route", "request-mental-model"),
        ("layered-models", "encapsulation"),
        ("dns-resolution", "dns-records-workbook"),
        ("asio-timeouts-cancellation", "asio-client-workbook"),
        ("asio-client-workbook", "asio-coroutines"),
        ("tls-trust-crypto-operations", "tls-capture-workbook"),
        ("ip-addressing-routing", "cidr-routing-workbook"),
        ("tcp-stream-handshake", "tcp-sender-receiver-internals"),
        ("partial-io-eof", "framing-parsers"),
        ("readiness-nonblocking", "level-edge-triggered"),
        ("asio-coroutines", "asio-coroutine-session-design"),
        ("asio-coroutine-session-design", "beast-http-server"),
        ("production-incident-and-project-evidence", "networking-design-review"),
    ],
    8: [
        ("api-client-server", "rest-constraints"),
        ("task-contract", "replace-patch"),
        ("json-domain", "httplib-example"),
        ("lost-update", "conditional-update"),
        ("retry-uncertainty", "idempotency-state"),
        ("browser-origin", "cors-csrf"),
        ("session-token", "identity-lifecycle-workbook"),
        ("identity-lifecycle-workbook", "browser-origin"),
        ("openapi-contract", "openapi-operation-workbook"),
        ("protobuf-evolution", "grpc-call-workbook"),
        ("grpc-call-workbook", "rpc-choice-workbook"),
        ("compatibility", "versioning"),
        ("collection-filters", "batch-projection-workbook"),
        ("batch-projection-workbook", "versioning"),
        ("protobuf-evolution", "rpc-choice-workbook"),
        ("rpc-choice-workbook", "protobuf-file-workbook"),
        ("protobuf-file-workbook", "format-cost-workbook"),
        ("streaming-choice", "sse-reconnect"),
        ("contract-tests", "project-review"),
        ("idempotency-state", "retry-budget-workbook"),
        ("retry-budget-workbook", "atomic-service"),
        ("compatibility", "compatibility-rollout"),
        ("compatibility-rollout", "pagination"),
        ("websocket-contract", "event-recovery-workbook"),
        ("event-recovery-workbook", "webhooks"),
        ("project-review", "api-final-workbook"),
        ("api-final-workbook", "summary"),
    ],
    5: [
        ("headers-sources", "diagnose-build-stage"),
        ("diagnose-build-stage", "translation-units-odr"),
        ("cmake-basics", "cmake-configure-model"),
        ("cmake-configure-model", "cmake-libraries"),
        ("cmake-usage-requirements", "cmake-tests-install"),
        ("git-basics", "git-object-model"),
        ("git-object-model", "build-reproducibility"),
        ("linux-basics", "linux-process-model"),
        ("profiling-evidence", "diagnostic-cases-workbook"),
        ("diagnostic-cases-workbook", "profile-comparison-workbook"),
        ("linux-process-model", "diagnostic-ladder"),
        ("linux-processes-memory", "ipc-pipes-shared-memory"),
    ],
}


class LearningSequence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stations = {
            path.stem.removeprefix("station"): json.loads(path.read_text())
            for path in CONTENT.glob("station[0-9]*.json")
        }

    def test_prerequisite_order(self):
        for n, data in self.stations.items():
            positions = {s["id"]: i for i, s in enumerate(data["theory"])}
            if n == '5-linux':
                dependencies = [('linux-process-kernel-model','linux-syscall-contract'),
                    ('linux-fork-exec-wait','linux-fd-open-description'),
                    ('linux-fd-open-description','linux-dup-pipe-inheritance'),
                    ('linux-address-space','linux-mmap-sharing'),
                    ('linux-signal-model','linux-safe-signal-delivery'),
                    ('linux-service-observation','linux-process-final-workbook')]
            elif n in BEFORE:
                dependencies = BEFORE[n]
            else:
                dependencies = [('sql-first-query','sql-select-basics'),('sql-aggregate-basics','sql-cte-union'),('sql-cte-union','sql-window-rank')] if n == '9-sql' else BEFORE[int(n)]
            for prerequisite, dependent in dependencies:
                with self.subTest(station=n, prerequisite=prerequisite, dependent=dependent):
                    self.assertLess(positions[prerequisite], positions[dependent])

    def test_checkpoints_finish_modules(self):
        for n, data in self.stations.items():
            for module in data["substations"]:
                with self.subTest(station=n, module=module["id"]):
                    sections = [
                        s for s in data["theory"]
                        if s["substation"] == module["id"]
                    ]
                    checkpoints = [
                        (i, j) for i, s in enumerate(sections)
                        for j, b in enumerate(s["blocks"])
                        if b["type"] == "note"
                        and "Контрольная точка" in b.get("html", "")
                    ]
                    self.assertEqual(checkpoints, [
                        (len(sections) - 1, len(sections[-1]["blocks"]) - 1)
                    ])

    def test_route_first_summary_last(self):
        for n, data in self.stations.items():
            with self.subTest(station=n):
                self.assertEqual(data["theory"][0]["id"], "learning-route")
                if any(s["id"] == "summary" for s in data["theory"]):
                    self.assertEqual(data["theory"][-1]["id"], "summary")


if __name__ == "__main__":
    unittest.main()
