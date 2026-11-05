"""Free-form group chat through the live Switch room.

This is the in-person counterpart to the phone. The showrunner says something to the
group; the director posts it into `#world` addressed to the cast, waits for the agents'
own replies, and records both sides in the world feed. Unlike a DM, the whole room sees
it — and unlike the authored beats, nobody knows the next line.
"""
from __future__ import annotations

import time

from world_engine.service import WorldService

from .switch_client import SwitchClient, SwitchError

DEFAULT_CHARACTERS = ("alice", "emily", "sophia", "mia")

# Switch emits this while it boots an agent session. It is not an in-character reply;
# keep waiting for the real line instead of showing it to the player.
PLACEHOLDERS = (
    "starting a session to handle this",
    "starting a session",
)


def _clean_character(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in DEFAULT_CHARACTERS:
        raise ValueError(f"unknown character: {value}")
    return value


def say_in_group(
    service: WorldService,
    message: str,
    characters: list[str] | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 45.0,
) -> dict:
    """Post one user line to the room and collect the addressed agents' replies."""
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > 800:
        raise ValueError("message is too long (max 800 characters)")

    targets = [_clean_character(c) for c in (characters or DEFAULT_CHARACTERS)]
    targets = list(dict.fromkeys(targets))
    switch = switch or SwitchClient()
    room = switch.find_room(room_name)
    room_id = room["room_id"]

    # Record the user's line first: a slow or dead agent must never erase it from the UI.
    service.record_event(
        "user",
        "dialogue",
        "You: " + message,
        participants=["user", *targets],
        visibility="public",
        room_id=room_id,
    )

    started = int(time.time() * 1000) - 500
    mentions = " ".join(f"@{character}" for character in targets)
    try:
        switch.post(room_id, f"{mentions} {message}")
    except SwitchError as exc:
        raise RuntimeError(
            "the Switch room did not accept the message; check that the gateway and the "
            f"four live sessions are running ({exc})"
        ) from exc

    deadline = time.time() + max(1.0, float(timeout))
    replies: list[dict] = []
    seen: dict[str, dict] = {}
    while time.time() < deadline:
        try:
            events = switch.history(room_id)
        except SwitchError:
            events = []
        for event in events:
            sender = event.get("sender_name")
            if sender not in targets or sender in seen:
                continue
            if int(event.get("timestamp") or 0) <= started:
                continue
            body = (event.get("body") or "").strip()
            if not body or any(marker in body.lower() for marker in PLACEHOLDERS):
                continue
            seen[sender] = event
        if len(seen) >= len(targets):
            break
        time.sleep(1.0)

    for character in targets:
        event = seen.get(character)
        if not event:
            continue
        body = (event.get("body") or "").strip()
        recorded = service.record_event(
            character,
            "dialogue",
            f"{character.title()}: {body}",
            participants=[character],
            visibility="public",
            room_id=room_id,
            message_id=str(event.get("event_id") or ""),
        )
        replies.append(
            {
                "character": character,
                "text": body,
                "event_id": recorded["id"],
                "message_id": event.get("event_id"),
            }
        )

    missing = [character for character in targets if character not in seen]
    return {
        "room": room,
        "targets": targets,
        "replies": replies,
        "missing": missing,
        "timed_out": bool(missing),
        "clock": service.clock(),
    }
