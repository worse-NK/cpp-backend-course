#!/usr/bin/env python3
"""Editorial candidates, not an automatic measure of assessment quality.

Different numeric/code answers may naturally have different lengths. This tool
flags conspicuously over-explained keys for human review, never pads alternatives
or changes an answer mechanically. See Waterloo CTE's MCQ design guide.
"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def questions():
    for path in sorted((ROOT / "content").glob("station*.json")):
        station = json.loads(path.read_text())
        for bank, entries in station["quizzes"].items():
            for index, question in enumerate(entries):
                yield f"{path.stem}/{bank}/{index}", question
    for path in sorted((ROOT / "content/checkpoints").glob("station*.json")):
        for module, entries in json.loads(path.read_text())["modules"].items():
            for index, question in enumerate(entries):
                if "options" in question:
                    yield f"{path.stem}/checkpoint/{module}/{index}", question
    page = (ROOT / "cpp_basic_level.html").read_text()
    topics = json.loads(re.search(r'<script id="topics-data"[^>]*>(.*?)</script>', page, re.S)[1])
    for topic in topics:
        for index, question in enumerate(topic["questions"]):
            yield f"basic/{topic['id']}/{index}", question


def audit():
    candidates, totals = [], {"questions": 0, "unique_longest_key": 0}
    for identifier, question in questions():
        totals["questions"] += 1
        options, answer = question["options"], question["answer"]
        lengths = [len(re.sub(r"\s+", " ", option).strip()) for option in options]
        others = [n for i, n in enumerate(lengths) if i != answer]
        unique_longest = lengths[answer] > max(others)
        totals["unique_longest_key"] += int(unique_longest)
        reasons = []
        if unique_longest and lengths[answer] >= 45 and lengths[answer] >= max(others) * 1.7:
            reasons.append("key at least 70% longer than every distractor")
        # Exclude parentheses used as code call syntax; look for prose inside.
        prose_parentheses = [bool(re.search(r"\([^)]*[А-Яа-я][^)]*\)", o)) for o in options]
        if prose_parentheses[answer] and sum(prose_parentheses) == 1:
            reasons.append("only the key has a parenthetical explanation")
        if reasons:
            candidates.append({"id": identifier, "reasons": reasons, "q": question["q"],
                               "options": options, "answer": answer})
    return {"notice": "Human-review candidates; length parity alone does not make a good question.",
            "totals": totals, "candidates": candidates}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.summary:
        report = {"totals": report["totals"], "candidates": len(report["candidates"])}
    print(json.dumps(report, ensure_ascii=False, indent=2))
