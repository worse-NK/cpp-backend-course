#include "ipc_common.hpp"
#include <iostream>

int main() {
    try {
        int pair[2];
        if (::socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair) < 0)
            ipc::fail("socketpair");
        ipc::Fd parent(pair[0]), worker(pair[1]);
        const pid_t child = ::fork();
        if (child < 0) ipc::fail("fork");
        if (child == 0) {
            parent.reset();
            const std::string request = ipc::read_to_eof(worker.get());
            ipc::require(request == "job:41\n", "unexpected request");
            ipc::send_all(worker.get(), "accepted " + request);
            return 0; // worker's last descriptor closes; parent can observe EOF.
        }
        worker.reset();
        ipc::send_all(parent.get(), "job:41\n");
        if (::shutdown(parent.get(), SHUT_WR) < 0) ipc::fail("shutdown");
        const std::string reply = ipc::read_to_eof(parent.get());
        ipc::wait_child(child); // Drain first, then wait: no circular wait for output.
        ipc::require(reply == "accepted job:41\n", "unexpected reply");
        std::cout << "reply: " << reply;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
