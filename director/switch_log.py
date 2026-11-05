"""Export detailed Switch room history for a demo or a bug report.

The dashboard shows the world-state projection. When something looks off in Switch, the
room history has the missing layer: who sent what, from which room, with Switch's own
event id and timestamp. This module reads that history through the director's Switch
credentials and writes JSONL that can be attached to a demo note.

    uv run director --switch-log
    uv run director --switch-log --room world
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from world_engine import config

from .switch_client import SwitchClient


def _rooms(switch: SwitchClient) -> list[dict]:
    rooms = switch._op("list_rooms")
    if isinstance(rooms, dict):
        rooms = rooms.get("result", [])
    return [room for room in rooms if not room.get("archived")]


def collect(switch: SwitchClient | None = None, room: str | None = None) -> list[dict]:
    switch = switch or SwitchClient()
    rooms = _rooms(switch)
    if room:
        rooms = [item for item in rooms if item.get("name") == room]
        if not rooms:
            raise ValueError(f"Switch room not found: {room}")
    events: list[dict] = []
    for item in rooms:
        for event in switch.history(item["room_id"]):
            timestamp = event.get("timestamp")
            iso = ""
            if timestamp:
                try:
                    iso = datetime.fromtimestamp(
                        int(timestamp) / 1000, tz=timezone.utc
                    ).isoformat()
                except (TypeError, ValueError):
                    iso = ""
            events.append(
                {
                    "room_id": item["room_id"],
                    "room_name": item.get("name"),
                    "event_id": event.get("id"),
                    "kind": event.get("kind") or event.get("type"),
                    "sender": event.get("sender"),
                    "sender_name": event.get("sender_name"),
                    "timestamp": timestamp,
                    "timestamp_iso": iso,
                    "body": event.get("body") or "",
                    "attachments": event.get("attachments") or [],
                }
            )
    events.sort(key=lambda item: item.get("timestamp") or 0)
    return events


def write_jsonl(events: list[dict], path: Path | str | None = None) -> Path:
    if path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = Path(config.EXPORT_DIR) / f"switch-log-{stamp}.jsonl"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
