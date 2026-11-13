// Linux-only, deliberately small HTTP service for the local kind laboratory.
// No database, user authentication, TLS or durable business state is provided.
#include "httplib.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <pthread.h>
#include <signal.h>
#include <stdexcept>
#include <string>
#include <thread>

namespace {
constexpr const char* not_ready_file = "/tmp/course13.not-ready";

class Admission {
    mutable std::mutex mutex_;
    bool draining_ = false;
    std::size_t active_ = 0;
public:
    bool enter() {
        const std::lock_guard lock(mutex_);
        if (draining_) return false;
        ++active_;
        return true;
    }
    void leave() {
        const std::lock_guard lock(mutex_);
        if (active_ == 0) std::terminate();
        --active_;
    }
    void drain() { const std::lock_guard lock(mutex_); draining_ = true; }
    bool ready() const { const std::lock_guard lock(mutex_); return !draining_; }
    bool stopped() const {
        const std::lock_guard lock(mutex_);
        return draining_ && active_ == 0;
    }
};

struct ActiveRequest {
    Admission& gate;
    explicit ActiveRequest(Admission& owner) : gate(owner) {}
    ~ActiveRequest() { gate.leave(); }
    ActiveRequest(const ActiveRequest&) = delete;
    ActiveRequest& operator=(const ActiveRequest&) = delete;
};

bool local_ready() {
    return !std::ifstream(not_ready_file).good();
}

int self_test() {
    Admission gate;
    if (!gate.enter()) return 1;
    gate.drain();
    if (gate.ready() || gate.enter() || gate.stopped()) return 2;
    gate.leave();
    if (!gate.stopped()) return 3;
    std::cout << "admission/drain self-test passed\n";
    return 0;
}
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--self-test") return self_test();
    if (argc == 2 && std::string(argv[1]) == "--not-ready") {
        std::ofstream out(not_ready_file);
        if (!out) return 1;
        out << "manual laboratory readiness failure\n";
        return out.good() ? 0 : 1;
    }
    if (argc == 2 && std::string(argv[1]) == "--ready") {
        std::ifstream current(not_ready_file);
        if (!current.good()) return 0;
        current.close();
        return std::remove(not_ready_file) == 0 ? 0 : 1;
    }
    if (argc == 4 && std::string(argv[1]) == "--get") {
        // HOST is a name in the reader's own isolated cluster. This is not
        // a browser proxy. DNS has its own resolver timing; I/O timeouts are
        // not advertised as a bound on the entire name-resolution process.
        httplib::Client client(argv[2], 80);
        client.set_connection_timeout(2, 0);
        client.set_read_timeout(2, 0);
        client.set_write_timeout(2, 0);
        auto result = client.Get(argv[3]);
        if (!result) { std::cerr << "request failed\n"; return 1; }
        std::cout << result->status << '\n' << result->body;
        return result->status == 200 ? 0 : 1;
    }
    if (argc != 1) {
        std::cerr << "usage: server [--self-test|--not-ready|--ready|--get HOST PATH]\n";
        return 2;
    }

    sigset_t signals;
    sigemptyset(&signals);
    sigaddset(&signals, SIGTERM);
    sigaddset(&signals, SIGINT);
    if (pthread_sigmask(SIG_BLOCK, &signals, nullptr) != 0) return 3;
    // Blocking before starting any thread makes the listener and its workers
    // inherit the mask. Signal handling stays in this ordinary main thread.
    Admission gate;
    httplib::Server server;
    // cpp-httplib0.59.0: base threads, maximum threads, queued-request limit.
    server.new_task_queue = [] { return new httplib::ThreadPool(4, 4, 16); };
    server.set_read_timeout(2, 0);
    server.set_write_timeout(2, 0);
    server.set_keep_alive_max_count(1);
    server.set_payload_max_length(1024);
    const char* version_env = std::getenv("APP_VERSION");
    const std::string version = version_env ? version_env : "v1";
    const char* instance_env = std::getenv("APP_INSTANCE");
    const std::string instance = instance_env ? instance_env : "local";

    server.Get("/livez", [](const auto&, auto& response) {
        response.set_content("alive\n", "text/plain");
    });
    server.Get("/readyz", [&](const auto&, auto& response) {
        response.status = gate.ready() && local_ready() ? 200 : 503;
        response.set_content(response.status == 200 ? "ready\n" : "not ready\n",
                             "text/plain");
    });
    const auto serve = [&](const httplib::Request& request, httplib::Response& response) {
        if (!gate.enter()) {
            response.status = 503;
            response.set_content("draining\n", "text/plain");
            return;
        }
        ActiveRequest active(gate);
        if (request.path == "/work")
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        response.set_content("course-api " + version + " instance=" + instance + "\n",
                             "text/plain");
    };
    server.Get("/", serve);
    server.Get("/work", serve);
    // Only run this server in the lab network. Pod HTTP probes address the Pod
    // interface, so a listener restricted to 127.0.0.1 would not be sufficient.
    if (!server.bind_to_port("0.0.0.0", 8080)) return 4;
    std::atomic<bool> listener_done{false};
    std::jthread listener([&] {
        server.listen_after_bind();
        listener_done.store(true);
    });
    std::cout << "listening 8080 version=" << version << " instance=" << instance << std::endl;
    while (!listener_done.load()) {
        timespec wait{0, 100000000};
        const int signal = sigtimedwait(&signals, nullptr, &wait);
        if (signal == SIGTERM || signal == SIGINT) {
            gate.drain();
            std::cout << "drain: no new business requests" << std::endl;
            server.stop();
            break;
        }
    }
    listener.join();
    // cpp-httplib's task-queue shutdown joins workers before listen returns.
    // This is a demonstration, not a proof of any deployment's total deadline.
    if (!gate.stopped()) gate.drain();
    std::cout << "stopped drained=" << std::boolalpha << gate.stopped() << std::endl;
}
