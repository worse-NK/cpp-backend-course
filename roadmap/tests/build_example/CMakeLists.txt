cmake_minimum_required(VERSION 3.20)
project(Lesson LANGUAGES CXX)
include(GNUInstallDirs)

add_library(core STATIC src/core.cpp)
target_compile_features(core PUBLIC cxx_std_20)
target_include_directories(core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

add_executable(app src/main.cpp)
target_link_libraries(app PRIVATE core)

include(CTest)
if(BUILD_TESTING)
    add_executable(core_tests tests/core_test.cpp)
    target_link_libraries(core_tests PRIVATE core)
    add_test(NAME core.unit COMMAND core_tests)
endif()

install(TARGETS core EXPORT LessonTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES include/core.hpp
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT LessonTargets
        FILE LessonTargets.cmake
        NAMESPACE Lesson::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Lesson)
