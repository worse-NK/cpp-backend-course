#include <pqxx/pqxx>
#include <cstdlib>
#include <exception>
#include <iostream>

// One attempt, not an idempotent HTTP booking endpoint.
int main() {
    const char* config = std::getenv("CPP_COURSE_DB");
    if (config == nullptr || *config == '\0') {
        std::cerr << "Set CPP_COURSE_DB.\n";
        return 1;
    }
    try {
        pqxx::connection connection{config};
        pqxx::work transaction{connection};
        const auto result = transaction.exec(
            "UPDATE parking SET available = available - 1 "
            "WHERE id = $1 AND available > 0 RETURNING available",
            pqxx::params{1});
        if (result.empty()) {
            std::cout << "not_reserved: full or absent\n";
            return 2;
        }
        const int remaining = result[0][0].as<int>();
        transaction.commit();
        std::cout << "reserved; remaining=" << remaining << '\n';
        return 0;
    } catch (const pqxx::in_doubt_error&) {
        std::cerr << "Commit outcome unknown; do not blindly retry.\n";
        return 3;
    } catch (const pqxx::sql_error& error) {
        std::cerr << "SQLSTATE=" << error.sqlstate() << '\n';
        return 4;
    } catch (const std::exception&) {
        std::cerr << "Database operation failed; investigate before retrying.\n";
        return 5;
    }
}
