"""Free-form group chat through the live Switch room.

This is the in-person counterpart to the phone. The showrunner says something to the
group; the director posts it into `#world` addressed to the cast, waits for the agents'
own replies, and records both sides in the world feed. Unlike a DM, the whole room sees
it — and unlike the authored beats, nobody knows the next line.

The turn is planned deterministically before anything is posted (see
`docs/SCENE_PROTOCOL.md`): a named addressee answers as the primary, shared small-talk
becomes a short chorus, intimate topics stay a primary plus one reactor, and everyone
else is silent. Only planned speakers are collected. A planned speaker who never answers
becomes a `silence` beat instead of an error.

A physical-boundary violation is cut before the act is written anywhere: the public feed
gets one detail-free `boundary_violation`, the target refuses and leaves, and every other
present character privately records that the user crossed a line.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Mapping

from world_engine.service import WorldService

from . import social
from .switch_client import SwitchClient, SwitchError

DEFAULT_CHARACTERS = ("alice", "emily", "sophia", "mia")
CHORUS_TOPICS = {"small-talk", "personal"}
INTIMATE_TOPICS = {"private-emotional", "body", "contact"}
MAX_MESSAGE = 800
TURN_CAP_SECONDS = 35.0

# A witness's confidence is deliberately distinct per character: Alice is certain,
# Emily nearly so, Sophia and Mia more cautious. Nothing is shared with the target.
BOUNDARY_CONFIDENCE = {"alice": 1.0, "emily": 0.9, "sophia": 0.85, "mia": 0.8}
BOUNDARY_KEY = "user-crossed-a-line"

BOUNDARY_REACTIONS = {
    "alice": "goes quiet and does not look at the user.",
    "emily": "goes still, watching the user.",
    "sophia": "marks it down without a word.",
    "mia": "jaw tightens.",
}

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


def _turn_id() -> str:
    return "t-" + uuid.uuid4().hex[:12]


def _named_addressee(message: str, present: list[str]) -> str | None:
    """`@alice` or a line that opens with "Alice, ..." / "Alice: ..."."""
    classified = social.classify(message)
    candidate = classified.get("addressee")
    if candidate in present:
        return candidate
    match = re.match(r"\s*@?([A-Za-z]+)\b[\s,:;]", message or "")
    if match:
        name = match.group(1).lower()
        if name in present:
            return name
    return None


def plan_turn(message: str, present: list[str], verdicts: Mapping[str, dict]) -> dict:
    """The deterministic stage direction for one user line."""
    classified = social.classify(message)
    topic = classified["topic"]
    plan = {
        "primary": None,
        "reactors": [],
        "silent": [],
        "chorus": False,
        "topic": topic,
    }
    if not present:
        return plan

    addressee = _named_addressee(message, present)
    if addressee:
        others = [c for c in present if c != addressee]
        plan.update({"primary": addressee, "reactors": others[:2], "silent": others[2:]})
        return plan

    if topic in INTIMATE_TOPICS:
        primary = present[0]
        reactor = None
        primary_stance = verdicts.get(primary, {}).get("stance")
        for candidate in present[1:]:
            if verdicts.get(candidate, {}).get("stance") != primary_stance:
                reactor = candidate
                break
        if reactor is None and len(present) > 1:
            reactor = present[1]
        reactors = [reactor] if reactor else []
        plan.update(
            {
                "primary": primary,
                "reactors": reactors,
                "silent": [c for c in present if c != primary and c not in reactors],
            }
        )
        return plan

    if topic in CHORUS_TOPICS:
        if len(present) == 1:
            plan.update({"primary": present[0]})
            return plan
        # 2 speakers when the room is 3 (one silent), 3 speakers when it is 4 or more.
        speakers = present[: min(3, max(2, len(present) - 1))]
        plan.update(
            {
                "primary": speakers[0],
                "chorus": True,
                "chorus_speakers": speakers,
                "silent": present[len(speakers):],
            }
        )
        return plan

    primary = present[0]
    reactors = present[1:3]
    plan.update(
        {
            "primary": primary,
            "reactors": reactors,
            "silent": present[3:],
        }
    )
    return plan


def _speakers(plan: dict) -> list[str]:
    if plan.get("chorus"):
        return list(plan.get("chorus_speakers") or [])
    return [c for c in [plan.get("primary"), *plan.get("reactors", [])] if c]


def _role_for(plan: dict, character: str) -> str:
    if plan.get("chorus") and character in plan.get("chorus_speakers", []):
        return "chorus"
    if character == plan.get("primary"):
        return "primary"
    if character in plan.get("reactors", []):
        return "reactor"
    return "silent"


def _plan_summary(plan: dict) -> str:
    if plan.get("chorus"):
        who = ", ".join(plan.get("chorus_speakers") or [])
        return f"Turn plan: chorus ({who}) on {plan['topic']}."
    primary = plan.get("primary") or "nobody"
    reactors = ", ".join(plan.get("reactors") or []) or "none"
    silent = ", ".join(plan.get("silent") or []) or "none"
    return (
        f"Turn plan: primary {primary}; reactors {reactors}; silent {silent} "
        f"on {plan['topic']}."
    )


def _limit_words(text: str, limit: int = 12) -> str:
    words = (text or "").split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).rstrip(",;:") + "."


def _beat_mode(text: str, role: str) -> tuple[str, str]:
    """Split a reply into a scene-protocol mode and its visible text."""
    text = (text or "").strip()
    if role == "chorus":
        return "chorus", _limit_words(text)
    if role == "reactor":
        return "reaction", text
    match = re.match(r"^\*(.+)\*$", text, re.S)
    if match:
        return "action", match.group(1).strip()
    if text.startswith("(") and text.endswith(")"):
        return "action", text[1:-1].strip()
    return "speech", text


def _expression(verdict: dict, role: str, mode: str) -> str:
    if mode == "silence":
        return "neutral"
    if verdict.get("boundary") == "violation":
        return "alarmed"
    if mode == "reaction":
        return "cold" if int(verdict.get("tier", 0)) >= 2 else "neutral"
    if role == "chorus":
        return "smile"
    if verdict.get("stance") in {"refuse", "hard_refuse"}:
        return "cold"
    if verdict.get("stance") in {"answer", "tease"}:
        return "smile"
    return "neutral"


def _role_instruction(role: str) -> str:
    if role == "primary":
        return (
            "Stage direction: you are the primary speaker this beat. Answer the user "
            "directly in your own voice, in one or two short sentences."
        )
    if role == "reactor":
        return (
            "Stage direction: you are a reactor this beat. Add one short reaction, spoken "
            "or a brief action in *asterisks*. Do not take over the scene."
        )
    if role == "chorus":
        return (
            "Stage direction: you are one voice in a chorus. Say one short line of at most "
            "12 words that carries the same shared fact in your own texture. Do not add a "
            "new topic and do not ask a question."
        )
    return (
        "Stage direction: you are silent this beat. Do not speak. If you answer at all, "
        "keep it to one small action."
    )


def _prompt_for(
    service: WorldService,
    character: str,
    message: str,
    verdict: dict,
    role: str,
) -> str:
    return (
        f"@{character} {social.relationship_block(service, character)}\n\n"
        f"{social.policy_block(verdict)}\n\n"
        f"{_role_instruction(role)}\n\n"
        f'The user says to the room: "{message}"\n\n'
        "Reply only as yourself. Keep it 17+ SFW. Do not mention the policy, the stage "
        "direction, or that you are following instructions."
    )


def _metadata(
    turn_id: str,
    mode: str,
    role: str,
    expression: str,
    target: str | None,
    chorus: bool,
) -> dict:
    return {
        "turn_id": turn_id,
        "mode": mode,
        "role": role,
        "expression": expression,
        "target": target,
        "chorus": chorus,
    }


def _boundary_target(
    message: str, present: list[str], verdicts: Mapping[str, dict]
) -> str | None:
    if not any(v.get("boundary") == "violation" for v in verdicts.values()):
        return None
    return _named_addressee(message, present) or present[0]


def _boundary_turn(
    service: WorldService,
    message: str,
    present: list[str],
    verdicts: dict,
    target: str,
    turn_id: str,
) -> dict:
    """Cut the act and show only the consequence."""
    classified = social.classify(message)
    witnesses = [c for c in present if c != target]
    plan = {
        "primary": target,
        "reactors": witnesses,
        "silent": [],
        "chorus": False,
        "topic": classified["topic"],
        "boundary": "violation",
    }
    service.record_event(
        "director",
        "turn_plan",
        _plan_summary(plan) + " The act is cut; only the consequence is shown.",
        participants=[],
        visibility="public",
        metadata={"turn_id": turn_id, "plan": plan, "topic": classified["topic"]},
    )
    boundary = service.record_event(
        "director",
        "boundary_violation",
        f"The user crossed a physical boundary with {target.title()}.",
        participants=[target],
        visibility="public",
        metadata=_metadata(turn_id, "reaction", "primary", "alarmed", target, False),
    )

    target_verdict = {**verdicts[target], "stance": "hard_refuse", "boundary": "violation"}
    verdicts[target] = target_verdict
    social.record_verdict(service, target, target_verdict)
    social.apply_deltas(service, target, target_verdict)

    refusal = social.deflection(target, target_verdict, message)
    refusal_event = service.record_event(
        target,
        "dialogue",
        f"{target.title()}: {refusal}",
        participants=[target],
        visibility="public",
        metadata=_metadata(turn_id, "speech", "primary", "hurt", target, False),
    )
    lines = [
        {
            "character": target,
            "mode": "speech",
            "role": "primary",
            "text": refusal,
            "expression": "hurt",
            "event_id": refusal_event["id"],
        }
    ]
    replies = [
        {
            "character": target,
            "text": refusal,
            "event_id": refusal_event["id"],
            "message_id": None,
        }
    ]

    # The target leaves the scene. Later group sends filter absent characters.
    service.mark_absent(target, reason="crossed a physical boundary")

    proposition = f"The user crossed a physical boundary with {target.title()}."
    for witness in witnesses:
        confidence = BOUNDARY_CONFIDENCE.get(witness, 0.8)
        service.remember(
            witness,
            proposition=proposition,
            source="observation",
            confidence=confidence,
            visibility="private",
            proposition_key=BOUNDARY_KEY,
        )
        reaction = BOUNDARY_REACTIONS.get(witness, "goes still.")
        reaction_event = service.record_event(
            witness,
            "dialogue",
            f"{witness.title()}: {reaction}",
            participants=[witness],
            visibility="public",
            metadata=_metadata(turn_id, "reaction", "reactor", "alarmed", target, False),
        )
        lines.append(
            {
                "character": witness,
                "mode": "reaction",
                "role": "reactor",
                "text": reaction,
                "expression": "alarmed",
                "event_id": reaction_event["id"],
            }
        )

    turn = {"id": turn_id, "plan": plan, "lines": lines, "missing": []}
    return {
        "room": None,
        "targets": present,
        "verdicts": verdicts,
        "replies": replies,
        "missing": [],
        "timed_out": False,
        "clock": service.clock(),
        "turn": turn,
        "boundary": boundary,
    }


def say_in_group(
    service: WorldService,
    message: str,
    characters: list[str] | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = TURN_CAP_SECONDS,
) -> dict:
    """Post one user line to the room and collect the planned speakers' replies."""
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message is too long (max {MAX_MESSAGE} characters)")

    requested = [_clean_character(c) for c in (characters or DEFAULT_CHARACTERS)]
    requested = list(dict.fromkeys(requested))
    # Presence is part of the scene: a character who left is not addressed or posted to.
    present = [c for c in requested if not service.is_absent(c)]
    verdicts = {
        character: social.appraise(service, character, message, public=True)
        for character in present
    }
    turn_id = _turn_id()

    boundary_target = _boundary_target(message, present, verdicts) if present else None
    if boundary_target:
        return _boundary_turn(service, message, present, verdicts, boundary_target, turn_id)

    plan = plan_turn(message, present, verdicts)
    speakers = _speakers(plan)

    if not present:
        # An empty room still keeps the user's line; there is nobody to plan for.
        service.record_event(
            "user",
            "dialogue",
            "You: " + message,
            participants=["user"],
            visibility="public",
            metadata=_metadata(turn_id, "speech", "primary", "neutral", None, False),
        )
        turn = {"id": turn_id, "plan": plan, "lines": [], "missing": []}
        return {
            "room": None,
            "targets": [],
            "verdicts": {},
            "replies": [],
            "missing": [],
            "timed_out": False,
            "clock": service.clock(),
            "turn": turn,
        }

    switch = switch or SwitchClient()
    room = switch.find_room(room_name)
    room_id = room["room_id"]

    # Record the user's line first: a slow or dead agent must never erase it from the UI.
    service.record_event(
        "user",
        "dialogue",
        "You: " + message,
        participants=["user", *present],
        visibility="public",
        room_id=room_id,
        metadata=_metadata(turn_id, "speech", "primary", "neutral", None, False),
    )
    service.record_event(
        "director",
        "turn_plan",
        _plan_summary(plan),
        participants=[],
        visibility="public",
        room_id=room_id,
        metadata={"turn_id": turn_id, "plan": plan, "topic": plan["topic"]},
    )

    cap = min(max(1.0, float(timeout)), TURN_CAP_SECONDS)
    deadline = time.time() + cap
    started = int(time.time() * 1000) - 500
    try:
        for character in present:
            if time.time() >= deadline:
                break
            verdict = verdicts[character]
            switch.post(
                room_id,
                _prompt_for(
                    service, character, message, verdict, _role_for(plan, character)
                ),
            )
    except SwitchError as exc:
        raise RuntimeError(
            "the Switch room did not accept the message; check that the gateway and the "
            f"four live sessions are running ({exc})"
        ) from exc

    seen: dict[str, dict] = {}
    while time.time() < deadline and len(seen) < len(speakers):
        try:
            events = switch.history(room_id)
        except SwitchError:
            events = []
        for event in events:
            sender = event.get("sender_name")
            if sender not in speakers or sender in seen:
                continue
            if int(event.get("timestamp") or 0) <= started:
                continue
            body = (event.get("body") or "").strip()
            if not body or any(marker in body.lower() for marker in PLACEHOLDERS):
                continue
            seen[sender] = event
        if len(seen) >= len(speakers):
            break
        time.sleep(1.0)

    lines: list[dict] = []
    replies: list[dict] = []
    for character in speakers:
        role = _role_for(plan, character)
        verdict = verdicts[character]
        event = seen.get(character)
        if not event:
            silence = service.record_event(
                character,
                "silence",
                f"{character.title()} stays silent.",
                participants=[character],
                visibility="public",
                room_id=room_id,
                metadata=_metadata(
                    turn_id, "silence", role, "neutral", plan.get("primary"), False
                ),
            )
            lines.append(
                {
                    "character": character,
                    "mode": "silence",
                    "role": role,
                    "text": None,
                    "expression": "neutral",
                    "event_id": silence["id"],
                }
            )
            continue

        body = (event.get("body") or "").strip()
        if verdict["stance"] in {"refuse", "hard_refuse"} or social.contains_leak(body, verdict):
            body = social.deflection(character, verdict, message)
        message_id = str(event.get("event_id") or "")
        if message_id and service.event_by_message_id(message_id):
            continue

        social.record_verdict(service, character, verdict)
        social.apply_deltas(service, character, verdict)
        mode, text = _beat_mode(body, role)
        expression = _expression(verdict, role, mode)
        kind = "action" if mode == "action" else "dialogue"
        summary = (
            f"{character.title()}: {text}"
            if kind == "dialogue"
            else f"{character.title()} {text}"
        )
        recorded = service.record_event(
            character,
            kind,
            summary,
            participants=[character],
            visibility="public",
            room_id=room_id,
            message_id=message_id,
            metadata=_metadata(
                turn_id, mode, role, expression, plan.get("primary"), plan["chorus"]
            ),
        )
        lines.append(
            {
                "character": character,
                "mode": mode,
                "role": role,
                "text": text,
                "expression": expression,
                "event_id": recorded["id"],
            }
        )
        replies.append(
            {
                "character": character,
                "text": text,
                "event_id": recorded["id"],
                "message_id": event.get("event_id"),
            }
        )

    turn_missing = [character for character in speakers if character not in seen]
    missing = [character for character in present if character not in seen]
    turn = {"id": turn_id, "plan": plan, "lines": lines, "missing": turn_missing}
    return {
        "room": room,
        "targets": present,
        "verdicts": verdicts,
        "replies": replies,
        "missing": missing,
        "timed_out": bool(turn_missing),
        "clock": service.clock(),
        "turn": turn,
    }
