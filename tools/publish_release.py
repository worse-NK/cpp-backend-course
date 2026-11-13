#!/usr/bin/env python3
"""Prepare allowlisted release files and publish a verified GitHub draft.

Building is local and never installs the package. Publication is a separate,
explicit command; its token comes from the Actions environment, not a file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'cpp-backend-course-desktop'
MANIFEST = 'release-manifest.json'
API_VERSION = '2022-11-28'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_path(value):
    path = Path(value).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Release paths must not contain symbolic links')
    return path


def version(root=ROOT):
    metadata = json.loads(checked_path(Path(root) / 'desktop-course/app/package.json').read_text())
    value = metadata.get('version', '')
    if metadata.get('name') != PACKAGE or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', value):
        raise ValueError('Release requires the expected application and a semantic version')
    return value


def identity(tag, sha, root=ROOT):
    release_version = version(root)
    if tag != 'desktop-v' + release_version:
        raise ValueError('Release tag must exactly match the application version')
    if not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
        raise ValueError('A complete source commit SHA is required')
    return release_version


def source_sha(root=ROOT):
    value = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('Cannot identify the checked-out source commit')
    return value


def ci_metadata(env=None, root=ROOT):
    env = os.environ if env is None else env
    event = env.get('GITHUB_EVENT_NAME')
    if event == 'push':
        ref = env.get('GITHUB_REF', '')
        if not ref.startswith('refs/tags/desktop-v'):
            raise ValueError('A tag push is required, not an ordinary branch push')
        tag = ref.removeprefix('refs/tags/')
    elif event == 'workflow_dispatch':
        tag = env.get('REQUESTED_RELEASE_TAG', '')
    else:
        raise ValueError('Release runs only for a tag push or a manual dispatch')
    sha = source_sha(root)
    release_version = identity(tag, sha, root)
    expected = env.get('GITHUB_SHA', '')
    if expected and not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise ValueError('Invalid event commit SHA')
    if expected and expected != sha:
        # Annotated tags may supply a tag object; peel it before comparing.
        peeled = subprocess.check_output(['git', '-C', str(root), 'rev-parse', expected + '^{commit}'], text=True).strip()
        if peeled != sha:
            raise ValueError('Checked-out source differs from the event commit')
    result = {'tag': tag, 'version': release_version, 'source_sha': sha}
    output = env.get('GITHUB_OUTPUT')
    if not output:
        raise ValueError('GITHUB_OUTPUT is required for the release workflow')
    with Path(output).open('a', encoding='utf-8') as stream:
        for name, value in result.items():
            stream.write(name + '=' + value + '\n')
    return result


def asset_names(release_version):
    return (PACKAGE + '_' + release_version + '_amd64.deb',
            'cpp-backend-course-web_' + release_version + '.zip',
            'cpp-backend-course-local_' + release_version + '.zip')


def check_zip(path):
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            pure = PurePosixPath(entry.filename)
            if (pure.is_absolute() or '\\' in entry.filename or '..' in pure.parts
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe path in release archive')
        if archive.testzip() is not None:
            raise ValueError('A release archive failed its CRC check')


def check_package(path, release_version):
    result = subprocess.check_output(['dpkg-deb', '--field', str(path),
        'Package', 'Version', 'Architecture'], text=True)
    fields = dict(line.split(': ', 1) for line in result.splitlines() if ': ' in line)
    if fields != {'Package': PACKAGE, 'Version': release_version, 'Architecture': 'amd64'}:
        raise ValueError('Debian package identity differs from the release')


def prepare(tag, sha, output=None, root=ROOT):
    root = checked_path(root)
    release_version = identity(tag, sha, root)
    if source_sha(root) != sha:
        raise ValueError('Release must be prepared from the identified source commit')
    output = checked_path(output or root / 'build/release-assets')
    names = asset_names(release_version)
    inputs = (root / 'desktop-course/release' / names[0],
              root / 'publish/cpp-backend-course.zip',
              root / 'build/cpp-backend-course-local.zip')
    # Validate every input before creating or writing the output directory.
    payloads = {}
    for name, path in zip(names, inputs):
        path = checked_path(path)
        if not path.is_file() or not 0 < path.stat().st_size < 2 * 1024 ** 3:
            raise ValueError('Missing or oversized release input: ' + name)
        if path.suffix == '.zip':
            check_zip(path)
        else:
            check_package(path, release_version)
        payloads[name] = path.read_bytes()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Refusing to overwrite existing release artifacts')
    metadata = {name: {'bytes': len(data), 'sha256': digest(data)}
                for name, data in sorted(payloads.items())}
    sums = ''.join(info['sha256'] + '  ' + name + '\n' for name, info in metadata.items()).encode()
    payloads['SHA256SUMS'] = sums
    metadata['SHA256SUMS'] = {'bytes': len(sums), 'sha256': digest(sums)}
    manifest = {'format': 1, 'version': release_version, 'tag': tag,
                'source_sha': sha, 'files': metadata}
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def read_bundle(directory, tag, sha, root=ROOT):
    directory = checked_path(directory)
    release_version = identity(tag, sha, root)
    manifest = json.loads(checked_path(directory / MANIFEST).read_text())
    expected_names = set(asset_names(release_version)) | {'SHA256SUMS'}
    if (manifest.get('format') != 1 or manifest.get('version') != release_version
            or manifest.get('tag') != tag or manifest.get('source_sha') != sha
            or set(manifest.get('files', {})) != expected_names):
        raise ValueError('Release manifest does not match its source and version')
    if {path.name for path in directory.iterdir()} != expected_names | {MANIFEST}:
        raise ValueError('Unexpected files in release bundle')
    payloads = {}
    for name, info in manifest['files'].items():
        data = checked_path(directory / name).read_bytes()
        if info != {'bytes': len(data), 'sha256': digest(data)}:
            raise ValueError('Release artifact differs from its manifest: ' + name)
        payloads[name] = data
    expected_sums = ''.join(manifest['files'][name]['sha256'] + '  ' + name + '\n'
                            for name in sorted(expected_names - {'SHA256SUMS'})).encode()
    if payloads['SHA256SUMS'] != expected_sums:
        raise ValueError('SHA256SUMS is inconsistent with the release files')
    return manifest, payloads


class GitHubError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('GitHub API request failed with HTTP ' + str(status))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to a redirected host.
        return None


class GitHub:
    def __init__(self, repository, token, opener=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository or ''):
            raise ValueError('Expected an owner/repository name, not a URL')
        if any(part in ('.', '..') for part in repository.split('/')):
            raise ValueError('Invalid repository name')
        if not token or token != token.strip() or '\r' in token or '\n' in token:
            raise ValueError('A GitHub token must be supplied through the environment')
        self.repository = repository
        self.token = token
        self.opener = opener or build_opener(NoRedirect())

    def request(self, method, path, payload=None, data=None, content_type=None, upload=False):
        host = 'https://uploads.github.com' if upload else 'https://api.github.com'
        parts = urlsplit(path)
        if (not path.startswith('/repos/' + self.repository + '/') or parts.scheme or parts.netloc
                or parts.fragment or '\\' in path or any(ord(char) < 32 for char in path)
                or any(part in ('.', '..') for part in unquote(parts.path).split('/'))):
            raise ValueError('GitHub request is outside the selected repository')
        if payload is not None:
            data = json.dumps(payload).encode()
            content_type = 'application/json'
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': API_VERSION,
                   'User-Agent': 'cpp-backend-course-release', 'Authorization': 'Bearer ' + self.token}
        if content_type:
            headers['Content-Type'] = content_type
        request = Request(host + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=180) as response:
                return json.load(response)
        except HTTPError as error:
            # Response bodies may contain private diagnostic data: never log them.
            raise GitHubError(error.code) from None
        except URLError:
            raise RuntimeError('GitHub API connection failed; no token or response body was logged') from None


def verify_ref(client, tag, sha, absent_ok=False):
    base = '/repos/' + client.repository
    try:
        value = client.request('GET', base + '/git/ref/tags/' + quote(tag, safe=''))['object']
    except GitHubError as error:
        if absent_ok and error.status == 404:
            return False
        raise
    for _ in range(5):
        if value.get('type') == 'commit':
            if value.get('sha') != sha:
                raise ValueError('Existing GitHub tag points to a different source commit')
            return True
        if value.get('type') != 'tag' or not re.fullmatch(r'[0-9a-f]{40}', value.get('sha', '')):
            raise ValueError('Unexpected GitHub tag object')
        value = client.request('GET', base + '/git/tags/' + value['sha'])['object']
    raise ValueError('Too many nested annotated tags')


def release_body(release_version, sha, repository):
    return ('C++ Backend ' + release_version + '\n\n'
        'Варианты использования учебника:\n'
        '- Онлайн: https://worse-nk.github.io/cpp-backend-course/\n'
        '- Веб-раздача: архив web для самостоятельного размещения сайта.\n'
        '- Локальный браузер: архив local с библиотеками и шрифтами внутри; интернет для чтения не нужен.\n'
        '- Приложение: .deb для Linux amd64 с собственным Electron; установленный браузер не требуется.\n\n'
        'Сборка из исходников описана в README и docs/BUILDING.md. '
        'GitHub автоматически добавляет архивы исходников соответствующего тега.\n\n'
        'SHA256SUMS содержит контрольные суммы трёх файлов, а не цифровую подпись. '
        'Внешние серверные лаборатории и инструменты разработки в приложение не входят.\n\n'
        'Исходный коммит: https://github.com/' + repository + '/commit/' + sha + '\n'
        '<!-- course-release-source:' + sha + ' -->\n')


def checked_assets(client, release_id, manifest, allow_missing=False):
    path = '/repos/' + client.repository + '/releases/' + str(release_id) + '/assets?per_page=100'
    assets = client.request('GET', path)
    names = [item.get('name') for item in assets]
    if len(names) != len(set(names)) or set(names) - set(manifest['files']):
        raise ValueError('Existing release contains unexpected assets; nothing overwritten')
    for item in assets:
        expected = manifest['files'][item['name']]
        if (item.get('state') != 'uploaded' or item.get('size') != expected['bytes']
                or item.get('digest') != 'sha256:' + expected['sha256']):
            raise ValueError('Uploaded release hash or size mismatch; draft remains unpublished')
    if not allow_missing and set(names) != set(manifest['files']):
        raise ValueError('Release upload is incomplete; draft remains unpublished')
    return set(names)


def publish(directory, repository, tag, sha, token=None, client=None, root=ROOT, env=None):
    env = os.environ if env is None else env
    if env.get('GITHUB_REPOSITORY') and env['GITHUB_REPOSITORY'] != repository:
        raise ValueError('Publication repository differs from the Actions repository')
    manifest, payloads = read_bundle(directory, tag, sha, root)
    if source_sha(root) != sha:
        raise ValueError('Publication code was checked out from a different commit')
    client = client or GitHub(repository, token or env.get('GITHUB_TOKEN', ''))
    base = '/repos/' + repository
    tag_exists = verify_ref(client, tag, sha, absent_ok=True)
    try:
        release = client.request('GET', base + '/releases/tags/' + quote(tag, safe=''))
    except GitHubError as error:
        if error.status != 404:
            raise
        release = client.request('POST', base + '/releases', payload={
            'tag_name': tag, 'target_commitish': sha, 'name': 'C++ Backend ' + manifest['version'],
            'body': release_body(manifest['version'], sha, repository), 'draft': True,
            'prerelease': '-' in manifest['version']})
    if (release.get('tag_name') != tag
            or '<!-- course-release-source:' + sha + ' -->' not in release.get('body', '')
            or not isinstance(release.get('id'), int) or release['id'] <= 0):
        raise ValueError('Existing release is not this source bundle; nothing overwritten')
    # A manual draft need not create its tag until publication. If it already
    # exists (or appeared concurrently), it must still identify these sources.
    if not tag_exists:
        verify_ref(client, tag, sha, absent_ok=True)
    release_id = release['id']
    uploaded = checked_assets(client, release_id, manifest, allow_missing=bool(release.get('draft')))
    if not release.get('draft'):
        return 'https://github.com/' + repository + '/releases/tag/' + tag
    for name in sorted(set(payloads) - uploaded):
        media = 'application/vnd.debian.binary-package' if name.endswith('.deb') else (
            'application/zip' if name.endswith('.zip') else 'text/plain')
        client.request('POST', base + '/releases/' + str(release_id) + '/assets?name=' + quote(name, safe=''),
                       data=payloads[name], content_type=media, upload=True)
    checked_assets(client, release_id, manifest)
    verify_ref(client, tag, sha, absent_ok=True)
    result = client.request('PATCH', base + '/releases/' + str(release_id), payload={
        'draft': False, 'make_latest': 'false' if '-' in manifest['version'] else 'true'})
    if result.get('draft') is not False:
        raise ValueError('GitHub did not confirm release publication')
    verify_ref(client, tag, sha)
    return 'https://github.com/' + repository + '/releases/tag/' + tag


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('metadata', help='Validate Actions event and emit safe job outputs')
    for command in ('prepare', 'publish'):
        item = commands.add_parser(command)
        item.add_argument('--tag', required=True)
        item.add_argument('--sha', required=True)
        item.add_argument('--directory', type=Path, default=ROOT / 'build/release-assets')
        if command == 'publish':
            item.add_argument('--repository', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'metadata':
            print(json.dumps(ci_metadata(), indent=2))
        elif args.command == 'prepare':
            print(json.dumps(prepare(args.tag, args.sha, args.directory), indent=2))
        else:
            print(publish(args.directory, args.repository, args.tag, args.sha))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
