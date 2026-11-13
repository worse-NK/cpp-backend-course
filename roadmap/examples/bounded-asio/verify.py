#!/usr/bin/env python3
"""Own child process, loopback only; no remote target or firewall changes."""
import contextlib
from pathlib import Path
import select
import re
import signal
import socket
import struct
import subprocess
import sys
import time


@contextlib.contextmanager
def server(binary, budget=600):
    process = subprocess.Popen([str(binary), "0", str(budget)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        if not select.select([process.stdout], [], [], 5)[0]:
            raise AssertionError("server did not become ready")
        line = process.stdout.readline()
        assert line.startswith("ready "), line
        port = int(line.split()[1])
        report = {}
        yield port, process, report
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, (process.returncode, output, errors)
        assert not errors, errors
        assert "stopped active=0" in output, output
        summary = re.search(r"accepted=(\d+) finished=(\d+) rejected=(\d+) peak=(\d+)", output)
        assert summary and summary[1] == summary[2], output
        assert int(summary[4]) <= 16, output
        residents = re.search(r"resident=(\d+) peak_resident=(\d+)", output)
        assert residents and int(residents[1]) == 0 and int(residents[2]) <= 16, output
        report["output"] = output
        print(output.strip())


def connect(port, receive_buffer=None):
    stream = socket.socket()
    if receive_buffer:
        stream.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer)
    stream.settimeout(3)
    stream.connect(("127.0.0.1", port))
    return stream


def exact(stream, count):
    result = bytearray()
    while len(result) < count:
        part = stream.recv(count - len(result))
        if not part:
            raise AssertionError(("short response", len(result), count))
        result.extend(part)
    return bytes(result)


def closed(stream):
    try:
        assert stream.recv(1) == b""
    except ConnectionResetError:
        pass  # unread request bytes may cause an abortive TCP close


def main():
    binary = Path(sys.argv[1]).resolve()
    with server(binary) as (port, process, report):
        with connect(port) as stream:
            frame = struct.pack("!I", 5) + b"hello"
            # Deliberately split a frame, not a claim about real TCP segments.
            for part in (frame[:1], frame[1:3], frame[3:6], frame[6:]):
                stream.sendall(part)
            assert exact(stream, len(frame)) == frame
            closed(stream)
        for length in (0, 65537, 0xffffffff):
            with connect(port) as stream:
                stream.sendall(struct.pack("!I", length))
                closed(stream)
        with connect(port) as stream:
            stream.sendall(struct.pack("!I", 10) + b"xx")
            stream.shutdown(socket.SHUT_WR)
            closed(stream)
        with connect(port) as stream:
            stream.sendall(b"\0")
            closed(stream)  # the same overall deadline also bounds a partial header
        # Reader grants a small window, sends a large request, then does not read.
        with connect(port, receive_buffer=1024) as stream:
            frame = struct.pack("!I", 65536) + b"x" * 65536
            stream.sendall(frame)
            time.sleep(.9)
            # Timing is not proof of a blocked write; inspect the server outcome.
        assert process.poll() is None
    assert "finish deadline phase=write" in report["output"], report
    with server(binary, budget=3000) as (port, process, report):
        clients = [connect(port) for _ in range(20)]
        try:
            closed(clients[-1])  # admission limit rejects an excess connection
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=4)
        finally:
            for stream in clients:
                stream.close()
    assert "finish shutdown_limit" in report["output"], report
    rejected = re.search(r"rejected=(\d+)", report["output"])
    assert rejected and int(rejected[1]) > 0, report
    # Repeated close/cancel/accept churn must not free capacity prematurely.
    with server(binary) as (port, process, report):
        for _ in range(80):
            with connect(port) as stream:
                stream.sendall(struct.pack("!I", 0))
                closed(stream)
    print("PASS loopback protocol, limits, partial input, slow reader and shutdown")


if __name__ == "__main__":
    main()
