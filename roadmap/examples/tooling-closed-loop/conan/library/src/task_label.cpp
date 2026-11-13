#include "task_label.hpp"
namespace course {
std::string task_label(unsigned id) {
    return "task:" + std::to_string(id);
}
}
