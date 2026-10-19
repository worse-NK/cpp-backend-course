#include <cstddef>
#include <iostream>
#include <stdexcept>
#include <string>

enum class Admission { accepted, full, draining };

class Gate {
    std::size_t limit_;
    std::size_t active_ = 0;
    bool draining_ = false;
public:
    explicit Gate(std::size_t limit) : limit_(limit) {
        if (limit == 0) throw std::invalid_argument("zero limit");
    }
    Admission enter() noexcept {
        if (draining_) return Admission::draining;
        if (active_ == limit_) return Admission::full;
        ++active_;
        return Admission::accepted;
    }
    void finish() {
        if (active_ == 0) throw std::logic_error("unmatched finish");
        --active_;
    }
    void drain() noexcept { draining_ = true; }
    bool ready() const noexcept { return !draining_; }
    bool stopped() const noexcept { return draining_ && active_ == 0; }
    std::size_t active() const noexcept { return active_; }
};

void check(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

void run_checks() {
    bool rejected = false;
    try { Gate invalid(0); }
    catch (const std::invalid_argument&) { rejected = true; }
    check(rejected, "zero limit must fail");

    Gate gate(2);
    check(gate.ready(), "initial readiness");
    check(!gate.stopped(), "idle is not stopped");
    check(gate.enter() == Admission::accepted, "first accepted");
    check(gate.enter() == Admission::accepted, "second accepted");
    check(gate.enter() == Admission::full, "third rejected");
    check(gate.active() == 2, "rejection preserves count");
    gate.finish();
    check(gate.enter() == Admission::accepted, "capacity recovered");

    gate.drain();
    gate.drain(); // repeated stop request is harmless
    check(!gate.ready(), "draining is not ready");
    check(!gate.stopped(), "existing work still present");
    check(gate.enter() == Admission::draining, "drain has priority");
    check(gate.active() == 2, "drain rejection preserves count");
    gate.finish();
    check(!gate.stopped(), "one work item remains");
    gate.finish();
    check(gate.stopped(), "drained completely");
    check(gate.enter() == Admission::draining, "no restart after drain");

    bool unmatched = false;
    try { gate.finish(); }
    catch (const std::logic_error&) { unmatched = true; }
    check(unmatched && gate.active() == 0, "no counter underflow");

    Gate idle(1);
    idle.drain();
    check(idle.stopped(), "idle drain completes immediately");
}

int main() {
    try {
        run_checks();
        std::cout << "all checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "check failed: " << error.what() << '\n';
        return 1;
    }
}
