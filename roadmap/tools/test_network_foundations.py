"""Regression checks for station 7's introductory network/access examples.

These checks protect structure, examples, links and assessment mappings. They
do not establish that networking theory is correct or replace editorial review
against RFCs, OS manuals and the documentation of the relevant implementation.
No command shown by the course is executed and no network access is required.
"""

from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import shlex
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
NEW_SECTIONS = {
    "private-public-addresses": "network-layers",
    "dhcp-network-config": "network-layers",
    "inbound-access-cgnat": "remote-access",
    "vpn-network-context": "remote-access",
    "ssh-home-access": "remote-access",
    "network-diagnostics-basics": "remote-access",
    "network-access-workbook": "remote-access",
}

# Existing anchors are public reading/progress links, not disposable numbering.
LEGACY_IDS = """
learning-route request-mental-model url-to-service latency-round-trips
bytes-streams-messages backend-hop-chain request-debug-model
request-identities-and-addresses request-caches-and-reuse
request-time-and-failure-model layered-models encapsulation ethernet-neighbor
ip-addressing-routing nat-ports dns-resolution dns-records-workbook mtu-mss-path
wire-header-anatomy cidr-routing-workbook dns-routing-nat-worked-example
udp-semantics multicast-model tcp-stream-handshake tcp-loss-retransmission
flow-congestion-control tcp-close-states listen-queues-keepalive quic-overview
tcp-sender-receiver-internals tcp-capacity-loss-control udp-rtp-reliability
transport-production-failures socket-api-lifecycle address-resolution-bind
partial-io-eof framing-parsers blocking-server-concurrency socket-options-errors
multicast-socket-lab socket-interview-checklist posix-server-from-start-to-finish
stream-parser-engineering posix-io-correctness-and-performance concurrency-models
readiness-nonblocking select-poll-epoll level-edge-triggered reactor-state-machine
event-loop-buffers-backpressure timers-wakeup-io-uring epoll-kernel-contract
reactor-implementation-walkthrough fibers-coroutines-threads
event-loop-scaling-and-completion asio-mental-model asio-buffers-composed-ops
asio-executors-strands asio-session-lifetime asio-timeouts-cancellation
asio-client-workbook asio-coroutines asio-server-shutdown
asio-initiation-tokens-executors asio-coroutine-session-design
asio-cancellation-shutdown-proof http-semantics-versions http-methods-status-fields
http1-framing-persistence http2-multiplexing http3-quic tls13-handshake
certificates-sni-alpn beast-http-server http1-parser-and-semantics-deep
http2-http3-deep http-cookies tls-trust-crypto-operations tls-capture-workbook
timeout-taxonomy-retries slowloris-input-limits overload-backpressure
proxy-load-balancer container-networking network-observability
telemetry-gateway-project production-capacity-and-overload
production-proxy-container-topology production-incident-and-project-evidence
networking-design-review framing-final-workbook
""".split()

RFC1918 = tuple(map(ipaddress.IPv4Network, (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
)))
SHARED = ipaddress.IPv4Network("100.64.0.0/10")
IP_LITERAL = r"(?:\d{1,3}\.){3}\d{1,3}"
CIDR = re.compile(rf"(?<![\d.]){IP_LITERAL}/\d{{1,2}}\b")
RANGE = re.compile(rf"({IP_LITERAL})\s*[–—-]\s*({IP_LITERAL})")
PRIMARY_DOMAINS = {
    "www.rfc-editor.org", "rfc-editor.org", "datatracker.ietf.org",
    "www.iana.org", "iana.org", "man7.org", "man.openbsd.org",
    "www.wireguard.com", "wireguard.com", "tailscale.com",
}


def strings_for(value, key):
    """Yield only a selected field, including nested diagrams/exchanges."""
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from strings_for(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from strings_for(child, key)


def text_of(value):
    return unescape(re.sub(r"<[^>]*>", " ", value))


class ProseParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == "a":
            self.links.append(dict(attrs).get("href"))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"Unexpected closing tag: {tag}; stack={self.stack}")
        else:
            self.stack.pop()


def ssh_destination(words):
    """Parse the deliberately small SSH client syntax taught in these blocks."""
    if not words or words[0] != "ssh":
        raise ValueError("Expected an SSH client command")
    port, destination, index = 22, None, 1
    while index < len(words):
        word = words[index]
        if word == "-v":
            index += 1
        elif word == "-p":
            port = int(words[index + 1])
            index += 2
        elif word == "-o":
            option = words[index + 1]
            if not re.fullmatch(r"ConnectTimeout=[1-9]\d*", option):
                raise ValueError(f"Unexpected SSH option: {option}")
            index += 2
        elif destination is None and not word.startswith("-"):
            destination = word
            index += 1
        else:
            raise ValueError(f"Unexpected argument or remote command: {word}")
    if destination is None or destination.count("@") != 1:
        raise ValueError("Expected explicit user@host")
    user, host = destination.split("@")
    if not re.fullmatch(r"[a-z_][a-z0-9_.-]*", user) or not 1 <= port <= 65535:
        raise ValueError("Invalid example user or TCP port")
    return user, host, port


class NetworkFoundations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.station = json.loads((ROOT / "content/station7.json").read_text())
        cls.sections = {section["id"]: section for section in cls.station["theory"]}
        cls.questions = [
            (kind, question)
            for kind, questions in cls.station["quizzes"].items()
            for question in questions
            if set(question.get("theoryRefs", ())) & NEW_SECTIONS.keys()
        ]
        cls.tasks = [task for task in cls.station["tasks"]
                     if task.get("substation") == "remote-access"]

    def test_section_schema_and_existing_anchor_order(self):
        ids = [section["id"] for section in self.station["theory"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(LEGACY_IDS).issubset(ids))
        self.assertEqual([sid for sid in ids if sid in LEGACY_IDS], LEGACY_IDS)
        for sid, group in NEW_SECTIONS.items():
            with self.subTest(section=sid):
                section = self.sections[sid]
                self.assertEqual(section["substation"], group)
                self.assertTrue(section["title"].strip())
                self.assertTrue(section["lead"].strip())
                self.assertIsInstance(section["blocks"], list)
                self.assertTrue(section["blocks"])

    def test_prerequisites_and_remote_access_group_order(self):
        groups = [group["id"] for group in self.station["substations"]]
        self.assertLess(groups.index("network-layers"), groups.index("remote-access"))
        self.assertLess(groups.index("remote-access"), groups.index("transport"))
        ids = [section["id"] for section in self.station["theory"]]
        for before, after in (
            ("private-public-addresses", "ip-addressing-routing"),
            ("ip-addressing-routing", "dhcp-network-config"),
            ("dhcp-network-config", "nat-ports"),
            ("nat-ports", "inbound-access-cgnat"),
            ("inbound-access-cgnat", "vpn-network-context"),
            ("vpn-network-context", "ssh-home-access"),
            ("ssh-home-access", "network-diagnostics-basics"),
            ("network-diagnostics-basics", "network-access-workbook"),
            ("network-access-workbook", "udp-semantics"),
        ):
            with self.subTest(before=before, after=after):
                self.assertLess(ids.index(before), ids.index(after))

    def test_new_prose_has_balanced_html_and_primary_https_sources(self):
        for sid in NEW_SECTIONS:
            sources = []
            for fragment in strings_for(self.sections[sid], "html"):
                with self.subTest(section=sid, fragment=fragment[:80]):
                    parser = ProseParser()
                    parser.feed(fragment)
                    parser.close()
                    self.assertEqual(parser.errors, [])
                    self.assertEqual(parser.stack, [])
                    for link in parser.links:
                        self.assertIsNotNone(link)
                        self.assertNotRegex(link, r"[\s\\\"<>]")
                        parts = urlsplit(link)
                        if parts.scheme or parts.netloc:
                            self.assertEqual(parts.scheme, "https")
                            self.assertIn(parts.hostname, PRIMARY_DOMAINS)
                            sources.append(link)
                        elif not link.startswith("#"):
                            self.assertTrue((ROOT / parts.path).is_file(), link)
            with self.subTest(section=sid):
                self.assertTrue(sources, "Each new section needs primary source links")

    def test_all_new_sections_have_questions_and_practice_references(self):
        assessed = {ref for _, question in self.questions for ref in question["theoryRefs"]}
        practiced = {ref for task in self.tasks for ref in task["theoryRefs"]}
        self.assertGreaterEqual(len(self.questions), 26)
        self.assertTrue(NEW_SECTIONS.keys() <= assessed, NEW_SECTIONS.keys() - assessed)
        self.assertTrue(NEW_SECTIONS.keys() <= practiced, NEW_SECTIONS.keys() - practiced)
        for kind, question in self.questions:
            with self.subTest(kind=kind, question=question["q"]):
                self.assertIn(kind, {"basic", "advanced", "interview"})
                self.assertTrue(question["q"].strip())
                self.assertGreaterEqual(len(question["options"]), 3)
                self.assertEqual(len(question["options"]), len(set(question["options"])))
                self.assertIs(type(question["answer"]), int)
                self.assertTrue(0 <= question["answer"] < len(question["options"]))
                self.assertTrue(question["why"].strip())
                self.assertTrue(set(question["theoryRefs"]) <= self.sections.keys())

    def test_practice_is_an_open_lab_not_another_mcq(self):
        self.assertGreaterEqual(len(self.tasks), 3)
        for task in self.tasks:
            with self.subTest(task=task["title"]):
                self.assertEqual(task["level"], "Практика")
                self.assertTrue(task["title"].startswith("Лаборатория:"))
                self.assertEqual(task["solutionFormat"], "text")
                self.assertTrue(task["brief"].strip())
                self.assertTrue(task["solution"].strip())
                self.assertGreaterEqual(len(task["checks"]), 3)
                self.assertTrue(task["hints"])
                self.assertTrue(set(task["theoryRefs"]) <= self.sections.keys())
                self.assertNotIn("options", task)
                self.assertNotIn("answer", task)

    def test_rfc1918_question_answer_is_exactly_the_three_networks(self):
        matches = [q for _, q in self.questions
                   if "RFC 1918" in q["q"] and "три диапазона" in q["q"]]
        self.assertEqual(len(matches), 1)
        question = matches[0]
        for index, option in enumerate(question["options"]):
            networks = {ipaddress.IPv4Network(value) for value in CIDR.findall(option)}
            self.assertEqual(networks == set(RFC1918), index == question["answer"])

    def test_teaching_range_endpoints_and_border_examples(self):
        private = " ".join(strings_for(self.sections["private-public-addresses"], "title"))
        pairs = {(ipaddress.IPv4Address(first), ipaddress.IPv4Address(last))
                 for first, last in RANGE.findall(private)}
        for network in RFC1918:
            self.assertIn((network.network_address, network.broadcast_address), pairs)
        self.assertIn(ipaddress.IPv4Address("172.19.115.180"), RFC1918[1])
        self.assertNotIn(ipaddress.IPv4Address("172.40.1.2"), RFC1918[1])
        for network in RFC1918:
            self.assertNotIn(network.network_address - 1, network)
            self.assertNotIn(network.broadcast_address + 1, network)
        prose = " ".join(strings_for(self.sections["inbound-access-cgnat"], "html"))
        shared_pairs = {(ipaddress.IPv4Address(first), ipaddress.IPv4Address(last))
                        for first, last in RANGE.findall(text_of(prose))}
        self.assertIn((SHARED.network_address, SHARED.broadcast_address), shared_pairs)
        self.assertIn(ipaddress.IPv4Address("100.72.8.9"), SHARED)
        self.assertNotIn(ipaddress.IPv4Address("100.128.0.0"), SHARED)
        self.assertFalse(any(SHARED.overlaps(network) for network in RFC1918))

    def test_shared_address_question_uses_exact_range(self):
        matches = [q for _, q in self.questions if "RFC 6598" in q["q"]]
        self.assertEqual(len(matches), 1)
        question = matches[0]
        option = question["options"][question["answer"]]
        self.assertEqual({ipaddress.IPv4Network(value) for value in CIDR.findall(option)},
                         {SHARED})
        self.assertEqual([(ipaddress.IPv4Address(a), ipaddress.IPv4Address(b))
                          for a, b in RANGE.findall(option)],
                         [(SHARED.network_address, SHARED.broadcast_address)])

    def test_overlapping_vpn_route_example_by_longest_prefix(self):
        matches = [q for _, q in self.questions
                   if q["q"].startswith("В выбранной IPv4-таблице")]
        self.assertEqual(len(matches), 1)
        question = matches[0]
        networks = [ipaddress.IPv4Network(value) for value in CIDR.findall(question["q"])]
        destination = ipaddress.IPv4Address("192.168.1.10")
        winner = max((network for network in networks if destination in network),
                     key=lambda network: network.prefixlen)
        self.assertEqual(winner, ipaddress.IPv4Network("192.168.1.0/24"))
        correct = question["options"][question["answer"]]
        self.assertIn(f"/{winner.prefixlen}", correct)
        self.assertIn("домашн", correct)

    def test_ssh_commands_keep_user_host_and_port_separate(self):
        examples = set()
        for sid in NEW_SECTIONS:
            for code in strings_for(self.sections[sid], "code"):
                for line in code.splitlines():
                    words = shlex.split(line, comments=True)
                    if words and words[0] == "ssh":
                        examples.add(ssh_destination(words))
        self.assertEqual(examples, {
            ("nikita", "172.19.115.180", 22),
            ("nikita", "home.example", 22),
            ("nikita", "home.example", 2222),
        })
        matches = [q for _, q in self.questions if q["q"].startswith("Что задаёт команда ssh ")]
        self.assertEqual(len(matches), 1)
        question = matches[0]
        command = question["q"].removeprefix("Что задаёт команда ").removesuffix("?")
        user, host, port = ssh_destination(shlex.split(command))
        correct = question["options"][question["answer"]]
        self.assertIn(f"Пользователь {user}", correct)
        self.assertIn(f"узел {host}", correct)
        self.assertIn(f"TCP-порт {port}", correct)

    def test_code_is_limited_to_inspection_and_documented_ssh_clients(self):
        # Check executable examples, not prose/distractors warning about bad actions.
        allowed_inspections = {
            ("ip", "-br", "address"), ("ip", "route", "show"),
            ("ip", "route", "get", "172.19.115.180"),
            ("resolvectl", "status"), ("ss", "-ltn"),
        }
        for sid in NEW_SECTIONS:
            for code in strings_for(self.sections[sid], "code"):
                for line in code.splitlines():
                    words = shlex.split(line, comments=True)
                    if not words:
                        continue
                    with self.subTest(section=sid, command=line):
                        if words[0] == "ssh":
                            _, host, _ = ssh_destination(words)
                            self.assertIn(host, {"172.19.115.180", "home.example"})
                        else:
                            self.assertIn(tuple(words), allowed_inspections)

    def test_no_embedded_private_key_material_in_the_added_content(self):
        # Concrete private-key delimiters, not an overbroad "secret" word scan.
        added = [self.sections[sid] for sid in NEW_SECTIONS]
        added += [question for _, question in self.questions] + self.tasks
        serialized = json.dumps(added, ensure_ascii=False)
        for marker in (
            "-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN ENCRYPTED PRIVATE KEY-----",
        ):
            self.assertNotIn(marker, serialized)


if __name__ == "__main__":
    unittest.main()
