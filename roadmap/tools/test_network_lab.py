"""7Б: безопасные mock-проверки shell и ограниченный обмен ТОЛЬКО через loopback.

Настоящие ip/sysctl/nft, sudo и up/down исходного скрипта не запускаются.
Root-only ownership cases меняют только временные файлы, используя fake ip.
Отказ сетевой политики/отсутствующая IPv6 явно отмечаются как skip, не обходятся.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "roadmap/examples/station7-netlab"
SCRIPT = EXAMPLES / "network_lab.sh"
CPP = EXAMPLES / "udp_probe.cpp"
NAMES = ("nl7-client", "nl7-peer", "nl7-router", "nl7-server")
TOKEN = "12345678-1234-1234-1234-123456789abc"
ROOT_ONLY = unittest.skipUnless(os.geteuid() == 0, "ownership mocks require EUID 0 for root-owned state; no sudo")


class ShellNetworkLabTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="course7-shell-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.state = self.directory / "state"
        self.handles = self.directory / "netns"
        self.handles.mkdir()
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.log = self.directory / "calls.jsonl"
        self.scenario = self.directory / "scenario.json"
        self.scenario.write_text("{}", encoding="utf-8")
        self.copy = self.directory / "network_lab.sh"
        source = SCRIPT.read_text(encoding="utf-8")
        source, count_state = re.subn(r"(?m)^readonly STATE_DIR=.*$", "readonly STATE_DIR=" + shlex.quote(str(self.state)), source)
        source, count_netns = re.subn(r"(?m)^readonly NETNS_DIR=.*$", "readonly NETNS_DIR=" + shlex.quote(str(self.handles)), source)
        self.assertEqual((count_state, count_netns), (1, 1))
        self.copy.write_text(source, encoding="utf-8")
        # Чистый read-only JSON-verifier тестируется и без root, не обходя guards
        # настоящего up/down: ниже запускается только код с fake ip во временной папке.
        self.verifier = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        fake = "#!" + sys.executable + "\n" + r'''
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["COURSE7_TEST_LOG"], "a", encoding="utf-8") as out:
    out.write(json.dumps([tool, *args]) + "\n")
if tool != "ip":
    sys.exit("unexpected executable call: " + tool)
case = json.loads(pathlib.Path(os.environ["COURSE7_TEST_SCENARIO"]).read_text())
if len(args) == 3 and args[:2] == ["netns", "pids"]:
    print(case.get("pids", {}).get(args[2], ""), end="")
elif len(args) == 8 and args[0] == "-n" and args[2:5] == ["link", "set", "dev"] and args[6] == "alias":
    pass  # Only the extracted tag_topology function, no real network commands.
elif len(args) == 6 and args[:2] == ["-j", "-n"] and args[3:] == ["-d", "link", "show"]:
    print(json.dumps(case.get("links", {}).get(args[2], [])))
elif len(args) == 7 and args[:2] == ["-j", "-n"] and args[3:6] == ["netns", "list-id", "nsid"]:
    print(json.dumps(case.get("nsids", {}).get(args[2], {}).get(args[6], [])))
elif len(args) == 3 and args[:2] == ["netns", "delete"]:
    allowed = {"nl7-client", "nl7-peer", "nl7-router", "nl7-server"}
    if args[2] not in allowed:
        sys.exit("unknown deletion target")
    (pathlib.Path(os.environ["COURSE7_TEST_HANDLES"]) / args[2]).unlink()
else:
    sys.exit("unexpected fake ip arguments: " + repr(args))
'''
        for tool in ("ip", "sysctl", "nft"):
            target = self.bin / tool
            target.write_text(fake, encoding="utf-8")
            target.chmod(0o755)
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", os.defpath),
                                COURSE7_TEST_LOG=str(self.log), COURSE7_TEST_SCENARIO=str(self.scenario),
                                COURSE7_TEST_HANDLES=str(self.handles))

    def run_shell(self, *args):
        return subprocess.run(["bash", str(self.copy), *args], capture_output=True, text=True,
                              env=self.environment, timeout=5, check=False)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_inventory(self, ready=1, names=NAMES):
        return subprocess.run([sys.executable, "-c", self.verifier, TOKEN, str(ready), *names],
                              capture_output=True, text=True, env=self.environment, timeout=5)

    def state_fixture(self, names=NAMES):
        self.state.mkdir(mode=0o700)
        records = ["FORMAT 1", "TOKEN " + TOKEN]
        links, nsids = {}, {}
        for name in names:
            handle = self.handles / name
            handle.touch()
            info = handle.stat()
            records.append(f"NS {name} {info.st_dev}:{info.st_ino}")
            links[name] = [{"ifindex": 1, "ifname": "lo", "link_type": "loopback"}]
            nsids[name] = {}
        if "nl7-router" in names:
            links["nl7-router"].append({"ifindex": 2, "ifname": "br-lan", "ifalias": "cpp-course-netlab7:" + TOKEN,
                                        "linkinfo": {"info_kind": "bridge"}})
        for device, peer, router_index, router_nsid, peer_nsid in (
                ("lan-client", "nl7-client", 3, 0, 7), ("lan-peer", "nl7-peer", 4, 1, 9),
                ("wan0", "nl7-server", 5, 2, 3)):
            if "nl7-router" not in names or peer not in names:
                continue  # Законный partial setup до создания этой пары: нет обоих концов.
            for namespace, interface, index, peer_index, nsid, target in (
                    ("nl7-router", device, router_index, 2, router_nsid, peer),
                    (peer, "eth0", 2, router_index, peer_nsid, "nl7-router")):
                links[namespace].append({"ifindex": index, "ifname": interface, "ifalias": "cpp-course-netlab7:" + TOKEN,
                                         "linkinfo": {"info_kind": "veth"}, "link_index": peer_index,
                                         "link_netnsid": nsid})
                nsids[namespace][str(nsid)] = [{"nsid": nsid, "name": target}]
        if tuple(names) == NAMES:
            records.append("READY")
        self.manifest = self.state / "manifest"
        self.manifest.write_text("\n".join(records) + "\n", encoding="utf-8")
        self.manifest.chmod(0o600)
        lock = self.state / "lock"
        lock.touch(mode=0o600)
        scenario = {"links": links, "pids": {}, "nsids": nsids}
        self.scenario.write_text(json.dumps(scenario), encoding="utf-8")
        return scenario

    def assert_no_deletions(self):
        self.assertFalse(any(call[1:3] == ["netns", "delete"] for call in self.calls()), self.calls())

    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ownership_alias_is_explicitly_assigned_to_both_veth_ends(self):
        source = SCRIPT.read_text(encoding="utf-8")
        function = re.search(r"(?ms)^tag_topology\(\) \{\n.*?^\}", source).group()
        result = subprocess.run(["bash", "-c", function + '\ntag_topology "$1"', "test", "cpp-course-netlab7:" + TOKEN],
                                text=True, capture_output=True, env=self.environment, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = [("nl7-router", device) for device in ("br-lan", "lan-client", "lan-peer", "wan0")]
        expected += [(ns, "eth0") for ns in ("nl7-client", "nl7-peer", "nl7-server")]
        self.assertEqual(self.calls(), [["ip", "-n", ns, "link", "set", "dev", device, "alias", "cpp-course-netlab7:" + TOKEN]
                                       for ns, device in expected])
        self.assertIn('    tag_topology "$tag"', source)

    def test_help_check_and_status_are_read_only(self):
        for arguments in ((), ("help",), ("check",), ("check", "--inside-disposable-vm"), ("status",)):
            with self.subTest(arguments=arguments):
                result = self.run_shell(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout)
                self.assertFalse(self.state.exists())
                self.assertEqual(self.calls(), [])

    def test_mutations_require_explicit_confirmation_before_commands(self):
        for action in ("up", "down"):
            with self.subTest(action=action):
                result = self.run_shell(action)
                self.assertEqual(result.returncode, 1)
                self.assertIn("--inside-disposable-vm", result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.state.exists())

    def test_unknown_commands_and_options_are_rejected_before_commands(self):
        for args in (("unknown",), ("up", "--unsafe"), ("down", "--inside-disposable-vm", "extra"),
                     ("check", "--inside-disposable-vm", "--inside-disposable-vm")):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_shell(*args).returncode, 0)
                self.assertEqual(self.calls(), [])

    @unittest.skipIf(os.geteuid() == 0, "non-root guard is exercised on ordinary-user runs")
    def test_flag_does_not_replace_root_requirement(self):
        for action in ("up", "down"):
            result = self.run_shell(action, "--inside-disposable-vm")
            self.assertEqual(result.returncode, 1)
            self.assertIn("UID 0", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_mutation_boundaries_are_namespace_scoped(self):
        source = SCRIPT.read_text(encoding="utf-8")
        commands = [line.strip() for line in source.splitlines() if line.lstrip().startswith("ip ")]
        self.assertTrue(commands)
        for command in commands:
            self.assertTrue(command.startswith(("ip -n ", "ip netns ")), command)
        self.assertNotRegex(source, r"(?m)^\s*(?:sudo|sysctl|nft|kill|eval|source)\s")
        self.assertNotRegex(source, r"ip\s+(?:-all|-a)\s+netns|netns\s+(?:delete|del)\s+-all")
        self.assertIn("verify_cleanup_targets\n", source)
        self.assertLess(source.index("    verify_cleanup_targets\n"), source.index('            ip netns delete "$ns"'))

    def test_inventory_accepts_only_complete_pairs_in_partial_setup(self):
        scenario = self.state_fixture()
        self.assertEqual(self.run_inventory().returncode, 0)
        scenario["links"]["nl7-router"] = [row for row in scenario["links"]["nl7-router"] if row["ifname"] != "wan0"]
        scenario["links"]["nl7-server"] = [row for row in scenario["links"]["nl7-server"] if row["ifname"] != "eth0"]
        self.scenario.write_text(json.dumps(scenario))
        partial = self.run_inventory(ready=0)
        self.assertEqual(partial.returncode, 0, partial.stderr)
        self.assertEqual(self.run_inventory(ready=1).returncode, 1)
        self.assert_no_deletions()

    def test_inventory_missing_peer_refuses_ready_and_partial(self):
        scenario = self.state_fixture()
        scenario["links"]["nl7-server"] = [row for row in scenario["links"]["nl7-server"] if row["ifname"] != "eth0"]
        self.scenario.write_text(json.dumps(scenario))
        for ready in (0, 1):
            with self.subTest(ready=ready):
                result = self.run_inventory(ready=ready)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertRegex(result.stderr, "peer|интерфейс")
        self.assert_no_deletions()

    def test_inventory_external_peer_refuses_even_with_matching_local_indexes(self):
        scenario = self.state_fixture()
        # Все ifindex/link_index попарно совпадают, но peer NSID ведёт за пределы стенда.
        scenario["nsids"]["nl7-router"]["2"] = [{"nsid": 2, "name": "foreign-namespace"}]
        self.scenario.write_text(json.dumps(scenario))
        for ready in (0, 1):
            with self.subTest(ready=ready):
                result = self.run_inventory(ready=ready)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Внешний/unmapped peer", result.stderr)
        self.assert_no_deletions()

    def test_inventory_reverse_peer_and_reciprocal_index_are_required(self):
        scenario = self.state_fixture()
        scenario["nsids"]["nl7-server"]["3"] = [{"nsid": 3, "name": "nl7-peer"}]
        self.scenario.write_text(json.dumps(scenario))
        self.assertEqual(self.run_inventory().returncode, 1)
        scenario["nsids"]["nl7-server"]["3"] = [{"nsid": 3, "name": "nl7-router"}]
        scenario["links"]["nl7-server"][1]["link_index"] = 999
        self.scenario.write_text(json.dumps(scenario))
        result = self.run_inventory()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Не взаимная veth-пара", result.stderr)
        self.assert_no_deletions()

    def test_inventory_unknown_or_unmapped_nsid_refuses(self):
        scenario = self.state_fixture()
        for mapping in ([], [{"nsid": 2}], [{"nsid": 99, "name": "nl7-server"}],
                        {"unexpected": "format"}, [{"nsid": 2, "name": "nl7-server", "deleted": True}]):
            with self.subTest(mapping=mapping):
                scenario["nsids"]["nl7-router"]["2"] = mapping
                self.scenario.write_text(json.dumps(scenario))
                self.assertEqual(self.run_inventory().returncode, 1)
        self.assert_no_deletions()

    def test_inventory_ready_requires_all_owned_namespaces(self):
        self.state_fixture(("nl7-client",))
        self.assertEqual(self.run_inventory(ready=0, names=("nl7-client",)).returncode, 0)
        self.assertEqual(self.run_inventory(ready=1, names=("nl7-client",)).returncode, 1)
        self.assert_no_deletions()

    @ROOT_ONLY
    def test_owned_mock_cleanup_and_repeat(self):
        self.state_fixture()
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 0, result.stderr)
        deletions = [call[3] for call in self.calls() if call[1:3] == ["netns", "delete"]]
        self.assertEqual(deletions, ["nl7-client", "nl7-peer", "nl7-server", "nl7-router"])
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.handles.iterdir()), [])
        before = self.calls()
        self.assertEqual(self.run_shell("down", "--inside-disposable-vm").returncode, 0)
        self.assertEqual(self.calls(), before)

    @ROOT_ONLY
    def test_partial_owned_setup_can_be_cleaned(self):
        self.state_fixture(("nl7-client",))  # Нет READY и остальных namespace.
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.state.exists())

    @ROOT_ONLY
    def test_inode_mismatch_refuses_every_deletion(self):
        self.state_fixture()
        text = self.manifest.read_text()
        info = (self.handles / NAMES[0]).stat()
        self.manifest.write_text(text.replace(f"{info.st_dev}:{info.st_ino}", f"{info.st_dev}:{info.st_ino + 1000000}", 1))
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 1)
        self.assertIn("inode", result.stderr)
        self.assert_no_deletions()
        self.assertTrue(self.manifest.exists())

    @ROOT_ONLY
    def test_active_process_refuses_every_deletion_without_kill(self):
        scenario = self.state_fixture()
        scenario["pids"][NAMES[0]] = "424242\n"
        self.scenario.write_text(json.dumps(scenario))
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 1)
        self.assertIn("424242", result.stderr)
        self.assert_no_deletions()

    @ROOT_ONLY
    def test_last_namespace_unknown_link_refuses_all_deletions(self):
        scenario = self.state_fixture()
        scenario["links"][NAMES[-1]].append({"ifindex": 9, "ifname": "foreign0", "link_type": "ether"})
        self.scenario.write_text(json.dumps(scenario))
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 1)
        self.assertIn("foreign0", result.stderr)
        self.assert_no_deletions()
        self.assertEqual(len(list(self.handles.iterdir())), 4)

    @ROOT_ONLY
    def test_missing_alias_refuses_all_deletions(self):
        scenario = self.state_fixture()
        scenario["links"][NAMES[0]][1]["ifalias"] = "foreign-token"
        self.scenario.write_text(json.dumps(scenario))
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ownership", result.stderr)
        self.assert_no_deletions()

    @ROOT_ONLY
    def test_untracked_handle_and_corrupt_manifest_refuse(self):
        self.state_fixture(("nl7-client",))
        (self.handles / "nl7-peer").touch()
        result = self.run_shell("down", "--inside-disposable-vm")
        self.assertEqual(result.returncode, 1)
        self.assert_no_deletions()
        self.manifest.write_text("FORMAT 1\nTOKEN invalid\n")
        self.assertEqual(self.run_shell("down", "--inside-disposable-vm").returncode, 1)
        self.assert_no_deletions()


class UdpProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("g++ is unavailable; C++ compilation/runtime not verified")
        cls.temporary = tempfile.TemporaryDirectory(prefix="course7-udp-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.binaries = []
        for name, flags in (("debug", ["-O0", "-g"]), ("release", ["-O2", "-DNDEBUG"])):
            binary = cls.directory / name
            result = subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                                     *flags, str(CPP), "-o", str(binary)], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise AssertionError(f"{name} compilation failed:\n{result.stdout}{result.stderr}")
            cls.binaries.append(binary)
        cls.binary = cls.binaries[-1]

    def run_probe(self, *arguments, timeout=8):
        return subprocess.run([str(self.binary), *map(str, arguments)], capture_output=True,
                              text=True, timeout=timeout, check=False)

    def test_invalid_usage_before_socket(self):
        cases = [(), ("bad-mode", "127.0.0.1", "9000"), ("client", "example.com", "9000"),
                 ("server", "0.0.0.0", "9000"), ("server", "::", "9000"),
                 ("client", "[::1]", "9000"), ("client", "::ffff:127.0.0.1", "9000"),
                 ("client", "127.0.0.1", "0"), ("client", "::1", "65536"),
                 ("client", "::1", "+9000"), ("client", "::1", "-1"),
                 ("client", "::1", "9000x"), ("client", "::1", " 9000"),
                 ("client", "::1", "9000", "extra"), ("server", "::1", "9000", "9001"),
                 ("client", "::1", "9000", "0"), ("client", "::1", "9000", "65536")]
        for binary in self.binaries:
            for args in cases:
                with self.subTest(binary=binary.name, args=args):
                    result = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=2)
                    self.assertEqual(result.returncode, 64, result.stderr)
                    self.assertTrue(result.stderr)

    def own_socket(self, family):
        host = "127.0.0.1" if family == socket.AF_INET else "::1"
        try:
            endpoint = socket.socket(family, socket.SOCK_DGRAM)
            try:
                if family == socket.AF_INET6:
                    endpoint.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                endpoint.bind((host, 0))
            except BaseException:
                endpoint.close()
                raise
        except OSError as error:
            unavailable = {errno.EPERM, errno.EACCES, errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL}
            if isinstance(error, PermissionError) or error.errno in unavailable:
                self.skipTest(f"UDP loopback family={family} unavailable/denied: {error}; no escalation")
            raise
        return endpoint

    @staticmethod
    def stop_own_process(process):
        if process.poll() is None:
            process.terminate()  # Только Popen, созданный этим тестом, никогда поиск чужих PID.
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=1)

    def skip_denied_program(self, stderr):
        markers = ("Operation not permitted", "Permission denied", "Address family not supported", "Protocol not supported")
        if any(marker in stderr for marker in markers):
            self.skipTest(f"C++ UDP loopback denied/unsupported: {stderr.strip()}; no escalation")

    @contextlib.contextmanager
    def own_server(self, family=socket.AF_INET):
        # Порт выбирается UDP-bind(0), затем освобождается. Возможная гонка bind: две попытки.
        for attempt in range(2):
            with self.own_socket(family) as reservation:
                host, port = reservation.getsockname()[:2]
            process = subprocess.Popen([str(self.binary), "server", host, str(port)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                readable, _, _ = select.select([process.stdout], [], [], 2)
                self.assertTrue(readable, "own server readiness exceeded two seconds")
                ready = process.stdout.readline()
                if ready.startswith("ready local="):
                    try:
                        yield process, host, port, ready
                    finally:
                        self.stop_own_process(process)
                    return
                output, error = process.communicate(timeout=1)
                self.skip_denied_program(error)
                if "Address already in use" in error and attempt == 0:
                    continue
                self.fail(f"own server did not become ready: {ready}{output}{error}")
            finally:
                self.stop_own_process(process)
        self.fail("could not reserve own loopback UDP port after two attempts")

    def exchange(self, family):
        with self.own_server(family) as (server, host, port, ready):
            result = self.run_probe("client", host, port)
            self.skip_denied_program(result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("received course7:pong", result.stdout)
            self.assertIn("local=", result.stdout)
            self.assertIn("peer=", result.stdout)
            if family == socket.AF_INET6:
                self.assertIn("[::1]:", ready)
                self.assertIn("peer=[::1]:", result.stdout)
            output, error = server.communicate(timeout=2)
            self.assertEqual(server.returncode, 0, error)
            self.assertEqual(output.count("sent course7:pong"), 1)
            self.assertIn("peer=", output)

    def test_ipv4_one_shot_exchange(self):
        self.exchange(socket.AF_INET)

    def test_ipv6_one_shot_exchange(self):
        self.exchange(socket.AF_INET6)

    def test_explicit_client_source_port_is_observed(self):
        with self.own_server() as (server, host, port, _):
            with self.own_socket(socket.AF_INET) as reservation:
                source_port = reservation.getsockname()[1]
            result = self.run_probe("client", host, port, source_port)
            self.skip_denied_program(result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"local=127.0.0.1:{source_port} ", result.stdout)
            output, error = server.communicate(timeout=2)
            self.assertEqual(server.returncode, 0, error)
            self.assertIn(f"peer=127.0.0.1:{source_port}\n", output)

    def test_occupied_client_source_port_reports_bind_failure(self):
        with self.own_socket(socket.AF_INET) as peer, self.own_socket(socket.AF_INET) as occupied:
            host, port = peer.getsockname()
            source_port = occupied.getsockname()[1]
            result = self.run_probe("client", host, port, source_port)
            self.skip_denied_program(result.stderr)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("bind source port", result.stderr)
            self.assertIn("Address already in use", result.stderr)
            peer.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                peer.recvfrom(128)

    def test_server_rejects_empty_malformed_and_truncated_datagrams(self):
        for payload, message in ((b"", "empty or unexpected"), (b"wrong", "empty or unexpected"),
                                 (b"x" * 80, "truncated datagram")):
            with self.subTest(payload_size=len(payload)):
                with self.own_server() as (server, host, port, _):
                    with self.own_socket(socket.AF_INET) as sender:
                        sender.sendto(payload, (host, port))
                    _, error = server.communicate(timeout=2)
                    self.assertEqual(server.returncode, 1, error)
                    self.assertIn(message, error)

    def test_client_rejects_malformed_response_from_own_peer(self):
        with self.own_socket(socket.AF_INET) as peer:
            host, port = peer.getsockname()
            peer.settimeout(2)
            process = subprocess.Popen([str(self.binary), "client", host, str(port)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                try:
                    payload, address = peer.recvfrom(128)
                except TimeoutError:
                    if process.poll() is not None:
                        _, error = process.communicate(timeout=1)
                        self.skip_denied_program(error)
                        self.fail("own client exited without request: " + error)
                    self.fail("own client did not send its request within two seconds")
                self.assertEqual(payload, b"course7:ping")
                peer.sendto(b"not-course7:pong", address)
                _, error = process.communicate(timeout=2)
                self.assertEqual(process.returncode, 1, error)
                self.assertIn("unexpected datagram", error)
            finally:
                self.stop_own_process(process)

    def test_client_deadline_against_own_silent_bound_socket(self):
        # Сокет существует и принадлежит тесту: не шлём на произвольный чужой/закрытый порт.
        with self.own_socket(socket.AF_INET) as peer:
            host, port = peer.getsockname()
            start = time.monotonic()
            result = self.run_probe("client", host, port)
            elapsed = time.monotonic() - start
            self.skip_denied_program(result.stderr)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("timeout", result.stderr)
            self.assertGreaterEqual(elapsed, 4)
            self.assertLess(elapsed, 8)
            peer.settimeout(0.2)
            self.assertEqual(peer.recvfrom(128)[0], b"course7:ping")


if __name__ == "__main__":
    unittest.main()
