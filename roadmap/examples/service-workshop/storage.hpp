#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace course {
using Number = std::int64_t;
inline constexpr std::size_t max_tasks = 1000;
inline constexpr std::size_t max_body_bytes = 4096;

struct TaskInput { std::string title; bool done; };
struct Task { Number id; std::string title; bool done; Number version; };
struct InputError : std::runtime_error {
  int status;
  InputError(int code, const char* reason) : std::runtime_error(reason), status(code) {}
};
struct StorageUnavailable : std::runtime_error {
  StorageUnavailable() : std::runtime_error("storage_unavailable") {}
};

// These deliberately narrow parsers are part of the exercise's API contract.
Number parse_positive(std::string_view text);
Number parse_etag(std::string_view text);
int parse_port(std::string_view text);
TaskInput parse_input(std::string_view body);
void validate_input(const TaskInput& input);
Number next_version(Number version);
bool valid_token(std::string_view token) noexcept;
bool token_matches(std::string_view supplied, std::string_view expected) noexcept;

class Storage {
public:
  virtual ~Storage() = default;
  virtual bool ready() noexcept = 0;
  virtual std::vector<Task> list() = 0;
  virtual std::optional<Task> get(Number id) = 0;
  virtual Task create(const TaskInput& input) = 0;
  // nullopt / false includes both a missing task and an obsolete version.
  virtual std::optional<Task> update(Number id, Number version, const TaskInput& input) = 0;
  virtual bool erase(Number id, Number version) = 0;
};

class MemoryStorage final : public Storage {
public:
  bool ready() noexcept override { return true; }
  std::vector<Task> list() override;
  std::optional<Task> get(Number id) override;
  Task create(const TaskInput& input) override;
  std::optional<Task> update(Number id, Number version, const TaskInput& input) override;
  bool erase(Number id, Number version) override;
private:
  std::mutex mutex_;
  std::map<Number, Task> tasks_;
  Number next_id_ = 1;
};

// APP_STORAGE=postgres is rejected when the optional adapter was not compiled.
std::unique_ptr<Storage> make_storage(std::string_view mode);
} // namespace course
