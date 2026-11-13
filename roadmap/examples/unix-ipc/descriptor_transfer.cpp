#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "ipc_common.hpp"
#include <array>
#include <cstddef>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <vector>

struct Record {
    std::string body;
    std::vector<ipc::Fd> descriptors;
    ucred credentials{};
    bool has_credentials = false;
};

static void send_record(int socket, std::string_view body, int file = -1) {
    ipc::require(!body.empty() && body.size() <= 128, "record body bound");
    iovec io{const_cast<char*>(body.data()), body.size()};
    alignas(cmsghdr) std::array<std::byte, CMSG_SPACE(sizeof(int))> control{};
    msghdr msg{};
    msg.msg_iov = &io; msg.msg_iovlen = 1;
    if (file >= 0) {
        msg.msg_control = control.data(); msg.msg_controllen = control.size();
        cmsghdr* header = CMSG_FIRSTHDR(&msg);
        header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
        header->cmsg_len = CMSG_LEN(sizeof(int));
        std::memcpy(CMSG_DATA(header), &file, sizeof file);
    }
    ssize_t n;
    do { n = ::sendmsg(socket, &msg, MSG_NOSIGNAL); } while (n < 0 && errno == EINTR);
    if (n < 0) ipc::fail("sendmsg");
    ipc::require(static_cast<std::size_t>(n) == body.size(), "incomplete record");
}

static Record receive_record(int socket) {
    std::array<char, 128> data{};
    // Extra descriptor slots let us reject and close unexpected delivered FDs.
    alignas(cmsghdr) std::array<std::byte,
        CMSG_SPACE(4 * sizeof(int)) + CMSG_SPACE(sizeof(ucred))> control{};
    iovec io{data.data(), data.size()};
    msghdr msg{};
    msg.msg_iov = &io; msg.msg_iovlen = 1;
    msg.msg_control = control.data(); msg.msg_controllen = control.size();
    ssize_t n;
    do { n = ::recvmsg(socket, &msg, MSG_CMSG_CLOEXEC); } while (n < 0 && errno == EINTR);
    if (n < 0) ipc::fail("recvmsg");
    ipc::require(n > 0, "peer ended before record");
    Record result;
    bool malformed = false;
    for (cmsghdr* c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
        if (c->cmsg_len < CMSG_LEN(0)) { malformed = true; continue; }
        const std::size_t size = c->cmsg_len - CMSG_LEN(0);
        if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS) {
            if (size % sizeof(int) != 0) malformed = true;
            for (std::size_t offset = 0; offset + sizeof(int) <= size; offset += sizeof(int)) {
                int received = -1;
                std::memcpy(&received, CMSG_DATA(c) + offset, sizeof received);
                result.descriptors.emplace_back(received);
            }
        } else if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS) {
            if (size != sizeof(ucred) || result.has_credentials) malformed = true;
            else {
                std::memcpy(&result.credentials, CMSG_DATA(c), sizeof(ucred));
                result.has_credentials = true;
            }
        } else malformed = true;
    }
    // Already collected FDs are RAII-owned even when we reject the record.
    ipc::require(!(msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC)), "truncated record");
    ipc::require(!malformed && result.has_credentials, "invalid ancillary data");
    result.body.assign(data.data(), static_cast<std::size_t>(n));
    return result;
}

static void write_file(int file, std::string_view bytes) {
    while (!bytes.empty()) {
        const ssize_t n = ::write(file, bytes.data(), bytes.size());
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) ipc::fail("write temporary file");
        ipc::require(n > 0, "file write made no progress");
        bytes.remove_prefix(static_cast<std::size_t>(n));
    }
}

int main() {
    try {
        int pair[2];
        if (::socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) < 0)
            ipc::fail("socketpair");
        ipc::Fd parent(pair[0]), worker(pair[1]);
        int enabled = 1;
        for (int endpoint : pair)
            if (::setsockopt(endpoint, SOL_SOCKET, SO_PASSCRED, &enabled, sizeof enabled) < 0)
                ipc::fail("SO_PASSCRED");
        const pid_t child = ::fork();
        if (child < 0) ipc::fail("fork");
        if (child == 0) {
            parent.reset();
            Record request = receive_record(worker.get());
            ipc::require(request.body == "FILE" && request.descriptors.size() == 1,
                         "expected exactly one file descriptor");
            ipc::require(request.credentials.pid == ::getppid() &&
                         request.credentials.uid == ::getuid(), "unexpected sender credentials");
            const int file = request.descriptors[0].get();
            const int flags = ::fcntl(file, F_GETFD);
            if (flags < 0) ipc::fail("F_GETFD");
            ipc::require((flags & FD_CLOEXEC) != 0, "received FD lacks CLOEXEC");
            std::string prefix;
            while (prefix.size() < 6) {
                char bytes[6];
                const ssize_t n = ::read(file, bytes, 6 - prefix.size());
                if (n < 0 && errno == EINTR) continue;
                if (n < 0) ipc::fail("read received file");
                ipc::require(n > 0, "unexpected file EOF");
                prefix.append(bytes, static_cast<std::size_t>(n));
            }
            ipc::require(prefix == "shared", "unexpected prefix");
            send_record(worker.get(), "read:" + prefix);
            return 0;
        }
        worker.reset();
        char path[] = "/tmp/course-unix-ipc-XXXXXX";
        ipc::Fd file(::mkostemp(path, O_CLOEXEC));
        if (file.get() < 0) ipc::fail("mkostemp");
        if (::unlink(path) < 0) ipc::fail("unlink own temporary file");
        write_file(file.get(), "shared:41\n");
        if (::lseek(file.get(), 0, SEEK_SET) < 0) ipc::fail("lseek");
        send_record(parent.get(), "FILE", file.get());
        Record reply = receive_record(parent.get());
        ipc::require(reply.body == "read:shared" && reply.descriptors.empty(), "unexpected reply");
        ipc::require(reply.credentials.pid == child && reply.credentials.uid == ::getuid(),
                     "unexpected worker credentials");
        const std::string tail = ipc::read_to_eof(file.get());
        ipc::wait_child(child);
        ipc::require(tail == ":41\n", "open file description offset was not shared");
        std::cout << "child_prefix=shared\nparent_tail=" << tail
                  << "fd_cloexec=true\ncredential_uid_match=true\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
