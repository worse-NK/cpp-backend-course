#include <hiredis.h>
#include <charconv>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

struct ContextDeleter { void operator()(redisContext* p) const { redisFree(p); } };
struct ReplyDeleter { void operator()(redisReply* p) const { freeReplyObject(p); } };
using Context = std::unique_ptr<redisContext, ContextDeleter>;
using Reply = std::unique_ptr<redisReply, ReplyDeleter>;

std::string env(const char* key) {
    const char* value = std::getenv(key);
    if (!value || !*value) throw std::runtime_error(std::string("missing ") + key);
    return value;
}

class Redis {
    Context context_;
public:
    Redis(const std::string& host, int port, const std::string& password) {
        const timeval timeout{1, 0};
        context_.reset(redisConnectWithTimeout(host.c_str(), port, timeout));
        if (!context_ || context_->err) throw std::runtime_error("connect failed");
        if (redisSetTimeout(context_.get(), timeout) != REDIS_OK)
            throw std::runtime_error("command timeout setup failed");
        auto reply = command({"AUTH", password});
        if (reply->type != REDIS_REPLY_STATUS || std::string_view(reply->str, reply->len) != "OK")
            throw std::runtime_error("authentication failed");
    }
    Reply command(const std::vector<std::string>& args) {
        if (args.empty() || args.size() > 32) throw std::invalid_argument("argument count");
        std::vector<const char*> argv;
        std::vector<std::size_t> sizes;
        for (const auto& arg : args) { argv.push_back(arg.data()); sizes.push_back(arg.size()); }
        Reply reply(static_cast<redisReply*>(redisCommandArgv(
            context_.get(), static_cast<int>(args.size()), argv.data(), sizes.data())));
        if (!reply) throw std::runtime_error("Redis I/O failed; outcome may be unknown");
        if (reply->type == REDIS_REPLY_ERROR)
            throw std::runtime_error("Redis rejected the command");
        return reply;
    }
    std::optional<std::string> get(const std::string& key) {
        auto reply = command({"GET", key});
        if (reply->type == REDIS_REPLY_NIL) return std::nullopt;
        if (reply->type != REDIS_REPLY_STRING) throw std::runtime_error("GET reply type");
        return std::string(reply->str, reply->len);
    }
    void put(const std::string& key, const std::string& value) {
        auto reply = command({"SET", key, value, "PX", "5000"});
        if (reply->type != REDIS_REPLY_STATUS || std::string_view(reply->str, reply->len) != "OK")
            throw std::runtime_error("SET reply type");
    }
};

int main() {
    try {
        const auto host = env("COURSE12_HOST");
        if (host != "127.0.0.1" && host != "redis") throw std::runtime_error("lab host only");
        const auto port_text = env("COURSE12_PORT");
        int port = 0;
        const auto parsed = std::from_chars(port_text.data(), port_text.data()+port_text.size(), port);
        if (parsed.ec != std::errc{} || parsed.ptr != port_text.data()+port_text.size() || port < 1024 || port > 65535)
            throw std::runtime_error("invalid lab port");
        const auto run_id = env("COURSE12_RUN_ID");
        if (run_id.size() != 16 || run_id.find_first_not_of("0123456789abcdef") != std::string::npos)
            throw std::runtime_error("invalid run id");
        const auto key = "course12:" + run_id + ":cpp:card";
        Redis redis(host, port, env("COURSE12_PASSWORD"));
        redis.command({"DEL", key}); // One exact, run-owned key; no database flush.
        const auto first = redis.get(key);
        const std::string source_value("A\0B", 3); // Embedded NUL must survive RESP.
        if (first) throw std::runtime_error("expected initial miss");
        redis.put(key, source_value);
        const auto second = redis.get(key);
        if (!second || *second != source_value) throw std::runtime_error("binary round trip failed");
        std::cout << "first: miss\nsecond: hit, bytes=" << second->size() << '\n';
        redis.command({"DEL", key});
        std::cout << "after invalidation: " << (redis.get(key) ? "hit" : "miss") << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1; // Never print the password or the complete environment.
    }
}
