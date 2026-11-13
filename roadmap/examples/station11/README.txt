СТАНЦИЯ 11. ЛОКАЛЬНАЯ ЛАБОРАТОРИЯ СООБЩЕНИЙ

Что здесь можно проверить

1. Без Docker: повтор одного события в запускаемой C++-модели.
2. С Docker: независимое чтение Kafka-истории разными группами.
3. С Docker: маршрутизацию RabbitMQ и возврат полученной доставки.
4. При отдельно доступных SDK: реальные C++-клиенты Kafka и AMQP.

Это два независимых ОДНОУЗЛОВЫХ брокера. Они не пересылают данные друг
другу. Kafka имеет RF=1, RabbitMQ — quorum queue с одним участником.
Ни один опыт не проверяет отказоустойчивость нескольких машин.

30.10.2026 этот одноузловой стенд реально запущен: проверены
независимое чтение Kafka и повторная доставка RabbitMQ через командные
клиенты, HTTP и AMQP. Это не проверка отказоустойчивости нескольких машин.
Проверка Compose без запуска и C++-модель сами по себе не заменяют такой опыт.
Наблюдения ниже — критерии для самостоятельной проверки, не измерения вашей машины.

Файлы положи вместе в НОВУЮ отдельную папку:
  compose.yaml, CMakeLists.txt, delivery_model.cpp,
  kafka_roundtrip.cpp, rabbit_roundtrip.cpp, rabbit_api.py, README.txt.
Ничего не копируй поверх чужих лабораторий. Образы закреплены тегом и
проверенным digest: Apache Kafka 4.1.2 и RabbitMQ 4.3.6-management.
Docker скачает заметный объём данных; проверь свободное место заранее.

ЧАСТЬ 1. C++ БЕЗ БРОКЕРА

Нужны CMake >=3.22 и компилятор C++20. Из папки этих файлов:

  cmake -S . -B build
  cmake --build build
  ctest --test-dir build --output-on-failure
  ./build/delivery_model

Можно вместо CMake собрать один файл:

  g++ -std=c++20 -Wall -Wextra -Werror delivery_model.cpp -o delivery_model
  ./delivery_model

Базовый вывод:
  delivery 0 applied total=3
  restart 0 duplicate total=3
  delivery 1 applied total=7
  next=2 receipts=2

Слово restart обозначает учебное возобновление чтения, а не перезапуск
всего процесса. Ledger остаётся в его памяти. Программа не пишет на диск,
не подключает broker, не выполняет конкурентный доступ. Это проверка
алгоритма защиты выбранного эффекта, а не готовая production-система.

ЧАСТЬ 2. ПОДГОТОВКА ЛОКАЛЬНОГО DOCKER-ПРОЕКТА

Далее команды для Bash на машине, которой ты управляешь. Не выполняй их
в production-кластере, в чужом Compose-проекте или на публичном broker.
Если Docker ещё не установлен, используй официальную инструкцию своей ОС;
этот набор ничего не устанавливает глобально и не включает Docker daemon.
Доступ к Docker сам по себе даёт широкие полномочия на хосте.

Проверь доступность:
  docker version
  docker compose version

Если server недоступен/permission denied, остановись на C++-модели.
Не меняй автоматически права socket и не запускай команды через sudo
просто ради прохождения лаборатории.

Проверь также Docker context — выбранное подключение CLI к конкретному
Docker Engine. Локальный docker на твоём компьютере может управлять
удалённым сервером. Имя проекта и loopback-порты сами этого не исключают.
В КАЖДОМ терминале опыта, до pull/up и любых следующих Docker-операций:

  test -z "${DOCKER_HOST-}" && printf 'DOCKER_HOST: пусто\n'
  test -z "${DOCKER_CONTEXT-}" && printf 'DOCKER_CONTEXT: пусто\n'
  docker context inspect --format '{{.Endpoints.docker.Host}}'

Обе первые команды должны напечатать подтверждение «пусто»; test проверяет
отсутствие значения, а && печатает подтверждение только при успехе. Если
подтверждения нет, СТОП: есть override из окружения. Последняя команда
должна показать только unix:///... — локальный Unix socket собственного
Docker Engine в этой машине/своей учебной VM. При ssh://, tcp://, неизвестном
адресе, ошибке inspect или чужой VM остановись. Не выполняй unset и не
переключай context автоматически: сначала осознанно разберись, куда смотрит
CLI. Этот опыт не предназначен для remote/prod Docker. Windows named pipe
этим вариантом инструкции не поддерживается; нужен собственный локальный
WSL/Linux-стенд. Не меняй рабочий context и эти переменные во время опыта;
проверку повторяй при открытии нового терминала и перед завершением.

Выбери НОВОЕ имя, например course11-local-20261030-a. В каждом терминале
этого опыта используй одно и то же значение:

  export COURSE11_PROJECT=course11-local-20261030-a
  [[ "$COURSE11_PROJECT" =~ ^course11-[a-z0-9][a-z0-9-]{2,50}$ ]]
  docker ps -a --filter "label=com.docker.compose.project=$COURSE11_PROJECT"
  docker volume ls --filter "label=com.docker.compose.project=$COURSE11_PROJECT"
  docker network ls --filter "label=com.docker.compose.project=$COURSE11_PROJECT"

Команда [[ ... ]] должна завершиться с кодом 0 (успех). При первоначальном выборе
имени три списка должны быть пустыми, кроме заголовков. Если там уже есть
ресурсы, НЕ удаляй их: выбери другое новое имя. После старта ресурсы именно
этого опыта, разумеется, будут видны. Не используй имя чужого проекта.

Опубликованы только loopback-порты:
  127.0.0.1:29092 — Kafka для клиента на хосте;
  127.0.0.1:25672 — RabbitMQ AMQP для клиента на хосте;
  127.0.0.1:25673 — RabbitMQ management HTTP/UI.

На Linux проверь занятость, например:
  ss -ltn '( sport = :29092 or sport = :25672 or sport = :25673 )'

Если порты заняты, не останавливай неизвестные процессы. Для первого опыта
лучше выбрать другую доступную машину. Самостоятельная смена Kafka-порта
потребует согласовать published port, EXTERNAL advertised listener и адрес
C++-клиента; изменение одной строки создаёт ложное впечатление поломки Kafka.

Введи собственный локальный пароль без его появления в истории команд:
  read -r -s -p 'Локальный пароль RabbitMQ: ' COURSE11_RABBIT_PASSWORD
  printf '\n'
  export COURSE11_RABBIT_PASSWORD
  test -n "$COURSE11_RABBIT_PASSWORD"

Не записывай пароль в общий отчёт, Git, URL или скриншот. Переменная среды
и конфигурация контейнера не являются хранилищем секретов от администратора
хоста. Внутри учебной Docker-сети используется незашифрованный протокол;
это не конфигурация для интернета или реальной многопользовательской среды.

Проверь конфигурацию, НЕ печатая раскрытый пароль:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" config --quiet

Эта команда разбирает файл без запуска контейнеров; успех не проверяет
доступность образа, готовность приложения, авторизацию и обмен сообщениями.
Если всё выше проверено, запуск ТОЛЬКО собственного нового проекта:

  docker compose -f compose.yaml -p "$COURSE11_PROJECT" pull
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" up -d
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" ps

Проверь готовность отдельно; первое выполнение сразу после старта может
ещё не пройти. Подожди немного и повтори ограниченное число раз вручную:

  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T kafka /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server kafka:19092
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T rabbit rabbitmq-diagnostics -q ping

Если готовности нет, изучи журнал СВОЕГО сервиса, не рассылай его без
просмотра на секреты:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" logs --tail=80 kafka
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" logs --tail=80 rabbit

Вход в management UI: http://127.0.0.1:25673/ , пользователь course11,
vhost course11, пароль введён выше. Web UI не нужен для CLI-части.

ЧАСТЬ 3. KAFKA: ОДНА ИСТОРИЯ, НЕЗАВИСИМЫЕ ГРУППЫ

Адрес kafka:19092 работает внутри Compose-сети. Адрес 127.0.0.1:29092
предназначен для клиента НА ХОСТЕ. В отдельном произвольном контейнере
localhost обозначал бы тот контейнер, а не этот broker.

Создай topic один раз:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --create --topic course11-orders --partitions 3 --replication-factor 1

Если topic уже существует в твоём сохранённом проекте, не удаляй его
автоматически. Просмотри его и учти уже имеющиеся записи:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --describe --topic course11-orders

Публикация через штатную CLI. Команда ждёт ввод; напечатай ровно одну
строку ниже, затем Ctrl+D. Ключ и значение разделены первым двоеточием:

  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:19092 --topic course11-orders --property parse.key=true --property key.separator=: --producer-property acks=all --producer-property enable.idempotence=true

Строка для ввода:
  order-101:evt-101|order=101

Прочитай одну сохранённую запись новой группой A:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:19092 --topic course11-orders --group course11-reader-a --from-beginning --max-messages 1 --timeout-ms 15000 --consumer-property enable.auto.commit=false --property print.key=true --property print.partition=true --property print.offset=true

Повтори другой новой группой B:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:19092 --topic course11-orders --group course11-reader-b --from-beginning --max-messages 1 --timeout-ms 15000 --consumer-property enable.auto.commit=false --property print.key=true --property print.partition=true --property print.offset=true

Обе группы могут увидеть одну сохранённую запись. Это НЕ обязательно
две публикации. Сравни topic,partition,offset и payload. При трёх partitions
не обещаем конкретный номер partition или общий порядок всех записей.
CLI здесь не фиксирует позицию автоматически; это задано явно.

Не запускай reset-offsets для неизвестных групп. Для нового опыта выбирай
новую course11-... группу, сохраняя требуемую историю. Earliest не вернёт
данные, уже удалённые политикой хранения.

ЧАСТЬ 4. RABBITMQ: МАРШРУТ И ПОВТОРНОЕ ПОЛУЧЕНИЕ

Helper требует только Python3 stdlib и обращается к ФИКСИРОВАННОМУ
management API127.0.0.1:25673 с паролем из переменной среды.
Это диагностический HTTP-инструмент, не AMQP-клиент и не рекомендация
реализовать таким способом production-consumer.

  python3 rabbit_api.py setup
  python3 rabbit_api.py publish
  python3 rabbit_api.py status
  python3 rabbit_api.py peek
  python3 rabbit_api.py peek
  python3 rabbit_api.py take
  python3 rabbit_api.py status

Setup объявляет durable direct exchange course11.events, durable quorum
queue course11.audit и binding для orders.created. Publish передаёт
одну persistent публикацию evt-101; routed=true относится к маршруту API,
а не к уже завершённому обработчику.

Peek НЕ является неизменяющим просмотром файла: API получает доставку
и возвращает её в очередь через ack_requeue_true. Take использует
ack_requeue_false: сервер 4.3.6 получает сообщение с no_ack=true и снимает
его автоматически, не проверяя полезную работу клиента. Потеря HTTP-ответа
не отменяет снятие. При пустой очереди придёт
пустой список. При прежних публикациях не обещаем ровно одно сообщение.
Management-статистика может обновляться с задержкой; не делай из неё
атомарный журнал каждого шага. Redelivery и новая публикация — разные вещи.

ЧАСТЬ 5. OPTIONAL C++ SDK-КЛИЕНТЫ

Основная сборка их НЕ загружает. Нужны уже доступные dev headers/libs:
  librdkafka >=2.12.1, pkg-config package rdkafka;
  rabbitmq-c >=0.18.1, pkg-config package librabbitmq.

Используй официальный способ сборки/пакет своей ОС. Не подставляй старый
неподдерживаемый SDK ради отсутствия ошибок компиляции: rabbitmq-c0.18.1
содержит исправление безопасности. Чтение headers не заменяет проверку
сборки именно с твоими установленными библиотеками.

  cmake -S . -B build-sdk -DCOURSE11_BUILD_CLIENTS=ON
  cmake --build build-sdk

Kafka (topic должен существовать):
  ./build-sdk/kafka_roundtrip send course11-cpp-a
  ./build-sdk/kafka_roundtrip read-no-commit course11-cpp-a
  ./build-sdk/kafka_roundtrip read course11-cpp-a
  ./build-sdk/kafka_roundtrip read-no-commit course11-cpp-b

Первый режим принимает запись локально и ждёт delivery report. Он
явно включает idempotence: у librdkafka2.12.1 её default=false, что нельзя
подменять default Java producer. Успех producev — ещё не успех доставки.
Режим read сохраняет следующую позицию после печати. Read-no-commit
намеренно этого не делает; повтор той же группы может увидеть запись снова.
Печать stdout не является долговечным бизнес-эффектом. Poll имеет учебное
окно 15 секунд; close и teardown не обещают общий жёсткий предел 15 секунд.

RabbitMQ AMQP (отдельно от management helper):
  ./build-sdk/rabbit_roundtrip send
  ./build-sdk/rabbit_roundtrip read-no-ack
  ./build-sdk/rabbit_roundtrip read

Send объявляет маршрут, публикует одно сообщение и ждёт publisher confirm
на своём канале. Отсутствующий маршрут/неожиданный ответ считается ошибкой.
Read-no-ack закрывается без consumer ack; доставка может вернуться.
Read печатает и подтверждает полученное сообщение. Это демонстрация разных
границ подтверждения, а не транзакция stdout+broker. Отдельные публикации
всегда могут добавить записи с таким же учебным event_id; SDK не реализует
бизнес-дедупликацию за принимающее приложение.

ЧАСТЬ 6. ЗАВЕРШЕНИЕ БЕЗ ПОТЕРИ ДАННЫХ

Сначала проверь значение и ресурсы именно СВОЕГО проекта:
  [[ "$COURSE11_PROJECT" =~ ^course11-[a-z0-9][a-z0-9-]{2,50}$ ]]
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" ps

Только если это твои ресурсы, остановка с сохранением контейнеров:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" stop

Или снятие контейнеров и сети при СОХРАНЕНИИ named volumes:
  docker compose -f compose.yaml -p "$COURSE11_PROJECT" down

Не добавляй -v/--volumes и не выполняй global prune, массовый stop,
delete/purge чужих очередей или удаление неизвестных каталогов. Автоматической
команды удаления учебных данных здесь намеренно нет. Повторный up с тем же
проектом использует сохранённые тома. Сохрани выбранный пароль приватно:
смена env не обязана переопределить пользователя в уже инициализированном
томе RabbitMQ. Для чистого независимого опыта выбирай НОВЫЙ проект.

ОТЧЁТ

Запиши версию CLI/SDK, имя проекта без пароля, режим опыта, topic/queue,
group,partition,offset/message_id, шаги и фактический вывод/ошибку.
Отдельно отметь: что выполнил, что лишь прочитал, где осталась неопределённость.
Не публикуй секреты, реальные клиентские payload и журналы без просмотра.
Если broker недоступен, напиши «не запускался», а не «успешно по ожиданию».

ПЕРВОИСТОЧНИКИ ДЛЯ ЭТОГО НАБОРА

Kafka4.1: https://kafka.apache.org/41/getting-started/docker/
Kafka design: https://kafka.apache.org/41/design/design/
RabbitMQ4.3 quorum queues: https://www.rabbitmq.com/docs/4.3/quorum-queues
RabbitMQ HTTP API: https://www.rabbitmq.com/docs/http-api-reference
librdkafka2.12.1: https://github.com/confluentinc/librdkafka/tree/v2.12.1
rabbitmq-c0.18.1: https://github.com/alanxz/rabbitmq-c/releases/tag/v0.18.1


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

Основание выбора режима CMake 3.24:
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD.html
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD_REQUIRED.html
https://cmake.org/cmake/help/v3.24/variable/CMAKE_CXX_COMPILER.html
