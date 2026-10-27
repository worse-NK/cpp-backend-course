import json
import re
import unittest
from pathlib import Path
from html.parser import HTMLParser
from build_sql_lab import render, ROOT

class Tags(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=[];self.links=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag in ('script','link','a'):
            url=a.get('src',a.get('href'))
            if url:self.links.append(url)

class SqlLabTests(unittest.TestCase):
    def test_offline_assets_and_bundle(self):
        self.assertEqual((ROOT/'generated/sql-lab-worker.data.js').read_text(),render())
        page=Tags((ROOT/'sql_trainer.html').read_text())
        self.assertEqual(len(page.ids),len(set(page.ids)))
        for link in page.links:
            self.assertFalse(link.startswith('https://'),'Runtime must be offline')
            self.assertTrue((ROOT/link.split('#')[0]).is_file(),link)
        self.assertTrue((ROOT/'vendor/sqljs/LICENSE').is_file())
        ui=(ROOT/'assets/sql-lab.js').read_text()
        self.assertNotIn('innerHTML',ui)
        self.assertIn('worker.terminate()',ui)
    def test_intro_order_and_trainer_navigation(self):
        d=json.loads((ROOT/'content/station9-sql.json').read_text())
        ids=[s['id'] for s in d['theory']]
        route=['sql-language','sql-first-query','sql-create-basics','tables','sql-select-basics','sql-filter-basics','sql-null-basics','sql-order-basics','sql-write-basics','queries','sql-join-basics','worked-example','sql-trainer','sql-aggregate-basics','sql-exists','sql-window-rank']
        self.assertEqual(sorted(route,key=ids.index),route)
        core=(ROOT/'assets/sql-lab-core.js').read_text()
        for ref in set(re.findall(r"'(sql-[a-z-]+|worked-example|aggregation)'",core)):
            self.assertIn(ref,ids)
        blocks=[b for s in d['theory'] for b in s['blocks'] if b['type']=='sql-trainer']
        self.assertEqual(blocks,[{'type':'sql-trainer','exercise':'expression'}])
        self.assertIn('sql-trainer', (ROOT/'assets/station-app.js').read_text())

if __name__=='__main__':unittest.main()
