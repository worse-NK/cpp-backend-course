// Compare the existing C++20 security parser with the two endian loaders.
#define COURSE_FRAME_NO_MAIN
#include "s7-endian-frame.cpp"
#include "../station15/frame_parser.hpp"
#include <algorithm>

int main() {
    using namespace course::endian_demo;
    std::size_t checked = 0;
    for (std::size_t length : {0u, 1u, 255u, 256u, 4096u, 4097u}) {
        const auto n = static_cast<std::uint32_t>(length);
        std::vector<std::byte> bytes{std::byte((n >> 24) & 255), std::byte((n >> 16) & 255),
                                    std::byte((n >> 8) & 255), std::byte(n & 255)};
        bytes.resize(4 + length, std::byte{0x41});
        for (std::size_t cut = 0; cut <= bytes.size(); ++cut) {
            const auto input = std::span<const std::byte>(bytes).first(cut);
            const auto before = course::security::parse_frame(input);
            const auto after20 = parse(input, load_be20);
#if __cplusplus > 202002L
            const auto after = parse(input, load_be23);
#else
            const auto after = after20;
#endif
            const auto same = [&](const Frame& value) {
                const auto expected = before.status == course::security::ParseStatus::incomplete
                    ? Status::incomplete : before.status == course::security::ParseStatus::reject
                    ? Status::reject : Status::complete;
                require(value.status == expected);
                require(value.consumed == before.consumed && value.payload.size() == before.payload.size());
                require(std::equal(value.payload.begin(), value.payload.end(), before.payload.begin()));
                if (value.status == Status::complete)
                    require(value.payload.data() == before.payload.data());
            };
            same(after20);
            same(after);
            ++checked;
        }
    }
    require(checked > 8000);
    std::cout << "endian regression passed\n";
}
