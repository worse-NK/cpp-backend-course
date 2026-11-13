// Build: g++ -std=c++20 -Wall -Wextra -Wpedantic -Werror frame_parser_test.cpp -o frame_parser_test
// Self-contained Linux/local test: no server, external dependency or user files.
#include "frame_parser.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <vector>

using namespace course::security;
void require(bool condition, const char* message) {
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
std::vector<std::byte> frame(std::size_t length) {
    require(length <= max_payload, "test fixture length");
    const auto n = static_cast<std::uint32_t>(length);
    std::vector<std::byte> bytes{std::byte((n >> 24) & 255), std::byte((n >> 16) & 255),
                               std::byte((n >> 8) & 255), std::byte(n & 255)};
    for (std::size_t i=0; i<length; ++i) bytes.push_back(std::byte(i & 255));
    return bytes;
}
int main() {
    std::size_t prefixes = 0;
    for (std::size_t length : {0u,1u,7u,255u,256u,4096u}) {
        const auto bytes = frame(length);
        const std::span<const std::byte> input(bytes);
        for (std::size_t cut=0; cut<bytes.size(); ++cut) {
            const auto part = parse_frame(input.first(cut));
            require(part.status==ParseStatus::incomplete && part.consumed==0 && part.payload.empty(), "partial frame consumed");
            ++prefixes;
        }
        const auto full = parse_frame(input);
        require(full.status==ParseStatus::complete && full.consumed==bytes.size(), "complete frame size");
        require(full.payload.size()==length && full.payload.data()==bytes.data()+header_size, "borrowed payload range");
        require(std::equal(full.payload.begin(),full.payload.end(),bytes.begin()+header_size), "binary payload changed");
    }
    for (const auto& bytes : {std::array{std::byte{0},std::byte{0},std::byte{0x10},std::byte{1}},
                              std::array{std::byte{255},std::byte{255},std::byte{255},std::byte{255}}}) {
        const auto result = parse_frame(bytes);
        require(result.status==ParseStatus::reject && result.consumed==0 && result.payload.empty(), "oversize not rejected at header");
    }
    auto joined = frame(1);
    const auto empty = frame(0), last = frame(2);
    joined.insert(joined.end(),empty.begin(),empty.end());
    joined.insert(joined.end(),last.begin(),last.end());
    std::span<const std::byte> remaining(joined);
    for (std::size_t expected : {1u,0u,2u}) {
        const auto next = parse_frame(remaining);
        require(next.status==ParseStatus::complete && next.payload.size()==expected, "trailing frame lost");
        remaining = remaining.subspan(next.consumed);
    }
    require(remaining.empty(), "unexpected trailing bytes");
    auto trailing = frame(1);
    trailing.push_back(std::byte{0}); trailing.push_back(std::byte{0});
    const auto first = parse_frame(trailing);
    require(first.status==ParseStatus::complete && first.consumed==5, "first frame waits for trailing header");
    const auto tail = parse_frame(std::span<const std::byte>(trailing).subspan(first.consumed));
    require(tail.status==ParseStatus::incomplete && tail.consumed==0, "trailing partial header consumed");
    std::cout << "PASS: " << prefixes << " partial prefixes; 0..4096 boundaries; big-endian; binary payload; trailing frames\n";
}
