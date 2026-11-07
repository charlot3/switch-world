"""``director``: run the authored beats and inspect the world.

Arguments are parsed before the container is built, so ``director --help``
does not open a database, create the data directory, or construct a transport.
Every other invocation builds :class:`Settings` and the composition-root
container once and reuses its ``WorldService``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="director",
        description=(
            "Run the switch-world director: authored beats, the local café "
            "prototype, ledger inspection and world resets."
        ),
    )
    parser.add_argument("--simulate", action="store_true", help="run the local café prototype")
    parser.add_argument("--tell-alice", action="store_true", help="record the user's DM to Alice")
    parser.add_argument("--secret", default=None, help="the secret the user tells Alice")
    parser.add_argument("--key", default=None, help="the proposition_key for the secret")
    parser.add_argument("--reset", action="store_true", help="re-seed the world")
    parser.add_argument("--status", action="store_true", help="print the clock and matrix")
    parser.add_argument("--switch", action="store_true", help="run the live Switch café beat")
    parser.add_argument("--room", default="world", help="Switch room name for the live beat")
    parser.add_argument(
        "--timeout", type=float, default=90.0, help="seconds to wait for each reply"
    )
    parser.add_argument(
        "--tavily-event", action="store_true", help="fetch a real-world event through Tavily"
    )
    parser.add_argument("--query", default=None, help="Tavily query for --tavily-event")
    parser.add_argument("--bifrost", action="store_true", help="run the café beat through Bifrost")
    parser.add_argument("--beat", default=None, help="run one authored beat, e.g. morning-shop")
    parser.add_argument(
        "--transport",
        choices=["local", "bifrost", "switch", "cloud"],
        default="local",
        help=(
            "transport for --beat (switch becomes cloud when "
            "WORLD_AGENT_MODE=cloud)"
        ),
    )
    parser.add_argument("--arc", action="store_true", help="run all five beats locally")
    parser.add_argument(
        "--switch-log", action="store_true", help="export detailed Switch room history"
    )
    return parser


def _status(service) -> None:
    print(json.dumps(service.clock(), indent=2))
    for row in service.matrix():
        holders = ", ".join(
            f"{cid} {cell['confidence']:.2f} ({cell['source']})"
            for cid, cell in row["holders"].items()
        )
        print(f"- {row['label']}: {holders or '—'}")


def _error(exc: BaseException) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Heavy imports stay below --help.
    from director import DEMO_KEY, DEMO_SECRET
    from switch_world.config import load_settings
    from switch_world.container import build_container

    settings = load_settings(os.environ)
    container = build_container(settings)
    service = container.service
    secret = args.secret if args.secret is not None else DEMO_SECRET
    key = args.key if args.key is not None else DEMO_KEY

    try:
        if args.reset:
            service.reset()
            print("world reset")
        if args.tell_alice:
            from director.simulate import user_tells_alice

            belief = user_tells_alice(service, secret=secret, key=key)
            print(f"Alice now knows: {belief.get('proposition', belief)}")
        if args.status:
            _status(service)
        if args.switch_log:
            from director.switch_log import collect, write_jsonl

            try:
                room = None if args.room == "all" else args.room
                events = collect(room=room)
                path = write_jsonl(events)
            except Exception as exc:
                return _error(exc)
            print(f"{len(events)} Switch events -> {path}")
            for event in events[-20:]:
                print(
                    f"{event['timestamp_iso']} · {event['room_name']} · "
                    f"{event['sender_name']} · {event['kind']} · {event['body'][:160]}"
                )
            return 0
        if args.arc:
            from director.beats import run_arc

            try:
                result = run_arc(service)
            except Exception as exc:
                return _error(exc)
            for item in result["beats"]:
                print(f"{item['beat']['id']}: {item['beat']['title']}")
            print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
            print(f"scene card: {result['card']['path']}")
            return 0
        if args.beat:
            from director.beats import run_beat

            try:
                result = run_beat(
                    service,
                    args.beat,
                    transport=args.transport,
                    room_name=args.room,
                    timeout=args.timeout,
                )
            except Exception as exc:
                return _error(exc)
            print(f"beat: {result['beat']['title']} ({result['beat']['id']})")
            if result.get("branch"):
                print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
            for line in result.get("transcript", []):
                print(line)
            print(f"scene card: {result['card']['path']}")
            return 0
        if args.tavily_event:
            from director.tavily_beat import fetch_world_event

            try:
                result = fetch_world_event(service, query=args.query)
            except Exception as exc:
                return _error(exc)
            print(f"event: {result['event']['summary']}")
            print(f"key: {result['key']} · holders: {', '.join(result['holders'])}")
            print("offline fixture" if result["offline"] else "live Tavily result")
            if not args.bifrost:
                return 0
        if args.bifrost:
            from director.bifrost_scene import run_cafe_bifrost

            try:
                result = run_cafe_bifrost(service)
            except Exception as exc:
                return _error(exc)
            print("Alice:", result["alice"])
            print("Emily:", result["emily"])
            print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
            print(
                "canon:",
                "holds"
                if not result["canon_issues"]
                else "; ".join(result["canon_issues"]),
            )
            print("scene card:", result["card"]["path"])
            print("bifrost:", json.dumps(result["bifrost"], indent=2))
            if not args.switch:
                return 0
        if args.switch:
            from director.run_switch import run_cafe_switch

            try:
                result = run_cafe_switch(room_name=args.room, timeout=args.timeout)
            except Exception as exc:
                return _error(exc)
            print("Alice:", result["alice"])
            print("Emily:", result["emily"])
            print("branch:", result["branch"]["label"], f"({result['branch']['id']})")
            print(
                "canon:",
                "holds"
                if not result["canon_issues"]
                else "; ".join(result["canon_issues"]),
            )
            print("room:", result["room"]["room_id"])
            print("scene card:", result["card"]["path"])
            return 0

        if args.simulate or not any(
            [
                args.reset,
                args.tell_alice,
                args.status,
                args.switch,
                args.tavily_event,
                args.bifrost,
                args.beat,
                args.arc,
                args.switch_log,
            ]
        ):
            from director.simulate import run_cafe

            try:
                result = run_cafe(service)
            except ValueError as exc:
                return _error(exc)
            for line in result["transcript"]:
                print(line)
            print()
            print(f"branch: {result['branch']['label']} ({result['branch']['id']})")
            print(
                "canon:",
                "holds"
                if not result["canon_issues"]
                else "; ".join(result["canon_issues"]),
            )
            print(f"scene card: {result['card']['path']}")
            print(f"world clock: {result['clock']['now']}")
    finally:
        container.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
