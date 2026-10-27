#pragma once
#include <memory>
class Client {
    class Impl;
    std::unique_ptr<Impl> impl_;
public:
    Client();
    ~Client();
    Client(Client&&) noexcept;
    int value() const;
};
