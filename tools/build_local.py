#!/usr/bin/env python3
"""Build a source-free, offline browser copy using the pinned desktop vendors.

This is not the Electron application: no desktop controls, profile API or runtime
are injected. The shared course data, JavaScript and CSS remain unchanged.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'local-build.json'
ARCHIVE = 'cpp-backend-course-local.zip'
DEFAULT_OUTPUT = ROOT / 'build/local'
README = '''C++ и backend — локальная браузерная версия
===========================================

В этой папке находится готовый учебник: страницы, тесты, встроенные схемы,
SQL-тренажёр, скрипты и шрифты. Для чтения и встроенных заданий интернет
не нужен. Внешние статьи и установка инструментов для настоящих серверных
лабораторных остаются отдельными действиями и могут требовать сети.

Как открыть
-----------
Распакуйте весь архив. Откройте терминал именно в этой папке — рядом с
index.html и local-build.json — и выполните:

  python3 -m http.server 8000 --bind 127.0.0.1

Затем откройте в своём браузере:

  http://127.0.0.1:8000/

Не запускайте эту команду из домашней папки: она раздаёт файлы текущего
каталога. Параметр --bind ограничивает доступ этим компьютером. Пока вы
читаете курс, оставьте терминал открытым; Ctrl+C остановит сервер.
Это только раздача готовых файлов, а не backend-сервис из учебных заданий.
Открытие index.html через file:// может ограничить работу SQL-worker,
поэтому для этой версии рекомендуется указанный локальный HTTP-адрес.

Где прогресс
------------
Отметки и SQL-черновики хранятся в профиле браузера, а не внутри этой папки
или архива. Используйте тот же браузер и тот же адрес с портом 8000.
Другой порт, имя localhost вместо 127.0.0.1 или отдельный профиль браузера
создают другой адрес хранения. Сайт и Electron-приложение автоматически
с этой копией не синхронизируются. Очистка данных браузера может удалить
сохранённые отметки.

В этом архиве нет Electron, установщика, личного профиля или исходников
сборщика. Манифест local-build.json содержит состав и контрольные суммы
этой копии. Исходники и инструкции сборки всех вариантов находятся в:

  https://github.com/worse-NK/cpp-backend-course
'''


def desktop_adapter():
    name = '_course_local_desktop_builder'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / 'desktop-course/build_site.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    return (isinstance(name, str) and bool(name) and '\\' not in name and '%' not in name
            and not PurePosixPath(name).is_absolute()
            and all(part not in ('', '.', '..') for part in name.split('/'))
            and not any(ord(char) < 32 or ord(char) == 127 for char in name))


def checked_path(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Symlinks and parent traversal are not accepted in output paths')
    return path


def collect():
    adapter = desktop_adapter()
    original, stations = adapter.publication.collect()
    checks = adapter.publication.check_release(original, stations)
    files = {name: adapter.localize(name, data, controls=False) if name.endswith('.html') else data
             for name, data in original.items() if name != 'README.md'}
    files.update(adapter.vendor_files())
    files['README.txt'] = README.encode()
    runtime_links = adapter.check_local(files)
    version = digest(json.dumps({name: digest(data) for name, data in sorted(files.items())},
                                sort_keys=True).encode())[:20]
    manifest = {
        'format': 1, 'mode': 'offline-browser', 'version': version,
        'stationCount': len(stations), 'fileCount': len(files) + 1,
        'externalRuntimeResources': [], 'runtimeLinksChecked': runtime_links,
        'originalBrowserLinksChecked': checks['local_links_checked'],
        'files': {name: {'bytes': len(data), 'sha256': digest(data)}
                  for name, data in sorted(files.items())},
    }
    files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return files, manifest


def read_payload(directory):
    """Validate all bytes before serving or replacing a previous local build."""
    directory = checked_path(directory)
    manifest_path = checked_path(directory / MANIFEST)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    entries = manifest.get('files') if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get('format') != 1 or manifest.get('mode') != 'offline-browser'
            or not isinstance(entries, dict) or 'index.html' not in entries):
        raise ValueError('Invalid local-build.json')
    if (not isinstance(manifest.get('version'), str)
            or not re.fullmatch(r'[a-f0-9]{20}', manifest['version'])
            or manifest.get('fileCount') != len(entries) + 1):
        raise ValueError('Invalid local build version or file count')
    payload = {}
    for name, metadata in entries.items():
        if not safe_name(name) or not isinstance(metadata, dict):
            raise ValueError('Unsafe local build file metadata')
        target = checked_path(directory / name)
        if not target.is_file():
            raise ValueError('Missing local build file: ' + name)
        data = target.read_bytes()
        if len(data) != metadata.get('bytes') or digest(data) != metadata.get('sha256'):
            raise ValueError('Manual changes in local output: ' + name)
        payload[name] = data
    found = list(directory.rglob('*'))
    if any(item.is_symlink() or not (item.is_file() or item.is_dir()) for item in found):
        raise ValueError('Symlinks and special files in local output are refused')
    actual = {item.relative_to(directory).as_posix() for item in found if item.is_file()}
    if actual != set(entries) | {MANIFEST}:
        raise ValueError('Unmanaged or missing files in local output')
    payload[MANIFEST] = manifest_bytes
    return payload, manifest


def archive_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            if not safe_name(name):
                raise ValueError('Unsafe local archive file name')
            entry = zipfile.ZipInfo('cpp-backend-course-local/' + name,
                                    date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def write_site(output=DEFAULT_OUTPUT, archive=None):
    output = checked_path(output)
    protected = [ROOT, *ROOT.parents]
    sources = [ROOT / name for name in ('roadmap', 'desktop-course', 'tools', 'docs', '.git')]
    if output in protected or any(output == item or item in output.parents for item in sources):
        raise ValueError('Local output must not overwrite repository sources or a parent directory')
    if output.exists() and not output.is_dir():
        raise ValueError('Local output is not a directory')
    files, manifest = collect()
    previous = None
    if output.exists():
        found = list(output.rglob('*'))
        if found:
            previous, _ = read_payload(output)
            if set(previous) - set(files):
                raise ValueError('Obsolete files in previous local build; choose a new output directory')
    packed = None
    if archive is not None:
        archive = checked_path(archive)
        if (archive == output or output in archive.parents or archive in protected
                or any(archive == item or item in archive.parents for item in sources)):
            raise ValueError('Local ZIP must be outside the generated site and source folders')
        packed = archive_bytes(files)
        if archive.exists():
            if not archive.is_file():
                raise ValueError('Local archive destination is not a regular file')
            current = archive.read_bytes()
            if current != packed and (previous is None or current != archive_bytes(previous)):
                raise ValueError('Unmanaged or edited local ZIP; nothing overwritten')
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if archive is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(packed)
    return manifest
