#include "metrics.hpp"
#include <iostream>

int main() {
    Metrics metrics;
    // These are inputs of a deterministic exercise, not measured requests.
    struct Observation { double seconds; bool success; };
    for (auto sample : {Observation{0.05, true}, {0.10, true}, {0.12, false},
                        {0.30, true}, {0.80, true}}) {
        metrics.enter();
        metrics.complete(sample.seconds, sample.success);
    }
    std::cout << metrics.exposition();
}
