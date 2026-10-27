#!/usr/bin/env python3
"""Validate station sources and build browser-ready data plus thin HTML shells."""

from __future__ import annotations

import hashlib
import argparse
import json
import re
from pathlib import Path


ROADMAP = Path(__file__).resolve().parents[1]
CONTENT = ROADMAP / "content"
GENERATED = ROADMAP / "generated"


ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> dict:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error


def require_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: expected a non-empty string")
    return value


def require_keys(value: object, keys: set[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValueError(f"{where}: expected keys {sorted(keys)}, got {actual}")
    return value


def validate(data: dict, path: Path) -> None:
    required = {"meta", "theory", "quizzes", "tasks"}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object")
    data_keys = set(data)
    if not required <= data_keys or not data_keys <= required | {"substations", "readingOrder"}:
        raise ValueError(f"{path}: invalid root keys {sorted(data_keys)}")

    meta_keys = {
        "id", "number", "storeKey", "logo", "title", "subtitle", "sourceFile"
    }
    meta = require_keys(data["meta"], meta_keys, f"{path}: meta")
    station_id = require_text(meta["id"], f"{path}: meta.id")
    if station_id != path.stem:
        raise ValueError(f"{path}: meta.id must equal source stem {path.stem!r}")
    if not isinstance(meta["number"], int) or isinstance(meta["number"], bool):
        raise ValueError(f"{path}: meta.number must be an integer")
    expected_number = int(path.stem.removeprefix("station").split('-')[0])
    if meta["number"] != expected_number:
        raise ValueError(f"{path}: meta.number must be {expected_number}")
    for key in ("storeKey", "logo", "title", "subtitle"):
        require_text(meta[key], f"{path}: meta.{key}")
    source_file = require_text(meta["sourceFile"], f"{path}: meta.sourceFile")
    if Path(source_file).name != source_file or Path(source_file).suffix != ".html":
        raise ValueError(f"{path}: sourceFile must be a plain .html filename")

    substation_ids: set[str] = set()
    if "substations" in data:
        substations = data["substations"]
        if not isinstance(substations, list) or len(substations) < 2:
            raise ValueError(f"{path}: substations must contain at least two entries")
        labels: set[str] = set()
        for index, raw_substation in enumerate(substations, 1):
            where = f"{path}: substation #{index}"
            substation = require_keys(
                raw_substation, {"id", "label", "title", "subtitle"}, where
            )
            substation_id = require_text(substation["id"], f"{where}.id")
            if not ID_PATTERN.fullmatch(substation_id) or substation_id in substation_ids:
                raise ValueError(f"{where}.id: expected a unique lowercase identifier")
            substation_ids.add(substation_id)
            label = require_text(substation["label"], f"{where}.label")
            if label in labels:
                raise ValueError(f"{where}.label: duplicate label")
            labels.add(label)
            require_text(substation["title"], f"{where}.title")
            require_text(substation["subtitle"], f"{where}.subtitle")

    theory = data["theory"]
    if "readingOrder" in data:
        route = data["readingOrder"]
        section_ids = [s.get("id") for s in theory if isinstance(s, dict)] if isinstance(theory, list) else []
        if (not isinstance(route, list) or not all(isinstance(id, str) for id in route)
                or len(route) != len(section_ids) or set(route) != set(section_ids)
                or len(route) != len(set(route))):
            raise ValueError(f"{path}: readingOrder must list every theory id exactly once")
    if not isinstance(theory, list) or not theory:
        raise ValueError(f"{path}: theory must be a non-empty list")
    ids: list[str] = []
    for section_index, raw_section in enumerate(theory, 1):
        where = f"{path}: theory section #{section_index}"
        if not isinstance(raw_section, dict):
            raise ValueError(f"{where}: expected an object")
        section_keys = set(raw_section)
        required_section_keys = {"id", "title", "lead", "blocks"}
        if (not required_section_keys <= section_keys
                or not section_keys <= required_section_keys | {"substation"}):
            raise ValueError(f"{where}: invalid keys {sorted(section_keys)}")
        section = raw_section
        if substation_ids:
            if section.get("substation") not in substation_ids:
                raise ValueError(f"{where}.substation: unknown or missing substation")
        elif "substation" in section:
            raise ValueError(f"{where}.substation: root has no substations")
        section_id = require_text(section["id"], f"{where}.id")
        if not ID_PATTERN.fullmatch(section_id):
            raise ValueError(f"{where}.id: use lowercase words separated by hyphens")
        ids.append(section_id)
        require_text(section["title"], f"{where}.title")
        require_text(section["lead"], f"{where}.lead")
        blocks = section["blocks"]
        if not isinstance(blocks, list) or not blocks:
            raise ValueError(f"{where}.blocks: expected a non-empty list")
        for block_index, raw_block in enumerate(blocks, 1):
            block_where = f"{where}, block #{block_index}"
            if not isinstance(raw_block, dict):
                raise ValueError(f"{block_where}: expected an object")
            block_type = raw_block.get("type")
            if block_type == "lab":
                block = require_keys(raw_block, {"type", "lab", "scenario"}, block_where)
                catalog = load_json(CONTENT / "visual-labs.json")["labs"]
                lab = next((lab for lab in catalog if lab["id"] == block["lab"]), None)
                if not lab or not any(
                    e["station"] == station_id and e["section"] == section_id
                    and e["scenario"] == block["scenario"] for e in lab["entries"]
                ):
                    raise ValueError(f"{block_where}: unknown lab or misplaced entry")
            elif block_type == "sql-trainer":
                block = require_keys(raw_block, {"type", "exercise"}, block_where)
                if meta["number"] != 9 or block["exercise"] not in {
                    "expression", "columns", "filter", "and", "null", "sort", "distinct",
                    "insert", "update", "delete", "join", "group", "left", "having"
                }:
                    raise ValueError(f"{block_where}: invalid SQL trainer exercise")
            elif block_type == "text":
                block = require_keys(raw_block, {"type", "html"}, block_where)
                require_text(block["html"], f"{block_where}.html")
            elif block_type == "self-check":
                block = require_keys(raw_block, {"type", "prompt", "answer"}, block_where)
                require_text(block["prompt"], f"{block_where}.prompt")
                require_text(block["answer"], f"{block_where}.answer")
            elif block_type == "code":
                allowed = ({"type", "code"}, {"type", "caption", "code"})
                if set(raw_block) not in allowed:
                    raise ValueError(f"{block_where}: invalid code block keys")
                require_text(raw_block["code"], f"{block_where}.code")
                if "caption" in raw_block:
                    require_text(raw_block["caption"], f"{block_where}.caption")
            elif block_type == "note":
                block = require_keys(raw_block, {"type", "kind", "html"}, block_where)
                if block["kind"] not in {"tip", "warn", "key"}:
                    raise ValueError(f"{block_where}.kind: unknown note kind")
                require_text(block["html"], f"{block_where}.html")
            elif block_type == "diagram":
                allowed = (
                    {"type", "title", "mode", "items"},
                    {"type", "title", "mode", "items", "caption"},
                )
                if set(raw_block) not in allowed:
                    raise ValueError(f"{block_where}: invalid diagram block keys")
                require_text(raw_block["title"], f"{block_where}.title")
                if raw_block["mode"] not in {"flow", "grid"}:
                    raise ValueError(f"{block_where}.mode: expected 'flow' or 'grid'")
                items = raw_block["items"]
                if not isinstance(items, list) or len(items) < 2:
                    raise ValueError(f"{block_where}.items: expected at least two items")
                for item_index, raw_item in enumerate(items, 1):
                    item_where = f"{block_where}, item #{item_index}"
                    item = require_keys(raw_item, {"title", "html"}, item_where)
                    require_text(item["title"], f"{item_where}.title")
                    require_text(item["html"], f"{item_where}.html")
                if "caption" in raw_block:
                    require_text(raw_block["caption"], f"{block_where}.caption")
            elif block_type == "visual":
                allowed = (
                    {"type", "variant", "title", "items"},
                    {"type", "variant", "title", "eyebrow", "items"},
                    {"type", "variant", "title", "items", "caption"},
                    {"type", "variant", "title", "eyebrow", "items", "caption"},
                )
                if set(raw_block) not in allowed:
                    raise ValueError(f"{block_where}: invalid visual block keys")
                if raw_block["variant"] not in {"flow", "layers", "sequence", "compare"}:
                    raise ValueError(f"{block_where}.variant: unknown visual variant")
                require_text(raw_block["title"], f"{block_where}.title")
                for optional_text in ("eyebrow", "caption"):
                    if optional_text in raw_block:
                        require_text(raw_block[optional_text], f"{block_where}.{optional_text}")
                items = raw_block["items"]
                if not isinstance(items, list) or len(items) < 2:
                    raise ValueError(f"{block_where}.items: expected at least two items")
                for item_index, raw_item in enumerate(items, 1):
                    item_where = f"{block_where}, item #{item_index}"
                    item = require_keys(raw_item, {"label", "title", "html"}, item_where)
                    for key in ("label", "title", "html"):
                        require_text(item[key], f"{item_where}.{key}")
            elif block_type == "packet":
                block = require_keys(
                    raw_block,
                    {"type", "title", "assumption", "payload", "layers", "caption"},
                    block_where,
                )
                for key in ("title", "assumption", "caption"):
                    require_text(block[key], f"{block_where}.{key}")
                payload = require_keys(
                    block["payload"], {"label", "bytes", "html"},
                    f"{block_where}.payload",
                )
                require_text(payload["label"], f"{block_where}.payload.label")
                require_text(payload["html"], f"{block_where}.payload.html")
                if not isinstance(payload["bytes"], int) or payload["bytes"] <= 0:
                    raise ValueError(f"{block_where}.payload.bytes: expected positive int")
                layers = block["layers"]
                if not isinstance(layers, list) or len(layers) < 2:
                    raise ValueError(f"{block_where}.layers: expected at least two layers")
                layer_keys = {"label", "title", "headerBytes", "trailerBytes", "result", "html"}
                for layer_index, raw_layer in enumerate(layers, 1):
                    layer_where = f"{block_where}, layer #{layer_index}"
                    layer = require_keys(raw_layer, layer_keys, layer_where)
                    for key in ("label", "title", "result", "html"):
                        require_text(layer[key], f"{layer_where}.{key}")
                    for key in ("headerBytes", "trailerBytes"):
                        if not isinstance(layer[key], int) or layer[key] < 0:
                            raise ValueError(f"{layer_where}.{key}: expected non-negative int")
                    if layer["headerBytes"] + layer["trailerBytes"] == 0:
                        raise ValueError(f"{layer_where}: layer must add bytes")
            elif block_type == "exchange":
                allowed = (
                    {"type", "title", "left", "right", "steps"},
                    {"type", "title", "left", "right", "steps", "caption"},
                )
                if set(raw_block) not in allowed:
                    raise ValueError(f"{block_where}: invalid exchange block keys")
                for key in ("title", "left", "right"):
                    require_text(raw_block[key], f"{block_where}.{key}")
                steps = raw_block["steps"]
                if not isinstance(steps, list) or len(steps) < 2:
                    raise ValueError(f"{block_where}.steps: expected at least two steps")
                for step_index, raw_step in enumerate(steps, 1):
                    step_where = f"{block_where}, step #{step_index}"
                    step = require_keys(raw_step, {"from", "label", "title", "html"}, step_where)
                    if step["from"] not in {"left", "right"}:
                        raise ValueError(f"{step_where}.from: expected left or right")
                    for key in ("label", "title", "html"):
                        require_text(step[key], f"{step_where}.{key}")
                if "caption" in raw_block:
                    require_text(raw_block["caption"], f"{block_where}.caption")
            elif block_type == "lanes":
                required = {"type", "title", "lanes"}
                if not required <= set(raw_block) <= required | {"caption", "mode"}:
                    raise ValueError(f"{block_where}: invalid lanes block keys")
                if raw_block.get("mode", "timeline") not in ("timeline", "fields"):
                    raise ValueError(f"{block_where}.mode: expected timeline or fields")
                require_text(raw_block["title"], f"{block_where}.title")
                lanes = raw_block["lanes"]
                if not isinstance(lanes, list) or len(lanes) < 2:
                    raise ValueError(f"{block_where}.lanes: expected at least two lanes")
                for lane_index, raw_lane in enumerate(lanes, 1):
                    lane_where = f"{block_where}, lane #{lane_index}"
                    lane = require_keys(raw_lane, {"label", "title", "segments", "html"}, lane_where)
                    for key in ("label", "title", "html"):
                        require_text(lane[key], f"{lane_where}.{key}")
                    segments = lane["segments"]
                    if not isinstance(segments, list) or not segments:
                        raise ValueError(f"{lane_where}.segments: expected non-empty list")
                    for segment_index, segment in enumerate(segments, 1):
                        require_text(segment, f"{lane_where}.segments[{segment_index}]")
                if "caption" in raw_block:
                    require_text(raw_block["caption"], f"{block_where}.caption")
            else:
                raise ValueError(f"{block_where}.type: unknown block type {block_type!r}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: theory section ids must be unique")

    quizzes = data["quizzes"]
    if not isinstance(quizzes, dict):
        raise ValueError(f"{path}: quizzes must be an object")
    quiz_kinds = set(quizzes)
    if not {"basic", "advanced"} <= quiz_kinds or not quiz_kinds <= {
        "basic", "advanced", "interview"
    }:
        raise ValueError(
            f"{path}: quizzes must contain basic/advanced and may contain interview"
        )
    theory_by_id = {section["id"]: section for section in theory}
    substation_order = {entry["id"]: index for index, entry in enumerate(data.get("substations", []))}
    seen_questions: set[str] = set()
    for kind in ("basic", "advanced", "interview"):
        if kind not in quizzes:
            continue
        questions = quizzes[kind]
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"{path}: quiz {kind!r} must not be empty")
        for index, raw_question in enumerate(questions, 1):
            where = f"{path}: {kind} question #{index}"
            if not isinstance(raw_question, dict):
                raise ValueError(f"{where}: expected an object")
            question_keys = set(raw_question)
            required_question_keys = {"level", "q", "options", "answer", "why"}
            if (not required_question_keys <= question_keys
                    or not question_keys <= required_question_keys | {"substation", "theoryRefs"}):
                raise ValueError(f"{where}: invalid keys {sorted(question_keys)}")
            question = raw_question
            if substation_ids:
                if question.get("substation") not in substation_ids:
                    raise ValueError(f"{where}.substation: unknown or missing substation")
            elif "substation" in question:
                raise ValueError(f"{where}.substation: root has no substations")
            if question["level"] not in {"easy", "medium", "hard"}:
                raise ValueError(f"{where}: invalid level")
            prompt = require_text(question["q"], f"{where}.q")
            normalized_prompt = " ".join(prompt.split())
            if normalized_prompt in seen_questions:
                raise ValueError(f"{where}: duplicate question text")
            seen_questions.add(normalized_prompt)
            options = question["options"]
            if not isinstance(options, list) or len(options) < 2:
                raise ValueError(f"{where}.options: expected at least two choices")
            for option_index, option in enumerate(options, 1):
                require_text(option, f"{where}.options[{option_index}]")
            if len(options) != len(set(options)):
                raise ValueError(f"{where}.options: choices must be unique")
            answer = question["answer"]
            if (not isinstance(answer, int) or isinstance(answer, bool)
                    or not 0 <= answer < len(options)):
                raise ValueError(f"{where}.answer: index is outside options")
            require_text(question["why"], f"{where}.why")
            # Every question must have traceable, already-introduced prerequisites.
            refs = question.get("theoryRefs")
            if not isinstance(refs, list) or not refs:
                raise ValueError(f"{where}.theoryRefs: expected a non-empty list")
            seen_refs: set[str] = set()
            for ref in refs:
                require_text(ref, f"{where}.theoryRefs")
                if ref not in theory_by_id or ref in seen_refs:
                    raise ValueError(f"{where}.theoryRefs: unknown or duplicate section {ref!r}")
                seen_refs.add(ref)
                if substation_ids:
                    target = theory_by_id[ref]["substation"]
                    if substation_order[target] > substation_order[question["substation"]]:
                        raise ValueError(f"{where}.theoryRefs: prerequisite {ref!r} is in a later substation")

    tasks = data["tasks"]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"{path}: tasks must be a non-empty list")
    task_titles: set[str] = set()
    for index, raw_task in enumerate(tasks, 1):
        where = f"{path}: task #{index}"
        if not isinstance(raw_task, dict):
            raise ValueError(f"{where}: expected an object")
        task_keys = set(raw_task)
        required_task_keys = {"level", "title", "brief", "hints", "solution", "notes", "theoryRefs", "solutionFormat"}
        if (not required_task_keys <= task_keys
                or not task_keys <= required_task_keys | {"checks", "substation", "code"}):
            raise ValueError(f"{where}: invalid task keys {sorted(task_keys)}")
        task = raw_task
        if task["solutionFormat"] not in ("text", "code"):
            raise ValueError(f"{where}.solutionFormat: expected text or code")
        refs = task["theoryRefs"]
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"{where}.theoryRefs: expected a non-empty list")
        seen_refs = set()
        for ref in refs:
            require_text(ref, f"{where}.theoryRefs")
            if ref not in ids or ref in seen_refs:
                raise ValueError(f"{where}.theoryRefs: unknown or duplicate section {ref!r}")
            seen_refs.add(ref)
        if substation_ids:
            if task.get("substation") not in substation_ids:
                raise ValueError(f"{where}.substation: unknown or missing substation")
        elif "substation" in task:
            raise ValueError(f"{where}.substation: root has no substations")
        for key in ("level", "title", "brief", "solution", "notes"):
            require_text(task[key], f"{where}.{key}")
        if "code" in task:
            require_text(task["code"], f"{where}.code")
        if task["title"] in task_titles:
            raise ValueError(f"{where}.title: duplicate task title")
        task_titles.add(task["title"])
        hints = task["hints"]
        if not isinstance(hints, list) or not hints:
            raise ValueError(f"{where}.hints: expected a non-empty list")
        for hint_index, hint in enumerate(hints, 1):
            require_text(hint, f"{where}.hints[{hint_index}]")
        if "checks" in task:
            checks = task["checks"]
            if not isinstance(checks, list) or len(checks) < 2:
                raise ValueError(f"{where}.checks: expected at least two items")
            for check_index, check in enumerate(checks, 1):
                require_text(check, f"{where}.checks[{check_index}]")

    if substation_ids:
        theory_coverage = {section["substation"] for section in theory}
        task_coverage = {task["substation"] for task in tasks}
        if theory_coverage != substation_ids:
            missing = sorted(substation_ids - theory_coverage)
            raise ValueError(f"{path}: substations without theory: {missing}")
        if task_coverage != substation_ids:
            missing = sorted(substation_ids - task_coverage)
            raise ValueError(f"{path}: substations without tasks: {missing}")
        for kind, questions in quizzes.items():
            quiz_coverage = {question["substation"] for question in questions}
            if quiz_coverage != substation_ids:
                missing = sorted(substation_ids - quiz_coverage)
                raise ValueError(
                    f"{path}: substations without {kind!r} questions: {missing}"
                )


def html_for(data: dict) -> str:
    from build_glossary import catalog_version
    if "checkpoints" not in data:
        from checkpoint_data import with_checkpoints
        data = with_checkpoints(data)
    meta = data["meta"]
    # A changed chapter or renderer must not reuse a browser's older cached
    # script. Fingerprints also work when two fixes ship on the same day.
    data_version = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    app_version = hashlib.sha256((ROADMAP / "assets/station-app.js").read_bytes()).hexdigest()[:12]
    title = meta["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    extra_css = '<link rel="stylesheet" href="assets/database-intro.css">' if meta["number"] == 9 else ""
    label = {"station5-linux": "5Б", "station7-netlab": "7Б", "station7-traffic": "7В"}.get(meta["id"], str(meta["number"]))
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Интерактивная станция {label} курса по backend-разработке на C++">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/station.css?v={hashlib.sha256((ROADMAP / 'assets/station.css').read_bytes()).hexdigest()[:12]}">
  <link rel="stylesheet" href="assets/terms.css?v=20261021">
{extra_css}
</head>
<body>
  <div id="root"><div class="fatal">Загрузка станции…</div></div>
  <noscript><div class="fatal">Для интерактивной станции нужен JavaScript.</div></noscript>
{'<script src="assets/database-route.js"></script>' if meta['number'] == 9 else ''}
  <script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>
  <script src="generated/{meta['id']}.data.js?v={data_version}"></script>
  <script src="generated/visual-labs.data.js"></script>
  <script src="generated/terms.data.js?v={catalog_version()}" defer></script>
  <script src="assets/terms-core.js?v=20261021" defer></script>
  <script src="assets/terms.js?v=20261021" defer></script>
  <script src="assets/station-app.js?v={app_version}"></script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", help="Build only this source id, for example station0")
    args = parser.parse_args()
    GENERATED.mkdir(exist_ok=True)
    from build_visual_labs import render as render_lab_catalog
    from build_glossary import render as render_glossary, render_data as render_term_data
    (GENERATED / "visual-labs.data.js").write_text(render_lab_catalog(), encoding="utf-8")
    (GENERATED / "terms.data.js").write_text(render_term_data(), encoding="utf-8")
    (ROADMAP / "glossary.html").write_text(render_glossary(), encoding="utf-8")
    paths = sorted(CONTENT.glob("station*.json"))
    if args.station:
        paths = [path for path in paths if path.stem == args.station]
    if not paths:
        raise SystemExit("No station sources found")
    station_ids: set[str] = set()
    output_files: set[str] = set()
    for path in paths:
        data = load_json(path)
        validate(data, path)
        from checkpoint_data import with_checkpoints
        data = with_checkpoints(data)
        meta = data["meta"]
        if meta["id"] in station_ids:
            raise ValueError(f"{path}: duplicate station id {meta['id']!r}")
        if meta["sourceFile"] in output_files:
            raise ValueError(f"{path}: duplicate output file {meta['sourceFile']!r}")
        station_ids.add(meta["id"])
        output_files.add(meta["sourceFile"])
        generated = "window.STATION_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
        (GENERATED / f"{meta['id']}.data.js").write_text(generated, encoding="utf-8")
        (ROADMAP / meta["sourceFile"]).write_text(html_for(data), encoding="utf-8")
        quiz_summary = " + ".join(
            f"{len(questions)} {kind}" for kind, questions in data["quizzes"].items()
        )
        print(f"built {meta['id']}: {quiz_summary} questions")


if __name__ == "__main__":
    main()
