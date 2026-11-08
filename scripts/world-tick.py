#!/usr/bin/env python3
"""Scheduler: turn one Tavily search into a shared world event.

    uv run python scripts/world-tick.py --once
    uv run python scripts/world-tick.py --every 86400   # once a day

The one-shot mode is the demo path. The loop mode is the production shape: the world
gets a real-world input, every character records the same event with its source, and the
World Feed shows what changed. It does not advance the café scene by itself; that remains
the director's authored beat.
"""
from __future__ import annotations

import argparse
import sys
import time

from switch_world.application.tavily_beat import fetch_world_event
from switch_world.application.facade import WorldService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None)
    parser.add_argument("--every", type=int, default=86_400)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    service = WorldService()
    while True:
        try:
            result = fetch_world_event(service, query=args.query)
        except Exception as exc:
            print(f"world tick failed: {exc}", file=sys.stderr)
            return 1
        marker = " (offline fixture)" if result["offline"] else ""
        print(f"world event{marker}: {result['event']['summary']}")
        print(f"key: {result['key']} · holders: {', '.join(result['holders'])}")
        if args.once:
            return 0
        time.sleep(max(60, args.every))


if __name__ == "__main__":
    raise SystemExit(main())
