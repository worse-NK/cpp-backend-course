Kubernetes: собственный C++-сервис в отдельном локальном kind
===========================================================

Это приложение к станции13, не инструкция для рабочего кластера.
Сначала прочитай теорию, затем проходи шаги по одному. 30.10.2026 на Linux
в отдельном локальном kind проверены DNS/Service, готовность экземпляров,
обновление ConfigMap с заменой Pod, завершение сервиса сигналом SIGTERM
(просьбой корректно остановиться) и выпуск отдельного нового образа программы.
После проверки учебный кластер и его временные ресурсы удалены.

Это ограниченный опыт на одном узле, не проверка высокой доступности.
Согласованное выселение Pod для обслуживания узла, автомасштабирование HPA
и сетевую фильтрацию NetworkPolicy здесь не испытывали. Офлайн-проверки C++
и файлов сами по себе также не проверяют сеть и Kubernetes. Ожидаемые результаты
ниже — критерии для твоего стенда, не гарантия тех же времён на любой машине.

Рабочая среда: Linux, C++20, CMake>=3.24, компилятор с C++20 и pthreads,
Python3. Для настоящего стенда дополнительно нужны разрешённый Docker engine,
kind v0.33.0 и kubectl v1.36.x (сервер стенда1.36.4), curl. На macOS/Windows
можно исследовать контейнерный стенд с поддерживаемым Docker; нативный app.cpp
использует Linux/POSIX signals. Вариант Windows-кода здесь не обещается.

Фиксация версий
--------------
Узел: kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed
kind: v0.33.0, https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0
cpp-httplib:0.59.0, архив с SHA256
7c8cc7df044abb837d75f7c1e56333305acb40335c3788b8f5fbf5927e63e148
Builder: gcc:14.4.0-trixie; runtime: debian:trixie-20261027-slim.
Последние два имени — проверенные теги официальных images, не обещание
неизменяемого содержимого. При настоящем запуске сохрани platform/image ID
и разрешённые digest. Не называй эту фиксацию «последней версией Kubernetes».
Документация главы привязана к snapshot v1.36.

Файлы, которые нужно скачать в одну новую папку
--------------------------------------------
README.txt, CMakeLists.txt, app.cpp, drain_model.cpp, Dockerfile, .dockerignore,
kind.yaml, verify.py, namespace.json, configmap.json, deployment.json,
service.json, pdb-example.json, hpa-example.json, role-example.json,
networkpolicy-example.json. Не копируй сюда kubeconfig рабочего окружения.
При работе с Git также используй включённый .gitignore; не коммить build/,
скачанный httplib.h, логи с чувствительными данными и course13.kubeconfig.

JSON выбран намеренно: Kubernetes принимает JSON- и YAML-манифесты одного API,
а локальную структуру можно проверить стандартным Python без новых пакетов.
verify.py не является полноценным валидатором всех API Kubernetes.

Как получить инструменты, прежде чем запускать лабораторию
---------------------------------------------------------
Учебник и его офлайн-версия содержат текст, схемы и исходники, но не Docker,
Kubernetes, компилятор или контейнерные образы. Не путай два действия:
«сохранить курс» и «подготовить машину для запуска скачанного проекта».
Для первоначальной подготовки ниже нужен интернет. После неё CMake и Docker
также могут обращаться к сети за закреплёнными зависимостями и образами.

Python3 выполняет проверки, CMake организует сборку, g++ компилирует C++.
На отдельной учебной Ubuntu24.04 базовые инструменты можно установить так,
если владелец машины разрешил изменение системы:

  sudo apt update
  sudo apt install build-essential cmake python3 curl ca-certificates

Это установка системных пакетов, не команда запуска лаборатории. На других
системах сначала выбери подходящие пакеты и проверь CMake>=3.24/C++20:

  python3 --version
  cmake --version
  g++ --version

Docker запускает контейнеры. Если он уже установлен, не переустанавливай его.
Если его нет, сначала прочитай официальную инструкцию именно для своей ОС:
  Ubuntu: https://docs.docker.com/engine/install/ubuntu/
  Debian: https://docs.docker.com/engine/install/debian/
Там сначала выбирают поддерживаемую ОС и настраивают официальный репозиторий,
а затем устанавливают docker-ce, docker-ce-cli, containerd.io,
docker-buildx-plugin и docker-compose-plugin. Не запускай последнюю команду
установки отдельно от подготовки репозитория и не удаляй чужие пакеты/службы.
Docker меняет системную службу и сетевые правила; предпочтительна учебная VM.
Шаги установки и выдачу доступа согласуют отдельно. Группа docker даёт
root-уровень доступа к обычному Docker daemon, а не просто удобный псевдоним.
Основание: https://docs.docker.com/engine/install/linux-postinstall/

Проверь выбранное подключение и доступ к нему; эти команды не создают контейнер:

  docker context show
  docker version
  docker compose version

В docker version должны успешно отобразиться и Client, и Server. При отказе
доступа остановись: не дописывай sudo к дальнейшим командам и не меняй группы.
Убедись, что context относится к твоему разрешённому локальному Docker,
а не к удалённому рабочему серверу. Compose нужен соседним практикумам;
сам kind-стенд не использует Compose.

kind создаёт учебный кластер, kubectl общается с его API. Если подходящие версии
уже доступны, проверь их и переходи к шагу0. Иначе следующий блок сохраняет
kind0.33.0 и kubectl1.36.4 ТОЛЬКО в новую .course13-tools внутри папки проекта.
Поддержаны Linux x86_64 и aarch64. Системные программы, PATH в настройках
оболочки и kubeconfig не меняются; существующая .course13-tools не затирается.
Прочитай блок целиком; копируй его из корня своей новой лабораторной папки:

  (
    set -eu
    case "$(uname -m)" in
      x86_64) course13_arch=amd64 ;;
      aarch64) course13_arch=arm64 ;;
      *) printf '%s\n' 'Нужен отдельный вариант для этой архитектуры.' >&2; exit 1 ;;
    esac
    test ! -e .course13-tools
    mkdir -m 700 .course13-tools
    cd .course13-tools
    curl --fail --location --proto '=https' --tlsv1.2 \
      -o "kind-linux-$course13_arch" \
      "https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-$course13_arch"
    curl --fail --location --proto '=https' --tlsv1.2 \
      -o kind.sha256sum \
      "https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-$course13_arch.sha256sum"
    sha256sum --check kind.sha256sum
    install -m 0755 "kind-linux-$course13_arch" kind
    curl --fail --location --proto '=https' --tlsv1.2 \
      -o kubectl "https://dl.k8s.io/release/v1.36.4/bin/linux/$course13_arch/kubectl"
    curl --fail --location --proto '=https' --tlsv1.2 \
      -o kubectl.sha256 "https://dl.k8s.io/release/v1.36.4/bin/linux/$course13_arch/kubectl.sha256"
    printf '%s  kubectl\n' "$(tr -d '[:space:]' < kubectl.sha256)" | sha256sum --check
    chmod 0755 kubectl
    ./kind version
    ./kubectl version --client
  )

Обе проверки sha256sum должны завершиться с OK, kind показать0.33.0,
а kubectl — Client Version v1.36.4. Это проверка целостности по опубликованным
контрольным суммам, не независимая подпись автора. При любой ошибке не запускай
скачанные файлы и не продолжай; папку оставь для разбора причины. Если каталог
уже существовал, блок останавливается до скачивания: не удаляй его вслепую.

Только после полного успеха, из корня той же лабораторной папки, выполни:

  export PATH="$PWD/.course13-tools:$PATH"
  kind version
  kubectl version --client

Это меняет поиск команд только в текущем терминале и его дочерних процессах.
В новом терминале снова перейди в папку проекта и повтори export. Не добавляй
его в .bashrc/.zshrc автоматически. Инструменты остаются внутри проекта;
подготовка ещё не создала кластер. Официальные основания выбора версий,
платформ и проверки SHA-256:
  https://kind.sigs.k8s.io/docs/user/quick-start/#installing-from-release-binaries
  https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0
  https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/#install-kubectl-binary-with-curl-on-linux

0. Самая безопасная часть: без Docker, сети и Kubernetes
------------------------------------------------------
В этой папке:

  python3 verify.py
  g++ -std=c++20 -Wall -Wextra -Wpedantic drain_model.cpp -o drain_model
  ./drain_model

Ожидается пять строк:

  first accepted: true
  ready: false
  second accepted: false
  stopped before finish: false
  stopped after finish: true

Это последовательная модель учёта, не эмулятор кластера и не тест сети.
Не редактируй файл ради получения нужного вывода: сначала объясни переходы.

1. Собрать HTTP-программу
------------------------
CMake ниже скачивает только закреплённый архив cpp-httplib и проверяет SHA256.
Это осознанная сетевая операция сборки. Глобальной установки библиотек нет.

  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build -j2
  ctest --test-dir build --output-on-failure

CTest выполняет только последовательные проверки --self-test и drain_model;
не открывает listener. Если уже есть проверенная распакованная cpp-httplib
именно0.59.0, можно вместо сетевого скачивания указать её путь:

  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DFETCHCONTENT_SOURCE_DIR_HTTPLIB=/ABSOLUTE/PATH/cpp-httplib-0.59.0

Замени /ABSOLUTE/PATH/... своим проверенным каталогом. Само переопределение
FetchContent обходит скачивание, поэтому проверка происхождения кеша твоя.

В обычном варианте заголовок находится здесь. Копирование нужно только
в собственной новой лабораторной папке; не перезаписывай чужой файл:

  test ! -e httplib.h && cp build/_deps/httplib-src/httplib.h ./httplib.h

При переопределённом каталоге скопируй именно его httplib.h вместо пути _deps.
Dockerfile не скачивает зависимости и не выполняет apt. Для сборки ему нужен
этот локальный заголовок. Часть libstdc++/libgcc связывается статически,
а glibc остаётся динамической в совместимом Debian runtime: это не scratch
образ и не обещание полностью статического DNS/NSS.

Программа отдаёт:
  GET /        — короткий ответ с APP_VERSION и APP_INSTANCE;
  GET /work    — тот же ответ после500мс искусственной работы;
  GET /livez   — лёгкую живость процесса;
  GET /readyz  — пригодность принимать обычный трафик.
APP_INSTANCE получает имя Pod через fieldRef metadata.name (Downward API —
передача процессу выбранных сведений о собственном окружении).

Это не production HTTP API: нет TLS, БД, пользовательской авторизации,
устойчивых операций и защиты от всех вариантов медленного клиента.
I/O timeouts не обещают ограничить суммарное время DNS, handler и drain.
Нативный listener не запускай на публичном сервере по этой инструкции.

2. Проверить инструменты и границы
---------------------------------
Следующие команды не создают кластер:

  docker version
  kind version
  kubectl version --client
  kind get clusters

Если Docker недоступен по правам, остановись. Не используй sudo, не меняй
членство в группах и не запускай daemon ради этого упражнения. Согласуй
разрешённое локальное окружение с владельцем компьютера. Установка инструментов
описана выше и выполняется отдельно, не из учебной страницы. Официальные инструкции:
https://kind.sigs.k8s.io/docs/user/quick-start/
https://kubernetes.io/docs/tasks/tools/

Имя стенда строго course-station13-v1. Если оно уже есть в kind get clusters,
НЕ удаляй его и НЕ продолжай вслепую: сначала выясни принадлежность. Если файл
course13.kubeconfig уже существует, тоже остановись. Это должны быть новая
собственная среда и новый отдельный файл. Не выполняй kubectl config use-context;
не меняй переменную KUBECONFIG и рабочий ~/.kube/config.

Потребуются свободные CPU, RAM и диск, в том числе на образы. Один kind-узел
не доказывает отказоустойчивость: все копии делят хост и его Docker engine.
kind.yaml привязывает API server к127.0.0.1. Не публикуй API server наружу,
не добавляй --insecure-skip-tls-verify и не передавай kubeconfig третьим лицам.

3. Создать только новый собственный стенд
---------------------------------------
ВАЖНО: kind v0.33.0 запускает узел как привилегированный контейнер — ему дают
существенно больше прав, чем обычному приложению в контейнере. Это расширяет
его доступ к хосту (системе, на которой работает Docker Engine). То, что наш
C++-сервис работает без административных прав, не отменяет этих прав узла kind.

Предпочти отдельную учебную виртуальную машину либо компьютер, владелец которого
осознанно разрешил такой стенд. Если такой доступ не разрешён, не создавай кластер:
теория и офлайн-часть остаются доступны. Не выдавай дополнительные права и не
меняй настройки Docker, чтобы обойти этот запрет. Поведение именно этой версии:
https://github.com/kubernetes-sigs/kind/blob/v0.33.0/pkg/cluster/internal/providers/docker/provision.go#L202-L225

Только после проверок предыдущего шага, из лабораторной папки:

  kind create cluster --name course-station13-v1 --config ./kind.yaml --kubeconfig ./course13.kubeconfig --wait 120s

Эта команда меняет локальную контейнерную среду. Она явно отделена от офлайн-
проверок. Доступ хранится только в новом course13.kubeconfig. Не продолжай
после ошибки создания. Не заменяй имя на рабочее окружение.

Для bash/zsh создай функцию ТОЛЬКО в текущем окне терминала:

  k13() {
    kubectl --kubeconfig ./course13.kubeconfig --context kind-course-station13-v1 --namespace course13 "$@"
  }

Она не устанавливает программу и не переключает глобальный context. Во всех
терминалах опыта повтори определение; работай из той же лабораторной папки.
Не используй просто kubectl без этих явных параметров для мутаций.
Namespace ещё не существует: get pods сейчас может сказать NotFound — это
не причина менять context. Проверить выбранный узел, не читая чужие Pod:

  k13 get nodes

Namespace и Node — cluster-scoped объекты; -n не ограничивает их. Поэтому мы
создаём только явно именованный namespace, а чтение nodes относится только
к явно указанному собственному kind. Приложение дальше namespace-scoped.

4. Образ и первый Deployment
---------------------------
Сначала убедись, что httplib.h скопирован по шагу1:

  docker build --pull -t course-api:station13-v1 .
  docker image inspect course-api:station13-v1 --format '{{.Id}}'
  kind load docker-image course-api:station13-v1 --name course-station13-v1

Первая команда использует сеть для официальных базовых images; тег приложения
уникален для опыта. Загрузка в kind не равна push в registry и не касается
других кластеров. imagePullPolicy=Never сделает забытый load видимой ошибкой.

  k13 apply -f namespace.json
  k13 apply -f configmap.json -f deployment.json -f service.json
  k13 rollout status deployment/course-api --timeout=120s
  k13 get pods -l app=course-api -o wide
  k13 get service course-api
  k13 get endpointslices -l kubernetes.io/service-name=course-api -o yaml

При успехе ожидаются две готовые копии. Если ожидание не выполнено, переходи
к диагностике шага9. Не лечи ошибку изменением всех настроек одновременно.
Проверь путь внутри кластера встроенным клиентом из выбранной копии:

  k13 exec deployment/course-api -- /app/server --get course-api /

Клиент обращается к Service:80, а Service направляет на containerPort8080.
В выводе должны быть200 и имя ответившего экземпляра. Число запросов мало:
это не нагрузочный тест и не доказательство равномерного распределения.

5. Туннель — отдельный диагностический путь
-----------------------------------------
В терминале A:

  k13 port-forward --address 127.0.0.1 service/course-api 18083:80

Пока он работает, в B:

  curl --fail --show-error --max-time 3 http://127.0.0.1:18083/

Port-forward выбирает один Pod и даёт туннель через управляющий путь. Он не
доказывает обычный DNS/ClusterIP путь и не является внешним Ingress. Сохрани
имя ответившего Pod. Остановить только этот foreground-туннель можно Ctrl+C.
Не привязывай туннель к0.0.0.0. Во время замены выбранного Pod он может
закончиться; это не то же самое, что отказ Service у всех клиентов.

6. Готовность отличается от живости и запрета прямого доступа
------------------------------------------------------------
Получи список своих Pod:

  k13 get pods -l app=course-api -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'

Скопируй ровно одно имя из этого списка в собственную переменную:

  COURSE13_POD='ЗАМЕНИ_ИМЕНЕМ_СВОЕГО_POD'

Проверь, что заменил строку, и перечитай конкретный объект:

  k13 get pod "$COURSE13_POD"
  k13 exec "$COURSE13_POD" -- /app/server --not-ready
  k13 get pods -l app=course-api
  k13 get endpointslices -l kubernetes.io/service-name=course-api -o yaml

Повторяй только чтение до наблюдаемого изменения Ready. Не называй задержку
строго равной periodSeconds: есть другие компоненты и распространение данных.
В A можно открыть другой туннель к этому конкретному Pod. В каждом новом
терминале сначала повтори функцию k13 и явно задай тот же COURSE13_POD:

  k13 port-forward --address 127.0.0.1 pod/"$COURSE13_POD" 18084:8080

В B сделай каждый запрос отдельно; -i показывает фактический статус:

  curl -i --show-error --max-time 3 http://127.0.0.1:18084/readyz
  curl -i --show-error --max-time 3 http://127.0.0.1:18084/livez
  curl -i --show-error --max-time 3 http://127.0.0.1:18084/

По договору примера ожидаются503,200,200. Readiness-флаг не является firewall.
Сравни UID и restartCount: неуспех готовности сам по себе не требует рестарта.
Прямой полезный запрос к Pod ещё разрешён, но ordinary Service path должен
перестать выбирать эту ready-цель после обновления состояния. Для проверки
Service используй встроенный клиент шага4 и наблюдай actual EndpointSlice.
Небольшое число ответов само по себе не доказывает полноту сетевой фильтрации.

Восстанови флаг только в том же Pod:

  k13 exec "$COURSE13_POD" -- /app/server --ready
  k13 get pods -l app=course-api

Убедись в возвращении Ready, затем закрой foreground-туннель Ctrl+C.

7. Выпуск настройки и выпуск программы — разные опыты
-----------------------------------------------------
В своей копии configmap.json поменяй только APP_VERSION с v1 на v2 и сохрани.

  k13 apply -f configmap.json
  k13 exec deployment/course-api -- /app/server --get course-api /

Работающие процессы ещё сохраняют старое окружение. Сохрани UID, затем:

  k13 rollout restart deployment/course-api
  k13 rollout status deployment/course-api --timeout=120s
  k13 get pods -l app=course-api -o wide
  k13 exec deployment/course-api -- /app/server --get course-api /

У новых процессов ожидается v2, но image остался тем же. Это не доказательство
нового C++-алгоритма. Для отдельного опыта с программой поменяй в app.cpp
строку тела ответа (не правила допуска и не probes), собери уникальный tag:

  docker build --pull -t course-api:station13-v2 .
  kind load docker-image course-api:station13-v2 --name course-station13-v1
  k13 set image deployment/course-api api=course-api:station13-v2
  k13 rollout status deployment/course-api --timeout=120s
  k13 get pods -l app=course-api -o wide
  k13 exec deployment/course-api -- /app/server --get course-api /

Проверь image в spec и body в реально работающем Pod. Манифест deployment.json
пока описывает v1: повторный apply вернёт намерение к нему. Согласуй свою копию
файла с выбранным результатом, если продолжаешь лабораторию. Не путай diff
декларации, текущую ревизию и содержимое уже работающего процесса.

8. Один контролируемый опыт завершения
-------------------------------------
Не добавляй нагрузку и не делай бесконечных циклов. Выбери текущий Pod по шагу6,
открой к нему туннель18084 и отдельный foreground-log в двух терминалах:

  k13 logs --follow pod/"$COURSE13_POD" --timestamps

В третьем терминале начни ровно один /work, затем в четвёртом один rollout:

  curl -i --show-error --max-time 4 http://127.0.0.1:18084/work

  k13 rollout restart deployment/course-api
  k13 rollout status deployment/course-api --timeout=120s

Ты можешь не успеть попасть внутрь500мс — это не повод придумывать результат.
Запиши фактический исход. Добавь в собственной копии сервисного кода журнал
входа/выхода handler, если нужен более точный след; не увеличивай срок работы
до бесконечного ожидания. Наблюдай, был ли запрос принят до drain. Ожидаемый
механизм: главный поток блокирует SIGTERM/SIGINT до создания workers; затем
sigtimedwait принимает сигнал в обычном потоке. Gate закрывает новый допуск,
stop закрывает listener, библиотека завершает очередь и присоединяет workers.
RAII убирает активность после обычного выхода принятого handler. Последняя
строка stopped drained=true относится к этому примеру, не к доставке ответа.

Готовность и EndpointSlice меняются независимо от доставки ответа старому
клиенту. Grace=15с — внешний предел, не новый таймер после preStop (preStop
в этих manifests вообще нет). Приложение и I/O могут не успеть; SIGKILL не
выполняет деструкторы. Успех одного опыта не доказывает отсутствие потерь.
Потерянный ответ бизнес-операции в реальном API потребовал бы устойчивого ID
и проверки результата; наш /work не пишет данные и не демонстрирует COMMIT.

9. Если что-то не работает
--------------------------
Используй только свой явный context и namespace:

  k13 get pods -l app=course-api -o wide
  k13 describe deployment course-api
  k13 get events --sort-by=.metadata.creationTimestamp
  k13 describe pod "$COURSE13_POD"
  k13 logs pod/"$COURSE13_POD" --timestamps

Если контейнер действительно перезапускался, предыдущие logs могут помочь:

  k13 logs pod/"$COURSE13_POD" --previous --timestamps

Предыдущего контейнера может не быть — такая ошибка команды не говорит о БД.
Выбирай чтение по первому неуспешному этапу:
  Pending: события scheduler, requests и ограничения подходящих узлов.
  ErrImageNeverPull: локальная загрузка image именно в этот kind и точное имя.
  CrashLoopBackOff: причина последнего завершения и предыдущий лог, не новая
    фаза Pod с гарантированно известной причиной.
  Running, но не Ready: startup/readiness, порт, ответ и события проверки.
  Ready, но нет полезного ответа: имя, Service, EndpointSlice, порт, listener,
    очередь приложения и конкретный путь запроса.

При сбое не выдавай cluster-admin, не включай privileged, не отключай TLS-
проверку и не удаляй все объекты «на пробу». Сначала сохрани наблюдения.

10. Примеры, которые не применяются автоматически
-------------------------------------------------
pdb-example.json: minAvailable=1 при двух пригодных копиях ограничивает часть
добровольных выселений через Eviction API. Не предотвращает потерю узла,
прямое удаление Pod и не становится универсальной блокировкой rolling update.
hpa-example.json: CPU utilization60% относительно requests, min2/max4.
Нужен источник resource metrics (обычно Metrics Server). Он здесь НЕ установлен;
сохранение объекта само не создаст рабочую метрику. Это не обязательный шаг.
role-example.json: чтение Pods, без RoleBinding никому не выданы эти права.
Нельзя путать этот доступ с пользовательскими разрешениями своего API.
networkpolicy-example.json: намерение deny ingress для выбранных Pod; не применяй
в минимальном опыте. Без поддерживающего network plugin enforcement не обещан;
базовый kind не назван доказанной лабораторией NetworkPolicy.

PVC/StatefulSet/Job разобраны в теории. Развёртывания БД в Kubernetes здесь нет:
обязательны дополнительные знания конкретного хранения, восстановления,
репликации и эксплуатации. Это не рекомендация ставить production PostgreSQL
с одним случайным томом по учебному примеру.

11. Завершить только созданный собственный стенд
-----------------------------------------------
Сначала останови собственные foreground port-forward/logs через Ctrl+C.
Убедись, что это именно кластер, который ТЫ создал в шаге3, и данные не нужны.
Сохрани несекретные результаты. Удаление ниже необратимо уничтожает его Pod
и временные данные; пользовательские посторонние кластеры не затрагиваются:

  kind get clusters
  kind delete cluster --name course-station13-v1 --kubeconfig ./course13.kubeconfig

Даже при удалении явно указываем тот же отдельный kubeconfig. Без этого флага
kind использовал бы KUBECONFIG или обычный ~/.kube/config, а не файл стенда.

Если принадлежность сомнительна — НЕ выполняй delete. Не используй docker
system prune, массовое удаление containers/images/volumes, rm -rf или удаление
namespace в чужом context. Локальные файлы проекта и скачанные images остаются;
удалять их автоматически инструкция не предлагает. Kubeconfig остаётся
чувствительным файлом: храни приватно и не отправляй в Git.

Основные первоисточники
----------------------
https://kind.sigs.k8s.io/docs/user/quick-start/
https://kind.sigs.k8s.io/docs/user/configuration/
https://v1-36.docs.kubernetes.io/docs/concepts/workloads/controllers/deployment/
https://v1-36.docs.kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
https://v1-36.docs.kubernetes.io/docs/concepts/workloads/pods/probes/
https://v1-36.docs.kubernetes.io/docs/tasks/inject-data-application/environment-variable-expose-pod-information/
https://github.com/yhirose/cpp-httplib/tree/v0.59.0
https://man7.org/linux/man-pages/man3/pthread_sigmask.3.html
https://man7.org/linux/man-pages/man2/sigwaitinfo.2.html

В отчёт включи версии, контекст, namespace, свойства пути, UID, image ID,
метку настройки и исход каждого опыта. Честно отдели прочитанное правило,
ожидаемый исход, реально наблюдаемый результат и непроверенные свойства.


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
