"""Readability source contracts for the course's dark laboratory surfaces.

These checks inspect shipped HTML/CSS and calculate contrast for the explicit
palette pairs. They do not compute a browser cascade, render a screenshot, or
certify layout, font rasterization, zoom, or assistive-technology behavior.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Element:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children = []

    @property
    def classes(self):
        return set(self.attrs.get("class", "").split())

    def descendants(self):
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.descendants()

    def text(self):
        return "".join(child.text() if isinstance(child, Element) else child
                       for child in self.children)


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.current = self.root
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        child = Element(tag, attrs, self.current)
        self.current.children.append(child)
        if tag not in self.VOID:
            self.current = child

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, attrs, self.current))

    def handle_endtag(self, tag):
        current = self.current
        while current is not self.root:
            if current.tag == tag:
                self.current = current.parent
                return
            current = current.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def find(self, *, tag=None, cls=None, ident=None):
        return [node for node in self.root.descendants()
                if (tag is None or node.tag == tag)
                and (cls is None or cls in node.classes)
                and (ident is None or node.attrs.get("id") == ident)]


def contrast(foreground, background):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045
                  else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(value * factor for value, factor in zip(linear, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + .05) / (dark + .05)


def style_rules(source):
    """Leaf declaration blocks only, for named source contracts, not matching.

    The selected course declarations contain no nested functions with braces.
    Media rules retain their source ordering. This is deliberately not a CSS
    parser or a selector/specificity engine.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    records = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", source):
        selector = " ".join(match.group(1).split())
        declarations = dict((name.strip(), value.strip())
                            for name, value in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)", match.group(2)))
        records.append((selector, declarations))
    return records


class LabReadability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.theme = (ROOT / "assets/course-theme.css").read_text()
        cls.surfaces = (ROOT / "assets/course-dark-surfaces.css").read_text()
        cls.reader = (ROOT / "assets/course-dark-reader.css").read_text()
        cls.station_map = (ROOT / "assets/station-map.css").read_text()
        cls.app = (ROOT / "assets/station-app.js").read_text()
        cls.tokens = dict(re.findall(r"(--course-[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", cls.theme))
        cls.rules = style_rules(cls.surfaces)

    def source_declaration(self, selector, property_name, expected):
        """Require a named rule exactly as shipped; do not resolve its cascade."""
        self.assertTrue(any(candidate == selector and declarations.get(property_name) == expected
                            for candidate, declarations in self.rules),
                        f"Missing source contract: {selector} {{ {property_name}: {expected}; }}")

    def source_font_floor(self, selector_fragment, minimum):
        sizes = []
        for selector, declarations in self.rules:
            if selector_fragment not in selector or "font-size" not in declarations:
                continue
            value = declarations["font-size"]
            if re.fullmatch(r"\d+(?:\.\d+)?px", value):
                sizes.append(float(value[:-2]))
        self.assertTrue(sizes, "Missing explicit font contract for " + selector_fragment)
        self.assertGreaterEqual(min(sizes), minimum,
                                f"A source rule shrinks {selector_fragment} below {minimum}px")

    def source_fragment_declaration(self, selector_fragment, property_name, expected):
        """Guard a selected child in an explicitly scoped grouped selector."""
        self.assertTrue(any(selector_fragment in candidate and ".course-" in candidate
                            and declarations.get(property_name) == expected
                            for candidate, declarations in self.rules),
                        f"Missing qualified child contract for {selector_fragment}: {property_name}={expected}")

    def test_explicit_reading_and_state_palette_pairs_have_text_contrast(self):
        # Actual shared token values, not a claim that every DOM node inherits
        # these colors. Separate selector contracts guard the reported cases.
        for foreground in ("ink", "muted", "accent"):
            for background in ("canvas", "surface", "surface-raised", "code"):
                with self.subTest(foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(self.tokens["--course-" + foreground],
                                                     self.tokens["--course-" + background]), 4.5)
        for tone in ("success", "warning", "danger"):
            with self.subTest(tone=tone):
                self.assertGreaterEqual(contrast(self.tokens["--course-" + tone],
                                                 self.tokens["--course-" + tone + "-soft"]), 4.5)
        self.assertGreaterEqual(contrast(self.tokens["--course-canvas"],
                                         self.tokens["--course-accent"]), 4.5)

    def test_selected_code_line_keeps_muted_annotations_readable(self):
        # The active row previously lowered muted annotation contrast to 4.44.
        # Test both actual row backgrounds, not only the shared base palette.
        for selector in (".course-support .lab-code-line.active",
                         ".course-page-lifetime .code-line.current"):
            backgrounds = [declarations["background"] for candidate, declarations in self.rules
                           if candidate == selector and "background" in declarations]
            self.assertTrue(backgrounds, selector)
            with self.subTest(selector=selector):
                self.assertRegex(backgrounds[-1], r"^#[0-9a-fA-F]{6}$")
                for token in ("--course-ink", "--course-muted"):
                    self.assertGreaterEqual(contrast(self.tokens[token], backgrounds[-1]), 4.5)

    def test_lifetime_introduction_contract_targets_the_real_heading(self):
        doc = Document((ROOT / "object_lifetime_demo.html").read_text())
        intro, = doc.find(cls="lab-introduction")
        heading, = [node for node in intro.descendants() if node.tag == "h2"]
        self.assertEqual(heading.attrs["id"], "introTitle")
        self.assertEqual(heading.text(), "Что здесь происходит")
        self.assertTrue(any("intro-boundary" in node.classes for node in intro.descendants()))
        self.assertTrue(doc.find(cls="experiment-copy"))
        # The new declarations are checked below after the legacy mobile styles
        # have been loaded; the HTML's old light intro must not be used as-is.
        styles = [node.attrs.get("href", "") for node in doc.find(tag="link")
                  if node.attrs.get("rel") == "stylesheet"]
        self.assertIn("course-dark-surfaces.css", styles[-1])

    def test_lifetime_reading_surface_and_small_screen_floors(self):
        self.source_declaration(".course-page-lifetime .lab-introduction", "background", "var(--course-surface)")
        self.source_declaration(".course-page-lifetime .lab-introduction", "color", "var(--course-ink)")
        self.source_declaration(".course-page-lifetime .lab-introduction h2", "color", "var(--course-ink)")
        self.source_declaration(".course-page-lifetime .lab-introduction p", "color", "var(--course-ink)")
        self.source_declaration(".course-page-lifetime .lab-introduction .intro-boundary", "color", "var(--course-muted)")
        # The formerly dark-green strong is explicitly assigned an accessible
        # accent; only its reported rule is tested, not every possible state.
        emphasis = [(selector, declaration) for selector, declaration in self.rules
                    if ".experiment-copy strong" in selector]
        self.assertTrue(any(declaration.get("color") == "var(--course-accent)"
                            for _, declaration in emphasis))
        for fragment, minimum in ((".lab-introduction h2", 22), (".lab-introduction p", 17),
                                  (".lab-introduction .intro-boundary", 16),
                                  (".course-page-lifetime .code-line", 15),
                                  (".course-page-lifetime .insight p", 18)):
            with self.subTest(selector=fragment):
                self.source_font_floor(fragment, minimum)
        self.assertTrue(".experiment-copy" in self.surfaces and "max-width: 72ch" in self.surfaces)

    def test_other_lab_families_have_explicit_reading_and_code_sizes(self):
        for fragment, minimum in ((".lab-hero p", 17), (".lab-primer-copy p", 17),
                                  (".lab-primer-instructions p", 17), (".lab-insight p", 17),
                                  (".course-support .lab-rule", 16), (".lab-code-line", 15),
                                  (".course-page-sql :is(textarea,pre)", 15),
                                  (".course-page-sql :is(.muted,footer)", 16),
                                  (".instruction span", 17), (".model-result p", 17),
                                  (".reading-notes p", 18), (".boundary-note p", 17),
                                  (".course-page-workshop :is(pre", 15),
                                  (".course-page-workshop .command-place", 14)):
            with self.subTest(selector=fragment):
                self.source_font_floor(fragment, minimum)
        for selector in (".course-page-sql", ".course-page-workshop"):
            self.source_declaration(selector, "font-size", "18px")
        self.assertTrue("@media (max-width: 1100px)" in self.surfaces)
        for selector in (".course-page-lifetime .workspace", ".course-page-visual-labs .lab-workspace"):
            self.assertTrue(any(selector in candidate and declarations.get("grid-template-columns") == "minmax(0,1fr)"
                                for candidate, declarations in self.rules), selector)

    def test_explicit_children_do_not_keep_legacy_light_theme_colors(self):
        for fragment, property_name, expected in (
                (".lab-primer-copy p", "color", "var(--course-ink)"),
                (".lab-primer-instructions p", "color", "var(--course-ink)"),
                (".lab-insight p", "color", "var(--course-muted)"),
                (".lab-rule", "color", "var(--course-muted)"),
                (".lab-scene .node text", "fill", "var(--course-ink)"),
                (".node.dead text", "fill", "var(--course-muted)"),
                (".code-context code", "color", "var(--course-muted)"),
                (".experiment-copy strong", "color", "var(--course-accent)"),
                (".output-line.new .output-no", "color", "var(--course-accent)"),
                (".request-path", "color", "var(--course-muted)"),
                (".instruction strong", "color", "var(--course-ink)"),
                (".orientation-copy strong", "color", "var(--course-ink)"),
                (".instruction span", "color", "var(--course-muted)"),
                (".model-result p", "color", "var(--course-muted)"),
                (".guide-context code", "color", "#cee8f4"),
                (".course-page-sql textarea", "color", "var(--course-ink)"),
                (".command.remote .command-place", "color", "var(--course-accent)")):
            with self.subTest(selector=fragment):
                self.source_fragment_declaration(fragment, property_name, expected)

    def test_laboratory_styles_follow_each_pages_legacy_mobile_rules(self):
        # New qualified rules live after legacy sheets/inline styles, so the
        # old lab's 9–12px mobile declarations are not the last stylesheet.
        for filename in ("visual_labs.html", "object_lifetime_demo.html", "sql_trainer.html",
                         "security_labs.html", "security_sql_demo.html", "service_workshop.html"):
            doc = Document((ROOT / filename).read_text())
            links = [node.attrs.get("href", "") for node in doc.find(tag="link")
                     if node.attrs.get("rel") == "stylesheet"]
            with self.subTest(page=filename):
                self.assertTrue(links)
                self.assertTrue("course-dark-surfaces.css" in links[-1])
                self.assertEqual(len([href for href in links if "course-dark-surfaces.css" in href]), 1)

    def test_lab_headers_keep_native_catalog_links_with_decorative_flasks(self):
        for filename in ("visual_labs.html", "object_lifetime_demo.html",
                         "security_labs.html", "security_sql_demo.html",
                         "sql_trainer.html", "service_workshop.html"):
            doc = Document((ROOT / filename).read_text())
            with self.subTest(page=filename):
                links = [node for node in doc.find(tag="a")
                         if node.attrs.get("href") == "visual_labs.html"
                         and ("lab-catalog-link" in node.classes or "lab-brand" in node.classes)]
                self.assertTrue(links, "Expected a visible, native catalog navigation link")
                self.assertTrue(any("Все лаборатории" in node.text() for node in links))
                for link in links:
                    icons = [node for node in link.descendants()
                             if node.tag == "svg" and "lab-flask" in node.classes]
                    self.assertTrue(icons)
                    for icon in icons:
                        self.assertEqual(icon.attrs.get("aria-hidden"), "true")
                        self.assertEqual(icon.attrs.get("focusable"), "false")
                        self.assertEqual(icon.attrs.get("viewbox"), "0 0 24 24")
                        self.assertEqual(icon.attrs.get("width"), "24")
                        self.assertEqual(icon.attrs.get("height"), "24")
                        self.assertFalse(icon.text().strip())
                self.assertNotIn("onclick", links[0].attrs)
                self.assertNotIn("hidden", links[0].attrs)

    def test_finale_remains_native_navigation_with_a_prominent_hook(self):
        for needle in ('stationMapLink("#view=final"', 'className: "map-finish"',
                       '"Завершение станции"', 'href: "visual_labs.html"', "lab-flask"):
            self.assertTrue(needle in self.app, "station-app.js missing " + needle)
        for needle in (".map-finish strong", ".map-finish .map-marker",
                       ".map-finish:hover strong", ".map-finish.is-current .map-marker"):
            self.assertTrue(needle in self.station_map, "station-map.css missing " + needle)
        rules = dict(style_rules(self.station_map))
        title = rules["body.course-map .map-finish strong"]
        self.assertGreaterEqual(float(title["font-size"].removesuffix("px")), 16)
        self.assertGreaterEqual(contrast(title["color"], self.tokens["--course-paper"]), 4.5)
        marker = rules["body.course-map .map-finish .map-marker"]
        self.assertGreaterEqual(contrast(marker["color"], marker["background"]), 4.5)


if __name__ == "__main__":
    unittest.main()
