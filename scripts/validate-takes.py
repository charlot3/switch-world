#!/usr/bin/env python3
"""Validate every take against its scenario, cast, scene refs, art and cues.

Exit code 0 when every take is valid. On failure, print one line per problem with the
offending file path and exit 1. Safe to run from any working directory:

    PYTHONPATH=. python scripts/validate-takes.py
    python scripts/validate-takes.py path/to/takes
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from switch_world.application.takes import TAKE_DIR, validate_takes  # noqa: E402


def main(argv: list[str]) -> int:
    takes_dir = Path(argv[1]).resolve() if len(argv) > 1 else TAKE_DIR
    errors = validate_takes(takes_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        count = len(list(takes_dir.glob("*.json")))
        print(
            f"{len(errors)} problem(s) across {count} take file(s).",
            file=sys.stderr,
        )
        return 1
    count = len(list(takes_dir.glob("*.json")))
    print(f"Validated {count} takes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
