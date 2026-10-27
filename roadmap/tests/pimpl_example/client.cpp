#include "client.hpp"
class Client::Impl {
public:
    int value = 7;
};
Client::Client() : impl_(std::make_unique<Impl>()) {}
Client::~Client() = default;
Client::Client(Client&&) noexcept = default;
int Client::value() const { return impl_ ? impl_->value : 0; }
