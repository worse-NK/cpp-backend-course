#include "storage.hpp"

#include <charconv>
#include <cstdlib>
#include <limits>
#include <set>
#include <nlohmann/json.hpp>
#ifdef COURSE_WITH_POSTGRES
#include <pqxx/pqxx>
#endif

namespace course {
Number parse_positive(std::string_view text) {
  Number result = 0;
  if (text.empty() || text.front() < '1' || text.front() > '9')
    throw InputError(400, "invalid_positive_integer");
  auto [end, ec] = std::from_chars(text.data(), text.data() + text.size(), result);
  if (ec != std::errc{} || end != text.data() + text.size() || result <= 0)
    throw InputError(400, "invalid_positive_integer");
  return result;
}

Number parse_etag(std::string_view text) {
  // This is not a general RFC entity-tag parser: exactly one strong "vN" tag.
  if (text.size() < 4 || text.substr(0, 2) != "\"v" || text.back() != '"')
    throw InputError(400, "invalid_if_match");
  return parse_positive(text.substr(2, text.size() - 3));
}

int parse_port(std::string_view text) {
  auto value = parse_positive(text);
  if (value > 65535) throw InputError(400, "invalid_port");
  return static_cast<int>(value);
}

void validate_input(const TaskInput& input) {
  if (input.title.empty() || input.title.size() > 200 ||
      input.title.find('\0') != std::string::npos)
    throw InputError(422, "invalid_title");
  // JSON serialization checks UTF-8 even when storage is called without HTTP.
  try { (void)nlohmann::json(input.title).dump(); }
  catch (const nlohmann::json::exception&) { throw InputError(422, "invalid_title"); }
}

TaskInput parse_input(std::string_view body) {
  if (body.size() > max_body_bytes) throw InputError(413, "body_too_large");
  bool duplicate = false;
  std::vector<std::set<std::string>> keys;
  auto callback = [&](int, nlohmann::json::parse_event_t event, nlohmann::json& value) {
    if (event == nlohmann::json::parse_event_t::object_start) keys.emplace_back();
    else if (event == nlohmann::json::parse_event_t::key) {
      if (!keys.back().insert(value.get<std::string>()).second) duplicate = true;
    } else if (event == nlohmann::json::parse_event_t::object_end) keys.pop_back();
    return true;
  };
  nlohmann::json value;
  try { value = nlohmann::json::parse(body, callback); }
  catch (const nlohmann::json::exception&) { throw InputError(400, "invalid_json"); }
  if (duplicate) throw InputError(400, "duplicate_json_key");
  if (!value.is_object() || value.size() != 2 || !value.contains("title") ||
      !value.contains("done") || !value["title"].is_string() || !value["done"].is_boolean())
    throw InputError(422, "invalid_task_schema");
  TaskInput input{value["title"].get<std::string>(), value["done"].get<bool>()};
  validate_input(input);
  return input;
}

Number next_version(Number version) {
  if (version < 1 || version == std::numeric_limits<Number>::max()) throw StorageUnavailable{};
  return version + 1;
}

bool valid_token(std::string_view token) noexcept {
  if (token.size() != 64) return false;
  for (unsigned char c : token)
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
      return false;
  return true;
}

bool token_matches(std::string_view supplied, std::string_view expected) noexcept {
  if (supplied.size() != 64 || expected.size() != 64) return false;
  // Fixed-work comparison for this demo, NOT a cryptographic timing guarantee.
  volatile unsigned int difference = 0;
  for (std::size_t i = 0; i != 64; ++i)
    difference = difference | static_cast<unsigned char>(supplied[i] ^ expected[i]);
  return difference == 0;
}

std::vector<Task> MemoryStorage::list() {
  std::lock_guard lock(mutex_);
  std::vector<Task> result;
  result.reserve(tasks_.size());
  for (const auto& [id, task] : tasks_) { (void)id; result.push_back(task); }
  return result;
}
std::optional<Task> MemoryStorage::get(Number id) {
  std::lock_guard lock(mutex_);
  auto it = tasks_.find(id);
  if (it == tasks_.end()) return std::nullopt;
  return it->second;
}
Task MemoryStorage::create(const TaskInput& input) {
  validate_input(input);
  std::lock_guard lock(mutex_);
  if (tasks_.size() >= max_tasks || next_id_ == std::numeric_limits<Number>::max())
    throw StorageUnavailable{};
  Task task{next_id_++, input.title, input.done, 1};
  tasks_.emplace(task.id, task);
  return task;
}
std::optional<Task> MemoryStorage::update(Number id, Number version, const TaskInput& input) {
  validate_input(input);
  std::lock_guard lock(mutex_);
  auto it = tasks_.find(id);
  if (it == tasks_.end() || it->second.version != version) return std::nullopt;
  Task replacement{id, input.title, input.done, next_version(it->second.version)};
  it->second = replacement;
  return replacement;
}
bool MemoryStorage::erase(Number id, Number version) {
  std::lock_guard lock(mutex_);
  auto it = tasks_.find(id);
  if (it == tasks_.end() || it->second.version != version) return false;
  tasks_.erase(it);
  return true;
}

#ifdef COURSE_WITH_POSTGRES
namespace {
std::string env_or(const char* name, const char* fallback) {
  const char* value = std::getenv(name);
  return value ? value : fallback;
}
std::string connection_value(const std::string& value) {
  std::string result = "'";
  for (char c : value) { if (c == '\\' || c == '\'') result += '\\'; result += c; }
  return result + "'";
}
Task from_row(const pqxx::row& row) {
  return {row[0].as<Number>(), row[1].as<std::string>(), row[2].as<bool>(), row[3].as<Number>()};
}

// One connection per operation is intentionally simple, NOT a production pool.
class PostgresStorage final : public Storage {
public:
  PostgresStorage() {
    const auto password = env_or("PGPASSWORD", "");
    if (password.empty()) throw std::invalid_argument("PGPASSWORD is required for PostgreSQL storage");
    const auto port = env_or("PGPORT", "5432");
    (void)parse_port(port);
    connection_ = "host=" + connection_value(env_or("PGHOST", "db")) +
      " port=" + connection_value(port) +
      " dbname=" + connection_value(env_or("PGDATABASE", "course_tasks")) +
      " user=" + connection_value(env_or("PGUSER", "course_app")) +
      " password=" + connection_value(password) +
      " connect_timeout=3 options='-c statement_timeout=3000'";
  }
  bool ready() noexcept override {
    try {
      pqxx::connection conn(connection_);
      pqxx::read_transaction tx(conn);
      (void)tx.exec("SELECT id,title,done,version FROM public.tasks LIMIT 0");
      return true;
    } catch (...) { return false; }
  }
  std::vector<Task> list() override {
    pqxx::connection conn(connection_);
    pqxx::read_transaction tx(conn);
    std::vector<Task> tasks;
    for (auto row : tx.exec("SELECT id,title,done,version FROM public.tasks ORDER BY id LIMIT 1000"))
      tasks.push_back(from_row(row));
    return tasks;
  }
  std::optional<Task> get(Number id) override {
    pqxx::connection conn(connection_);
    pqxx::read_transaction tx(conn);
    auto result = tx.exec("SELECT id,title,done,version FROM public.tasks WHERE id=$1", pqxx::params{id});
    if (result.empty()) return std::nullopt;
    return from_row(result[0]);
  }
  Task create(const TaskInput& input) override {
    validate_input(input);
    pqxx::connection conn(connection_);
    pqxx::work tx(conn);
    // Serializes insert/count with this API's other writers; SELECT stays usable.
    (void)tx.exec("LOCK TABLE public.tasks IN EXCLUSIVE MODE");
    if (tx.exec("SELECT count(*) FROM public.tasks")[0][0].as<Number>() >= static_cast<Number>(max_tasks))
      throw StorageUnavailable{};
    auto result = tx.exec("INSERT INTO public.tasks(title,done) VALUES($1,$2) RETURNING id,title,done,version",
                          pqxx::params{input.title, input.done});
    Task task = from_row(result[0]);
    tx.commit();
    return task;
  }
  std::optional<Task> update(Number id, Number version, const TaskInput& input) override {
    validate_input(input);
    pqxx::connection conn(connection_);
    pqxx::work tx(conn);
    auto existing = tx.exec("SELECT version FROM public.tasks WHERE id=$1 FOR UPDATE", pqxx::params{id});
    if (existing.empty() || existing[0][0].as<Number>() != version) return std::nullopt;
    const auto next = next_version(version);
    auto result = tx.exec("UPDATE public.tasks SET title=$1,done=$2,version=$3 WHERE id=$4 RETURNING id,title,done,version",
                          pqxx::params{input.title, input.done, next, id});
    Task task = from_row(result[0]);
    tx.commit();
    return task;
  }
  bool erase(Number id, Number version) override {
    pqxx::connection conn(connection_);
    pqxx::work tx(conn);
    auto result = tx.exec("DELETE FROM public.tasks WHERE id=$1 AND version=$2 RETURNING id", pqxx::params{id, version});
    bool removed = !result.empty();
    tx.commit();
    return removed;
  }
private:
  std::string connection_;
};
} // namespace
#endif

std::unique_ptr<Storage> make_storage(std::string_view mode) {
  if (mode == "memory") return std::make_unique<MemoryStorage>();
#ifdef COURSE_WITH_POSTGRES
  if (mode == "postgres") return std::make_unique<PostgresStorage>();
#endif
  throw std::invalid_argument("APP_STORAGE must be memory, or postgres in a PostgreSQL-enabled build");
}
} // namespace course
