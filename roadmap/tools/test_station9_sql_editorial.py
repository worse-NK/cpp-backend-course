"""SQL editorial regressions. SQLite runs cover only the common SQL subset.

They are not a PostgreSQL server, isolation, durability, or planner test.
"""
import json
from pathlib import Path
import sqlite3
import unittest

from build_stations import validate
from test_linux_systems import Fragment
from test_sql_architecture_deepening import run_script

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'content/station9-sql.json'


class SqlEditorial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SOURCE.read_text())
        cls.sections = {s['id']: s for s in cls.data['theory']}

    def html(self, sid):
        return ' '.join(b.get('html', '') + b.get('answer', '')
                        for b in self.sections[sid]['blocks'])

    def code(self, sid):
        return [b['code'] for b in self.sections[sid]['blocks'] if b['type'] == 'code']

    def database(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript('''
          PRAGMA foreign_keys=ON;
          CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
          CREATE TABLE tasks(id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0, priority INTEGER);
          INSERT INTO users VALUES(1,'Анна'),(2,'Борис'),(3,'Вера');
          INSERT INTO tasks VALUES
            (10,1,'Написать тест',0,3),(11,1,'Прочитать главу',1,NULL),
            (12,2,'Проверить API',0,1);
        ''')
        return db

    def test_schema_identity_and_all_sections(self):
        validate(self.data, SOURCE)
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station9_sql_progress_v1')
        self.assertEqual(len(self.sections), 26)
        self.assertEqual([len(x) for x in self.data['quizzes'].values()], [29,8,10])

    def test_each_section_has_revealable_reasoning_and_valid_fragments(self):
        count = 0
        for sid, section in self.sections.items():
            checks = [b for b in section['blocks'] if b['type'] == 'self-check']
            self.assertTrue(checks, sid)
            count += len(checks)
            for b in section['blocks']:
                for key in ('html','prompt','answer'):
                    if key in b:
                        f = Fragment(b[key])
                        self.assertEqual((f.errors,f.stack), ([],[]), (sid,key))
        self.assertGreaterEqual(count,42)

    def test_two_dataset_boundaries_are_explicit(self):
        self.assertIn('два пользователя', self.html('worked-example'))
        self.assertIn('девять', self.html('worked-example'))
        self.assertIn('уже есть', self.html('aggregation'))
        self.assertIn('повторная вставка', self.html('aggregation'))
        self.assertIn('три независимых', self.html('sql-write-basics'))

    def test_write_listings_combined_are_not_claimed_to_reset_each_other(self):
        db = self.database()
        for source in self.code('sql-write-basics'):
            run_script(db, source)
        self.assertEqual(db.execute('SELECT id FROM tasks ORDER BY id').fetchall(),
                         [(10,),(12,),(20,)])

    def test_inner_join_and_cross_join_counts_on_both_datasets(self):
        for include_vera, counts in [(True,(9,6)), (False,(6,4))]:
            db = self.database()
            if not include_vera:
                db.execute('DELETE FROM users WHERE id=3')
            self.assertEqual(db.execute('SELECT count(*) FROM tasks CROSS JOIN users').fetchone()[0], counts[0])
            self.assertEqual(db.execute('SELECT count(*) FROM tasks CROSS JOIN users WHERE done=false').fetchone()[0], counts[1])
            rows = run_script(db,self.code('worked-example')[0])[0]
            self.assertEqual([row[0] for row in rows],[10,12])

    def test_null_application_and_window_count_assessments(self):
        db = self.database()
        self.assertEqual(db.execute('SELECT 3 NOT IN (1,NULL)').fetchone(), (None,))
        db.executescript('DELETE FROM tasks; INSERT INTO tasks VALUES (1,1,\'a\',0,NULL),(2,1,\'b\',0,5);')
        rows=db.execute('''SELECT COUNT(priority) OVER (PARTITION BY owner_id ORDER BY id
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) FROM tasks ORDER BY id''').fetchall()
        self.assertEqual(rows,[(0,),(1,)])
        self.assertEqual(self.data['quizzes']['interview'][4]['answer'],0)

    def test_left_join_does_not_drop_completed_only_owner(self):
        db = self.database()
        db.execute('UPDATE tasks SET done=true WHERE owner_id=2')
        rows=run_script(db,self.code('aggregation')[-1])[0]
        self.assertEqual(rows,[(1,'Анна',1),(2,'Борис',0),(3,'Вера',0)])

    def test_final_report_empty_and_added_task(self):
        db=self.database();sql=self.code('sql-report-final-workbook')[0]
        self.assertEqual(run_script(db,sql)[0],[(1,'Анна',1,10),(2,'Борис',1,12),(3,'Вера',0,None)])
        db.execute("INSERT INTO tasks VALUES (20,1,'Ещё',0,2)")
        self.assertEqual(run_script(db,sql)[0][0],(1,'Анна',2,20))
        db.execute('DELETE FROM tasks')
        self.assertEqual(run_script(db,sql)[0],[(1,'Анна',0,None),(2,'Борис',0,None),(3,'Вера',0,None)])

    def test_five_checkpoint_questions_per_module(self):
        plan=json.loads((ROOT/'content/checkpoints/station9-sql.json').read_text())
        self.assertEqual(len(plan['modules']),6)
        self.assertTrue(all(len(qs)==5 for qs in plan['modules'].values()))

    def test_postgresql_sqlite_and_parameter_contracts_are_not_conflated(self):
        for word in ('PostgreSQL','SQLite','char_length','length','foreign_keys=ON'):
            self.assertIn(word,self.html('tables'))
        for word in (':last_time','$1','сним', 'timestamptz','lang_conflict.html'):
            self.assertIn(word,self.html('sql-backend-boundaries'))


if __name__=='__main__':
    unittest.main()
