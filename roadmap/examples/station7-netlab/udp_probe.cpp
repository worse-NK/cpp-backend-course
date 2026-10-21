// Linux, C++20. Один учебный запрос, без DNS, повторов и гарантий доставки.
// Не production-сервер: нет аутентификации, защиты от подделки и конкурентности.
#include <arpa/inet.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <algorithm>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <climits>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>

namespace {
using Clock = std::chrono::steady_clock;
using Deadline = Clock::time_point;
constexpr std::string_view request = "course7:ping", response = "course7:pong";
struct Usage : std::runtime_error { using std::runtime_error::runtime_error; };
struct Timeout : std::runtime_error { Timeout() : std::runtime_error("timeout (5 s deadline)") {} };
[[noreturn]] void system_failure(const char* operation) {
    throw std::system_error(errno, std::generic_category(), operation);
}
class Fd {
    int value_;
public:
    explicit Fd(int value) : value_(value) { if (value < 0) system_failure("socket"); }
    ~Fd() { ::close(value_); } // В Linux close после EINTR не повторяем.
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    int get() const noexcept { return value_; }
};
struct Address {
    sockaddr_storage value{};
    socklen_t size = sizeof(value);
    sockaddr* ptr() { return reinterpret_cast<sockaddr*>(&value); }
    const sockaddr* ptr() const { return reinterpret_cast<const sockaddr*>(&value); }
};
unsigned short parse_port(std::string_view port_text) {
    unsigned port = 0;
    const auto result = std::from_chars(port_text.data(), port_text.data() + port_text.size(), port);
    if (result.ec != std::errc{} || result.ptr != port_text.data() + port_text.size() || port == 0 || port > 65535)
        throw Usage("port must be a decimal integer in 1..65535");
    return static_cast<unsigned short>(port);
}
Address parse_address(const char* host, std::string_view port_text, bool allow_wildcard = false) {
    const auto port = parse_port(port_text);
    Address address;
    sockaddr_in v4{};
    v4.sin_family = AF_INET;
    v4.sin_port = htons(port);
    if (::inet_pton(AF_INET, host, &v4.sin_addr) == 1) {
        if (!allow_wildcard && v4.sin_addr.s_addr == htonl(INADDR_ANY)) throw Usage("wildcard address is not allowed");
        address.size = sizeof(v4);
        std::memcpy(&address.value, &v4, sizeof(v4));
        return address;
    }
    sockaddr_in6 v6{};
    v6.sin6_family = AF_INET6;
    v6.sin6_port = htons(port);
    if (::inet_pton(AF_INET6, host, &v6.sin6_addr) != 1)
        throw Usage("use a numeric IPv4/IPv6 address (no DNS, brackets or scope suffix)");
    if ((!allow_wildcard && IN6_IS_ADDR_UNSPECIFIED(&v6.sin6_addr)) || IN6_IS_ADDR_V4MAPPED(&v6.sin6_addr))
        throw Usage("wildcard and IPv4-mapped IPv6 addresses are not allowed");
    address.size = sizeof(v6);
    std::memcpy(&address.value, &v6, sizeof(v6));
    return address;
}
std::string numeric(const Address& address) {
    char host[NI_MAXHOST]{}, port[NI_MAXSERV]{};
    const int error = ::getnameinfo(address.ptr(), address.size, host, sizeof(host), port, sizeof(port),
                                    NI_NUMERICHOST | NI_NUMERICSERV | NI_DGRAM);
    if (error != 0) throw std::runtime_error(std::string("getnameinfo: ") + ::gai_strerror(error));
    return address.value.ss_family == AF_INET6 ? "[" + std::string(host) + "]:" + port
                                               : std::string(host) + ":" + port;
}
Address socket_address(int fd, bool peer) {
    Address address;
    const int result = peer ? ::getpeername(fd, address.ptr(), &address.size)
                            : ::getsockname(fd, address.ptr(), &address.size);
    if (result < 0) system_failure(peer ? "getpeername" : "getsockname");
    return address;
}
void connect_peer(int fd, const Address& address) {
    if (::connect(fd, address.ptr(), address.size) < 0) system_failure("connect UDP");
}
void print_endpoints(int fd) {
    std::cout << "local=" << numeric(socket_address(fd, false))
              << " peer=" << numeric(socket_address(fd, true)) << '\n';
}
void wait_ready(int fd, short events, Deadline deadline) {
    for (;;) {
        const auto remaining = deadline - Clock::now();
        if (remaining <= Clock::duration::zero()) throw Timeout();
        const auto ms = std::chrono::ceil<std::chrono::milliseconds>(remaining).count();
        const int timeout = static_cast<int>(std::clamp<decltype(ms)>(ms, 1, INT_MAX));
        pollfd item{fd, events, 0};
        const int result = ::poll(&item, 1, timeout);
        if (result < 0) { if (errno == EINTR) continue; system_failure("poll"); }
        if (result == 0) continue; // Повторно сравниваем с абсолютным steady-clock deadline.
        if (Clock::now() >= deadline) throw Timeout(); // Readiness не продлевает deadline после паузы планировщика.
        if ((item.revents & POLLNVAL) != 0) throw std::runtime_error("poll: invalid fd");
        if ((item.revents & events) != 0) return;
        if ((item.revents & POLLERR) != 0) {
            int error = 0;
            socklen_t size = sizeof(error);
            if (::getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) < 0) system_failure("SO_ERROR");
            if (error != 0) throw std::system_error(error, std::generic_category(), "UDP socket");
            throw std::runtime_error("poll: socket error without SO_ERROR");
        }
        if ((item.revents & POLLHUP) != 0) throw std::runtime_error("poll: unexpected hangup");
    }
}
void send_packet(int fd, std::string_view payload, Deadline deadline) {
    for (;;) {
        if (Clock::now() >= deadline) throw Timeout();
        const auto count = ::send(fd, payload.data(), payload.size(), MSG_DONTWAIT);
        if (count >= 0) {
            if (static_cast<std::size_t>(count) != payload.size()) throw std::runtime_error("short UDP send");
            return; // Один datagram, НЕ цикл досылки TCP-хвоста.
        }
        if (errno == EINTR) continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK) { wait_ready(fd, POLLOUT, deadline); continue; }
        system_failure("send");
    }
}
Address receive_packet(int fd, std::string_view expected, Deadline deadline) {
    for (;;) {
        wait_ready(fd, POLLIN, deadline);
        char buffer[64]{};
        Address peer;
        iovec vector{buffer, sizeof(buffer)};
        msghdr message{};
        message.msg_name = peer.ptr();
        message.msg_namelen = peer.size;
        message.msg_iov = &vector;
        message.msg_iovlen = 1;
        const auto count = ::recvmsg(fd, &message, MSG_DONTWAIT | MSG_TRUNC);
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) continue;
            system_failure("recvmsg");
        }
        if ((message.msg_flags & MSG_TRUNC) != 0 || static_cast<std::size_t>(count) > sizeof(buffer))
            throw std::runtime_error("truncated datagram rejected");
        if (count == 0 || std::string_view(buffer, static_cast<std::size_t>(count)) != expected)
            throw std::runtime_error("empty or unexpected datagram rejected");
        peer.size = message.msg_namelen;
        if (peer.size > sizeof(peer.value)) throw std::runtime_error("invalid peer address length");
        return peer;
    }
}
} // namespace

int main(int argc, char** argv) {
    try {
        if ((argc != 4 && argc != 5) || (std::string_view(argv[1]) != "server" && std::string_view(argv[1]) != "client")
            || (argc == 5 && std::string_view(argv[1]) == "server"))
            throw Usage("usage: udp_probe server <numeric-IP> <port> | client <numeric-IP> <port> [source-port]");
        const bool server = std::string_view(argv[1]) == "server";
        const Address target = parse_address(argv[2], argv[3]); // Все usage-проверки ДО socket().
        const Address local = argc == 5 ? parse_address(target.value.ss_family == AF_INET ? "0.0.0.0" : "::", argv[4], true)
                                       : Address{};
        Fd socket(::socket(target.value.ss_family, SOCK_DGRAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0));
        const int fd = socket.get();
        if (target.value.ss_family == AF_INET6) {
            const int only_v6 = 1;
            if (::setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &only_v6, sizeof(only_v6)) < 0)
                system_failure("IPV6_V6ONLY");
        }
        if (server) {
            if (::bind(fd, target.ptr(), target.size) < 0) system_failure("bind");
            std::cout << "ready local=" << numeric(socket_address(fd, false)) << '\n' << std::flush;
            const Deadline deadline = Clock::now() + std::chrono::seconds(5);
            const Address peer = receive_packet(fd, request, deadline);
            connect_peer(fd, peer);
            print_endpoints(fd);
            send_packet(fd, response, deadline);
            std::cout << "sent course7:pong (delivery not guaranteed)\n";
        } else {
            // Только client: фиксируем локальный порт, не включая SO_REUSEADDR.
            // Wildcard здесь означает выбор исходного IP маршрутом, не сервер на всех адресах.
            if (argc == 5 && ::bind(fd, local.ptr(), local.size) < 0) system_failure("bind source port");
            connect_peer(fd, target); // UDP connect не выполняет handshake и не доказывает живость сервера.
            print_endpoints(fd);
            const Deadline deadline = Clock::now() + std::chrono::seconds(5);
            send_packet(fd, request, deadline);
            receive_packet(fd, response, deadline); // Connected UDP фильтрует чужие endpoint, НЕ аутентифицирует.
            std::cout << "received course7:pong\n";
        }
        return 0;
    } catch (const Usage& error) { std::cerr << error.what() << '\n'; return 64;
    } catch (const Timeout& error) { std::cerr << error.what() << '\n'; return 2;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
