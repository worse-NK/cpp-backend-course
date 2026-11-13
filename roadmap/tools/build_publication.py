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
from build_security_sql_demo import render as render_security_sql_worker
from build_stations import html_for, validate
from checkpoint_data import with_checkpoints
from build_visual_labs import render as render_labs
from build_glossary import render as render_glossary, render_data as render_terms
from build_service_workshop import render as render_service_workshop
from build_traffic_examples import build as build_traffic_examples
from build_distributed_lab import render as render_distributed_lab
from course_theme import decorate_html, SUPPORT_PAGES

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
    'security_sql_demo.html', 'security_labs.html', 'distributed_lab.html',
)
ASSETS = (
    'home.css', 'station.css', 'station-app.js', 'cheatsheet.css', 'cheatsheet.js',
    'course-ui.css', 'course-reader.css', 'station-map.css', 'station-map-joints.css',
    'course-theme.css', 'course-dark-surfaces.css', 'course-dark-reader.css', 'course-code.js', 'course-code.css',
    'database-intro.css', 'database-route.js', 'sql-lab-core.js', 'sql-lab.css',
    'sql-lab.js', 'visual-lab-models.js', 'visual-labs.css', 'visual-labs.js',
    'terms-core.js', 'terms.js', 'terms.css', 'glossary.js', 'glossary.css',
    'service-workshop.js', 'service-workshop.css',
    'security-sql-demo.css', 'security-sql-demo.js',
    'security-sql-model.js', 'security-sql-worker.js',
    'security-lab-models.js', 'security-labs.js', 'security-labs.css',
    'distributed-lab-model.js', 'distributed-lab.js', 'distributed-lab.css',
)
HIGHLIGHT_ASSETS = (
    'highlight.min.js', 'http.min.js', 'cmake.min.js', 'dockerfile.min.js', 'nginx.min.js', 'LICENSE', 'ORIGIN.json',
)
EXAMPLES = (
    'sql-design/README.md', 'sql-design/history.sql', 'sql-design/model.sql',
    'sql-design/observe.sql', 'sql-design/run.sql',
    'query-execution/README.md', 'query-execution/join-query.sql',
    'query-execution/joins-plans.sql', 'query-execution/joins-setup.sql',
    'query-execution/memory-plans.sql', 'query-execution/memory-setup.sql',
    'query-execution/run.sql', 'query-execution/statistics.sql',
    'tooling-closed-loop/CMakeLists.txt', 'tooling-closed-loop/README.txt',
    'tooling-closed-loop/conan/app/CMakeLists.txt',
    'tooling-closed-loop/conan/app/conanfile.py', 'tooling-closed-loop/conan/app/main.cpp',
    'tooling-closed-loop/conan/conan.lock.json',
    'tooling-closed-loop/conan/library/CMakeLists.txt',
    'tooling-closed-loop/conan/library/conanfile.py',
    'tooling-closed-loop/conan/library/include/task_label.hpp',
    'tooling-closed-loop/conan/library/src/task_label.cpp',
    'tooling-closed-loop/conan/profiles/linux-gcc13.txt',
    'tooling-closed-loop/conan/requirements-conan.txt',
    'tooling-closed-loop/perf-vm-evidence.json', 'tooling-closed-loop/perf_workload.cpp',
    'tooling-closed-loop/report_before.cpp', 'tooling-closed-loop/report_fixed.cpp',
    'bounded-asio/CMakeLists.txt', 'bounded-asio/README.txt', 'bounded-asio/resolve.cpp',
    'bounded-asio/server.cpp', 'bounded-asio/verify.py',
    'tcp-observation/README.txt', 'tcp-observation/build_vm.py',
    'tcp-observation/captures/baseline.pcap', 'tcp-observation/captures/delay.pcap',
    'tcp-observation/captures/loss.pcap', 'tcp-observation/captures/report.json',
    'tcp-observation/captures/slow-reader.pcap', 'tcp-observation/experiment.py',
    'tcp-observation/guest_init.sh', 'tcp-observation/run_vm.py',
    'station16/README.txt', 'station16/history_checker.cpp', 'station16/workflow_recovery.py',
    'unix-ipc/CMakeLists.txt', 'unix-ipc/README.txt', 'unix-ipc/descriptor_transfer.cpp',
    'unix-ipc/ipc_common.hpp', 'unix-ipc/socketpair_stream.cpp',
    'network-specialization/README.txt', 'network-specialization/build_vm.py',
    'network-specialization/guest.py', 'network-specialization/init.sh',
    'network-specialization/run_vm.py',
    'cpp-foundations/global-lifetime/runtime.hpp',
    'cpp-foundations/global-lifetime/runtime.cpp',
    'cpp-foundations/global-lifetime/main.cpp',
    'cpp-foundations/global-lifetime/README.txt',
    'cpp23/s7-endian-frame.cpp', 'cpp23/s8-expected-http.cpp',
    'cpp23/s15-endian-regression.cpp', 'cpp23/README.md', 'station10/README.md',
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
    'service-workshop/production-path-lab/.dockerignore',
    'service-workshop/production-path-lab/.gitignore',
    'service-workshop/production-path-lab/CMakeLists.txt',
    'service-workshop/production-path-lab/Dockerfile',
    'service-workshop/production-path-lab/README.md',
    'service-workshop/production-path-lab/acceptance.py',
    'service-workshop/production-path-lab/api.cpp',
    'service-workshop/production-path-lab/common.cpp',
    'service-workshop/production-path-lab/common.hpp',
    'service-workshop/production-path-lab/compose.yaml',
    'service-workshop/production-path-lab/init-db.sh',
    'service-workshop/production-path-lab/lab.py',
    'service-workshop/production-path-lab/main.cpp',
    'service-workshop/production-path-lab/messaging.cpp',
    'service-workshop/production-path-lab/replication_lab.py',
    'service-workshop/production-path-lab/schema.sql',
    'service-workshop/production-path-lab/test_lab.py',
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
    'station11/CMakeLists.txt', 'station11/README.txt', 'station11/compose.yaml',
    'station11/delivery_model.cpp', 'station11/kafka_roundtrip.cpp',
    'station11/rabbit_roundtrip.cpp', 'station11/rabbit_api.py',
    'station12/.dockerignore', 'station12/.env.example', 'station12/.gitignore',
    'station12/CMakeLists.txt', 'station12/Dockerfile', 'station12/README.md',
    'station12/cache_client.cpp', 'station12/cache_model.cpp', 'station12/compose.yaml',
    'station12/lab.py', 'station12/rate_limit.lua', 'station12/redis.conf',
    'station12/release_lock.lua',
    'station13/.dockerignore', 'station13/.gitignore', 'station13/CMakeLists.txt',
    'station13/Dockerfile', 'station13/README.txt', 'station13/app.cpp',
    'station13/configmap.json', 'station13/deployment.json', 'station13/drain_model.cpp',
    'station13/hpa-example.json', 'station13/kind.yaml', 'station13/namespace.json',
    'station13/networkpolicy-example.json', 'station13/pdb-example.json',
    'station13/role-example.json', 'station13/service.json', 'station13/verify.py',
    'station14/.dockerignore', 'station14/.gitignore', 'station14/CMakeLists.txt',
    'station14/Dockerfile', 'station14/README.txt', 'station14/alerts.yaml',
    'station14/app.cpp', 'station14/collector.yaml', 'station14/compose.yaml',
    'station14/dashboard.json', 'station14/dashboards.yaml', 'station14/datasource.yaml',
    'station14/lab.py', 'station14/metrics.hpp', 'station14/metrics_model.cpp',
    'station14/prometheus.yaml',
    'security_sql_demo.cpp',
    'station15/README.txt', 'station15/CMakeLists.txt',
    'station15/access_policy.cpp', 'station15/access_policy_test.cpp',
    'station15/frame_parser.hpp', 'station15/frame_parser_test.cpp',
    'station15/frame_fuzz.cpp', 'station15/verify_security_evidence.py',
    'station15/outbound-policy.example.json', 'station15/network-evidence.example.json',
    'station15/delivery-policy.example.json', 'station15/release-evidence.example.json',
)
PUBLIC_README = '''# C++ и backend-разработка

Учебный маршрут для читателей с базовыми знаниями C/C++: классы и ресурсы,
STL, сборка, многопоточность, сети, API, SQL, PostgreSQL и эксплуатация сервиса.
Станции 0–16 включают 5Б (системное программирование Linux), 9A (SQL)
и 9B (PostgreSQL). После сборки пройдите 5Б перед многопоточностью и сетями.
После общих сетей есть 7Б — изолированная Linux-сетевая лаборатория.
Её root-настройки выполняются только внутри отдельной одноразовой VM со снимком,
не на рабочем компьютере или сервере. Чтение схем и моделей не требует запуска.
7В — необязательная станция по анализу трафика в Wireshark и TShark.
Прежние traffic-analysis/*.pcap синтетические: байты и метки созданы для обучения.
Новые tcp-observation/captures/*.pcap записаны в настоящем учебном TCP-обмене
в изолированной offline VM; условия и границы отдельно указаны в README/отчёте.
Ни те, ни другие файлы не являются захватом рабочего пользовательского сервиса.
Разбор можно читать без установки Wireshark.

Backend-ветка продолжается после станции 10: 11 — Kafka/RabbitMQ, 12 — Redis,
13 — Kubernetes, 14 — Prometheus/Grafana/OpenTelemetry/Jaeger. Каждая глава
начинается с основ и содержит самостоятельные локальные лабораторные,
скачиваемые C++-проекты и отдельные модели, не требующие сервера.
Ограничения и версии закреплены в README соответствующего examples/stationN.
Дополнительная часть service_workshop.html#production связывает вход, права,
PostgreSQL/outbox/RabbitMQ и постоянный receipt, затем отдельно проверяет
ручное переключение и пересоздание копии PostgreSQL. Это новый локальный стенд,
не обновление прежнего Task API и не промышленная HA-система.
Docker-лаборатории требуют собственного доступного движка; Kubernetes — своего
локального kind-кластера и отдельного kubeconfig. Не используйте рабочие
контексты, серверы, базы и секреты. Чтение, тесты и схемы не требуют контейнеров.

15 — безопасность backend-сервиса: вход и права, недоверенные данные,
исходящие запросы, TLS, секреты, выпуск и C++-обработчики. Её можно проходить
после основных станций 7–10, без предварительного изучения Kafka или Kubernetes.
SQL-лаборатория `roadmap/security_sql_demo.html` выполняет запросы на локальной
SQLite в браузере. `roadmap/security_labs.html` содержит подготовленные модели
доступа, исходящих запросов и TLS: они не отправляют сетевые запросы, не проверяют
настоящие сертификаты и не применяют правила сервера. Обе страницы используют
локальные скрипты и стили; работа моделей не требует сервера или внешнего fetch.
Файлы политик и отчётов в `roadmap/examples/station15/` проверяются отдельно;
корректная структура JSON не доказывает применение защиты в работающей системе.

16 — распределённые системы: истории операций, согласованность, Raft,
время и владение, шардирование и восстановление многошагового процесса.
distributed_lab.html показывает три подготовленные истории, а не исполняет
настоящий протокол или платёж. Отдельные C++ и Python/SQLite-примеры запускаются
локально. Необязательные UNIX IPC, VLAN/STP и OSPF/BGP расширяют Linux/сетевой
маршрут; их вопросы не включаются в обязательный итоговый тест станции.

## Как открыть

Онлайн-адрес опубликованного сайта автор может указать в разделе About этого
репозитория. После скачивания и распаковки всего репозитория откройте `index.html`
в браузере. Один HTML без соседних папок не содержит весь учебник.

Страницы, тесты и интерактивные учебные модели выполняются в браузере;
серверные лабораторные запускаются отдельно, по инструкциям. React 18.3.1 загружается
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
python3 roadmap/tools/build_home_metadata.py
python3 roadmap/tools/build_sources.py
python3 roadmap/tools/build_cheatsheet.py
python3 roadmap/tools/build_security_sql_demo.py
python3 roadmap/tools/build_distributed_lab.py
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
с поддержкой используемых средств C++20/23, CMake/CTest, Ninja и GJS
(он запускает JS-тесты и часть проверок из Python).
Проверки новых листингов запускаются отдельно: `CXX=g++-15 python3
roadmap/tools/cpp_examples.py --require-supported`. Указывайте фактический
путь к компилятору; один номер версии не гарантирует наличие всех библиотек.
Матрица этих проверок — `roadmap/content/cpp-examples.json`.
Для C++23-программ визуальных лабораторий также задайте `CXX23`.
Отсутствующая возможность отмечается как UNSUPPORTED, а не успешный пропуск.
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
                 *(f'examples/{n}' for n in EXAMPLES), 'vendor/sqljs/LICENSE',
                 *(f'vendor/highlightjs/{name}' for name in HIGHLIGHT_ASSETS)):
        content = source_bytes(name)
        if name in SUPPORT_PAGES:
            content = decorate_html(content.decode(), page=SUPPORT_PAGES[name]).encode()
        files['roadmap/' + name] = content
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
        'generated/security-sql-worker.data.js': render_security_sql_worker(),
        'glossary.html': render_glossary(), 'generated/terms.data.js': render_terms(),
        'service_workshop.html': render_service_workshop(),
        'distributed_lab.html': render_distributed_lab(),
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
    # Never ship an arbitrary capture. Older fixtures are deterministic and
    # synthetic; these four new real experiments are individually allowlisted
    # and bound to their reviewed report hashes. Keep their provenance distinct.
    traffic_captures = {'roadmap/examples/traffic-analysis/' + name: data
                        for name, data in build_traffic_examples().items()
                        if name.endswith('.pcap')}
    report_name = 'roadmap/examples/tcp-observation/captures/report.json'
    if files.get(report_name) != source_bytes('examples/tcp-observation/captures/report.json'):
        raise ValueError('Real TCP capture manifest differs from reviewed experiment')
    report = json.loads(files[report_name])
    expected_real = {'baseline.pcap', 'delay.pcap', 'loss.pcap', 'slow-reader.pcap'}
    observed_real = {s['capture'][0]['file']: s['capture'][0]
                     for s in report['scenarios']}
    if set(observed_real) != expected_real or report['environment']['external_nic']:
        raise ValueError('Unexpected real TCP capture provenance')
    real_captures = {'roadmap/examples/tcp-observation/captures/' + name: capture
                     for name, capture in observed_real.items()}
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
        elif name in real_captures:
            capture = real_captures[name]
            if (hashlib.sha256(content).hexdigest() != capture['sha256']
                    or len(content) != capture['bytes'] or capture['socket_drops'] != 0):
                raise ValueError(f'Real TCP capture differs from reviewed experiment: {name}')
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
