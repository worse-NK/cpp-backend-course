Время жизни конфигурации, журнала и службы

Учебный проект из двух единиц трансляции: runtime.cpp и main.cpp.
runtime.hpp содержит объявления, а не определения глобальных служб.
Никакая сеть не открывается: порт 8080 здесь только значение конфигурации.
Журнал печатает сообщения в stdout, а не создаёт файл.

Из корня скачанного курса, где находится roadmap/:

LIFETIME_BUILD=$(mktemp -d) &&
g++ -std=c++20 -Wall -Wextra -pedantic-errors \
  roadmap/examples/cpp-foundations/global-lifetime/main.cpp \
  roadmap/examples/cpp-foundations/global-lifetime/runtime.cpp \
  -o "$LIFETIME_BUILD/lifetime" &&
"$LIFETIME_BUILD/lifetime"

Повторить можно с -std=c++23. Для каждого нового опыта можно создать новый
каталог mktemp -d. Ни исходники, ни системные настройки команда не меняет.
После опыта проверь сохранённый путь LIFETIME_BUILD: созданный временный
каталог можно удалить вручную, например через файловый менеджер. Исходники
курса удалять не нужно.

Точный stdout для показанного однопоточного штатного выполнения:

defaults: load
journal: open
service: start
journal: request
service: port 8080
journal: service stop
service: stop
journal: close
check: OK

Ожидаемый код завершения: 0. При несовпадении проверяемых счётчиков — 1.
Сравнение двух адресов проверяет повторное обращение к тому же local static.
Финальная проверка выполняется ПОСЛЕ разрушения Service и Journal, пока
Counters и статическая конфигурация ещё существуют. У Config тривиальный
деструктор; отдельной строки его разрушения в выводе нет.

Self-test проверяет состояние показанного корректного пути; он не доказывает
безопасность произвольной перестановки владельцев. В частности, вызывать
метод уже разрушенного Journal нельзя даже ради проверки journal_open.
Намеренно опасный пример с межфайловой глобальной инициализацией в проект
не входит и никогда не запускается.

Основания (открытый проект C++20 N4861, не опубликованный стандарт ISO):
https://timsong-cpp.github.io/cppwp/n4861/stmt.dcl
https://timsong-cpp.github.io/cppwp/n4861/basic.start.term
https://timsong-cpp.github.io/cppwp/n4861/basic.start.main
https://timsong-cpp.github.io/cppwp/n4861/class.cdtor

Явные владельцы в main — рекомендация по устройству этого приложения,
а не требование языка ко всем программам.
