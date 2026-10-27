#!/usr/bin/env python3
"""Real-kernel acceptance, runnable ONLY as a child of the test guest's PID 1.

No imports/calls to this module are needed by ordinary course unit tests.
The corresponding QEMU VM has no external NIC, disk or shared host directory.
"""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import re
import select
import socket
import struct
import subprocess
import sys
import time

NAMES = ("nl7-client", "nl7-peer", "nl7-router", "nl7-server")
IP4 = "198.51.100.10"
IP6 = "2001:db8:7:2::10"
CHILDREN = []
RECORDS = []


def guard(require_init_parent=True):
    if (os.geteuid() != 0 or (require_init_parent and os.getppid() != 1)
            or "course7_acceptance=1" not in Path("/proc/cmdline").read_text()):
        raise SystemExit("Refusing: this is not the dedicated course acceptance guest")


def log(kind, **values):
    print(json.dumps({"event": kind, **values}, ensure_ascii=False), flush=True)


def command(*args, expected=0, timeout=20):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    log("command", argv=args, rc=result.returncode,
        stdout=result.stdout, stderr=result.stderr)
    if result.returncode != expected:
        raise AssertionError((args, result.returncode, expected, result.stderr))
    return result


def start(*args):
    process = subprocess.Popen(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    CHILDREN.append(process)
    return process


def ready(process):
    readable, _, _ = select.select([process.stdout], [], [], 10)
    if not readable:
        raise AssertionError("No ready line from guest child")
    line = process.stdout.readline()
    if "ready" not in line:
        raise AssertionError(("Unexpected child startup", line, process.poll()))
    return line


def finish(process, stop=False):
    if stop and process.poll() is None:
        process.terminate()
    output, errors = process.communicate(timeout=12)
    CHILDREN.remove(process)
    return process.returncode, output, errors


def lab(action, expected=0):
    args = ["bash", "/course/network_lab.sh", action]
    if action in ("up", "down"):
        args.append("--inside-disposable-vm")
    return command(*args, expected=expected, timeout=40)


def reset():
    lab("down")
    lab("up")


def capture(namespace, interface):
    process = start("ip", "netns", "exec", namespace, "python3", "-u", __file__,
                    "capture", interface)
    ready(process)
    return process


def captured(process, where):
    code, text, errors = finish(process, stop=True)
    if code != -15 or errors:
        raise AssertionError(("Packet capture failed", where, code, errors))
    packets = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
    log("real-packet-capture", where=where, packets=packets, stderr=errors)
    RECORDS.extend(packets)
    return packets


def packet_fields(data):
    if len(data) < 14:
        return None
    ethertype = int.from_bytes(data[12:14], "big")
    if ethertype == 0x0800 and len(data) >= 42 and data[23] == 17:
        ip = data[14:]
        header = (ip[0] & 15) * 4
        if len(ip) < header + 8:
            return None
        source, destination = socket.inet_ntop(socket.AF_INET, ip[12:16]), socket.inet_ntop(socket.AF_INET, ip[16:20])
        hop, size, family = ip[8], int.from_bytes(ip[2:4], "big"), 4
    elif ethertype == 0x86DD and len(data) >= 62 and data[20] == 17:
        ip = data[14:]
        header = 40  # This experiment sends UDP without extension headers.
        source, destination = socket.inet_ntop(socket.AF_INET6, ip[8:24]), socket.inet_ntop(socket.AF_INET6, ip[24:40])
        hop, size, family = ip[7], 40 + int.from_bytes(ip[4:6], "big"), 6
    else:
        return None
    source_port, destination_port, length = struct.unpack("!HHH", ip[header:header + 6])
    if source_port not in (9000, 9001) and destination_port not in (9000, 9001):
        return None
    return {"family": family, "source": source, "destination": destination,
            "source_port": source_port, "destination_port": destination_port,
            "hop_limit_or_ttl": hop, "ip_size": size, "udp_size": length,
            "payload_hex": ip[header + 8:header + length].hex(),
            "ethernet_source": data[6:12].hex(":"), "ethernet_destination": data[:6].hex(":")}


def capture_loop(interface):
    # This role also runs only INSIDE the VM, entered by ip netns exec.
    if os.geteuid() != 0 or "course7_acceptance=1" not in Path("/proc/cmdline").read_text():
        raise SystemExit("Refusing packet capture outside acceptance guest")
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as stream:
        stream.bind((interface, 0))
        print("ready capture", flush=True)
        while True:
            fields = packet_fields(stream.recv(65535))
            if fields:
                print(json.dumps(fields), flush=True)


def probe(address, source_port, server_namespace="nl7-server", target=None,
          expected=0, capture_packets=False, client_namespace="nl7-client", port=9000):
    captures = []
    if capture_packets:
        captures = [("router:br-lan", capture("nl7-router", "br-lan")),
                    ("router:wan0", capture("nl7-router", "wan0"))]
    server = start("ip", "netns", "exec", server_namespace, "/course/udp_probe",
                   "server", address, str(port))
    startup = ready(server)
    client = command("ip", "netns", "exec", client_namespace, "/course/udp_probe",
                     "client", target or address, str(port), str(source_port),
                     expected=expected, timeout=12)
    code, output, errors = finish(server)
    log("probe-server", rc=code, stdout=startup + output, stderr=errors)
    if code != expected:
        raise AssertionError(("Server outcome differs", code, expected))
    if expected == 0 and "received course7:pong" not in client.stdout:
        raise AssertionError("Client did not receive the real response")
    packets = {where: captured(process, where) for where, process in captures}
    return startup + output, client.stdout, packets


def nft_file(name):
    filename = "/course/" + name + ".nft"
    command("ip", "netns", "exec", "nl7-router", "nft", "-c", "-f", filename)
    command("ip", "netns", "exec", "nl7-router", "nft", "-f", filename)


def counters():
    text = command("ip", "netns", "exec", "nl7-router", "nft", "-j", "list", "table", "inet", "course7").stdout
    return json.loads(text)


def pmtu_client():
    guard(require_init_parent=False)
    # Separate size experiment, NOT the fixed 12-byte UDP-probe protocol.
    with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as stream:
        stream.settimeout(3)
        stream.connect((IP6, 9002))
        stream.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_DONTFRAG, 1)
        stream.send(b"X" * 1400)  # 1448-byte IP packet, LAN1500 -> WAN1400.
        try:
            stream.recv(1)
            raise AssertionError("Oversized request unexpectedly received data")
        except OSError as error:
            if error.errno != errno.EMSGSIZE:
                raise
        # Linux UAPI <linux/in6.h>: Python does not export IPV6_MTU on every build.
        mtu = stream.getsockopt(socket.IPPROTO_IPV6, getattr(socket, "IPV6_MTU", 24))
        if mtu != 1400:
            raise AssertionError(("Unexpected learned PMTU", mtu))
        stream.send(b"X" * 1352)  # A NEW 1400-byte IP packet, not fragmentation.
        if stream.recv(8) != b"ok:1352":
            raise AssertionError("Reduced datagram response missing")
        log("real-ipv6-pmtu", mtu=mtu, rejected_payload=1400, new_payload=1352)


def pmtu_server():
    guard(require_init_parent=False)
    with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as stream:
        stream.bind((IP6, 9002))
        stream.settimeout(8)
        print("ready pmtu", flush=True)
        data, peer = stream.recvfrom(4096)
        if len(data) != 1352:
            raise AssertionError(("Oversized packet reached server", len(data)))
        stream.sendto(b"ok:1352", peer)
        log("real-ipv6-pmtu-server", payload=len(data))


def main():
    guard()
    log("environment", kernel=command("uname", "-r").stdout.strip(),
        nft=command("nft", "--version").stdout.strip(),
        ip=command("ip", "-Version").stdout.strip())
    # An absent external NIC is part of the VM's acceptance boundary.
    initial = json.loads(command("ip", "-j", "link", "show").stdout)
    if {link["ifname"] for link in initial} != {"lo"}:
        raise AssertionError("Guest has unexpected network devices")
    lab("help")
    lab("check")
    lab("status")
    try:
        lab("up")
        lab("status")
        expected = set(NAMES)
        actual = {item["name"] for item in json.loads(command("ip", "-j", "netns", "list").stdout)}
        if actual != expected:
            raise AssertionError((actual, expected))
        for ns in NAMES:
            command("ip", "-n", ns, "-d", "-j", "link", "show")
            command("ip", "-n", ns, "-j", "address", "show")
            command("ip", "-n", ns, "-4", "route", "show")
            command("ip", "-n", ns, "-6", "route", "show")
        probe("192.0.2.11", 41001, server_namespace="nl7-peer")
        probe("2001:db8:7:1::11", 41002, server_namespace="nl7-peer")
        server, _, path = probe(IP4, 41003, capture_packets=True)
        pre = [p for p in path["router:br-lan"] if p["source_port"] == 41003]
        post = [p for p in path["router:wan0"] if p["source_port"] == 41003]
        if not pre or not post or pre[0]["hop_limit_or_ttl"] != 64 or post[0]["hop_limit_or_ttl"] != 63:
            raise AssertionError("Observed route must decrease TTL from 64 to 63")
        if post[0]["ip_size"] != 40 or post[0]["udp_size"] != 20:
            raise AssertionError("12-byte protocol packet size mismatch")
        if pre[0]["ethernet_destination"] == post[0]["ethernet_destination"]:
            raise AssertionError("Router must use the next link's Ethernet destination")
        _, _, path6 = probe(IP6, 41004, capture_packets=True)
        pre6 = [p for p in path6["router:br-lan"] if p["source_port"] == 41004]
        post6 = [p for p in path6["router:wan0"] if p["source_port"] == 41004]
        if not pre6 or not post6 or pre6[0]["hop_limit_or_ttl"] != 64 or post6[0]["hop_limit_or_ttl"] != 63:
            raise AssertionError("IPv6 route must decrease Hop Limit from 64 to 63")
        if post6[0]["ip_size"] != 60 or post6[0]["udp_size"] != 20:
            raise AssertionError("IPv6 fixed protocol size mismatch")
        log("case-pass", case="baseline IPv4/IPv6, bridge and routed packet capture")

        for policy in ("filter", "block", "snat", "dnat", "trace"):
            reset()  # Fresh namespaces ALSO remove old conntrack bindings.
            nft_file(policy)
            if policy == "block":
                _, _, path = probe(IP4, 42001, expected=2, capture_packets=True)
                if not any(p["source_port"] == 42001 for p in path["router:br-lan"]):
                    raise AssertionError("Blocked request never reached router ingress")
                if any(p["source_port"] == 42001 for p in path["router:wan0"]):
                    raise AssertionError("Blocked request appeared on routed WAN")
                probe(IP6, 42002, expected=2)
            elif policy == "snat":
                server, _, path = probe(IP4, 43001, capture_packets=True)
                if "peer=198.51.100.1:43001" not in server:
                    raise AssertionError("Server did not observe SNAT source")
                if not any(p["source"] == "198.51.100.1" and p["source_port"] == 43001
                           for p in path["router:wan0"]):
                    raise AssertionError("Capture did not show translated source")
                probe(IP6, 43002)  # This file applies NAT to IPv4 only.
            elif policy == "dnat":
                server, client, path = probe(IP4, 44001, target="192.0.2.1", capture_packets=True)
                if "peer=192.0.2.1:9000" not in client or "peer=192.0.2.10:44001" not in server:
                    raise AssertionError("DNAT client/server endpoints mismatch")
                if not any(p["destination"] == IP4 and p["source_port"] == 44001
                           for p in path["router:wan0"]):
                    raise AssertionError("Capture did not show DNAT destination")
            elif policy == "trace":
                monitor = start("ip", "netns", "exec", "nl7-router", "nft", "monitor", "trace")
                time.sleep(0.25)
                probe(IP4, 45001)
                time.sleep(0.1)
                code, trace, errors = finish(monitor, stop=True)
                log("real-nft-trace", stdout=trace, stderr=errors)
                if (code != -15 or errors or
                        not re.search(r"(?m)^trace id \w+ inet course7 forward rule .*\(verdict accept\)", trace)):
                    raise AssertionError("Missing real forwarding trace")
            else:
                probe(IP4, 46001)
                probe(IP6, 46002)
                probe(IP4, 46003, expected=2, client_namespace="nl7-peer")
                probe(IP4, 46004, expected=2, port=9001)
            table = counters()
            total = sum(expr.get("counter", {}).get("packets", 0)
                        for row in table["nftables"] for expr in row.get("rule", {}).get("expr", []))
            if total < 1:
                raise AssertionError("No nft counter observed packets")
            log("case-pass", case=policy, counted_packets=total)

        reset()
        command("ip", "-n", "nl7-router", "link", "set", "wan0", "mtu", "1400")
        receiver = start("ip", "netns", "exec", "nl7-server", "python3", "-u", __file__, "pmtu-server")
        ready(receiver)
        command("ip", "netns", "exec", "nl7-client", "python3", "-u", __file__, "pmtu-client", timeout=12)
        code, output, errors = finish(receiver)
        log("pmtu-receiver", rc=code, stdout=output, stderr=errors)
        if code != 0:
            raise AssertionError("PMTU server failed")
        log("case-pass", case="real IPv6 PTB, PMTU and new reduced UDP datagram")

        resident = start("ip", "netns", "exec", "nl7-router", "sleep", "30")
        time.sleep(0.1)
        lab("down", expected=1)
        remaining = {item["name"] for item in json.loads(command("ip", "-j", "netns", "list").stdout)}
        if remaining != set(NAMES):
            raise AssertionError("Busy cleanup performed a partial deletion")
        finish(resident, stop=True)
        log("case-pass", case="cleanup refuses a resident process before deleting any namespace")
    finally:
        for child in list(CHILDREN):
            finish(child, stop=True)
        lab("down")
    if json.loads(command("ip", "-j", "netns", "list").stdout):
        raise AssertionError("Namespaces remain after down")
    if Path("/run/cpp-course-netlab7").exists():
        raise AssertionError("Ownership state remains after down")
    lab("down")  # Idempotent absent-state path.
    log("acceptance-pass", captures=len(RECORDS), external_network=False,
        cases=["baseline", "filter", "block", "snat", "dnat", "trace", "ipv6-pmtu", "busy-cleanup", "full-down"])


if __name__ == "__main__":
    if sys.argv[1:] == ["pmtu-client"]:
        pmtu_client()
    elif sys.argv[1:] == ["pmtu-server"]:
        pmtu_server()
    elif len(sys.argv) == 3 and sys.argv[1] == "capture":
        capture_loop(sys.argv[2])
    else:
        try:
            main()
        except Exception as error:
            log("acceptance-fail", error=repr(error))
            raise
