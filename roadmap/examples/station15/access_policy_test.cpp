// c++ -std=c++20 -Wall -Wextra -Wpedantic access_policy_test.cpp -o access_policy_test
// Один .cpp включён намеренно: скачиваемый пример не требует отдельного заголовка.
#define COURSE_SECURITY_POLICY_NO_MAIN
#include "access_policy.cpp"
#include <stdexcept>

#define CHECK(condition) do { \
    if (!(condition)) throw std::runtime_error("check failed: " #condition); \
} while (false)

int main() {
  try {
    using namespace security15;
    const Context valid{true, 7, 10}, expired{false, 7, 10};
    const Request read{Action::get, {}}, rename{Action::rename, {"title"}};
    CHECK((visible_ids(Mode::login_only, valid) == std::vector<int>{41, 42, 43}));
    CHECK((visible_ids(Mode::owner_only, valid) == std::vector<int>{41, 43}));
    CHECK((visible_ids(Mode::strict, valid) == std::vector<int>{41}));
    CHECK(decide(Mode::strict, valid, fixture[0], read).allowed);
    CHECK(!decide(Mode::strict, valid, fixture[1], read).allowed);
    CHECK(!decide(Mode::strict, valid, fixture[2], read).allowed);
    CHECK(decide(Mode::strict, {true, 7, 20}, fixture[2], read).allowed);
    CHECK(!decide(Mode::strict, {true, 7, 20}, fixture[0], read).allowed);
    CHECK(decide(Mode::strict, valid, fixture[0], rename).allowed);
    for (const auto& fields : {std::vector<std::string>{}, {"owner_id"}, {"tenant_id"},
                              {"title", "owner_id"}, {"title", "title"}, {"unknown"}})
        CHECK(!decide(Mode::strict, valid, fixture[0], {Action::rename, fields}).allowed);
    CHECK(!decide(Mode::strict, valid, fixture[0], {Action::change_owner, {}}).allowed);
    CHECK(!decide(Mode::strict, valid, fixture[0], {Action::get, {"owner_id"}}).allowed);
    CHECK(!decide(static_cast<Mode>(99), valid, fixture[0], read).allowed);
    CHECK(!decide(Mode::strict, valid, fixture[0], {static_cast<Action>(99), {}}).allowed);
    for (const auto mode : {Mode::login_only, Mode::owner_only, Mode::strict}) {
        for (const auto& task : fixture) {
            CHECK(!decide(mode, expired, task, read).allowed);
            CHECK(!decide(mode, expired, task, rename).allowed);
        }
        bool denied = false;
        try { (void)visible_ids(mode, expired); }
        catch (const std::invalid_argument&) { denied = true; }
        CHECK(denied);
    }
    std::cout << "PASS: identity, tenant, owner, action, fields and list\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}
