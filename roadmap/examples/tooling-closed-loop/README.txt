Три замкнутых опыта: диагностика, измерение и зависимость
========================================================

Программа отчёта показывает первое задание. Пустой список — нормальный вход.
report_before ошибочно требует элемент 0 и получает проверяемое исключение at().
Не запускайте эту версию на рабочих данных: empty вызываем только под GDB.
report_fixed отдельно представляет отсутствие номера и проходит --self-test.

Это GNU/Linux-практикум. Проверено: GCC 13.3, GDB 15.1, CMake 3.28.3,
Ninja 1.11.1; Conan 2.22.2 в отдельном Python 3.12 venv.
Все shell-команды ниже выполняются из корня скачанного курса, где есть roadmap/.
Сначала прочитайте разделы станции5: gdb-core-regression,
perf-cpu-wait-workbook и conan-target-lock-workbook.
Не продолжайте следующий этап после ошибки предыдущего.

1. Собственная диагностика
-------------------------
TOOLING_SRC="$PWD/roadmap/examples/tooling-closed-loop"
TOOLING_LAB=$(mktemp -d)
cmake -S "$TOOLING_SRC" -B "$TOOLING_LAB/build" -G Ninja &&
cmake --build "$TOOLING_LAB/build" --parallel 2

До аварии непустой вход можно проверить отдельно:
"$TOOLING_LAB/build/report_before" ready
stdout: first task: 41
stderr: tasks=2

Создать снимок своей остановленной программы:
(
  umask 077
  ulimit -c 0
  gdb -nx -q -batch \
    -iex 'set auto-load off' -iex 'set debuginfod enabled off' \
    -ex 'set confirm off' -ex 'set disable-randomization off' \
    -ex run -ex "generate-core-file $TOOLING_LAB/report.core" \
    -ex kill --args "$TOOLING_LAB/build/report_before" empty
)
test -s "$TOOLING_LAB/report.core"

Не изменяются core_pattern, sysctl или настройки чужого процесса.
ulimit действует только в подоболочке; GDB пишет core явно.
При ptrace denied опыт с core НЕ ПРОВЕРЕН. Не обходите системную политику.
Core должен быть непустым; в проверке он имел права 0600 внутри приватной папки.
Не публикуйте его: память может содержать секреты.

После остановки дочернего процесса:
readelf -n "$TOOLING_LAB/build/report_before"
sha256sum "$TOOLING_LAB/build/report_before"
gdb -nx -q -batch \
  -iex 'set auto-load off' -iex 'set debuginfod enabled off' \
  "$TOOLING_LAB/build/report_before" "$TOOLING_LAB/report.core" \
  -ex bt -ex 'frame function first_task' -ex 'info locals' -ex list

Ожидаемые свидетельства: SIGABRT -> обработка исключения -> vector::at ->
first_task -> main. В first_task count=0, доступ at(0).
Номера кадров, адреса и библиотечные сообщения зависят от сборки.
В core нельзя рассчитывать на исполнение функции вроде tasks.size().
Не перезаписывайте report_before перед разбором его core.

Проверка исправления:
"$TOOLING_LAB/build/report_fixed" empty &&
"$TOOLING_LAB/build/report_fixed" ready &&
ctest --test-dir "$TOOLING_LAB/build" --output-on-failure

stdout соответственно:
no tasks
first task: 41
Регрессионный режим отдельно проверяет пустоту, 41, 0 и -7:
"$TOOLING_LAB/build/report_fixed" --self-test
Точный stdout: regression: OK и перевод строки, exit 0.

2. CPU и ожидание
----------------
"$TOOLING_LAB/build/perf_workload" cpu 40
"$TOOLING_LAB/build/perf_workload" wait 40

Оба запуска: exit 0, requests=40.
Подтверждённые checksum: cpu — 14768256629272300802, wait — 6213229451036900623.
Времена НЕ фиксированы и не являются условием теста.
Режимы вычисляют разный объём: это модель разных причин длительности,
не доказательство оптимизации одинакового алгоритма.
Допустимо 1..100 операций; неверный ввод даёт exit 2.

Если наблюдение разрешено в вашей учебной среде:
perf stat -r 3 -e task-clock,context-switches,page-faults -- \
  "$TOOLING_LAB/build/perf_workload" cpu 40
perf stat -r 3 -e task-clock,context-switches,page-faults -- \
  "$TOOLING_LAB/build/perf_workload" wait 40
perf record -e cpu-clock:u -F 99 -g --call-graph fp \
  -o "$TOOLING_LAB/cpu.perf.data" -- \
  "$TOOLING_LAB/build/perf_workload" cpu 100 &&
perf report --stdio --no-children -i "$TOOLING_LAB/cpu.perf.data"

При подготовке курса perf 6.8.12: stat и record отказали (paranoid=4).
На ЭТОМ хосте PERF PROFILE NOT VERIFIED, а не PASS и не нулевые счётчики.
Измерения самой программы выполнены; они не подменяют perf.
Без sudo/изменений sysctl/capabilities/системного -a.

Отдельно инструмент проверен в одноразовой offline QEMU/TCG VM:
Linux 6.8.0-142-generic x86_64, тот же perf 6.8.12, собственная программа.
В VM нет внешней NIC, диска и общей папки; политика хоста не менялась.
perf-vm-evidence.json сохраняет ФАКТИЧЕСКИЕ stdout/stat/report этого запуска.
Чтобы ограничить опыт, использованы cpu 4, wait 4, затем cpu 8 для record;
частота record 49, событие cpu-clock:u, не аппаратный cycles.
stat открыл события task-clock/context-switches/page-faults; record сохранил
17 выборок без зарегистрированных lost samples. В report mix занял 82,35%.
Малое число выборок не даёт точной оценки доли: это проверка маршрута инструмента.
Не сравнивайте эти времена с host cpu 40 или с настоящим сервером.
stat охватывает запуск процесса, тогда как std::clock() в программе — только
измеренный участок main; их границы тоже не обязаны совпасть.
Программные события в эмуляции не подтверждают наличие аппаратной PMU.
Отдельный успешный гостевой запуск НЕ снимает запрет perf на рабочем хосте.

3. Conan2 с явной ревизией
-------------------------
Профиль предназначен для Linux x86_64 и /usr/bin/g++ major 13.
/usr/bin/g++ --version
cmake --version
ninja --version
python3 --version

Не подменяйте реальную версию компилятора настройкой профиля.
Для другого окружения нужен согласованный профиль и новая проверка.
Загрузка Python-пакетов ниже идёт только с официального PyPI.
Рецепты C++-пакета полностью локальные, remotes Conan запрещены.

CONAN_SRC="$PWD/roadmap/examples/tooling-closed-loop/conan"
CONAN_LAB=$(mktemp -d)
python3 -m venv "$CONAN_LAB/venv" &&
"$CONAN_LAB/venv/bin/python" -m pip install \
  --index-url https://pypi.org/simple --disable-pip-version-check --no-cache-dir \
  -r "$CONAN_SRC/requirements-conan.txt"
"$CONAN_LAB/venv/bin/conan" --version

CONAN_HOME="$CONAN_LAB/home" "$CONAN_LAB/venv/bin/conan" export \
  "$CONAN_SRC/library" &&
CONAN_HOME="$CONAN_LAB/home" "$CONAN_LAB/venv/bin/conan" install \
  "$CONAN_SRC/app" --no-remote --build=missing \
  -pr:h "$CONAN_SRC/profiles/linux-gcc13.txt" \
  -pr:b "$CONAN_SRC/profiles/linux-gcc13.txt" \
  --lockfile "$CONAN_SRC/conan.lock.json" -of "$CONAN_LAB/deps"

Ожидаемая recipe revision:
course-task-label/1.0#f63e7a05c4cce3f812333a73a3609d33
Она закреплена в conan.lock.json, имя lock передаётся явно.
Сами lock/profiles не фиксируют весь компилятор/ОС/Python по байтам.
requirements фиксирует проверенные версии, но не wheel-хеши.

cmake -S "$CONAN_SRC/app" -B "$CONAN_LAB/build-a" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$CONAN_LAB/deps/conan_toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release &&
cmake --build "$CONAN_LAB/build-a" --parallel 2 &&
ctest --test-dir "$CONAN_LAB/build-a" --output-on-failure &&
"$CONAN_LAB/build-a/task_report"

Точный stdout приложения: task:41 и перевод строки, exit 0.
Повторите последний блок с build-b вместо build-a:
это новый каталог потребителя, но тот же кеш зависимости.

Для принятого изменения библиотеки нужен новый проверенный lock.
В собственной копии можно изменить экспортированный исходник и экспортировать
в ещё один НОВЫЙ CONAN_HOME. Старый lock + --no-remote тогда не найдёт
отсутствующую старую ревизию: ожидаемый отказ, не зелёный результат.
Если старая ревизия уже в кеше, install может выбрать её и пройти.

Уборка
------
Команды создают только новые временные каталоги, указанные TOOLING_LAB и
CONAN_LAB. После проверки путей удалите их вручную файловым менеджером.
Не удаляйте исходники, общий кеш Conan или рабочие дампы.
Сборка не требует очистки домашней папки и установки системных сервисов.
