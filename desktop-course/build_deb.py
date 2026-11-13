#!/usr/bin/env python3
"""Build an independent Electron .deb, never install it or change a profile."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PACKAGE = 'cpp-backend-course-desktop'
SITE_MANIFEST = 'desktop-build.json'
APP_FILES = ('main.cjs', 'preload.cjs', 'security.cjs', 'package.json')
# Direct ELF dependencies plus desktop URL dispatch. t64 alternatives cover
# Ubuntu24.04 while ordinary package names cover Ubuntu22.04 / Debian12.
DEPENDENCIES = (
    'libc6 (>= 2.35)', 'libgcc-s1', 'libglib2.0-0t64 | libglib2.0-0',
    'libnss3', 'libnspr4', 'libatk1.0-0t64 | libatk1.0-0',
    'libatk-bridge2.0-0t64 | libatk-bridge2.0-0', 'libcups2t64 | libcups2',
    'libdbus-1-3', 'libcairo2', 'libgtk-3-0t64 | libgtk-3-0', 'libpango-1.0-0',
    'libx11-6', 'libxcomposite1', 'libxdamage1', 'libxext6', 'libxfixes3',
    'libxrandr2', 'libgbm1', 'libexpat1', 'libxcb1', 'libxkbcommon0',
    'libudev1', 'libasound2t64 | libasound2', 'libatspi2.0-0t64 | libatspi2.0-0',
    'xdg-utils',
)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name
            and '%' not in name and not PurePosixPath(name).is_absolute()
            and all(part not in ('', '.', '..') for part in name.split('/'))
            and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def checked_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symbolic links are not accepted: ' + str(path))
    return path


def application_version():
    """Keep the CLI default in sync with the packaged application metadata."""
    metadata = json.loads(checked_path(ROOT / 'app/package.json').read_text())
    version = metadata.get('version')
    if metadata.get('name') != PACKAGE or not isinstance(version, str) or not re.fullmatch(r'[0-9][0-9A-Za-z.+:~\-]*', version):
        raise ValueError('Invalid application package metadata')
    return version


def site_payload(directory):
    directory = checked_path(directory)
    manifest_path = checked_path(directory / SITE_MANIFEST)
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get('files')
    if manifest.get('format') != 1 or not isinstance(files, dict) or 'index.html' not in files:
        raise ValueError('Invalid desktop-build.json')
    if not isinstance(manifest.get('version'), str) or not re.fullmatch(r'[a-f0-9]{12,64}', manifest['version']):
        raise ValueError('Invalid course content version')
    payload = {}
    for name, metadata in files.items():
        if not safe_name(name) or not isinstance(metadata, dict):
            raise ValueError('Unsafe desktop file metadata')
        path = checked_path(directory / name)
        if not path.is_file():
            raise ValueError('Missing desktop file: ' + name)
        data = path.read_bytes()
        if len(data) != metadata.get('bytes') or digest(data) != metadata.get('sha256'):
            raise ValueError('Desktop file differs from manifest: ' + name)
        payload[name] = data
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    if actual != set(files) | {SITE_MANIFEST}:
        raise ValueError('Unmanaged or missing files in the desktop site')
    payload[SITE_MANIFEST] = manifest_path.read_bytes()
    return manifest, payload


def write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def stage_package(stage, site, runtime, version, app_dir=None, icons_dir=None):
    """Populate a fresh staging dir; all runtime and course bytes are checked."""
    app_dir = checked_path(app_dir or ROOT / 'app')
    icons_dir = checked_path(icons_dir or ROOT / 'icons')
    fetcher = module('fetch_electron', ROOT / 'fetch_runtime.py')
    runtime = checked_path(runtime)
    runtime_metadata = fetcher.verify_runtime(runtime)
    content_metadata, payload = site_payload(site)
    package_json = json.loads(checked_path(app_dir / 'package.json').read_text())
    if package_json.get('main') != 'main.cjs' or package_json.get('version') != version:
        raise ValueError('App package.json must match main.cjs and requested package version')
    destination = stage / 'opt' / PACKAGE
    for name, metadata in runtime_metadata['files'].items():
        data = checked_path(runtime / name).read_bytes()
        # verify_runtime checked them all; verify again at the copy boundary.
        if len(data) != metadata['bytes'] or digest(data) != metadata['sha256']:
            raise ValueError('Runtime changed while copying: ' + name)
        target_name = 'course-backend' if name == 'electron' else name
        mode = 0o755 if metadata.get('executable') else 0o644
        if name == 'chrome-sandbox':
            mode = 0o4755
        write(destination / target_name, data, mode)
    write(destination / 'runtime-manifest.json', (runtime / 'runtime-manifest.json').read_bytes())
    app_target = destination / 'resources/app'
    app_hashes = {}
    for name in APP_FILES:
        data = checked_path(app_dir / name).read_bytes()
        write(app_target / name, data)
        app_hashes[name] = digest(data)
    for name, data in payload.items():
        write(app_target / 'site' / name, data)
    # The BrowserWindow icon is supplied directly by app code as well as by
    # desktop integration. Keep its stable path under resources/app/icons.
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        source = checked_path(icons_dir / ('app-' + str(size) + '.png'))
        if not source.exists():
            if size == 512:
                raise ValueError('Required 512px application icon is missing')
            continue
        image = source.read_bytes()
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid PNG icon')
        write(stage / 'usr/share/icons/hicolor' / (str(size) + 'x' + str(size)) / 'apps' / (PACKAGE + '.png'), image)
        if size == 512:
            write(app_target / 'icons/app-512.png', image)
    vector = checked_path(icons_dir / 'app.svg').read_bytes()
    write(stage / 'usr/share/icons/hicolor/scalable/apps' / (PACKAGE + '.svg'), vector)
    write(app_target / 'icons/app.svg', vector)
    launcher = (ROOT / 'linux' / PACKAGE).read_text().replace('@COURSE_VERSION@', version).replace(
        '@ELECTRON_VERSION@', fetcher.VERSION)
    write(stage / 'usr/bin' / PACKAGE, launcher.encode(), 0o755)
    write(stage / 'usr/share/applications' / (PACKAGE + '.desktop'),
          (ROOT / 'linux' / (PACKAGE + '.desktop')).read_bytes())
    docs = stage / 'usr/share/doc' / PACKAGE
    readme = ROOT / 'README.txt'
    if readme.is_file():
        write(docs / 'README.txt', readme.read_bytes())
    write(docs / 'copyright',
          b'Course content is packaged at the author\'s request; no new content license is granted.\n'
          b'Electron and Chromium licenses: /opt/cpp-backend-course-desktop/LICENSE and LICENSES.chromium.html.\n'
          b'React and font licenses accompany the bundled site/vendor files.\n')
    installed = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())
    debian = stage / 'DEBIAN'
    debian.mkdir()
    control = (
        'Package: ' + PACKAGE + '\nVersion: ' + version + '\n'
        'Section: education\nPriority: optional\nArchitecture: amd64\n'
        'Maintainer: C++ Backend Course <noreply@localhost>\n'
        'Depends: ' + ', '.join(DEPENDENCIES) + '\n'
        'Conflicts: cpp-backend-course-offline\nReplaces: cpp-backend-course-offline\n'
        'Installed-Size: ' + str((installed + 1023) // 1024) + '\n'
        'Description: Standalone offline C++ and backend textbook\n'
        ' Includes a private Electron runtime, the course, tests and local labs.\n'
        ' No browser, Node.js installation or local HTTP server is required.\n'
        ' User progress is stored separately; no automatic shell commands run.\n'
        ' External development tools and practice servers are not included.\n')
    write(debian / 'control', control.encode())
    sums = []
    for path in sorted(stage.rglob('*')):
        if path.is_file() and 'DEBIAN' not in path.relative_to(stage).parts:
            sums.append(hashlib.md5(path.read_bytes()).hexdigest() + '  ' + path.relative_to(stage).as_posix())
    write(debian / 'md5sums', ('\n'.join(sums) + '\n').encode())
    return {'course_version': content_metadata['version'], 'runtime_version': runtime_metadata['version'],
            'runtime_archive_sha256': runtime_metadata['archive_sha256'],
            'installed_bytes': installed, 'course_files': len(payload), 'app_sha256': app_hashes,
            'sandbox_helper_mode': 'root:root 4755 (as recorded in .deb data archive)'}


def build(site, runtime, output, version, app_dir=None, icons_dir=None):
    if not re.fullmatch(r'[0-9][0-9A-Za-z.+:~\-]*', version):
        raise ValueError('Invalid Debian package version')
    if not shutil.which('dpkg-deb'):
        raise ValueError('dpkg-deb is required only to build the package')
    output = checked_path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / (PACKAGE + '_' + version + '_amd64.deb')
    report_file = output / (target.name + '.json')
    if target.exists() or target.is_symlink() or report_file.exists() or report_file.is_symlink():
        raise ValueError('Refusing to overwrite an existing release artifact')
    with tempfile.TemporaryDirectory(prefix='cpp-course-electron-deb-') as temporary:
        stage = Path(temporary) / PACKAGE
        stage.mkdir()
        report = stage_package(stage, site, runtime, version, app_dir, icons_dir)
        command = ['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(stage), str(target)]
        subprocess.run(command, check=True, capture_output=True, text=True)
    report.update({'package': target.name, 'version': version, 'bytes': target.stat().st_size,
                   'sha256': digest(target.read_bytes()), 'system_install_performed': False})
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    parser.add_argument('--version', default=application_version())
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.site, args.runtime, args.output, args.version), ensure_ascii=False, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
