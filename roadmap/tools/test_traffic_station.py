"""Guard the optional traffic route, sources and downloadable teaching traces.

These structural checks complement manual technical/editorial review; they do
not certify that a novice understands the chapter or that a capture is real.
"""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest

from build_stations import validate

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href')


class TrafficStation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'content/station7-traffic.json'
        cls.data = json.loads(cls.source.read_text())
        cls.manifest = json.loads((ROOT / 'examples/traffic-analysis/manifest.json').read_text())

    def test_optional_route_and_preserved_station_ids(self):
        home = (ROOT / 'cpp_backend_roadmap.html').read_text()
        route = json.loads(re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>', home, re.S)[1])
        extras = [stage for stage in route['stages'] if stage.get('optional')]
        self.assertEqual([stage['id'] for stage in extras], ['traffic-analysis'])
        self.assertIs(extras[0]['optional'], True)
        self.assertEqual(extras[0]['station']['file'], self.data['meta']['sourceFile'])
        self.assertEqual(extras[0]['station']['totalSections'], len(self.data['theory']))
        self.assertEqual(self.data['meta']['storeKey'], 'cpp_station7_traffic_progress_v1')
        self.assertEqual(route['stages'][8]['id'], 'networking')
        self.assertEqual(route['stages'][9]['id'], 'linux-network-lab')
        self.assertEqual(route['stages'][10]['id'], 'rest-api')
        self.assertEqual(len([stage for stage in route['stages'] if not stage.get('optional')]), 14)

    def test_full_six_part_route_and_assessment_prerequisites(self):
        validate(self.data, self.source)
        self.assertEqual(len(self.data['substations']), 6)
        self.assertEqual(self.data['theory'][0]['id'], 'learning-route')
        self.assertEqual(self.data['theory'][-1]['id'], 'traffic-final-workbook')
        for module in self.data['substations']:
            for bank in ('basic', 'advanced', 'interview'):
                self.assertGreaterEqual(sum(q['substation'] == module['id'] for q in self.data['quizzes'][bank]), 3)
            tasks = [task for task in self.data['tasks'] if task['substation'] == module['id']]
            self.assertTrue(tasks)
            self.assertTrue(all(task['title'].startswith('Лаборатория: ') and len(task['checks']) >= 2 for task in tasks))

    def test_sources_and_all_downloads_are_in_actual_theory(self):
        links = Links()
        for section in self.data['theory']:
            text = ' '.join(block.get('html', '') for block in section['blocks'])
            with self.subTest(section=section['id']):
                self.assertRegex(text, r'https://(?:www\.wireshark\.org|wiki\.wireshark\.org|www\.rfc-editor\.org|datatracker\.ietf\.org)')
            links.feed(text)
        for name in self.manifest['cases']:
            self.assertIn('examples/traffic-analysis/' + name, links.links)
        for href in links.links:
            if href.startswith('examples/traffic-analysis/'):
                self.assertTrue((ROOT / href).is_file(), href)

    def test_workbook_numbers_refer_to_synthetic_trace_facts(self):
        self.assertIs(self.manifest['synthetic'], True)
        self.assertIs(self.manifest['captured_from_interface'], False)
        normal = self.manifest['cases']['traffic_http_ok.pcap']['facts']
        slow = self.manifest['cases']['traffic_http_delay.pcap']['facts']
        self.assertEqual((normal['request_frame'], normal['response_frame']), (4, 6))
        self.assertEqual((normal['request_to_response_us'], slow['request_to_response_us']), (50_000, 500_000))
        workbook = self.data['theory'][-1]
        prose = json.dumps(workbook, ensure_ascii=False)
        for marker in ('traffic_http_ok.pcap', 'traffic_http_delay.pcap', '50', '500', '450'):
            self.assertIn(marker, prose)
        self.assertRegex(prose.lower(), 'синтетическ|искусственн')


if __name__ == '__main__':
    unittest.main()
