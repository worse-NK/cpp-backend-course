cmake_minimum_required(VERSION 3.24)
project(course_production_path LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
include(FetchContent)
find_package(Threads REQUIRED)
find_package(PostgreSQL REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(SODIUM REQUIRED IMPORTED_TARGET libsodium>=1.0.18)

set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_INSTALL OFF CACHE BOOL "" FORCE)
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
set(JSON_Install OFF CACHE BOOL "" FORCE)
set(BUILD_TEST OFF CACHE BOOL "" FORCE)
set(SKIP_BUILD_TEST ON CACHE BOOL "" FORCE)
set(BUILD_DOC OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BUILD_STATIC_LIBS ON CACHE BOOL "" FORCE)
set(ENABLE_SSL_SUPPORT OFF CACHE BOOL "" FORCE)
FetchContent_Declare(httplib
 URL https://codeload.github.com/yhirose/cpp-httplib/tar.gz/refs/tags/v0.59.0
 URL_HASH SHA256=7c8cc7df044abb837d75f7c1e56333305acb40335c3788b8f5fbf5927e63e148
 DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_Declare(json
 URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
 URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
 DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_Declare(libpqxx
 URL https://codeload.github.com/jtv/libpqxx/tar.gz/refs/tags/7.10.1
 URL_HASH SHA256=cfbbb1d93a0a3d81319ec71d9a3db80447bb033c4f6cee088554a88862fd77d7
 DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_Declare(rabbitmq_c
 URL https://codeload.github.com/alanxz/rabbitmq-c/tar.gz/refs/tags/v0.18.1
 URL_HASH SHA256=0779bd4f00175ff2f722f9dc43b542bea3bc606ed079e7099fa8a18627c2ddc9
 DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(httplib json libpqxx rabbitmq_c)

add_executable(production_path main.cpp common.cpp api.cpp messaging.cpp)
target_link_libraries(production_path PRIVATE httplib::httplib nlohmann_json::nlohmann_json
 libpqxx::pqxx rabbitmq::rabbitmq-static PkgConfig::SODIUM Threads::Threads)
target_compile_options(production_path PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(production_path PRIVATE
 CPPHTTPLIB_REQUEST_URI_MAX_LENGTH=1024 CPPHTTPLIB_HEADER_MAX_LENGTH=4096
 CPPHTTPLIB_HEADER_MAX_COUNT=32 CPPHTTPLIB_REGEX_ROUTE_PATH_MAX_LENGTH=128)
