"""Integration points and independent checks for course visualization models."""
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import unittest

from build_visual_labs import render, load_catalog
from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]


class VisualLabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(['gjs', str(ROOT / 'tools/test_visual_labs.js'), '--json'], cwd=ROOT.parent,
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.models = json.loads(result.stdout)

    def test_generated_catalog_is_current(self):
        self.assertEqual((ROOT / 'generated/visual-labs.data.js').read_text(), render())

    def test_controller_and_course_context(self):
        run = subprocess.run(['gjs', str(ROOT / 'tools/test_visual_labs_ui.js')], cwd=ROOT.parent,
                             text=True, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_every_lab_has_exact_course_entry_and_local_files(self):
        catalog = load_catalog()['labs']
        expected = {(e['station'], e['section'], lab['id'], e['scenario'])
                    for lab in catalog for e in lab['entries']}
        actual = set()
        for path in (ROOT / 'content').glob('station*.json'):
            station = json.loads(path.read_text())
            validate(station, path)
            for section in station['theory']:
                for block in section['blocks']:
                    if block['type'] == 'lab':
                        key = (path.stem, section['id'], block['lab'], block['scenario'])
                        self.assertNotIn(key, actual)
                        actual.add(key)
        self.assertEqual(actual, expected)
        self.assertEqual(len({entry[0] for entry in actual}), 13)
        for lab in catalog:
            self.assertTrue((ROOT / lab['file']).is_file())
            for entry in lab['entries']:
                self.assertTrue((ROOT / entry['file']).is_file())
        for path in ['visual_labs.html', 'object_lifetime_demo.html']:
            source = (ROOT / path).read_text()
            self.assertNotRegex(source, r'<script[^>]+src="https?://')

    def test_sql_result_matches_real_sqlite(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);"
                             "CREATE TABLE tasks(id INTEGER PRIMARY KEY,owner_id INTEGER,done BOOLEAN);"
                             "INSERT INTO users VALUES(1,'Анна'),(2,'Борис'),(3,'Вера');"
                             "INSERT INTO tasks VALUES(10,1,false),(11,1,true),(12,2,false);")
            for model in self.models:
                if model['lab'] != 'sql':
                    continue
                actual = db.execute('\n'.join(model['code'])).fetchall()
                expected = [(r['id'], r['name'], r['count']) for r in model['steps'][-1]['state']['rows']]
                self.assertEqual(actual, expected, model['mode'])

    def test_executable_ownership_programs(self):
        expected = {'unique': 'destroy Item\n0 0\n', 'shared': '0\ndestroy Item\n1\n'}
        with tempfile.TemporaryDirectory(prefix='course-lab-cpp-') as work:
            for model in self.models:
                if not model.get('program'):
                    continue
                binary = str(Path(work) / model['mode'])
                compiled = subprocess.run(['g++', '-std=c++20', '-x', 'c++', '-', '-o', binary],
                                          input=model['program'], text=True, capture_output=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                run = subprocess.run([binary], text=True, capture_output=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout, expected[model['mode']])

    def test_lifetime_programs_and_actual_printing_lines(self):
        html = (ROOT / 'object_lifetime_demo.html').read_text()
        script = re.search(r'<script>\n(.*?)</script>', html, re.S)[1]
        builder = re.search(r'  const helper =.*?(?=  const courseParams)', script, re.S)[0]
        cases = [['members', False, 'none', True], ['members', True, 'none', True],
                 ['members', False, 'none', False], ['inheritance', False, 'none', False],
                 ['inheritance', False, 'none', True]]
        cases += [[kind, False, failure, True] for kind in ['exception', 'dynamic']
                  for failure in ['none', 'second', 'body']]
        js = builder + '\nconst cases=' + json.dumps(cases) + ';print(JSON.stringify(cases.map(c=>makeScenario(...c))));'
        result = subprocess.run(['gjs', '-c', js], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory(prefix='course-lifetime-') as work:
            for i, model in enumerate(json.loads(result.stdout)):
                for event in model['events']:
                    if event['newOutput']:
                        self.assertIn('std::cout', model['lines'][model['locations'][event['key']]])
                binary = str(Path(work) / str(i))
                compiled = subprocess.run(['g++', '-std=c++20', '-x', 'c++', '-', '-o', binary],
                                          input=model['source'], text=True, capture_output=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                run = subprocess.run([binary], text=True, capture_output=True, timeout=5)
                expected = ''.join(o['text'] + '\n' for o in model['events'][-1]['state']['output'])
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout, expected)


if __name__ == '__main__':
    unittest.main()
