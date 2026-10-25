#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <sys/mman.h>
#include <sys/stat.h>
#include <system_error>
#include <unistd.h>

[[noreturn]] void fail(const char* operation) {
    const int saved = errno;
    throw std::system_error(saved, std::generic_category(), operation);
}

class Fd {
    int value_;
public:
    explicit Fd(int value) : value_(value) {
        if (value_ < 0) fail("openat");
    }
    ~Fd() { ::close(value_); } // One close; do not retry blindly.
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    int get() const { return value_; }
};

class Workspace {
    char path_[64] = "/tmp/course-mapped-generation-XXXXXX";
    int directory_ = -1;
public:
    Workspace() {
        if (!::mkdtemp(path_)) fail("mkdtemp");
        directory_ = ::open(path_, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (directory_ < 0) {
            const int saved = errno;
            ::rmdir(path_); // Only the empty directory just created by us.
            throw std::system_error(saved, std::generic_category(), "open directory");
        }
    }
    ~Workspace() {
        // Only our two fixed names in our private, newly created directory.
        ::unlinkat(directory_, "next.bin", 0);
        ::unlinkat(directory_, "catalog.bin", 0);
        ::close(directory_);
        ::rmdir(path_);
    }
    Workspace(const Workspace&) = delete;
    Workspace& operator=(const Workspace&) = delete;
    int get() const { return directory_; }
};

void publish(const Workspace& workspace, std::string_view contents) {
    Fd file(::openat(workspace.get(), "next.bin",
                    O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600));
    if (::fchmod(file.get(), 0600) < 0) fail("fchmod own temporary file");
    std::size_t written = 0;
    while (written < contents.size()) {
        const auto n = ::write(file.get(), contents.data() + written,
                               contents.size() - written);
        if (n > 0) written += static_cast<std::size_t>(n);
        else if (n < 0 && errno == EINTR) continue;
        else if (n < 0) fail("write");
        else throw std::runtime_error("write made no progress");
    }
    if (::fsync(file.get()) < 0) fail("fsync file");
    if (::renameat(workspace.get(), "next.bin", workspace.get(), "catalog.bin") < 0)
        fail("renameat");
    if (::fsync(workspace.get()) < 0) fail("fsync directory");
}

class Mapping {
    const char* bytes_ = nullptr;
    std::size_t length_ = 0;
public:
    explicit Mapping(const Workspace& workspace) {
        Fd file(::openat(workspace.get(), "catalog.bin",
                         O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
        struct stat info {};
        if (::fstat(file.get(), &info) < 0) fail("fstat");
        if (!S_ISREG(info.st_mode) || info.st_size <= 0 || info.st_size > 4096)
            throw std::runtime_error("expected a small nonempty regular file");
        length_ = static_cast<std::size_t>(info.st_size);
        void* region = ::mmap(nullptr, length_, PROT_READ, MAP_PRIVATE, file.get(), 0);
        if (region == MAP_FAILED) fail("mmap");
        bytes_ = static_cast<const char*>(region);
        // Closing this FD does not invalidate the successfully created mapping.
    }
    ~Mapping() { ::munmap(const_cast<char*>(bytes_), length_); }
    Mapping(const Mapping&) = delete;
    Mapping& operator=(const Mapping&) = delete;
    std::string_view text() const { return {bytes_, length_}; }
};

int main() {
    try {
        Workspace workspace;
        publish(workspace, "generation-1");
        Mapping reader1(workspace);
        std::cout << "R1 before: " << reader1.text() << '\n';
        publish(workspace, "generation-2");
        Mapping reader2(workspace);
        std::cout << "R2 after: " << reader2.text() << '\n';
        std::cout << "R1 still: " << reader1.text() << '\n';
        // Mappings die before workspace. No threads or production files involved.
    } catch (const std::exception& error) {
        std::cerr << "example failed: " << error.what() << '\n';
        return 1;
    }
}
