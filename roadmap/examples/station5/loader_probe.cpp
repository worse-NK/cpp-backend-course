#include <iostream>

extern "C" int course_value();

int main() {
    std::cout << "main: " << course_value() << '\n';
}
