"""Cross-station integrity checks; these do not certify editorial completeness."""
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlsplit, unquote, parse_qs

from test_linux_systems import Fragment

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


class CourseIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = [json.loads(p.read_text()) for p in (ROOT / "content").glob("station*.json")]
        cls.sections = {d["meta"]["sourceFile"]: {s["id"] for s in d["theory"]} for d in cls.data}

    def test_internal_theory_links_and_downloads(self):
        for data in self.data:
            for section in data["theory"]:
                parser = Links()
                for value in strings(section["blocks"]):
                    parser.feed(value)
                for href in parser.links:
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        continue
                    target = unquote(url.path) or data["meta"]["sourceFile"]
                    with self.subTest(station=data["meta"]["id"], section=section["id"], href=href):
                        self.assertTrue((ROOT / target).is_file(), target)
                        section_id = parse_qs(url.fragment).get("section", [])
                        if target in self.sections and section_id:
                            self.assertIn(section_id[0], self.sections[target])

    def test_reading_order_has_no_missing_or_duplicate_sections(self):
        for data in self.data:
            if "readingOrder" in data:
                with self.subTest(station=data["meta"]["id"]):
                    self.assertCountEqual(data["readingOrder"], [s["id"] for s in data["theory"]])

    def test_theory_and_revealed_answers_have_self_contained_html(self):
        # Template syntax belongs in escaped text, not accidental HTML tags.
        # Structural validity is useful, but does not establish prose quality.
        for data in self.data:
            for section in data['theory']:
                for index, block in enumerate(section['blocks']):
                    for field in ('html', 'prompt', 'answer'):
                        if not isinstance(block.get(field), str):
                            continue
                        with self.subTest(station=data['meta']['id'],
                                          section=section['id'], block=index,
                                          field=field):
                            fragment=Fragment(block[field])
                            self.assertEqual(fragment.errors, [])
                            self.assertEqual(fragment.stack, [])

    def test_recent_interview_topics_are_accessible(self):
        for number, refs in {
            3: ["template-instantiation-cost"],
            6: ["spsc-ring-model", "spsc-ring-code"],
            7: ["multicast-model", "multicast-socket-lab"],
            9: ["storage-maintenance"],
            10: ["capacity-experiment", "capacity-local-lab"],
        }.items():
            data = next(d for d in self.data if d["meta"]["id"] == f"station{number}")
            checked = {ref for q in data["quizzes"]["interview"] for ref in q["theoryRefs"]}
            self.assertTrue(set(refs) <= checked)


if __name__ == "__main__":
    unittest.main()
