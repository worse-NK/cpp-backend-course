#include <iostream>
#include <optional>
#include <stdexcept>

// A deterministic teaching model, not a Redis or PostgreSQL implementation.
struct Card { int price; unsigned version; };
struct Entry { Card card; int expires_at_ms; };

class Cache {
    unsigned floor_ = 0;
    std::optional<Entry> entry_;
public:
    void invalidate(unsigned version) {
        if (version > floor_) floor_ = version;
        entry_.reset();
    }
    bool fill(Card card, int now_ms, int ttl_ms, bool check_version) {
        if (ttl_ms <= 0) throw std::invalid_argument("positive TTL required");
        if (check_version && card.version < floor_) return false;
        entry_ = Entry{card, now_ms + ttl_ms};
        return true;
    }
    std::optional<Card> get(int now_ms) const {
        if (!entry_ || now_ms >= entry_->expires_at_ms) return std::nullopt;
        return entry_->card;
    }
};

int main() {
    const Card loaded_before_write{100, 1};
    const Card authoritative_now{120, 2};
    Cache ttl_only;
    ttl_only.invalidate(authoritative_now.version);       // Writer at t=20.
    ttl_only.fill(loaded_before_write, 30, 50, false);     // Delayed reader.
    const auto old = ttl_only.get(40);
    if (!old || old->price != 100) return 1;
    std::cout << "TTL-only: " << old->price
              << ", origin: " << authoritative_now.price << '\n';

    Cache with_floor;
    with_floor.invalidate(authoritative_now.version);
    const bool accepted = with_floor.fill(loaded_before_write, 30, 50, true);
    if (accepted || with_floor.get(40)) return 2;
    with_floor.fill(authoritative_now, 40, 50, true);
    std::cout << "old fill accepted: " << std::boolalpha << accepted << '\n';
    std::cout << "reloaded: " << with_floor.get(40)->price << '\n';
    std::cout << "at expiry: " << with_floor.get(90).has_value() << '\n';
    if (!with_floor.get(89) || with_floor.get(90)) return 3;
    bool rejected_invalid_ttl = false;
    try { with_floor.fill(authoritative_now, 40, 0, true); }
    catch (const std::invalid_argument&) { rejected_invalid_ttl = true; }
    if (!rejected_invalid_ttl) return 4;
}
