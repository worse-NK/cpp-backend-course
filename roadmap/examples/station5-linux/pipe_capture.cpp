#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <spawn.h>
#include <stdexcept>
#include <string_view>
#include <system_error>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>

extern char** environ;

class Fd {
    int value_;
public:
    explicit Fd(int value) noexcept : value_(value) {}
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    int get() const noexcept { return value_; }
    void close_now() noexcept {
        const int old = std::exchange(value_, -1);
        if (old >= 0) (void)::close(old); // Linux: never blindly retry close.
    }
    ~Fd() { close_now(); }
};

void check_code(int code, const char* operation) {
    // posix_spawn APIs return the error number, not -1 plus errno.
    if (code != 0) throw std::system_error(code, std::generic_category(), operation);
}

class Actions {
public:
    posix_spawn_file_actions_t value{};
    Actions() { check_code(::posix_spawn_file_actions_init(&value), "actions_init"); }
    Actions(const Actions&) = delete;
    Actions& operator=(const Actions&) = delete;
    ~Actions() { (void)::posix_spawn_file_actions_destroy(&value); }
};

int writer(bool fail, bool empty) {
    constexpr char row[] = "ABCDE\n";
    const int count = empty ? 0 : 40000;
    for (int i = 0; i < count; ++i) {
        std::size_t offset = 0;
        while (offset < sizeof(row) - 1) {
            const auto n = ::write(STDOUT_FILENO, row + offset, sizeof(row) - 1 - offset);
            if (n > 0) offset += static_cast<std::size_t>(n);
            else if (n < 0 && errno == EINTR) continue;
            else return 3;
        }
    }
    return fail ? 7 : 0;
}

int main(int argc, char** argv) {
    const std::string_view mode = argc == 2 ? argv[1] : "";
    if (mode == "--writer") return writer(false, false);
    if (mode == "--writer-fail") return writer(true, false);
    if (mode == "--writer-empty") return writer(false, true);
    if (argc > 2 || (mode != "" && mode != "--fail" &&
                     mode != "--empty" && mode != "--missing")) return 64;
    try {
        // Keep this introductory example explicit: standard FDs must be open.
        for (int fd = 0; fd != 3; ++fd)
            if (::fcntl(fd, F_GETFD) == -1)
                throw std::system_error(errno, std::generic_category(), "standard fd");
        int ends[2];
        if (::pipe2(ends, O_CLOEXEC) == -1)
            throw std::system_error(errno, std::generic_category(), "pipe2");
        Fd input(ends[0]), output(ends[1]);
        Actions actions;
        check_code(::posix_spawn_file_actions_adddup2(&actions.value, output.get(),
                                                     STDOUT_FILENO), "adddup2");
        check_code(::posix_spawn_file_actions_addclose(&actions.value, input.get()), "close input");
        check_code(::posix_spawn_file_actions_addclose(&actions.value, output.get()), "close output");
        char name[] = "pipe_capture";
        char normal[] = "--writer", failed[] = "--writer-fail", empty[] = "--writer-empty";
        char* child_args[] = {name, mode == "--fail" ? failed :
                                  mode == "--empty" ? empty : normal, nullptr};
        const char* executable = mode == "--missing" ?
            "/this-course-example-has-no-such-program" : "/proc/self/exe";
        pid_t child{};
        check_code(::posix_spawn(&child, executable, &actions.value, nullptr,
                                child_args, environ), "posix_spawn");
        output.close_now(); // Parent must not keep a pipe writer alive.

        std::array<char, 4096> buffer{};
        std::uint64_t bytes = 0, checksum = 0;
        int read_error = 0;
        for (;;) {
            const auto n = ::read(input.get(), buffer.data(), buffer.size());
            if (n > 0) {
                bytes += static_cast<std::uint64_t>(n);
                for (ssize_t i = 0; i < n; ++i)
                    checksum += static_cast<unsigned char>(buffer[static_cast<std::size_t>(i)]);
            } else if (n == 0) break;
            else if (errno == EINTR) continue;
            else { read_error = errno; break; }
        }
        input.close_now(); // Close before waiting, including a read-error path.
        int status = 0;
        while (::waitpid(child, &status, 0) == -1) {
            if (errno == EINTR) continue;
            throw std::system_error(errno, std::generic_category(), "waitpid");
        }
        if (read_error != 0)
            throw std::system_error(read_error, std::generic_category(), "read");
        std::printf("bytes=%llu checksum=%llu\n", static_cast<unsigned long long>(bytes),
                    static_cast<unsigned long long>(checksum));
        if (WIFEXITED(status)) {
            const int code = WEXITSTATUS(status);
            std::printf("child_exit=%d\n", code);
            return code == 0 ? 0 : 2;
        }
        if (WIFSIGNALED(status)) std::printf("child_signal=%d\n", WTERMSIG(status));
        return 2;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
