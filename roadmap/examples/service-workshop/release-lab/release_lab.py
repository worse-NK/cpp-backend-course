#!/usr/bin/env python3
"""Create/check private settings only. Never runs Docker, SSH, or a shell."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import secrets
import stat
import sys


ROOT = Path(__file__).resolve().parent
SECRET_NAMES = ("POSTGRES_PASSWORD", "APP_DB_PASSWORD")
PROJECT = re.compile(r"course-release-lab-[0-9a-f]{12}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def init(root=ROOT):
    values = {"RELEASE_LAB_PROJECT": "course-release-lab-" + secrets.token_hex(6),
              **{name: secrets.token_hex(32) for name in SECRET_NAMES}}
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "w", encoding="ascii") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write("".join(name + "=" + value + "\n" for name, value in values.items()))
            target.flush()
            os.fsync(target.fileno())
    finally:
        os.close(directory)


def read_env(root=ROOT):
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(".env", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "r", encoding="ascii") as source:
        metadata = os.fstat(source.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
            raise ValueError("Expected an owned single-link 0600 .env")
        text = source.read(2049)
    if len(text) > 2048:
        raise ValueError("Private file too large")
    values = {}
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        pattern = PROJECT if name == "RELEASE_LAB_PROJECT" else HEX
        if (not separator or name not in ("RELEASE_LAB_PROJECT", *SECRET_NAMES)
                or name in values or not pattern.fullmatch(value)):
            raise ValueError("Unexpected private configuration")
        values[name] = value
    if set(values) != {"RELEASE_LAB_PROJECT", *SECRET_NAMES}:
        raise ValueError("Incomplete private configuration")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "check-env"))
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init()
            print("Created private .env with a new isolated project name; no values displayed")
        else:
            values = read_env()
            print("Project: " + values["RELEASE_LAB_PROJECT"])
            print("POSTGRES_PASSWORD: present; APP_DB_PASSWORD: present")
    except (OSError, ValueError, UnicodeError):
        print("Refused: check private file, permissions and directory; existing .env is never overwritten",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
