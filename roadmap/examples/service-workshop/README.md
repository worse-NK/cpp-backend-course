# C++ service workshop

Учебный сервис `course_tasks`: C++ HTTP API, memory/PostgreSQL, Docker Compose и
необязательный Caddy HTTPS. Полный маршрут и задания — в практикуме курса.
Команды ниже выполняются из этой директории; Python 3 и инструменты C++ уже
должны быть доступны. Скрипт ничего не устанавливает и не вызывает Docker/SSH.

## Локально, без базы

```sh
python3 lab.py init
python3 lab.py check-env
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel 2
python3 lab.py run
```

В другом терминале из той же директории:

```sh
curl --noproxy 127.0.0.1 --connect-timeout 2 --max-time 5 http://127.0.0.1:8080/health/ready
curl --config .secrets/client.curl http://127.0.0.1:8080/tasks
```

`run` всегда выбирает `127.0.0.1`, memory и порт 8080 (либо `--port 18080`).
`Ctrl-C` останавливает процесс; память теряет задачи после перезапуска.
Первичная CMake-конфигурация скачивает закреплённые зависимости. Все `/tasks`
запросы требуют Bearer-токен; публичны только общие health-ответы.
Генерируемый `client.curl` содержит `noproxy = "127.0.0.1,localhost,::1"`:
локальный HTTP-запрос с токеном не должен уходить через прокси из окружения
пользователя. Для других адресов, включая публичный HTTPS, это правило не
отключает настроенный прокси. Уже существующие приватные файлы `init` не меняет.

Успешный PUT возвращает JSON с управляемыми сервером `id`/`version`, но **без
ETag/Last-Modified**: представление преобразуется (RFC 9110 §9.3.4). Актуальная
метка берётся отдельным GET; If-Match всё равно проверяется атомарно при записи.
Простой формат `"vN"` — ограниченный учебный договор. После потери memory-store
старые ID и метки необходимо отбросить: локальные счётчики не защищают клиента
между разными историями хранилища. Согласованные валидаторы при восстановлении,
нескольких экземплярах и изменении сериализации требуют отдельной политики.

## Контейнеры — только по явной команде пользователя

Если Docker Engine и Compose v2 уже настроены на вашем компьютере:

```sh
python3 lab.py check-env
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail 50 app
docker compose down
```

Приложение работает как UID/GID 65532 и публикуется **только** на
`127.0.0.1:8080`. PostgreSQL 18 не публикует порт и находится в отдельной
`internal`-сети; приложение дополнительно подключено к bridge-сети `edge`.
`internal` запрещает внешнюю связность именно этой сети, но не является
межсетевым экраном для сервиса, подключённого ещё и к `edge`.

Именованный `pgdata` смонтирован в `/var/lib/postgresql` — корректный путь для
PostgreSQL 18+. Bootstrap создаёт схему и отдельную роль `course_app` с правами
только на работу с задачами и их sequence. Администратор `postgres` не передаётся
приложению. Init-скрипт выполняется **только для пустого volume**. Изменение
`.env`, `schema.sql` или перезапуск не меняют существующие пароли/схему. Это не
система миграций. `down` сохраняет данные; не добавляйте `-v`, если данные нужны.

## Измерение и совместимый выпуск

На своём запущенном локальном API выполни `python3 load.py`: клиент делает только
ограниченное число `GET /tasks`, не пишет данные, читает токен из приватного
`.secrets/client.curl` и показывает отдельные baseline/load/recovery. Полный
разбор измеряемых границ находится в практикуме, шаг «Измеряем свой API».
`handler_us` в безопасных серверных логах — интервал нашего обработчика;
`storage_us` — вложенный вызов хранилища, а не исключительно время SQL.
Очередь workers, чтение HTTP и отправка ответа в эти поля не входят.
Отказы до обработчика обозначены `not_measured`, а не старым измерением
предыдущего запроса. Запись статуса в лог не доказывает доставку ответа клиенту.

Отдельный каталог `release-lab/` — лаборатория двух C++-бинарников и расширяемой
схемы PostgreSQL. Она находится в полной копии репозитория/учебника, не входит
в минимальный архив `lab.py pack` для переноса основного HTTP-сервиса.
Это не автоматическая миграция рабочей базы Task API и не rolling HTTP deploy.

## Секреты и упаковка

`init` генерирует три независимых случайных 64-hex значения: `APP_TOKEN`,
`POSTGRES_PASSWORD`, `APP_DB_PASSWORD`. `.env` и curl-конфиг создаются с 0600,
`.secrets` — с 0700. Существующие файлы и симлинки не перезаписываются;
помощник не выводит секреты и не интерпретирует `.env` как shell-код.
Каталоги `.secrets*` (включая `.secrets-vm` и `.secrets-vps`), `backups/` и
файлы `*.dump` исключены из Git и Docker build context. Секреты и резервные
копии всё равно хранятся локально: ignore-правило не шифрует и не удаляет их.

Это учебная передача секретов через environment: владелец Docker daemon/root
может прочитать их через inspect и окружение контейнеров. Не выводите
`docker compose config` без `--quiet`, `env`, curl `-v`, `.env` или client.curl
в чат, логи и скриншоты. Не отправляйте токен по публичному HTTP; только по
локальному loopback, SSH-туннелю или проверенному HTTPS. Ротация существующей
БД требует отдельного административного действия, не удаления `.env`.
Compose предпочитает уже экспортированные переменные окружения значениям
из `.env`: не экспортируйте эти три имени из старых экспериментов. Проверка
`lab.py check-env` проверяет именно файл и не раскрывает значения.

```sh
python3 lab.py pack
```

Создаёт `service-workshop-source.tar.gz` только из явного списка исходников и
конфигураций; `.env`, `.secrets`, build и Git туда не попадают. Существующий
архив не заменяется (можно выбрать новое имя: `--output workshop-v2.tar.gz`).
Никакая загрузка на сервер не выполняется. На своей целевой машине секреты
создаются заново командой `python3 lab.py init`.

## Необязательный публичный HTTPS

Только на подготовленном сервере, которым вы управляете: реальный домен с
правильными A/AAAA, входящие TCP 80/443 и доступ Caddy к ACME. Не включайте слой
на случайном VPS и не отправляйте учебный токен до проверки HTTPS.
`COURSE_DOMAIN` и `ACME_EMAIL` передаются отдельно; не добавляйте их в строгий
файл `.env`, который читает `lab.py`.

```sh
COURSE_DOMAIN=tasks.example.org ACME_EMAIL=admin@example.org docker compose -f compose.yaml -f compose.https.yaml config --quiet
COURSE_DOMAIN=tasks.example.org ACME_EMAIL=admin@example.org docker compose -f compose.yaml -f compose.https.yaml up --build -d
```

Замените домен и email на свои. Overlay публикует 80/443, сохраняет loopback-порт
приложения и проксирует на `app:8080`; Caddy ограничивает тело запроса 16KB.
Сертификаты хранятся в `caddy_data`. Получение публичного сертификата не входит
в локальную автоматическую проверку. Не используйте `curl -k` как «исправление»
ошибки сертификата.

Основания конфигурации: [Compose networking](https://docs.docker.com/compose/how-tos/networking/),
[PostgreSQL official image](https://hub.docker.com/_/postgres),
[psql quoting](https://www.postgresql.org/docs/18/app-psql.html#APP-PSQL-INTERPOLATION),
[Caddy HTTPS](https://caddyserver.com/docs/automatic-https),
[Caddy request body limit](https://caddyserver.com/docs/caddyfile/directives/request_body),
[CMake CLI](https://cmake.org/cmake/help/latest/manual/cmake.1.html).


Выбор C++20 или C++23 для локальной CMake-сборки
------------------------------------------------
По умолчанию проект остаётся на C++20. Для сравнения режимов используйте
разные каталоги сборки; команды выполняются в каталоге этого проекта:

    cmake -S . -B build-cxx20 -DCOURSE_CXX_STANDARD=20
    cmake --build build-cxx20
    cmake -S . -B build-cxx23 -DCOURSE_CXX_STANDARD=23
    cmake --build build-cxx23

COURSE_CXX_STANDARD допускает только 20 или 23. CMake требует выбранный
стандарт без перехода на более ранний и отключает расширения языка. Уже
существующие build-каталоги, настройки lab.py и контейнерные образы команды
выше не меняют. В каждый новый каталог отдельно передавайте нужные флаги
необязательных адаптеров из инструкции выше и установите указанные зависимости.

Для отдельного компилятора добавьте при ПЕРВОЙ настройке нового build-каталога:

    -DCMAKE_CXX_COMPILER=/absolute/path/to/g++

Не подменяйте компилятор в старом CMake cache. Сам режим -std=c++23 не обновляет
стандартную библиотеку и не доказывает поддержку всех возможностей C++23.
Текущие базовые исходники сохраняют требования C++20; поддержку нужных функций
и совместимость зависимостей проверяют для конкретной сборки. Это не перевод
Docker-образов или внешних SDK на другую версию.

После сборки проверьте зарегистрированные тесты отдельно в каждом режиме:

    ctest --test-dir build-cxx20 --output-on-failure
    ctest --test-dir build-cxx23 --output-on-failure

Необязательное упражнение C++23 не изменяет Storage, HTTP-маршруты и запущенный
сервер. Оно собирает отдельную программу examples/cpp23/s8-expected-http.cpp.
Запускайте из полного репозитория курса, чтобы соседний файл существовал:

    cmake -S . -B build-expected -DCOURSE_CXX_STANDARD=23 -DCOURSE_BUILD_CPP23_EXAMPLES=ON
    cmake --build build-expected --target course_expected_http
    ctest --test-dir build-expected -R course_expected_http_contract --output-on-failure

Для этого упражнения нужна библиотека с __cpp_lib_expected >= 202211L
(не только базовый expected, но и and_then/transform). Компилятор выбирается
флагом CMAKE_CXX_COMPILER при первом configure, как показано выше. Настройка
всего workshop по-прежнему требует его закреплённых HTTP/JSON-зависимостей;
чтобы проверить только упражнение без скачивания SDK, достаточно прямой сборки
из корня репозитория:

    g++ -std=c++23 roadmap/examples/cpp23/s8-expected-http.cpp -o expected-http
    ./expected-http

Вывод содержит шесть строк с кодами 200/400/422; сами запросы в сеть не уходят.

Основание выбора режима CMake 3.24:
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD.html
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD_REQUIRED.html
https://cmake.org/cmake/help/v3.24/variable/CMAKE_CXX_COMPILER.html
