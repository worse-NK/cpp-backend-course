#include <pqxx/pqxx>

#include <charconv>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>

#if RELEASE_VERSION != 1 && RELEASE_VERSION != 2
#error "Build release_v1 or release_v2 using CMake"
#endif

namespace {
using Number = std::int64_t;
constexpr std::string_view columns =
#if RELEASE_VERSION == 2
  "id,title,version,note";
#else
  "id,title,version";
#endif

Number positive_version(std::string_view value) {
  Number result{};
  const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
  if (value.empty() || value.front() == '0' || parsed.ec != std::errc{} ||
      parsed.ptr != value.data() + value.size() || result <= 0)
    throw std::invalid_argument("invalid version");
  return result;
}

struct Task {
  Number id;
  std::string title;
  Number version;
#if RELEASE_VERSION == 2
  std::string note;
  bool note_is_null;
#endif
};

Task read_task(const pqxx::row& row) {
  Task result{row[0].as<Number>(), row[1].as<std::string>(), row[2].as<Number>()
#if RELEASE_VERSION == 2
    , row[3].is_null() ? std::string{} : row[3].as<std::string>(), row[3].is_null()
#endif
  };
  return result;
}

void print(const Task& task) {
  std::cout << "v" << RELEASE_VERSION << " id=" << task.id
            << " title=" << std::quoted(task.title) << " version=" << task.version;
#if RELEASE_VERSION == 2
  std::cout << " note=";
  if (task.note_is_null) std::cout << "NULL";
  else std::cout << std::quoted(task.note);
#endif
  std::cout << '\n';
}
} // namespace

int main(int argc, char* argv[]) {
  try {
    const std::string_view action = argc >= 2 ? argv[1] : "";
    const bool show = action == "show" && argc == 2;
    bool write = action == "rename" && argc == 4;
#if RELEASE_VERSION == 2
    write = write || (action == "set-note" && argc == 4);
#endif
    if (!show && !write) throw std::invalid_argument("invalid command");
    Number expected{};
    std::string value;
    if (write) {
      expected = positive_version(argv[2]);
      value = argv[3];
      if (value.size() > 200 || (action == "rename" && value.empty()))
        throw std::invalid_argument("invalid value");
    }
    // libpq reads PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD. In the lab these
    // refer only to its own database and its non-owning application role.
    pqxx::connection connection{"connect_timeout=3"};
    if (show) {
      pqxx::read_transaction tx(connection);
      tx.exec("SET LOCAL statement_timeout='3000ms'");
      const auto rows = tx.exec("SELECT " + std::string(columns) +
                                " FROM release_lab.tasks WHERE id=1");
      if (rows.size() != 1) throw std::runtime_error("expected one lab task");
      print(read_task(rows[0]));
      return 0;
    }
    pqxx::work tx(connection);
    tx.exec("SET LOCAL lock_timeout='2000ms'");
    tx.exec("SET LOCAL statement_timeout='3000ms'");
    // V1 writes only fields it knows. It neither rebuilds the whole row nor
    // fills unknown columns with NULL. The column name comes from the binary,
    // never from a user-supplied SQL fragment.
    const std::string column = action == "rename" ? "title" : "note";
    const auto rows = tx.exec(
      "UPDATE release_lab.tasks SET " + column + "=$1,version=version+1 "
      "WHERE id=1 AND version=$2 AND version<9223372036854775807 RETURNING " +
      std::string(columns), pqxx::params{value, expected});
    if (rows.empty()) {
      std::cout << "not_applied: absent, stale version, or version exhausted\n";
      return 2;
    }
    const auto task = read_task(rows[0]); // Convert before COMMIT.
    tx.commit();
    print(task); // Do not announce a successful change before COMMIT.
    return 0;
  } catch (const pqxx::in_doubt_error&) {
    std::cerr << "commit_outcome_unknown: inspect state; do not blindly retry\n";
    return 3;
  } catch (const pqxx::sql_error& error) {
    std::cerr << "sql_failed SQLSTATE=" << error.sqlstate() << '\n';
    return 4;
  } catch (const std::invalid_argument&) {
    std::cerr << "usage: show | rename EXPECTED_VERSION TITLE"
#if RELEASE_VERSION == 2
              << " | set-note EXPECTED_VERSION NOTE"
#endif
              << " (values at most 200 UTF-8 bytes; rename nonempty)\n";
    return 1;
  } catch (const std::exception&) {
    // Connection details and raw SQL error text can contain secrets.
    std::cerr << "release_lab_failed: check configuration and the owned database\n";
    return 5;
  }
}
