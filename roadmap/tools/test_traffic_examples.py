"""Independently parse generated PCAP bytes; never capture or contact a host."""
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

import build_traffic_examples


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "examples/traffic-analysis"
FILES = ("traffic_http_ok.pcap", "traffic_http_delay.pcap", "traffic_dns.pcap")


def valid_checksum(payload):
    # Separate implementation from the writer, including odd final bytes.
    accumulator = 0
    for offset in range(0, len(payload), 2):
        word = payload[offset] << 8
        if offset + 1 < len(payload):
            word |= payload[offset + 1]
        accumulator += word
        accumulator = (accumulator & 65535) + (accumulator >> 16)
    while accumulator > 65535:
        accumulator = (accumulator & 65535) + (accumulator >> 16)
    return accumulator == 65535


def read_capture(path):
    source = path.read_bytes()
    assert source[:4] == b"\xd4\xc3\xb2\xa1"
    major, minor, zone, accuracy, snaplen, network = struct.unpack_from("<HHIIII", source, 4)
    assert (major, minor, zone, accuracy, snaplen, network) == (2, 4, 0, 0, 65535, 1)
    offset, frames = 24, []
    while offset < len(source):
        seconds, microseconds, included, original = struct.unpack_from("<IIII", source, offset)
        offset += 16
        assert 0 <= microseconds < 1_000_000
        assert included == original and 60 <= included <= snaplen
        raw = source[offset:offset + included]
        assert len(raw) == included
        frames.append({"timestamp_us": seconds * 1_000_000 + microseconds, "raw": raw})
        offset += included
    assert offset == len(source)
    first = frames[0]["timestamp_us"]
    for frame in frames:
        frame["relative_us"] = frame["timestamp_us"] - first
    return frames


def layers(frame):
    ethernet = frame["raw"]
    assert ethernet[12:14] == b"\x08\x00"
    packet = ethernet[14:]
    ihl = (packet[0] & 15) * 4
    assert packet[0] >> 4 == 4 and ihl == 20
    total = int.from_bytes(packet[2:4], "big")
    assert total <= 1500 and total <= len(packet)
    assert packet[total:] == bytes(len(packet) - total)
    assert valid_checksum(packet[:ihl])
    assert int.from_bytes(packet[6:8], "big") == 0x4000
    assert packet[8] == 64
    source, destination = packet[12:16], packet[16:20]
    protocol = packet[9]
    segment = packet[ihl:total]
    pseudo = source + destination + bytes([0, protocol]) + len(segment).to_bytes(2, "big")
    assert valid_checksum(pseudo + segment)
    result = {"source": str(ipaddress.IPv4Address(source)),
              "destination": str(ipaddress.IPv4Address(destination)), "protocol": protocol,
              "sport": int.from_bytes(segment[:2], "big"), "dport": int.from_bytes(segment[2:4], "big"),
              "source_mac": ethernet[6:12], "destination_mac": ethernet[:6]}
    if protocol == 6:
        length = (segment[12] >> 4) * 4
        assert length == 20 and segment[12] & 15 == 0
        result.update(sequence=int.from_bytes(segment[4:8], "big"),
                      ack=int.from_bytes(segment[8:12], "big"), flags=segment[13], payload=segment[length:])
    else:
        assert protocol == 17
        assert int.from_bytes(segment[4:6], "big") == len(segment)
        assert segment[6:8] != b"\0\0"
        result["payload"] = segment[8:]
    return result


def dns_name(message, start, seen=None):
    seen = set() if seen is None else set(seen)
    assert start not in seen
    seen.add(start)
    labels, offset = [], start
    while True:
        size = message[offset]
        if size & 0xc0 == 0xc0:
            pointer = ((size & 63) << 8) | message[offset + 1]
            assert pointer < offset  # These fixtures use only backward compression.
            suffix, _ = dns_name(message, pointer, seen)
            return ".".join(labels + [suffix]), offset + 2
        assert size <= 63
        offset += 1
        if size == 0:
            return ".".join(labels), offset
        label = message[offset:offset + size]
        assert len(label) == size
        labels.append(label.decode("ascii"))
        offset += size


def dns_message(message):
    identifier, flags, questions, answers, authority, additional = struct.unpack_from("!6H", message)
    assert questions == 1 and additional == 0
    query, offset = dns_name(message, 12)
    qtype, qclass = struct.unpack_from("!HH", message, offset)
    assert (qtype, qclass) == (1, 1)
    offset += 4
    records = []
    for index in range(answers + authority):
        owner, offset = dns_name(message, offset)
        kind, category, ttl, length = struct.unpack_from("!HHIH", message, offset)
        assert category == 1
        offset += 10
        end = offset + length
        assert end <= len(message)
        if kind == 1:
            assert length == 4
            value = str(ipaddress.IPv4Address(message[offset:end]))
        else:
            assert kind == 6
            primary, next_offset = dns_name(message, offset)
            mailbox, next_offset = dns_name(message, next_offset)
            numbers = struct.unpack_from("!5I", message, next_offset)
            assert next_offset + 20 == end
            value = (primary, mailbox, *numbers)
        records.append({"owner": owner, "type": kind, "ttl": ttl, "value": value,
                        "section": "answer" if index < answers else "authority"})
        offset = end
    assert offset == len(message)
    return {"id": identifier, "flags": flags, "query": query, "answers": answers,
            "authority": authority, "records": records}


class SyntheticTrafficExamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / "manifest.json").read_text())

    def test_generated_files_are_byte_current_and_repeatable(self):
        first, second = build_traffic_examples.build(), build_traffic_examples.build()
        self.assertEqual(first, second)
        self.assertEqual(set(first), {*FILES, "manifest.json", "decoded.json", "README.txt"})
        for filename, expected in first.items():
            self.assertEqual((DATA / filename).read_bytes(), expected, filename)

    def test_writer_refuses_links_and_nonregular_files_without_touching_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "important.txt"
            target.write_bytes(b"keep")
            output = root / "outputs"
            output.mkdir()
            linked = output / "example.pcap"
            linked.symlink_to(target)
            with self.assertRaises(ValueError):
                build_traffic_examples.write_outputs(output, {"example.pcap": b"replace"})
            self.assertEqual(target.read_bytes(), b"keep")
            linked.unlink()
            os.link(target, linked)
            with self.assertRaises(ValueError):
                build_traffic_examples.write_outputs(output, {"example.pcap": b"replace"})
            self.assertEqual(target.read_bytes(), b"keep")
            linked.unlink()
            linked.mkdir()
            with self.assertRaises(ValueError):
                build_traffic_examples.write_outputs(output, {"example.pcap": b"replace"})
            with self.assertRaises(ValueError):
                build_traffic_examples.write_outputs(output, {"../important.txt": b"replace"})
            self.assertEqual(target.read_bytes(), b"keep")

    def test_pcap_and_every_ipv4_transport_checksum_length_are_valid(self):
        for filename in FILES:
            frames = read_capture(DATA / filename)
            self.assertEqual(len(frames), 4 if filename == "traffic_dns.pcap" else 11)
            self.assertEqual([f["relative_us"] for f in frames], sorted(f["relative_us"] for f in frames))
            for frame in frames:
                with self.subTest(filename=filename, time=frame["relative_us"]):
                    layers(frame)

    def test_all_addresses_are_documentation_or_locally_administered(self):
        network = ipaddress.IPv4Network("192.0.2.0/24")
        for filename in FILES:
            for frame in read_capture(DATA / filename):
                packet = layers(frame)
                self.assertIn(ipaddress.IPv4Address(packet["source"]), network)
                self.assertIn(ipaddress.IPv4Address(packet["destination"]), network)
                for key in ("source_mac", "destination_mac"):
                    self.assertEqual(packet[key][0] & 3, 2)  # locally administered, unicast.
                if packet["protocol"] == 17:
                    decoded = dns_message(packet["payload"])
                    self.assertTrue(decoded["query"].endswith(".test"))

    def test_tcp_handshake_stream_sequence_ack_and_both_fin_are_complete(self):
        for filename in FILES[:2]:
            packets = [layers(frame) for frame in read_capture(DATA / filename)]
            self.assertEqual([packet["flags"] for packet in packets],
                             [2, 18, 16, 24, 16, 24, 16, 17, 16, 17, 16])
            next_sequence = {"192.0.2.10": 1000, "192.0.2.20": 5000}
            for packet in packets:
                self.assertEqual(packet["sequence"], next_sequence[packet["source"]])
                if packet["flags"] & 16:
                    self.assertEqual(packet["ack"], next_sequence[packet["destination"]])
                next_sequence[packet["source"]] += (len(packet["payload"]) +
                    bool(packet["flags"] & 2) + bool(packet["flags"] & 1))
                self.assertEqual({packet["sport"], packet["dport"]}, {40000, 8080})
            self.assertEqual(next_sequence, {"192.0.2.10": 1064, "192.0.2.20": 5107})

    def test_http_framing_request_and_exact_json_content_length(self):
        for filename in FILES[:2]:
            packets = [layers(frame) for frame in read_capture(DATA / filename)]
            self.assertEqual([index + 1 for index, packet in enumerate(packets) if packet["payload"]], [4, 6])
            self.assertEqual(packets[3]["payload"],
                b"GET /health HTTP/1.1\r\nHost: course.test\r\nConnection: close\r\n\r\n")
            headers, body = packets[5]["payload"].split(b"\r\n\r\n", 1)
            lines = headers.decode("ascii").split("\r\n")
            self.assertEqual(lines[0], "HTTP/1.1 200 OK")
            fields = dict(line.split(": ", 1) for line in lines[1:])
            self.assertEqual(fields["Content-Type"], "application/json")
            self.assertEqual(int(fields["Content-Length"]), len(body))
            self.assertEqual(len(body), 15)
            self.assertEqual(json.loads(body), {"status": "ok"})
            self.assertEqual(len(packets[3]["payload"]), 62)
            self.assertEqual(len(packets[5]["payload"]), 105)

    def test_http_delay_changes_only_capture_times_not_network_bytes(self):
        quick, delayed = [read_capture(DATA / name) for name in FILES[:2]]
        self.assertEqual([f["raw"] for f in quick], [f["raw"] for f in delayed])
        self.assertEqual(quick[5]["relative_us"] - quick[3]["relative_us"], 50_000)
        self.assertEqual(delayed[5]["relative_us"] - delayed[3]["relative_us"], 500_000)
        for index, (a, b) in enumerate(zip(quick, delayed)):
            self.assertEqual(b["timestamp_us"] - a["timestamp_us"], 450_000 if index >= 5 else 0)

    def test_dns_transaction_pairing_a_and_nxdomain_negative_soa(self):
        frames = read_capture(DATA / FILES[2])
        packets = [layers(frame) for frame in frames]
        messages = [dns_message(packet["payload"]) for packet in packets]
        self.assertEqual([frame["relative_us"] for frame in frames], [0, 20_000, 100_000, 120_000])
        self.assertEqual([message["flags"] for message in messages], [0x0100, 0x8180, 0x0100, 0x8183])
        self.assertEqual([message["id"] for message in messages], [4660, 4660, 4661, 4661])
        self.assertEqual([(packet["sport"], packet["dport"]) for packet in packets],
                         [(53000, 53), (53, 53000), (53001, 53), (53, 53001)])
        self.assertEqual(messages[0]["query"], messages[1]["query"])
        self.assertEqual(messages[2]["query"], messages[3]["query"])
        self.assertEqual(messages[1]["records"], [{"owner": "api.course.test", "type": 1, "ttl": 300,
            "value": "192.0.2.20", "section": "answer"}])
        self.assertEqual((messages[3]["answers"], messages[3]["authority"]), (0, 1))
        self.assertEqual(messages[3]["records"], [{"owner": "course.test", "type": 6, "ttl": 60,
            "value": ("ns.course.test", "hostmaster.course.test", 1, 3600, 600, 86400, 60),
            "section": "authority"}])

    def test_manifest_matches_raw_facts_hashes_and_declares_synthetic_limits(self):
        self.assertIs(self.manifest["synthetic"], True)
        self.assertIs(self.manifest["captured_from_interface"], False)
        self.assertIs(self.manifest["privacy"]["no_real_hosts_or_credentials"], True)
        for filename in FILES:
            case = self.manifest["cases"][filename]
            self.assertEqual(hashlib.sha256((DATA / filename).read_bytes()).hexdigest(), case["sha256"])
            frames = read_capture(DATA / filename)
            self.assertEqual(case["file_bytes"], (DATA / filename).stat().st_size)
            self.assertEqual(case["frame_count"], len(frames))
            date = datetime.datetime.fromtimestamp(frames[0]["timestamp_us"] / 1_000_000, datetime.timezone.utc)
            self.assertEqual(date.isoformat(), "2026-01-01T00:00:00+00:00")
            for expected, frame in zip(case["frames"], frames):
                packet = layers(frame)
                self.assertEqual(expected["relative_us"], frame["relative_us"])
                self.assertEqual(expected["captured_bytes"], len(frame["raw"]))
                self.assertEqual(expected["source"], packet["source"])
                self.assertEqual(expected["source_port"], packet["sport"])
                if packet["protocol"] == 6:
                    self.assertEqual(expected["tcp_sequence_raw"], packet["sequence"])
                    self.assertEqual(expected["tcp_acknowledgement_raw"], packet["ack"])
                    self.assertEqual(expected["tcp_payload_bytes"], len(packet["payload"]))
        readme = (DATA / "README.txt").read_text()
        self.assertIn("НЕ ЗАХВАТ РЕАЛЬНОЙ СЕТИ", readme)
        self.assertIn("а не измерено", readme)
        self.assertIn("не отсутствие ответа", readme)
        decoded = json.loads((DATA / "decoded.json").read_text())
        self.assertIs(decoded["synthetic"], True)
        for filename, case in self.manifest["cases"].items():
            self.assertEqual(len(decoded["cases"][filename]), case["frame_count"])
            for simplified, detailed in zip(decoded["cases"][filename], case["frames"]):
                self.assertEqual(simplified["frame"], detailed["frame"])
                self.assertEqual(simplified["time_us"], detailed["relative_us"])
                self.assertEqual(simplified["time_ms"] * 1000, detailed["relative_us"])
                self.assertEqual(simplified["source"], f'{detailed["source"]}:{detailed["source_port"]}')
                self.assertTrue(simplified["summary"].strip())


if __name__ == "__main__":
    unittest.main()
