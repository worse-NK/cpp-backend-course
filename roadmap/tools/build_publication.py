#!/usr/bin/env python3
"""Build an allowlisted, source-free GitHub Pages release; never clean the workspace."""
import argparse
import hashlib
import io
import json
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
import zipfile

from build_cheatsheet import render as render_cheatsheet
from build_sources import render as render_sources
from build_sql_lab import render as render_sql_worker
from build_stations import html_for, validate
from checkpoint_data import with_checkpoints
from build_visual_labs import render as render_labs
from build_glossary import render as render_glossary, render_data as render_terms
from build_service_workshop import render as render_service_workshop
from build_traffic_examples import build as build_traffic_examples

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / 'publish' / 'github-pages'
ARCHIVE_NAME = 'cpp-backend-course.zip'
MANIFEST_NAME = 'publication-manifest.json'
INSTRUCTIONS_NAME = 'PUBLISH.txt'

# Deliberately not globbing the workspace: a future .env, report, binary, or test
# cannot silently become public. New learner downloads must be added explicitly.
PAGES = (
    'cpp_backend_roadmap.html', 'cpp_basic_level.html',
    'cpp_project_device_monitoring.html', 'cpp_station9_databases_intro.html',
    'object_lifetime_demo.html', 'sql_trainer.html', 'visual_labs.html',
)
ASSETS = (
    'home.css', 'station.css', 'station-app.js', 'cheatsheet.css', 'cheatsheet.js',
    'database-intro.css', 'database-route.js', 'sql-lab-core.js', 'sql-lab.css',
    'sql-lab.js', 'visual-lab-models.js', 'visual-labs.css', 'visual-labs.js',
    'terms-core.js', 'terms.js', 'terms.css', 'glossary.js', 'glossary.css',
    'service-workshop.js', 'service-workshop.css',
)
EXAMPLES = (
    'traffic-analysis/traffic_http_ok.pcap',
    'traffic-analysis/traffic_http_delay.pcap',
    'traffic-analysis/traffic_dns.pcap',
    'traffic-analysis/manifest.json', 'traffic-analysis/decoded.json',
    'traffic-analysis/README.txt',
    'station7-netlab/network_lab.sh', 'station7-netlab/udp_probe.cpp',
    'station7-netlab/filter.nft', 'station7-netlab/block.nft',
    'station7-netlab/snat.nft', 'station7-netlab/dnat.nft', 'station7-netlab/trace.nft',
    'station5-linux/pipe_capture.cpp', 'station5-linux/signal_wait.cpp',
    'station5-linux/mapped_generation.cpp', 'station6/state_architecture.cpp',
    'station3/request_arena.cpp', 'station5/loader_probe.cpp', 'station5/loader_value.cpp',
    'interview_gaps/capacity.js', 'interview_gaps/local_object.cpp',
    'interview_gaps/multicast.cpp', 'interview_gaps/spsc.cpp',
    'interview_gaps/stack_frame.cpp',
    'station9/CMakeLists.txt', 'station9/Dockerfile.verify', 'station9/README.md',
    'station9/main.cpp', 'station9/parking.cpp', 'station9/parking.sql',
    'station9/schema.sql', 'station9/verify.py',
    'station10/.dockerignore', 'station10/CMakeLists.txt',
    'station10/Dockerfile', 'station10/check.yml', 'station10/main.cpp',
    'service-workshop/CMakeLists.txt', 'service-workshop/app.cpp',
    'service-workshop/storage.hpp', 'service-workshop/storage.cpp',
    'service-workshop/tests.cpp', 'service-workshop/schema.sql',
    'service-workshop/Dockerfile', 'service-workshop/compose.yaml',
    'service-workshop/compose.https.yaml', 'service-workshop/Caddyfile',
    'service-workshop/.dockerignore', 'service-workshop/.gitignore',
    'service-workshop/init-db.sh', 'service-workshop/lab.py', 'service-workshop/load.py',
    'service-workshop/README.md',
    'service-workshop/release-lab/CMakeLists.txt',
    'service-workshop/release-lab/Dockerfile',
    'service-workshop/release-lab/client.cpp',
    'service-workshop/release-lab/001-initial.sql',
    'service-workshop/release-lab/002-expand-note.sql',
    'service-workshop/release-lab/init-db.sh',
    'service-workshop/release-lab/compose.yaml',
    'service-workshop/release-lab/release_lab.py',
    'service-workshop/release-lab/README.md',
    'service-workshop/release-lab/.dockerignore',
    'service-workshop/release-lab/.gitignore',
)
PUBLIC_README = '''# C++ и backend-разработка

Учебный маршрут для читателей с базовыми знаниями C/C++: классы и ресурсы,
STL, сборка, многопоточность, сети, API, SQL, PostgreSQL и эксплуатация сервиса.
Станции 0–10 включают 5Б (системное программирование Linux), 9A (SQL)
и 9B (PostgreSQL). После сборки пройдите 5Б перед многопоточностью и сетями.
После общих сетей есть 7Б — изолированная Linux-сетевая лаборатория.
Её root-настройки выполняются только внутри отдельной одноразовой VM со снимком,
не на рабочем компьютере или сервере. Чтение схем и моделей не требует запуска.
7В — необязательная станция по анализу трафика в Wireshark и TShark.
Её PCAP-файлы синтетические: байты и временные метки созданы для обучения,
это не измерения реального сервера. Разбор можно читать без установки Wireshark.

## Как открыть

Онлайн-адрес опубликованного сайта автор может указать в разделе About этого
репозитория. После скачивания и распаковки всего репозитория откройте `index.html`
в браузере. Один HTML без соседних папок не содержит весь учебник.

Страницы, тесты и лаборатории выполняются в браузере. React 18.3.1 загружается
с unpkg.com; Inter и JetBrains Mono — из Google Fonts (для шрифтов есть системная
замена). Поэтому полностью автономный режим для всего курса не заявляется.
SQL-тренажёр использует локальную SQLite/sql.js, а не сервер PostgreSQL.
Лицензия sql.js сохранена в `roadmap/vendor/sqljs/LICENSE`.

Прогресс хранится в браузере на текущем устройстве. Регистрации и серверной
синхронизации нет. Прогресс локальной file://-версии автоматически на сайт
не переносится; режим инкогнито и очистка данных браузера могут удалить отметки.
Для запуска C++-примеров и серверных практических работ нужна отдельная
локальная среда; необходимые версии и инструкции указаны в главах и примерах.

## Редактирование и сборка

В репозитории хранятся и готовые страницы, и редактируемые исходники:

- `roadmap/content/station*.json` — теория, основные тесты и задания;
- `roadmap/content/checkpoints/station*.json` — закрепления подглав;
- `roadmap/content/glossary.json` — определения терминов;
- `roadmap/content/service-workshop/` — исходники серверного практикума;
- `roadmap/assets/` — общий интерфейс, стили и интерактивные лаборатории;
- `roadmap/tools/` — сборщики, проверки и тесты.
- `roadmap/tests/` — исходники небольших C++/CMake-проектов для этих проверок.

Страницы станций и `roadmap/generated/` собираются из исходников; для правки
теории меняйте JSON, а не сгенерированный JS. Главная и базовый тест имеют
редактируемые данные прямо в своих HTML. Для сборки нужен Python 3.10+ без
сторонних Python-пакетов. Команды выполняются из корня клонированного репозитория:

```sh
python3 roadmap/tools/build_stations.py
python3 roadmap/tools/build_sources.py
python3 roadmap/tools/build_cheatsheet.py
python3 roadmap/tools/validate_materials.py
python3 roadmap/tools/build_publication.py
```

Последняя команда создаёт отдельно `publish/github-pages/` и ZIP сайта.
Эта компактная раздача не содержит исходников и тестовой инфраструктуры;
сам Git-репозиторий их сохраняет. Не указывайте Git checkout как `--output`
сборщика публикации. Если источники редактируются в отдельной рабочей папке,
обновляйте checkout вместе со всеми исходниками:

```sh
python3 roadmap/tools/sync_repository.py --repository /путь/к/checkout
```

Команда не удаляет файлы, не делает commit/push и отказывается перезаписывать
конфликтующие локальные правки. Если работа идёт прямо в клоне, укажите `.`:
она пересоберёт готовые страницы и сохранит исходники на месте.
Для полного набора тестов нужны C++-компилятор и стандартная библиотека
с поддержкой C++20 и `std::expected` из C++23, CMake/CTest, Ninja и GJS
(он запускает JS-тесты и часть проверок из Python).
Браузерные проверки, Docker/PostgreSQL и VM-приёмка требуют отдельной среды:
для обычного изменения текста и сборки сайта они не нужны.

```sh
python3 -m unittest discover -s roadmap/tools -p 'test_*.py'
gjs roadmap/tools/test_station_assessment.js
gjs roadmap/tools/test_assembly_ui.js
```

Кэши, пароли, временные VM-образы, внутренние отчёты и личные файлы автора
в Git не добавляются. Вендорная SQLite/sql.js с лицензией сохранена для
воспроизводимой сборки SQL-тренажёра.
Учебные примеры находятся в `roadmap/examples/`; этот префикс сохранён,
чтобы команды из глав работали после скачивания репозитория.

Сквозной серверный практикум: `roadmap/service_workshop.html`.
Один C++ API проходит путь от localhost до PostgreSQL и отдельной Linux-VM;
VPS/HTTPS — необязательная часть. Исходники: `roadmap/examples/service-workshop/`.
Секреты создаются читателем локально, в репозитории их нет. Учебник на Pages
не исполняет серверные команды и не размещает пользовательские API.
'''

INSTRUCTIONS = '''ПУБЛИКАЦИЯ УЧЕБНИКА НА GITHUB PAGES

Готовая папка: github-pages/
Архив той же папки: cpp-backend-course.zip
publication-manifest.json — локальный отчёт сборки, на GitHub он не нужен.

1. Создайте на GitHub новый публичный репозиторий, например cpp-backend-course.
   Не загружайте весь CPP_edu: в нём есть другие проекты и рабочие материалы.
   Бесплатный GitHub Pages требует публичного репозитория.
2. Через Add file → Upload files загрузите СОДЕРЖИМОЕ github-pages/, а не саму
   папку github-pages и не ZIP. В корне репозитория должны оказаться index.html,
   README.md, .nojekyll и папка roadmap/. Содержимое roadmap/ сохраните целиком.
   Если скрытый .nojekyll не попал в загрузку, добавьте его через Add file →
   Create new file. В файл можно поместить одну пустую строку.
3. Сохраните файлы коммитом в основную ветку (обычно main).
4. Settings → Pages → Build and deployment → Source: Deploy from a branch.
   Выберите ветку с файлами, папку /(root), нажмите Save.
5. Дождитесь успешной публикации во вкладке Actions. Адрес будет показан в
   Settings → Pages: https://ВАШ-ЛОГИН.github.io/ИМЯ-РЕПОЗИТОРИЯ/.
   HTTPS для github.io предоставляется автоматически. Компьютер можно выключить.
6. Откройте сайт и проверьте главную, станцию 0, SQL-тренажёр и лаборатории.
   Пришлите ссылку на репозиторий и, после публикации, адрес сайта.
   Пароли, токены, SSH-ключи и коды подтверждения присылать не нужно.

Для обновлений: измените рабочий курс и из корня CPP_edu запустите
python3 roadmap/tools/build_publication.py
Затем замените файлы в публичном репозитории актуальной сборкой. Сборщик
не удаляет рабочие материалы и откажется перезаписывать вручную изменённую
папку публикации. Править курс нужно в рабочих исходниках, не в github-pages/.

Страницы используют React с CDN; шрифты Google необязательны для работы.
Личные отметки локальной версии автоматически на новый домен не переносятся.
Сайт и его файлы будут общедоступны. Собственная лицензия курса автоматически
не назначалась; лицензии сторонних компонентов сохранены.
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_bytes(name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f'Unsafe source path: {name}')
    path = ROOT / name
    if any(p.is_symlink() for p in [path, *path.parents] if p != ROOT.parent):
        raise ValueError(f'Symlink is not a publication source: {name}')
    return path.read_bytes()


def entry_page():
    return '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>C++ и backend — учебный курс</title>
<meta http-equiv="refresh" content="0; url=roadmap/cpp_backend_roadmap.html">
<script>location.replace("roadmap/cpp_backend_roadmap.html" + location.search + location.hash);</script>
</head><body><p><a href="roadmap/cpp_backend_roadmap.html">Открыть учебник C++ и backend →</a></p></body></html>
'''


def collect():
    files = {'index.html': entry_page().encode(), '.nojekyll': b'\n',
             'README.md': PUBLIC_README.encode()}
    for name in (*PAGES, *(f'assets/{n}' for n in ASSETS),
                 *(f'examples/{n}' for n in EXAMPLES), 'vendor/sqljs/LICENSE'):
        files['roadmap/' + name] = source_bytes(name)
    stations = []
    for path in sorted((ROOT / 'content').glob('station*.json')):
        data = json.loads(source_bytes('content/' + path.name))
        validate(data, path)
        data = with_checkpoints(data)
        stations.append(data)
        filename = data['meta']['sourceFile']
        if PurePosixPath(filename).name != filename:
            raise ValueError(f'Unexpected station page: {filename}')
        files['roadmap/' + filename] = html_for(data).encode()
        files['roadmap/generated/' + data['meta']['id'] + '.data.js'] = (
            'window.STATION_DATA = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';\n').encode()
    for name, content in {
        'cpp_cheatsheet.html': render_cheatsheet(), 'sources.html': render_sources(),
        'generated/visual-labs.data.js': render_labs(),
        'generated/sql-lab-worker.data.js': render_sql_worker(),
        'glossary.html': render_glossary(), 'generated/terms.data.js': render_terms(),
        'service_workshop.html': render_service_workshop(),
    }.items():
        files['roadmap/' + name] = content.encode()
    return files, stations


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ('href', 'src'):
            if a.get(key):
                self.links.append((a[key], tag in ('script', 'link')))
        if tag == 'meta' and a.get('http-equiv', '').lower() == 'refresh':
            match = re.search(r'url\s*=\s*(.+)', a.get('content', ''), re.I)
            if match:
                self.links.append((match[1].strip(' \"\x27'), False))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def check_release(files, stations):
    # Never accidentally ship a real capture under a teaching filename. Only
    # the exact deterministic offline fixtures from the generator are allowed.
    traffic_captures = {'roadmap/examples/traffic-analysis/' + name: data
                        for name, data in build_traffic_examples().items()
                        if name.endswith('.pcap')}
    sections = {'roadmap/' + s['meta']['sourceFile']: {v['id'] for v in s['theory']}
                for s in stations}
    checked, external = 0, set()
    # Token boundaries avoid treating a short substring inside sql.js's encoded
    # SQLite binary as an AWS key. No entire file is exempted from scanning.
    # alice/demo are explicit teaching fixtures, not the machine's account.
    forbidden = re.compile(r'/(?:home|Users)/(?!alice/|demo/)[^/\s"<>]+/|file:///(?:home|Users)/|'
                           r'(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|'
                           r'github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})(?![A-Za-z0-9_])|'
                           r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')

    def check_url(base, href, resource=False):
        nonlocal checked
        url = urlsplit(href)
        if url.scheme in ('http', 'https') or url.netloc:
            if resource:
                external.add(href)
            return
        if url.scheme:
            raise ValueError(f'Unsupported local URL in {base}: {href}')
        if not url.path:
            target = base
        else:
            if url.path.startswith('/'):
                raise ValueError(f'Root URL breaks project Pages in {base}: {href}')
            target = posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(url.path)))
        if target not in files:
            raise ValueError(f'Missing published target in {base}: {href} -> {target}')
        # Exercise a project subpath, not only a domain-root deployment.
        resolved = urljoin('https://example.github.io/cpp-backend-course/' + base, href)
        if not urlsplit(resolved).path.startswith('/cpp-backend-course/'):
            raise ValueError(f'URL escaped project path: {href}')
        section = parse_qs(url.fragment).get('section', [])
        if target in sections and section and section[0] not in sections[target]:
            raise ValueError(f'Unknown theory section: {href}')
        checked += 1

    def check_html(base, value):
        parser = Links()
        parser.feed(value)
        for href, resource in parser.links:
            check_url(base, href, resource)

    for name, content in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or any(
                part in {'.git', '.aws', '.codex', '.agents', '__pycache__', 'content', 'tools', 'tests'}
                for part in path.parts):
            raise ValueError(f'Non-public file in release: {name}')
        if name in traffic_captures:
            if content != traffic_captures[name]:
                raise ValueError(f'Synthetic teaching capture differs from generator: {name}')
            # Latin-1 preserves every byte, including ASCII secrets/path markers;
            # binary files are not exempt from the privacy scan below.
            text = content.decode('latin-1')
        else:
            text = content.decode('utf-8')
        if forbidden.search(text):
            raise ValueError(f'Potential private path or credential in {name}; review locally')
        if len(content) > 25 * 1024 * 1024:
            raise ValueError(f'Too large for GitHub browser upload: {name}')
        if name.endswith('.html'):
            check_html(name, text)
        if name.endswith('.css'):
            for href in re.findall(r'url\(\s*[\"\x27]?([^\)\"\x27]+)', text):
                if not href.startswith('data:'):
                    check_url(name, href.strip(), True)
    for station in stations:
        base = 'roadmap/' + station['meta']['sourceFile']
        for text in strings(station):
            check_html(base, text)
    home = files['roadmap/cpp_backend_roadmap.html'].decode()
    data = json.loads(re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>', home, re.S)[1])
    for stage in data['stages']:
        check_url('roadmap/cpp_backend_roadmap.html', stage['station']['file'])
    for extra in data['bonusFiles']:
        check_url('roadmap/cpp_backend_roadmap.html', extra['file'])
    return {'local_links_checked': checked, 'external_runtime_resources': sorted(external)}


def write_release(output=DEFAULT_OUTPUT):
    output = Path(output).absolute()
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('Publication destination must not be a symlink')
    files, stations = collect()
    checks = check_release(files, stations)
    manifest_path = output.parent / MANIFEST_NAME
    archive_path = output.parent / ARCHIVE_NAME
    instructions_path = output.parent / INSTRUCTIONS_NAME
    for path in (manifest_path, archive_path, instructions_path):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f'Unsafe output file: {path.name}; nothing overwritten')
    if output.exists() and not output.is_dir():
        raise ValueError('Publication destination is not a directory; nothing overwritten')
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if output.exists():
        entries = list(output.rglob('*'))
        if any(p.is_symlink() for p in entries):
            raise ValueError('Publication folder contains a symlink; nothing overwritten')
        actual = {p.relative_to(output).as_posix(): p for p in entries if p.is_file()}
        if actual and (not previous or set(actual) != set(previous['files'])):
            raise ValueError('Unmanaged files in publication folder; nothing overwritten')
        for name, path in actual.items():
            if digest(path.read_bytes()) != previous['files'][name]['sha256']:
                raise ValueError(f'Publication file edited manually: {name}; nothing overwritten')
        if set(actual) - set(files):
            raise ValueError('Previous release has obsolete files; keep it separately before rebuilding')
    for path, key in [(archive_path, 'archive_sha256'), (instructions_path, 'instructions_sha256')]:
        if path.exists() and (not previous or digest(path.read_bytes()) != previous[key]):
            raise ValueError(f'Unmanaged or edited output: {path.name}; nothing overwritten')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo('github-pages/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    packed = archive.getvalue()
    report = {'format': 1, 'station_count': len(stations), 'file_count': len(files),
              'uncompressed_bytes': sum(map(len, files.values())), 'archive_bytes': len(packed),
              'archive_sha256': digest(packed), 'instructions_sha256': digest(INSTRUCTIONS.encode()),
              'files': {n: {'bytes': len(v), 'sha256': digest(v)} for n, v in sorted(files.items())},
              **checks, 'browser_visual_check': 'not_performed',
              'excluded': ['working JSON sources', 'generators and tests', 'audit reports',
                           'interview source document', 'caches', 'other workspace projects']}
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    archive_path.write_bytes(packed)
    instructions_path.write_text(INSTRUCTIONS)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = write_release(args.output)
    print(f"Built {result['station_count']} stations, {result['file_count']} public files; "
          f"{result['local_links_checked']} local links checked")
    print(f"ZIP: {result['archive_bytes']:,} bytes; external runtime resources: "
          f"{len(result['external_runtime_resources'])}")
