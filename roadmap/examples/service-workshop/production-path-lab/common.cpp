#include "common.hpp"
#include <sodium.h>
#include <array>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace course_path {
std::string setting(const char* key,std::string fallback) {
    const char* value=std::getenv(key);
    return value && *value ? std::string(value) : fallback;
}
std::string secret_file(const std::string& path) {
    std::ifstream in(path,std::ios::binary);
    if(!in) throw std::runtime_error("secret file is unavailable");
    std::string value((std::istreambuf_iterator<char>(in)),{});
    if(!value.empty() && value.back()=='\n') value.pop_back();
    if(value.empty() || value.size()>2048 || value.find('\0')!=std::string::npos)
        throw std::runtime_error("invalid secret file");
    return value;
}
std::string hex(const unsigned char* bytes,std::size_t size) {
    std::string value(size*2+1,'\0');
    sodium_bin2hex(value.data(),value.size(),bytes,size);
    value.resize(size*2);
    return value;
}
std::string random_secret() {
    std::array<unsigned char,32> value{};
    randombytes_buf(value.data(),value.size());
    return hex(value.data(),value.size());
}
std::string digest(std::string_view value) {
    std::array<unsigned char,32> output{};
    if(crypto_generichash(output.data(),output.size(),
        reinterpret_cast<const unsigned char*>(value.data()),value.size(),nullptr,0)!=0)
        throw std::runtime_error("hash operation failed");
    return hex(output.data(),output.size());
}
std::string password_verifier(std::string_view value) {
    std::array<char,crypto_pwhash_STRBYTES> out{};
    if(crypto_pwhash_str(out.data(),value.data(),value.size(),
        crypto_pwhash_OPSLIMIT_INTERACTIVE,crypto_pwhash_MEMLIMIT_INTERACTIVE)!=0)
        throw std::runtime_error("password hashing failed");
    return out.data();
}
bool password_matches(std::string_view password,const std::string& verifier) {
    return crypto_pwhash_str_verify(verifier.c_str(),password.data(),password.size())==0;
}
bool lower_hex64(std::string_view value) {
    if(value.size()!=64) return false;
    for(char c:value) if(!((c>='0'&&c<='9')||(c>='a'&&c<='f'))) return false;
    return true;
}
std::string conn_quote(std::string_view value) {
    std::string result="'";
    for(char c:value) { if(c=='\''||c=='\\') result+='\\'; result+=c; }
    return result+"'";
}
pqxx::connection database(const std::string& role) {
    if(role!="api" && role!="relay" && role!="consumer" && role!="admin")
        throw std::invalid_argument("unknown fixed role");
    const auto user=role=="admin"?"postgres":"path_"+role;
    const auto password=secret_file("/run/secrets/"+role+"_password");
    const auto connection="host="+conn_quote(setting("PATH_DB_HOST","db"))+
        " dbname=course_path user="+conn_quote(user)+" password="+conn_quote(password)+
        " connect_timeout=3 application_name=course_path_"+role;
    return pqxx::connection{connection};
}
void transaction_limits(pqxx::work& tx) {
    tx.exec("SET LOCAL statement_timeout='2s'");
    tx.exec("SET LOCAL lock_timeout='1s'");
}
void seed() {
    auto db=database("admin"); pqxx::work tx{db};
    transaction_limits(tx);
    for(const auto& [id,name]:std::array<std::pair<long long,const char*>,2>{{{1,"alice"},{2,"bo"}}}) {
        auto password=secret_file(std::string("/run/secrets/")+name+"_password");
        auto verifier=password_verifier(password);
        tx.exec("INSERT INTO course_path.users(user_id,username,password_verifier) VALUES($1,$2,$3) ON CONFLICT(user_id) DO NOTHING",
                pqxx::params{id,name,verifier});
        sodium_memzero(password.data(),password.size());
    }
    tx.commit();
}
}
