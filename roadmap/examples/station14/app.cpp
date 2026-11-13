#include "httplib.h"
#include "metrics.hpp"
#include <atomic>
#include <algorithm>
#include <chrono>
#include <charconv>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <optional>
#include <pthread.h>
#include <string>
#include <string_view>
#include <syncstream>
#include <thread>

#ifdef COURSE_WITH_OTEL
#include "opentelemetry/context/runtime_context.h"
#include "opentelemetry/trace/propagation/http_trace_context.h"
#include "opentelemetry/trace/provider.h"
#include "opentelemetry/exporters/otlp/otlp_http_exporter_factory.h"
#include "opentelemetry/exporters/otlp/otlp_http_exporter_options.h"
#include "opentelemetry/sdk/resource/resource.h"
#include "opentelemetry/sdk/trace/batch_span_processor_factory.h"
#include "opentelemetry/sdk/trace/batch_span_processor_options.h"
#include "opentelemetry/sdk/trace/tracer_provider_factory.h"
namespace ot = opentelemetry;
namespace trace = ot::trace;
namespace sdk = ot::sdk::trace;
namespace otlp = ot::exporter::otlp;

struct Carrier : ot::context::propagation::TextMapCarrier {
    httplib::Headers headers;
    ot::nostd::string_view Get(ot::nostd::string_view key) const noexcept override {
        auto it = headers.find(std::string(key.data(), key.size()));
        if (it == headers.end()) return {};
        return {it->second.data(), it->second.size()};
    }
    void Set(ot::nostd::string_view key, ot::nostd::string_view value) noexcept override {
        headers.emplace(std::string(key.data(), key.size()),
                        std::string(value.data(), value.size()));
    }
};
std::shared_ptr<sdk::TracerProvider> init_tracing(const std::string& role) {
    otlp::OtlpHttpExporterOptions options;
    const char* endpoint = std::getenv("COURSE_OTLP_URL");
    options.url = endpoint ? endpoint : "http://127.0.0.1:4318/v1/traces";
    options.timeout = std::chrono::milliseconds(700);
    options.retry_policy_max_attempts = 1; // Bounded diagnostic demo, not a durable queue.
    sdk::BatchSpanProcessorOptions batch;
    batch.max_queue_size = 256;
    batch.max_export_batch_size = 64;
    batch.schedule_delay_millis = std::chrono::milliseconds(200);
    auto exporter = otlp::OtlpHttpExporterFactory::Create(options);
    auto processor = sdk::BatchSpanProcessorFactory::Create(std::move(exporter), batch);
    auto resource = ot::sdk::resource::Resource::Create({{"service.name", role}});
    std::shared_ptr<sdk::TracerProvider> provider =
        sdk::TracerProviderFactory::Create(std::move(processor), resource);
    std::shared_ptr<trace::TracerProvider> api_provider = provider;
    trace::Provider::SetTracerProvider(api_provider);
    return provider;
}
class Trace {
    ot::nostd::shared_ptr<trace::Span> span_;
    std::unique_ptr<trace::Scope> active_;
public:
    Trace(const std::string& name, bool client, const httplib::Headers& headers = {}) {
        auto current = ot::context::RuntimeContext::GetCurrent();
        Carrier carrier; carrier.headers = headers;
        auto parent = client ? current : trace::propagation::HttpTraceContext{}.Extract(carrier, current);
        trace::StartSpanOptions options;
        options.kind = client ? trace::SpanKind::kClient : trace::SpanKind::kServer;
        options.parent = parent;
        auto tracer = trace::Provider::GetTracerProvider()->GetTracer("course-station14", "1.0");
        span_ = tracer->StartSpan(name, options);
        active_ = std::make_unique<trace::Scope>(span_);
    }
    ~Trace() { span_->End(); }
    void result(int status) {
        span_->SetAttribute("http.response.status_code", status);
        if (status != 200) span_->SetStatus(trace::StatusCode::kError);
    }
    std::string id() const {
        std::array<char, 32> value{};
        span_->GetContext().trace_id().ToLowerBase16(value);
        return {value.data(), value.size()};
    }
    httplib::Headers inject() const {
        Carrier carrier;
        auto current = ot::context::RuntimeContext::GetCurrent();
        trace::propagation::HttpTraceContext{}.Inject(carrier, current);
        return carrier.headers;
    }
};
#else
class Trace {
public:
    Trace(const std::string&, bool, const httplib::Headers& = {}) {}
    void result(int) {}
    std::string id() const { return "disabled"; }
    httplib::Headers inject() const { return {}; }
};
#endif

int main() {
    sigset_t signals;
    sigemptyset(&signals); sigaddset(&signals, SIGTERM); sigaddset(&signals, SIGINT);
    if (pthread_sigmask(SIG_BLOCK, &signals, nullptr) != 0) return 2;
    const char* raw = std::getenv("COURSE_ROLE");
    const std::string role = raw ? raw : "api";
    if (role != "api" && role != "worker") { std::cerr << "role must be api or worker\n"; return 2; }
    int port = role == "api" ? 8080 : 8081;
    if (const char* text = std::getenv("COURSE_PORT")) {
        const std::string_view value(text);
        const auto parsed = std::from_chars(value.data(), value.data() + value.size(), port);
        if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size()) return 2;
    }
    if (port < 1024 || port > 65535) return 2;
    const char* raw_run = std::getenv("COURSE_LAB_ID");
    const std::string run = raw_run ? raw_run : "standalone";
    if (raw_run && (run.size() != 12 || !std::all_of(run.begin(), run.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    }))) return 2;
#ifdef COURSE_WITH_OTEL
    auto provider = init_tracing(role);
#endif
    Metrics metrics;
    std::atomic<std::uint64_t> sequence{0};
    httplib::Server server;
    server.new_task_queue = [] { return new httplib::ThreadPool(4, 4, 16); };
    server.set_payload_max_length(1024);
    server.set_read_timeout(2, 0); server.set_write_timeout(2, 0);
    server.set_keep_alive_max_count(1);
    server.Get("/healthz", [&](const auto&, auto& res) {
        res.set_header("X-Course-Lab", "station14");
        res.set_header("X-Course-Lab-Run", run);
        res.set_content("ready\n", "text/plain");
    });
    server.Get("/metrics", [&](const auto&, auto& res) {
        res.set_content(metrics.exposition(), "text/plain; version=0.0.4; charset=utf-8");
    });
    const std::string route = role == "api" ? "/work" : "/step";
    server.Get(route, [&](const httplib::Request& req, httplib::Response& res) {
        const auto start = std::chrono::steady_clock::now();
        const auto request = ++sequence;
        metrics.enter();
        std::optional<Trace> incoming;
        int status = 503;
        try {
            incoming.emplace("GET " + route, false, req.headers);
            std::string mode = req.get_param_value("mode");
            if (mode.empty()) mode = "normal";
            if (mode != "normal" && mode != "slow" && mode != "error") status = 400;
            else if (role == "worker") {
                if (mode == "slow") std::this_thread::sleep_for(std::chrono::milliseconds(200));
                status = mode == "error" ? 503 : 200;
            } else {
                Trace outgoing("GET /step", true);
                const char* peer = std::getenv("COURSE_WORKER_URL");
                httplib::Client worker(peer ? peer : "http://127.0.0.1:8081");
                worker.set_connection_timeout(1, 0);
                worker.set_read_timeout(1, 0); worker.set_write_timeout(1, 0);
                auto reply = worker.Get("/step?mode=" + mode, outgoing.inject());
                status = reply ? reply->status : 503;
                outgoing.result(status);
            }
        } catch (...) { status = 503; }
        res.status = status;
        res.set_header("X-Course-Lab", "station14");
        res.set_header("X-Course-Lab-Run", run);
        res.set_content(status == 200 ? "done\n" : "request failed\n", "text/plain");
        if (incoming) incoming->result(status);
        res.set_header("X-Course-Trace-Id", incoming ? incoming->id() : "unavailable");
        const double seconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();
        metrics.complete(seconds, status == 200);
        // All string fields below are fixed route/role/hex values, not user payloads.
        std::osyncstream(std::cout) << "{\"service\":\"" << role
            << "\",\"route\":\"" << route << "\",\"request_seq\":" << request
            << ",\"status\":" << status << ",\"duration_seconds\":" << seconds
            << ",\"trace_id\":\"" << (incoming ? incoming->id() : "unavailable") << "\"}\n";
    });
    // Loopback by default. Compose must explicitly opt into container networking.
    const char* bind = std::getenv("COURSE_BIND");
    if (!server.bind_to_port(bind ? bind : "127.0.0.1", port)) return 1;
    std::atomic<bool> stopped{false}; bool ok = false;
    std::thread listener([&] { ok = server.listen_after_bind(); stopped.store(true); });
    while (!stopped.load()) {
        timespec timeout{0, 200000000};
        if (sigtimedwait(&signals, nullptr, &timeout) >= 0) break;
    }
    server.stop(); listener.join();
#ifdef COURSE_WITH_OTEL
    provider->ForceFlush(std::chrono::seconds(2));
    provider->Shutdown(std::chrono::seconds(2));
#endif
    return ok ? 0 : 1;
}
