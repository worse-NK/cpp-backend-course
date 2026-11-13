"""Dark-course source/output contracts, not a browser/layout certification."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

import course_theme


ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DarkCourse(unittest.TestCase):
    def test_all_twenty_one_station_shells_use_one_reader(self):
        fixtures = list((ROOT / "content").glob("station*.json"))
        self.assertEqual(len(fixtures), 21)
        for fixture in fixtures:
            data = json.loads(fixture.read_text())
            source = (ROOT / data["meta"]["sourceFile"]).read_text()
            doc = Document(source)
            with self.subTest(station=data["meta"]["id"]):
                html = next(attrs for tag, attrs in doc.tags if tag == "html")
                body = next(attrs for tag, attrs in doc.tags if tag == "body")
                self.assertIn("course-dark", html.get("class", "").split())
                self.assertTrue({"course-reader", "course-dark"} <= set(body.get("class", "").split()))
                self.assertNotIn("design-studio", body.get("class", ""))
                self.assertNotIn("maximum-scale", source)
                self.assertNotIn("user-scalable=no", source)
                self.assertNotIn("fonts.googleapis.com", source)
                theme = [attrs for tag, attrs in doc.tags if tag == "meta" and attrs.get("name") == "theme-color"]
                self.assertEqual(theme, [{"name": "theme-color", "content": "#18252f"}])
                for asset in ["course-ui.css", "course-reader.css", "course-theme.css", "course-dark-reader.css", "course-code.css"]:
                    links = [attrs["href"] for tag, attrs in doc.tags if tag == "link" and asset in attrs.get("href", "")]
                    self.assertEqual(len(links), 1, asset)
                self.assertLess(source.index("course-theme.css"), source.index("course-dark-reader.css"))
                scripts = [attrs.get("src", "") for tag, attrs in doc.tags if tag == "script"]
                highlighter = next(i for i, name in enumerate(scripts) if "vendor/highlightjs/highlight.min.js" in name)
                helper = next(i for i, name in enumerate(scripts) if "assets/course-code.js" in name)
                app = next(i for i, name in enumerate(scripts) if "assets/station-app.js" in name)
                self.assertLess(highlighter, helper)
                self.assertLess(helper, app)
                for tag, attrs in doc.tags:
                    reference = attrs.get("src") if tag == "script" else attrs.get("href")
                    if not reference:
                        continue
                    url = urlsplit(reference)
                    if not url.scheme and url.path:
                        self.assertTrue((ROOT / url.path).is_file(), reference)

    def test_support_surfaces_keep_the_same_dark_foundation(self):
        self.assertGreaterEqual(len(course_theme.SUPPORT_PAGES), 12)
        for name, page in course_theme.SUPPORT_PAGES.items():
            source = (ROOT / name).read_text()
            doc = Document(source)
            with self.subTest(page=name):
                body = next(attrs for tag, attrs in doc.tags if tag == "body")
                self.assertTrue({"course-dark", "course-support", "course-page-" + page} <= set(body.get("class", "").split()))
                links = [attrs.get("href", "") for tag, attrs in doc.tags if tag == "link"]
                self.assertEqual(sum("course-theme.css" in href for href in links), 1)
                self.assertEqual(sum("course-dark-surfaces.css" in href for href in links), 1)
                self.assertNotIn("maximum-scale=1", source)

    def test_compact_action_contract_prevents_the_reported_flex_collapse(self):
        # Source contracts explicitly guard the fix; they cannot measure the
        # text's actual rendered width or replace a narrow-screen visual check.
        source = (ROOT / "assets/course-dark-reader.css").read_text()
        row = re.search(r"body\.course-reader\.course-dark :is\(\.section-actions, \.assembly-actions, \.reader-return-actions\)\s*\{([^}]+)\}", source)
        self.assertIsNotNone(row)
        for declaration in ["display: flex", "flex-wrap: wrap", "align-items: flex-start", "align-content: flex-start"]:
            self.assertIn(declaration, row.group(1))
        child = re.search(r"body\.course-reader\.course-dark :is\(\.section-actions, \.assembly-actions, \.reader-return-actions\) > :is\(button, a\)\s*\{([^}]+)\}", source)
        self.assertIsNotNone(child)
        for declaration in ["flex: 0 0 auto", "align-self: flex-start", "width: fit-content", "max-width: 100%", "height: auto"]:
            self.assertIn(declaration, child.group(1))
        compact = re.search(r"body\.course-reader\.course-dark :is\(\.primary, \.secondary, \.solution-button, \.ghost, \.quiz-back, \.hint-button\)\s*\{([^}]+)\}", source)
        self.assertIsNotNone(compact)
        for declaration in ["min-height: 44px", "height: auto", "word-break: normal", "white-space: normal"]:
            self.assertIn(declaration, compact.group(1))
        self.assertIn("@media (max-width: 600px)", source)
        self.assertNotRegex(compact.group(1), r"(?:height|min-height):\s*(?:100%|100vh|\d{3,}px)")

    def test_left_contents_and_keyboard_access_contract(self):
        source = (ROOT / "assets/course-reader.css").read_text()
        rail = re.search(r"body\.course-reader \.page > \.substation-shell\s*\{([^}]+)\}", source)
        self.assertIsNotNone(rail)
        for declaration in ["grid-column: 1", "position: sticky", "overflow: auto", "max-height: calc(100dvh - 48px)"]:
            self.assertIn(declaration, rail.group(1))
        self.assertRegex(source, r"grid-template-columns:\s*270px minmax\(0, 1fr\)")
        self.assertIn("@media (max-width: 1099px)", source)
        dark = (ROOT / "assets/course-dark-reader.css").read_text()
        self.assertIn(":focus-visible", dark)
        self.assertIn("outline: 3px solid var(--course-focus)", dark)
        theme = (ROOT / "assets/course-theme.css").read_text()
        self.assertIn("color-scheme: dark", theme)

    def test_local_highlighter_provenance_and_published_assets(self):
        directory = ROOT / "vendor/highlightjs"
        origin = json.loads((directory / "ORIGIN.json").read_text())
        self.assertEqual(origin["version"], "11.12.0")
        self.assertEqual(origin["license"], "BSD-3-Clause")
        for name, record in origin["files"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), record["sha256"], name)
        from build_publication import collect
        files, _ = collect()
        for name in ["course-ui.css", "course-reader.css", "course-theme.css", "course-dark-reader.css", "course-dark-surfaces.css", "course-code.js", "course-code.css"]:
            self.assertIn("roadmap/assets/" + name, files)
        self.assertIn("roadmap/vendor/highlightjs/highlight.min.js", files)
        self.assertIn("roadmap/vendor/highlightjs/LICENSE", files)
        self.assertFalse(any("design_station0_" in name or "station-design-preview" in name for name in files))


if __name__ == "__main__":
    unittest.main()
