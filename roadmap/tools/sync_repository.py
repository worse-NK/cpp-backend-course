#!/usr/bin/env python3
"""Sync the site AND editable sources into an existing course Git checkout.

The deployment ZIP stays source-free. This separate repository snapshot keeps
canonical data and rebuild dependencies in Git, without copying workspace files.
Never deletes files, stages, commits or pushes; refuses conflicting local edits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from build_publication import ROOT, collect, check_release, source_bytes


def collect_repository_files() -> dict[str, bytes]:
    files, stations = collect()
    check_release(files, stations)
    sources = {
        "content/cheatsheet.json", "content/glossary.json", "content/visual-labs.json",
        "content/service-workshop/route.json", "assets/sql-lab-worker.js",
        "vendor/sqljs/sql-asm.js", "vendor/sqljs/README.md",
    }
    sources.update("tests/" + name for name in (
        "build_example/CMakeLists.txt", "build_example/include/core.hpp",
        "build_example/src/core.cpp", "build_example/src/main.cpp",
        "build_example/tests/core_test.cpp", "installed_consumer/CMakeLists.txt",
        "installed_consumer/main.cpp", "odr_example/left.cpp", "odr_example/main.cpp",
        "odr_example/math.hpp", "pimpl_example/client.cpp", "pimpl_example/client.hpp",
        "pimpl_example/main.cpp"))
    for station in stations:
        identifier = station["meta"]["id"]
        sources.update((f"content/{identifier}.json", f"content/checkpoints/{identifier}.json"))
    route = json.loads(source_bytes("content/service-workshop/route.json"))
    for chapter in route["chapters"]:
        identifier = chapter["id"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier):
            raise ValueError("Unsafe workshop source id")
        sources.add(f"content/service-workshop/{identifier}.html")
    # Only code entry points, not arbitrary files next to the test suite.
    patterns = ("build_*.py", "test_*.py", "test_*.js", "verify_*.py")
    sources.update("tools/" + path.name for pattern in patterns
                   for path in (ROOT / "tools").glob(pattern))
    sources.update("tools/" + name for name in (
        "checkpoint_data.py", "export_final_selection.js", "audit_question_choices.py",
        "validate_materials.py", "netlab_vm_guest.py", "netlab_vm_init.sh",
        "run_netlab_vm.py", "sync_repository.py"))
    files.update({"roadmap/" + name: source_bytes(name) for name in sorted(sources)})
    files[".gitignore"] = (ROOT.parent / ".gitignore").read_bytes()
    return files


def git_paths(repository: Path, *args: str) -> set[str]:
    result = subprocess.run(["git", "-C", str(repository), *args, "-z"],
                            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return set(result.stdout.decode().rstrip("\0").split("\0")) - {""}


def sync_repository(destination: Path, files: dict[str, bytes] | None = None) -> int:
    repository = Path(destination).absolute()
    if repository.is_symlink() or any(p.is_symlink() for p in repository.parents):
        raise ValueError("Repository path must not contain symlinks")
    if not (repository / ".git").exists():
        raise ValueError("Destination must be an existing Git checkout")
    files = collect_repository_files() if files is None else files
    indexed = git_paths(repository, "ls-files", "-v")
    tracked = {entry[2:] for entry in indexed}
    # These index flags can hide real edits from git diff. Do not touch such a
    # target at all when an update is needed, even if Git reports it clean.
    protected = {entry[2:] for entry in indexed if entry[0].islower() or entry[0] == "S"}
    dirty = git_paths(repository, "diff", "--name-only") | git_paths(repository, "diff", "--cached", "--name-only")
    targets = {PurePosixPath(name) for name in files}
    if any(parent in targets for target in targets for parent in target.parents):
        raise ValueError("Repository file target cannot be another target's parent")
    changes = []
    for name, data in sorted(files.items()):
        path = PurePosixPath(name)
        if path.is_absolute() or any(p in {"..", ".git"} for p in path.parts):
            raise ValueError(f"Unsafe repository target: {name}")
        target = repository / name
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError(f"Symlink in repository target: {name}")
        if target.exists() and not target.is_file():
            raise ValueError(f"Repository target is not a file: {name}")
        if any(p.exists() and not p.is_dir() for p in target.parents):
            raise ValueError(f"Repository parent is not a directory: {name}")
        current = target.read_bytes() if target.exists() else None
        if current == data:
            continue
        if name in dirty or name in protected or (current is not None and name not in tracked):
            raise ValueError(f"Conflicting local edit: {name}; nothing overwritten")
        changes.append((target, data))
    # Validate every destination before writing even the first file.
    for target, data in changes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return len(changes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path,
                        help="Existing Git checkout; not the github-pages output folder")
    args = parser.parse_args()
    count = sync_repository(args.repository)
    print(f"Synchronized {count} changed files; editable sources included; no files deleted")
    print("Review git diff, then commit and push explicitly.")
