#include "storage.hpp"

#include <atomic>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <pthread.h>
#include <string>
#include <syncstream>
#include <thread>
#include <httplib.h>
#include <nlohmann/json.hpp>

namespace {
using Json = nlohmann::json;
std::string env_or(const char* name, const char* fallback) {
  const char* value = std::getenv(name);
  return value ? value : fallback;
}
Json as_json(const course::Task& task) {
  return {{"id",task.id},{"title",task.title},{"done",task.done},{"version",task.version}};
}
void json_response(httplib::Response& response, int status, const Json& body) {
  response.status = status;
  response.set_content(body.dump(), "application/json");
}
void error_response(httplib::Response& response, int status, const char* code) {
  json_response(response, status, {{"error",code}});
}
std::string etag(course::Number version) { return "\"v" + std::to_string(version) + "\""; }

enum class Route { live, ready, collection, task, unknown };
Route route(std::string_view path) {
  if (path == "/health/live") return Route::live;
  if (path == "/health/ready") return Route::ready;
  if (path == "/tasks") return Route::collection;
  if (path.starts_with("/tasks/") && path.size() <= 128 &&
      path.substr(7).find('/') == std::string_view::npos) return Route::task;
  return Route::unknown;
}
const char* log_path(std::string_view path) {
  switch (route(path)) {
    case Route::live: return "/health/live";
    case Route::ready: return "/health/ready";
    case Route::collection: return "/tasks";
    case Route::task: return "/tasks/:id";
    default: return "<other>";
  }
}
const char* log_method(std::string_view method) {
  for (auto known : {"GET","HEAD","POST","PUT","DELETE","OPTIONS","PATCH"})
    if (method == known) return known;
  return "OTHER";
}
bool method_allowed(Route selected, std::string_view method) {
  if (selected == Route::live || selected == Route::ready) return method == "GET";
  if (selected == Route::collection) return method == "GET" || method == "POST";
  if (selected == Route::task) return method == "GET" || method == "PUT" || method == "DELETE";
  return false;
}
const char* allowed_methods(Route selected) {
  if (selected == Route::collection) return "GET, POST";
  if (selected == Route::task) return "GET, PUT, DELETE";
  return "GET";
}
bool json_content_type(const httplib::Request& request) {
  // Deliberately accepts only application/json, optionally charset=utf-8.
  if (request.get_header_value_count("Content-Type") != 1) return false;
  auto value = request.get_header_value("Content-Type");
  for (char& c : value) if (c >= 'A' && c <= 'Z') c = static_cast<char>(c + ('a' - 'A'));
  auto trim = [](std::string_view text) {
    while (!text.empty() && (text.front() == ' ' || text.front() == '\t')) text.remove_prefix(1);
    while (!text.empty() && (text.back() == ' ' || text.back() == '\t')) text.remove_suffix(1);
    return text;
  };
  std::string_view view = trim(value);
  auto semicolon = view.find(';');
  if (trim(view.substr(0, semicolon)) != "application/json") return false;
  if (semicolon == std::string_view::npos) return true;
  auto parameter = trim(view.substr(semicolon + 1));
  return parameter == "charset=utf-8" || parameter == "charset=\"utf-8\"";
}
course::Number precondition(const httplib::Request& request) {
  auto count = request.get_header_value_count("If-Match");
  if (count == 0) throw course::InputError(428, "if_match_required");
  if (count != 1) throw course::InputError(400, "invalid_if_match");
  return course::parse_etag(request.get_header_value("If-Match"));
}
} // namespace

int main() {
  try {
    // Block before creating ANY worker thread. sigtimedwait runs on an ordinary
    // thread, where server.stop() is safe; there is no async signal handler.
    sigset_t signals;
    sigemptyset(&signals);
    sigaddset(&signals, SIGINT);
    sigaddset(&signals, SIGTERM);
    if (pthread_sigmask(SIG_BLOCK, &signals, nullptr) != 0) {
      std::cerr << "startup_failed: signal_mask\n";
      return 1;
    }
    const auto token = env_or("APP_TOKEN", "");
    if (!course::valid_token(token)) {
      std::cerr << "startup_failed: APP_TOKEN must contain exactly 64 hexadecimal characters\n";
      return 1;
    }
    const auto bind = env_or("APP_BIND", "127.0.0.1");
    if (bind != "127.0.0.1" && bind != "0.0.0.0") {
      std::cerr << "startup_failed: APP_BIND must be 127.0.0.1 or 0.0.0.0\n";
      return 1;
    }
    const int port = course::parse_port(env_or("APP_PORT", "8080"));
    auto storage = course::make_storage(env_or("APP_STORAGE", "memory"));

    httplib::Server server;
    // Version 0.59: (base threads, maximum threads, maximum queued connections).
    // Saturation closes a connection; it is NOT a reliable HTTP 503 mechanism.
    server.new_task_queue = [] { return new httplib::ThreadPool(4, 4, 32); };
    server.set_read_timeout(3, 0);
    server.set_write_timeout(3, 0);
    server.set_keep_alive_timeout(2);
    server.set_keep_alive_max_count(10);
    server.set_payload_max_length(course::max_body_bytes);
    server.set_logger([](const httplib::Request& request, const httplib::Response& response) {
      // Never print raw paths, query strings, tokens, bodies or DB exceptions.
      std::osyncstream(std::cout) << "request method=" << log_method(request.method)
        << " path=" << log_path(request.path) << " status=" << response.status << '\n' << std::flush;
    });
    server.set_exception_handler([](const auto&, auto& response, std::exception_ptr) {
      error_response(response, 503, "service_unavailable");
    });
    server.set_error_handler([](const auto&, auto& response) {
      if (response.body.empty()) error_response(response, response.status, "request_failed");
    });
    server.set_pre_routing_handler([&](const auto& request, auto& response) {
      response.set_header("Cache-Control", "no-store");
      response.set_header("X-Content-Type-Options", "nosniff");
      const Route selected = route(request.path);
      const bool health = selected == Route::live || selected == Route::ready;
      if (!health) {
        const auto auth = request.get_header_value("Authorization");
        if (request.get_header_value_count("Authorization") != 1 ||
            !auth.starts_with("Bearer ") || !course::token_matches(std::string_view(auth).substr(7), token)) {
          response.set_header("WWW-Authenticate", "Bearer");
          error_response(response, 401, "unauthorized");
          return httplib::Server::HandlerResponse::Handled;
        }
      }
      if (selected == Route::unknown) {
        error_response(response, 404, "not_found");
        return httplib::Server::HandlerResponse::Handled;
      }
      if (!method_allowed(selected, request.method)) {
        response.set_header("Allow", allowed_methods(selected));
        error_response(response, 405, "method_not_allowed");
        return httplib::Server::HandlerResponse::Handled;
      }
      return httplib::Server::HandlerResponse::Unhandled;
    });

    auto handler = [&](const httplib::Request& request, httplib::Response& response) {
      try {
        const auto selected = route(request.path);
        if (selected == Route::live || selected == Route::ready) {
          bool ready = selected == Route::live || storage->ready();
          json_response(response, ready ? 200 : 503, {{"status",ready ? "ok" : "unavailable"}});
          return;
        }
        if (selected == Route::collection && request.method == "GET") {
          Json result = Json::array();
          for (const auto& task : storage->list()) result.push_back(as_json(task));
          json_response(response, 200, result);
          return;
        }
        const auto id = selected == Route::task ? course::parse_positive(std::string_view(request.path).substr(7)) : 0;
        if (request.method == "GET") {
          auto task = storage->get(id);
          if (!task) { error_response(response, 404, "not_found"); return; }
          response.set_header("ETag", etag(task->version));
          json_response(response, 200, as_json(*task));
          return;
        }
        if (request.method == "DELETE") {
          if (!storage->erase(id, precondition(request))) error_response(response, 412, "precondition_failed");
          else response.status = 204;
          return;
        }
        const auto expected = request.method == "PUT" ? precondition(request) : 0;
        if (!json_content_type(request)) { error_response(response, 415, "application_json_required"); return; }
        const auto input = course::parse_input(request.body);
        if (request.method == "POST") {
          auto task = storage->create(input);
          response.set_header("Location", "/tasks/" + std::to_string(task.id));
          response.set_header("ETag", etag(task.version));
          json_response(response, 201, as_json(task));
        } else {
          auto task = storage->update(id, expected, input);
          if (!task) { error_response(response, 412, "precondition_failed"); return; }
          response.set_header("ETag", etag(task->version));
          json_response(response, 200, as_json(*task));
        }
      } catch (const course::InputError& error) {
        error_response(response, error.status, error.what());
      } catch (...) {
        // This includes DB/network errors, capacity and version exhaustion.
        error_response(response, 503, "service_unavailable");
      }
    };
    // Library bounds regex evaluation to 128-byte paths. No raw path is logged.
    server.Get(R"(/.*)", handler);
    server.Post(R"(/.*)", handler);
    server.Put(R"(/.*)", handler);
    server.Delete(R"(/.*)", handler);

    if (!server.bind_to_port(bind, port)) {
      std::cerr << "startup_failed: bind\n";
      return 1;
    }
    std::atomic_bool interrupted{false};
    std::jthread signal_thread([&](std::stop_token stop) {
      const timespec interval{0, 100'000'000};
      while (!stop.stop_requested()) {
        const int received = sigtimedwait(&signals, nullptr, &interval);
        if (received == SIGINT || received == SIGTERM) {
          interrupted = true;
          server.stop();
          return;
        }
        if (received < 0 && errno != EAGAIN && errno != EINTR) {
          server.stop();
          return;
        }
      }
    });
    std::cout << "server_started\n" << std::flush;
    const bool listened = server.listen_after_bind();
    signal_thread.request_stop();
    signal_thread.join();
    std::cout << "server_stopped\n";
    return listened || interrupted.load() ? 0 : 1;
  } catch (...) {
    // Do not log exception.what(): it can contain SQL, input or credentials.
    std::cerr << "startup_failed: invalid_configuration_or_unavailable_resource\n";
    return 1;
  }
}
