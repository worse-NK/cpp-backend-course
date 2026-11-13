#pragma once

struct Config {
    int port;
};

struct Counters {
    int requests = 0;
    int active_services = 0;
    int journal_entries = 0;
    bool journal_open = false;
};

const Config& default_config();

class Journal {
public:
    explicit Journal(Counters& counters);
    ~Journal();
    Journal(const Journal&) = delete;
    Journal& operator=(const Journal&) = delete;
    void write(const char* message);

private:
    Counters& counters_;
};

class Service {
public:
    Service(const Config& config, Journal& journal, Counters& counters);
    ~Service();
    Service(const Service&) = delete;
    Service& operator=(const Service&) = delete;
    void handle();

private:
    const Config& config_;
    Journal& journal_;
    Counters& counters_;
};
