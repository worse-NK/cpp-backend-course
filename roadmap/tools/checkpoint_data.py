"""Resolve dedicated chapter assessments without changing historical quiz banks."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[1] / "content"


def normalize_prompt(value: str) -> str:
    return " ".join(value.split()).casefold()


def with_checkpoints(data: dict, directory: Path | None = None) -> dict:
    """Validate source plans and return a separate browser-ready station object.

    References reserve existing, non-final questions; inline entries are new
    questions. Neither canonical station data nor shared bank entries are mutated.
    Version each module by resolved content, so a three-question legacy attempt
    (or a changed answer) can never masquerade as a current completed checkpoint.
    """
    path = (directory or CONTENT / "checkpoints") / (data["meta"]["id"] + ".json")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(plan, dict) or set(plan) != {"version", "modules"}
            or type(plan["version"]) is not int or plan["version"] != 1):
        raise ValueError(f"{path}: expected checkpoint plan version 1")
    modules = {m["id"] for m in data["substations"]}
    if not isinstance(plan["modules"], dict) or set(plan["modules"]) != modules:
        raise ValueError(f"{path}: checkpoint modules must match the station")
    section_ids = {s["id"] for s in data["theory"]}
    module_order = {m["id"]: i for i, m in enumerate(data["substations"])}
    section_modules = {s["id"]: s["substation"] for s in data["theory"]}
    resolved, versions, seen = {}, {}, set()
    for module, entries in plan["modules"].items():
        if not isinstance(entries, list) or len(entries) < 5:
            raise ValueError(f"{path}/{module}: at least five questions required")
        questions = []
        for index, entry in enumerate(entries):
            where = f"{path}/{module}[{index}]"
            if not isinstance(entry, dict):
                raise ValueError(f"{where}: expected question or bank reference")
            if set(entry) == {"bank", "index"}:
                bank, position = entry["bank"], entry["index"]
                if (bank not in {"basic", "advanced"} or type(position) is not int
                        or not 0 <= position < len(data["quizzes"][bank])):
                    raise ValueError(f"{where}: invalid bank reference")
                question = copy.deepcopy(data["quizzes"][bank][position])
            else:
                question = copy.deepcopy(entry)
            common = {"level", "q", "answer", "why", "theoryRefs", "substation"}
            assembly = question.get("type") == "assemble"
            expected = common | ({"type", "tokens", "before", "after"} if assembly else {"options"})
            if set(question) != expected:
                raise ValueError(f"{where}: unexpected question fields {set(question) ^ expected}")
            if question["substation"] != module or question["level"] not in {"easy", "medium", "hard"}:
                raise ValueError(f"{where}: invalid module or difficulty")
            for field in ("q", "why"):
                if not isinstance(question[field], str) or not question[field].strip():
                    raise ValueError(f"{where}: missing {field}")
            refs = question["theoryRefs"]
            if (not isinstance(refs, list) or not refs or len(refs) != len(set(refs))
                    or not all(isinstance(ref, str) and ref in section_ids for ref in refs)):
                raise ValueError(f"{where}: unknown or missing theory references")
            if any(module_order[section_modules[ref]] > module_order[module] for ref in refs):
                raise ValueError(f"{where}: requires a later subchapter")
            stem = normalize_prompt(question["q"])
            if stem in seen:
                raise ValueError(f"{where}: repeated checkpoint question")
            seen.add(stem)
            if assembly:
                tokens, answer = question["tokens"], question["answer"]
                if (not isinstance(tokens, list) or not 3 <= len(tokens) <= 24
                        or not all(isinstance(token, str) and token.strip() for token in tokens)
                        or not isinstance(answer, list) or not answer
                        or not all(type(i) is int and 0 <= i < len(tokens) for i in answer)
                        or len(answer) != len(set(answer))
                        or not all(isinstance(question[f], str) for f in ("before", "after"))):
                    raise ValueError(f"{where}: invalid assembly tokens or answer")
            else:
                options, answer = question["options"], question["answer"]
                if (not isinstance(options, list) or not 2 <= len(options) <= 6
                        or not all(isinstance(o, str) and o.strip() for o in options)
                        or len(set(options)) != len(options)
                        or type(answer) is not int or not 0 <= answer < len(options)):
                    raise ValueError(f"{where}: invalid alternatives or answer")
            questions.append(question)
        resolved[module] = questions
        versions[module] = hashlib.sha256(json.dumps(
            questions, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    # Optional training uses both complete banks.  Authored positions stay
    # stable, but a result for a former question must not label its replacement
    # as already attempted.  This is build metadata, not a new progress store.
    training = {kind: data['quizzes'].get(kind, []) for kind in ('basic', 'advanced')}
    training_version = hashlib.sha256(json.dumps(
        training, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return dict(data, checkpoints=resolved, checkpointVersion=versions,
                trainingVersion=training_version)
