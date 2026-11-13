"""Build/markup safeguards for the prepared distributed laboratory, not pixel QA."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import parse_qs, urlsplit

from build_distributed_lab import ROOT, OUTPUT, render


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DistributedLabBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = OUTPUT.read_text(encoding="utf-8")
        cls.page = Page()
        cls.page.feed(cls.html)

    def test_output_current_and_deterministic(self):
        self.assertEqual(self.html, render())
        self.assertEqual(render(), render())

    def test_assets_exist_and_are_cache_versioned(self):
        assets = [attrs.get("href", attrs.get("src"))
                  for tag, attrs in self.page.tags if tag in ("script", "link")]
        self.assertEqual(len(assets), 4)
        for href in assets:
            url = urlsplit(href)
            self.assertTrue((ROOT / url.path).is_file(), href)
            self.assertRegex(parse_qs(url.query)["v"][0], r"^[a-f0-9]{12}$")

    def test_semantic_page_and_unique_control_ids(self):
        ids = [attrs["id"] for _, attrs in self.page.tags if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for id_ in ("experiment", "event-title", "scenario-title", "scenario-navigation",
                    "participants", "delivery", "operation-history", "lab-announcement"):
            self.assertIn(id_, ids)
        self.assertTrue(any(tag == "html" and attrs.get("lang") == "ru"
                            and attrs.get("class") == "course-dark"
                            for tag, attrs in self.page.tags))
        self.assertEqual(sum(tag == "h1" for tag, _ in self.page.tags), 1)
        self.assertTrue(any(attrs.get("role") == "status"
                            and attrs.get("aria-live") == "polite"
                            for _, attrs in self.page.tags))
        for tag, attrs in self.page.tags:
            if tag == "button":
                self.assertEqual(attrs.get("type"), "button")
        self.assertIn("Подготовленная учебная модель", self.html)
        self.assertNotIn("user-scalable=no", self.html)

    def test_static_theory_links_resolve(self):
        stations = {}
        for path in (ROOT / "content").glob("station*.json"):
            data = json.loads(path.read_text())
            stations[data["meta"]["sourceFile"]] = {s["id"] for s in data["theory"]}
        for tag, attrs in self.page.tags:
            if tag != "a":
                continue
            href = attrs["href"]
            self.assertNotRegex(href, r'[\\\s"]')
            url = urlsplit(href)
            section = parse_qs(url.fragment).get("section", [None])[0]
            if section:
                self.assertIn(section, stations[url.path])

    def test_interface_safeguards_are_present(self):
        css = (ROOT / "assets/distributed-lab.css").read_text()
        js = (ROOT / "assets/distributed-lab.js").read_text()
        self.assertIn("var(--course-canvas)", css)
        self.assertIn("var(--course-ink)", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("max-height: 600px", css)
        self.assertIn("grid-template-columns: minmax(0,1fr)", css)
        self.assertNotRegex(css, r"transition:\s*all")
        self.assertNotRegex(js, r"innerHTML|\beval\s*\(|\bfetch\s*\(|localStorage")
        self.assertIn('"popstate"', js)
        self.assertIn('"hashchange"', js)
        self.assertIn('[role="region"]', js)

    def test_prepared_model_and_dom_regressions(self):
        for filename in ("test_distributed_lab_model.js", "test_distributed_lab_ui.js"):
            result = subprocess.run(
                ["gjs", str(ROOT / "tools" / filename)],
                cwd=ROOT.parent, text=True, capture_output=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(result.stdout.startswith("PASS: "))
            if filename.endswith("_ui.js"):
                self.assertIn("actual browser rendering not verified", result.stdout)
            else:
                self.assertIn("No live cluster or browser", result.stdout)


if __name__ == "__main__":
    unittest.main()
