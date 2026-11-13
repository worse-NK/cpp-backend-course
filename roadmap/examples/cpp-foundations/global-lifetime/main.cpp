#include "runtime.hpp"
#include <cstdio>

int main() {
    Counters counters;
    const Config& defaults = default_config();
    if (&defaults != &default_config()) {
        std::puts("check: different defaults");
        return 1;
    }

    {
        Config config = defaults;
        Journal journal{counters};
        {
            Service service{config, journal, counters};
            service.handle();
        }
    }

    const bool ok = defaults.port == 8080
        && counters.requests == 1
        && counters.active_services == 0
        && counters.journal_entries == 2
        && !counters.journal_open;
    std::puts(ok ? "check: OK" : "check: FAIL");
    return ok ? 0 : 1;
}
