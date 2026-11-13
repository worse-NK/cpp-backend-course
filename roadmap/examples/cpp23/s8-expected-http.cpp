// C++23. No socket, database, HTTP framework or user files are involved.
#include <charconv>
#include <cstdint>
#include <expected>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <version>

#if !defined(__cpp_lib_expected) || __cpp_lib_expected < 202211L
#error "This example needs std::expected with monadic operations (202211L)"
#endif

enum class Problem { missing, malformed, numeric_overflow, outside_policy };
struct TaskId { std::uint32_t value; };
struct Reply { int status; std::string_view code; };

std::expected<std::uint32_t, Problem> parse_number(std::string_view text) {
    if (text.empty()) return std::unexpected(Problem::missing);
    // The exercise accepts decimal digits only: no sign or whitespace.
    for (char ch : text)
        if (ch < '0' || ch > '9') return std::unexpected(Problem::malformed);
    std::uint32_t value{};
    const auto [end, ec] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (ec == std::errc::result_out_of_range)
        return std::unexpected(Problem::numeric_overflow);
    if (ec != std::errc{} || end != text.data() + text.size())
        return std::unexpected(Problem::malformed);
    return value;
}

std::expected<TaskId, Problem> validate_id(std::uint32_t value) {
    // Chosen policy of this exercise, not an HTTP or PostgreSQL requirement.
    if (value == 0 || value > 1000) return std::unexpected(Problem::outside_policy);
    return TaskId{value};
}

Reply error_reply(Problem problem) {
    switch (problem) {
    case Problem::missing: return {400, "missing_id"};
    case Problem::malformed: return {400, "invalid_id"};
    case Problem::numeric_overflow: return {400, "id_overflow"};
    case Problem::outside_policy: return {422, "id_outside_policy"};
    }
    throw std::logic_error("unknown Problem");
}

Reply explicit_reply(std::string_view text) {
    const auto number = parse_number(text);
    if (!number) return error_reply(number.error());
    const auto id = validate_id(*number);
    if (!id) return error_reply(id.error());
    return {200, "accepted"};
}

Reply composed_reply(std::string_view text) {
    const auto result = parse_number(text)
        .and_then(validate_id)
        .transform([](TaskId) { return Reply{200, "accepted"}; });
    if (!result) return error_reply(result.error());
    return *result;
}

int main() {
    struct Case { std::string_view input; int status; std::string_view code; };
    const Case cases[]{{"42", 200, "accepted"}, {"", 400, "missing_id"},
        {"12x", 400, "invalid_id"}, {"0", 422, "id_outside_policy"},
        {"1001", 422, "id_outside_policy"}, {"4294967296", 400, "id_overflow"}};
    for (const auto& item : cases) {
        const auto first = explicit_reply(item.input);
        const auto second = composed_reply(item.input);
        if (first.status != item.status || first.code != item.code ||
            second.status != first.status || second.code != first.code)
            throw std::runtime_error("reply contract failed");
        std::cout << '[' << item.input << "] -> " << first.status << ' ' << first.code << '\n';
    }
    for (const auto invalid : {"-1", "+7", " 7", "7 ", "1.0"})
        if (composed_reply(invalid).status != 400)
            throw std::runtime_error("invalid syntax accepted");
    if (composed_reply("1000").status != 200)
        throw std::runtime_error("upper boundary rejected");
}
