#!/usr/bin/env python3
"""Run private netlab acceptance in an unprivileged, disconnected QEMU VM.

Only an existing build_netlab_vm.py directory directly below /tmp is accepted.
There are no guest disks, host directory shares, external NICs or monitor. The
serial transcript and machine-readable result stay in that temporary directory.
QEMU's exit status is NOT treated as proof of guest acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time


VERSION = "6.8.0-142-generic"
TIMEOUT_SECONDS = 300
BOOT_MARKER = "COURSE7_VM_BOOT:"
EXIT_MARKER = re.compile(r"^COURSE7_VM_EXIT=(-?\d+)\s*$")
PANIC_MARKER = re.compile(r"kernel panic|not syncing|^Oops:", re.IGNORECASE)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_paths(argument):
    directory = argument.resolve(strict=True)
    if (not directory.is_dir() or directory.parent != Path("/tmp")
            or not directory.name.startswith("cpp-course-netlab-vm-")):
        raise ValueError("Use an existing /tmp/cpp-course-netlab-vm-* directory")
    if directory.stat().st_uid != os.geteuid():
        raise ValueError("The temporary build directory must belong to your current UID")
    paths = {}
    for name, relative in (("kernel", f"kernel-package/boot/vmlinuz-{VERSION}"),
                           ("initramfs", "initramfs.cpio.gz")):
        path = (directory / relative).resolve(strict=True)
        if not path.is_relative_to(directory) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Expected a nonempty {name} file inside {directory}")
        paths[name] = path
    return directory, paths


def qemu_argv(executable, paths):
    # No caller-supplied extra QEMU options: these isolation properties are fixed.
    return [str(executable), "-no-user-config", "-nodefaults", "-machine", "pc",
            "-accel", "tcg", "-cpu", "max", "-m", "768", "-smp", "2",
            "-nic", "none", "-display", "none", "-serial", "stdio",
            "-monitor", "none", "-no-reboot", "-kernel", str(paths["kernel"]),
            "-initrd", str(paths["initramfs"]), "-append",
            "console=ttyS0 rdinit=/init course7_acceptance=1 panic=-1"]


def inspect_line(line, summary):
    line = line.strip()
    if line.startswith(BOOT_MARKER):
        summary["boot_markers"].append(line)
    marker = EXIT_MARKER.fullmatch(line)
    if marker:
        summary["guest_exit_codes"].append(int(marker[1]))
    if ("COURSE7_VM_MODULE_FAILURE" in line or "COURSE7_VM_MOUNT_FAILURE" in line
            or "COURSE7_VM_FAILURE" in line or PANIC_MARKER.search(line)
            or line.startswith(("Traceback (most recent call last):", "Fatal Python error:"))):
        summary["failure_markers"].append(line)
    if not line.startswith("{"):
        return
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return
    if not isinstance(record, dict):
        return
    event = record.get("event")
    if event == "acceptance-pass":
        summary["acceptance_pass"].append(record)
    elif event == "case-pass":
        summary["case_pass"].append(record)
    elif event == "environment":
        summary["environment"].append(record)
    elif isinstance(event, str) and event.endswith(("-fail", "-failure")):
        summary["failure_markers"].append(record)


def stream_guest(argv, transcript, summary):
    """Tee raw serial output live, with a wall-clock deadline even without output."""
    started = time.monotonic()
    process = None
    timed_out = False
    error = None
    pending = b""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            eof = False
            while not eof or process.poll() is None:
                remaining = TIMEOUT_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    process.kill()
                    break
                for key, _ in selector.select(min(0.25, remaining)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        eof = True
                        continue
                    transcript.write(chunk)
                    transcript.flush()
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        inspect_line(line.decode("utf-8", errors="replace"), summary)
            process.wait(timeout=5)
    except KeyboardInterrupt:
        error = "Interrupted by the user"
    except (OSError, subprocess.SubprocessError) as exception:
        error = repr(exception)
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    error = "QEMU did not exit after SIGKILL"
            process.stdout.close()
        if pending:
            inspect_line(pending.decode("utf-8", errors="replace"), summary)
    return {"qemu_returncode": process.returncode if process is not None else None,
            "timed_out": timed_out, "runner_error": error,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if os.geteuid() == 0 or os.getuid() == 0:
        print("Run as an ordinary user; this wrapper never needs root or sudo", file=sys.stderr)
        return 1
    try:
        directory, paths = build_paths(args.directory)
        executable = shutil.which("qemu-system-x86_64")
        if executable is None:
            raise ValueError("qemu-system-x86_64 is not installed; no VM was started")
        executable = Path(executable).resolve(strict=True)
        artifacts = {name: {"path": str(path), "sha256": sha256(path),
                            "size_bytes": path.stat().st_size} for name, path in paths.items()}
    except (OSError, ValueError) as error:
        print(f"No VM started: {error}", file=sys.stderr)
        return 1
    argv = qemu_argv(executable, paths)
    timestamp = datetime.now(timezone.utc)
    prefix = "acceptance-" + timestamp.strftime("%Y%m%dT%H%M%SZ") + "-"
    descriptor, filename = tempfile.mkstemp(prefix=prefix, suffix=".log", dir=directory)
    transcript_path = Path(filename)
    result_path = transcript_path.with_suffix(".json")
    summary = {"boot_markers": [], "guest_exit_codes": [], "acceptance_pass": [],
               "case_pass": [], "environment": [], "failure_markers": []}
    print(f"Transcript: {transcript_path}\nResult: {result_path}", flush=True)
    with os.fdopen(descriptor, "wb") as transcript:
        outcome = stream_guest(argv, transcript, summary)
    failures = []
    if outcome["timed_out"]:
        failures.append(f"QEMU exceeded the {TIMEOUT_SECONDS}-second deadline")
    if outcome["runner_error"]:
        failures.append(outcome["runner_error"])
    if outcome["qemu_returncode"] != 0:
        failures.append(f"QEMU exited with {outcome['qemu_returncode']}")
    if not summary["boot_markers"]:
        failures.append("Missing isolated guest boot marker")
    if len(summary["acceptance_pass"]) != 1:
        failures.append("Expected exactly one acceptance-pass JSON record")
    if summary["guest_exit_codes"] != [0]:
        failures.append("Expected exactly one COURSE7_VM_EXIT=0 marker")
    if summary["failure_markers"]:
        failures.append("Guest failure, module failure, traceback or kernel panic detected")
    for name, path in paths.items():
        try:
            if sha256(path) != artifacts[name]["sha256"]:
                failures.append(f"{name} changed during acceptance")
        except OSError as error:
            failures.append(f"Could not recheck {name}: {error}")
    result = {"passed": not failures, "failures": failures, "argv": argv,
              "started_utc": timestamp.isoformat(), "uid": os.geteuid(),
              "timeout_seconds": TIMEOUT_SECONDS, "artifacts": artifacts,
              "transcript": str(transcript_path), "summary": summary, **outcome}
    with result_path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("\nNETLAB_VM_ACCEPTANCE=" + ("PASS" if result["passed"] else "FAIL"), flush=True)
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
