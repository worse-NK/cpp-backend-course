"""Bind reviewed examples to saved stdout, without compiling anything during a build.

Only code in theory is eligible. Quiz answers, arbitrary snippets and commands
are not inspected. Source hashes intentionally require a fresh editorial check
when a listed program changes. The author can run verify_listing_outputs.py.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

CONTENT = Path(__file__).resolve().parents[1] / "content"
OUTPUT_CAPTION = re.compile(r'^(?:(?:точный|ожидаемый|проверенный) вывод\b|вывод\b)', re.I)


def digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def plan():
    data = json.loads((CONTENT / "listing-outputs.json").read_text(encoding="utf-8"))
    if set(data) != {"version", "cppManifestListings", "cxx20Listings"} or data["version"] != 1:
        raise ValueError("Unknown listing output plan")
    manifest = json.loads((CONTENT / "cpp-examples.json").read_text(encoding="utf-8"))
    cases = {c["exampleId"]: c for c in manifest["examples"] if "exampleId" in c}
    reviewed = {}
    for record in data["cppManifestListings"]:
        if set(record) != {"exampleId", "sha256"}:
            raise ValueError("A reviewed listing requires an exampleId and a SHA-256 digest")
        identifier, source_hash = record["exampleId"], record["sha256"]
        if identifier in reviewed or not re.fullmatch(r'[a-f0-9]{64}', source_hash):
            raise ValueError(f"{identifier}: invalid or duplicate review record")
        case = cases[identifier]
        if "before" in case or "after" in case:
            raise ValueError(f"{identifier}: test wrappers are not the displayed program")
        checks = [c for c in case["checks"] if c["mode"] == "run"]
        if not checks or any(not isinstance(c.get("stdout"), str) for c in checks):
            raise ValueError(f"{identifier}: exact stdout required for every run")
        results = {(c.get("stdin"), c["stdout"]) for c in checks}
        if len(results) != 1:
            raise ValueError(f"{identifier}: cannot present different results as one")
        stdin, stdout = results.pop()
        metadata = {"verifiedOutput": stdout,
                    "verifiedOutputStandard": "/".join(c["standard"] for c in checks)}
        if stdin is not None:
            metadata["verifiedInput"] = stdin
        reviewed[identifier] = source_hash, metadata

    per_station = {}
    for station, rows in data["cxx20Listings"].items():
        specs = {}
        for row in rows:
            if set(row) != {"section", "sha256", "stdout"} or not isinstance(row["stdout"], str):
                raise ValueError(f"{station}: invalid review record")
            key = row["section"], row["sha256"]
            if key in specs or not re.fullmatch(r'[a-f0-9]{64}', key[1]):
                raise ValueError(f"{station}: invalid or duplicate listing digest")
            specs[key] = row["stdout"]
        per_station[station] = specs
    return reviewed, per_station


def reading_sections(station: str, sections: list[dict]) -> list[dict]:
    reviewed, per_station = plan()
    specs = per_station.get(station, {})
    seen, result = set(), []
    for section in sections:
        blocks = []
        last_program = None
        for block in section["blocks"]:
            if block["type"] != "code":
                blocks.append(block)
                continue
            source = block["code"]
            key = section["id"], digest(source)
            identifier = block.get("exampleId")
            meta = None
            if identifier in reviewed:
                source_hash, meta = reviewed[identifier]
                if key[1] != source_hash:
                    raise ValueError(f"{station}/{key[0]}: changed {identifier}; review saved output")
            elif key in specs:
                if key in seen:
                    raise ValueError(f"{station}/{key[0]}: ambiguous source")
                seen.add(key)
                meta = {"verifiedOutput": specs[key], "verifiedOutputStandard": "20"}
            if meta is not None:
                last_program = dict(block, **meta)
                blocks.append(last_program)
            elif (last_program is not None and OUTPUT_CAPTION.match(block.get("caption", ""))
                  and last_program["verifiedOutput"].rstrip("\n") == source.rstrip("\n")):
                # Keep the authored instruction/qualification in the disclosure.
                # Do not remove a different branch, a terminal transcript, or prose.
                last_program["verifiedOutputCaption"] = block["caption"]
                last_program = None
            else:
                blocks.append(block)
                # A second program without verified stdout must not inherit a
                # previous program's result. A shell compile command is not one.
                if re.search(r"\bint\s+main\s*\(", source):
                    last_program = None
        result.append(dict(section, blocks=blocks))
    if set(specs) != seen:
        stale = ", ".join(sorted(s + ":" + h[:10] for s, h in set(specs) - seen))
        raise ValueError(f"{station}: changed/missing reviewed program: {stale}")
    return result
