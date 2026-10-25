#include "storage.hpp"

#include <atomic>
#include <iostream>
#include <limits>
#include <thread>

namespace {
void check(bool condition, const char* description) {
  if (!condition) throw std::runtime_error(description);
}
template<class F> void rejects(int status, F action) {
  try { action(); }
  catch (const course::InputError& error) { check(error.status == status, "wrong rejection status"); return; }
  throw std::runtime_error("input unexpectedly accepted");
}
template<class F> void unavailable(F action) {
  try { action(); }
  catch (const course::StorageUnavailable&) { return; }
  throw std::runtime_error("storage limit unexpectedly accepted");
}
} // namespace

int main() {
  try {
    using namespace course;
    check(parse_positive("1") == 1, "positive parser");
    check(parse_positive("9223372036854775807") == std::numeric_limits<Number>::max(), "int64 maximum");
    for (const auto* invalid : {"", "0", "01", "+1", "-1", " 1", "1 ", "1a", "9223372036854775808"})
      rejects(400, [&] { (void)parse_positive(invalid); });
    check(parse_port("65535") == 65535, "port maximum");
    rejects(400, [] { (void)parse_port("65536"); });
    check(parse_etag("\"v2\"") == 2, "etag parser");
    for (const auto* invalid : {"*", "W/\"v1\"", "\"v0\"", "\"v01\"", "v1", "\"v1\",\"v2\"", "\"v1\" "})
      rejects(400, [&] { (void)parse_etag(invalid); });
    auto input = parse_input(R"({"title":"Hello","done":false})");
    check(input.title == "Hello" && !input.done, "input parser");
    rejects(400, [] { (void)parse_input(R"({"title":"a","done":false,"title":"b"})"); });
    rejects(400, [] { (void)parse_input(R"({"title":"a","done":false,})"); });
    rejects(400, [] { (void)parse_input(R"({"title":{"a":1,"a":2},"done":false})"); });
    for (const auto* invalid : {R"([])", R"({"title":"a"})", R"({"title":"","done":false})",
         R"({"title":"a","done":0})", R"({"title":"a","done":false,"extra":1})",
         R"({"title":"\u0000","done":false})"})
      rejects(422, [&] { (void)parse_input(invalid); });
    rejects(413, [] { (void)parse_input(std::string(4097, ' ')); });
    validate_input({std::string(200, 'a'), false});
    rejects(422, [] { validate_input({std::string(201, 'a'), false}); });
    rejects(422, [] { validate_input({std::string("\xc0\xaf", 2), false}); });
    const std::string token(64, 'a');
    check(valid_token(token) && !valid_token(std::string(64, 'z')), "token format");
    check(token_matches(token, token) && !token_matches(std::string(64, 'b'), token) &&
          !token_matches("", token), "token comparison");
    check(next_version(1) == 2, "version increment");
    unavailable([] { (void)next_version(std::numeric_limits<Number>::max()); });

    MemoryStorage storage;
    check(storage.ready() && storage.list().empty(), "empty store");
    const auto first = storage.create(input);
    check(first.id == 1 && first.version == 1, "creation");
    auto updated = storage.update(first.id, 1, {"updated", true});
    check(updated && updated->version == 2 && updated->done, "update");
    check(!storage.update(first.id, 1, input), "stale update");
    check(!storage.update(999, 1, input), "missing update");
    check(!storage.erase(first.id, 1), "stale erase");
    std::atomic<int> winners{0};
    std::vector<std::jthread> writers;
    for (int i = 0; i != 8; ++i) writers.emplace_back([&] {
      if (storage.update(first.id, 2, input)) ++winners;
    });
    writers.clear();
    check(winners == 1 && storage.get(first.id)->version == 3, "atomic concurrent update");
    check(storage.erase(first.id, 3) && !storage.get(first.id), "erase");
    check(!storage.erase(first.id, 3), "missing erase");
    for (std::size_t i = 0; i != max_tasks; ++i) (void)storage.create(input);
    auto tasks = storage.list();
    check(tasks.size() == max_tasks && tasks.front().id < tasks.back().id, "capacity and order");
    unavailable([&] { (void)storage.create(input); });
    check(storage.erase(tasks.front().id, 1), "release capacity");
    check(storage.create(input).id > tasks.back().id, "identifiers not reused");
    check(make_storage("memory")->ready(), "factory");
    std::cout << "All storage/parser contracts passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "Test failed: " << error.what() << '\n';
    return 1;
  }
}
