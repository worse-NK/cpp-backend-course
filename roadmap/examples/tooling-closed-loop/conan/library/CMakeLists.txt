cmake_minimum_required(VERSION 3.28)
project(course_task_label LANGUAGES CXX)
add_library(course_task_label STATIC src/task_label.cpp)
target_compile_features(course_task_label PUBLIC cxx_std_20)
target_include_directories(course_task_label PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
install(TARGETS course_task_label ARCHIVE DESTINATION lib)
install(FILES include/task_label.hpp DESTINATION include)
