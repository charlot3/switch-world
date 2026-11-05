"""The Switch-driven café beat.

This posts scene turns into the live `#world` room and waits for the OpenCode/Claude sessions
to answer. The characters' own world MCP calls are what write beliefs and relationships; the
director only records the public dialogue/feed and exports the scene card.
"""
from __future__ import annotations

import time

from world_engine.service import WorldService

from . import DEMO_KEY
from .beats import (
    _apply_effects,
    _canon_warning,
    _ensure_secret,
    _record_beat,
    advance_to,
    get_beat,
    prompts_for,
)
from .canon import brief, branch_for, load as load_canon, record_branch, validate
from .switch_client import SwitchClient

ALICE_PROMPT = (
    "{canon}\n\n"
    "It is 18:30 at the café. Emily is here, and she notices you're distracted. She asks "
    "you directly: \"Is something wrong?\" A friend of yours — the person who has been "
    "coming around lately — told you in a private DM that they are leaving the city at the "
    "end of the month; they haven't told the others. You decide whether to tell Emily. If "
    "you tell her, say it in this room, then call world__remember with source user and "
    "proposition_key {key} so the record stays honest. If you keep it, say so honestly. "
    "Keep it to a few sentences, and do not call them 'the user' in the room."
)

EMILY_PROMPT = (
    "{canon}\n\n"
    'Alice says: "{alice}" — how do you respond? If you learned something from her, call '
    "world__remember with source character:alice, a confidence below 1.0 and "
    "proposition_key {key}. If she only dodged, you may remember a suspicion instead, but "
    "do not record it as the secret itself. If your view of Alice or the user changed, call "
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
    canon = load_canon()
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
    switch.post(
        room_id,
        "@alice " + ALICE_PROMPT.format(canon=brief("alice", canon), key=DEMO_KEY),
    )
    alice_event = switch.wait_for(room_id, "alice", started, timeout=timeout)
    if alice_event is None:
        service.record_event("director", "no_reply", "Alice did not answer in the room.", ["alice"], "public")
        card = service.scene_card("Café, 18:30 — no reply")
        return {"shared": None, "alice": None, "emily": None, "card": card, "room": room}

    alice = (alice_event.get("body") or "").strip()
    service.record_event("alice", "dialogue", "Alice: " + alice, ["alice"], "public")

    started = int(time.time() * 1000) - 1000
    switch.post(
        room_id,
        "@emily " + EMILY_PROMPT.format(
            canon=brief("emily", canon),
            alice=alice.replace('"', "'"),
            key=DEMO_KEY,
        ),
    )
    emily_event = switch.wait_for(room_id, "emily", started, timeout=timeout)
    emily = (emily_event.get("body") or "").strip() if emily_event else ""

    if emily:
        service.record_event("emily", "dialogue", "Emily: " + emily, ["emily"], "public")
    else:
        service.record_event("director", "no_reply", "Emily did not answer in the room.", ["emily"], "public")

    # The characters' MCP calls update beliefs/relationships. Classify from the
    # ledger: a source of character:alice is necessary but not sufficient — the
    # belief must also be about the secret, not a suspicion that Alice is hiding
    # something, and it must clear the confidence floor.
    holders = service.who_knows(DEMO_KEY)["holders"]
    branch = branch_for(service, DEMO_KEY)
    issues = validate(service, canon)
    shared = branch["id"] == "disclosure"
    participants = ["alice", "emily"] + [
        h["holder"] for h in holders if h["holder"] in {"sophia", "mia"}
    ]
    service.record_event(
        "director",
        "disclosure" if shared else "scene_turn",
        "Alice and Emily met at the café; the world state records what Emily learned."
        if shared else "Alice and Emily met at the café; Alice kept the secret.",
        participants=["alice", "emily"],
        visibility="public",
    )
    record_branch(service, branch, issues, participants=participants)
    service.advance_time("director", 30)
    service.record_event("director", "scene_end", "The café scene ends.", ["alice", "emily"], "public")
    beat = get_beat("cafe", canon)
    _record_beat(service, beat)
    card = service.scene_card(f"Café, 18:30 — {branch['id']}")
    return {
        "shared": shared,
        "beat": beat,
        "transport": "switch",
        "branch": branch,
        "canon_issues": issues,
        "alice": alice,
        "emily": emily,
        "card": card,
        "room": room,
        "matrix": service.matrix(),
    }


def run_beat_switch(
    service: WorldService | None = None,
    beat_id: str = "cafe",
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    """Run any authored beat through the live Switch room."""
    service = service or WorldService()
    switch = switch or SwitchClient()
    canon = load_canon()
    beat = get_beat(beat_id, canon)

    if beat_id == "cafe":
        _ensure_secret(service)
        advance_to(service, beat["time"])
        result = run_cafe_switch(
            service=service,
            switch=switch,
            room_name=room_name,
            timeout=timeout,
        )
        result["beat"] = beat
        result["transport"] = "switch"
        return result

    branch = None
    branch_id = None
    if beat_id == "aftermath":
        if not [e for e in service.state()["events"] if e["kind"] == "branch"]:
            raise ValueError("run the café beat first; aftermath needs a branch")
        branch = branch_for(service, DEMO_KEY)
        branch_id = branch["id"]

    if beat_id in {"morning-shop", "roundup"}:
        _ensure_secret(service)
    advance_to(service, beat["time"])
    room = switch.find_room(room_name)
    room_id = room["room_id"]
    service.record_event(
        "director",
        "beat_start",
        f"Beat: {beat['id']} — {beat['title']}",
        participants=beat.get("characters", []),
        visibility="public",
    )

    prompts = prompts_for(beat, branch_id)
    transcript = []
    for character in beat.get("characters", []):
        if character in {"user", "director"}:
            continue
        prompt = prompts.get(character)
        if not prompt:
            continue
        started = int(time.time() * 1000) - 1000
        switch.post(
            room_id,
            f"@{character} {brief(character, canon)}\n\n{prompt}",
        )
        event = switch.wait_for(room_id, character, started, timeout=timeout)
        if event is None:
            service.record_event(
                "director", "no_reply", f"{character.title()} did not answer.", [character], "public"
            )
            continue
        reply = (event.get("body") or "").strip()
        service.record_event(
            character, "dialogue", f"{character.title()}: {reply}", [character], "public"
        )
        transcript.append(f"{character.title()}: {reply}")

    _apply_effects(service, beat_id, branch_id)
    _record_beat(service, beat)
    issues = _canon_warning(service, canon)
    card = service.scene_card(f"{beat['title']} — {beat_id}")
    return {
        "beat": beat,
        "transport": "switch",
        "branch": branch,
        "canon_issues": issues,
        "transcript": transcript,
        "card": card,
        "room": room,
        "matrix": service.matrix(),
    }
