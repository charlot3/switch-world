#!/usr/bin/env python3
"""One-off repair for relationship rows written with display names.

Early live sessions called `world__update_relationship("Emily", ...)` instead of
`("emily", ...)`. The engine now normalises at the boundary, but existing databases
can still contain parallel rows such as `alice -> Emily` and `alice -> emily`. This
script folds each canonical pair back to one row.

Default is a dry run. Pass --apply to commit.

    python3 scripts/normalize-relationships.py
    python3 scripts/normalize-relationships.py --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "world.sqlite"


def canonical(value: str, ids: set[str], names: dict[str, str]) -> str | None:
    raw = str(value).strip()
    lowered = raw.lower()
    if lowered in {"user", "you", "the user", "me"}:
        return "user"
    if lowered in ids:
        return lowered
    for cid, name in names.items():
        if lowered == name.lower() or lowered == name.split()[0].lower():
            return cid
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    characters = [dict(row) for row in conn.execute("SELECT id, name FROM characters")]
    ids = {row["id"] for row in characters}
    names = {row["id"]: row["name"] for row in characters}
    rows = [dict(row) for row in conn.execute("SELECT * FROM relationships ORDER BY a, b")]

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    unreadable: list[dict] = []
    for row in rows:
        a = canonical(row["a"], ids, names)
        b = canonical(row["b"], ids, names)
        if a is None or b is None:
            unreadable.append(row)
            continue
        groups[(a, b)].append(row)

    changes: list[str] = []
    for (a, b), group in sorted(groups.items()):
        canonical_row = next((row for row in group if row["a"] == a and row["b"] == b), None)
        keep = canonical_row or max(group, key=lambda row: row["last_interaction"])
        latest = max(row["last_interaction"] for row in group)
        if keep["a"] != a or keep["b"] != b or keep["last_interaction"] != latest:
            changes.append(
                f"keep {keep['a']}->{keep['b']} as {a}->{b}, last={latest}"
            )
            if args.apply:
                conn.execute(
                    "UPDATE relationships SET a = ?, b = ?, last_interaction = ? "
                    "WHERE a = ? AND b = ?",
                    (a, b, latest, keep["a"], keep["b"]),
                )
        for row in group:
            if row is keep:
                continue
            changes.append(
                f"drop {row['a']}->{row['b']} "
                f"({row['trust']:.2f}/{row['closeness']:.2f}/{row['tension']:.2f})"
            )
            if args.apply:
                conn.execute(
                    "DELETE FROM relationships WHERE a = ? AND b = ?",
                    (row["a"], row["b"]),
                )

    for row in unreadable:
        changes.append(f"skip unreadable {row['a']}->{row['b']}")

    for change in changes:
        print(change)
    if not changes:
        print("relationships already canonical")
    if args.apply:
        conn.commit()
        print(f"applied to {args.db}")
    else:
        conn.rollback()
        print("dry run; pass --apply to write")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
