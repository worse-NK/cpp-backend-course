#include <charconv>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <string_view>
#include <system_error>
#include <thread>

std::uint64_t mix(std::uint64_t value, unsigned iterations) {
    for (unsigned i = 0; i < iterations; ++i) {
        value = value * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
        value ^= value >> 17;
    }
    return value;
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: perf_workload cpu|wait requests(1..100)\n";
        return 2;
    }
    const std::string_view mode{argv[1]}, text{argv[2]};
    unsigned requests = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), requests);
    if ((mode != "cpu" && mode != "wait") || parsed.ec != std::errc{}
        || parsed.ptr != text.data() + text.size() || requests == 0 || requests > 100) {
        std::cerr << "invalid bounded workload\n";
        return 2;
    }
    const auto start = std::chrono::steady_clock::now();
    const std::clock_t cpu_start = std::clock();
    if (cpu_start == std::clock_t{-1}) return 3;
    std::uint64_t checksum = 0;
    for (unsigned i = 0; i < requests; ++i) {
        checksum ^= mix(i + 1, mode == "cpu" ? 8000000U : 8000U);
        if (mode == "wait") std::this_thread::sleep_for(std::chrono::milliseconds{20});
    }
    const std::clock_t cpu_end = std::clock();
    if (cpu_end == std::clock_t{-1}) return 3;
    const double wall_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - start).count();
    const double cpu_ms = 1000.0 * static_cast<double>(cpu_end - cpu_start) / CLOCKS_PER_SEC;
    std::cout << "mode=" << mode << " requests=" << requests << " checksum=" << checksum
              << " wall_ms=" << wall_ms << " cpu_ms=" << cpu_ms << '\n';
}
