#!/usr/bin/env python3
"""Sync the site AND editable sources into an existing course Git checkout.

The deployment ZIP stays source-free. This separate repository snapshot keeps
canonical data and rebuild dependencies in Git, without copying workspace files.
Never deletes files, stages, commits or pushes; refuses conflicting local edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from build_publication import ROOT, collect, check_release, source_bytes


PROJECT_SOURCES = (
    ".gitignore", "README.md", "docs/BUILDING.md", "docs/SECURITY.md",
    "docs/RELEASING.md", "docs/THIRD_PARTY.md", "tools/course.py",
    "tools/build_local.py", "tools/test_course_tools.py",
    "tools/publish_release.py", "tools/test_publish_release.py",
    ".github/workflows/release-desktop.yml",
)
DESKTOP_SOURCES = (
    ".gitignore", "README.txt", "build_site.py", "build_deb.py", "fetch_runtime.py",
    "app/package.json", "app/main.cjs", "app/preload.cjs", "app/security.cjs",
    "linux/cpp-backend-course-desktop", "linux/cpp-backend-course-desktop.desktop",
    "web/progress.html", "web/desktop-ui.js", "web/desktop.css",
    "web/progress-core.js", "web/progress-ui.js",
    "icons/app.svg", "icons/render_icons.py",
    "tests/cdp.py", "tests/test_browser.py", "tests/test_build.py",
    "tests/test_desktop_identity.py", "tests/test_downloads.py",
    "tests/test_multiwindow.py", "tests/test_package.py", "tests/test_progress.py",
    "tests/test_progress_ui.py", "tests/test_real_package.py",
    "tests/test_security.cjs", "tests/test_upgrade.cjs", "tests/test_visual.py",
)
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def project_source_bytes(project: Path, name: str) -> bytes:
    """Read an explicitly selected project source, never an arbitrary subtree."""
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or ".." in relative.parts
            or ".git" in relative.parts or "\\" in name
            or relative.as_posix() != name):
        raise ValueError(f"Unsafe project source path: {name}")
    path = project / name
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError(f"Symlink is not a repository source: {name}")
    if not path.is_file():
        raise ValueError(f"Required repository source is missing: {name}")
    return path.read_bytes()


def collect_desktop_sources(project: Path) -> dict[str, bytes]:
    """Ship build inputs and pinned small assets, not runtime or personal data."""
    names = {"desktop-course/" + name for name in DESKTOP_SOURCES}
    names.update(f"desktop-course/icons/app-{size}.png" for size in ICON_SIZES)
    result = {name: project_source_bytes(project, name) for name in sorted(names)}
    lock_name = "desktop-course/vendor/ORIGIN.json"
    lock_bytes = project_source_bytes(project, lock_name)
    lock = json.loads(lock_bytes)
    if (not isinstance(lock, dict) or lock.get("format") != 1
            or not isinstance(lock.get("files"), dict) or not lock["files"]):
        raise ValueError("Invalid desktop vendor lock")
    result[lock_name] = lock_bytes
    for name, expected in sorted(lock["files"].items()):
        if not isinstance(name, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid desktop vendor entry")
        relative = PurePosixPath(name)
        # Only frozen JS/fonts/styles and their notices can be vendor inputs.
        # A lockfile edit must not turn a local .env or key into a public source.
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or relative.as_posix() != name or len(relative.parts) < 2
                or relative.parts[0] not in {"react", "fonts"}
                or any(part.startswith(".") for part in relative.parts)
                or not (relative.suffix in {".js", ".css", ".ttf", ".woff", ".woff2"}
                        or relative.name.startswith("LICENSE"))):
            raise ValueError("Unsafe desktop vendor entry")
        target = "desktop-course/vendor/" + name
        content = project_source_bytes(project, target)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Desktop vendor hash mismatch: {name}")
        result[target] = content
    return result


def check_repository_source_privacy(files: dict[str, bytes]) -> None:
    """Reject obvious key material without suppressing whole test/source files.

    Tests legitimately enumerate PEM header strings, so a header alone is not
    a usable key. This lightweight gate checks complete key bodies and known
    provider-token shapes; it complements, not replaces, a full secret scanner.
    """
    provider_token = re.compile(
        rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|"
        rb"github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})(?![A-Za-z0-9_])")
    private_key = re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
        rb"[ \t]*(?:\r?\n|\\n)[A-Za-z0-9+/=\\\r\n]{64,}"
        rb"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
    for name, content in files.items():
        if (provider_token.search(content) or private_key.search(content)
                or content.startswith(b"SQLite format 3\0")):
            raise ValueError(f"Potential credential or private database in {name}; review locally")
        # The broad web-distribution path regex cannot be applied to source
        # tests: some intentionally contain /home/example negative fixtures.
        # Still reject the exporting workspace's real literal path everywhere.
        if len(ROOT.parent.parts) > 2 and str(ROOT.parent).encode() in content:
            raise ValueError(f"Potential private workspace path in {name}; review locally")


def collect_repository_files() -> dict[str, bytes]:
    files, stations = collect()
    check_release(files, stations)
    sources = {
        "content/cheatsheet.json", "content/glossary.json", "content/visual-labs.json",
        "content/cpp-examples.json",
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
        "validate_materials.py", "cpp_examples.py", "course_theme.py", "netlab_vm_guest.py", "netlab_vm_init.sh",
        "run_netlab_vm.py", "sync_repository.py"))
    sources.update("tools/" + name for name in (
        "run_gap_network_vm.py", "gap_network_vm_init.sh", "tooling_perf_vm_guest.py",
        "prepare_tooling_perf_vm.py"))
    files.update({"roadmap/" + name: source_bytes(name) for name in sorted(sources)})
    # Repository documentation is different from the compact web ZIP's README.
    # Neither source collection changes the source-free publication allowlist.
    files.update({name: project_source_bytes(ROOT.parent, name) for name in PROJECT_SOURCES})
    files.update(collect_desktop_sources(ROOT.parent))
    check_repository_source_privacy(files)
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
