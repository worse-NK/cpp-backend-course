# Прикладные примеры C++20 и C++23

Это отдельные программы для сравнения небольшого механизма, а не замена
сервера практикума. Они не открывают порты, не обращаются к базе и не меняют
пользовательские файлы. Команды ниже выполняются из корня репозитория курса.

## Длина бинарного сообщения

`s7-endian-frame.cpp` читает четырёхбайтовую big-endian длину, проверяет предел
4096 и полноту содержимого. C++20 собирает число сдвигами, C++23 дополнительно
проверяет ветвь с `memcpy` и `std::byteswap`.

```sh
g++ -std=c++20 roadmap/examples/cpp23/s7-endian-frame.cpp -o frame20
./frame20
g++ -std=c++23 roadmap/examples/cpp23/s7-endian-frame.cpp -o frame23
./frame23
```

В обоих случаях ожидается `frame checks passed`. Вход и результаты заданы
внутри программы; это не фаззинг и не измерение скорости. C++23-ветвь требует
`__cpp_lib_byteswap >= 202110L` из `<version>`.

## От проверки входа к ответу API

`s8-expected-http.cpp` сравнивает обычные `if` и цепочку
`expected::and_then`/`transform`. Номера 1–1000 и отображение причин в 400/422 —
условия этого упражнения. Успешный результат не подтверждает существование
задачи, полномочия пользователя или изменение данных.

```sh
g++ -std=c++23 roadmap/examples/cpp23/s8-expected-http.cpp -o expected-http
./expected-http
```

Нужна библиотека с `__cpp_lib_expected >= 202211L`, а не только более ранний
базовый `expected`. Программа печатает:

```text
[42] -> 200 accepted
[] -> 400 missing_id
[12x] -> 400 invalid_id
[0] -> 422 id_outside_policy
[1001] -> 422 id_outside_policy
[4294967296] -> 400 id_overflow
```

## Сохранение договора безопасности

`s15-endian-regression.cpp` сравнивает новый разборщик с существующим
`examples/station15/frame_parser.hpp`: статусы, consumed и заимствованный
участок. Нужны все три файла в исходной структуре папок; копирование одного
файла в произвольное место не переносит его зависимости.

```sh
g++ -std=c++20 roadmap/examples/cpp23/s15-endian-regression.cpp -o regression20
./regression20
g++ -std=c++23 roadmap/examples/cpp23/s15-endian-regression.cpp -o regression23
./regression23
```

Ожидается `endian regression passed`. Это проверка выбранных длин и всех
начальных частей соответствующих сообщений, не доказательство всех входов.

## Компилятор и библиотека — разные условия

Вместо `g++` можно указать полный путь к отдельному компилятору. Флаг
`-std=c++23` выбирает режим языка, но не устанавливает новую стандартную
библиотеку. Примеры явно отказываются собираться без нужного feature-test macro
(макроса, которым библиотека сообщает наличие конкретной возможности).
Пройдённая сборка этих программ не означает полную поддержку C++23.

Основание: открытый проект C++23 N4950
[byteswap](https://timsong-cpp.github.io/cppwp/n4950/bit.byteswap),
[операции expected](https://timsong-cpp.github.io/cppwp/n4950/expected.object.monadic),
[официальная таблица libstdc++](https://gcc.gnu.org/onlinedocs/libstdc++/manual/status.html).
