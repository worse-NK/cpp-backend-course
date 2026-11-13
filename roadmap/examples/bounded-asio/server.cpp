// Boost.Asio 1.85; one io_context::run thread; loopback only.
#include <utility>
#include <boost/asio.hpp>
#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <climits>
#include <csignal>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace asio = boost::asio;
using tcp = asio::ip::tcp;
using Error = boost::system::error_code;
using Clock = std::chrono::steady_clock;
constexpr std::size_t max_payload = 65536;
constexpr std::size_t max_sessions = 16;
static_assert(CHAR_BIT == 8, "This wire format requires eight-bit bytes");

// A closed session can outlive its active-registry entry: cancelled handlers
// still own it. Release this capacity only when the Session is destroyed.
struct ResidentCount {
    std::size_t live = 0, peak = 0;
};

class Session : public std::enable_shared_from_this<Session> {
    tcp::socket socket_;
    asio::steady_timer timer_;
    Clock::time_point deadline_;
    std::array<unsigned char, 4> header_{};
    std::vector<unsigned char> body_;
    std::function<void(Session*, std::string_view)> on_done_;
    std::shared_ptr<ResidentCount> residents_;
    bool done_ = false;
    enum class Phase { header, body, writing } phase_ = Phase::header;

    void finish(std::string_view reason) {
        if (done_) return;
        done_ = true; // first, before cancellation can produce more handlers
        Error ignored;
        timer_.cancel(ignored);
        socket_.close(ignored);
        on_done_(this, reason);
    }
    bool expired_or_done() {
        if (done_) return true;
        if (Clock::now() >= deadline_) {
            finish("deadline");
            return true;
        }
        return false;
    }
    void write_response() {
        phase_ = Phase::writing;
        std::array<asio::const_buffer, 2> buffers{
            asio::buffer(header_), asio::buffer(body_)};
        auto self = shared_from_this();
        asio::async_write(socket_, buffers, [self](Error ec, std::size_t) {
            if (self->expired_or_done()) return;
            self->finish(ec ? "write_error" : "complete");
        });
    }
    void read_body() {
        phase_ = Phase::body;
        auto self = shared_from_this();
        asio::async_read(socket_, asio::buffer(body_), [self](Error ec, std::size_t) {
            if (self->expired_or_done()) return;
            if (ec) return self->finish("incomplete_body");
            self->write_response();
        });
    }
public:
    Session(tcp::socket socket, std::chrono::milliseconds budget,
            std::function<void(Session*, std::string_view)> on_done,
            std::shared_ptr<ResidentCount> residents)
        : socket_(std::move(socket)), timer_(socket_.get_executor()),
          deadline_(Clock::now() + budget), on_done_(std::move(on_done)),
          residents_(std::move(residents)) {
        if (residents_->live >= max_sessions)
            throw std::logic_error("resident capacity exceeded");
        ++residents_->live;
        residents_->peak = std::max(residents_->peak, residents_->live);
    }
    ~Session() { --residents_->live; }

    void start() {
        // Small socket send buffer makes the slow-reader experience observable.
        // It is an exercise setting, not a production performance recommendation.
        socket_.set_option(asio::socket_base::send_buffer_size(4096));
        timer_.expires_at(deadline_);
        auto self = shared_from_this();
        timer_.async_wait([self](Error ec) {
            if (!ec && !self->done_) self->finish("deadline");
        });
        asio::async_read(socket_, asio::buffer(header_), [self](Error ec, std::size_t n) {
            if (self->expired_or_done()) return;
            if (ec) return self->finish(n == 0 && ec == asio::error::eof
                                      ? "empty_eof" : "incomplete_header");
            std::uint32_t length = 0;
            for (unsigned char byte : self->header_)
                length = (length << 8) | byte;
            if (length == 0 || length > max_payload)
                return self->finish("invalid_length");
            self->body_.resize(length); // only after validating the wire length
            self->read_body();
        });
    }
    void force_stop() { finish("shutdown_limit"); }
    bool writing() const { return phase_ == Phase::writing; }
};

class Server {
    tcp::acceptor acceptor_;
    asio::signal_set signals_;
    asio::steady_timer shutdown_;
    std::set<std::shared_ptr<Session>> sessions_;
    std::shared_ptr<ResidentCount> residents_ = std::make_shared<ResidentCount>();
    std::chrono::milliseconds budget_;
    bool stopping_ = false;
    std::size_t accepted_ = 0, rejected_ = 0, finished_ = 0, peak_ = 0;

    void remove(Session* session, std::string_view reason) {
        auto it = std::find_if(sessions_.begin(), sessions_.end(),
                              [session](const auto& p) { return p.get() == session; });
        if (it == sessions_.end()) throw std::logic_error("duplicate completion");
        const bool writing = (*it)->writing();
        sessions_.erase(it);
        ++finished_;
        std::cout << "finish " << reason << " phase=" << (writing ? "write" : "read")
                  << " active=" << sessions_.size() << '\n';
        if (stopping_ && sessions_.empty()) {
            Error ignored;
            shutdown_.cancel(ignored);
        }
    }
    void accept() {
        acceptor_.async_accept([this](Error ec, tcp::socket socket) {
            if (stopping_) return;
            if (ec) {
                // A persistent accept failure must not become a busy retry loop.
                throw boost::system::system_error(ec);
            }
            if (residents_->live >= max_sessions) {
                ++rejected_;
                Error ignored;
                socket.close(ignored);
            } else {
                ++accepted_;
                auto session = std::make_shared<Session>(std::move(socket), budget_,
                    [this](Session* p, std::string_view reason) { remove(p, reason); },
                    residents_);
                sessions_.insert(session);
                peak_ = std::max(peak_, sessions_.size());
                session->start();
            }
            accept();
        });
    }
public:
    Server(asio::io_context& io, unsigned short port, std::chrono::milliseconds budget)
        : acceptor_(io), signals_(io, SIGINT, SIGTERM), shutdown_(io), budget_(budget) {
        const tcp::endpoint endpoint(asio::ip::make_address("127.0.0.1"), port);
        acceptor_.open(endpoint.protocol());
        acceptor_.bind(endpoint);
        acceptor_.listen(64);
    }
    void start() {
        signals_.async_wait([this](Error ec, int) { if (!ec) begin_stop(); });
        accept();
        std::cout << "ready " << acceptor_.local_endpoint().port() << std::endl;
    }
    void begin_stop() {
        if (stopping_) return;
        stopping_ = true;
        Error ignored;
        acceptor_.close(ignored);
        signals_.cancel(ignored);
        // Each accepted connection has only one frame. Those already accepted
        // may finish during the grace interval; no second frame is ever read.
        if (sessions_.empty()) return;
        shutdown_.expires_after(std::chrono::milliseconds(300));
        shutdown_.async_wait([this](Error ec) {
            if (ec) return;
            // Completion erases from sessions_; iterate a separate ownership list.
            auto pending = std::vector(sessions_.begin(), sessions_.end());
            for (const auto& session : pending) session->force_stop();
        });
    }
    void report() const {
        std::cout << "stopped active=" << sessions_.size() << " accepted=" << accepted_
                  << " finished=" << finished_ << " rejected=" << rejected_
                  << " peak=" << peak_ << " resident=" << residents_->live
                  << " peak_resident=" << residents_->peak << '\n';
    }
};

unsigned number(std::string_view text, unsigned maximum) {
    unsigned value = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size() || value > maximum)
        throw std::invalid_argument("invalid argument");
    return value;
}

int main(int argc, char** argv) {
    try {
        if (argc > 3) throw std::invalid_argument("usage: bounded_server [port] [budget_ms]");
        const auto port = static_cast<unsigned short>(argc > 1 ? number(argv[1], 65535) : 0);
        const auto budget = argc > 2 ? number(argv[2], 10000) : 1000;
        if (budget < 100) throw std::invalid_argument("budget_ms must be 100..10000");
        asio::io_context io;
        Server server(io, port, std::chrono::milliseconds(budget));
        server.start();
        io.run(); // exactly one execution thread for all state, timers and signals
        server.report();
    } catch (const std::exception& error) {
        // Initiation/allocation failures are fatal in this small exercise.
        std::cerr << "fatal: " << error.what() << '\n';
        return 1;
    }
}
