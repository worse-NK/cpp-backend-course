"""Static glossary, shared catalog, safety and integration; no live browser required."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import build_glossary as glossary
import build_publication as public

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.ids = []; self.links = []; self.articles = 0
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs: self.ids.append(attrs['id'])
        if 'href' in attrs: self.links.append(attrs['href'])
        if tag == 'article': self.articles += 1


class Glossary(unittest.TestCase):
    def test_catalog_has_substantial_definitions_and_primary_sources(self):
        entries = glossary.load()
        self.assertGreaterEqual(len(entries), 100)
        for e in entries:
            with self.subTest(term=e['id']):
                self.assertGreater(sum(map(len, e['paragraphs'])), 200)
                self.assertTrue(e['sources'])
                self.assertTrue(e['learn']['section'])

    def test_reviewed_api_sources_are_term_specific(self):
        # A regression guard for manually reviewed mappings, not a mechanical
        # proof that a page supports every sentence in a definition.
        entries = {entry['id']: entry for entry in glossary.load()}
        topics = {
            'deadline': 'grpc.io/docs/guides/deadlines/',
            'api': 'CppCoreGuidelines#i-interfaces',
            'rpc': 'grpc.io/docs/what-is-grpc/core-concepts/',
            'validation': 'Input_Validation_Cheat_Sheet',
            'xss': 'Cross_Site_Scripting_Prevention_Cheat_Sheet',
            'csrf': 'Cross-Site_Request_Forgery_Prevention_Cheat_Sheet',
            'cors': 'fetch.spec.whatwg.org/#http-cors-protocol',
            'openapi': 'spec.openapis.org/oas/v3.1.1.html',
            'pagination': 'google.aip.dev/158',
        }
        for term, topic in topics.items():
            with self.subTest(term=term):
                self.assertTrue(any(topic in source['url']
                                    for source in entries[term]['sources']))
        for term, section in {'cors': 'cors-csrf', 'openapi': 'openapi-contract',
                              'pagination': 'pagination', 'rpc': 'rpc-grpc'}.items():
            self.assertEqual(entries[term]['learn']['section'], section)

    def test_page_is_complete_without_javascript(self):
        entries = glossary.load(); html = glossary.render(); page = Page(html)
        self.assertEqual(page.articles, len(entries))
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for e in entries:
            self.assertIn('term-' + e['id'], page.ids)
            self.assertIn(e['learn']['file'] + '#section=' + e['learn']['section'], page.links)
        self.assertIn('class="glossary-search" hidden', html)

    def test_popup_catalog_does_not_download_the_whole_glossary(self):
        result = glossary.render_data()
        entries = json.loads(result.split('window.COURSE_TERMS = ', 1)[1].rstrip().removesuffix(';'))
        self.assertEqual(len(entries), len(glossary.load()))
        self.assertTrue(all(set(e) == {'id','title','forms','short','inlineDefinitions'} for e in entries))
        self.assertNotIn('paragraphs', result)

    def test_definitions_are_escaped_not_executed_as_markup(self):
        entries = copy.deepcopy(glossary.load())
        entries[0]['short'] = '<img src=x onerror=alert(1)>'
        entries[0]['paragraphs'][0] = '<script>alert(1)</script>'
        with patch.object(glossary, 'load', return_value=entries):
            html = glossary.render()
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img src=x', html)
        self.assertIn('&lt;script&gt;', html)

    def test_project_pages_publication_contains_dictionary_and_popup_assets(self):
        files, stations = public.collect()
        for filename in ['glossary.html', 'generated/terms.data.js', 'assets/terms-core.js',
                         'assets/terms.js', 'assets/terms.css', 'assets/glossary.js', 'assets/glossary.css']:
            self.assertIn('roadmap/' + filename, files)
        self.assertGreater(public.check_release(files, stations)['local_links_checked'], 900)
        for station in stations:
            page = files['roadmap/' + station['meta']['sourceFile']].decode()
            self.assertIn('assets/terms.js', page)
            self.assertIn('generated/terms.data.js', page)
        self.assertNotIn('roadmap/content/glossary.json', files)

    def test_generated_files_are_current(self):
        self.assertEqual((ROOT/'glossary.html').read_text(), glossary.render())
        self.assertEqual((ROOT/'generated/terms.data.js').read_text(), glossary.render_data())


if __name__ == '__main__': unittest.main()
