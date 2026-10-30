"""Check route destinations and the explicitly simplified mathematical examples.

These are arithmetic/model checks, not benchmarks, a queueing simulation of a
production service, or an implementation of a monitoring system's quantiles.
"""
from fractions import Fraction
from html.parser import HTMLParser
import math
import unittest

from test_expanded_examples import station


class RouteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('class') == 'learning-route-link':
            self.links.append(attrs)


class LearningBridges(unittest.TestCase):
    def test_all_routes_have_readiness_answer_and_valid_links(self):
        docs = {n: station(n) for n in [*range(9), '5-linux', '7-netlab', '7-traffic']}
        by_file = {d['meta']['sourceFile']: d for d in docs.values()}
        for n, data in docs.items():
            route = next(s for s in data['theory'] if s['id'] == 'learning-route')
            prose = '\n'.join(b.get('html', '') for b in route['blocks'])
            self_checks = [b for b in route['blocks'] if b['type'] == 'self-check']
            if self_checks:
                self.assertTrue(all(b['prompt'].strip() and b['answer'].strip() for b in self_checks))
            else:
                self.assertIn('Проверка перед стартом', prose)
                self.assertIn('Сверь рассуждение', prose)
            parser = RouteLinks()
            parser.feed(prose)
            self.assertGreaterEqual(len(parser.links), len(data['substations']) + 1)
            for link in parser.links:
                path, ref = link['href'].split('#section=')
                self.assertIn(path, by_file)
                self.assertIn(ref, {s['id'] for s in by_file[path]['theory']})
                self.assertEqual(link['target'], '_blank')
                self.assertIn('noopener', link['rel'].split())

    def test_station6_first_pass_defers_formal_model(self):
        route = station(6)['theory'][0]
        block = next(b for b in route['blocks'] if 'Первый проход: точные' in b.get('html', ''))
        parser = RouteLinks()
        parser.feed(block['html'])
        refs = [a['href'].split('#section=')[1] for a in parser.links]
        for early in ('mutex-basics', 'condition-variable', 'future-promise'):
            self.assertLess(refs.index(early), refs.index('memory-locations-conflicts'))
            self.assertLess(refs.index(early), refs.index('atomic'))
        self.assertLess(refs.index('atomic'), refs.index('shutdown-backpressure'))

    def test_geometric_growth_amortized_cost(self):
        def costs(n):
            size, capacity, moved = 0, 1, 0
            for _ in range(n):
                if size == capacity:
                    moved += size
                    capacity *= 2
                size += 1
            return moved + n
        self.assertEqual(costs(8), 15)
        self.assertEqual(costs(9), 24)
        self.assertEqual(costs(9) - costs(8), 9)
        for n in range(1, 257):
            self.assertLess(costs(n), 3 * n)
        self.assertEqual(sum(range(8)) + 8, 36)

    def test_halving_counts(self):
        for power in (4, 10, 20):
            candidates, steps = 2 ** power, 0
            while candidates > 1:
                candidates //= 2
                steps += 1
            self.assertEqual(steps, power)

    def test_little_identity_for_complete_trace(self):
        requests = [(0, 2), (1, 4), (3, 6)]
        occupancies = [sum(a <= t < b for a, b in requests) for t in range(6)]
        self.assertEqual(occupancies, [1, 2, 1, 2, 1, 1])
        person_time = sum(b-a for a, b in requests)
        self.assertEqual(person_time, sum(occupancies))
        average_number = Fraction(person_time, 6)
        rate = Fraction(len(requests), 6)
        average_time = Fraction(person_time, len(requests))
        self.assertEqual(average_number, rate * average_time)
        self.assertEqual(average_number, Fraction(4, 3))
        self.assertEqual((100 * Fraction(200, 1000), 100 * Fraction(150, 1000)), (20, 15))

    def test_arbitrary_window_requires_boundary_accounting(self):
        # Same trace, window [1,3): B is unfinished at the right boundary.
        measured_number = Fraction(2 + 1, 2)
        completed_rate = Fraction(1, 2)  # A is the only completion.
        completed_mean_lifetime = 2
        self.assertNotEqual(measured_number, completed_rate * completed_mean_lifetime)
        capacity = 4 / Fraction(20, 1000)
        self.assertEqual(capacity, 200)
        self.assertEqual(Fraction(500, 300-capacity), 5)

    def test_network_units_and_window_bound(self):
        rtt = Fraction(40, 1000)
        self.assertEqual(1_000_000_000 * rtt / 8, 5_000_000)
        window = 256 * 1024
        rate = window / rtt
        self.assertEqual(rate, 6_553_600)
        self.assertEqual(rate / 1024**2, Fraction(25, 4))
        self.assertEqual(rate * 8, 52_428_800)
        self.assertEqual(window / (2 * rtt), rate / 2)

    @staticmethod
    def percentile(values, p):
        # Exact rational rank, unlike a monitoring library's approximation.
        ordered = sorted(values)
        return ordered[math.ceil(p * len(ordered))-1]

    def test_percentile_is_not_mean_or_mean_of_percentiles(self):
        p99 = Fraction(99, 100)
        values = [10] * 99 + [1010]
        self.assertEqual(sum(values) / len(values), 20)
        self.assertEqual(self.percentile(values, p99), 10)
        a, b = [10] * 1000, [1000] * 10
        self.assertEqual((self.percentile(a, p99) + self.percentile(b, p99)) / 2, 505)
        self.assertEqual(self.percentile(a+b, p99), 10)

    def test_percentile_of_sum_is_not_sum_of_percentiles(self):
        a, b = [1, 100], [100, 1]
        p99 = Fraction(99, 100)
        self.assertEqual(self.percentile(a, p99) + self.percentile(b, p99), 200)
        self.assertEqual(self.percentile([x+y for x,y in zip(a,b)], p99), 101)

    def test_math_lessons_have_questions_and_tasks(self):
        for n, ref, title in [
            (3, 'container-cost-model', 'Дорогой шаг внутри дешёвой серии'),
            (6, 'pool-sizing-overload', 'Одна граница и правильные единицы'),
            (7, 'tcp-capacity-loss-control', 'Раздели полосу, окно и задержку'),
            (8, 'observations', 'Процентиль сервиса — не среднее двух процентилей'),
        ]:
            data = station(n)
            section = next(s for s in data['theory'] if s['id'] == ref)
            # Readable editions may replace the old literal heading. Keep the
            # teaching contract: a revealable reasoning check, questions in
            # each bank, and the dedicated application task below.
            self.assertTrue(any(b['type'] == 'self-check' and b['prompt'].strip()
                                and b['answer'].strip() for b in section['blocks']))
            for kind in ('basic', 'advanced', 'interview'):
                self.assertTrue(any(ref in q['theoryRefs'] for q in data['quizzes'][kind]))
            task = next(t for t in data['tasks'] if t['title'] == title)
            self.assertEqual(task['substation'], section['substation'])


if __name__ == '__main__':
    unittest.main()
