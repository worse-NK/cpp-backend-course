"""Concrete examples and integration guards for station 3's editorial pass.

Execution checks examples, not the portability of every C++ implementation or
the readability of all prose. Language/API claims still need primary sources.
"""
import json
from pathlib import Path
import unittest

from test_cpp_editorial_audit import ProseParser
import test_expanded_examples

ROOT = Path(__file__).resolve().parents[1]


class StationThreeEditorial(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "content/station3.json").read_text())
        cls.sections = {s["id"]: s for s in cls.data["theory"]}

    def code_with(self, section, marker):
        found = [b["code"] for b in self.sections[section]["blocks"]
                 if b["type"] == "code" and marker in b["code"]]
        self.assertEqual(len(found), 1, (section, marker))
        return found[0]

    def test_section_addresses_and_progress_key_are_stable(self):
        self.assertEqual(list(self.sections), [
            "learning-route", "what-is-stl", "vector", "allocation-containers",
            "map-set", "container-cost-model", "associative-deep",
            "unordered-contract", "invalidation-erasure",
            "sequence-container-topology", "container-decision", "iterators",
            "algorithms", "iterator-categories-ranges", "algorithm-pipeline",
            "interview-algorithm-invariants", "interview-sequence-workbook",
            "bit-mask-workbook", "subtree-sets-workbook", "graph-copy-workbook",
            "rle-workbook", "comparator-contract", "templates", "templates-class",
            "template-compilation", "templates-deep", "constant-evaluation",
            "sfinae-and-constraints", "callables-and-invoke",
            "template-instantiation-cost", "modern-tools", "non-owning-vocabulary",
            "ranges-lifetime", "lru-window-generations", "sliding-window-workbook",
            "generation-storage", "fixed-pool-workbook", "request-memory-arena",
            "frequency-final-workbook", "summary",
        ])
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station3_progress_v1")

    def test_templates_in_self_checks_are_visible_not_html(self):
        for section in self.sections.values():
            for index, block in enumerate(section["blocks"]):
                if block["type"] != "self-check":
                    continue
                for field in ("prompt", "answer"):
                    with self.subTest(section=section["id"], block=index, field=field):
                        parser = ProseParser()
                        parser.feed(block[field])
                        self.assertEqual(parser.unknown, [])

    def test_ordinary_vector_is_shown_before_bool_proxy(self):
        regular = self.code_with("vector", "results.push_back(30)")
        proxy = self.code_with("vector", "auto access = bits[0]")
        blocks = [b["code"] for b in self.sections["vector"]["blocks"]
                  if b["type"] == "code"]
        self.assertLess(blocks.index(regular), blocks.index(proxy))
        self.check_cpp(regular, "3 30")
        self.check_cpp(proxy, "1 0")

    def test_clear_and_swap_are_not_the_same_operation(self):
        self.check_cpp(self.code_with("sequence-container-topology",
                                      "values.swap(empty)"), "0 1 1")

    def test_map_access_does_not_need_default_constructor_but_brackets_do(self):
        complete = self.code_with("associative-deep", "struct Connection")
        prefix = complete.split("\nint main()", 1)[0]
        self.check_cpp(prefix + r'''
int main() {
    std::map<std::string, Connection> pool;
    pool.try_emplace("primary", 80);
    std::cout << pool.at("primary").port;
}
''', "make 80 80")
        self.check_cpp(prefix + r'''
int main() {
    std::map<std::string, Connection> pool;
    pool.try_emplace("primary", 80);
    return pool["primary"].port;
}
''', valid=False)

    def test_map_comparison_can_accept_a_different_lookup_type(self):
        fragment = self.code_with("associative-deep", 'counters.find("requests")')
        self.check_cpp("#include <functional>\n#include <map>\n#include <string>\n"
                       "#include <cassert>\nint main() {\n" + fragment +
                       "\nassert(it != counters.end() && it->second == 1);\n}", "")

    def test_deque_edge_insertion_preserves_reference(self):
        # Never use an iterator invalidated by push_front.
        self.check_cpp(r'''
#include <cassert>
#include <deque>
int main() {
    std::deque<int> values{10, 20};
    int& first = values.front();
    values.push_front(5);
    assert(first == 10 && &first == &values[1]);
    first = 17;
    assert(values[1] == 17);
}
''', "")

    def test_collisions_do_not_replace_equality(self):
        self.check_cpp(self.code_with("unordered-contract", "struct ConstantHash"),
                       "2 70 90")

    def test_doubling_model_counts_and_boundaries(self):
        # This models the explicitly stated exercise, not std::vector capacity.
        costs, capacity = [], 1
        for size in range(100):
            moved = size if size == capacity else 0
            if moved:
                capacity *= 2
            costs.append(1 + moved)
        self.assertEqual(sum(costs[:8]), 15)
        self.assertEqual(costs[8], 9)
        self.assertEqual(sum(costs[:9]), 24)
        for n in range(1, 101):
            self.assertLess(sum(costs[:n]), 3 * n)

    def test_comparator_counterexample_without_running_sort(self):
        question = self.data["quizzes"]["interview"][3]
        self.assertIn("A=(0,0), B=(3,-1), C=(2,2)", question["q"])
        self.check_cpp(r'''
#include <cassert>
#include <iostream>
struct Point { int x, y; };
int main() {
    auto comp = [](Point a, Point b) { return a.x < b.x && a.y < b.y; };
    auto equiv = [&](Point a, Point b) { return !comp(a,b) && !comp(b,a); };
    const Point a{0,0}, b{3,-1}, c{2,2};
    assert(!comp(a,a) && comp(a,c) && !comp(c,a));
    std::cout << equiv(a,b) << ' ' << equiv(b,c) << ' ' << equiv(a,c);
}
''', "1 1 0")

    def test_range_constraint_checks_the_const_parameter(self):
        question = self.data["quizzes"]["interview"][15]
        self.assertEqual(question["options"][question["answer"]],
                         "std::ranges::input_range<const R>")
        source = r'''
#include <iostream>
#include <ranges>
#include <vector>
template<class R> requires std::ranges::input_range<const R>
int sum(const R& range) {
    int result = 0;
    for (int value : range) result += value;
    return result;
}
int main() {
    std::vector<int> values{1,2};
    auto filtered = values | std::views::filter([](int x) { return x > 0; });
    static_assert(std::ranges::input_range<decltype(filtered)>);
    static_assert(!std::ranges::input_range<const decltype(filtered)>);
    std::cout << sum(values);
}
'''
        self.check_cpp(source, "3")
        self.check_cpp(source.replace("sum(values)", "sum(filtered)"), valid=False)


if __name__ == "__main__":
    unittest.main()
