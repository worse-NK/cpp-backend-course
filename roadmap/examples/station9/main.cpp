#include <pqxx/pqxx>
#include <cstdlib>
#include <cstdint>
#include <iostream>
#include <string>

// Local demonstration, not an HTTP endpoint: actor/id/version are fixed inputs.
int main(int argc, char* argv[]) {
    if (argc != 2 || std::string{argv[1]}.empty()) {
        std::cerr << "Usage: task_edit NEW_TITLE\n";
        return 1;
    }
    const char* config = std::getenv("CPP_COURSE_DB");
    if (config == nullptr || *config == '\0') {
        std::cerr << "Set CPP_COURSE_DB (without a password in source code).\n";
        return 1;
    }
    try {
        pqxx::connection connection{config};
        pqxx::work transaction{connection};
        const std::int64_t task_id = 10, actor_id = 1, expected_version = 1;
        const auto result = transaction.exec(
            "UPDATE tasks SET title = $1, version = version + 1 "
            "WHERE id = $2 AND owner_id = $3 AND version = $4 "
            "RETURNING id, title, version",
            pqxx::params{std::string{argv[1]}, task_id, actor_id, expected_version});
        if (result.empty()) {
            std::cout << "not_applied: absent, inaccessible, or stale version\n";
            return 2; // RAII rolls back this transaction; there were no matching rows.
        }
        // Convert before commit: conversion failure should not look like commit failure.
        const auto id = result[0][0].as<std::int64_t>();
        const auto title = result[0][1].as<std::string>();
        const auto version = result[0][2].as<std::int64_t>();
        transaction.commit();
        std::cout << id << " | " << title << " | " << version << '\n';
        return 0;
    } catch (const pqxx::in_doubt_error&) {
        std::cerr << "Commit outcome unknown; do not blindly retry.\n";
        return 3;
    } catch (const pqxx::sql_error& error) {
        std::cerr << "SQLSTATE=" << error.sqlstate() << '\n';
        return 4;
    } catch (const std::exception&) {
        // Do not expose connection strings, SQL text, or user input in a public log.
        std::cerr << "Database operation failed; investigate before retrying.\n";
        return 5;
    }
}
