#include <array>
#include <atomic>
#include <cstddef>
#include <iostream>
#include <stdexcept>
#include <thread>

template<std::size_t Slots>
class SpscIntQueue {
    static_assert(Slots >= 2);
    static_assert(std::atomic<std::size_t>::is_always_lock_free,
                  "This example requires lock-free size_t atomics");
    std::array<int, Slots> data_{};
    std::atomic<std::size_t> read_{0};
    std::atomic<std::size_t> write_{0};
    static std::size_t next(std::size_t i) noexcept {
        return i + 1 == Slots ? 0 : i + 1;
    }
public:
    // Exactly one producer calls this method.
    bool try_push(int value) noexcept {
        const auto w = write_.load(std::memory_order_relaxed);
        const auto following = next(w);
        if (following == read_.load(std::memory_order_acquire))
            return false;
        data_[w] = value;
        write_.store(following, std::memory_order_release);
        return true;
    }
    // Exactly one consumer calls this method.
    bool try_pop(int& value) noexcept {
        const auto r = read_.load(std::memory_order_relaxed);
        if (r == write_.load(std::memory_order_acquire))
            return false;
        value = data_[r];
        read_.store(next(r), std::memory_order_release);
        return true;
    }
};

void check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
int main() {
    try {
        SpscIntQueue<4> small; // usable capacity = 3
        int value = -1;
        check(!small.try_pop(value) && value == -1, "empty");
        check(small.try_push(10), "push 10");
        check(small.try_push(20), "push 20");
        check(small.try_push(30), "push 30");
        check(!small.try_push(40), "full");
        check(small.try_pop(value) && value == 10, "pop 10");
        check(small.try_push(40), "wrap");
        for (int expected : {20, 30, 40})
            check(small.try_pop(value) && value == expected, "FIFO");
        check(!small.try_pop(value), "empty again");

        SpscIntQueue<128> queue;
        constexpr int count = 100000;
        bool ordered = true; // written only by consumer, read after join
        {
            std::jthread producer([&](std::stop_token stop) {
                for (int i = 0; i < count; ++i) {
                    while (!queue.try_push(i)) {
                        if (stop.stop_requested()) return;
                        std::this_thread::yield();
                    }
                }
            });
            std::jthread consumer([&] {
                for (int expected = 0; expected < count; ++expected) {
                    int item = -1;
                    while (!queue.try_pop(item)) std::this_thread::yield();
                    if (item != expected) ordered = false;
                }
            });
            producer.join();
            consumer.join();
        } // both threads joined before accessing ordered / destroying queue
        check(ordered, "concurrent FIFO");
        std::cout << "boundary checks passed\nFIFO 100000 passed\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
