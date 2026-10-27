import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from build_cheatsheet import render, ROOT


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links, self.scripts, self.tags = [], [], [], set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag == 'script' and 'src' in a:
            self.scripts.append(a['src'])


class CheatSheetTest(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'cpp_cheatsheet.html').read_text()
        self.page = Page(self.html)
        self.data = json.loads((ROOT / 'content/cheatsheet.json').read_text())

    def test_generated_file_is_current(self):
        self.assertEqual(self.html, render())

    def test_every_station_has_content_and_chapter_link(self):
        groups = {s['num']: s for s in self.data['stations']}
        for i in range(10):
            self.assertIn(str(i), groups)
            self.assertGreaterEqual(len(groups[str(i)]['sections']), 8)
            meta = json.loads((ROOT / f'content/station{i}.json').read_text())['meta']
            self.assertIn(meta['sourceFile'], self.page.links)
            self.assertIn(f'#station-{i}', self.page.links)
            self.assertIn('Источники', groups[str(i)]['sections'][-1]['h'])

    def test_anchor_and_local_link_integrity(self):
        self.assertEqual(len(self.page.ids), len(set(self.page.ids)))
        for link in self.page.links:
            if link.startswith('#'):
                self.assertIn(link[1:], self.page.ids)
            elif not link.startswith('https://'):
                self.assertTrue((ROOT / link.split('#')[0]).is_file(), link)

    def test_offline_content_and_assets(self):
        self.assertEqual([src.split('?')[0] for src in self.page.scripts], [
            'assets/cheatsheet.js', 'generated/terms.data.js',
            'assets/terms-core.js', 'assets/terms.js'])
        self.assertTrue(all(not src.startswith(('http:', 'https:', '//')) for src in self.page.scripts))
        for src in self.page.scripts:
            self.assertTrue((ROOT / src.split('?')[0]).is_file(), src)
        self.assertNotIn('unpkg', self.html)
        self.assertIn('<h2>REST API', self.html)
        for asset in ['assets/cheatsheet.js', 'assets/cheatsheet.css']:
            self.assertTrue((ROOT / asset).is_file())

    def test_cpp_templates_are_not_html_tags(self):
        allowed = set('html head meta title link body a div aside details summary nav span main header p h1 label input button h2 h3 h4 section pre code b strong em footer script'.split())
        self.assertFalse(self.page.tags - allowed, self.page.tags - allowed)
        self.assertIn('template&lt;typename T&gt;', self.html)

    def test_pure_virtual_rule_distinguishes_qualified_nonvirtual_call(self):
        station = next(s for s in self.data['stations'] if s['num'] == '2')
        rules = [item['rule'] for section in station['sections']
                 for item in section['items'] if 'pure virtual' in item.get('rule', '')]
        rule = next(text for text in rules if 'ctor/dtor' in text)
        self.assertIn('виртуальный вызов', rule)
        self.assertIn('Base::f()', rule)
        self.assertIn('подавляет виртуальный', rule)
        self.assertIn('n4861/class.abstract#6', rule)


if __name__ == '__main__':
    unittest.main()
