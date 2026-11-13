#!/usr/bin/env python3
"""Check a small report's shape. Never apply policy or certify its truth."""
import argparse
import json
from pathlib import Path

LIMIT = 65536
SCHEMAS = {
    "outbound-policy": {
        "scope": str, "purpose": str, "destination_selection": str,
        "allowed_services": list, "allowed_scheme": str, "allowed_port": int,
        "dns_policy": str, "connect_policy": str, "redirect_policy": str,
        "max_redirects": int, "deadline_ms": int, "max_response_bytes": int,
        "enforcement": str,
    },
    "delivery-policy": {
        "scope": str, "runtime_user": str, "docker_socket": bool,
        "runtime_owns_schema": bool, "runtime_can_assume_migration": bool,
        "secrets_in_image": bool, "untrusted_ci_has_release_secrets": bool,
        "dependency_pin": str, "rotation_checks": list, "release_evidence": list,
    },
    "network-evidence": {"scope": str, "observations": list, "not_tested": list},
    "release-evidence": {"scope": str, "changes": list, "not_tested": list},
}


def require_fields(data, schema):
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект")
    for key, expected in schema.items():
        if key not in data or type(data[key]) is not expected:
            raise ValueError(f"Отсутствует поле нужного типа: {key}")


def validate(kind, data):
    require_fields(data, SCHEMAS[kind])
    if kind in ("outbound-policy", "delivery-policy"):
        if data["scope"] != "training-policy-not-applied":
            raise ValueError("Шаблон политики должен сохранять учебную область not-applied")
    if kind == "outbound-policy":
        if data["enforcement"] != "not-applied":
            raise ValueError("Этот файл сам не применяет политику")
        for key in ("allowed_port", "deadline_ms", "max_response_bytes"):
            if data[key] <= 0:
                raise ValueError(f"Нужно положительное число: {key}")
        if data["max_redirects"] < 0:
            raise ValueError("max_redirects не может быть отрицательным")
    if kind == "network-evidence":
        if data["scope"] != "synthetic-only":
            raise ValueError("Для этого опыта требуется область synthetic-only")
        if not data["observations"]:
            raise ValueError("Нужно хотя бы одно наблюдение")
        for observation in data["observations"]:
            require_fields(observation, {key: str for key in (
                "case", "weak_strategy", "weak_decision", "every_hop_decision", "trace_reason")})
    if kind == "release-evidence":
        if data["scope"] != "review-only-no-runtime":
            raise ValueError("Этот отчёт не проверяет рабочую среду")
        if not data["changes"]:
            raise ValueError("Нужно хотя бы одно изменение")
        for change in data["changes"]:
            require_fields(change, {"field": str, "reason": str})
            if "before" not in change or "after" not in change:
                raise ValueError("В изменении нужны before и after")
    for key in ("not_tested", "allowed_services", "rotation_checks", "release_evidence"):
        if key in data and any(not isinstance(v, str) or not v.strip() for v in data[key]):
            raise ValueError(f"В списке нужны непустые строки: {key}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=SCHEMAS)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        # Bound both disk input and allocation; do not load an arbitrarily big report.
        with args.report.open("rb") as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Отчёт больше 64 КиБ")
        def reject_constant(_value):
            raise ValueError("Нестандартное числовое значение JSON")
        validate(args.kind, json.loads(raw, parse_constant=reject_constant))
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        parser.exit(1, "Не прошла проверка формата, типов или учебной области. Проверь шаблон; содержимое файла не выводится.\n")
    print("PASS: формат учебного файла. Политика не применена; достоверность отчёта и безопасность среды не проверены.")


if __name__ == "__main__":
    main()
