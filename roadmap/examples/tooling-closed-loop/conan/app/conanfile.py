from conan import ConanFile
from conan.tools.cmake import CMakeDeps, CMakeToolchain


class ReportApp(ConanFile):
    settings = "os", "arch", "compiler", "build_type"
    requires = "course-task-label/1.0"

    def generate(self):
        CMakeDeps(self).generate()
        toolchain = CMakeToolchain(self)
        toolchain.user_presets_path = False
        toolchain.generate()
