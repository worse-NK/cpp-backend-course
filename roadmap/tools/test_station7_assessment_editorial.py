"""Assessment regressions for the networking editorial pass.

Arithmetic/state examples are teaching models, not real network measurements.
No capture, network configuration, or remote connection is performed here.
"""
import json
from pathlib import Path
import re
import unittest

from build_stations import validate

ROOT=Path(__file__).resolve().parents[1]


class NetworkAssessmentEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/'content/station7.json'
        cls.data=json.loads(cls.path.read_text())
        cls.sections={s['id']:s for s in cls.data['theory']}

    def question(self,kind,index):
        return self.data['quizzes'][kind][index]

    def test_schema_and_question_identity_counts(self):
        validate(self.data,self.path)
        self.assertEqual([len(self.data['quizzes'][k]) for k in
                          ('basic','advanced','interview')],[53,83,63])
        self.assertEqual(self.data['meta']['storeKey'],'cpp_station7_progress_v1')

    def test_no_dominant_shortest_or_longest_answer_shortcut(self):
        for kind,questions in self.data['quizzes'].items():
            for extreme in (min,max):
                hits=0
                for q in questions:
                    sizes=[len(re.sub('<[^>]+>','',o)) for o in q['options']]
                    limit=extreme(sizes)
                    hits+=sizes[q['answer']]==limit and sizes.count(limit)==1
                self.assertLessEqual(hits/len(questions),.5,(kind,extreme.__name__))

    def test_instead_of_repeated_et_drain_there_are_distinct_contracts(self):
        for i,term in [(16,'EPOLLONESHOT'),(58,'EPOLLHUP'),(73,'LT')]:
            self.assertIn(term,self.question('advanced',i)['q'])
        self.assertIn('EPOLL_CTL_MOD',self.question('advanced',16)['options'][1])
        self.assertIn('не закрепляет',self.question('advanced',73)['why'])

    def test_udp_zero_length_is_not_stream_eof(self):
        q=self.question('advanced',11)
        self.assertEqual(q['answer'],2)
        self.assertIn('датаграмму нулевой длины',q['options'][2])
        prose=json.dumps(self.sections['udp-semantics'],ensure_ascii=False)
        self.assertIn('нулевой длины допустима',prose)
        self.assertIn('recv.2.html',prose)

    def test_dns_negative_cache_is_not_the_same_question_as_open_tcp(self):
        self.assertIn('NXDOMAIN',self.question('advanced',7)['q'])
        self.assertEqual(self.question('advanced',7)['answer'],1)
        ttl=self.question('advanced',50)
        self.assertEqual(300-60,240)
        self.assertEqual(ttl['answer'],0)
        self.assertIn('300-й',ttl['options'][0])
        self.assertIn('CNAME',self.question('advanced',76)['q'])
        self.assertIn('TCP-соединение',self.question('basic',8)['q'])

    def test_bdp_and_window_rate_questions_require_different_units(self):
        self.assertEqual(1_000_000_000*.040/8,5_000_000)
        mbps=128*1024/.050*8/1_000_000
        self.assertAlmostEqual(mbps,20.97152)
        self.assertIn('20,97',self.question('advanced',36)['options'][2])
        self.assertIn('5 000 000',self.question('basic',44)['options'][2])

    def test_two_bit_generation_can_match_again_while_old_result_lives(self):
        values=[i%4 for i in range(5)]
        self.assertEqual(values,[0,1,2,3,0])
        self.assertEqual(values[0],values[-1])
        q=self.question('interview',28)
        self.assertEqual(q['answer'],1)
        self.assertIn('оборот',q['why'])

    def test_strand_contracts_are_not_a_single_repeated_write_question(self):
        self.assertIn('напрямую',self.question('advanced',23)['q'])
        self.assertIn('Две корутины',self.question('advanced',75)['q'])
        self.assertEqual(self.question('advanced',23)['answer'],2)
        self.assertEqual(self.question('advanced',75)['answer'],0)

    def test_original_code_in_interview_question_is_unchanged(self):
        self.assertIn('char buf[1024];\nssize_t n = recv(fd, buf, sizeof buf, 0);\nstd::string s(buf);',
                      self.question('interview',9)['q'])
        self.assertIn('сначала',self.question('interview',9)['why'].lower())

    def test_checkpoint_count_and_refs(self):
        plan=json.loads((ROOT/'content/checkpoints/station7.json').read_text())
        self.assertEqual(len(plan['modules']),9)
        for module,questions in plan['modules'].items():
            self.assertEqual(len(questions),5)
            for entry in questions:
                q=self.question(entry['bank'],entry['index']) if 'bank' in entry else entry
                self.assertEqual(q['substation'],module)
                self.assertTrue(q['theoryRefs'])

    def test_new_buffer_task_accounts_for_rejection_and_live_whole_blocks(self):
        task=self.data['tasks'][26]
        q,reserve,paused=40,0,False
        states=[]
        def record():
            nonlocal paused
            if q+reserve>=192:
                paused=True
            elif q+reserve<=96:
                paused=False
            states.append((q,reserve,paused))
        reserve+=80; record()
        self.assertGreater(q+reserve+224,320)
        record()  # C rejected: neither ownership nor accounting changed.
        reserve+=96; record()
        reserve-=80; q+=56; record()
        record()  # Partial send: the complete block is still alive.
        q-=40; record()
        reserve-=96; record()  # B has completed, not merely been cancelled.
        q-=56; record()
        self.assertEqual(states,[(40,80,False),(40,80,False),(40,176,True),
                                 (96,96,True),(96,96,True),(56,96,True),
                                 (56,0,False),(0,0,False)])
        for term in ('344','Q=56, R=96','Q=56, R=0','весь RSS'):
            self.assertIn(term,task['solution']+' '+task['notes'])
        self.assertEqual(task['theoryRefs'],['event-loop-buffers-backpressure'])

    def test_new_window_task_applies_both_limits_before_rate(self):
        task=self.data['tasks'][27]
        self.assertEqual(2_000_000_000*.025/8,6_250_000)
        window=min(384*1024,192*1024)
        self.assertEqual(window,196_608)
        self.assertEqual(min(768*1024,192*1024),window)
        self.assertAlmostEqual(window/.025*8/1_000_000,62.91456)
        self.assertIn('62,9',task['solution'])
        self.assertIn('не проведение сетевого теста',task['notes'])

    def test_new_deadline_and_dns_tasks_require_transfer_not_name_replacement(self):
        deadline=self.data['tasks'][24]
        self.assertEqual(2000-300-400,1300)
        self.assertEqual(len('PONG\n'),5)
        self.assertIn('1,9',deadline['brief'])
        self.assertIn('2,1',deadline['brief'])
        self.assertIn('timed_out',deadline['solution'])
        dns=self.data['tasks'][25]
        self.assertIn('CNAME',dns['code'])
        for term in ('MX','A/AAAA'):
            self.assertIn(term,dns['brief'])
        self.assertIn('не является командой закрыть',dns['solution'])


if __name__=='__main__':
    unittest.main()
