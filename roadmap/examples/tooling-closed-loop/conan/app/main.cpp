#include <iostream>
#include "task_label.hpp"
int main() {
    const auto label = course::task_label(41);
    std::cout << label << '\n';
    return label == "task:41" ? 0 : 1;
}
