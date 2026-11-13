// C++20, no network. A single-threaded model, not a durable storage engine.
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

struct Event {
    std::string id;
    int amount;
};

class Ledger {
    struct State {
        int total = 0;
        std::set<std::string> receipts;
        void swap(State& other) noexcept {
            std::swap(total, other.total);
            receipts.swap(other.receipts);
        }
    } state_;
public:
    bool apply(const Event& event) {
        if (state_.receipts.contains(event.id)) return false;
        if (event.amount < 0 ||
            event.amount > std::numeric_limits<int>::max() - state_.total)
            throw std::invalid_argument("amount outside the teaching contract");
        State prepared = state_;             // Failure here changes nothing.
        prepared.receipts.insert(event.id);   // Receipt and effect in one state.
        prepared.total += event.amount;
        state_.swap(prepared);                // Non-throwing commit of the model.
        return true;
    }
    int total() const noexcept { return state_.total; }
    std::size_t receipt_count() const noexcept { return state_.receipts.size(); }
};

int main() {
    const std::vector<Event> log{{"evt-101", 3}, {"evt-102", 4}};
    Ledger store;
    std::size_t next = 0;
    const bool first = store.apply(log.at(next));
    std::cout << "delivery " << next << ' ' << (first ? "applied" : "duplicate")
              << " total=" << store.total() << '\n';
    // The worker loses its acknowledgement. The independent store survives.
    const bool replay = store.apply(log.at(next));
    std::cout << "restart " << next << ' ' << (replay ? "applied" : "duplicate")
              << " total=" << store.total() << '\n';
    ++next;                                  // Commit the next unread position.
    const bool second = store.apply(log.at(next));
    std::cout << "delivery " << next << ' ' << (second ? "applied" : "duplicate")
              << " total=" << store.total() << '\n';
    ++next;
    std::cout << "next=" << next << " receipts=" << store.receipt_count() << '\n';
    if (!first || replay || !second || store.total() != 7 || next != 2 ||
        store.receipt_count() != 2) return 1;
    const int before = store.total();
    try { store.apply({"bad", -1}); return 2; }
    catch (const std::invalid_argument&) {}
    if (store.total() != before || store.receipt_count() != 2) return 3;
}
