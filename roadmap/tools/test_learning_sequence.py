#!/usr/bin/env python3
"""Guard selected teaching dependencies, not the readability of prose."""
import json
import re
from pathlib import Path
import unittest

CONTENT = Path(__file__).resolve().parents[1] / "content"

# Only pedagogically important edges: unrelated sections may still move.
BEFORE = {
    16: [('failure-model', 'unknown-outcome'),
         ('operation-histories', 'consistency-contracts'),
         ('consistency-contracts', 'partitions-cap'),
         ('quorum-intersections', 'raft-log-commit'),
         ('raft-log-commit', 'raft-elections-reads'),
         ('logical-physical-clocks', 'leases-fencing'),
         ('sharding-key-design', 'shard-migration'),
         ('workflow-state-machine', 'workflow-recovery'),
         ('workflow-recovery', 'compensation-not-rollback'),
         ('coordination-choices', 'atomic-commit-boundaries'),
         ('atomic-commit-boundaries', 'distributed-final-workbook')],
    15: [('identity-session-jwt', 'identity-oauth-oidc'),
         ('frame-parser-contract', 'frame-parser-bounds-lifetime'),
         ('frame-parser-bounds-lifetime', 'endian-modernization-regression')],
    11: [('commands-events-jobs', 'queue-versus-log'),
         ('acknowledgement-boundaries', 'failure-windows-dedup'),
         ('kafka-topics-partitions-offsets', 'kafka-acks-isr'),
         ('kafka-consumer-positions', 'kafka-parallel-frontier'),
         ('rabbit-routing', 'rabbit-confirms-acks'),
         ('cpp-client-lifecycle', 'messaging-local-lab'),
         ('messaging-local-lab', 'kafka-replay-lab')],
    12: [('ttl-and-expiry', 'cache-contract'),
         ('cache-aside-read-write', 'cache-invalidation-race'),
         ('atomic-command-vs-sequence', 'multi-exec-errors'),
         ('multi-exec-errors', 'lua-server-logic'),
         ('rdb-aof-lifecycle', 'replica-ack-wait'),
         ('lease-vs-lock', 'fencing-resource-contract'),
         ('cpp-hiredis-ownership', 'redis-lab-guide'),
         ('cache-race-final-workbook', 'redis-design-review')],
    13: [('why-cluster', 'control-plane-and-node'),
         ('deployment-reading', 'rollout-budget'),
         ('service-and-endpoints', 'connection-lifetime'),
         ('probe-questions', 'termination-timeline'),
         ('termination-timeline', 'cpp-drain-contract'),
         ('filesystem-lifetimes', 'pv-pvc-storageclass'),
         ('resource-contract', 'hpa-loop'),
         ('cpp-drain-contract', 'lab-readiness-rollout')],
    14: [('request-boundaries', 'promql-rates'),
         ('metric-types', 'promql-rates'),
         ('histogram-buckets', 'promql-quantiles'),
         ('trace-tree', 'context-propagation'),
         ('cpp-instrumentation', 'lab-trace-path'),
         ('sli-slo', 'burn-rate'),
         ('burn-rate', 'alert-design'),
         ('lab-failures', 'incident-reasoning')],
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
        ("storage-and-construction", "object-representation-access"),
        ("object-representation-access", "representation-copy-bit-cast"),
        ("representation-copy-bit-cast", "shared-aliasing"),
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
        ("allocation-containers", "numeric-sizes-conversions"),
        ("numeric-sizes-conversions", "numeric-intermediate-narrowing"),
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
        ("template-compilation", "lookup-adl"),
        ("lookup-adl", "adl-customization"),
        ("sfinae-and-constraints", "parameter-packs-fold"),
        ("parameter-packs-fold", "callables-and-invoke"),
        ("templates-class", "template-specialization-choices"),
        ("chrono-types-units", "chrono-deadline-clock"),
        ("chrono-deadline-clock", "sliding-window-workbook"),
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
        ("loader-before-main", "global-initialization-order"),
        ("global-initialization-order", "global-lifetime-workbook"),
        ("global-lifetime-workbook", "abi-evolution"),
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
                    sections = [s for s in data["theory"]
                                if s["substation"] == module["id"]]
                    checkpoints = [
                        (i, j) for i, s in enumerate(sections)
                        for j, b in enumerate(s["blocks"])
                        if b["type"] == "note"
                        and "Контрольная точка" in b.get("html", "")
                    ]
                    # The shared reader separates station-level workbooks
                    # from ordinary chapter reading. A concluding note may
                    # close that chapter or the separate worked example, but
                    # must never interrupt ordinary theory or appear twice.
                    ordinary = [(i, s) for i, s in enumerate(sections)
                                if not re.search(r'(?:-final-workbook|clock-worked-example)$', s['id'])]
                    allowed = {(len(sections) - 1, len(sections[-1]["blocks"]) - 1)}
                    if ordinary:
                        i, last = ordinary[-1]
                        allowed.add((i, len(last["blocks"]) - 1))
                    self.assertEqual(len(checkpoints), 1)
                    self.assertIn(checkpoints[0], allowed)

    def test_route_first_summary_last(self):
        for n, data in self.stations.items():
            with self.subTest(station=n):
                self.assertEqual(data["theory"][0]["id"], "learning-route")
                if any(s["id"] == "summary" for s in data["theory"]):
                    self.assertEqual(data["theory"][-1]["id"], "summary")


if __name__ == "__main__":
    unittest.main()
