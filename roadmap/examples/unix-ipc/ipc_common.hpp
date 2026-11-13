#pragma once
// Linux-only teaching helpers. The programs start single-threaded before fork.
#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

namespace ipc {
[[noreturn]] inline void fail(const char* operation) {
    throw std::runtime_error(std::string(operation) + ": " + std::strerror(errno));
}
inline void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
class Fd {
    int value_ = -1;
public:
    explicit Fd(int value = -1) noexcept : value_(value) {}
    ~Fd() { reset(); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    Fd(Fd&& other) noexcept : value_(std::exchange(other.value_, -1)) {}
    Fd& operator=(Fd&& other) noexcept {
        if (this != &other) { reset(); value_ = std::exchange(other.value_, -1); }
        return *this;
    }
    int get() const noexcept { return value_; }
    void reset() noexcept {
        const int old = std::exchange(value_, -1);
        if (old >= 0) { const int saved = errno; (void)::close(old); errno = saved; }
    }
};
inline void send_all(int fd, std::string_view bytes) {
    while (!bytes.empty()) {
        const ssize_t n = ::send(fd, bytes.data(), bytes.size(), MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) fail("send");
        require(n > 0, "send made no progress");
        bytes.remove_prefix(static_cast<std::size_t>(n));
    }
}
inline std::string read_to_eof(int fd, std::size_t limit = 128) {
    std::string result;
    char bytes[32];
    for (;;) {
        const ssize_t n = ::read(fd, bytes, sizeof bytes);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) fail("read");
        if (n == 0) return result;
        require(result.size() + static_cast<std::size_t>(n) <= limit,
                "teaching message exceeded its bound");
        result.append(bytes, static_cast<std::size_t>(n));
    }
}
inline void wait_child(pid_t child) {
    int status = 0;
    pid_t result;
    do { result = ::waitpid(child, &status, 0); } while (result < 0 && errno == EINTR);
    if (result < 0) fail("waitpid");
    require(WIFEXITED(status) && WEXITSTATUS(status) == 0, "child did not succeed");
}
}
