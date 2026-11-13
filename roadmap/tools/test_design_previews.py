#!/usr/bin/env python3
"""Source/output contracts for the local station 0 design comparison."""

from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from build_stations import load_json
from checkpoint_data import with_checkpoints


ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "roadmap"
spec = importlib.util.spec_from_file_location("design_preview_builder", ROOT / "authoring/build_design_previews.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DesignPreviews(unittest.TestCase):
    def test_six_explicit_designs_keep_originals(self):
        self.assertEqual(list(builder.VARIANTS), [
            "editorial", "workbook", "focus", "ribbon", "studio", "folio",
        ])

    def test_same_complete_station_fixture(self):
        data = with_checkpoints(load_json(ROADMAP / "content/station0.json"))
        source = (ROADMAP / "generated/station0-design-preview.data.js").read_text()
        actual = json.loads(source.removeprefix("window.STATION_DATA = ").removesuffix(";\n"))
        self.assertEqual(data, actual)
        self.assertEqual(actual["meta"]["id"], "station0")
        self.assertEqual(actual["meta"]["number"], 0)
        self.assertTrue(all(len(q) == 5 for q in actual["checkpoints"].values()))

    def test_each_shell_is_reproducible_and_links_resolve(self):
        for variant in builder.VARIANTS:
            path = ROADMAP / f"design_station0_{variant}.html"
            source = path.read_text()
            with self.subTest(variant=variant):
                self.assertEqual(source, builder.render(variant))
                document = Document(source)
                body = next(attrs for tag, attrs in document.tags if tag == "body")
                self.assertEqual(body["class"], "course-reader design-" + variant)
                self.assertEqual(body["data-design-variant"], variant)
                self.assertFalse(any(tag == "base" for tag, _ in document.tags))
                self.assertNotIn("fonts.googleapis.com", source)
                self.assertNotIn("maximum-scale", source)
                switcher = [attrs for tag, attrs in document.tags if tag == "a" and "data-design-link" in attrs]
                self.assertEqual(len(switcher), 6)
                self.assertEqual({attrs["data-design-link"] for attrs in switcher}, set(builder.VARIANTS))
                self.assertEqual(sum(attrs.get("aria-current") == "page" for attrs in switcher), 1)
                if variant in {"ribbon", "studio"}:
                    self.assertIn("station-design-experiments.css", source)
                if variant == "folio":
                    self.assertIn("station-design-folio.css", source)
                if variant == "studio":
                    html = next(attrs for tag, attrs in document.tags if tag == "html")
                    self.assertIn("design-studio", html.get("class", ""))
                self.assertIn('name="robots" content="noindex, nofollow"', source)
                for tag, attrs in document.tags:
                    reference = attrs.get("src") if tag == "script" else attrs.get("href")
                    if not reference:
                        continue
                    url = urlsplit(reference)
                    if not url.scheme and url.path:
                        self.assertTrue((ROADMAP / url.path).is_file(), reference)

    def test_preview_renderer_is_reproducible_and_storage_is_isolated(self):
        source = (ROADMAP / "generated/station-design-preview.app.js").read_text()
        self.assertEqual(source, builder.preview_renderer())
        self.assertNotIn("localStorage.getItem", source)
        self.assertNotIn("localStorage.setItem", source)
        self.assertIn('var prefix = "cpp_course_design_preview_v1:";', source)
        self.assertIn('window.sessionStorage.setItem(prefix + key', source)
        self.assertIn('["focus", "ribbon", "folio"].indexOf(window.COURSE_DESIGN_VARIANT) >= 0 ? false', source)
        self.assertIn('var readerPilot = true;', source)
        self.assertNotIn(': "Станция 15"),', source)

    def test_highlighter_is_local_pinned_and_only_loaded_by_studio(self):
        directory = ROADMAP / "vendor/highlightjs"
        origin = json.loads((directory / "ORIGIN.json").read_text())
        self.assertEqual(origin["version"], "11.12.0")
        self.assertEqual(origin["license"], "BSD-3-Clause")
        for name, record in origin["files"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), record["sha256"])
        for variant in builder.VARIANTS:
            source = (ROADMAP / f"design_station0_{variant}.html").read_text()
            with self.subTest(variant=variant):
                self.assertEqual("vendor/highlightjs/highlight.min.js" in source, variant == "studio")
                self.assertEqual("assets/station-design-syntax.css" in source, variant == "studio")
                if variant == "studio":
                    self.assertLess(source.index("vendor/highlightjs/highlight.min.js"),
                                    source.index("generated/station-design-preview.app.js"))

    def test_production_uses_shared_reader_but_previews_are_not_published(self):
        from build_publication import collect
        app = (ROADMAP / "assets/station-app.js").read_text()
        self.assertIn('var readerPilot = true;', app)
        self.assertNotIn("COURSE_DESIGN_VARIANT", app)
        original = (ROADMAP / "cpp_station0_oop_basics.html").read_text()
        self.assertIn('class="course-reader', original)
        self.assertNotIn("station-design", original)
        files, _ = collect()
        self.assertFalse(any("design_station0_" in name or "design-preview" in name or "station-design-variants" in name
                             for name in files))
        self.assertFalse(any("station-design-experiments" in name or "station-design-folio" in name
                             for name in files))
        self.assertTrue(any("vendor/highlightjs/highlight.min.js" in name for name in files))
        self.assertFalse(any("station-design-syntax" in name for name in files))


if __name__ == "__main__":
    unittest.main()
