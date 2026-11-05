"""Director CLI.

    uv run director --simulate      # run the local café prototype
    uv run director --tell-alice    # record the user's DM to Alice
    uv run director --reset         # re-seed the world
    uv run director --status        # print the clock and the belief matrix
    uv run director --switch        # real Switch transport (Day 1+)
"""
from __future__ import annotations

import argparse
import json
import sys

from world_engine.service import WorldService

from . import DEMO_KEY, DEMO_SECRET
from .simulate import run_cafe, user_tells_alice


def _status(service: WorldService) -> None:
    print(json.dumps(service.clock(), indent=2))
    for row in service.matrix():
        holders = ", ".join(
            f"{cid} {cell['confidence']:.2f} ({cell['source']})"
            for cid, cell in row["holders"].items()
        )
        print(f"- {row['label']}: {holders or '—'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="director", description=__doc__)
    parser.add_argument("--simulate", action="store_true", help="run the local café prototype")
    parser.add_argument("--tell-alice", action="store_true", help="record the user's DM to Alice")
    parser.add_argument("--secret", default=DEMO_SECRET, help="the secret the user tells Alice")
    parser.add_argument("--key", default=DEMO_KEY, help="the proposition_key for the secret")
    parser.add_argument("--reset", action="store_true", help="re-seed the world")
    parser.add_argument("--status", action="store_true", help="print the clock and matrix")
    parser.add_argument("--switch", action="store_true", help="run the live Switch café beat")
    parser.add_argument("--room", default="world", help="Switch room name for the live beat")
    parser.add_argument("--timeout", type=float, default=90.0, help="seconds to wait for each reply")
    parser.add_argument("--tavily-event", action="store_true", help="fetch a real-world event through Tavily")
    parser.add_argument("--query", default=None, help="Tavily query for --tavily-event")
    parser.add_argument("--bifrost", action="store_true", help="run the café beat through Bifrost")
    args = parser.parse_args(argv)

    service = WorldService()

    if args.reset:
        service.reset()
        print("world reset")
    if args.tell_alice:
        belief = user_tells_alice(service, secret=args.secret, key=args.key)
        print(f"Alice now knows: {belief.get('proposition', belief)}")
    if args.status:
        _status(service)
    if args.tavily_event:
        from .tavily_beat import fetch_world_event

        try:
            result = fetch_world_event(service, query=args.query)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"event: {result['event']['summary']}")
        print(f"key: {result['key']} · holders: {', '.join(result['holders'])}")
        print("offline fixture" if result["offline"] else "live Tavily result")
        if not args.bifrost:
            return 0
    if args.bifrost:
        from .bifrost_scene import run_cafe_bifrost

        try:
            result = run_cafe_bifrost(service)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("Alice:", result["alice"])
        print("Emily:", result["emily"])
        print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
        print("canon:", "holds" if not result["canon_issues"] else "; ".join(result["canon_issues"]))
        print("scene card:", result["card"]["path"])
        print("bifrost:", json.dumps(result["bifrost"], indent=2))
        if not args.switch:
            return 0
    if args.switch:
        from .run_switch import run_cafe_switch

        try:
            result = run_cafe_switch(room_name=args.room, timeout=args.timeout)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("Alice:", result["alice"])
        print("Emily:", result["emily"])
        print("branch:", result["branch"]["label"], f"({result['branch']['id']})")
        print("canon:", "holds" if not result["canon_issues"] else "; ".join(result["canon_issues"]))
        print("room:", result["room"]["room_id"])
        print("scene card:", result["card"]["path"])
        return 0

    if args.simulate or not any(
        [args.reset, args.tell_alice, args.status, args.switch, args.tavily_event, args.bifrost]
    ):
        try:
            result = run_cafe(service)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for line in result["transcript"]:
            print(line)
        print()
        print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
        print("canon:", "holds" if not result["canon_issues"] else "; ".join(result["canon_issues"]))
        print(f"scene card: {result['card']['path']}")
        print(f"world clock: {result['clock']['now']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
