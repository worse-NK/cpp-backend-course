// Optional SDK example: rabbitmq-c >= 0.18.1. C API used from C++20.
#include <rabbitmq-c/amqp.h>
#include <rabbitmq-c/tcp_socket.h>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void ok(amqp_rpc_reply_t result, const char* operation) {
    if (result.reply_type != AMQP_RESPONSE_NORMAL)
        throw std::runtime_error(std::string(operation) + " failed; inspect broker and client diagnostics");
}
void sent(int status, const char* operation) {
    if (status != AMQP_STATUS_OK)
        throw std::runtime_error(std::string(operation) + ": " + amqp_error_string2(status));
}
struct Connection {
    amqp_connection_state_t state = amqp_new_connection();
    Connection() { if (!state) throw std::bad_alloc(); }
    ~Connection() { amqp_destroy_connection(state); }
    Connection(const Connection&) = delete;
    Connection& operator=(const Connection&) = delete;
};
struct Envelope {
    amqp_envelope_t value{};
    bool valid = false;
    ~Envelope() { if (valid) amqp_destroy_envelope(&value); }
};
}

int main(int argc, char** argv) {
    try {
        if (argc != 2 || (std::string(argv[1]) != "send" && std::string(argv[1]) != "read"
                          && std::string(argv[1]) != "read-no-ack")) {
            std::cerr << "usage: rabbit_roundtrip send|read|read-no-ack\n";
            return 2;
        }
        const char* password = std::getenv("COURSE11_RABBIT_PASSWORD");
        if (!password || !*password) throw std::invalid_argument("Set COURSE11_RABBIT_PASSWORD");
        Connection connection;
        auto* socket = amqp_tcp_socket_new(connection.state);
        if (!socket) throw std::bad_alloc();
        timeval timeout{5, 0};
        sent(amqp_set_handshake_timeout(connection.state, &timeout), "handshake timeout");
        sent(amqp_set_rpc_timeout(connection.state, &timeout), "RPC timeout");
        sent(amqp_socket_open_noblock(socket, "127.0.0.1", 25672, &timeout), "connect");
        ok(amqp_login(connection.state, "course11", 0, 131072, 30,
                      AMQP_SASL_METHOD_PLAIN, "course11", password), "login");
        constexpr amqp_channel_t channel = 1;
        amqp_channel_open(connection.state, channel);
        ok(amqp_get_rpc_reply(connection.state), "channel.open");
        const auto exchange = amqp_cstring_bytes("course11.events");
        const auto queue = amqp_cstring_bytes("course11.audit");
        const auto routing = amqp_cstring_bytes("orders.created");
        amqp_exchange_declare(connection.state, channel, exchange, amqp_cstring_bytes("direct"),
                              0, 1, 0, 0, amqp_empty_table);
        ok(amqp_get_rpc_reply(connection.state), "exchange.declare");
        amqp_table_entry_t entry{};
        entry.key = amqp_cstring_bytes("x-queue-type");
        entry.value.kind = AMQP_FIELD_KIND_UTF8;
        entry.value.value.bytes = amqp_cstring_bytes("quorum");
        amqp_table_t arguments{1, &entry};
        amqp_queue_declare(connection.state, channel, queue, 0, 1, 0, 0, arguments);
        ok(amqp_get_rpc_reply(connection.state), "queue.declare");
        amqp_queue_bind(connection.state, channel, queue, exchange, routing, amqp_empty_table);
        ok(amqp_get_rpc_reply(connection.state), "queue.bind");
        if (std::string(argv[1]) == "send") {
            amqp_confirm_select(connection.state, channel);
            ok(amqp_get_rpc_reply(connection.state), "confirm.select");
            amqp_basic_properties_t properties{};
            properties._flags = AMQP_BASIC_DELIVERY_MODE_FLAG | AMQP_BASIC_MESSAGE_ID_FLAG;
            properties.delivery_mode = 2;
            properties.message_id = amqp_cstring_bytes("evt-101");
            sent(amqp_basic_publish(connection.state, channel, exchange, routing, 1, 0,
                                    &properties, amqp_cstring_bytes("evt-101|order=101")), "basic.publish");
            amqp_publisher_confirm_t confirmation{};
            ok(amqp_publisher_confirm_wait(connection.state, &timeout, &confirmation), "publisher confirm");
            if (confirmation.channel != channel || confirmation.method != AMQP_BASIC_ACK_METHOD ||
                confirmation.payload.ack.delivery_tag != 1)
                throw std::runtime_error("Expected acknowledgement of the only published message");
            std::cout << "broker_confirmed; consumer effect is not confirmed\n";
        } else {
            amqp_basic_qos(connection.state, channel, 0, 1, 0);
            ok(amqp_get_rpc_reply(connection.state), "basic.qos");
            amqp_basic_consume(connection.state, channel, queue, amqp_empty_bytes, 0, 0, 0, amqp_empty_table);
            ok(amqp_get_rpc_reply(connection.state), "basic.consume");
            Envelope envelope;
            ok(amqp_consume_message(connection.state, &envelope.value, &timeout, 0), "consume");
            envelope.valid = true;
            std::cout << "redelivered=" << envelope.value.redelivered << " body=";
            std::cout.write(static_cast<const char*>(envelope.value.message.body.bytes),
                            static_cast<std::streamsize>(envelope.value.message.body.len));
            std::cout << '\n';
            if (std::string(argv[1]) == "read") {
                sent(amqp_basic_ack(connection.state, channel, envelope.value.delivery_tag, 0), "basic.ack");
                std::cout << "consumer_ack_sent; local print is not a durable business effect\n";
            } else std::cout << "no_ack; closing connection allows redelivery\n";
        }
        ok(amqp_channel_close(connection.state, channel, AMQP_REPLY_SUCCESS), "channel.close");
        ok(amqp_connection_close(connection.state, AMQP_REPLY_SUCCESS), "connection.close");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
