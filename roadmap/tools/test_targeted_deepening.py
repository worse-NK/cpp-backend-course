"""Executable checks and small state models for the targeted October 6 additions.

These models check the worked examples, not a production executor/cache/server.
No deliberately deadlocked process or data-race example is executed.
"""
from collections import deque
import unittest

from test_expanded_examples import station
import test_remaining_examples


class TargetedDeepening(unittest.TestCase):
    cpp = test_remaining_examples.RemainingExamples.cpp

    def test_future_timeout_does_not_cancel_producer(self):
        self.cpp(r'''
#include <future>
#include <chrono>
#include <iostream>
int main() {
    std::promise<int> producer;
    auto result = producer.get_future();
    std::cout << (result.wait_for(std::chrono::seconds(0)) ==
                  std::future_status::timeout) << ' ';
    producer.set_value(42);
    std::cout << result.get();
}
''', '1 42')

    def test_nested_wait_witness_for_any_fixed_pool_size(self):
        # An allowed schedule: every worker starts a parent before any child.
        for size in range(1, 9):
            workers = {i: ('parent', i) for i in range(size)}
            ready = deque()
            waits = {}
            for worker in workers:
                child = ('child', worker)
                ready.append(child)
                waits[worker] = child
            self.assertEqual(len(ready), size)
            self.assertEqual(set(waits), set(workers))
            self.assertFalse(any(worker not in waits for worker in workers))
            self.assertTrue(all(child in ready for child in waits.values()))
            # A wait notification does not create an executor or a result.
            self.assertEqual(set(waits.values()), set(ready))

    def test_continuations_release_executor_slots(self):
        # Finite, nonblocking tasks: each parent queues a child and returns;
        # each child queues a continuation and returns. Even one worker suffices.
        for count in (1, 2, 8, 100):
            ready = deque(('parent', i) for i in range(count))
            completed = set()
            steps = 0
            while ready:
                kind, i = ready.popleft()
                if kind == 'parent': ready.append(('child', i))
                elif kind == 'child': ready.append(('continuation', i))
                else: completed.add(i)
                steps += 1
                self.assertLessEqual(steps, 3 * count)
            self.assertEqual(completed, set(range(count)))
            self.assertEqual(steps, 3 * count)

    def test_buffer_budget_and_hysteresis_timeline(self):
        q, reserved, paused = 32, 0, False
        totals = [q]
        def update_pause(total, previous):
            if previous: return total > 64
            return total >= 128
        for _ in ('A', 'B'):
            self.assertFalse(paused)
            self.assertLessEqual(q + reserved + 64, 256)
            reserved += 64
            paused = update_pause(q + reserved, paused)
            totals.append(q + reserved)
        self.assertTrue(paused)
        # A converts its own reservation to a smaller live block.
        reserved -= 64
        q += 48
        totals.append(q + reserved)
        # Partial send changes unsent bytes, not ownership of the whole block.
        old_unsent = 32 - 20
        self.assertEqual(old_unsent, 12)
        totals.append(q + reserved)
        for freed in (32, 48):
            q -= freed
            paused = update_pause(q + reserved, paused)
            totals.append(q + reserved)
            self.assertEqual(paused, freed == 32)
        self.assertEqual(totals, [32, 96, 160, 144, 144, 112, 64])
        self.assertEqual((q, reserved, paused), (0, 64, False))
        # B still owns a reservation; finishing B merely changes its category.
        reserved -= 64
        q += 64
        self.assertEqual((q, reserved), (64, 0))

    def test_local_and_global_admission_is_one_decision(self):
        local, global_used = 0, 160
        before = (local, global_used)
        amount = 64
        allowed = local + amount <= 256 and global_used + amount <= 192
        if allowed:
            local += amount
            global_used += amount
        self.assertFalse(allowed)
        self.assertEqual((local, global_used), before)
        # A smaller reservation can fit exactly; no partial reservation leaks.
        amount = 32
        self.assertTrue(local + amount <= 256 and global_used + amount <= 192)
        local += amount
        global_used += amount
        self.assertEqual((local, global_used), (32, 192))

    def test_age_calculation_and_freshness_boundary(self):
        def age(request, response, date, incoming_age, now):
            initial = max(max(0, response-date), incoming_age + response-request)
            return initial + now-response
        self.assertEqual(age(100, 102, 80, 20, 130), 50)
        self.assertEqual(age(100, 102, 80, 20, 140), 60)
        for residence, fresh in ((0, True), (30, True), (39, True), (40, False)):
            self.assertEqual(20 + residence < 60, fresh)
        # A future Date must not produce a negative initial age.
        self.assertEqual(age(100, 102, 110, 0, 102), 2)

    def test_cache_variant_and_validation_are_separate(self):
        # Deliberately limited model: exact language values, public full GET,
        # no no-cache request and no authorization/personalization.
        cached = dict(language='ru', etag='"help-ru-7"', body='Справка',
                      max_age=60, initial_age=20)
        def reusable(language, elapsed):
            return (cached['language'] == language and
                    cached['initial_age'] + elapsed < cached['max_age'])
        self.assertTrue(reusable('ru', 30))
        self.assertFalse(reusable('ru', 40))
        self.assertFalse(reusable('en', 10))
        old_body = cached['body']
        # Suitable upstream 304: update metadata, retain the corresponding body.
        cached.update(max_age=120, initial_age=0)
        self.assertEqual(cached['body'], old_body)
        self.assertTrue(reusable('ru', 119))
        self.assertFalse(reusable('ru', 120))
        browser_status = 200  # Its request was unconditional.
        self.assertEqual((browser_status, cached['body']), (200, 'Справка'))

    def test_added_questions_point_to_expanded_lessons(self):
        refs = {6: 'thread-pool-contract', 7: 'event-loop-buffers-backpressure',
                8: 'cache-validation'}
        for number, ref in refs.items():
            data = station(number)
            section = next(s for s in data['theory'] if s['id'] == ref)
            # The editorial pass replaces the former repeated heading with
            # a concrete retrieval question and an answer the reader reveals.
            # Keep checking the learning element, not its old stock phrase.
            checks=[b for b in section['blocks'] if b['type']=='self-check']
            self.assertTrue(checks,ref)
            self.assertTrue(all(b['prompt'].strip() and b['answer'].strip()
                                for b in checks),ref)
            prefixes = {
                6: ['Два работника пула заняты', 'В фиксированном пуле каждый',
                    'Очередь ограниченного пула полна.', 'Родитель получил timeout'],
                7: ['Очередь ответов пуста', 'Бюджет памяти равен Q+R:',
                    'Суммарный бюджет памяти Q+R=144', 'У сессии свободен локальный'],
                8: ['Публичный ответ /help на русском', 'Возраст ответа при получении кэшем',
                    'Обычный GET браузера попал', 'Запрос ушёл в t=100'],
            }
            questions = [q for qs in data['quizzes'].values() for q in qs]
            for prefix in prefixes[number]:
                matched = [q for q in questions if q['q'].startswith(prefix)]
                self.assertEqual(len(matched), 1, prefix)
                self.assertEqual(matched[0]['theoryRefs'], [ref])
                self.assertEqual(matched[0]['substation'], section['substation'])
            titles = {
                6: 'Два свободных мьютекса и ни одного свободного работника',
                7: 'Проследи резерв до освобождения буфера',
                8: 'Один URL, два языка и два разных статуса',
            }
            task = next(t for t in data['tasks'] if t['title'] == titles[number])
            self.assertEqual(task['substation'], section['substation'])


if __name__ == '__main__':
    unittest.main()
