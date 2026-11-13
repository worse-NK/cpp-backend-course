// Linux/glibc address candidates, not a DNS-only tool or reachability test.
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <iostream>
#include <memory>

int main(int argc, char** argv) {
    if (argc > 2) return 2;
    const char* host = argc == 2 ? argv[1] : "localhost";
    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_NUMERICSERV;
    addrinfo* raw = nullptr;
    const int error = getaddrinfo(host, "443", &hints, &raw);
    if (error != 0) {
        std::cerr << "lookup: " << gai_strerror(error) << '\n';
        return 1;
    }
    std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> addresses(raw, freeaddrinfo);
    for (auto p = addresses.get(); p; p = p->ai_next) {
        char address[NI_MAXHOST]{}, service[NI_MAXSERV]{};
        const int result = getnameinfo(p->ai_addr, p->ai_addrlen,
            address, sizeof address, service, sizeof service,
            NI_NUMERICHOST | NI_NUMERICSERV);
        if (result != 0) return 1;
        std::cout << (p->ai_family == AF_INET6 ? "IPv6 " : "IPv4 ")
                  << address << " port=" << service << '\n';
    }
}
