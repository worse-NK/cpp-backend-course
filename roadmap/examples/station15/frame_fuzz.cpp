// Requires matching Clang/libFuzzer + ASan/UBSan runtimes, not just a compiler binary.
// clang++ -std=c++20 -g -O1 -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer frame_fuzz.cpp -o frame_fuzz
// ./frame_fuzz -runs=2000 -max_len=8200 -timeout=1 -rss_limit_mb=256 -seed=15
// Small bounded local smoke only. Longer fuzzing belongs to an isolated test job.
#include "frame_parser.hpp"
#include <cstdlib>

using namespace course::security;
void invariant(bool condition) { if (!condition) std::abort(); }
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    if (size==0) {
        const auto result = parse_frame({});
        invariant(result.status==ParseStatus::incomplete && result.consumed==0 && result.payload.empty());
        return 0;
    }
    auto input = std::as_bytes(std::span<const std::uint8_t>(data,size));
    while (!input.empty()) {
        // Independent arithmetic reference: at most four base-256 digits,
        // so the intermediate value fits uint64_t. No type-punning loads.
        std::uint64_t length = 0;
        if (input.size() >= header_size)
            for (std::size_t i=0; i<header_size; ++i)
                length = length*256 + std::to_integer<unsigned>(input[i]);
        const auto result = parse_frame(input);
        const auto expected = input.size()<header_size ? ParseStatus::incomplete :
            length>max_payload ? ParseStatus::reject :
            length>input.size()-header_size ? ParseStatus::incomplete : ParseStatus::complete;
        invariant(result.status==expected);
        if (result.status!=ParseStatus::complete) {
            invariant(result.consumed==0 && result.payload.empty());
            break;
        }
        invariant(result.consumed>=header_size && result.consumed<=input.size());
        invariant(result.payload.size()==length && result.payload.size()<=max_payload);
        invariant(result.payload.data()==input.data()+header_size);
        for (std::size_t i=0; i<result.payload.size(); ++i)
            invariant(result.payload[i]==input[header_size+i]);
        input = input.subspan(result.consumed); // Strict progress, even for empty payload.
    }
    return 0;
}
