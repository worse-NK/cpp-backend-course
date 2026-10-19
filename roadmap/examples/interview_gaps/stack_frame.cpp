struct Pair { unsigned long first, second; };
extern void observe(const Pair*);

unsigned long inspect(unsigned long x) {
    Pair p{x, x + 1};
    observe(&p);
    return p.second;
}
int answer() {
    int local = 42;
    return local;
}
