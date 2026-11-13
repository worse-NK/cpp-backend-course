#include "runtime.hpp"
#include <cstdio>

namespace {
Config load_defaults() {
    std::puts("defaults: load");
    return Config{8080};
}
}

const Config& default_config() {
    static const Config value = load_defaults();
    return value;
}

Journal::Journal(Counters& counters) : counters_(counters) {
    counters_.journal_open = true;
    std::puts("journal: open");
}

Journal::~Journal() {
    counters_.journal_open = false;
    std::puts("journal: close");
}

void Journal::write(const char* message) {
    ++counters_.journal_entries;
    std::puts(message);
}

Service::Service(const Config& config, Journal& journal, Counters& counters)
    : config_(config), journal_(journal), counters_(counters) {
    ++counters_.active_services;
    std::puts("service: start");
}

Service::~Service() {
    journal_.write("journal: service stop");
    --counters_.active_services;
    std::puts("service: stop");
}

void Service::handle() {
    journal_.write("journal: request");
    std::printf("service: port %d\n", config_.port);
    ++counters_.requests;
}
