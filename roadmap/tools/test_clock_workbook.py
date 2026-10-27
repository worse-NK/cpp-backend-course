"""Compile the actual station-0 worked solution and check its contract."""
import unittest
from test_expanded_examples import station
import test_expanded_examples


class ClockWorkbook(unittest.TestCase):
    check_cpp = test_expanded_examples.ExpandedExamples.check_cpp

    @staticmethod
    def source():
        section = next(s for s in station(0)['theory'] if s['id'] == 'clock-worked-example')
        return next(b['code'] for b in section['blocks']
                    if b['type'] == 'code' and b['code'].startswith('#include'))

    def test_printed_walkthrough(self):
        self.check_cpp(self.source(), '\n'.join([
            'start: 0:0:0', 'set: true', 'original: 23:59:59',
            'copy: 23:59:58', 'midnight: 0:0:0', 'bad set: false',
            'after refusal: 0:0:0', 'copy after tick: 23:59:59',
            'copy after assignment: 0:0:0']))

    def test_all_day_transitions_and_refusals(self):
        source = self.source().split('int main()', 1)[0]
        self.check_cpp(source + r'''
int main() {
    Clock c;
    for (long t = 0; t < 86400; ++t) {
        if (!c.try_set(t / 3600, t / 60 % 60, t % 60)) return 1;
        Clock original = c;
        c.tick();
        const long next = (t + 1) % 86400;
        if (c.hours() != next / 3600 || c.minutes() != next / 60 % 60 ||
            c.seconds() != next % 60) return 2;
        if (original.hours() != t / 3600 || original.minutes() != t / 60 % 60 ||
            original.seconds() != t % 60) return 3;
    }
    c.try_set(9, 30, 15);
    const int bad[][3] = {{-1, 30, 15}, {24, 30, 15}, {12, -1, 15},
                         {12, 60, 15}, {12, 40, -1}, {12, 40, 60}};
    for (const auto& values : bad) {
        if (c.try_set(values[0], values[1], values[2])) return 4;
        if (c.hours() != 9 || c.minutes() != 30 || c.seconds() != 15) return 5;
    }
    Clock assigned;
    assigned = c;
    assigned.tick();
    if (assigned.seconds() != 16 || c.seconds() != 15) return 6;
    const Clock frozen = c;
    if (frozen.hours() != 9) return 7;
    std::cout << "OK";
}
''', 'OK')

    def test_copy_and_alias_exercise(self):
        source = self.source().split('int main()', 1)[0]
        self.check_cpp(source + r'''
int main() {
    Clock a;
    a.try_set(5, 59, 59);
    Clock b = a;
    b.tick();
    std::cout << a.try_set(6, 0, 60) << ' ';
    print("a: ", a); print("b: ", b);
    Clock& alias = a;
    alias.tick();
    std::cout << a.try_set(6, 0, 60) << ' ';
    print("alias: ", alias);
}
''', '0 a: 5:59:59\nb: 6:0:0\n0 alias: 6:0:0')

    def test_last_section_and_route_link(self):
        data = station(0)
        self.assertEqual(data['theory'][-1]['id'], 'clock-worked-example')
        self.assertIn('#section=clock-worked-example', str(data['theory'][0]))


if __name__ == '__main__':
    unittest.main()
