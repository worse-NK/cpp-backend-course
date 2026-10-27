"""Regression guards for the concrete novice audit; not a readability score."""
import copy
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]

class NoviceRevision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {n: json.loads((ROOT / f'content/station{n}.json').read_text()) for n in range(9)}

    def test_reading_path_dependencies(self):
        d = self.data[6]
        route = d['readingOrder']
        self.assertCountEqual(route, [s['id'] for s in d['theory']])
        for before, after in [('race-condition','mutex-basics'),
                              ('condition-variable','happens-before'),
                              ('future-state-lifecycle','happens-before'),
                              ('atomic','wait-state-workbook'),
                              ('memory-order','wait-state-workbook'),
                              ('concurrent-api','thread-pool-contract')]:
            self.assertLess(route.index(before),route.index(after))
        for bad_route in (route[:-1],route+[route[0]],route[:-1]+['missing']):
            bad = copy.deepcopy(d); bad['readingOrder'] = bad_route
            with self.assertRaises(ValueError): validate(bad,ROOT/'content/station6.json')

    def test_no_length_shortcut_in_revised_banks(self):
        # Warning signal only: passing this does not prove good distractors.
        revised = [(n, 'interview') for n in (4,5,6,7)]
        revised += [(n, 'basic') for n in (4,5,6,7)]
        revised += [(n, 'advanced') for n in (4,5,6,7)]
        for n, kind in revised:
            qs=self.data[n]['quizzes'][kind]
            for extreme in (min,max):
                hits=0
                for q in qs:
                    lengths=[len(re.sub('<[^>]+>','',o)) for o in q['options']]
                    target=extreme(lengths)
                    hits += lengths[q['answer']]==target and lengths.count(target)==1
                self.assertLessEqual(hits/len(qs),.5,(n,kind,extreme.__name__,hits))

    def test_revised_conditions_are_self_contained(self):
        pipe = self.data[5]['quizzes']['advanced'][31]
        self.assertNotIn('предыдущ', pipe['q'])
        for detail in ('пустой буфер', 'пишущий конец открыт', 'O_NONBLOCK', 'ненулевым'):
            self.assertIn(detail, pipe['q'])
        thread = self.data[6]['quizzes']['basic'][23]
        self.assertIn('std::thread', thread['q'])
        self.assertIn('promise', thread['q'])
        self.assertIn('set_exception', thread['options'][thread['answer']])
        dns = self.data[7]['quizzes']['basic'][8]
        self.assertIn('политики выдачи устаревших данных нет', dns['q'])
        self.assertIn('открыто исправное TCP-соединение', dns['q'])
        write = self.data[7]['quizzes']['basic'][41]
        self.assertIn('shared_ptr', write['q'])
        self.assertIn('строку до завершения не меняют', write['q'])

    def test_intro_exception_example_and_constructor_handler(self):
        intro=next(s for s in self.data[4]['theory'] if s['id']=='exceptions-basics')
        source=next(b['code'] for b in intro['blocks'] if b['type']=='code')
        q=self.data[4]['quizzes']['advanced'][21]
        ctor=q['q'].split('\n\n', 1)[1]
        for code, expected in ((source, 'ошибка: деление на ноль'),
                               (ctor, q['options'][q['answer']])):
            with tempfile.TemporaryDirectory(prefix='novice-exceptions-') as tmp:
                out=Path(tmp)/'example'
                subprocess.run(['g++','-std=c++20','-x','c++','-','-o',str(out)],input=code,text=True,check=True,capture_output=True)
                self.assertEqual(subprocess.check_output([str(out)],text=True),expected)

    def test_nonblocking_pipe_distinguishes_empty_from_eof(self):
        import os
        import errno
        read_fd, write_fd = os.pipe()
        try:
            os.set_blocking(read_fd, False)
            with self.assertRaises(BlockingIOError) as raised:
                os.read(read_fd, 10)
            self.assertEqual(raised.exception.errno, errno.EAGAIN)
            os.write(write_fd, b'ab')
            os.close(write_fd)
            write_fd = None
            self.assertEqual(os.read(read_fd, 10), b'ab')
            self.assertEqual(os.read(read_fd, 10), b'')
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)

    def test_self_contained_percentile_and_const_exercise(self):
        q=self.data[8]['quizzes']['advanced'][-1]
        self.assertIn('99 заняли по 10 мс',q['q'])
        self.assertIn('1010 мс',q['q'])
        self.assertNotIn('Для тех же',q['q'])
        t=next(t for t in self.data[1]['tasks'] if 'Counter' in t['brief'])
        self.assertIn('// cc.increment();',t['code'])

    def test_transfer_tasks(self):
        for n,d in self.data.items():
            tasks=[t for t in d['tasks'] if t['title'].startswith('Самостоятельный вариант:')]
            self.assertTrue(tasks,n)
            for t in tasks:
                self.assertTrue(t['checks'])
                self.assertTrue(t['solution'])

    def test_compiled_transfer_variants(self):
        for n,expected in ((0,'ABbXa'),(2,'D4 D9 B4 D6 ')):
            t=next(t for t in self.data[n]['tasks'] if t['title'].startswith('Самостоятельный вариант:'))
            with tempfile.TemporaryDirectory(prefix='novice-cpp-') as tmp:
                out=Path(tmp)/'example'
                subprocess.run(['g++','-std=c++20','-x','c++','-','-o',str(out)],input=t['code'],text=True,check=True,capture_output=True)
                self.assertEqual(subprocess.check_output([str(out)],text=True),expected)
                if n==0:
                    changed=t['code'].replace("    if (early) return;\n    Mark c{'C', 'c'};", "    Mark c{'C', 'c'};\n    if (early) return;")
                    subprocess.run(['g++','-std=c++20','-x','c++','-','-o',str(out)],input=changed,text=True,check=True,capture_output=True)
                    self.assertEqual(subprocess.check_output([str(out)],text=True),'ABCcbXa')

    def test_math_variants(self):
        import math
        self.assertAlmostEqual(.2/200,.001)
        self.assertAlmostEqual(.1*4/200,.002)
        for slow,expected in ((100,1000),(1,10)):
            sample=[10]*900+[1000]*slow
            self.assertEqual(sample[math.ceil(.99*len(sample))-1],expected)

    def test_followup_numeric_conditions(self):
        task=next(t for t in self.data[5]['tasks'] if t['title']=='CPU и задержка — разные бюджеты')
        self.assertIn('100% означает один полностью занятый CPU',task['brief'])
        self.assertAlmostEqual(.10/100,.001)
        self.assertAlmostEqual(.15/150,.001)
        retry=self.data[7]['quizzes']['advanced'][28]
        self.assertIn('включая первую',retry['q'])
        self.assertIn(str(3**3),retry['options'][retry['answer']])
        budget=self.data[7]['quizzes']['advanced'][79]
        self.assertIn('резерв',budget['q'])
        self.assertEqual(budget['options'][budget['answer']],f'{80+64} КиБ')

    def test_barrier_group_handles_partial_startup(self):
        task=next(t for t in self.data[6]['tasks'] if t['title']=='barrier: синхронные фазы сбора')
        prefix='''
#include <vector>
#include <iostream>
#include <stdexcept>
struct Metric { int value; };
int phases=0, metrics=0;
std::vector<Metric> collectFrom(const char*) { return {{1}}; }
void logNoThrow(const char*, const char*) noexcept {}
void logUnknownFailureNoThrow(const char*) noexcept {}
void publishSnapshotNoThrow(const std::vector<Metric>& values) noexcept {
    ++phases;
    metrics += static_cast<int>(values.size());
}
'''
        suffix='''
int main() {
    try { scenario(); }
    catch (const std::runtime_error&) { std::cout << "failed "; }
    std::cout << phases << ' ' << metrics;
}
'''
        code=task['code'].replace('int main() {','void scenario() {')
        original='for (const char* name : names)\n            workers.emplace_back(collectorLoop, name);'
        self.assertIn(original,code)
        for fail_at,expected in ((None,'10 30'),(1,'failed 10 10'),(2,'failed 10 20')):
            variant=code
            if fail_at is not None:
                variant=variant.replace(original,'''for (const char* name : names) {
            if (workers.size() == %d) throw std::runtime_error("startup");
            workers.emplace_back(collectorLoop, name);
        }''' % fail_at)
            with tempfile.TemporaryDirectory(prefix='novice-barrier-') as tmp:
                out=Path(tmp)/'example'
                subprocess.run(['g++','-std=c++20','-pthread','-x','c++','-','-o',str(out)],input=prefix+variant+suffix,text=True,check=True,capture_output=True)
                # A missing-participant regression used to hang in jthread's join.
                self.assertEqual(subprocess.check_output([str(out)],text=True,timeout=5),expected)

    def test_parallel_sum_partition_examples(self):
        task=next(t for t in self.data[6]['tasks'] if t['title']=='Результат из потока через future')
        self.assertIn('Все промежуточные суммы',task['brief'])
        source=task['code']+'''
#include <iostream>
int main() {
    std::cout << parallelSum({}) << ' ' << parallelSum({3,4}) << ' '
              << parallelSum({1,2,3,4,5,6,7,8,9,10}) << ' '
              << parallelSum({-5,2,3,-1});
}
'''
        with tempfile.TemporaryDirectory(prefix='novice-parallel-sum-') as tmp:
            out=Path(tmp)/'example'
            subprocess.run(['g++','-std=c++20','-pthread','-x','c++','-','-o',str(out)],input=source,text=True,check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(out)],text=True,timeout=5),'0 7 55 -1')

    def test_practice_contracts_and_non_spoiling_checklist(self):
        history=next(t for t in self.data[8]['tasks'] if t['title']=='Полностью восстанови историю Task 42')
        self.assertIn('Сервер успешно применил PATCH X',history['brief'])
        self.assertIn('сильный ETag',history['brief'])
        self.assertNotRegex(' '.join(history['checks']),r'\b(?:200|304|412|422|v8|v9)\b')
        session=next(t for t in self.data[8]['tasks'] if t['title']=='Выход пользователя и две копии секрета')
        self.assertIn('не состояние отзыва',session['brief'])
        self.assertIn('актуальную серверную запись',session['brief'])
        budget=next(t for t in self.data[7]['tasks'] if t['title']=='Проследи резерв до освобождения буфера')
        self.assertIn('R=0',budget['brief'])
        self.assertIn('заменяет её резерв целиком',budget['brief'])

if __name__=='__main__':unittest.main()
