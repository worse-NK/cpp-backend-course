#pragma once
#include <nlohmann/json.hpp>
#include <pqxx/pqxx>
#include <string>
#include <string_view>

namespace course_path {
using Json=nlohmann::json;
struct Failure { int status; std::string code; };
std::string setting(const char* key,std::string fallback);
std::string secret_file(const std::string& path);
std::string random_secret();
std::string digest(std::string_view value);
std::string password_verifier(std::string_view value);
bool password_matches(std::string_view password,const std::string& verifier);
bool lower_hex64(std::string_view text);
pqxx::connection database(const std::string& role);
void transaction_limits(pqxx::work& tx);
void seed();
int api(bool crash_after_commit);
int relay_once(bool crash_after_confirm);
int consume_once(bool crash_after_effect);
}
