#include <iostream>

struct Part {
    Part() { std::cout << "Part "; }
    ~Part() { std::cout << "~Part "; }
};
struct Job {
    Part part;
    int id;
    explicit Job(int value) : part(), id(value) {
        std::cout << "Job" << id << ' ';
    }
    ~Job() { std::cout << "~Job "; }
};
void work(bool early) {
    Job job{7};
    std::cout << "work ";
    if (early) return;
    std::cout << "tail ";
}
int main() {
    std::cout << "before ";
    work(true);
    std::cout << "after\n";
}
