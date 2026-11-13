#ifndef COURSE_STATION15_FRAME_PARSER_HPP
#define COURSE_STATION15_FRAME_PARSER_HPP

// Educational protocol, not a production framing standard:
// 4 octets of unsigned big-endian payload length, then that many octets.
// Payload length 0..4096 is allowed; an invalid length rejects the stream.
// No allocation, I/O, reinterpret_cast load, or access beyond a checked span.
// Result.payload borrows input: keep its backing storage alive and unchanged.
// C++20 draft N4861: [expr.shift], [span.sub], [basic.life].
#include <climits>
#include <cstddef>
#include <cstdint>
#include <span>

namespace course::security {
static_assert(CHAR_BIT == 8, "This educational wire format requires 8-bit octets");
inline constexpr std::size_t header_size = 4;
inline constexpr std::size_t max_payload = 4096;

enum class ParseStatus { incomplete, reject, complete };
struct ParseResult {
    ParseStatus status;
    std::size_t consumed;
    std::span<const std::byte> payload;
};

[[nodiscard]] constexpr ParseResult parse_frame(std::span<const std::byte> input) noexcept {
    if (input.size() < header_size) return {ParseStatus::incomplete, 0, {}};
    const auto octet = [&](std::size_t index) {
        return std::to_integer<std::uint32_t>(input[index]);
    };
    const std::uint32_t length = (octet(0) << 24) | (octet(1) << 16)
                              | (octet(2) << 8) | octet(3);
    if (length > max_payload) return {ParseStatus::reject, 0, {}};
    const auto size = static_cast<std::size_t>(length); // Proven <=4096 first.
    if (size > input.size() - header_size) return {ParseStatus::incomplete, 0, {}};
    return {ParseStatus::complete, header_size + size, input.subspan(header_size, size)};
}
} // namespace course::security
#endif
