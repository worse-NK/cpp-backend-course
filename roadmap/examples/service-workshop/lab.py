#!/usr/bin/env python3
"""Small Linux/Python 3 workshop helper. Never runs Docker, SSH, or a shell."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
SECRET_NAMES = ("APP_TOKEN", "POSTGRES_PASSWORD", "APP_DB_PASSWORD")
HEX_SECRET = re.compile(r"[0-9a-f]{64}\Z")
ARCHIVE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz\Z")
# Explicit source allowlist. No recursive directory walk and no user-selected
# source paths: adding a new source file requires a deliberate code change.
SOURCE_FILES = (
    "CMakeLists.txt", "app.cpp", "storage.hpp", "storage.cpp", "tests.cpp",
    "schema.sql", "Dockerfile", "compose.yaml",
    "compose.https.yaml", "Caddyfile", "init-db.sh", "lab.py", "README.md",
    ".dockerignore", ".gitignore",
)


class LabError(Exception):
    """A safe diagnostic containing no secret values."""


def open_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def open_regular_at(directory: int, name: str, *, private: bool = False) -> int:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise LabError(f"{name}: expected a regular file, not a link or device")
    if private and (metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_nlink != 1):
        os.close(descriptor)
        raise LabError(f"{name}: expected an owned, single-link 0600 private file")
    return descriptor


def assert_absent_at(directory: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise LabError(f"{name} already exists; nothing will be overwritten")


def write_exclusive_at(directory: int, name: str, content: str) -> None:
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def init_secrets(root: Path = ROOT) -> None:
    with ExitStack() as stack:
        root_fd = open_directory(root)
        stack.callback(os.close, root_fd)
        assert_absent_at(root_fd, ".env")
        try:
            metadata = os.stat(".secrets", dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.mkdir(".secrets", 0o700, dir_fd=root_fd)
        else:
            if (not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o700):
                raise LabError(".secrets must be an owned 0700 directory, not a link")
        secrets_fd = os.open(".secrets", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=root_fd)
        stack.callback(os.close, secrets_fd)
        assert_absent_at(secrets_fd, "client.curl")
        values = {name: secrets.token_hex(32) for name in SECRET_NAMES}
        env_text = "".join(f"{name}={values[name]}\n" for name in SECRET_NAMES)
        curl_text = (
            f'header = "Authorization: Bearer {values["APP_TOKEN"]}"\n'
            'noproxy = "127.0.0.1,localhost,::1"\n'
            "connect-timeout = 2\n"
            "max-time = 5\n"
            "fail-with-body\n"
            "silent\n"
            "show-error\n"
        )
        write_exclusive_at(root_fd, ".env", env_text)
        write_exclusive_at(secrets_fd, "client.curl", curl_text)


def read_env(root: Path = ROOT) -> dict[str, str]:
    with ExitStack() as stack:
        root_fd = open_directory(root)
        stack.callback(os.close, root_fd)
        env_fd = open_regular_at(root_fd, ".env", private=True)
        with os.fdopen(env_fd, "r", encoding="ascii") as source:
            text = source.read(4097)
    if len(text) > 4096:
        raise LabError(".env is too large")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if (not separator or name not in SECRET_NAMES or name in values
                or not HEX_SECRET.fullmatch(value)):
            raise LabError(".env must contain each expected name once, with 64 hex characters")
        values[name] = value
    if set(values) != set(SECRET_NAMES):
        raise LabError(".env is incomplete: run init in a fresh workshop copy")
    return values


def check_environment(root: Path = ROOT) -> int:
    try:
        values = read_env(root)
    except FileNotFoundError:
        for name in SECRET_NAMES:
            print(f"{name}: absent")
        return 1
    for name in SECRET_NAMES:
        print(f"{name}: {'present' if name in values else 'absent'}")
    return 0


def run_native(root: Path = ROOT, port: int = 8080) -> int:
    values = read_env(root)
    binary = root / "build" / "course_tasks"
    if (binary.is_symlink() or binary.parent.is_symlink()
            or not binary.is_file() or not os.access(binary, os.X_OK)):
        raise LabError("build/course_tasks not found; configure and build the native target first")
    # The database admin password is not inherited by the native app. Native
    # mode deliberately needs no database and cannot bind a public interface.
    environment = {key: value for key, value in os.environ.items()
                   if key not in SECRET_NAMES and not key.startswith("PG")}
    environment.update(APP_TOKEN=values["APP_TOKEN"], APP_BIND="127.0.0.1",
                       APP_PORT=str(port), APP_STORAGE="memory")
    print(f"Starting memory service at http://127.0.0.1:{port}; Ctrl-C stops it", flush=True)
    return subprocess.run([str(binary)], cwd=root, env=environment, check=False).returncode


def pack_sources(root: Path = ROOT, output: str = "service-workshop-source.tar.gz") -> None:
    if not ARCHIVE_NAME.fullmatch(output):
        raise LabError("--output must be a plain .tar.gz filename inside this workshop")
    with ExitStack() as stack:
        root_fd = open_directory(root)
        stack.callback(os.close, root_fd)
        assert_absent_at(root_fd, output)
        sources = []
        for name in SOURCE_FILES:
            descriptor = open_regular_at(root_fd, name)
            stream = stack.enter_context(os.fdopen(descriptor, "rb"))
            metadata = os.fstat(stream.fileno())
            if metadata.st_size > 2 * 1024 * 1024:
                raise LabError(f"{name}: source exceeds the 2 MiB packing limit")
            sources.append((name, stream, metadata.st_size))
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=root_fd)
        with os.fdopen(descriptor, "wb") as destination:
            with tarfile.open(fileobj=destination, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
                for name, stream, size in sources:
                    entry = tarfile.TarInfo(f"service-workshop/{name}")
                    entry.size = size
                    entry.mode = 0o644
                    entry.mtime = 0
                    archive.addfile(entry, stream)


def parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("use an unprivileged port from 1024 to 65535")
    return port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create private local secrets without overwriting files")
    commands.add_parser("check-env", help="check secret names/presence without printing values")
    run = commands.add_parser("run", help="run build/course_tasks on loopback with memory storage")
    run.add_argument("--port", type=parse_port, default=8080)
    pack = commands.add_parser("pack", help="make an allowlisted source-only archive; never upload it")
    pack.add_argument("--output", default="service-workshop-source.tar.gz")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            init_secrets()
            print("Created .env (0600) and .secrets/client.curl (0600); values are not displayed")
        elif arguments.command == "check-env":
            return check_environment()
        elif arguments.command == "run":
            return run_native(port=arguments.port)
        elif arguments.command == "pack":
            pack_sources(output=arguments.output)
            print(f"Created {arguments.output}; source only, no upload, no local secrets")
    except KeyboardInterrupt:
        return 130
    except LabError as error:
        print(f"Operation refused: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        # OS exceptions may include attacker-controlled paths, while decoding
        # exceptions may include bytes from a malformed secret. Keep output safe.
        print("Operation refused: check private file permissions, required source files, "
              "and whether a target already exists. No file is overwritten.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
