#!/usr/bin/env python3
"""Compile only the reviewed reader examples and compare their complete stdout.

Use --station station0 for a quick local check. CXX20 and CXX23 may name
different compilers; unsupported configurations are failures, not silent skips.
Never invoked by opening the page, publishing it, or building a Debian package.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_listing_outputs import CONTENT, digest, plan, reading_sections
from cpp_examples import load_manifest, check_case, probe


def checks(stations):
    versioned, legacy = plan()
    cases, _ = load_manifest()
    by_id = {c["exampleId"]: c for c in cases if "exampleId" in c}
    for station in sorted(stations):
        data = json.loads((CONTENT / (station + ".json")).read_text())
        reading_sections(station, data["theory"])  # validate the actual reader path
        for section in data["theory"]:
            for b in section["blocks"]:
                if b["type"] != "code":
                    continue
                key = section["id"], digest(b["code"])
                name = f"{station}/{section['id']}:{key[1][:8]}"
                if key in legacy.get(station, {}):
                    yield name, b["code"], {"standard": "20", "mode": "run",
                                              "flags": ["-pthread"], "stdout": legacy[station][key]}
                elif b.get("exampleId") in versioned:
                    case = by_id[b["exampleId"]]
                    for check in case["checks"]:
                        if check["mode"] == "run":
                            dirs = ["-I" + str(CONTENT.parent / d) for d in case.get("includeDirs", [])]
                            yield name, b["code"], dict(check, flags=check.get("flags", []) + dirs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", action="append", choices=sorted(p.stem for p in CONTENT.glob("station*.json")))
    parser.add_argument("--jobs", type=int, default=2, choices=range(1, 9), metavar="1..8")
    options = parser.parse_args()
    selected = options.station or [p.stem for p in CONTENT.glob("station*.json")]
    rows = list(checks(selected))
    profiles = {}
    for standard in {check["standard"] for _, _, check in rows}:
        compiler = os.environ.get("CXX" + standard, os.environ.get("CXX", "g++"))
        binary = shutil.which(compiler)
        if not binary:
            parser.error(f"C++{standard}: compiler not found: {compiler}")
        binary = str(Path(binary).absolute())
        profiles[standard] = binary, *probe(binary, standard)

    def run(row):
        label, source, check = row
        try:
            compiler, macros, error = profiles[check["standard"]]
            status, detail = check_case(compiler, source, check, macros, error)
        except subprocess.TimeoutExpired:
            status, detail = "FAIL", "compile/run timed out"
        return status, f"{label} C++{check['standard']} — {detail}"

    failures = []
    with ThreadPoolExecutor(max_workers=options.jobs) as pool:
        for status, detail in pool.map(run, rows):
            if status != "PASS":
                failures.append(f"{status}: {detail}")
    if failures:
        print("\n".join(failures))
    print(f"{len({name for name, _, _ in rows})} listings; {len(rows) - len(failures)}/{len(rows)} output checks passed")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
