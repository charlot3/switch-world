"""The Studio rail: health chips, the beat clock, the cast and a recent feed.

Every external probe is independent and hard-capped at 300ms. A sleeping Switch,
Mattermost, gateway or Bifrost turns into a `false` flag, never into an error: the
dashboard must render even when the demo stack is half down. `world` is always true
because this process is serving the summary.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import httpx

from . import config
from .service import WorldService

PROBE_TIMEOUT = 0.3
RECENT_LIMIT = 10


def _url(value: str, fallback: str) -> str:
    return (value or fallback).rstrip("/")


SWITCH_HEALTH_URL = os.environ.get(
    "SWITCH_HEALTH_URL", "http://127.0.0.1:8000/health"
)
MATTERMOST_PING_URL = os.environ.get(
    "MATTERMOST_PING_URL", "http://127.0.0.1:8065/api/v4/system/ping"
)
GATEWAY_HEALTH_URL = os.environ.get(
    "GATEWAY_HEALTH_URL", "http://127.0.0.1:3000/"
)
BIFROST_BASE = _url(
    os.environ.get("BIFROST_URL", ""), "http://127.0.0.1:8080/v1"
)
BIFROST_HEALTH_URL = os.environ.get("BIFROST_HEALTH_URL", BIFROST_BASE + "/models")


def probe(url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """One non-fatal reachability check. Any exception means the service is down."""
    try:
        response = httpx.get(url, timeout=timeout)
        return response.status_code < 500
    except Exception:
        return False


def _check(prober, url: str) -> bool:
    try:
        return bool(prober(url))
    except Exception:
        return False


def _health(prober=probe) -> dict:
    return {
        "world": True,
        "switch": _check(prober, SWITCH_HEALTH_URL),
        "mattermost": _check(prober, MATTERMOST_PING_URL),
        "gateway": _check(prober, GATEWAY_HEALTH_URL),
        "bifrost": _check(prober, BIFROST_HEALTH_URL),
    }


def _beat_slim(beat: dict | None) -> dict | None:
    if not beat:
        return None
    return {key: beat.get(key) for key in ("id", "title", "time")}


def _load_rooms() -> list[dict]:
    path = config.ROOT / "world" / "rooms.json"
    try:
        rooms = json.loads(path.read_text(encoding="utf-8")).get("rooms") or {}
    except (OSError, ValueError):
        rooms = {}
    if not rooms:
        return [{"name": "world", "room_id": "world"}]
    result = []
    for name, info in rooms.items():
        info = info if isinstance(info, dict) else {}
        result.append({"name": name, "room_id": info.get("room_id")})
    # The public room first; then the DM rooms in their authored order.
    result.sort(key=lambda room: (room["name"] != "world", room["name"]))
    return result


def _last_event_for(events: list[dict], character: str) -> str | None:
    for event in reversed(events):
        if character in event.get("participants", []):
            return event.get("summary")
    return None


def studio_summary(service: WorldService, prober=None) -> dict:
    from director.clock import current_beat, next_beat, next_unplayed

    prober = prober or probe

    canon = json.loads((config.ROOT / "world" / "canon.json").read_text(encoding="utf-8"))
    clock = service.clock()
    now = datetime.fromisoformat(clock["now"])
    current = current_beat(canon, now)
    upcoming, _target = next_beat(canon, now)

    events = service.events()
    recent = [
        {"kind": event["kind"], "summary": event["summary"]}
        for event in events[-RECENT_LIMIT:]
    ]
    recent.reverse()

    done = service.completed_beats()
    agents = [
        {
            "id": character["id"],
            "name": character["name"],
            "role": character["role"],
            "friend": service.is_friend(character["id"]),
            "absent": service.is_absent(character["id"]),
            "last_event": _last_event_for(events, character["id"]),
        }
        for character in service.characters()
    ]

    return {
        "health": _health(prober),
        "clock": {"now": clock["now"], "mode": clock["mode"]},
        "current_beat": _beat_slim(current),
        "next_beat": _beat_slim(upcoming),
        "agents": agents,
        "rooms": _load_rooms(),
        "recent": recent,
        "done_beats": done,
        "arc_complete": next_unplayed(canon, set(done)) is None,
    }
