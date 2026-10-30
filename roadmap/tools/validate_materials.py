#!/usr/bin/env python3
"""Validate embedded roadmap, basic-test and cheat-sheet data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROADMAP = Path(__file__).resolve().parents[1]
SCRIPT_PATTERN = re.compile(
    r'<script\b[^>]*\bid=["\'](?P<id>[^"\']+)["\'][^>]*>(?P<body>.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def require_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: expected a non-empty string")
    return value


def require_exact_keys(value: object, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValueError(f"{where}: expected keys {sorted(keys)}, got {actual}")
    return value


def embedded_json(path: Path, script_id: str) -> Any:
    matches = [
        match.group("body")
        for match in SCRIPT_PATTERN.finditer(path.read_text(encoding="utf-8"))
        if match.group("id") == script_id
    ]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one script #{script_id}, got {len(matches)}")
    try:
        return json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON in #{script_id}: {error}") from error


def validate_question(raw: object, where: str, seen: set[str]) -> None:
    question = require_exact_keys(
        raw, {"level", "q", "options", "answer", "why"}, where
    )
    if question["level"] not in {"easy", "medium", "hard"}:
        raise ValueError(f"{where}.level: unknown level {question['level']!r}")
    prompt = require_text(question["q"], f"{where}.q")
    normalized = " ".join(prompt.split()).casefold()
    if normalized in seen:
        raise ValueError(f"{where}.q: duplicate prompt")
    seen.add(normalized)

    options = question["options"]
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"{where}.options: expected at least two choices")
    normalized_options: set[str] = set()
    for index, option in enumerate(options, 1):
        text = require_text(option, f"{where}.options[{index}]")
        # Case can be the substance of an answer (for example, "HELLO" vs "Hello").
        normalized_option = " ".join(text.split())
        if normalized_option in normalized_options:
            raise ValueError(f"{where}.options[{index}]: duplicate choice")
        normalized_options.add(normalized_option)

    answer = question["answer"]
    if (
        not isinstance(answer, int)
        or isinstance(answer, bool)
        or not 0 <= answer < len(options)
    ):
        raise ValueError(f"{where}.answer: index outside options")
    require_text(question["why"], f"{where}.why")


def validate_task(raw: object, where: str) -> None:
    task = require_exact_keys(
        raw, {"title", "brief", "hints", "solution", "notes", "level"}, where
    )
    for key in ("title", "brief", "solution", "notes", "level"):
        require_text(task[key], f"{where}.{key}")
    hints = task["hints"]
    if not isinstance(hints, list) or not hints:
        raise ValueError(f"{where}.hints: expected a non-empty list")
    for index, hint in enumerate(hints, 1):
        require_text(hint, f"{where}.hints[{index}]")


def validate_basic() -> tuple[int, int, int]:
    path = ROADMAP / "cpp_basic_level.html"
    topics = embedded_json(path, "topics-data")
    reference = embedded_json(path, "reference-data")
    if not isinstance(topics, list) or not topics:
        raise ValueError(f"{path}: topics-data must be a non-empty list")

    ids: set[str] = set()
    numbers: set[int] = set()
    prompts: set[str] = set()
    task_titles: set[str] = set()
    question_count = 0
    for topic_index, raw_topic in enumerate(topics, 1):
        where = f"{path}: topic #{topic_index}"
        topic = require_exact_keys(
            raw_topic, {"id", "title", "questions", "task", "task2", "num"}, where
        )
        topic_id = require_text(topic["id"], f"{where}.id")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", topic_id):
            raise ValueError(f"{where}.id: invalid identifier")
        if topic_id in ids:
            raise ValueError(f"{where}.id: duplicate {topic_id!r}")
        ids.add(topic_id)
        require_text(topic["title"], f"{where}.title")
        number = topic["num"]
        if not isinstance(number, int) or isinstance(number, bool) or number in numbers:
            raise ValueError(f"{where}.num: expected a unique integer")
        numbers.add(number)

        questions = topic["questions"]
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"{where}.questions: expected a non-empty list")
        for question_index, question in enumerate(questions, 1):
            validate_question(
                question, f"{where}, question #{question_index}", prompts
            )
        question_count += len(questions)
        for key in ("task", "task2"):
            validate_task(topic[key], f"{where}.{key}")
            title = topic[key]["title"]
            if title in task_titles:
                raise ValueError(f"{where}.{key}.title: duplicate {title!r}")
            task_titles.add(title)

    expected_numbers = set(range(min(numbers), min(numbers) + len(numbers)))
    if numbers != expected_numbers:
        raise ValueError(f"{path}: topic numbers must be contiguous")

    if not isinstance(reference, list) or not reference:
        raise ValueError(f"{path}: reference-data must be a non-empty list")
    groups: set[str] = set()
    reference_names: set[str] = set()
    reference_count = 0
    for group_index, raw_group in enumerate(reference, 1):
        where = f"{path}: reference group #{group_index}"
        group = require_exact_keys(raw_group, {"group", "items"}, where)
        group_name = require_text(group["group"], f"{where}.group")
        if group_name in groups:
            raise ValueError(f"{where}.group: duplicate {group_name!r}")
        groups.add(group_name)
        items = group["items"]
        if not isinstance(items, list) or not items:
            raise ValueError(f"{where}.items: expected a non-empty list")
        for item_index, raw_item in enumerate(items, 1):
            item_where = f"{where}, item #{item_index}"
            item = require_exact_keys(raw_item, {"name", "desc", "ex"}, item_where)
            name = require_text(item["name"], f"{item_where}.name")
            if name in reference_names:
                raise ValueError(f"{item_where}.name: duplicate {name!r}")
            reference_names.add(name)
            require_text(item["desc"], f"{item_where}.desc")
            require_text(item["ex"], f"{item_where}.ex")
        reference_count += len(items)

    return question_count, len(task_titles), reference_count


def validate_cheatsheet() -> tuple[int, int, int]:
    path = ROADMAP / "cpp_cheatsheet.html"
    data = require_exact_keys(
        embedded_json(path, "cheat-data"), {"title", "subtitle", "stations"}, str(path)
    )
    require_text(data["title"], f"{path}: title")
    require_text(data["subtitle"], f"{path}: subtitle")
    stations = data["stations"]
    if not isinstance(stations, list) or not stations:
        raise ValueError(f"{path}: stations must be a non-empty list")

    station_numbers: set[str] = set()
    section_count = 0
    item_count = 0
    for station_index, raw_station in enumerate(stations, 1):
        where = f"{path}: cheat station #{station_index}"
        station = require_exact_keys(
            raw_station, {"num", "title", "color", "sections"}, where
        )
        number = require_text(station["num"], f"{where}.num")
        if number in station_numbers:
            raise ValueError(f"{where}.num: duplicate {number!r}")
        station_numbers.add(number)
        require_text(station["title"], f"{where}.title")
        color = require_text(station["color"], f"{where}.color")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            raise ValueError(f"{where}.color: expected #RRGGBB")

        sections = station["sections"]
        if not isinstance(sections, list) or not sections:
            raise ValueError(f"{where}.sections: expected a non-empty list")
        section_names: set[str] = set()
        for section_index, raw_section in enumerate(sections, 1):
            section_where = f"{where}, section #{section_index}"
            section = require_exact_keys(raw_section, {"h", "items"}, section_where)
            heading = require_text(section["h"], f"{section_where}.h")
            if heading in section_names:
                raise ValueError(f"{section_where}.h: duplicate {heading!r}")
            section_names.add(heading)
            items = section["items"]
            if not isinstance(items, list) or not items:
                raise ValueError(f"{section_where}.items: expected a non-empty list")
            for item_index, raw_item in enumerate(items, 1):
                item_where = f"{section_where}, item #{item_index}"
                if not isinstance(raw_item, dict):
                    raise ValueError(f"{item_where}: expected an object")
                if not {"t"} <= set(raw_item) <= {"t", "rule", "code"}:
                    raise ValueError(f"{item_where}: invalid keys {sorted(raw_item)}")
                require_text(raw_item["t"], f"{item_where}.t")
                if "rule" not in raw_item and "code" not in raw_item:
                    raise ValueError(f"{item_where}: expected rule or code")
                for key in ("rule", "code"):
                    if key in raw_item:
                        require_text(raw_item[key], f"{item_where}.{key}")
            item_count += len(items)
        section_count += len(sections)

    return len(stations), section_count, item_count


def validate_roadmap() -> tuple[int, int]:
    path = ROADMAP / "cpp_backend_roadmap.html"
    data = require_exact_keys(
        embedded_json(path, "roadmap-data"),
        {"title", "subtitle", "intro", "stages", "closing", "bonusFiles"},
        str(path),
    )
    for key in ("title", "subtitle", "intro", "closing"):
        require_text(data[key], f"{path}: {key}")
    stages = data["stages"]
    if not isinstance(stages, list) or not stages:
        raise ValueError(f"{path}: stages must be a non-empty list")

    station_sources: dict[str, tuple[Path, dict[str, Any]]] = {}
    for source_path in sorted((ROADMAP / "content").glob("station*.json")):
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source_file = source.get("meta", {}).get("sourceFile")
        if isinstance(source_file, str):
            station_sources[source_file] = (source_path, source)

    stage_ids: set[str] = set()
    station_files: set[str] = set()
    ready = 0
    for index, stage in enumerate(stages, 1):
        where = f"{path}: stage #{index}"
        if not isinstance(stage, dict):
            raise ValueError(f"{where}: expected an object")
        stage_id = require_text(stage.get("id"), f"{where}.id")
        if "optional" in stage and not isinstance(stage["optional"], bool):
            raise ValueError(f"{where}.optional: expected a boolean")
        if stage_id in stage_ids:
            raise ValueError(f"{where}.id: duplicate {stage_id!r}")
        stage_ids.add(stage_id)
        require_text(stage.get("title"), f"{where}.title")
        station = stage.get("station")
        if station is None:
            continue
        station = require_exact_keys(
            station, {"file", "storeKey", "totalSections", "label"},
            f"{where}.station",
        )
        station_file = require_text(station["file"], f"{where}.station.file")
        if station_file in station_files:
            raise ValueError(f"{where}.station.file: duplicate {station_file!r}")
        station_files.add(station_file)
        if station_file not in station_sources:
            raise ValueError(f"{where}.station.file: no matching content source")
        source_path, source = station_sources[station_file]
        if station["storeKey"] != source["meta"]["storeKey"]:
            raise ValueError(f"{where}.station.storeKey: differs from {source_path}")
        expected_sections = len(source["theory"])
        if station["totalSections"] != expected_sections:
            raise ValueError(
                f"{where}.station.totalSections: expected {expected_sections}"
            )
        if not (ROADMAP / station_file).is_file():
            raise ValueError(f"{where}.station.file: generated HTML is missing")
        ready += 1

    return len(stages), ready


def validate_station_sources() -> tuple[int, int, int, int, int]:
    """Validate the shared station schema and substation coverage.

    build_stations.py validates this too, but keeping the checks in the normal
    validation command prevents hand-edited content/roadmap drift from passing.
    """
    station_count = 0
    theory_count = 0
    question_count = 0
    task_count = 0
    source_note_count = 0

    for path in sorted((ROADMAP / "content").glob("station*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        from checkpoint_data import with_checkpoints
        with_checkpoints(data)
        where = str(path)
        substations = data.get("substations", [])
        if not isinstance(substations, list) or not substations:
            raise ValueError(f"{where}: substations must be a non-empty list")
        substation_ids = {
            require_text(item.get("id"), f"{where}: substation.id")
            for item in substations
            if isinstance(item, dict)
        }
        if len(substation_ids) != len(substations):
            raise ValueError(f"{where}: duplicate or invalid substation id")

        theory = data.get("theory")
        if not isinstance(theory, list) or not theory:
            raise ValueError(f"{where}: theory must be a non-empty list")
        theory_ids: set[str] = set()
        theory_coverage: set[str] = set()
        source_coverage: set[str] = set()
        checkpoint_coverage: set[str] = set()
        for index, section in enumerate(theory, 1):
            section_where = f"{where}: theory #{index}"
            if not isinstance(section, dict):
                raise ValueError(f"{section_where}: expected an object")
            section_id = require_text(section.get("id"), f"{section_where}.id")
            if section_id in theory_ids:
                raise ValueError(f"{section_where}.id: duplicate {section_id!r}")
            theory_ids.add(section_id)
            substation = require_text(
                section.get("substation"), f"{section_where}.substation"
            )
            if substation not in substation_ids:
                raise ValueError(f"{section_where}: unknown substation {substation!r}")
            theory_coverage.add(substation)
            require_text(section.get("title"), f"{section_where}.title")
            require_text(section.get("lead"), f"{section_where}.lead")
            blocks = section.get("blocks")
            if not isinstance(blocks, list) or not blocks:
                raise ValueError(f"{section_where}.blocks: expected a non-empty list")
            for block_index, block in enumerate(blocks, 1):
                if not isinstance(block, dict):
                    raise ValueError(
                        f"{section_where}.blocks[{block_index}]: expected an object"
                    )
                html = block.get("html", "")
                if isinstance(html, str) and re.search(r"Первичные источники\b", html):
                    source_coverage.add(substation)
                    source_note_count += 1
                if isinstance(html, str) and "Контрольная точка " in html:
                    checkpoint_coverage.add(substation)

        if theory_coverage != substation_ids:
            raise ValueError(f"{where}: theory does not cover every substation")
        # Stations 0-5 use one primary-source note per substation. Later
        # chapters have their own source layout and remain build-validated.
        number = data.get("meta", {}).get("number")
        if isinstance(number, int) and number <= 5:
            if source_coverage != substation_ids:
                missing = sorted(substation_ids - source_coverage)
                raise ValueError(f"{where}: missing primary sources for {missing}")
            if checkpoint_coverage != substation_ids:
                missing = sorted(substation_ids - checkpoint_coverage)
                raise ValueError(f"{where}: missing checkpoints for {missing}")

        quizzes = data.get("quizzes")
        if not isinstance(quizzes, dict):
            raise ValueError(f"{where}: quizzes must be an object")
        quiz_coverage: dict[str, set[str]] = {}
        prompts: set[str] = set()
        for kind in ("basic", "advanced", "interview"):
            questions = quizzes.get(kind)
            if not isinstance(questions, list) or not questions:
                raise ValueError(f"{where}: quiz {kind!r} must be non-empty")
            coverage: set[str] = set()
            for index, question in enumerate(questions, 1):
                question_where = f"{where}: {kind} question #{index}"
                if not isinstance(question, dict):
                    raise ValueError(f"{question_where}: expected an object")
                prompt = require_text(question.get("q"), f"{question_where}.q")
                normalized = " ".join(prompt.split()).casefold()
                if normalized in prompts:
                    raise ValueError(f"{question_where}: duplicate prompt")
                prompts.add(normalized)
                substation = require_text(
                    question.get("substation"), f"{question_where}.substation"
                )
                if substation not in substation_ids:
                    raise ValueError(
                        f"{question_where}: unknown substation {substation!r}"
                    )
                coverage.add(substation)
                options = question.get("options")
                answer = question.get("answer")
                if not isinstance(options, list) or len(options) < 2:
                    raise ValueError(f"{question_where}.options: expected choices")
                if not isinstance(answer, int) or not 0 <= answer < len(options):
                    raise ValueError(f"{question_where}.answer: outside choices")
                require_text(question.get("why"), f"{question_where}.why")
            quiz_coverage[kind] = coverage
            question_count += len(questions)
        for kind, coverage in quiz_coverage.items():
            if coverage != substation_ids:
                missing = sorted(substation_ids - coverage)
                raise ValueError(f"{where}: {kind} quiz misses {missing}")

        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"{where}: tasks must be a non-empty list")
        task_coverage: set[str] = set()
        for index, task in enumerate(tasks, 1):
            task_where = f"{where}: task #{index}"
            if not isinstance(task, dict):
                raise ValueError(f"{task_where}: expected an object")
            substation = require_text(
                task.get("substation"), f"{task_where}.substation"
            )
            if substation not in substation_ids:
                raise ValueError(f"{task_where}: unknown substation {substation!r}")
            task_coverage.add(substation)
            checks = task.get("checks")
            if isinstance(number, int) and number <= 5:
                if not isinstance(checks, list) or not checks:
                    raise ValueError(f"{task_where}.checks: expected a non-empty list")
                for check_index, check in enumerate(checks, 1):
                    require_text(check, f"{task_where}.checks[{check_index}]")
        if task_coverage != substation_ids:
            missing = sorted(substation_ids - task_coverage)
            raise ValueError(f"{where}: tasks miss {missing}")

        station_count += 1
        theory_count += len(theory)
        task_count += len(tasks)

    return station_count, theory_count, question_count, task_count, source_note_count


def main() -> None:
    questions, tasks, reference = validate_basic()
    stations, sections, items = validate_cheatsheet()
    roadmap_stages, ready_stations = validate_roadmap()
    station_count, theory, station_questions, station_tasks, source_notes = (
        validate_station_sources()
    )
    print(
        f"basic: {questions} questions, {tasks} tasks, "
        f"{reference} reference entries"
    )
    print(f"cheatsheet: {stations} groups, {sections} sections, {items} items")
    print(f"roadmap: {roadmap_stages} stages, {ready_stations} ready stations")
    print(
        f"stations: {station_count} sources, {theory} theory sections, "
        f"{station_questions} questions, {station_tasks} tasks, "
        f"{source_notes} primary-source notes"
    )


if __name__ == "__main__":
    main()
