СТАНЦИЯ 15 — ЛОКАЛЬНЫЕ ПРИМЕРЫ И ОТЧЁТЫ

Эти упражнения не открывают порт, не меняют фаервол или права хоста,
не создают пользователей и не обращаются к сети. Все личности, объекты
и полномочия вымышлены. Не подставляйте реальные пароли и токены.

1. ЧТО СКАЧАТЬ

Для политики: access_policy.cpp и access_policy_test.cpp в один отдельный
каталог. Для парсера: frame_parser.hpp, frame_parser_test.cpp, frame_fuzz.cpp
рядом. CMakeLists.txt объединяет обычные программы и тесты. Исходный
access_policy.cpp включается в его тест намеренно: отдельный заголовок
для такого короткого скачиваемого примера не нужен.

Требуется компилятор с C++20. CMake необязателен. Команды ниже выполняются
из каталога с этими учебными файлами и создают только новые локальные
исполняемые файлы или каталог build. Они не устанавливают пакеты.

2. ПОЛИТИКА ДОСТУПА

c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror access_policy.cpp -o access_policy
./access_policy
c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror access_policy_test.cpp -o access_policy_test
./access_policy_test

Ожидаемый вывод первой программы:
login_only: 41 42 43
owner_only: 41 43
strict: 41
allowed
forbidden_fields
forbidden_action
session_invalid

Вторая программа проверяет допуски и запреты. Входной Context считается
уже проверенным: это не код настоящего входа, JWT или HTTP-обработчика.
Решение allow ещё не меняет базу. Отдельно нужны согласование проверки
с записью, публичный договор ошибок и все остальные границы сервиса.

3. ПАРСЕР КАДРА

c++ -std=c++20 -Wall -Wextra -Wpedantic -Werror frame_parser_test.cpp -o frame_parser_test
./frame_parser_test

Первые 4 байта — длина в big-endian; полезная часть не больше 4096 байт.
Тест проверяет неполный ввод, предельные длины, хвост и несколько кадров.
Payload — заимствованный view: он не переживает уничтожение или
перевыделение исходного буфера. Парсер не управляет сетевым ожиданием.

При наличии Clang и его sanitizer runtime можно отдельно выполнить:
clang++ -std=c++20 -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer frame_parser_test.cpp -o frame_parser_sanitized
./frame_parser_sanitized
clang++ -std=c++20 -g -O1 -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer frame_fuzz.cpp -o frame_fuzz
./frame_fuzz -runs=2000 -seed=15 -max_len=8200 -timeout=2 -rss_limit_mb=256

Это ограниченный пробный прогон. max_len — верхняя допустимая длина,
а не обещание, что fuzzer сгенерирует все длины до неё. RSS проверяется
периодически, не является системным жёстким ограничением памяти.
Если окружение запрещает LeakSanitizer или runtime отсутствует, запишите
ошибку среды: не объявляйте такой запуск успешным и не отключайте проверки
ради зелёного сообщения. Успех не доказывает отсутствие всех ошибок.

Альтернатива для обычных тестов:
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure

4. ФАЙЛЫ ПОЛИТИК И СВИДЕТЕЛЬСТВ

outbound-policy.example.json — проектное ограничение исходящих запросов.
Идентификаторы catalog-a/catalog-b означают два заранее выбранных сервиса;
в браузерной модели им соответствуют docs.partner.test/cdn.partner.test.
Это не файл настроек реального HTTP-клиента. Размеры и сроки — условие
упражнения; применять их к рабочему сервису без анализа нельзя.

delivery-policy.example.json намеренно содержит плохие решения. В своей
копии исправьте их и объясните каждое изменение. JSON ничего не меняет
в Docker, GitHub Actions, Linux или PostgreSQL.

network-evidence.example.json и release-evidence.example.json — ПРИМЕРЫ,
не записанные результаты запуска. Сохраните собственные наблюдения,
явно отметьте их область и то, что не проверялось. В браузерных моделях
нет настоящих DNS/HTTP/TLS. В файловом ревью не проверялся рабочий хост.

Необязательная проверка формы, Python 3 без внешних зависимостей:
python3 verify_security_evidence.py outbound-policy outbound-policy.example.json
python3 verify_security_evidence.py network-evidence network-evidence.example.json
python3 verify_security_evidence.py delivery-policy delivery-policy.example.json
python3 verify_security_evidence.py release-evidence release-evidence.example.json

Проверяющий скрипт читает только указанный файл до 64 КиБ. PASS означает
типы и обязательные поля, а НЕ правдивость записи и НЕ безопасность.
Даже намеренно плохой стартовый delivery-policy имеет правильный формат.

5. SQL — ОТДЕЛЬНЫЙ ПРИМЕР

security_sql_demo.cpp лежит на уровень выше, в examples/. Ему нужны
заголовок и библиотека SQLite: это отдельная необязательная зависимость.
Браузерный SQL-разбор использует локальный sql.js; C++ там не компилируется.

Теория: ../../cpp_station15_security.html
Модели: ../../security_labs.html
SQL: ../../security_sql_demo.html


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

Для выбора C++23 требуется CMake 3.20 или новее (минимум проекта теперь 3.20).
Разборщик и его существующие тесты не требуют std::byteswap для C++20.

Основание выбора режима CMake 3.24:
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD.html
https://cmake.org/cmake/help/v3.24/prop_tgt/CXX_STANDARD_REQUIRED.html
https://cmake.org/cmake/help/v3.24/variable/CMAKE_CXX_COMPILER.html
