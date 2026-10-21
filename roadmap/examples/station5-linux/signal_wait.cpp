#include <cerrno>
#include <csignal>
#include <cstdio>

int main() {
    // Single-threaded demo. Only a signal sent to this process is generated.
    sigset_t selected;
    if (::sigemptyset(&selected) == -1 || ::sigaddset(&selected, SIGTERM) == -1)
        return 1;
    if (::sigprocmask(SIG_BLOCK, &selected, nullptr) == -1)
        return 1;
    if (::raise(SIGTERM) != 0)
        return 1;
    int received;
    do {
        received = ::sigwaitinfo(&selected, nullptr);
    } while (received == -1 && errno == EINTR);
    if (received != SIGTERM)
        return 1;
    // This is ordinary code, not an asynchronous signal handler.
    std::puts("received SIGTERM");
    std::puts("cleanup in normal code");
}
