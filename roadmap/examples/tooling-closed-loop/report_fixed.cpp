#include <iostream>
#include <optional>
#include <string_view>
#include <vector>

std::optional<int> first_task(const std::vector<int>& tasks) {
    if (tasks.empty()) return std::nullopt;
    return tasks.front();
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view{argv[1]} == "--self-test") {
        const bool ok = !first_task({}).has_value()
            && first_task({41, 73}) == std::optional<int>{41}
            && first_task({0}) == std::optional<int>{0}
            && first_task({-7}) == std::optional<int>{-7};
        std::cout << (ok ? "regression: OK\n" : "regression: FAIL\n");
        return ok ? 0 : 1;
    }
    if (argc != 2 || (std::string_view{argv[1]} != "empty"
                      && std::string_view{argv[1]} != "ready")) {
        std::cerr << "usage: report_fixed empty|ready|--self-test\n";
        return 2;
    }
    std::vector<int> tasks;
    if (std::string_view{argv[1]} == "ready") tasks = {41, 73};
    const auto first = first_task(tasks);
    if (!first) std::cout << "no tasks\n";
    else std::cout << "first task: " << *first << '\n';
}
