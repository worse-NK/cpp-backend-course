#include "client.hpp"
#include <iostream>
#include <utility>
int main() {
    Client first;
    Client second(std::move(first));
    std::cout << first.value() << ' ' << second.value();
}
