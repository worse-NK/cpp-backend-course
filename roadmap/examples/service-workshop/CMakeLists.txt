cmake_minimum_required(VERSION 3.24)
project(course_service_workshop VERSION 1.0 LANGUAGES CXX)

# This small POSIX teaching server uses sigtimedwait, not a signal handler.
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
  message(FATAL_ERROR "Use Linux or WSL for this sigtimedwait-based workshop")
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
option(COURSE_WITH_POSTGRES "Build the optional PostgreSQL storage adapter" OFF)
include(FetchContent)
include(CTest)
find_package(Threads REQUIRED)

# Release archives from the maintainers, pinned by SHA-256. Fetching needs network
# access on the first configure; CMake's FETCHCONTENT_SOURCE_DIR_* allows offline use.
set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_INSTALL OFF CACHE BOOL "" FORCE)
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
set(JSON_Install OFF CACHE BOOL "" FORCE)
FetchContent_Declare(httplib
  URL https://codeload.github.com/yhirose/cpp-httplib/tar.gz/refs/tags/v0.59.0
  URL_HASH SHA256=7c8cc7df044abb837d75f7c1e56333305acb40335c3788b8f5fbf5927e63e148
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(httplib json)

add_library(course_storage storage.cpp)
target_include_directories(course_storage PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(course_storage PUBLIC nlohmann_json::nlohmann_json Threads::Threads)
if(COURSE_WITH_POSTGRES)
  # libpq is the system C client: install libpq-dev (Debian/Ubuntu) first.
  find_package(PostgreSQL REQUIRED)
  set(BUILD_TEST OFF CACHE BOOL "" FORCE)
  set(SKIP_BUILD_TEST ON CACHE BOOL "" FORCE)
  set(BUILD_DOC OFF CACHE BOOL "" FORCE)
  # Keep the workshop container's runtime closure simple: libpqxx is static;
  # the PostgreSQL C client libpq (and its system dependencies) stays dynamic.
  set(BUILD_SHARED_LIBS OFF)
  FetchContent_Declare(libpqxx
    URL https://codeload.github.com/jtv/libpqxx/tar.gz/refs/tags/7.10.1
    URL_HASH SHA256=cfbbb1d93a0a3d81319ec71d9a3db80447bb033c4f6cee088554a88862fd77d7
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
  FetchContent_MakeAvailable(libpqxx)
  target_compile_definitions(course_storage PUBLIC COURSE_WITH_POSTGRES=1)
  target_link_libraries(course_storage PRIVATE libpqxx::pqxx)
endif()

add_executable(course_tasks app.cpp)
target_link_libraries(course_tasks PRIVATE course_storage httplib::httplib)
target_compile_definitions(course_tasks PRIVATE
  CPPHTTPLIB_REQUEST_URI_MAX_LENGTH=1024
  CPPHTTPLIB_HEADER_MAX_LENGTH=4096
  CPPHTTPLIB_HEADER_MAX_COUNT=32
  CPPHTTPLIB_REGEX_ROUTE_PATH_MAX_LENGTH=128)
foreach(course_target course_storage course_tasks)
  target_compile_options(${course_target} PRIVATE -Wall -Wextra -Wpedantic)
endforeach()
if(BUILD_TESTING)
  add_executable(course_storage_tests tests.cpp)
  target_link_libraries(course_storage_tests PRIVATE course_storage)
  target_compile_options(course_storage_tests PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME course_storage_contract COMMAND course_storage_tests)
endif()
