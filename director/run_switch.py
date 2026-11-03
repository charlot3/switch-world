"""The Switch-driven café beat.

This posts scene turns into the live `#world` room and waits for the OpenCode/Claude sessions
to answer. The characters' own world MCP calls are what write beliefs and relationships; the
director only records the public dialogue/feed and exports the scene card.
"""
from __future__ import annotations

import time

from world_engine.service import WorldService

from . import DEMO_KEY
from .switch_client import SwitchClient

ALICE_PROMPT = (
    "It is 18:30 at the café. Emily is here, and she notices you're distracted. She asks "
    "you directly: \"Is something wrong?\" The user told you in a private DM that they are "
    "leaving the city at the end of the month; they haven't told the others. You decide "
    "whether to tell Emily. If you tell her, say it in this room, then call world__remember "
    "with source user and proposition_key {key} so the record stays honest. If you keep it, "
    "say so honestly. Keep it to a few sentences."
)

EMILY_PROMPT = (
    'Alice says: "{alice}" — how do you respond? If you learned something from her, call '
    "world__remember with source character:alice, a confidence below 1.0 and "
    "proposition_key {key}. If your view of Alice or the user changed, call "
    "world__update_relationship with a short reason. Keep it to a few sentences."
)


def run_cafe_switch(
    service: WorldService | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    service = service or WorldService()
    switch = switch or SwitchClient()
    room = switch.find_room(room_name)
    room_id = room["room_id"]

    known = service.who_knows(DEMO_KEY)["holders"]
    if not any(h["holder"] == "alice" and h["source"] == "user" for h in known):
        raise ValueError(
            "Alice does not know the secret in the world state yet; run "
            "`uv run director --tell-alice` first."
        )

    service.record_event(
        "director",
        "scene_start",
        "Café, 18:30. Alice and Emily are at a table.",
        participants=["alice", "emily"],
        visibility="public",
    )

    started = int(time.time() * 1000) - 1000
    switch.post(room_id, "@alice " + ALICE_PROMPT.format(key=DEMO_KEY))
    alice_event = switch.wait_for(room_id, "alice", started, timeout=timeout)
    if alice_event is None:
        service.record_event("director", "no_reply", "Alice did not answer in the room.", ["alice"], "public")
        card = service.scene_card("Café, 18:30 — no reply")
        return {"shared": None, "alice": None, "emily": None, "card": card, "room": room}

    alice = (alice_event.get("body") or "").strip()
    service.record_event("alice", "dialogue", "Alice: " + alice, ["alice"], "public")

    started = int(time.time() * 1000) - 1000
    switch.post(room_id, "@emily " + EMILY_PROMPT.format(alice=alice.replace('"', "'"), key=DEMO_KEY))
    emily_event = switch.wait_for(room_id, "emily", started, timeout=timeout)
    emily = (emily_event.get("body") or "").strip() if emily_event else ""

    if emily:
        service.record_event("emily", "dialogue", "Emily: " + emily, ["emily"], "public")
    else:
        service.record_event("director", "no_reply", "Emily did not answer in the room.", ["emily"], "public")

    # The characters' MCP calls update beliefs/relationships. Decide from the world state
    # whether Emily learned it from Alice, not from the fact that she replied.
    holders = service.who_knows(DEMO_KEY)["holders"]
    shared = any(
        h["holder"] == "emily" and str(h["source"]).startswith("character:alice")
        for h in holders
    )
    service.record_event(
        "director",
        "disclosure" if shared else "scene_turn",
        "Alice and Emily met at the café; the world state records what Emily learned."
        if shared else "Alice and Emily met at the café; Alice kept the secret.",
        participants=["alice", "emily"],
        visibility="public",
    )
    service.advance_time("director", 30)
    service.record_event("director", "scene_end", "The café scene ends.", ["alice", "emily"], "public")
    card = service.scene_card("Café, 18:30")
    return {
        "shared": shared,
        "alice": alice,
        "emily": emily,
        "card": card,
        "room": room,
        "matrix": service.matrix(),
    }
