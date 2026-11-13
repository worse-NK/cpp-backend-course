#include <cstddef>
#include <iostream>
#include <stdexcept>

// A sequential model of an application's admission contract, not a simulator
// of the Kubernetes control plane or a substitute for request synchronization.
class Admission {
    bool draining_ = false;
    std::size_t active_ = 0;
public:
    bool enter() {
        if (draining_) return false;
        ++active_;
        return true;
    }
    void drain() noexcept { draining_ = true; }
    void finish() {
        if (active_ == 0) throw std::logic_error("no active request");
        --active_;
    }
    bool ready() const noexcept { return !draining_; }
    bool stopped() const noexcept { return draining_ && active_ == 0; }
};

int main() {
    Admission gate;
    std::cout << std::boolalpha;
    std::cout << "first accepted: " << gate.enter() << '\n';
    gate.drain();
    std::cout << "ready: " << gate.ready() << '\n';
    std::cout << "second accepted: " << gate.enter() << '\n';
    std::cout << "stopped before finish: " << gate.stopped() << '\n';
    gate.finish();
    std::cout << "stopped after finish: " << gate.stopped() << '\n';
}
