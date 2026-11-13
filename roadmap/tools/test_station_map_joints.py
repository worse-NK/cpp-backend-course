"""Shared station connectors: CSS geometry and coverage, not browser pixels."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import unittest
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from build_stations import html_for, load_json


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "assets/station-map-joints.css").read_text()


def declarations(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    if not match:
        raise AssertionError("Missing CSS selector: " + selector)
    return dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);", match.group(1)))


def length(expression, variables):
    """Evaluate the connector arithmetic without evaluating arbitrary Python."""
    expression = re.sub(r"var\((--[\w-]+)\)",
                        lambda match: str(variables[match.group(1)]), expression)
    expression = expression.removeprefix("calc(").removesuffix(")")
    expression = expression.replace("px", "")

    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -visit(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise AssertionError("Unexpected CSS arithmetic: " + expression)

    return visit(ast.parse(expression, mode="eval").body)


class StationMapJoints(unittest.TestCase):
    # Mobile base; desktop clamp; 800/700px compact modes; fractional dvh sizes.
    sizes = [(51, 84, 27, 28), (44, 70, 30, 8), (44, 68, 26, 8),
             (44, 60, 26, 5), (54, 90, 30, 16),
             (44.1, 72, 30, 12.6), (47.285, 77.2, 30, 13.51)]

    @staticmethod
    def variables(node, row, offset, gap):
        variables = {"--trail-node-size": node, "--trail-row-height": row,
                     "--trail-offset": offset, "--trail-step-gap": gap}
        body = declarations("body.course-map")
        for name in ("--trail-stroke", "--trail-slot-inset", "--trail-curve-height"):
            variables[name] = length(body[name], variables)
        return variables

    @staticmethod
    def curve():
        mask = declarations("body.course-map")["--trail-curve-mask"]
        svg = ET.fromstring(unquote(mask.removeprefix('url("data:image/svg+xml,').removesuffix('")')))
        path = svg.find("{http://www.w3.org/2000/svg}path")
        numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", path.attrib["d"])]
        return svg, path, list(zip(numbers[::2], numbers[1::2]))

    def test_curve_has_vertical_tangents_not_an_l_shaped_tail(self):
        svg, path, (start, control1, control2, end) = self.curve()
        self.assertRegex(path.attrib["d"], r"^M[\d. ]+ C[\d. ]+$")
        self.assertEqual(start[0], control1[0])
        self.assertEqual(control2[0], end[0])
        self.assertGreater(control1[1], start[1])
        self.assertGreater(end[1], control2[1])
        self.assertEqual(svg.attrib["preserveAspectRatio"], "none")
        self.assertEqual(path.attrib["vector-effect"], "non-scaling-stroke")
        self.assertEqual(float(path.attrib["stroke-width"]), 3)
        self.assertEqual(declarations("body.course-map .map-chapter::after")["mask-mode"], "alpha")

    def test_mirrored_curve_endpoints_and_stem_share_marker_axes(self):
        main = declarations("body.course-map .map-chapter::after")
        even = declarations("body.course-map .map-chapter:nth-child(even)::after")
        stem = declarations("body.course-map .map-chapter::before")
        svg, _, points = self.curve()
        view_width = float(svg.attrib["viewBox"].split()[2])
        for node, row, offset, gap in self.sizes:
            with self.subTest(node=node, row=row, offset=offset):
                variables = self.variables(node, row, offset, gap)
                width = length(main["width"], variables)
                odd_left = length(main["left"], variables)
                even_left = length(even["left"], variables)
                x_start, x_end = (points[index][0] / view_width for index in (0, 3))
                self.assertAlmostEqual(odd_left + width * x_start, node / 2)
                self.assertAlmostEqual(odd_left + width * x_end, offset + node / 2)
                self.assertAlmostEqual(offset + even_left + width * (1 - x_start), offset + node / 2)
                self.assertAlmostEqual(offset + even_left + width * (1 - x_end), node / 2)
                self.assertAlmostEqual(length(stem["left"], variables) + 1.5, node / 2)
                self.assertGreater(width * x_start, 1.5)  # The mask cannot clip its stroke.
        self.assertEqual(main["transform"], "none")
        self.assertEqual(even["transform"], "scaleX(-1)")

    def test_wrapping_and_expansion_extend_only_the_straight_stem(self):
        marker = declarations("body.course-map .map-chapter-link > .map-marker")
        main = declarations("body.course-map .map-chapter::after")
        stem = declarations("body.course-map .map-chapter::before")
        self.assertEqual(marker["align-self"], "start")
        self.assertEqual(declarations("body.course-map .map-chapter-toggle")["padding-block"], "0")
        for node, row, offset, gap in self.sizes:
            variables = self.variables(node, row, offset, gap)
            marker_top = length(marker["margin-top"], variables)
            curve_height = length(main["height"], variables)
            self.assertAlmostEqual(marker_top, (row - node) / 2)
            self.assertGreater(curve_height, 0)
            for extra_header in (0, 35, row * 1.5):
                for branch_height in (0, 200, 1200):
                    with self.subTest(node=node, row=row, extra=extra_header, branch=branch_height):
                        chapter_height = row + extra_header + branch_height + gap
                        stem_start = length(stem["top"], variables)
                        stem_end = chapter_height - length(stem["bottom"], variables)
                        curve_end = chapter_height - length(main["bottom"], variables)
                        self.assertAlmostEqual(stem_start, marker_top + node)
                        self.assertAlmostEqual(stem_end, curve_end - curve_height)
                        self.assertAlmostEqual(curve_end, chapter_height + marker_top)
                        self.assertAlmostEqual(stem_end - stem_start, extra_header + branch_height)

    def test_old_borders_are_removed_and_last_branch_has_no_outgoing_curve(self):
        chapter = declarations("body.course-map .map-chapter")
        main = declarations("body.course-map .map-chapter::after")
        even = declarations("body.course-map .map-chapter:nth-child(even)::after")
        stem = declarations("body.course-map .map-chapter::before")
        self.assertEqual(chapter["--chapter-track"], "var(--map-track)")
        self.assertEqual(main["background"], "var(--chapter-track)")
        self.assertEqual(stem["background"], "var(--chapter-track)")
        self.assertEqual(declarations("body.course-map .map-chapter.is-complete")["--chapter-track"], "#5f9980")
        self.assertEqual(declarations("body.course-map .map-lessons::before")["display"], "none")
        for rule in (main, even):
            self.assertEqual(rule["border"], "0")
            self.assertEqual(rule["border-radius"], "0")
        self.assertEqual(main["top"], "auto")
        self.assertEqual(declarations("body.course-map .map-chapter:last-child::after")["display"], "none")
        self.assertEqual(declarations("body.course-map .map-chapter:last-child:not(.is-expanded)::before")["display"], "none")
        branch = declarations("body.course-map .map-chapter:last-child.is-expanded::before")
        self.assertEqual(length(branch["bottom"], {"--trail-step-gap": 16}), 22)

    def test_ticks_are_centered_on_topics_and_checkpoint(self):
        tick = declarations("body.course-map .map-lesson::before")["top"]
        for selector, padding in (("body.course-map .map-lesson", 9),
                                  ("body.course-map .map-checkpoint", 13)):
            variables = {"--topic-top-padding": padding}
            self.assertEqual(length(declarations(selector)["--topic-top-padding"], {}), padding)
            self.assertAlmostEqual(length(tick, variables) + 0.5, padding + 4 + 13 / 2)

    def test_all_stations_load_one_shared_connector_after_base_map(self):
        sources = sorted((ROOT / "content").glob("station*.json"))
        self.assertEqual(len(sources), 21)
        expected = "assets/station-map-joints.css?v=" + hashlib.sha256(
            (ROOT / "assets/station-map-joints.css").read_bytes()).hexdigest()[:12]
        for source in sources:
            with self.subTest(station=source.stem):
                data = load_json(source)
                generated = (ROOT / data["meta"]["sourceFile"]).read_text()
                for html in (html_for(data), generated):
                    links = re.findall(r'href="(assets/station-map-joints\.css\?v=[a-f0-9]{12})"', html)
                    self.assertEqual(links, [expected])
                    self.assertGreater(html.index(links[0]), html.index("assets/station-map.css?"))


if __name__ == "__main__":
    unittest.main()
