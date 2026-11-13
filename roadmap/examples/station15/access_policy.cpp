// C++20: c++ -std=c++20 -Wall -Wextra -Wpedantic access_policy.cpp -o access_policy
// Чистая учебная политика: без HTTP, JWT, паролей, сети и изменения файлов.
// https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x17-V8-Authorization.md
#include <array>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace security15 {
enum class Mode { login_only, owner_only, strict };
enum class Action { get, list, rename, change_owner };
struct Context { bool session_valid; int user_id; int tenant_id; };
struct Task { int id; int owner_id; int tenant_id; };
struct Request { Action action; std::vector<std::string> fields; };
enum class Reason { allowed, session_invalid, mode_invalid, tenant, owner, action, fields };
struct Decision { bool allowed; Reason reason; };
constexpr std::array<Task, 3> fixture{{{41, 7, 10}, {42, 8, 10}, {43, 7, 20}}};

// Context создаёт доверенный код ПОСЛЕ проверки сессии, а не из JSON клиента.
// Два первых режима намеренно уязвимы. Причина отказа — внутренняя диагностика,
// а не обещание конкретного HTTP-статуса или содержимого публичной ошибки.
[[nodiscard]] Decision decide(Mode mode, const Context& user, const Task& task,
                              const Request& request) {
    if (!user.session_valid) return {false, Reason::session_invalid};
    if (mode == Mode::login_only) return {true, Reason::allowed};
    if (mode != Mode::owner_only && mode != Mode::strict)
        return {false, Reason::mode_invalid};
    if (mode == Mode::strict && task.tenant_id != user.tenant_id)
        return {false, Reason::tenant};
    if (task.owner_id != user.user_id) return {false, Reason::owner};
    if (mode == Mode::owner_only) return {true, Reason::allowed};
    switch (request.action) {
    case Action::get:
    case Action::list:
        if (!request.fields.empty()) return {false, Reason::fields};
        break;
    case Action::rename:
        if (request.fields.size() != 1 || request.fields.front() != "title")
            return {false, Reason::fields};
        break;
    case Action::change_owner:
    default:
        return {false, Reason::action};
    }
    return {true, Reason::allowed};
}

// List сначала проверяет вход как операцию целиком. Истёкшая сессия — отказ,
// а не успешный пустой список. Затем политика применяется к каждой строке.
std::vector<int> visible_ids(Mode mode, const Context& user) {
    if (!user.session_valid) throw std::invalid_argument("session invalid");
    std::vector<int> ids;
    for (const auto& task : fixture)
        if (decide(mode, user, task, {Action::list, {}}).allowed) ids.push_back(task.id);
    return ids;
}
std::string_view reason_name(Reason reason) {
    switch (reason) {
    case Reason::allowed: return "allowed";
    case Reason::session_invalid: return "session_invalid";
    case Reason::mode_invalid: return "mode_invalid";
    case Reason::tenant: return "wrong_tenant";
    case Reason::owner: return "not_owner";
    case Reason::action: return "forbidden_action";
    case Reason::fields: return "forbidden_fields";
    }
    return "invalid_reason";
}
} // namespace security15

#ifndef COURSE_SECURITY_POLICY_NO_MAIN
int main() {
    using namespace security15;
    const Context user{true, 7, 10};
    for (const auto mode : {Mode::login_only, Mode::owner_only, Mode::strict}) {
        const auto name = mode == Mode::login_only ? "login_only"
            : mode == Mode::owner_only ? "owner_only" : "strict";
        std::cout << name << ':';
        for (const auto id : visible_ids(mode, user)) std::cout << ' ' << id;
        std::cout << '\n';
    }
    const auto rename = decide(Mode::strict, user, fixture[0], {Action::rename, {"title"}});
    const auto mass_assignment = decide(Mode::strict, user, fixture[0],
                                        {Action::rename, {"title", "owner_id"}});
    const auto transfer = decide(Mode::strict, user, fixture[0], {Action::change_owner, {}});
    const auto expired = decide(Mode::strict, {false, 7, 10}, fixture[0], {Action::get, {}});
    for (const auto decision : {rename, mass_assignment, transfer, expired})
        std::cout << reason_name(decision.reason) << '\n';
}
#endif
