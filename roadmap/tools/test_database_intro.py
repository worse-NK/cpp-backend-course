"""Station 9 structural checks; runtime tests live in examples/station9."""
import json
import re
import unittest
from pathlib import Path
from html.parser import HTMLParser
from build_database_intro import updated_page
from build_stations import validate, html_for
ROOT = Path(__file__).resolve().parents[1]

class Links(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.append(dict(attrs)['href'])

class DatabaseStationTest(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'content/station9.json').read_text())
    def test_complete_common_format(self):
        validate(self.data,Path('station9.json'))
        self.assertEqual(len(self.data['substations']),12)
        self.assertEqual((ROOT/self.data['meta']['sourceFile']).read_text(),html_for(self.data))
        for module in self.data['substations']:
            self.assertGreaterEqual(sum(q['substation']==module['id'] for q in self.data['quizzes']['basic']),2)
        self.assertTrue(any(s['id'].endswith('-final-workbook') for s in self.data['theory']))
    def test_local_links_and_primary_sources(self):
        ids={s['id'] for s in self.data['theory']}
        for section in self.data['theory']:
            links=Links(' '.join(b.get('html','') for b in section['blocks'])).links
            self.assertTrue(any(x.startswith('https://') for x in links),section['id'])
            for link in links:
                if link.startswith('#section='):self.assertIn(link.split('=',1)[1],ids)
                elif not link.startswith('https://'):self.assertTrue((ROOT/link.split('#')[0]).is_file(),link)
        text=json.dumps(self.data,ensure_ascii=False)
        for term in ['ctid','40001','Serializable','retention','digest','nextval','libpqxx','WAL']:
            self.assertIn(term.lower(),text.lower())
    def test_code_and_legacy_link(self):
        for sid in ['cpp-storage','parking-final-workbook']:
            filename='main.cpp' if sid=='cpp-storage' else 'parking.cpp'
            code=(ROOT/'examples/station9'/filename).read_text().strip()
            sec=next(s for s in self.data['theory'] if s['id']==sid)
            self.assertIn(code,[b.get('code') for b in sec['blocks']])
        self.assertEqual((ROOT/'cpp_station9_databases_intro.html').read_text(),updated_page())
    def test_home_matches_station(self):
        home=(ROOT/'cpp_backend_roadmap.html').read_text()
        root=json.loads(re.search(r'<script id="roadmap-data" type="application/json">(.*?)</script>',home,re.S)[1])
        stage=next(s for s in root['stages'] if s['id']=='databases')
        self.assertNotIn('preview',stage)
        self.assertEqual(stage['station']['totalSections'],len(self.data['theory']))
        self.assertEqual(stage['station']['file'],self.data['meta']['sourceFile'])
if __name__=='__main__':unittest.main()
