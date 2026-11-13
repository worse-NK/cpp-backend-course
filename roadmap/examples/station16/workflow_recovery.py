#!/usr/bin/env python3
"""Local teaching model: two SQLite files, no network or real payment."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

MARKER = "course-station16-workflow-model-v1"
PAYMENT_KEY = "pay:731"
AMOUNT = 2500


@contextmanager
def connect(directory: Path, name: str):
    if (directory / ".course-model").read_text(encoding="utf-8") != MARKER:
        raise RuntimeError("not an initialized course model")
    target = directory / name
    if target.is_symlink() or not target.is_file():
        raise RuntimeError("expected an existing regular model database")
    db = sqlite3.connect(target)
    try:
        with db:
            yield db
    finally:
        db.close()


def charge(directory: Path, key: str, amount: int) -> int:
    with connect(directory, "provider.db") as db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute(
            "SELECT payment_id, amount FROM payments WHERE command_id = ?",
            (key,),
        ).fetchone()
        if old is not None:
            if old[1] != amount:
                raise ValueError("same payment key with different amount")
            return int(old[0])
        result = db.execute(
            "INSERT INTO payments(command_id, amount) VALUES (?, ?)",
            (key, amount),
        )
        return int(result.lastrowid)


def worker(directory: Path, action: str) -> int:
    if action not in {"lost-reply", "recover"}:
        raise ValueError("unknown worker action")
    with connect(directory, "orders.db") as db:
        key, amount = db.execute(
            "SELECT payment_key, amount FROM orders WHERE order_id = 731"
        ).fetchone()

    payment_id = charge(directory, key, amount)
    # charge() committed the provider transaction before returning.
    if action == "lost-reply":
        print("worker: provider committed; orders still pending", flush=True)
        return 75  # intentional stop before saving the result at orders
    with connect(directory, "orders.db") as db:
        db.execute(
            "UPDATE orders SET state = 'paid', payment_id = ? "
            "WHERE order_id = 731 AND payment_key = ?",
            (payment_id, key),
        )
    print(f"worker: recovered {key} as payment {payment_id}", flush=True)
    return 0


def snapshot(directory: Path) -> dict:
    with connect(directory, "orders.db") as db:
        state, payment_id = db.execute(
            "SELECT state, payment_id FROM orders WHERE order_id = 731"
        ).fetchone()
    with connect(directory, "provider.db") as db:
        count, total = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM payments"
        ).fetchone()
    return {"state": state, "payment_id": payment_id,
            "payments": count, "total": total}


def run_child(directory: Path, action: str, expected: int) -> None:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()),
         "--worker", str(directory), action],
        check=False, text=True, capture_output=True, timeout=15,
    )
    if result.returncode != expected:
        raise RuntimeError(f"worker failed: {result.returncode}: {result.stderr}")
    print(result.stdout, end="")


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        return worker(Path(sys.argv[2]), sys.argv[3])
    if len(sys.argv) != 1:
        raise SystemExit("Run this example without arguments.")

    # The model creates and removes only its own private temporary directory.
    with tempfile.TemporaryDirectory(prefix="course-s16-workflow-") as path:
        directory = Path(path)
        (directory / ".course-model").write_text(MARKER, encoding="utf-8")
        with closing(sqlite3.connect(directory / "orders.db")) as db, db:
            db.execute(
                "CREATE TABLE orders(order_id INTEGER PRIMARY KEY, "
                "state TEXT NOT NULL, payment_key TEXT NOT NULL UNIQUE, "
                "amount INTEGER NOT NULL, payment_id INTEGER)"
            )
            db.execute(
                "INSERT INTO orders VALUES (731, 'pay_pending', ?, ?, NULL)",
                (PAYMENT_KEY, AMOUNT),
            )
        with closing(sqlite3.connect(directory / "provider.db")) as db, db:
            db.execute(
                "CREATE TABLE payments(payment_id INTEGER PRIMARY KEY, "
                "command_id TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL)"
            )

        before = snapshot(directory)
        run_child(directory, "lost-reply", 75)
        unknown = snapshot(directory)
        run_child(directory, "recover", 0)
        recovered = snapshot(directory)
        run_child(directory, "recover", 0)
        repeated = snapshot(directory)

        rejected = False
        try:
            charge(directory, PAYMENT_KEY, AMOUNT + 1)
        except ValueError:
            rejected = True

        assert before == {"state": "pay_pending", "payment_id": None,
                          "payments": 0, "total": 0}
        assert unknown == {"state": "pay_pending", "payment_id": None,
                           "payments": 1, "total": AMOUNT}
        assert recovered == {"state": "paid", "payment_id": 1,
                             "payments": 1, "total": AMOUNT}
        assert repeated == recovered and rejected
        evidence = {"scope": "local-sqlite-model-no-network",
                    "before": before, "unknown_outcome": unknown,
                    "after_recovery": recovered, "after_repeat": repeated,
                    "changed_amount_rejected": rejected}
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
