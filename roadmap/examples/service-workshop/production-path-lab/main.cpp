#include "common.hpp"
#include <sodium.h>
#include <csignal>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if(sodium_init()<0) throw std::runtime_error("sodium initialization failed");
        std::signal(SIGPIPE,SIG_IGN);
        const std::string mode=argc==2?argv[1]:"";
        if(mode=="api") return course_path::api(false);
        if(mode=="api-crash-after-commit") return course_path::api(true);
        if(mode=="seed") {course_path::seed();std::cout<<"seeded\n";return 0;}
        if(mode=="relay-once") return course_path::relay_once(false);
        if(mode=="relay-crash-after-confirm") return course_path::relay_once(true);
        if(mode=="consume-once") return course_path::consume_once(false);
        if(mode=="consume-crash-after-effect") return course_path::consume_once(true);
        if(mode=="self-test") {
            const auto a=course_path::random_secret(), b=course_path::random_secret();
            if(!course_path::lower_hex64(a)||!course_path::lower_hex64(b)||a==b||
               course_path::digest(a)==a||course_path::digest(a)!=course_path::digest(a))
                throw std::runtime_error("primitive contract failed");
            const auto verifier=course_path::password_verifier("local-test-password");
            if(!course_path::password_matches("local-test-password",verifier)||
                course_path::password_matches("different-password",verifier))
                throw std::runtime_error("password verification contract failed");
            std::cout<<"primitive contracts passed; this is not a cryptographic audit\n";
            return 0;
        }
        std::cerr<<"mode: api|seed|relay-once|consume-once|self-test or explicit crash modes\n";
        return 2;
    } catch(const pqxx::sql_error& error) {
        std::cerr<<"database failure sqlstate="<<error.sqlstate()<<'\n';return 1;
    } catch(const std::exception&) {
        // Do not accidentally copy credentials, bound SQL values or bodies to logs.
        std::cerr<<"local lab operation failed; inspect the documented stage and resource state\n";
        return 1;
    }
}
