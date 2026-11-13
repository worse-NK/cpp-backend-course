// C++20 baseline; C++23 additionally checks the byteswap implementation.
// An educational format: four big-endian octets of length, then 0..4096 bytes.
#include <array>
#include <bit>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <span>
#include <stdexcept>
#include <vector>
#include <version>

#if __cplusplus > 202002L
#if !defined(__cpp_lib_byteswap) || __cpp_lib_byteswap < 202110L
#error "The C++23 variant needs std::byteswap (__cpp_lib_byteswap >= 202110L)"
#endif
#endif

namespace course::endian_demo {
static_assert(CHAR_BIT == 8 && sizeof(std::uint32_t) == 4);
constexpr std::size_t header_size = 4;
constexpr std::size_t max_payload = 4096;

// Precondition: input.size() >= 4. The parser below checks it first.
std::uint32_t load_be20(std::span<const std::byte> input) noexcept {
    const auto octet = [&](std::size_t i) {
        return std::to_integer<std::uint32_t>(input[i]);
    };
    return (octet(0) << 24) | (octet(1) << 16) | (octet(2) << 8) | octet(3);
}

#if __cplusplus > 202002L
std::uint32_t load_be23(std::span<const std::byte> input) noexcept {
    if constexpr (std::endian::native == std::endian::little) {
        std::uint32_t value{};
        std::memcpy(&value, input.data(), sizeof value);
        return std::byteswap(value);
    } else if constexpr (std::endian::native == std::endian::big) {
        std::uint32_t value{};
        std::memcpy(&value, input.data(), sizeof value);
        return value;
    } else {
        // A mixed-endian target is not automatically a little-endian target.
        return load_be20(input);
    }
}
#endif

enum class Status { incomplete, reject, complete };
struct Frame {
    Status status;
    std::size_t consumed;
    std::span<const std::byte> payload; // Borrows input; it is not an owning copy.
};
using Loader = std::uint32_t (*)(std::span<const std::byte>) noexcept;

Frame parse(std::span<const std::byte> input, Loader load) noexcept {
    if (input.size() < header_size) return {Status::incomplete, 0, {}};
    const std::uint32_t length = load(input);
    if (length > max_payload) return {Status::reject, 0, {}};
    const auto size = static_cast<std::size_t>(length); // Now proven <=4096.
    if (size > input.size() - header_size) return {Status::incomplete, 0, {}};
    return {Status::complete, header_size + size, input.subspan(header_size, size)};
}

void require(bool ok) {
    if (!ok) throw std::runtime_error("frame contract failed");
}

void check(Loader load) {
    // Begin at a byte offset, not at a promised uint32_t-aligned address.
    const std::array bytes{std::byte{99}, std::byte{0}, std::byte{0}, std::byte{0},
                          std::byte{3}, std::byte{'A'}, std::byte{0}, std::byte{'B'}};
    const auto input = std::span<const std::byte>(bytes).subspan(1);
    for (std::size_t cut = 0; cut < input.size(); ++cut) {
        const auto part = parse(input.first(cut), load);
        require(part.status == Status::incomplete && part.consumed == 0);
    }
    const auto full = parse(input, load);
    require(full.status == Status::complete && full.consumed == 7);
    require(full.payload.size() == 3 && full.payload.data() == input.data() + 4);
    require(full.payload[0] == std::byte{'A'} && full.payload[1] == std::byte{0});
    const std::array empty{std::byte{0}, std::byte{0}, std::byte{0}, std::byte{0}};
    require(parse(empty, load).consumed == 4);
    const std::array too_big{std::byte{0}, std::byte{0}, std::byte{0x10}, std::byte{1}};
    require(parse(too_big, load).status == Status::reject);
    const std::array max_number{std::byte{255}, std::byte{255}, std::byte{255}, std::byte{255}};
    require(parse(max_number, load).status == Status::reject);
    std::vector<std::byte> boundary(header_size + max_payload);
    boundary[2] = std::byte{0x10}; // 0x00001000 == 4096.
    require(parse(boundary, load).status == Status::complete);
    require(parse(std::span<const std::byte>(boundary).first(boundary.size() - 1), load)
                .status == Status::incomplete);
}
} // namespace course::endian_demo

#ifndef COURSE_FRAME_NO_MAIN
int main() {
    using namespace course::endian_demo;
    check(load_be20);
#if __cplusplus > 202002L
    check(load_be23);
#endif
    std::cout << "frame checks passed\n";
}
#endif
