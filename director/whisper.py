"""A whisper: the user speaks privately to one character while the room watches.

The words reach only the target. If a verified private Switch room is available the
transport is `switch`; otherwise the target is answered through its own Bifrost/phone
model and the response is marked `transport: "staged"` — the response never claims a
privacy the transport cannot prove.

One or two other present characters see the whisper *happen* but not its content. Their
prompt is built without any token from the whispered text, and their reaction is recorded
publicly. The whisper and its answer are private events with a lock for the player.
"""
from __future__ import annotations

import re

from world_engine.service import WorldService

from . import social
from .bifrost_scene import _apply, _parse_envelope, _system
from .canon import load as load_canon
from .group import DEFAULT_CHARACTERS, _metadata, _turn_id
from .tavily_beat import world_context

MAX_MESSAGE = 800
MAX_OBSERVERS = 2

# The template deliberately names nobody and repeats nothing. Any token that also occurs
# in the whispered text is scrubbed out before the prompt is sent (see `_observer_prompt`).
_OBSERVER_TEMPLATE = (
    "Across the table, two people lean together and speak too softly to hear. The room "
    "only catches the pause afterward. React with one short physical action or at most "
    "half a line. Do not guess at anything that was said."
)
_OBSERVER_FALLBACKS = (
    "A quiet exchange happens nearby. React with one brief look or gesture.",
    "Two people speak inaudibly beside you. Give one small visible reaction.",
)
_OBSERVER_REPLY_FALLBACK = "They glance over, then look away."


def _tokens(text: str) -> set[str]:
    """Every alphanumeric token, including one-letter ones: no leak is too small."""
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _without_tokens(text: str, forbidden: set[str]) -> str:
    """Remove every word whose token is in `forbidden`, preserving the rest."""
    words = re.split(r"(\s+)", text)
    kept = [
        word for word in words
        if not (word.strip() and word.strip(".,;:!?").lower() in forbidden)
    ]
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def _observer_prompt(message: str) -> str:
    forbidden = _tokens(message)
    for template in (_OBSERVER_TEMPLATE, *_OBSERVER_FALLBACKS):
        if not (_tokens(template) & forbidden):
            return template
    # Extremely unlucky overlap: keep the guarantee and accept a clipped sentence.
    return _without_tokens(_OBSERVER_TEMPLATE, forbidden)


def _observer_reaction(character: str, reply: str, message: str) -> str:
    """A public reaction must still not quote the private words."""
    forbidden = _tokens(message)
    reply = (reply or "").strip()
    if reply and not (_tokens(reply) & forbidden):
        return reply
    fallback = _without_tokens(_OBSERVER_REPLY_FALLBACK, forbidden)
    if fallback and not (_tokens(fallback) & forbidden):
        return fallback
    return "…"


def whisper_to_character(
    service: WorldService,
    to: str,
    message: str,
    client=None,
    switch=None,
    timeout: float = 35.0,
) -> dict:
    to = (to or "").strip().lower()
    message = (message or "").strip()
    if to not in DEFAULT_CHARACTERS:
        raise ValueError(f"unknown character: {to}")
    if not service.character_exists(to):
        raise ValueError(f"unknown character: {to}")
    if service.is_absent(to):
        raise ValueError(f"{to.title()} is not in the scene")
    scene_state = service.state()
    scene = scene_state.get("scene") or {}
    cast = (
        scene.get("cast")
        or (scene_state.get("scenario") or {}).get("cast")
        or list(DEFAULT_CHARACTERS)
    )
    if to not in cast:
        raise ValueError(f"{to.title()} is not in the scene")
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message is too long (max {MAX_MESSAGE} characters)")

    turn_id = _turn_id()
    verdict = social.appraise(service, to, message, public=False)

    # Private words. `private` keeps them out of every other character's prompt; the
    # player's own dashboard is the only place they render.
    whisper = service.record_event(
        "user",
        "whisper",
        f"You whisper to {to.title()}: {message}",
        participants=[to, "user"],
        visibility="private",
        metadata=_metadata(turn_id, "whisper", "primary", "neutral", to, False),
    )

    transport = "staged"
    room = None
    if switch is not None:
        finder = getattr(switch, "find_private_room", None)
        if callable(finder):
            try:
                room = finder(to)
            except Exception:  # a failed lookup is simply "no private room"
                room = None
            if room and room.get("room_id"):
                transport = "switch"

    writes: dict = {}
    reply: str
    if transport == "switch":
        reply = _answer_through_switch(switch, room, to, message, timeout)
    else:
        if client is None:
            from gateway.bifrost import BifrostClient

            client = BifrostClient()
        envelope = _parse_envelope(
            client.chat_json(to, _target_messages(service, to, message, verdict)),
            to,
        )
        reply = envelope["reply"]
        writes = _apply(service, to, envelope)
        if (
            verdict["stance"] in {"refuse", "hard_refuse"}
            or (verdict["stance"] == "limited" and social.looks_like_refusal(reply))
            or social.contains_leak(reply, verdict)
        ):
            reply = social.deflection(to, verdict, message)

    private_reply = service.record_event(
        to,
        "whisper_reply",
        f"{to.title()} (whisper): {reply}",
        participants=[to, "user"],
        visibility="private",
        metadata=_metadata(turn_id, "whisper_reply", "primary", "neutral", to, False),
    )
    social.record_verdict(service, to, verdict)
    social.apply_deltas(service, to, verdict)

    present = [
        c for c in cast
        if c != to and c in DEFAULT_CHARACTERS and not service.is_absent(c)
    ]
    observers = present[:MAX_OBSERVERS]
    observer_lines: list[dict] = []
    for observer in observers:
        line = _observe(service, observer, message, to, client, turn_id)
        observer_lines.append(line)

    lines = [
        {
            "character": to,
            "mode": "whisper",
            "role": "primary",
            "text": message,
            "expression": "neutral",
            "event_id": whisper["id"],
            "private": True,
        },
        {
            "character": to,
            "mode": "whisper_reply",
            "role": "primary",
            "text": reply,
            "expression": "neutral",
            "event_id": private_reply["id"],
            "private": True,
        },
        *observer_lines,
    ]
    plan = {
        "primary": to,
        "reactors": observers,
        "silent": [c for c in present if c not in observers],
        "chorus": False,
        "topic": "whisper",
        "target": to,
        "whisper": True,
    }
    turn = {"id": turn_id, "plan": plan, "lines": lines, "missing": []}
    return {
        "transport": transport,
        "target": to,
        "reply": reply,
        "verdict": verdict,
        "writes": writes,
        "observers": [line["character"] for line in observer_lines],
        "private_event_id": whisper["id"],
        "reply_event_id": private_reply["id"],
        "turn": turn,
    }


def _target_messages(
    service: WorldService, to: str, message: str, verdict: dict
) -> list[dict]:
    canon = load_canon()
    context = world_context(service)
    clock = service.clock()["now"]
    social_block = "\n\n".join(
        [
            social.relationship_block(service, to),
            social.policy_block(verdict),
            social.response_block(verdict),
            social.action_block(verdict),
        ]
    )
    if verdict.get("action_mode") == "attempt":
        social_block += (
            "\n\nThis is an attempt on you, not a fact. It is never automatic success: "
            "you decide what, if anything, you allow."
        )
    user = (
        "The user leans in and whispers privately to you. No one else can hear it.\n\n"
        f'The user whispers: "{message}"\n\n'
        "Answer in a whisper in your own voice: one or two short sentences. Be responsive "
        "to the private words. This is not the group scene; do not address the room. All "
        "characters are adults and the tone stays 17+ SFW. Return the JSON envelope."
    )
    return [
        {
            "role": "system",
            "content": _system(to, canon, context, clock=clock, social_block=social_block),
        },
        {"role": "user", "content": user},
    ]


def _observer_messages(
    service: WorldService, observer: str, message: str
) -> list[dict]:
    canon = load_canon()
    context = world_context(service)
    clock = service.clock()["now"]
    return [
        {
            "role": "system",
            "content": _system(
                observer,
                canon,
                context,
                clock=clock,
                social_block=social.relationship_block(service, observer),
            ),
        },
        # Built without any token from the whispered text.
        {"role": "user", "content": _observer_prompt(message)},
    ]


def _observe(
    service: WorldService,
    observer: str,
    message: str,
    target: str,
    client,
    turn_id: str,
) -> dict:
    reply = ""
    if client is not None:
        try:
            envelope = _parse_envelope(
                client.chat_json(observer, _observer_messages(service, observer, message)),
                observer,
            )
            reply = envelope["reply"]
        except Exception:
            reply = ""
    reaction = _observer_reaction(observer, reply, message)
    event = service.record_event(
        observer,
        "dialogue",
        f"{observer.title()}: {reaction}",
        participants=[observer],
        visibility="public",
        metadata=_metadata(turn_id, "reaction", "reactor", "alarmed", target, False),
    )
    return {
        "character": observer,
        "mode": "reaction",
        "role": "reactor",
        "text": reaction,
        "expression": "alarmed",
        "event_id": event["id"],
        "private": False,
    }


def _answer_through_switch(switch, room: dict, to: str, message: str, timeout: float) -> str:
    """Deliver into a verified private room and wait for the target's own answer."""
    room_id = room["room_id"]
    started = switch.history(room_id)[-1].get("timestamp", 0) if switch.history(room_id) else 0
    switch.post(room_id, message)
    wait = getattr(switch, "wait_for", None)
    event = wait(room_id, to, started, timeout=timeout) if callable(wait) else None
    body = (event or {}).get("body") or ""
    if not body.strip():
        raise RuntimeError("the private Switch room accepted the whisper but gave no answer")
    return body.strip()
