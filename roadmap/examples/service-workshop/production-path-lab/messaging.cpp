#include "common.hpp"
#include <rabbitmq-c/amqp.h>
#include <rabbitmq-c/tcp_socket.h>
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>
#include <vector>

namespace course_path {
namespace {
void rpc(amqp_rpc_reply_t reply) {
    if(reply.reply_type!=AMQP_RESPONSE_NORMAL) throw std::runtime_error("AMQP operation failed");
}
void sent(int status) { if(status!=AMQP_STATUS_OK) throw std::runtime_error("AMQP I/O failed"); }
class Broker {
public:
    amqp_connection_state_t state=amqp_new_connection();
    static constexpr amqp_channel_t channel=1;
    Broker() {
        if(!state) throw std::bad_alloc();
        try {
            auto* socket=amqp_tcp_socket_new(state);
            if(!socket) throw std::bad_alloc();
            timeval timeout{3,0};
            sent(amqp_set_handshake_timeout(state,&timeout));
            sent(amqp_set_rpc_timeout(state,&timeout));
            const auto password=secret_file("/run/secrets/broker_password");
            sent(amqp_socket_open_noblock(socket,"broker",5672,&timeout));
            rpc(amqp_login(state,"course_path",0,65536,30,AMQP_SASL_METHOD_PLAIN,"course_path",password.c_str()));
            amqp_channel_open(state,channel); rpc(amqp_get_rpc_reply(state));
            setup();
        } catch(...) { amqp_destroy_connection(state); state=nullptr; throw; }
    }
    ~Broker() { if(state) amqp_destroy_connection(state); }
    Broker(const Broker&)=delete;
    Broker& operator=(const Broker&)=delete;
private:
    void setup() {
        for(const auto* exchange:{"path.events","path.dead"}) {
            amqp_exchange_declare(state,channel,amqp_cstring_bytes(exchange),amqp_cstring_bytes("direct"),0,1,0,0,amqp_empty_table);
            rpc(amqp_get_rpc_reply(state));
        }
        amqp_queue_declare(state,channel,amqp_cstring_bytes("path.invalid"),0,1,0,0,amqp_empty_table);
        rpc(amqp_get_rpc_reply(state));
        amqp_queue_bind(state,channel,amqp_cstring_bytes("path.invalid"),amqp_cstring_bytes("path.dead"),amqp_cstring_bytes("invalid"),amqp_empty_table);
        rpc(amqp_get_rpc_reply(state));
        std::array<amqp_table_entry_t,7> a{};
        const auto string_argument=[&](std::size_t i,const char* key,const char* value) {
            a[i].key=amqp_cstring_bytes(key); a[i].value.kind=AMQP_FIELD_KIND_UTF8;
            a[i].value.value.bytes=amqp_cstring_bytes(value);
        };
        string_argument(0,"x-queue-type","quorum");
        string_argument(1,"x-overflow","reject-publish");
        string_argument(2,"x-dead-letter-exchange","path.dead");
        string_argument(3,"x-dead-letter-routing-key","invalid");
        a[4].key=amqp_cstring_bytes("x-max-length"); a[4].value.kind=AMQP_FIELD_KIND_I32; a[4].value.value.i32=1000;
        a[5].key=amqp_cstring_bytes("x-delivery-limit"); a[5].value.kind=AMQP_FIELD_KIND_I32; a[5].value.value.i32=5;
        // This lab deliberately has ONE node: durable restart, not high availability.
        a[6].key=amqp_cstring_bytes("x-quorum-initial-group-size"); a[6].value.kind=AMQP_FIELD_KIND_I32; a[6].value.value.i32=1;
        amqp_queue_declare(state,channel,amqp_cstring_bytes("path.created"),0,1,0,0,
                           amqp_table_t{static_cast<int>(a.size()),a.data()});
        rpc(amqp_get_rpc_reply(state));
        amqp_queue_bind(state,channel,amqp_cstring_bytes("path.created"),amqp_cstring_bytes("path.events"),
                        amqp_cstring_bytes("task.created"),amqp_empty_table);
        rpc(amqp_get_rpc_reply(state));
    }
};
struct Envelope {
    amqp_envelope_t value{};
    bool valid=false;
    ~Envelope() { if(valid) amqp_destroy_envelope(&value); }
};
std::string bytes(amqp_bytes_t value) {
    return {static_cast<const char*>(value.bytes),value.len};
}
}

int relay_once(bool crash_after_confirm) {
    auto db=database("relay"); pqxx::work tx{db}; transaction_limits(tx);
    const auto pending=tx.exec("SELECT event_id,payload FROM outbox WHERE sent_at IS NULL ORDER BY created_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED");
    if(pending.empty()) {tx.commit();std::cout<<Json{{"status","empty"}}.dump()<<'\n';return 0;}
    const auto event=pending[0][0].as<std::string>(); const auto payload=pending[0][1].as<std::string>();
    Broker broker;
    amqp_confirm_select(broker.state,Broker::channel); rpc(amqp_get_rpc_reply(broker.state));
    amqp_basic_properties_t properties{};
    properties._flags=AMQP_BASIC_DELIVERY_MODE_FLAG|AMQP_BASIC_MESSAGE_ID_FLAG|AMQP_BASIC_CONTENT_TYPE_FLAG;
    properties.delivery_mode=2;
    properties.message_id=amqp_cstring_bytes(event.c_str());
    properties.content_type=amqp_cstring_bytes("application/json");
    sent(amqp_basic_publish(broker.state,Broker::channel,amqp_cstring_bytes("path.events"),
        amqp_cstring_bytes("task.created"),1,0,&properties,amqp_cstring_bytes(payload.c_str())));
    timeval timeout{3,0}; amqp_publisher_confirm_t confirmation{};
    // With mandatory=true an unroutable basic.return arrives before ack. The
    // supported helper then returns UNEXPECTED_STATE; rpc throws, no sent_at.
    rpc(amqp_publisher_confirm_wait(broker.state,&timeout,&confirmation));
    if(confirmation.channel!=Broker::channel||confirmation.method!=AMQP_BASIC_ACK_METHOD||
       confirmation.payload.ack.delivery_tag!=1) throw std::runtime_error("publication not confirmed");
    if(crash_after_confirm) std::_Exit(87); // Broker accepted; SQL marker is absent.
    tx.exec("UPDATE outbox SET sent_at=clock_timestamp() WHERE event_id=$1",pqxx::params{event});
    tx.commit();
    std::cout<<Json{{"status","broker_confirmed"},{"event_id",event}}.dump()<<'\n';
    return 0;
}

int consume_once(bool crash_after_effect) {
    Broker broker;
    amqp_basic_qos(broker.state,Broker::channel,0,1,0); rpc(amqp_get_rpc_reply(broker.state));
    amqp_basic_consume(broker.state,Broker::channel,amqp_cstring_bytes("path.created"),amqp_empty_bytes,0,0,0,amqp_empty_table);
    rpc(amqp_get_rpc_reply(broker.state));
    Envelope message; timeval timeout{2,0};
    const auto delivery=amqp_consume_message(broker.state,&message.value,&timeout,0);
    if(delivery.reply_type==AMQP_RESPONSE_LIBRARY_EXCEPTION&&delivery.library_error==AMQP_STATUS_TIMEOUT) {
        std::cout<<Json{{"status","empty"}}.dump()<<'\n';return 0;
    }
    rpc(delivery); message.valid=true;
    Json event;
    try {
        if(message.value.message.body.len>4096) throw std::invalid_argument("message too large");
        std::vector<std::set<std::string>> keys;
        event=Json::parse(bytes(message.value.message.body),[&](int depth,Json::parse_event_t kind,Json& value) {
            if(depth>16) throw std::invalid_argument("event nesting limit");
            if(kind==Json::parse_event_t::object_start) keys.emplace_back();
            if(kind==Json::parse_event_t::key && !keys.back().insert(value.get<std::string>()).second)
                throw std::invalid_argument("duplicate event field");
            if(kind==Json::parse_event_t::object_end) keys.pop_back();
            return true;
        });
        if(!event.is_object()||event.size()!=5||!event.contains("schema_version")||
           !event["schema_version"].is_number_integer()||event["schema_version"]!=1||
           event.value("type",std::string{})!="task.created"||!event.contains("event_id")||
           !event["event_id"].is_string()||!lower_hex64(event["event_id"].get<std::string>())||
           !event.contains("task_id")||!event["task_id"].is_number_integer()||
           !event.contains("owner_id")||!event["owner_id"].is_number_integer())
            throw std::invalid_argument("invalid event");
        for(const auto* name:{"task_id","owner_id"}) {
            if(event[name].is_number_unsigned() && event[name].get<unsigned long long>()>
                    static_cast<unsigned long long>(std::numeric_limits<long long>::max()))
                throw std::invalid_argument("event identifier out of range");
            if(event[name].get<long long>()<=0) throw std::invalid_argument("invalid event identifier");
        }
        const auto& properties=message.value.message.properties;
        if(!(properties._flags&AMQP_BASIC_MESSAGE_ID_FLAG)||bytes(properties.message_id)!=event["event_id"].get<std::string>())
            throw std::invalid_argument("event identity mismatch");
    } catch(const std::exception&) {
        sent(amqp_basic_reject(broker.state,Broker::channel,message.value.delivery_tag,0));
        std::cout<<Json{{"status","invalid_rejected"}}.dump()<<'\n';return 0;
    }
    const auto identity=event["event_id"].get<std::string>();
    const auto owner=event["owner_id"].get<long long>();
    const auto task=event["task_id"].get<long long>();
    if(owner<=0||task<=0) {
        sent(amqp_basic_reject(broker.state,Broker::channel,message.value.delivery_tag,0));
        std::cout<<Json{{"status","invalid_rejected"}}.dump()<<'\n';return 0;
    }
    auto db=database("consumer"); pqxx::work tx{db}; transaction_limits(tx);
    const auto effect=tx.exec(
        "WITH received AS (INSERT INTO receipts(consumer,event_id) VALUES('creation-totals-v1',$1) "
        "ON CONFLICT(consumer,event_id) DO NOTHING RETURNING event_id) "
        "INSERT INTO creation_totals(user_id,total) SELECT $2,1 FROM received "
        "ON CONFLICT(user_id) DO UPDATE SET total=creation_totals.total+1 RETURNING total",
        pqxx::params{identity,owner});
    const bool applied=!effect.empty();
    tx.commit();
    if(crash_after_effect) std::_Exit(88); // Receipt+counter committed; no delivery ack.
    sent(amqp_basic_ack(broker.state,Broker::channel,message.value.delivery_tag,0));
    std::cout<<Json{{"status",applied?"effect_committed":"duplicate"},{"event_id",identity},
                    {"redelivered",static_cast<bool>(message.value.redelivered)}}.dump()<<'\n';
    return 0;
}
}
