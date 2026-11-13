#!/usr/bin/env python3
"""Scan the working tree and complete Git history; never print matched values."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = '8.30.1'
ARCHIVE = 'gitleaks_' + VERSION + '_linux_x64.tar.gz'
ARCHIVE_SHA256 = '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'
BINARY_SHA256 = '88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509'
FIXTURE = 'roadmap/tools/test_network_foundations.py'
FIXTURE_CURRENT_SHA256 = '995e37e40923aa787e9af70d8ef89441dcf5be3a468cf2a2674d35aaf58f05fd'
FIXTURE_HISTORY_SHA256 = '3b96e8be9ef53212a0a3957ad9fffd4ae741ebd04ec1b65805dc2352495174c7'
FIXTURE_COMMIT = '3debe3cef2b0938545ecacdaf2d549eb973028fc'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(repository, *arguments):
    result = subprocess.run(['git', '-C', str(repository), *arguments],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError('Git inspection failed; no diagnostic contents were printed')
    return result.stdout


def checked_binary(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()) != BINARY_SHA256:
        raise ValueError('Gitleaks executable does not match the reviewed binary')
    return path.absolute()


def fetch_binary(directory):
    if platform.system() != 'Linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ValueError('The pinned scanner currently supports Linux amd64 only')
    directory = Path(directory).absolute()
    if any(item.is_symlink() for item in (directory, *directory.parents)):
        raise ValueError('Scanner cache must not contain symlink paths')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ('gitleaks-' + VERSION)
    if target.exists() or target.is_symlink():
        return checked_binary(target)
    url = 'https://github.com/gitleaks/gitleaks/releases/download/v' + VERSION + '/' + ARCHIVE
    try:
        with urlopen(Request(url, headers={'User-Agent': 'course-secret-check'}), timeout=90) as response:
            packed = response.read(30 * 1024 * 1024 + 1)
    except URLError:
        raise ValueError('Cannot download the pinned scanner; no check was skipped') from None
    if sha256(packed) != ARCHIVE_SHA256:
        raise ValueError('Gitleaks archive checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
        members = [item for item in archive.getmembers() if item.name == 'gitleaks']
        if len(members) != 1 or not members[0].isfile():
            raise ValueError('Expected a regular Gitleaks executable')
        data = archive.extractfile(members[0]).read()
    if sha256(data) != BINARY_SHA256:
        raise ValueError('Gitleaks executable checksum mismatch')
    # Exclusive creation avoids replacing an existing cache entry.
    with target.open('xb') as stream:
        stream.write(data)
    target.chmod(0o755)
    return checked_binary(target)


def snapshot(repository, destination):
    """Include tracked files and nonignored new files, but never .git or symlinks."""
    names = git(repository, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    count = 0
    for raw in sorted(set(names.split(b'\0')) - {b''}):
        name = os.fsdecode(raw)
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '.git' in path.parts or '\\' in name:
            raise ValueError('Unsafe Git file path; scan stopped')
        source = repository / name
        if source.is_symlink() or any(parent.is_symlink() for parent in source.parents):
            raise ValueError('Symlink in scan inputs; inspect it explicitly before publishing')
        if not source.exists():
            continue  # Deleted working-tree files remain covered by Git history.
        if not source.is_file():
            raise ValueError('Nonregular file in scan inputs')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        count += 1
    return count


def run_scanner(binary, mode, target, private):
    report = private / (mode + '.json')
    config = private / 'defaults.toml'
    config.write_text('[extend]\nuseDefault = true\n')
    command = [str(binary), mode, str(target), '--config', str(config),
        '--gitleaks-ignore-path', str(private / 'no-ignore-file'), '--ignore-gitleaks-allow',
        '--redact=100', '--no-banner', '--no-color', '--max-target-megabytes=0',
        '--max-decode-depth=3', '--max-archive-depth=2', '--report-format=json', '--report-path', str(report)]
    if mode == 'git':
        command += ['--log-opts=--all --full-history']
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GITLEAKS_')}
    result = subprocess.run(command, env=environment, cwd=private,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode not in (0, 1) or not report.is_file():
        raise ValueError('Gitleaks did not complete; no diagnostic contents were printed')
    findings = json.loads(report.read_text())
    if not isinstance(findings, list):
        raise ValueError('Invalid scanner report')
    return findings


def relative_finding(finding, snapshot_root):
    name = finding.get('File', '')
    path = Path(name)
    if path.is_absolute():
        try:
            return path.relative_to(snapshot_root).as_posix()
        except ValueError:
            raise ValueError('Scanner returned a path outside its snapshot') from None
    return path.as_posix()


def reviewed_header_only(finding, name, repository, mode):
    """Only these exact, audited fixture bytes are exempt, never a file or rule."""
    if finding.get('RuleID') != 'private-key' or name != FIXTURE:
        return False
    commit = finding.get('Commit', '')
    if mode == 'git':
        if commit != FIXTURE_COMMIT or finding.get('StartLine') != 357:
            return False
        data = git(repository, 'show', commit + ':' + FIXTURE)
        return sha256(data) == FIXTURE_HISTORY_SHA256
    return (not commit and finding.get('StartLine') == 368
        and sha256((repository / FIXTURE).read_bytes()) == FIXTURE_CURRENT_SHA256)


def scan(repository, binary):
    repository = Path(repository).resolve()
    if git(repository, 'rev-parse', '--show-toplevel').decode().strip() != str(repository):
        raise ValueError('Scan the repository root, not a subdirectory')
    if git(repository, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('Full Git history is required; use fetch-depth: 0 or git fetch --unshallow')
    unresolved = []
    reviewed = 0
    with tempfile.TemporaryDirectory(prefix='course-secrets-') as temporary:
        private = Path(temporary)
        private.chmod(0o700)
        tree = private / 'tree'
        tree.mkdir()
        files = snapshot(repository, tree)
        if not files:
            raise ValueError('No files were scanned')
        for mode, target in (('dir', tree), ('git', repository)):
            for finding in run_scanner(binary, mode, target, private):
                name = relative_finding(finding, tree)
                if reviewed_header_only(finding, name, repository, mode):
                    reviewed += 1
                else:
                    unresolved.append({'mode': mode, 'file': name,
                        'line': finding.get('StartLine'), 'rule': finding.get('RuleID'),
                        'commit': finding.get('Commit', '')})
    return {'files': files, 'history': 'all local refs, full history',
        'reviewed_header_only_fixtures': reviewed, 'findings': unresolved}


def self_test(binary):
    """Exercise real detection in disposable Git; no test secret reaches this repo."""
    with tempfile.TemporaryDirectory(prefix='course-secrets-selftest-') as temporary:
        repository = Path(temporary)
        git(repository, 'init', '--quiet')
        git(repository, 'config', 'user.name', 'Scanner fixture')
        git(repository, 'config', 'user.email', 'fixture@users.noreply.github.com')
        git(repository, 'config', 'commit.gpgsign', 'false')
        hooks = repository / 'empty-hooks'
        hooks.mkdir()
        git(repository, 'config', 'core.hooksPath', str(hooks))
        fixture = repository / 'fixture.txt'
        fixture.write_text('Ordinary fixture text.\n')
        git(repository, 'add', 'fixture.txt')
        git(repository, 'commit', '--quiet', '-m', 'clean fixture')
        if scan(repository, binary)['findings']:
            raise ValueError('Scanner self-test rejected clean input')
        synthetic = 'gh' + chr(112) + '_' + '0aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1wX'
        fixture.write_text('token = "' + synthetic + '"\n')
        if not any(item['mode'] == 'dir' for item in scan(repository, binary)['findings']):
            raise ValueError('Scanner self-test failed to detect the synthetic working-tree token')
        git(repository, 'add', 'fixture.txt')
        git(repository, 'commit', '--quiet', '-m', 'synthetic scanner fixture')
        fixture.write_text('Ordinary fixture text.\n')
        remaining = scan(repository, binary)['findings']
        if any(item['mode'] == 'dir' for item in remaining):
            raise ValueError('Scanner self-test did not return to green for the cleaned working tree')
        if not any(item['mode'] == 'git' for item in remaining):
            raise ValueError('Scanner self-test failed to detect the synthetic historical token')
    return {'self_test': 'PASS: clean input green, synthetic working-tree/history tokens red'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--binary', type=Path, help='already downloaded, hash-verified Gitleaks executable')
    parser.add_argument('--self-test', action='store_true')
    arguments = parser.parse_args(argv)
    try:
        binary = checked_binary(arguments.binary) if arguments.binary else fetch_binary(ROOT / '.toolchains/secret-scan')
        report = self_test(binary) if arguments.self_test else scan(arguments.repository, binary)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return int(bool(report.get('findings')))
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError):
        print('Secret check failed safely; matched values and raw diagnostics were not printed.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
