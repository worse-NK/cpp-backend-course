#include <cstddef>
#include <iostream>
#include <string_view>
#include <vector>

int first_task(const std::vector<int>& tasks) {
    const std::size_t count = tasks.size();
    std::cerr << "tasks=" << count << '\n';
    return tasks.at(0); // A checked access throws for an empty list: no UB.
}

int main(int argc, char** argv) {
    if (argc != 2 || (std::string_view{argv[1]} != "empty"
                      && std::string_view{argv[1]} != "ready")) {
        std::cerr << "usage: report_before empty|ready\n";
        return 2;
    }
    std::vector<int> tasks;
    if (std::string_view{argv[1]} == "ready") tasks = {41, 73};
    const int first = first_task(tasks);
    std::cout << "first task: " << first << '\n';
}
