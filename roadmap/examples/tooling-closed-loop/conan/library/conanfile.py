from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout


class TaskLabel(ConanFile):
    name = "course-task-label"
    version = "1.0"
    package_type = "static-library"
    license = "MIT"
    settings = "os", "arch", "compiler", "build_type"
    exports_sources = "CMakeLists.txt", "include/*", "src/*"

    def layout(self):
        cmake_layout(self)

    def generate(self):
        CMakeToolchain(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        CMake(self).install()

    def package_info(self):
        self.cpp_info.libs = ["course_task_label"]
        self.cpp_info.set_property("cmake_file_name", "CourseTaskLabel")
        self.cpp_info.set_property("cmake_target_name", "Course::TaskLabel")
