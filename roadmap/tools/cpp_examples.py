#!/usr/bin/env python3
"""Version-aware course listings. No shell, package installation or network.

Unsupported features are reported separately and produce exit status 2, never
a successful silent skip. --require-supported makes them failures (CI profile).
Old station tests remain independent regression checks.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "content/cpp-examples.json"
IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MACRO = re.compile(r"__(?:cpp|GNUC|clang|GLIBCXX|LIBCPP)[A-Za-z0-9_]*\Z")


def listings() -> dict:
    result = {}
    for path in sorted((ROOT / "content").glob("station*.json")):
        data = json.loads(path.read_text())
        for section in data["theory"]:
            for block in section["blocks"]:
                if block.get("type") != "code" or "exampleId" not in block:
                    continue
                key = block["exampleId"]
                if key in result:
                    raise ValueError(f"duplicate exampleId: {key}")
                result[key] = (block, f"{path.stem}/{section['id']}")
    return result


def source_for(case: dict, indexed: dict) -> str:
    if "exampleId" in case:
        source = indexed[case["exampleId"]][0]["code"]
    else:
        relative = Path(case["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("example path must stay inside roadmap/")
        source = (ROOT / relative).read_text()
    return case.get("before", "") + source + case.get("after", "")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[list, dict]:
    document = json.loads(path.read_text())
    if set(document) != {"version", "examples"} or document["version"] != 1:
        raise ValueError("unsupported C++ example manifest")
    indexed, seen, covered = listings(), set(), set()
    cases = document["examples"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must contain examples")
    for case in cases:
        allowed = {"id", "exampleId", "path", "before", "after", "checks", "sources", "includeDirs"}
        if not {"id", "checks", "sources"} <= set(case) or not set(case) <= allowed:
            raise ValueError("invalid example keys")
        key = case["id"]
        if not IDENTIFIER.fullmatch(key) or key in seen:
            raise ValueError(f"invalid/duplicate case id: {key}")
        seen.add(key)
        if ("exampleId" in case) == ("path" in case):
            raise ValueError(f"{key}: select exactly one listing or file")
        if "exampleId" in case:
            if case["exampleId"] not in indexed:
                raise ValueError(f"{key}: missing listing")
            covered.add(case["exampleId"])
        source_for(case, indexed)
        for directory in case.get("includeDirs", []):
            relative = Path(directory)
            if relative.is_absolute() or ".." in relative.parts or not (ROOT / relative).is_dir():
                raise ValueError(f"{key}: include directory must stay inside roadmap/")
        if not case["sources"] or not all(isinstance(s, str) and s.startswith("https://") for s in case["sources"]):
            raise ValueError(f"{key}: primary sources required")
        if not isinstance(case["checks"], list) or not case["checks"]:
            raise ValueError(f"{key}: checks required")
        standards = set()
        for check in case["checks"]:
            allowed_check = {"standard", "mode", "stdin", "stdout", "requires", "flags", "linkFlags", "reason"}
            if not {"standard", "mode"} <= set(check) or not set(check) <= allowed_check:
                raise ValueError(f"{key}: invalid check keys")
            standard, mode = check["standard"], check["mode"]
            if standard not in {"20", "23"} or standard in standards:
                raise ValueError(f"{key}: invalid/duplicate standard")
            standards.add(standard)
            if mode not in {"run", "compile", "compile-fail", "source-only"}:
                raise ValueError(f"{key}: invalid check mode")
            if mode == "source-only" and not check.get("reason"):
                raise ValueError(f"{key}: source-only needs an explicit reason")
            if "stdout" in check and (mode != "run" or not isinstance(check["stdout"], str)):
                raise ValueError(f"{key}: stdout belongs to a run check")
            if "stdin" in check and (mode != "run" or not isinstance(check["stdin"], str)):
                raise ValueError(f"{key}: stdin belongs to a run check")
            for macro, minimum in check.get("requires", {}).items():
                if not MACRO.fullmatch(macro) or not isinstance(minimum, int) or isinstance(minimum, bool):
                    raise ValueError(f"{key}: invalid feature test")
            for flag in check.get("flags", []) + check.get("linkFlags", []):
                if not isinstance(flag, str) or not flag.startswith("-") or flag.startswith(("-o", "-std=", "-include", "-Xclang", "-fplugin")):
                    raise ValueError(f"{key}: disallowed flag {flag!r}")
    missing = set(indexed) - covered
    if missing:
        raise ValueError("identified listings missing from manifest: " + ", ".join(sorted(missing)))
    return cases, indexed


def invoke(args: list, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True, timeout=60, **kwargs)


def macro_number(value: str) -> int | None:
    match = re.fullmatch(r"\(?([0-9]+)[ULul]*\)?", value.strip())
    return int(match[1]) if match else None


def probe(compiler: str, standard: str) -> tuple[dict, str]:
    result = invoke([compiler, f"-std=c++{standard}", "-dM", "-E", "-x", "c++", "-"], input="#include <version>\n")
    macros = dict(re.findall(r"^#define (\w+) (.*)$", result.stdout, re.M))
    return macros, result.stderr if result.returncode else ""


def check_case(compiler: str, source: str, check: dict, macros: dict, probe_error: str = "") -> tuple[str, str]:
    if check["mode"] == "source-only":
        return "SOURCE_ONLY", check["reason"]
    if probe_error:
        return "UNSUPPORTED", probe_error
    for macro, minimum in check.get("requires", {}).items():
        actual = macro_number(macros.get(macro, ""))
        if actual is None or actual < minimum:
            return "UNSUPPORTED", f"{macro} >= {minimum} required; found {macros.get(macro, 'undefined')}"
    with tempfile.TemporaryDirectory(prefix="course-cxx-") as work:
        binary = str(Path(work) / "example")
        args = [compiler, f"-std=c++{check['standard']}", "-Wall", "-Wextra", "-pedantic-errors"]
        args += check.get("flags", []) + ["-x", "c++", "-"]
        args += ["-fsyntax-only"] if check["mode"] in {"compile", "compile-fail"} else ["-o", binary] + check.get("linkFlags", [])
        result = invoke(args, input=source)
        if result.returncode < 0:
            return "FAIL", f"compiler terminated by signal {-result.returncode}: {result.stderr}"
        if check["mode"] == "compile-fail":
            return ("PASS", "expected compilation failure") if result.returncode else ("FAIL", "unexpected compilation success")
        if result.returncode:
            return "FAIL", result.stderr
        if check["mode"] == "compile":
            return "PASS", "compiled; not executed"
        result = invoke([binary], input=check.get("stdin", ""))
        if result.returncode:
            return "FAIL", f"exit {result.returncode}: {result.stderr}"
        if "stdout" in check and result.stdout != check["stdout"]:
            return "FAIL", f"stdout: expected {check['stdout']!r}, got {result.stdout!r}"
        return "PASS", "compiled, linked and executed" + ("; stdout matched" if "stdout" in check else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"), help="one compiler executable, not a shell command")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--standard", choices=["20", "23"])
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--require-supported", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    cases, indexed = load_manifest(args.manifest)
    if args.only:
        unknown = set(args.only) - {c["id"] for c in cases}
        if unknown:
            parser.error("unknown examples: " + ", ".join(sorted(unknown)))
        cases = [c for c in cases if c["id"] in args.only]
    if args.validate_only:
        print(f"PASS: {len(cases)} manifest cases; {len(indexed)} stable theory listing IDs")
        return 0
    compiler = shutil.which(args.compiler)
    if not compiler:
        parser.error(f"compiler not found: {args.compiler}")
    identity = invoke([compiler, "--version"]).stdout.splitlines()[0]
    profiles, rows = {}, []
    for case in cases:
        for check in case["checks"]:
            standard = check["standard"]
            if args.standard and standard != args.standard:
                continue
            if standard not in profiles:
                macros, error = probe(compiler, standard)
                profiles[standard] = (macros, error)
            macros, error = profiles[standard]
            try:
                prepared = dict(check, flags=check.get("flags", []) + ["-I" + str(ROOT / d) for d in case.get("includeDirs", [])])
                status, detail = check_case(compiler, source_for(case, indexed), prepared, macros, error)
            except subprocess.TimeoutExpired:
                status, detail = "FAIL", "60-second compile/run timeout"
            row = {"id": case["id"], "standard": standard, "status": status, "detail": detail}
            rows.append(row)
            print(f"{status}: {case['id']} / C++{standard}: {detail}")
    if not rows:
        parser.error("selection contains no checks")
    runtime = {standard: {k: v for k, v in macros.items() if k in {"__cplusplus", "__GLIBCXX__", "_GLIBCXX_RELEASE", "_LIBCPP_VERSION", "__clang_major__", "__GNUC__", "__GNUC_MINOR__"}} for standard, (macros, _) in profiles.items()}
    report = {"compiler": compiler, "identity": identity, "profiles": runtime, "results": rows}
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    counts = {status: sum(r["status"] == status for r in rows) for status in ["PASS", "FAIL", "UNSUPPORTED", "SOURCE_ONLY"]}
    print(identity + "; " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    if counts["FAIL"] or args.require_supported and counts["UNSUPPORTED"]:
        return 1
    return 2 if counts["UNSUPPORTED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
