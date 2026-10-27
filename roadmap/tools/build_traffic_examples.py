#!/usr/bin/env python3
"""Build deterministic SYNTHETIC teaching PCAPs without sockets or capture tools.

All MAC/IP/name/application bytes below are invented examples. Timestamps are
assigned by this program, not measured. Only the six named generated outputs
are written; no interface, process, DNS server or remote host is contacted.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import struct


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "examples/traffic-analysis"
EPOCH = 1_767_225_600  # 2026-01-01T00:00:00Z, an arbitrary invented timestamp.
CLIENT_IP, SERVER_IP = "192.0.2.10", "192.0.2.20"
CLIENT_MAC, SERVER_MAC = bytes.fromhex("02000000000a"), bytes.fromhex("020000000014")
REQUEST = b"GET /health HTTP/1.1\r\nHost: course.test\r\nConnection: close\r\n\r\n"
BODY = b'{"status":"ok"}'
RESPONSE = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " +
            str(len(BODY)).encode("ascii") + b"\r\nConnection: close\r\n\r\n" + BODY)


def checksum(data):
    """Internet checksum: one's-complement sum of network-order 16-bit words."""
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!" + "H" * (len(data) // 2), data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def ip_bytes(address):
    return ipaddress.IPv4Address(address).packed


def ethernet_ipv4(source, destination, protocol, payload, identifier):
    header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), identifier,
                         0x4000, 64, protocol, 0, ip_bytes(source), ip_bytes(destination))
    header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
    source_mac, destination_mac = ((CLIENT_MAC, SERVER_MAC) if source == CLIENT_IP
                                   else (SERVER_MAC, CLIENT_MAC))
    frame = destination_mac + source_mac + b"\x08\x00" + header + payload
    # Ethernet padding belongs outside the IPv4 total_length. FCS is omitted,
    # as is common for saved Ethernet captures; frames are not truncated.
    return frame + b"\0" * max(0, 60 - len(frame))


def tcp(source, destination, sport, dport, sequence, acknowledgement, flags, payload=b""):
    header = struct.pack("!HHIIBBHHH", sport, dport, sequence, acknowledgement,
                         5 << 4, flags, 64240, 0, 0)
    pseudo = ip_bytes(source) + ip_bytes(destination) + struct.pack("!BBH", 0, 6, 20 + len(payload))
    value = checksum(pseudo + header + payload)
    return header[:16] + struct.pack("!H", value) + header[18:] + payload


def udp(source, destination, sport, dport, payload):
    length = 8 + len(payload)
    header = struct.pack("!HHHH", sport, dport, length, 0)
    pseudo = ip_bytes(source) + ip_bytes(destination) + struct.pack("!BBH", 0, 17, length)
    value = checksum(pseudo + header + payload) or 0xffff
    return struct.pack("!HHHH", sport, dport, length, value) + payload


def pcap(records):
    result = bytearray(struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    for relative_us, frame in records:
        seconds, micros = divmod(relative_us, 1_000_000)
        result.extend(struct.pack("<IIII", EPOCH + seconds, micros, len(frame), len(frame)))
        result.extend(frame)
    return bytes(result)


def http_case(delay_us):
    client_next, server_next = 1001 + len(REQUEST), 5001 + len(RESPONSE)
    response_time = 30_000 + delay_us
    definitions = [
        (0, True, 1000, 0, 0x02, b"", "TCP SYN"),
        (10_000, False, 5000, 1001, 0x12, b"", "TCP SYN, ACK"),
        (20_000, True, 1001, 5001, 0x10, b"", "TCP ACK: handshake complete"),
        (30_000, True, 1001, 5001, 0x18, REQUEST, "Complete HTTP GET /health"),
        (40_000, False, 5001, client_next, 0x10, b"", "TCP ACK of complete request"),
        (response_time, False, 5001, client_next, 0x18, RESPONSE, "Complete HTTP 200 + JSON body"),
        (response_time + 10_000, True, client_next, server_next, 0x10, b"", "TCP ACK of complete response"),
        (response_time + 20_000, False, server_next, client_next, 0x11, b"", "Server FIN, ACK"),
        (response_time + 30_000, True, client_next, server_next + 1, 0x10, b"", "Client ACK of server FIN"),
        (response_time + 40_000, True, client_next, server_next + 1, 0x11, b"", "Client FIN, ACK"),
        (response_time + 50_000, False, server_next + 1, client_next + 1, 0x10, b"", "Server final ACK"),
    ]
    records, decoded = [], []
    for number, (time_us, outgoing, sequence, acknowledgement, flags, data, event) in enumerate(definitions, 1):
        source, destination = (CLIENT_IP, SERVER_IP) if outgoing else (SERVER_IP, CLIENT_IP)
        sport, dport = (40000, 8080) if outgoing else (8080, 40000)
        segment = tcp(source, destination, sport, dport, sequence, acknowledgement, flags, data)
        frame = ethernet_ipv4(source, destination, 6, segment, number)
        records.append((time_us, frame))
        decoded.append({"frame": number, "relative_us": time_us, "event": event,
            "source": source, "source_port": sport, "destination": destination, "destination_port": dport,
            "layers": ["Ethernet II", "IPv4", "TCP"] + (["HTTP/1.1"] if data else []),
            "tcp_sequence_raw": sequence, "tcp_acknowledgement_raw": acknowledgement,
            "tcp_flags_hex": f"0x{flags:02x}", "tcp_payload_bytes": len(data), "captured_bytes": len(frame)})
    facts = {"tcp_streams": 1, "request_frame": 4, "response_frame": 6,
        "complete_request_time_us": 30_000, "response_time_us": response_time,
        "request_to_response_us": delay_us, "request_http_bytes": len(REQUEST),
        "response_http_bytes": len(RESPONSE), "response_content_length": len(BODY),
        "method": "GET", "path": "/health", "host": "course.test", "status": 200,
        "body": BODY.decode("ascii"), "transport_close": "Both FINs and their ACKs included",
        "time_interpretation": "Invented capture interval; not backend execution time, RTT or benchmark"}
    return records, decoded, facts


def name(domain):
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in domain.split(".")) + b"\0"


def dns_query(identifier, domain):
    return struct.pack("!6H", identifier, 0x0100, 1, 0, 0, 0) + name(domain) + struct.pack("!HH", 1, 1)


def dns_case():
    positive = dns_query(0x1234, "api.course.test")
    positive_answer = (struct.pack("!6H", 0x1234, 0x8180, 1, 1, 0, 0) + positive[12:] +
        b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 300, 4) + ip_bytes(SERVER_IP))
    negative = dns_query(0x1235, "missing.course.test")
    soa_data = (name("ns.course.test") + name("hostmaster.course.test") +
                struct.pack("!5I", 1, 3600, 600, 86400, 60))
    # In missing.course.test, offset20 starts the course label. The pointer
    # refers to earlier bytes inside this DNS message, not Ethernet/IP offsets.
    negative_answer = (struct.pack("!6H", 0x1235, 0x8183, 1, 0, 1, 0) + negative[12:] +
        b"\xc0\x14" + struct.pack("!HHIH", 6, 1, 60, len(soa_data)) + soa_data)
    definitions = [
        (0, True, 53000, positive, "Query A api.course.test", 0x1234, "api.course.test", None),
        (20_000, False, 53000, positive_answer, "A api.course.test -> 192.0.2.20", 0x1234, "api.course.test", 0),
        (100_000, True, 53001, negative, "Query A missing.course.test", 0x1235, "missing.course.test", None),
        (120_000, False, 53001, negative_answer, "NXDOMAIN missing.course.test + negative SOA", 0x1235, "missing.course.test", 3),
    ]
    records, decoded = [], []
    for number, (time_us, outgoing, client_port, message, event, identifier, domain, rcode) in enumerate(definitions, 1):
        source, destination = (CLIENT_IP, SERVER_IP) if outgoing else (SERVER_IP, CLIENT_IP)
        sport, dport = (client_port, 53) if outgoing else (53, client_port)
        datagram = udp(source, destination, sport, dport, message)
        frame = ethernet_ipv4(source, destination, 17, datagram, number)
        records.append((time_us, frame))
        decoded.append({"frame": number, "relative_us": time_us, "event": event,
            "source": source, "source_port": sport, "destination": destination, "destination_port": dport,
            "layers": ["Ethernet II", "IPv4", "UDP", "DNS"], "transaction_id": identifier,
            "query_name": domain, "query_type": "A", "response_code": rcode, "captured_bytes": len(frame)})
    return records, decoded, {"resolver": SERVER_IP + ":53", "query_response_us": [20_000, 20_000],
        "positive": {"transaction_id": 4660, "client_port": 53000, "name": "api.course.test",
                     "type": "A", "address": SERVER_IP, "ttl_seconds": 300},
        "negative": {"transaction_id": 4661, "client_port": 53001, "name": "missing.course.test",
            "rcode": 3, "meaning": "NXDOMAIN; not a connection timeout", "soa_owner": "course.test",
            "soa_mname": "ns.course.test", "soa_rname": "hostmaster.course.test",
            "soa_serial": 1, "soa_refresh": 3600, "soa_retry": 600, "soa_expire": 86400,
            "soa_ttl_seconds": 60, "soa_minimum_seconds": 60},
        "time_interpretation": "Invented query/response timestamps; not a measured resolver latency"}


def build():
    files, cases = {}, {}
    for filename, case in (("traffic_http_ok.pcap", http_case(50_000)),
                           ("traffic_http_delay.pcap", http_case(500_000)),
                           ("traffic_dns.pcap", dns_case())):
        records, decoded, facts = case
        content = pcap(records)
        files[filename] = content
        cases[filename] = {"sha256": hashlib.sha256(content).hexdigest(), "file_bytes": len(content),
                           "frame_count": len(records), "facts": facts, "frames": decoded}
    manifest = {"format_version": 1, "synthetic": True, "captured_from_interface": False,
        "generated_by": "roadmap/tools/build_traffic_examples.py (Python standard library)",
        "privacy": {"ipv4_documentation_range": "192.0.2.0/24", "domains": "Invented names below .test",
            "client_mac": "02:00:00:00:00:0a", "server_mac": "02:00:00:00:00:14",
            "no_real_hosts_or_credentials": True},
        "pcap": {"byte_order": "little-endian", "timestamp_unit": "microsecond", "linktype": 1,
            "linktype_name": "Ethernet", "snaplen": 65535, "fcs_included": False,
            "artificial_epoch_utc": "2026-01-01T00:00:00Z"},
        "assumptions": ["No socket, interface capture, host traffic or DNS lookup is performed",
            "Complete unfragmented IPv4 packets, valid IPv4/TCP/UDP checksums, Ethernet padding where needed",
            "One full TCP connection in each HTTP file; no TLS, packet loss, retransmissions or real performance claim",
            "HTTP files contain identical Ethernet frame bytes; only response-and-later capture times differ",
            "DNS file is independent of HTTP files; it does not prove a real application resolved its peer",
            "Decoder configuration and versions may change displayed names; raw packet semantics remain explicit"],
        "sources": ["https://www.wireshark.org/docs/wsug_html_chunked/ChIOOpenSection.html",
            "https://www.wireshark.org/docs/dfref/h/http.html", "https://www.wireshark.org/docs/dfref/d/dns.html"],
        "cases": cases}
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    http_summaries = ["Клиент начинает TCP-соединение: SYN.",
        "Сервер принимает начало соединения: SYN, ACK.", "Клиент подтверждает SYN сервера; согласование завершено.",
        "Клиент отправляет полный HTTP-запрос GET /health; полезная нагрузка TCP — 62 байта.",
        "TCP сервера подтверждает получение всех байтов запроса; это ещё не HTTP-ответ.",
        "Сервер отправляет полный HTTP 200 и JSON; Content-Length — 15 байт.",
        "TCP клиента подтверждает получение всех байтов ответа.",
        "Сервер сообщает, что больше не будет отправлять данные: FIN, ACK.",
        "Клиент подтверждает FIN сервера.", "Клиент также завершает своё направление передачи: FIN, ACK.",
        "Сервер подтверждает FIN клиента; обе стороны закрыли передачу."]
    dns_summaries = ["Клиент спрашивает A-запись api.course.test; ID запроса — 4660.",
        "DNS-сервер отвечает: A-запись api.course.test содержит 192.0.2.20, TTL — 300 секунд.",
        "Клиент спрашивает A-запись missing.course.test; ID запроса — 4661.",
        "DNS-сервер отвечает NXDOMAIN: имя не существует. В секции authority есть SOA course.test."]
    decoded = {"synthetic": True,
        "note": "Трасса создана программой. Время задано, а не измерено; это не захват реальной сети.", "cases": {}}
    for filename, case in cases.items():
        summaries = dns_summaries if filename == "traffic_dns.pcap" else http_summaries
        decoded["cases"][filename] = [{"frame": frame["frame"], "time_us": frame["relative_us"],
            "time_ms": frame["relative_us"] // 1000,
            "source": f'{frame["source"]}:{frame["source_port"]}',
            "destination": f'{frame["destination"]}:{frame["destination_port"]}',
            "protocol": frame["layers"][-1], "summary": summaries[frame["frame"] - 1]}
            for frame in case["frames"]]
    files["decoded.json"] = (json.dumps(decoded, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    lines = ["УЧЕБНЫЕ ПРИМЕРЫ WIRESHARK — СИНТЕТИКА, НЕ ЗАХВАТ РЕАЛЬНОЙ СЕТИ", "",
        "Все байты созданы программой на стандартном Python. Интерфейсы компьютера и DNS-серверы не использовались.",
        "Время задано автором примера, а не измерено. IP-адреса взяты из диапазона для документации, имена — из .test.",
        "MAC-адреса локально назначенные. В примерах нет паролей, токенов, пользовательских данных или реальных узлов.", "",
        "КАК ОТКРЫТЬ", "",
        "Скачай нужный .pcap и открой его в Wireshark: File → Open (Файл → Открыть).",
        "Запускать захват интерфейса для этого задания не нужно. Нужен уже установленный Wireshark; учебник его не устанавливает.",
        "Если используешь командный tshark, сначала перейди в папку со скачанными файлами:",
        "  tshark -n -r traffic_http_ok.pcap",
        "В полной копии репозитория эта папка — roadmap/examples/traffic-analysis; команда выполняется из неё.",
        "README и decoded.json позволяют проследить все события и без Wireshark. Manifest содержит точные поля и SHA-256 файлов.", "",
        "ЧТО ВНУТРИ HTTP-ПРИМЕРОВ", "",
        "Клиент 192.0.2.10:40000 обращается к 192.0.2.20:8080. В запросе: GET /health, Host: course.test.",
        'Ответ: HTTP/1.1 200, application/json, Content-Length: 15, тело {"status":"ok"}.',
        "В каждом файле одно полное TCP-соединение: начало, запрос, ответ и завершение обоих направлений через FIN/ACK.",
        "Байты кадров двух HTTP-файлов совпадают. Начиная с кадра 6 отличаются только временные отметки PCAP.",
        "Полный запрос находится в кадре 4 на отметке 30 мс. Полный ответ — в кадре 6 на 80 мс или 530 мс.",
        "Получаются интервалы 50 мс и 500 мс. Они НЕ доказывают время вычислений сервера, RTT сети или причину задержки.",
        "Начальные сырые TCP sequence numbers: 1000 у клиента и 5000 у сервера. SYN и каждый FIN занимают один номер.",
        "Пакеты содержат Ethernet/IPv4/TCP либо UDP. Контрольные суммы правильные, пакеты не обрезаны, FCS Ethernet не включён.", "",
        "ЧТО ВНУТРИ DNS-ПРИМЕРА", "",
        "DNS-сервер — 192.0.2.20:53. Клиент — 192.0.2.10, порты 53000 и 53001; ID запросов — 4660 и 4661.",
        "api.course.test получает A-запись 192.0.2.20 с TTL 300 секунд.",
        "missing.course.test получает законченный ответ NXDOMAIN. Это не отсутствие ответа и не HTTP-ошибка.",
        "Отрицательный ответ содержит SOA зоны course.test: ns.course.test / hostmaster.course.test.",
        "Поля SOA: serial 1, refresh 3600, retry 600, expire 86400, minimum 60 секунд; TTL самой записи — 60 секунд.",
        "Обе пары query/response разделены искусственными 20 мс. DNS-файл независим от HTTP-файлов.", ""]
    for filename, case in cases.items():
        lines += [filename, "SHA-256: " + case["sha256"],
                  "Кадр | Время от начала, мс | Источник → Получатель | Что произошло"]
        for frame in decoded["cases"][filename]:
            lines.append(f'{frame["frame"]:>4} | {frame["time_ms"]:>19} | '
                f'{frame["source"]} → {frame["destination"]} | {frame["summary"]}')
        lines.append("")
    lines += ["ФИЛЬТРЫ ОТОБРАЖЕНИЯ", "",
        "  tcp.stream == 0          Одно TCP-соединение в выбранном HTTP-файле.",
        "  http.request             Кадр с HTTP-запросом.",
        "  http.response            Кадр с HTTP-ответом.",
        "  dns                      DNS-запросы и ответы.",
        "  dns.flags.rcode == 3     Ответ NXDOMAIN.", "",
        "Для времени HTTP выбери кадр ответа 6. Имена и доступность полей зависят от версии декодера.",
        "Полное описание времён, длин, сырых sequence/ACK и ограничений находится в manifest.json.",
        "Эти примеры учат читать пакеты, но не проверяют настоящий DNS, TCP-стек, TLS, сетевую карту или сервер.",
        "Официальное руководство: https://www.wireshark.org/docs/wsug_html_chunked/ChIOOpenSection.html", ""]
    files["README.txt"] = ("\n".join(lines)).encode("utf-8")
    return files


def write_outputs(output_dir, files):
    """Replace only owned regular generated files, never links or devices."""
    output_dir.mkdir(parents=True, exist_ok=True)
    directory = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # Preflight the whole set before changing any existing output.
        for filename in files:
            if Path(filename).name != filename:
                raise ValueError("Generated output must be a plain filename")
            try:
                metadata = os.stat(filename, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or
                    metadata.st_uid != os.getuid()):
                raise ValueError("Refusing a linked, non-regular or non-owned output: " + filename)
        for filename, data in files.items():
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 0o644, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as destination:
                metadata = os.fstat(destination.fileno())
                if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or
                        metadata.st_uid != os.getuid()):
                    raise ValueError("Refusing an unsafe generated output: " + filename)
                destination.truncate(0)
                destination.write(data)
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DESTINATION)
    parser.add_argument("--check", action="store_true", help="Compare generated bytes without writing")
    args = parser.parse_args()
    files = build()
    if args.check:
        stale = [name for name, data in files.items()
                 if not (args.output_dir / name).is_file() or (args.output_dir / name).read_bytes() != data]
        if stale:
            raise SystemExit("Stale/missing synthetic examples: " + ", ".join(stale))
        print("PASS: six deterministic synthetic traffic files are current")
    else:
        write_outputs(args.output_dir, files)
        print("Built six synthetic traffic files; no network interface or socket used")


if __name__ == "__main__":
    main()
