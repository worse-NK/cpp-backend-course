#include <atomic>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>

struct Config {
    std::uint64_t version;
    int soft_limit;
    int hard_limit;
};

class ConfigStore {
    std::mutex writers_;
    std::atomic<std::shared_ptr<const Config>> current_{
        std::make_shared<const Config>(Config{1, 10, 20})};
public:
    std::shared_ptr<const Config> read() const {
        return current_.load(std::memory_order_acquire);
    }

    void increase_limits(int step) {
        if (step < 0) throw std::invalid_argument("negative step");
        std::lock_guard lock(writers_);
        const auto before = current_.load(std::memory_order_acquire);
        if (step > std::numeric_limits<int>::max() - before->hard_limit ||
            before->version == std::numeric_limits<std::uint64_t>::max())
            throw std::overflow_error("config limit");
        auto next = std::make_shared<const Config>(Config{
            before->version + 1,
            before->soft_limit + step,
            before->hard_limit + step});
        current_.store(std::move(next), std::memory_order_release);
    }
};

int main() {
    ConfigStore store;
    auto old_reader = store.read();
    std::weak_ptr<const Config> old_lifetime = old_reader;

    store.increase_limits(20);
    const auto new_reader = store.read();
    std::cout << "old: v" << old_reader->version << ' '
              << old_reader->soft_limit << '/' << old_reader->hard_limit << '\n';
    std::cout << "new: v" << new_reader->version << ' '
              << new_reader->soft_limit << '/' << new_reader->hard_limit << '\n';
    std::cout << std::boolalpha
              << "old retained: " << !old_lifetime.expired() << '\n';
    old_reader.reset();
    std::cout << "old released: " << old_lifetime.expired() << '\n';
    return 0;
}
