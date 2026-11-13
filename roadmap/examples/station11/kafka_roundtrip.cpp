// Optional SDK example: librdkafka >= 2.12.1. Only the local course broker.
#include <librdkafka/rdkafka.h>
#include <chrono>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
struct KafkaDelete { void operator()(rd_kafka_t* p) const { if (p) rd_kafka_destroy(p); } };
struct ConfigDelete { void operator()(rd_kafka_conf_t* p) const { if (p) rd_kafka_conf_destroy(p); } };
struct MessageDelete { void operator()(rd_kafka_message_t* p) const { if (p) rd_kafka_message_destroy(p); } };
using Kafka = std::unique_ptr<rd_kafka_t, KafkaDelete>;
using Config = std::unique_ptr<rd_kafka_conf_t, ConfigDelete>;
void set(rd_kafka_conf_t* conf, const char* key, const char* value) {
    char error[512];
    if (rd_kafka_conf_set(conf, key, value, error, sizeof error) != RD_KAFKA_CONF_OK)
        throw std::runtime_error(std::string(key) + ": " + error);
}
struct Delivery { bool seen = false; bool failed = false; };
void delivered(rd_kafka_t*, const rd_kafka_message_t* message, void* opaque) {
    auto& result = *static_cast<Delivery*>(opaque);
    result.seen = true;
    result.failed = message->err != RD_KAFKA_RESP_ERR_NO_ERROR;
    std::cout << "delivery_report=" << rd_kafka_err2str(message->err)
              << " partition=" << message->partition << " offset=" << message->offset << '\n';
}
Kafka create(rd_kafka_type_t kind, Config& conf) {
    char error[512];
    auto* raw = rd_kafka_new(kind, conf.get(), error, sizeof error);
    if (!raw) throw std::runtime_error(error);
    conf.release(); // rd_kafka_new owns the configuration on success only.
    return Kafka(raw);
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 3 || (std::string(argv[1]) != "send" && std::string(argv[1]) != "read"
                          && std::string(argv[1]) != "read-no-commit")) {
            std::cerr << "usage: kafka_roundtrip send|read|read-no-commit course11-GROUP\n";
            return 2;
        }
        const std::string group = argv[2];
        if (group.size() < 10 || group.size() > 80 || group.rfind("course11-", 0) != 0 ||
            group.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") != std::string::npos)
            throw std::invalid_argument("Choose a course11-... group name");
        Config conf(rd_kafka_conf_new());
        if (!conf) throw std::bad_alloc();
        set(conf.get(), "bootstrap.servers", "127.0.0.1:29092");
        set(conf.get(), "client.id", "course11-local-example");
        if (std::string(argv[1]) == "send") {
            set(conf.get(), "enable.idempotence", "true");
            set(conf.get(), "acks", "all");
            set(conf.get(), "message.timeout.ms", "8000");
            set(conf.get(), "queue.buffering.max.messages", "16");
            Delivery result;
            rd_kafka_conf_set_opaque(conf.get(), &result);
            rd_kafka_conf_set_dr_msg_cb(conf.get(), delivered);
            auto producer = create(RD_KAFKA_PRODUCER, conf);
            std::string value = "evt-101|order=101";
            std::string key = "order-101";
            const auto error = rd_kafka_producev(producer.get(),
                RD_KAFKA_V_TOPIC("course11-orders"), RD_KAFKA_V_MSGFLAGS(RD_KAFKA_MSG_F_COPY),
                RD_KAFKA_V_KEY(key.data(), key.size()),
                RD_KAFKA_V_VALUE(value.data(), value.size()), RD_KAFKA_V_END);
            if (error) throw std::runtime_error(rd_kafka_err2str(error));
            std::cout << "accepted_into_local_queue\n";
            const auto flushed = rd_kafka_flush(producer.get(), 10000);
            if (flushed || !result.seen || result.failed)
                throw std::runtime_error("Delivery not confirmed; do not infer absence of a stored record");
            return 0;
        }
        set(conf.get(), "group.id", group.c_str());
        set(conf.get(), "group.protocol", "classic");
        set(conf.get(), "enable.auto.commit", "false");
        set(conf.get(), "enable.auto.offset.store", "false");
        set(conf.get(), "auto.offset.reset", "earliest");
        auto consumer = create(RD_KAFKA_CONSUMER, conf);
        if (rd_kafka_poll_set_consumer(consumer.get())) throw std::runtime_error("poll setup failed");
        auto* topics = rd_kafka_topic_partition_list_new(1);
        if (!topics) throw std::bad_alloc();
        rd_kafka_topic_partition_list_add(topics, "course11-orders", RD_KAFKA_PARTITION_UA);
        const auto subscribed = rd_kafka_subscribe(consumer.get(), topics);
        rd_kafka_topic_partition_list_destroy(topics);
        if (subscribed) throw std::runtime_error(rd_kafka_err2str(subscribed));
        const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(15);
        bool processed = false;
        while (std::chrono::steady_clock::now() < until) {
            std::unique_ptr<rd_kafka_message_t, MessageDelete> message(
                rd_kafka_consumer_poll(consumer.get(), 250));
            if (!message) continue;
            if (message->err) throw std::runtime_error(rd_kafka_err2str(message->err));
            std::cout << "read partition=" << message->partition << " offset=" << message->offset << " body=";
            if (message->payload) std::cout.write(static_cast<const char*>(message->payload),
                                                static_cast<std::streamsize>(message->len));
            std::cout << '\n'; // Observation only: not a durable business transaction.
            if (std::string(argv[1]) == "read") {
                const auto committed = rd_kafka_commit_message(consumer.get(), message.get(), 0);
                if (committed) throw std::runtime_error(rd_kafka_err2str(committed));
                std::cout << "next_offset_committed=" << message->offset + 1 << '\n';
            } else std::cout << "offset_intentionally_not_committed\n";
            processed = true;
            break;
        }
        const auto closed = rd_kafka_consumer_close(consumer.get());
        if (closed) throw std::runtime_error(rd_kafka_err2str(closed));
        if (!processed) throw std::runtime_error("No record before the teaching wait limit");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
