// C++20 + SQLite3. Сборка при установленных заголовках и библиотеке SQLite:
// c++ -std=c++20 -Wall -Wextra -Wpedantic security_sql_demo.cpp -lsqlite3 -o security_sql_demo
// Только новая база :memory: — без файлов, сети и настоящих пользовательских данных.
// sqlite3_prepare_v2: https://www.sqlite.org/c3ref/prepare.html
// sqlite3_bind_text: https://www.sqlite.org/c3ref/bind_blob.html
// step/finalize: https://www.sqlite.org/c3ref/step.html
// https://www.sqlite.org/c3ref/finalize.html
// Защита: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
#include <sqlite3.h>

#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

[[noreturn]] void fail(sqlite3* db, const char* operation, int code) {
    throw std::runtime_error(std::string(operation) + " (" + std::to_string(code)
        + "): " + (db ? sqlite3_errmsg(db) : sqlite3_errstr(code)));
}
void check(sqlite3* db, int code, const char* operation) {
    if (code != SQLITE_OK) fail(db, operation, code);
}

// unique_ptr владеет ресурсом: даже при исключении он вызовет нужную очистку.
// Деструкторы не бросают; на обычном пути результат finalize проверяем явно.
struct CloseDatabase {
    void operator()(sqlite3* db) const noexcept { (void)sqlite3_close_v2(db); }
};
struct FinalizeStatement {
    void operator()(sqlite3_stmt* stmt) const noexcept { (void)sqlite3_finalize(stmt); }
};
using Database = std::unique_ptr<sqlite3, CloseDatabase>;
using Statement = std::unique_ptr<sqlite3_stmt, FinalizeStatement>; // Подготовленный запрос.

Statement prepare(sqlite3* db, const char* sql) {
    sqlite3_stmt* raw = nullptr;
    const int code = sqlite3_prepare_v2(db, sql, -1, &raw, nullptr);
    Statement stmt(raw);
    check(db, code, "prepare");
    if (!stmt) throw std::runtime_error("prepare: SQL не содержит команды");
    return stmt;
}
void finish(sqlite3* db, Statement& stmt) {
    // release передаёт указатель finalize и предотвращает повторную очистку.
    check(db, sqlite3_finalize(stmt.release()), "finalize");
}

struct Lesson { int id; std::string title; bool is_public; };

std::vector<Lesson> find_public(sqlite3* db, const std::string& term) {
    // term — корректный UTF-8; здесь его передают только литералы из main.
    // Ограничение учебного примера: до 120 байт, без встроенного нулевого байта.
    if (term.size() > 120 || term.find('\0') != std::string::npos)
        throw std::invalid_argument("term: максимум 120 байт UTF-8, без NUL");
    auto stmt = prepare(db,
        "SELECT id, title, is_public FROM lessons "
        "WHERE is_public = 1 AND title = $term ORDER BY id;");
    // is_public — правило этого каталога, не система прав пользователей.
    // $term — место для значения. Кавычки вокруг параметра в SQL не нужны.
    // SQLITE_TRANSIENT означает: SQLite скопирует текст до возврата из bind.
    check(db, sqlite3_bind_text(stmt.get(), 1, term.c_str(),
        static_cast<int>(term.size()), SQLITE_TRANSIENT), "bind_text");
    std::vector<Lesson> rows;
    for (;;) {
        const int code = sqlite3_step(stmt.get());
        if (code == SQLITE_DONE) break;
        if (code != SQLITE_ROW) fail(db, "step", code);
        if (rows.size() == 20) throw std::runtime_error("Слишком много строк");
        // column_* читаем только после SQLITE_ROW и до следующего step.
        const auto* text = sqlite3_column_text(stmt.get(), 1);
        if (!text) fail(db, "column_text", SQLITE_NOMEM); // title имеет NOT NULL.
        const int size = sqlite3_column_bytes(stmt.get(), 1);
        rows.push_back({sqlite3_column_int(stmt.get(), 0),
            std::string(reinterpret_cast<const char*>(text), static_cast<std::size_t>(size)),
            sqlite3_column_int(stmt.get(), 2) != 0});
    }
    finish(db, stmt);
    return rows;
}

int main() {
    try {
        sqlite3* raw = nullptr;
        const int code = sqlite3_open(":memory:", &raw);
        Database db(raw); // open может создать handle даже при ошибке: теперь он под RAII.
        check(db.get(), code, "open");
        std::cout << "SQLite " << sqlite3_libversion() << '\n';
        // Это только фиксированный SQL автора; пользовательского ввода здесь нет.
        const char* fixture = R"sql(
CREATE TABLE lessons (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    is_public INTEGER NOT NULL CHECK (is_public IN (0, 1))
);
INSERT INTO lessons VALUES
    (1, 'RAII', 1), (2, 'TCP', 1), (3, 'O''Reilly', 1),
    (4, 'Планирование', 1), (5, 'Черновик A', 0), (6, 'Черновик B', 0);
)sql";
        check(db.get(), sqlite3_exec(db.get(), fixture, nullptr, nullptr, nullptr), "fixture");
        for (const char* term : {"RAII", "O'Reilly", "' OR 1=1 --"}) {
            const auto rows = find_public(db.get(), term);
            std::cout << "\nterm = " << std::quoted(term) << " -> строк: " << rows.size() << '\n';
            for (const auto& row : rows)
                std::cout << row.id << " | " << row.title << " | is_public=" << row.is_public << '\n';
        }
        // Все statements уже уничтожены. При ошибке close db остаётся под RAII.
        const int close_code = sqlite3_close(db.get());
        if (close_code != SQLITE_OK) fail(db.get(), "close", close_code);
        (void)db.release(); // Успешный close уже освободил соединение.
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Ошибка локального примера: " << error.what() << '\n';
        return 1;
    }
}
