#!/usr/bin/env python3
"""Fetch and verify one reviewed Electron runtime, locally and without npm."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = '45.2.3'
ARCHIVE = 'electron-v45.2.3-linux-x64.zip'
# Official release asset digest, independently pinned rather than trusting any
# checksum fetched in the same transaction. It is integrity, not a signature.
ARCHIVE_SHA256 = 'a87fe741f6d121285117e574da6c9a2e65210d410123bbc04713b099add0263b'
# Canonical file map derived from the freshly SHA256-verified upstream ZIP.
# Anchors later local manifest checks as well, so editing a binary AND its
# adjacent metadata cannot silently pass the package copy boundary.
RUNTIME_FILES_SHA256 = 'f594c67aece3a5ba2ccc02802e3e8fd567177b0e5699e7cbca63800518822e50'
BASE = 'https://github.com/electron/electron/releases/download/v' + VERSION + '/'
MANIFEST = 'runtime-manifest.json'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def safe_path(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name
            and not PurePosixPath(name).is_absolute()
            and all(p not in ('', '.', '..') for p in name.split('/'))
            and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def no_symlink_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symbolic links are not accepted: ' + str(path))
    return path


def download(url, target, max_bytes):
    target = no_symlink_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Explicitly scoped to this destination, never a global cache/tool install.
    descriptor, temporary_name = tempfile.mkstemp(prefix='download-', dir=target.parent)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'cpp-backend-course-local-builder/1.0'})
        with os.fdopen(descriptor, 'wb') as output, urllib.request.urlopen(request, timeout=40) as response:
            if not response.geturl().startswith('https://'):
                raise ValueError('Refusing a non-HTTPS redirect')
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError('Download exceeds the reviewed size bound')
                output.write(chunk)
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def published_digest(checksums):
    matches = []
    for line in checksums.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip('*') == ARCHIVE:
            matches.append(fields[0])
    if matches != [ARCHIVE_SHA256]:
        raise ValueError('Published Electron checksum does not match reviewed pin')
    return matches[0]


def verify_runtime(directory):
    directory = no_symlink_path(directory)
    manifest_path = directory / MANIFEST
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('format') != 1 or manifest.get('version') != VERSION
            or manifest.get('archive_sha256') != ARCHIVE_SHA256
            or manifest.get('platform') != 'linux-x64' or not isinstance(manifest.get('files'), dict)):
        raise ValueError('Unreviewed runtime metadata')
    file_map_hash = hashlib.sha256(json.dumps(manifest['files'], sort_keys=True,
                                             separators=(',', ':')).encode()).hexdigest()
    if file_map_hash != RUNTIME_FILES_SHA256:
        raise ValueError('Runtime file map differs from the reviewed upstream archive')
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(manifest['files']) | {MANIFEST}:
        raise ValueError('Unmanaged or missing runtime files')
    for name, meta in manifest['files'].items():
        if not safe_path(name):
            raise ValueError('Unsafe runtime file path')
        path = no_symlink_path(directory / name)
        if not path.is_file() or path.stat().st_size != meta['bytes'] or digest(path) != meta['sha256']:
            raise ValueError('Runtime file changed: ' + name)
    for required in ('electron', 'chrome-sandbox', 'LICENSE', 'LICENSES.chromium.html', 'version'):
        if required not in manifest['files']:
            raise ValueError('Required runtime file missing: ' + required)
    if (directory / 'version').read_text().strip().lstrip('v') != VERSION:
        raise ValueError('Runtime version file differs')
    with (directory / 'electron').open('rb') as stream:
        prefix = stream.read(4)
    if prefix != b'\x7fELF':
        raise ValueError('Electron is not an ELF executable')
    return manifest


def extract_verified(archive, output, checksum_file):
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('Electron ZIP SHA256 mismatch; no executable extracted')
    published_digest(Path(checksum_file).read_text())
    output = no_symlink_path(output)
    if output.exists():
        return verify_runtime(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as packed:
        entries = packed.infolist()
        if len(entries) > 2000 or sum(e.file_size for e in entries) > 1024 * 1024 * 1024:
            raise ValueError('Unexpectedly large Electron archive')
        names = set()
        for entry in entries:
            name = entry.filename.rstrip('/')
            mode = entry.external_attr >> 16
            if not safe_path(name) or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('Unsafe ZIP path or file type: ' + entry.filename)
            if name in names:
                raise ValueError('Duplicate archive member: ' + name)
            names.add(name)
        # Stage next to the exact target; success becomes one rename, with no
        # partial output advertised as an installed/verified toolchain.
        with tempfile.TemporaryDirectory(prefix='electron-stage-', dir=output.parent) as temporary:
            stage = Path(temporary) / 'runtime'
            stage.mkdir()
            files = {}
            for entry in entries:
                target = stage / entry.filename
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with packed.open(entry) as source, target.open('wb') as destination:
                    shutil.copyfileobj(source, destination)
                executable = bool((entry.external_attr >> 16) & 0o111)
                target.chmod(0o755 if executable else 0o644)
                files[entry.filename] = {'bytes': target.stat().st_size, 'sha256': digest(target),
                                        'executable': executable}
            report = {'format': 1, 'version': VERSION, 'platform': 'linux-x64',
                      'source': BASE + ARCHIVE, 'checksum_source': BASE + 'SHASUMS256.txt',
                      'archive_sha256': ARCHIVE_SHA256, 'archive_bytes': Path(archive).stat().st_size,
                      'uncompressed_bytes': sum(item['bytes'] for item in files.values()),
                      'files': files}
            (stage / MANIFEST).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            verify_runtime(stage)
            stage.rename(output)
    return report


def fetch(output, cache):
    output = no_symlink_path(output)
    if output.exists():
        return verify_runtime(output)
    cache = no_symlink_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ARCHIVE
    sums = cache / ('SHASUMS256-' + VERSION + '.txt')
    if not sums.exists():
        download(BASE + 'SHASUMS256.txt', sums, 4 * 1024 * 1024)
    published_digest(sums.read_text())
    if not archive.exists():
        download(BASE + ARCHIVE, archive, 250 * 1024 * 1024)
    return extract_verified(archive, output, sums)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=[VERSION], default=VERSION)
    parser.add_argument('--output', type=Path, default=ROOT / '.toolchain' / ('electron-' + VERSION + '-linux-x64'))
    parser.add_argument('--cache', type=Path, default=ROOT / '.toolchain')
    args = parser.parse_args()
    result = fetch(args.output, args.cache)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, ensure_ascii=False, indent=2))
