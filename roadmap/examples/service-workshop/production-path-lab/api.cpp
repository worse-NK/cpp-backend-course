#include "common.hpp"
#include <httplib.h>
#include <algorithm>
#include <charconv>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <set>
#include <vector>

namespace course_path {
namespace {
void response(httplib::Response& out,int status,const Json& body) {
    out.status=status;
    out.set_content(body.dump(),"application/json");
}
template<class F> auto guarded(F operation) {
    return [operation](const httplib::Request& in,httplib::Response& out) {
        try { operation(in,out); }
        catch(const Failure& f) { response(out,f.status,Json{{"error",f.code}}); }
        catch(const pqxx::sql_error& error) {
            // SQLSTATE is diagnostic; no SQL, bound values, headers or tokens.
            std::cerr<<"database failure sqlstate="<<error.sqlstate()<<'\n';
            response(out,503,Json{{"error","database_unavailable"}});
        }
        catch(const pqxx::broken_connection&) { response(out,503,Json{{"error","database_unavailable"}}); }
        catch(const std::exception&) { response(out,500,Json{{"error","internal_failure"}}); }
    };
}
Json object_body(const httplib::Request& in) {
    if(in.get_header_value("Content-Type")!="application/json") throw Failure{415,"json_required"};
    if(in.body.empty()||in.body.size()>4096) throw Failure{400,"invalid_body"};
    try {
        std::vector<std::set<std::string>> keys;
        auto value=Json::parse(in.body,[&](int depth,Json::parse_event_t event,Json& parsed) {
            if(depth>32) throw Failure{400,"json_depth_limit"};
            if(event==Json::parse_event_t::object_start) keys.emplace_back();
            if(event==Json::parse_event_t::key && !keys.back().insert(parsed.get<std::string>()).second)
                throw Failure{400,"duplicate_fields"};
            if(event==Json::parse_event_t::object_end) keys.pop_back();
            return true;
        });
        if(!value.is_object()) throw Failure{400,"object_required"};
        return value;
    } catch(const Json::exception&) { throw Failure{400,"invalid_json"}; }
}
void fields(const Json& body,std::initializer_list<std::string_view> names) {
    if(body.size()!=names.size()) throw Failure{400,"invalid_fields"};
    for(auto name:names) if(!body.contains(name)) throw Failure{400,"invalid_fields"};
}
std::string string_field(const Json& body,const char* key,std::size_t limit) {
    if(!body.at(key).is_string()) throw Failure{400,"invalid_fields"};
    auto value=body.at(key).get<std::string>();
    if(value.empty()||value.size()>limit||value.find('\0')!=std::string::npos)
        throw Failure{400,"invalid_fields"};
    return value;
}
std::string session_digest(const httplib::Request& in) {
    if(in.get_header_value_count("Authorization")!=1) throw Failure{401,"session_required"};
    const auto header=in.get_header_value("Authorization");
    if(header.size()!=71) throw Failure{401,"session_required"};
    auto prefix=header.substr(0,7);
    for(char& c:prefix) if(c>='A'&&c<='Z') c=static_cast<char>(c-'A'+'a');
    if(prefix!="bearer "||!lower_hex64(std::string_view(header).substr(7)))
        throw Failure{401,"session_required"};
    return digest(std::string_view(header).substr(7));
}
long long authenticate(pqxx::work& tx,const std::string& token_digest) {
    // One active session per user. FOR UPDATE deliberately serializes protected
    // operations of that session with logout, renewal and idle-time updates.
    auto session=tx.exec(
        "SELECT user_id FROM sessions WHERE token_digest=$1 AND revoked_at IS NULL "
        "AND expires_at>clock_timestamp() "
        "AND last_seen_at>clock_timestamp()-interval '5 minutes' FOR UPDATE",
        pqxx::params{token_digest});
    if(session.empty()) throw Failure{401,"session_required"};
    tx.exec("UPDATE sessions SET last_seen_at=clock_timestamp() WHERE token_digest=$1",
            pqxx::params{token_digest});
    return session[0][0].as<long long>();
}
long long task_number(const httplib::Request& in) {
    const auto text=in.matches[1].str();
    long long number=0;
    const auto [end,ec]=std::from_chars(text.data(),text.data()+text.size(),number);
    if(ec!=std::errc{}||end!=text.data()+text.size()||number<=0) throw Failure{404,"not_found"};
    return number;
}
Json task_json(const pqxx::row& row) {
    return Json{{"id",row[0].as<long long>()},{"title",row[1].as<std::string>()},
                {"version",row[2].as<long long>()}};
}
bool command_key_valid(const std::string& key) {
    if(key.empty()||key.size()>64) return false;
    for(char c:key) if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-')) return false;
    return true;
}
}

int api(bool crash_after_commit) {
    const auto dummy=password_verifier(random_secret());
    httplib::Server server;
    server.new_task_queue=[] {return new httplib::ThreadPool(2,2,8);};
    server.set_payload_max_length(4096);
    server.set_read_timeout(3,0);
    server.set_write_timeout(3,0);
    server.set_keep_alive_timeout(2);
    server.set_keep_alive_max_count(8);
    const auto lab_id=setting("PATH_LAB_ID","");
    if(!lower_hex64(lab_id)) throw std::runtime_error("valid lab identifier is required");
    server.set_default_headers({{"Cache-Control","no-store"},{"X-Content-Type-Options","nosniff"},
                                {"X-Course-Lab",lab_id}});
    server.Get("/health",guarded([](const auto&,auto& out) {response(out,200,Json{{"status","ok"}});}));
    server.Get("/ready",guarded([](const auto&,auto& out) {
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        tx.exec("SELECT 1"); tx.commit(); response(out,200,Json{{"status","ready"}});
    }));
    server.Post("/login",guarded([&](const auto& in,auto& out) {
        const auto body=object_body(in); fields(body,{"username","password"});
        const auto username=string_field(body,"username",32);
        const auto password=string_field(body,"password",1024);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto users=tx.exec("SELECT user_id,password_verifier FROM users WHERE username=$1",pqxx::params{username});
        const auto verifier=users.empty()?dummy:users[0][1].as<std::string>();
        const bool valid=password_matches(password,verifier);
        if(!valid||users.empty()) throw Failure{401,"invalid_credentials"};
        const auto user=users[0][0].as<long long>();
        const auto token=random_secret();
        tx.exec("INSERT INTO sessions(token_digest,user_id,expires_at) "
                "VALUES($1,$2,clock_timestamp()+interval '20 minutes') "
                "ON CONFLICT(user_id) DO UPDATE SET token_digest=excluded.token_digest,"
                "created_at=clock_timestamp(),last_seen_at=clock_timestamp(),"
                "expires_at=excluded.expires_at,revoked_at=NULL",pqxx::params{digest(token),user});
        tx.commit();
        response(out,200,Json{{"token",token},{"token_type","Bearer"},{"expires_in",1200}});
    }));
    server.Post("/logout",guarded([](const auto& in,auto& out) {
        const auto token=session_digest(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        (void)authenticate(tx,token);
        tx.exec("UPDATE sessions SET revoked_at=clock_timestamp() WHERE token_digest=$1",pqxx::params{token});
        tx.commit(); response(out,200,Json{{"status","logged_out"}});
    }));
    server.Get("/tasks",guarded([](const auto& in,auto& out) {
        const auto token=session_digest(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto user=authenticate(tx,token);
        auto rows=tx.exec("SELECT task_id,title,version FROM tasks WHERE owner_id=$1 ORDER BY task_id LIMIT 100",pqxx::params{user});
        Json tasks=Json::array(); for(const auto& row:rows) tasks.push_back(task_json(row));
        tx.commit(); response(out,200,tasks);
    }));
    server.Get(R"(/tasks/(\d+))",guarded([](const auto& in,auto& out) {
        const auto token=session_digest(in); const auto number=task_number(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto user=authenticate(tx,token);
        auto rows=tx.exec("SELECT task_id,title,version FROM tasks WHERE task_id=$1 AND owner_id=$2",pqxx::params{number,user});
        if(rows.empty()) throw Failure{404,"not_found"};
        auto task=task_json(rows[0]); tx.commit(); response(out,200,task);
    }));
    server.Post("/tasks",guarded([&](const auto& in,auto& out) {
        const auto token=session_digest(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto user=authenticate(tx,token); // Identity before body-based rights.
        const auto body=object_body(in); fields(body,{"title"});
        const auto title=string_field(body,"title",200);
        if(in.get_header_value_count("Idempotency-Key")!=1) throw Failure{400,"command_key_required"};
        const auto key=in.get_header_value("Idempotency-Key");
        if(!command_key_valid(key)) throw Failure{400,"invalid_command_key"};
        const auto claimed=tx.exec("INSERT INTO commands(user_id,command_key,request_title) VALUES($1,$2,$3) "
                                  "ON CONFLICT(user_id,command_key) DO NOTHING RETURNING user_id",
                                  pqxx::params{user,key,title});
        if(claimed.empty()) {
            const auto previous=tx.exec("SELECT request_title,task_id FROM commands WHERE user_id=$1 AND command_key=$2",pqxx::params{user,key});
            if(previous.empty()||previous[0][1].is_null()) throw std::runtime_error("incomplete command invariant");
            if(previous[0][0].as<std::string>()!=title) throw Failure{409,"command_payload_mismatch"};
            // Replay returns the original creation response, not a renamed title.
            auto value=Json{{"id",previous[0][1].as<long long>()},{"title",title},{"version",1}};
            tx.commit(); out.set_header("Idempotent-Replay","true"); response(out,201,value); return;
        }
        auto rows=tx.exec("INSERT INTO tasks(owner_id,title) VALUES($1,$2) RETURNING task_id,title,version",pqxx::params{user,title});
        const auto number=rows[0][0].as<long long>(); const auto event=random_secret();
        const auto payload=Json{{"schema_version",1},{"type","task.created"},{"event_id",event},
                                {"task_id",number},{"owner_id",user}}.dump();
        tx.exec("INSERT INTO outbox(event_id,task_id,payload) VALUES($1,$2,$3)",pqxx::params{event,number,payload});
        tx.exec("UPDATE commands SET task_id=$3 WHERE user_id=$1 AND command_key=$2",pqxx::params{user,key,number});
        auto value=task_json(rows[0]); tx.commit();
        if(crash_after_commit) std::_Exit(86); // Explicit CLI-only fault, no response.
        response(out,201,value);
    }));
    server.Put(R"(/tasks/(\d+))",guarded([](const auto& in,auto& out) {
        const auto token=session_digest(in); const auto number=task_number(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto user=authenticate(tx,token);
        const auto body=object_body(in); fields(body,{"title","version"});
        const auto title=string_field(body,"title",200);
        if(!body["version"].is_number_integer()) throw Failure{400,"invalid_version"};
        if(body["version"].is_number_unsigned() && body["version"].template get<unsigned long long>()>
                static_cast<unsigned long long>(std::numeric_limits<long long>::max())) throw Failure{400,"invalid_version"};
        long long version=0;
        try {version=body["version"].template get<long long>();} catch(const Json::exception&) {throw Failure{400,"invalid_version"};}
        if(version<=0||version==std::numeric_limits<long long>::max()) throw Failure{400,"invalid_version"};
        const auto changed=tx.exec("UPDATE tasks SET title=$1,version=version+1 WHERE task_id=$2 AND owner_id=$3 AND version=$4 RETURNING task_id,title,version",
                                   pqxx::params{title,number,user,version});
        if(changed.empty()) {
            const auto owned=tx.exec("SELECT 1 FROM tasks WHERE task_id=$1 AND owner_id=$2",pqxx::params{number,user});
            throw Failure{owned.empty()?404:409,owned.empty()?"not_found":"version_conflict"};
        }
        auto task=task_json(changed[0]); tx.commit(); response(out,200,task);
    }));
    server.Get("/creation-total",guarded([](const auto& in,auto& out) {
        const auto token=session_digest(in);
        auto db=database("api"); pqxx::work tx{db}; transaction_limits(tx);
        const auto user=authenticate(tx,token);
        const auto rows=tx.exec("SELECT total FROM creation_totals WHERE user_id=$1",pqxx::params{user});
        const auto total=rows.empty()?0:rows[0][0].as<long long>();
        tx.commit(); response(out,200,Json{{"total",total}});
    }));
    const auto bind=setting("PATH_API_BIND","127.0.0.1");
    // Docker publishes this container port ONLY to host 127.0.0.1.
    if(!server.listen(bind,8080)) throw std::runtime_error("listen failed");
    return 0;
}
}
