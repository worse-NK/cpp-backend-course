import json
import re
import unittest
from pathlib import Path

from build_sources import render

ROOT = Path(__file__).resolve().parents[1]


class CourseSources(unittest.TestCase):
    def test_index_is_current_and_contains_every_theory_section(self):
        page = render()
        self.assertEqual((ROOT / 'sources.html').read_text(), page)
        count = 0
        for path in sorted((ROOT / 'content').glob('station[0-9]*.json')):
            data = json.loads(path.read_text())
            for section in data['theory']:
                self.assertIn(data['meta']['sourceFile'] + '#section=' + section['id'], page)
                count += 1
        self.assertEqual(page.count('<details>'), count)

    def test_course_does_not_assign_a_professional_background(self):
        paths = [ROOT / 'cpp_backend_roadmap.html', *sorted((ROOT / 'content').glob('station[0-9]*.json'))]
        forbidden = ('C-шника', 'поверх твоего C', 'У тебя как embedded-инженера',
                     'Твой опыт с прерываниями', 'то, что ты уже делал', '100% вакансий',
                     'Близкая тебе аналогия', 'ты делал «общую»')
        for path in paths:
            text = path.read_text()
            for phrase in forbidden:
                self.assertNotIn(phrase, text, str(path))

    def test_sources_are_reachable_from_home(self):
        home = (ROOT / 'cpp_backend_roadmap.html').read_text()
        data = json.loads(re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>', home, re.S)[1])
        self.assertTrue(any(item['file'] == 'sources.html' for item in data['bonusFiles']))


if __name__ == '__main__':
    unittest.main()
