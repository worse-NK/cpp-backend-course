#include <algorithm>
#include <cstddef>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

enum class Kind { write, read };

struct Operation {
    Kind kind;
    int value;   // written value, or value returned by a completed read
    int start;   // ordinal event number in the prepared history
    int finish;
};

bool search(const std::vector<Operation>& ops, unsigned used, int value) {
    const unsigned all = (1U << ops.size()) - 1U;
    if (used == all) {
        return true;
    }

    for (std::size_t i = 0; i < ops.size(); ++i) {
        const unsigned bit = 1U << i;
        if ((used & bit) != 0U) {
            continue;
        }

        bool predecessor_missing = false;
        for (std::size_t j = 0; j < ops.size(); ++j) {
            if (ops[j].finish < ops[i].start &&
                (used & (1U << j)) == 0U) {
                predecessor_missing = true;
                break;
            }
        }
        if (predecessor_missing) {
            continue;
        }
        if (ops[i].kind == Kind::read && ops[i].value != value) {
            continue;
        }

        const int next_value =
            ops[i].kind == Kind::write ? ops[i].value : value;
        if (search(ops, used | bit, next_value)) {
            return true;
        }
    }
    return false;
}

bool is_linearizable(const std::vector<Operation>& ops) {
    if (ops.size() > 8U) {
        throw std::invalid_argument("at most 8 completed operations");
    }
    std::vector<int> events;
    for (const Operation& op : ops) {
        if (op.start < 0 || op.start >= op.finish) {
            throw std::invalid_argument("invalid operation interval");
        }
        events.push_back(op.start);
        events.push_back(op.finish);
    }
    std::sort(events.begin(), events.end());
    if (std::adjacent_find(events.begin(), events.end()) != events.end()) {
        throw std::invalid_argument("event numbers must be distinct");
    }
    return search(ops, 0U, 0); // this model starts with register value 0
}

int main() {
    struct Case {
        const char* name;
        std::vector<Operation> operations;
        bool expected;
    };
    const std::vector<Case> cases{
        {"fresh", {{Kind::write, 1, 0, 4}, {Kind::read, 1, 5, 6}}, true},
        {"stale", {{Kind::write, 1, 0, 4}, {Kind::read, 0, 5, 6}}, false},
        {"overlap", {{Kind::write, 1, 0, 10}, {Kind::read, 0, 4, 5}}, true},
        {"new_then_old", {{Kind::write, 1, 0, 10},
                          {Kind::read, 1, 2, 3},
                          {Kind::read, 0, 4, 5}}, false}
    };

    for (const Case& test : cases) {
        const bool actual = is_linearizable(test.operations);
        std::cout << test.name << ": " << (actual ? "yes" : "no") << '\n';
        if (actual != test.expected) {
            std::cerr << "unexpected result\n";
            return 1;
        }
    }

    bool rejected = false;
    try {
        (void)is_linearizable({{Kind::read, 0, 3, 3}});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    if (!rejected || !is_linearizable({})) {
        std::cerr << "validation check failed\n";
        return 1;
    }
    std::cout << "all checks passed\n";
}
