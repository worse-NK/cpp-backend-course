#include <cstddef>
#include <iostream>
#include <memory_resource>
#include <new>
#include <numeric>
#include <vector>

int main() {
    alignas(std::max_align_t) std::byte buffer[4096];
    std::pmr::monotonic_buffer_resource arena(
        buffer, sizeof buffer, std::pmr::null_memory_resource());

    {
        std::pmr::vector<int> ids(&arena);
        ids.reserve(8);
        for (int id = 0; id < 8; ++id) ids.push_back(id);
        std::cout << "items=" << ids.size()
                  << " sum=" << std::accumulate(ids.begin(), ids.end(), 0) << '\n';

        try {
            // This cannot fit in the supplied buffer on the tested platform.
            ids.reserve(1'000'000);
        } catch (const std::bad_alloc&) {
            std::cout << "budget exceeded\n";
        }
        std::cout << "items after failure=" << ids.size() << '\n';
    } // Destroy the container before releasing its storage.

    arena.release();
    {
        std::pmr::vector<int> next_request(&arena);
        next_request.push_back(42);
        std::cout << "new request items=" << next_request.size() << '\n';
    }
} // arena is destroyed before buffer.
