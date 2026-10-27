"""Check runnable interview examples without requiring network permissions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/interview_gaps"


class InterviewExamples(unittest.TestCase):
    def compile_run(self, name, expected=None, transform=lambda s: s, assembly=False, exit_code=0):
        source = transform((EXAMPLES / name).read_text())
        with tempfile.TemporaryDirectory(prefix="interview-examples-") as tmp:
            binary = str(Path(tmp) / "example")
            command = ["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                       "-O2", "-pthread", "-x", "c++", "-", "-o", binary]
            if assembly:
                command.insert(1, "-S")
            compiled = subprocess.run(command, input=source, text=True,
                                      capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            if expected is not None:
                result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_local_object(self):
        self.compile_run("local_object.cpp", "before Part Job7 work ~Job ~Part after\n")
        self.compile_run("local_object.cpp", "before Part Job7 work tail ~Job ~Part after\n",
                         lambda s: s.replace("work(true)", "work(false)"))

    def test_spsc(self):
        for size in (2, 4, 128):
            with self.subTest(size=size):
                self.compile_run("spsc.cpp", "boundary checks passed\nFIFO 100000 passed\n",
                                 lambda s: s.replace("SpscIntQueue<128> queue", f"SpscIntQueue<{size}> queue"))

    def test_other_examples_compile(self):
        self.compile_run("multicast.cpp")
        self.compile_run("stack_frame.cpp", assembly=True)

    def test_spsc_consumer_start_failure_does_not_hang(self):
        self.compile_run("spsc.cpp", "", lambda s: s.replace(
            "std::jthread consumer([&] {",
            'throw std::runtime_error("simulated consumer start failure");\n            std::jthread consumer([&] {'),
            exit_code=1)

    def test_printed_code_matches_download(self):
        for number, sid, filename in [
            (1, "local-object-journey", "local_object.cpp"),
            (5, "stack-frame-object", "stack_frame.cpp"),
            (6, "spsc-ring-code", "spsc.cpp"),
            (7, "multicast-socket-lab", "multicast.cpp"),
            (10, "capacity-local-lab", "capacity.js"),
        ]:
            data = json.loads((ROOT / f"content/station{number}.json").read_text())
            section = next(s for s in data["theory"] if s["id"] == sid)
            codes = [b["code"].strip() for b in section["blocks"] if b["type"] == "code"]
            self.assertIn((EXAMPLES / filename).read_text().strip(), codes)


if __name__ == "__main__":
    unittest.main()
