// Linux IPv4: local-host experiment by default (TTL = 0).
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include <cerrno>
#include <iostream>
#include <stdexcept>
#include <string>
#include <system_error>

struct Socket {
    int fd;
    explicit Socket(int value) : fd(value) {}
    ~Socket() { if (fd >= 0) ::close(fd); }
    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;
};
void checked(int result, const char* operation) {
    if (result < 0)
        throw std::system_error(errno, std::generic_category(), operation);
}
in_addr address(const char* text) {
    in_addr value{};
    if (::inet_pton(AF_INET, text, &value) != 1)
        throw std::invalid_argument("expected numeric IPv4 address");
    return value;
}
int main(int argc, char** argv) {
    try {
        if (argc != 3 || (std::string(argv[1]) != "send"
                       && std::string(argv[1]) != "recv")) {
            std::cerr << "usage: multicast send|recv LOCAL_IPV4\n";
            return 2;
        }
        const auto interface = address(argv[2]);
        const auto group = address("239.255.42.42");
        constexpr unsigned short port = 45042;
        Socket socket{::socket(AF_INET, SOCK_DGRAM, 0)};
        checked(socket.fd, "socket");
        if (std::string(argv[1]) == "send") {
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_MULTICAST_IF,
                                &interface, sizeof(interface)), "outgoing interface");
            const unsigned char ttl = 0; // do not leave this host
            const unsigned char loop = 1;
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_MULTICAST_TTL,
                                &ttl, sizeof(ttl)), "TTL");
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_MULTICAST_LOOP,
                                &loop, sizeof(loop)), "local loop");
            sockaddr_in target{};
            target.sin_family = AF_INET;
            target.sin_port = htons(port);
            target.sin_addr = group;
            const std::string message = "seq=1 value=42";
            const auto sent = ::sendto(socket.fd, message.data(), message.size(), 0,
                                      reinterpret_cast<sockaddr*>(&target), sizeof(target));
            checked(static_cast<int>(sent), "sendto");
            if (static_cast<std::size_t>(sent) != message.size())
                throw std::runtime_error("unexpected datagram size");
            std::cout << "sent locally; delivery not acknowledged\n";
        } else {
            const int reuse = 1;
            checked(::setsockopt(socket.fd, SOL_SOCKET, SO_REUSEADDR,
                                &reuse, sizeof(reuse)), "reuse address");
            const int all = 0; // Linux: only groups joined by this socket
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_MULTICAST_ALL,
                                &all, sizeof(all)), "multicast filter");
            sockaddr_in local{};
            local.sin_family = AF_INET;
            local.sin_port = htons(port);
            local.sin_addr.s_addr = htonl(INADDR_ANY);
            checked(::bind(socket.fd, reinterpret_cast<sockaddr*>(&local),
                           sizeof(local)), "bind");
            ip_mreq membership{};
            membership.imr_multiaddr = group;
            membership.imr_interface = interface;
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_ADD_MEMBERSHIP,
                                &membership, sizeof(membership)), "join");
            const timeval timeout{5, 0};
            checked(::setsockopt(socket.fd, SOL_SOCKET, SO_RCVTIMEO,
                                &timeout, sizeof(timeout)), "receive timeout");
            std::cout << "joined; waiting up to 5 seconds\n" << std::flush;
            char buffer[1024];
            const auto received = ::recvfrom(socket.fd, buffer, sizeof(buffer),
                                            MSG_TRUNC, nullptr, nullptr);
            checked(static_cast<int>(received), "recvfrom");
            if (static_cast<std::size_t>(received) > sizeof(buffer))
                throw std::runtime_error("datagram truncated");
            std::cout.write(buffer, received);
            std::cout << '\n';
            checked(::setsockopt(socket.fd, IPPROTO_IP, IP_DROP_MEMBERSHIP,
                                &membership, sizeof(membership)), "leave");
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
