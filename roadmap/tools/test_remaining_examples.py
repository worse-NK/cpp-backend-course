#!/usr/bin/env python3
"""Check revised theory and reading exercises in stations 0–5."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_expanded_examples import code, station

ROOT = Path(__file__).resolve().parents[1]


class RemainingExamples(unittest.TestCase):
    def test_unique_lock_examples_release_before_next_acquisition(self):
        section = next(s for s in station(6)["theory"] if s["id"] == "lock-wrappers")
        examples = [b["code"] for b in section["blocks"]
                    if b["type"] == "code" and "doMoreProtectedWork" in b["code"]]
        self.assertEqual(len(examples), 1)
        # Actual std::mutex catches accidental overlapping ownership by timeout.
        self.cpp("""#include <mutex>
#include <cassert>
std::mutex m;
int protected_calls = 0;
void doProtectedWork() { ++protected_calls; }
void doMoreProtectedWork() { ++protected_calls; }
void doLongWorkWithoutLock() { }
int main() {
""" + examples[0] + "\nassert(protected_calls == 3);\n}", "", flags=("-pthread",))

    def override_example(self):
        section = next(s for s in station(2)["theory"] if s["id"] == "virtual-edge-cases")
        marker = "int value() const & override"
        matches = [b["code"] for b in section["blocks"]
                   if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(matches), 1, "Expected exactly one override-signature example")
        return matches[0]

    def cpp(self, source, expected=None, valid=True, flags=(), expected_exit=0):
        with tempfile.TemporaryDirectory(prefix="roadmap-remaining-") as directory:
            binary = str(Path(directory) / "example")
            command = ["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic", *flags, "-x", "c++", "-"]
            command += ["-fsyntax-only"] if expected is None else ["-o", binary]
            result = subprocess.run(command, input=source, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode == 0, valid, result.stderr)
            if valid and expected is not None:
                run = subprocess.run([binary], text=True, capture_output=True, timeout=5)
                self.assertEqual(run.returncode, expected_exit, run.stderr)
                choices = {expected} if isinstance(expected, str) else expected
                self.assertIn(run.stdout.strip(), choices)

    def test_theory_outputs(self):
        cases = [
            (0, "full-example", 0, "1 0 7 5"),
            (1, "smart-ptr-deep", 1, "2 1 destroy 1 0"),
            (1, "smart-ptr-deep", 2, ""),
            (2, "virtual-edge-cases", 0, "Bi Dd Bi"),
            (2, "slicing", 0, "BD 1 7"),
            (2, "polymorphic-copy", 0, "7 8"),
            (2, "polymorphic-boundary", 0, "7"),
            (3, "invalidation-erasure", 0, "1 3"),
            (3, "invalidation-erasure", 1, "5 3 1 3 4"),
            (3, "unordered-contract", 0, "2 70 90"),
            (3, "associative-deep", 0, "make 80 1 0 80\nmake 443 443"),
            (3, "comparator-contract", 0, "2 0 aa"),
            (3, "templates-deep", 0, "LCR"),
            (4, "context-and-logging", 0, "load profile -> storage unavailable"),
        ]
        for number, section, index, output in cases:
            with self.subTest(number=number, section=section, index=index):
                self.cpp(code(number, section, index), output)
        this_section = next(s for s in station(0)["theory"] if s["id"] == "this")
        chaining = [b["code"] for b in this_section["blocks"]
                    if b["type"] == "code" and "Point copy = a.setX(9)" in b["code"]]
        self.assertEqual(len(chaining), 1)
        self.cpp(chaining[0], "4 7 9 10")
        self.cpp(code(1, "smart-ptr-deep", 0))
        self.cpp(self.override_example())

    def test_return_paths(self):
        direct = code(1, "copy-elision", 0)
        self.cpp(direct, "ND")
        self.cpp(direct, "ND", flags=("-fno-elide-constructors",))
        self.cpp(direct.replace("return Token{};", "Token local; return local;"), valid=False)
        named = code(1, "copy-elision", 1)
        self.cpp(named, {"ND", "NMDD"})
        self.cpp(named, "NMDD", flags=("-fno-elide-constructors",))
        self.cpp("#include <utility>\n" + named.replace("return local;", "return std::move(local);"), "NMDD")
        frozen = named.replace("Trace local;", "const Trace local;")
        self.cpp(frozen, {"ND", "NCDD"})
        self.cpp(frozen, "NCDD", flags=("-fno-elide-constructors",))

    def test_dispatch_and_forwarding_variants(self):
        hiding = code(2, "virtual-edge-cases", 0).replace("using Base::f;", "")
        self.cpp(hiding, "Dd Dd Bi")
        signature = self.override_example()
        self.cpp(signature.replace("int value() const & override", "int value() override"), valid=False)
        forwarding = code(3, "templates-deep")
        self.cpp(forwarding.replace("std::forward<T>(item)", "item"), "LCL")
        self.cpp(forwarding.replace("std::forward<T>(item)", "std::move(item)"), "RCR")
        clone = code(2, "polymorphic-copy")
        self.cpp(clone.replace("std::unique_ptr<Value> clone() const override",
                               "std::unique_ptr<Number> clone() const override"), valid=False)

    def test_smart_owner_precondition(self):
        clone = station(2)["quizzes"]["interview"][11]["q"].split("\n\n", 1)[1]
        self.cpp(clone, "8 8")
        self.cpp(code(1, "smart-ptr-deep", 2).replace(
            "auto first = std::make_shared<Session>();\n    auto second = first->self();\n    return first.use_count() == 2 ? 0 : 1;",
            "Session local;\n    try { local.self(); } catch (const std::bad_weak_ptr&) { return 0; }\n    return 1;"), "")

    def test_task_programs(self):
        cases = [(0, 5, "0 7"), (1, 1, "10"),
                 (1, 5, "got 5 elements\ngot 1000 elements"),
                 (2, 4, "12.5664\n12"), (2, 5, "27.708"),
                 (4, 2, "захват\nосвобождение\nпоймано: сбой"), (4, 3, "-1\n-1")]
        for number, index, output in cases:
            with self.subTest(number=number, task=index):
                self.cpp(station(number)["tasks"][index]["code"], output)
        point = station(0)["tasks"][5]["code"].replace("x = x;", "this->x = x;")
        self.cpp(point, "4 7")
        array = station(1)["tasks"][6]["code"]
        self.cpp(array + """
#include <iostream>
#include <utility>
int main() {
    IntArray a(2); a.at(0)=7;
    IntArray b=a; b.at(0)=9;
    IntArray c=std::move(a);
    b=b; c=std::move(c);
    std::cout << a.getSize() << ' ' << b.getSize() << ' '
              << b.at(0) << ' ' << c.getSize() << ' ' << c.at(0);
}""", "0 2 9 2 7")
        counts = station(3)["tasks"][1]["code"]
        self.cpp(counts + """
#include <cassert>
int main() {
    auto result=countChars({'a','b','a','c','a'});
    assert(result.size()==3 && result.at('a')==3);
    assert(result.find('z')==result.end() && result.size()==3);
    try { result.at('z'); return 1; } catch (const std::out_of_range&) {}
    assert(result['z']==0 && result.size()==4);
}""".replace("#include <cassert>", "#include <cassert>\n#include <stdexcept>"), "")
        analyze = station(3)["tasks"][3]["code"]
        self.cpp(analyze + """
#include <cassert>
int main() {
    auto [n,a]=analyze({1,5,3,8,2},3); assert(n==2 && a==8);
    auto [m,b]=analyze({},3); assert(m==0 && !b);
    auto [k,c]=analyze({-5,-2},0); assert(k==0 && c==-2);
}""", "")
        stack = station(3)["tasks"][5]["code"]
        self.cpp(stack + """
#include <iostream>
int main() {
    Stack<int> s; s.push(1); s.push(2);
    const int& saved=s.top();
    (void)saved; s.pop();
    std::cout << s.size() << ' ' << s.top();
}""", "1 1")
        sentinel = station(4)["tasks"][3]["code"].replace("{10, 20, 30}", "{-1}").replace("safeGet(v, 1)", "safeGet(v, 0)")
        self.cpp(sentinel, "-1\n-1")

    def test_multifile_examples(self):
        fixtures = [("odr_example", ["left.cpp", "main.cpp"], "42 6"),
                    ("pimpl_example", ["client.cpp", "main.cpp"], "0 7")]
        for name, sources, output in fixtures:
            with self.subTest(fixture=name), tempfile.TemporaryDirectory(prefix="roadmap-multifile-") as directory:
                fixture = ROOT / "tests" / name
                binary = str(Path(directory) / "example")
                result = subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-pedantic",
                                         *[str(fixture / f) for f in sources], "-o", binary],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run([binary], text=True, capture_output=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), output)
        for name, section, offset, filenames in [
            ("odr_example", "translation-units-odr", 0, ["math.hpp", "left.cpp", "main.cpp"]),
            ("pimpl_example", "libraries-abi", 1, ["client.hpp", "client.cpp"]),
        ]:
            for i, filename in enumerate(filenames):
                self.assertEqual((ROOT / "tests" / name / filename).read_text(),
                                 code(5, section, offset+i) + "\n")


    def test_lifetime_and_owner_contracts(self):
        for number, section, index, output in [
            (1, "lifetime-storage", 1, "+ inner 7 - done"),
            (1, "lifetime-storage", 3, "+L L +P pass -P after -L"),
            (1, "ownership-contracts", 1, "7 consume 7 destroy false"),
            (1, "ownership-contracts", 2, "2 9 1 9"),
            (1, "ownership-contracts", 3, "Ada Grace"),
        ]:
            with self.subTest(section=section, index=index):
                self.cpp(code(number, section, index), output)
        for section, index in [("lifetime-storage", 0), ("lifetime-storage", 2),
                               ("ownership-contracts", 0)]:
            self.cpp(code(1, section, index))
        # The examples with dangling observers are never dereferenced.
        transfer = code(1, "ownership-contracts", 1)
        self.cpp(transfer.replace("consume(std::move(job));", "consume(job);"), valid=False)
        shared = code(1, "ownership-contracts", 2)
        self.cpp(shared.replace("// job.reset();", "job.reset();"), valid=False)

    def test_special_member_generation(self):
        self.cpp(code(1, "rule-of-five", 0))
        self.cpp(code(1, "rule-of-five", 1))  # Deliberate double-delete: compile only.
        zero = code(1, "rule-of-five", 2)
        self.cpp(zero, "7 9 0 7")
        self.cpp(zero.replace("// OwnerA third = second;", "OwnerA third = second;"), valid=False)
        owners = code(1, "rule-of-five", 3)
        self.cpp(owners)
        self.cpp(owners + "\nint main() { OwnerB a; OwnerB b(static_cast<OwnerB&&>(a)); }",
                 valid=False)
        self.cpp(owners + "\nint main() { OwnerC a; OwnerC b(static_cast<OwnerC&&>(a)); }", "")
        fallback = code(1, "rule-of-five", 4)
        self.cpp(fallback, "copy")
        deleted = fallback.replace("~CopyOnly() = default;",
                                   "~CopyOnly() = default;\n    CopyOnly(CopyOnly&&) = delete;")
        deleted = deleted.replace("static_assert(std::is_move_constructible_v<CopyOnly>);", "")
        self.cpp(deleted, valid=False)
        # A defaulted move defined as deleted is ignored, unlike explicit = delete.
        self.cpp("""
#include <iostream>
#include <utility>
struct Field {
    Field() = default;
    Field(const Field&) { std::cout << "copy"; }
    Field(Field&&) = delete;
};
struct Wrapper {
    Field field;
    Wrapper() = default;
    Wrapper(const Wrapper&) = default;
    Wrapper(Wrapper&&) = default;
};
int main() { Wrapper a; Wrapper b(std::move(a)); }
""", "copy")

    def test_rtti_contracts_and_quizzes(self):
        for index, output in [(0, "tcp not-tcp bad_cast"), (2, "closed 1"),
                              (3, "1 1 1 bad_typeid")]:
            with self.subTest(index=index):
                self.cpp(code(2, "rtti", index), output)
        self.cpp(code(2, "rtti", 1))
        self.cpp(code(2, "rtti", 0).replace("virtual ~Connection()", "~Connection()"), valid=False)
        self.cpp(code(2, "rtti", 2).replace("Reader* second = &memory;", "Reader* second = nullptr;"),
                 "closed 1")
        self.cpp(code(2, "rtti", 3).replace("virtual ~Base()", "~Base()"), "1 0 1")
        for number, kind, index, output in [
            (1, "advanced", 3, "1 12"),
            (1, "interview", 1, "CDM"),
            (1, "interview", 11, "C"),
            (2, "interview", 12, "1 0 1"),
        ]:
            with self.subTest(number=number, kind=kind, question=index):
                self.cpp(station(number)["quizzes"][kind][index]["q"].split("\n\n", 1)[1], output)

    def test_original_constructor_interview_variants(self):
        definitions = code(2, "interview-lifetime", 0)
        failed = "\n".join(["D()", "B()", "C()", "E()", "A()",
                            "~C()", "~B()", "~A()", "~D()"])
        success = "\n".join(["D()", "B()", "C()", "E()", "A()", "~E()",
                             "~C()", "~B()", "~A()", "~D()"])
        for index in [1, 2]:
            with self.subTest(throwing_main=index):
                self.cpp(definitions + "\n" + code(2, "interview-lifetime", index), failed)
        no_throw = definitions.replace('throw std::runtime_error("err");', "")
        self.cpp(no_throw + "\nint main() {\n" + code(2, "interview-lifetime", 3) + "\n}",
                 success + "\n" + success)
        start = definitions.index("struct B {")
        end = definitions.index("struct C {")
        member_failure = definitions[:start] + code(2, "interview-lifetime", 4) + "\n" + definitions[end:]
        self.cpp(member_failure + "\n" + code(2, "interview-lifetime", 1), "D()\nB()\n~D()")
        delegating = code(2, "interview-lifetime", 5)
        definition, body = delegating.split("\ntry ", 1)
        self.cpp("#include <iostream>\n" + definition + "\nint main() {\ntry " + body + "\n}",
                 "target\ndelegate\n~X")


    def test_template_class_and_views(self):
        self.cpp(code(3, "templates-class", 0), "7 hi")
        definitions = code(3, "templates-class", 0).split("\nint main()", 1)[0]
        owner = definitions + "\n" + code(3, "templates-class", 1)
        self.cpp(owner, "9")
        self.cpp(owner.replace("// auto duplicate = owner.copy();",
                               "auto duplicate = owner.copy();"), valid=False)
        self.cpp(definitions + """
#include <type_traits>
int main() {
    Box number{42};
    Box literal{"hi"};
    static_assert(std::is_same_v<decltype(number), Box<int>>);
    static_assert(std::is_same_v<decltype(literal), Box<const char*>>);
}
""", "")
        self.cpp(code(3, "templates-class", 2), "age 30 retries 3")
        for index, output in [(0, "10 5 12"), (1, "bat cat 3"), (2, "42 1 ready")]:
            with self.subTest(index=index):
                self.cpp(code(3, "non-owning-vocabulary", index), output)

    def test_meminfo_parser_boundaries(self):
        parser = code(4, "practical", 1)
        self.cpp(parser + "\n" + code(4, "practical", 2), "1024 256")
        self.cpp(parser + r"""
#include <cassert>
#include <limits>
#include <streambuf>

void rejects(const std::string& text, const std::string& message) {
    std::istringstream input(text);
    try { parseMeminfo(input); assert(false); }
    catch (const CollectorError& error) { assert(error.what() == message); }
}

// Deliver the valid prefix and then fail instead of reaching EOF.
class BrokenBuffer : public std::streambuf {
    std::string text_ = "MemTotal: 1024 kB\nMemAvailable: 256 kB\n";
public:
    BrokenBuffer() { setg(text_.data(), text_.data(), text_.data() + text_.size()); }
    int_type underflow() override { throw std::runtime_error("read failure"); }
};

int main() {
    const std::string available = "MemAvailable: 256 kB\n";
    for (const std::string invalid : {"-1", "+1", "-0", "12x", "99999999999999999999999"}) {
        rejects("MemTotal: " + invalid + " kB\n" + available, "meminfo: invalid number");
    }
    rejects("MemTotal: 0 kB\n" + available, "meminfo: total must be positive");
    rejects(available, "meminfo: missing required field");
    rejects("MemTotal: 1 kB\n", "meminfo: missing required field");
    rejects("MemTotal: 1 kB\nMemTotal: 2 kB\n" + available, "meminfo: duplicate field");
    for (const std::string invalid : {"MemTotal: 1024 MB\n", "MemTotal: 1024 kB extra\n",
                                      "MemTotal: kB\n", "MemTotal: 1024kB\n"}) {
        rejects(invalid + available, "meminfo: invalid field format");
    }
    std::istringstream valid("\nHugePages_Total: 0\nMemAvailable: 0 kB\nMemTotal: 1 kB  ");
    const auto values = parseMeminfo(valid); // Accept final line without a newline.
    assert(values.size() == 2 && values.at("MemTotal") == 1 && values.at("MemAvailable") == 0);

    std::istringstream upper("MemTotal: 9223372036854775807 kB\nMemAvailable: 0 kB\n");
    assert(parseMeminfo(upper).at("MemTotal") == std::numeric_limits<std::int64_t>::max());

    BrokenBuffer buffer;
    std::istream interrupted(&buffer);
    try { parseMeminfo(interrupted); assert(false); }
    catch (const CollectorError& error) {
        assert(std::string(error.what()) == "meminfo: read failed");
    }
    std::istringstream failed;
    failed.setstate(std::ios::failbit);
    try { parseMeminfo(failed); assert(false); }
    catch (const CollectorError& error) {
        assert(std::string(error.what()) == "meminfo: read failed");
    }
}
""", "")

    def test_sanitizer_configuration(self):
        import shutil

        def run(command):
            result = subprocess.run(command, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        with tempfile.TemporaryDirectory(prefix="roadmap-diagnostics-") as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(ROOT / "tests/build_example", source)
            # Generated test input, always obtained from the chapter.
            (source / "CMakeLists.txt").write_text(code(5, "tooling", 0) + "\n")
            for testing in ["ON", "OFF"]:
                with self.subTest(build_testing=testing):
                    build = root / testing
                    run(["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                         "-DCMAKE_BUILD_TYPE=Debug", "-DENABLE_SANITIZERS=ON",
                         "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-DBUILD_TESTING=" + testing])
                    commands = json.loads((build / "compile_commands.json").read_text())
                    self.assertEqual(len(commands), 3 if testing == "ON" else 2)
                    for entry in commands:
                        self.assertIn("-fsanitize=address,undefined", entry["command"])
                    log = run(["cmake", "--build", str(build), "--verbose"])
                    links = [line for line in log.splitlines() if " -o app " in line or " -o core_tests " in line]
                    self.assertEqual(len(links), 2 if testing == "ON" else 1, log)
                    for line in links:
                        self.assertIn("-fsanitize=address,undefined", line)
                    listing = run(["ctest", "--test-dir", str(build), "-N"])
                    self.assertIn("Total Tests: " + ("1" if testing == "ON" else "0"), listing)


    def test_cleanup_guarantees_and_transactions(self):
        for section, index, expected in [
            ("construction-cleanup", 0, "caught 0 1"),
            ("construction-cleanup", 1, "caught 1 0"),
            ("exception-safety", 0, "9 9 / 1 5"),
            ("transactional-updates", 0, "1 0 / 0 1"),
            ("transactional-updates", 1, "1 / 3 1 2 3"),
        ]:
            with self.subTest(section=section, index=index):
                self.cpp(code(4, section, index), expected)
        self.cpp(code(4, "exception-safety", 1) + """
#include <cassert>
int main() {
    int low = 1, high = 5;
    static_assert(noexcept(tryReplace(9, 3, low, high)));
    assert(!tryReplace(9, 3, low, high) && low == 1 && high == 5);
    assert(tryReplace(-3, -1, low, high) && low == -3 && high == -1);
}
""", "")

    def test_transaction_failure_boundaries(self):
        registry = code(4, "transactional-updates", 0).split("\nint main()", 1)[0]
        self.cpp(registry + """
#include <cassert>
int main() {
    Registry registry;
    registry.replace({"old"});
    for (const std::vector<std::string> bad : {
            std::vector<std::string>{""},
            std::vector<std::string>{"new", "late", "new"}}) {
        try { registry.replace(bad); assert(false); }
        catch (const std::invalid_argument&) {}
        assert(registry.contains("old") && !registry.contains("new"));
    }
    registry.replace({});
    assert(!registry.contains("old"));
    registry.replace({"one", "two"});
    assert(registry.contains("one") && registry.contains("two"));
}
""", "")
        rollback = code(4, "transactional-updates", 1).split("\nint main()", 1)[0]
        self.cpp(rollback + """
#include <cassert>
void early(std::vector<int>& values) {
    AppendTransaction transaction{values};
    transaction.add(9);
    return; // Normal return does not commit automatically.
}
int main() {
    std::vector<int> values{1};
    early(values);
    assert((values == std::vector<int>{1}));
    {
        AppendTransaction transaction{values};
        try { transaction.add(9); throw 1; } catch (int) {}
        // No propagating exception, but there was no commit either.
    }
    assert((values == std::vector<int>{1}));
    appendPair(values, false);
    assert((values == std::vector<int>{1,2,3}));
}
""", "")
        probe = code(4, "construction-cleanup", 1)
        self.cpp(probe.replace("throw 1;", "/* normal exit */"), "0 0")
        cleanup = code(4, "construction-cleanup", 0)
        self.cpp(cleanup.replace("Output fallback{true", "Output fallback{false"), "caught 0 0")

    def test_exception_quiz_variants(self):
        for index, expected in [(4, "inner outer 1"), (6, "9 5"), (7, "1 1")]:
            with self.subTest(index=index):
                self.cpp(station(4)["quizzes"]["interview"][index]["q"].split("\n\n", 1)[1], expected)
        nested = station(4)["quizzes"]["interview"][4]["q"].split("\n\n", 1)[1]
        throwing = nested.replace('try { throw 2; }\n        catch (int) { std::cout << "inner "; }', 'throw 2;')
        # A normal throwing destructor declared noexcept(false) may reach the caller.
        normal = throwing.replace("~Guard() noexcept", "~Guard() noexcept(false)")
        self.cpp(normal.replace("throw 1;", 'std::cout << "work ";'), "work outer 2")
        # Controlled terminate handler avoids a core dump and makes the outcome observable.
        for source in [throwing, normal]:
            source = "#include <cstdlib>\n#include <exception>\n" + source
            source = source.replace("int main() {", "int main() { std::set_terminate([] { std::_Exit(86); });")
            self.cpp(source, "", expected_exit=86)

    def test_presets_configure_build_and_test(self):
        import shlex
        import shutil

        with tempfile.TemporaryDirectory(prefix="roadmap-presets-") as directory:
            source = Path(directory) / "source"
            shutil.copytree(ROOT / "tests/build_example", source)
            # This is generated test input, not a second hand-maintained recipe.
            presets = code(5, "build-reproducibility", 0)
            self.assertEqual(json.loads(presets)["version"], 2)
            (source / "CMakePresets.json").write_text(presets + "\n")
            for index in [1, 2]:
                for command in code(5, "build-reproducibility", index).splitlines():
                    result = subprocess.run(shlex.split(command), cwd=source,
                                            text=True, capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if command.startswith("ctest"):
                        self.assertIn("100% tests passed", result.stdout)
            self.assertTrue((source / "build/dev/compile_commands.json").is_file())
            for tree in ["dev", "check"]:
                result = subprocess.run([str(source / "build" / tree / "app")],
                                        text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "42")
            again = subprocess.run(["cmake", "--build", "--preset", "dev"], cwd=source,
                                   text=True, capture_output=True, timeout=60)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("no work to do", again.stdout)



    def test_constructor_handlers_and_external_effects(self):
        source = code(4, "constructor-transaction", 0)
        self.cpp(source, "A B ~A ctor-catch outer")
        self.cpp(source.replace("        throw;", ""), "A B ~A ctor-catch outer")
        self.cpp(source.replace("Session session{true}", "Session session{false}"),
                 "A B body ~Session ~B ~A")
        self.cpp(source.replace("        throw;", "        return;"), valid=False)
        self.cpp(source.replace("Session session{true};", "auto session = new Session(true); delete session;"),
                 "A B ~A ctor-catch outer")
        external = code(4, "external-effects-guarantees", 0)
        self.cpp(external, "0 1")
        self.cpp(external.replace('        throw std::runtime_error("reply lost");', ""), "1 1")
        question = next(q for q in station(4)["quizzes"]["advanced"]
                        if q["q"].startswith("Чем закончится создание Session"))
        self.cpp(question["q"].split("\n\n", 1)[1], "MSmCO")


if __name__ == "__main__":
    unittest.main()
