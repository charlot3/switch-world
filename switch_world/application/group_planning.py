"""Deterministic group-turn planning, roles and prompt construction.

This is the planning half of the old ``director/group.py``. It is pure with
respect to the room: it reads the world to rank speakers and builds the text
the transport will carry, but it never posts, records or constructs a client.

``director/group.py`` re-exports these names so older imports keep working
while the turn pipeline lives in :mod:`switch_world.application.turns`.
"""
from __future__ import annotations

import re
import uuid
from typing import Mapping

from world_engine.service import WorldService

from director import arbiter as social_arbiter
from director import context, social
from director.social import PLACEHOLDERS, _strip_meta

DEFAULT_CHARACTERS = ("alice", "emily", "sophia", "mia")
CHORUS_TOPICS = {"small-talk", "personal"}
INTIMATE_TOPICS = {"private-emotional", "body", "contact"}
# A first-person body narration is a result, not a shared fact the room repeats.
BODY_RESULT_MARKERS = (
    "sit", "stand", "walk", "order", "open", "close", "drink", "eat", "lean",
    "nod", "smile", "laugh", "look", "turn", "put", "cross", "shake", "sip",
)
MAX_MESSAGE = 800
TURN_CAP_SECONDS = 35.0


def _is_shared_fact(message: str, classified: dict) -> bool:
    """Chorus is reserved for shared facts: a question or plain small talk."""
    if classified["topic"] not in CHORUS_TOPICS:
        return False
    if classified["action_mode"] != "result":
        return False
    text = message or ""
    if "?" in text or "？" in text:
        return True
    lowered = text.lower()
    return not any(
        re.search(r"\b" + re.escape(marker) + r"\b", lowered)
        for marker in BODY_RESULT_MARKERS
    )


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


def _sanitise_reply(
    character: str, body: str, verdict: dict, message: str
) -> str:
    """Replace a refused or topic-leaking model line with the policy's own line.

    Shared by the planned-speaker path and the relay path so the two cannot drift.
    """
    if (
        verdict["stance"] in {"refuse", "hard_refuse"}
        or (verdict["stance"] == "limited" and social.looks_like_refusal(body))
        or social.contains_leak(body, verdict)
    ):
        return social.deflection(character, verdict, message)
    return body


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


def _agent_mentions(text: str, present: list[str], sender: str) -> list[str]:
    """Present characters addressed by `@name`, or by a direct name at line start.

    Explicit `@name` is the contract. A leading ``Emily,`` / ``Emily —`` is accepted
    too because live roleplay models often write the address naturally; a plain
    mention ("Emily is hiding something") is not an address and does not relay.
    """
    available = {character.lower() for character in present}
    sender = (sender or "").lower()
    found: list[str] = []
    for raw in re.findall(r"@([A-Za-z0-9]+)", text or ""):
        name = raw.lower()
        if name == sender or name not in available or name in found:
            continue
        found.append(name)
    if not found:
        leading = re.match(r"^\s*([A-Za-z]{3,})\s*[,:;—–-]", text or "")
        if leading:
            name = leading.group(1).lower()
            if name != sender and name in available:
                found.append(name)
    return found


def _relay_prompt(
    service: WorldService, sender: str, target: str, text: str
) -> str:
    """One agent-to-agent aside inside the scene, never a private room."""
    relationship = social.relationship_block(service, target)
    return (
        f"@{target} {sender.title()} says to you: \"{text}\"\n\n"
        "Answer them directly, one or two short sentences, in your own voice.\n"
        "This is an aside inside the scene; do not address the room.\n"
        "Do not mention another @name in this reply.\n"
        "If this tells you something you did not know, record it with "
        f"world__remember(..., source=\"character:{sender}\") before replying.\n\n"
        f"{relationship}"
    )


def _affinity(service: WorldService | None, character: str) -> float:
    return float(social.affinity(service, character)["score"]) if service else 0.0


def _tension(service: WorldService | None, source: str, target: str) -> float:
    if service is None:
        return 0.0
    return float(service.relationship(source, target)["tension"])


def plan_turn(
    message: str,
    present: list[str],
    verdicts: Mapping[str, dict],
    service: WorldService | None = None,
) -> dict:
    """The deterministic stage direction for one user line.

    Connection-based: a named addressee wins; otherwise the primary is the character
    with the highest affinity to the user (or, for an intimate probe, the highest
    relevant tension). The reactor is the present character with the highest tension
    toward the primary — a real character↔character stake. A chorus is only used for
    shared facts, and never more than three voices. Everyone else is silent.
    """
    classified = social.classify(message)
    topic = classified["topic"]
    plan = {
        "primary": None,
        "reactors": [],
        "silent": [],
        "chorus": False,
        "topic": topic,
        "action_mode": classified["action_mode"],
        "response": None,
        "responses": {},
    }
    if not present:
        return plan

    def finish(primary: str | None, reactors: list[str]) -> dict:
        reactors = list(dict.fromkeys(c for c in reactors if c and c != primary))
        plan.update(
            {
                "primary": primary,
                "reactors": reactors,
                "silent": [
                    c for c in present if c != primary and c not in reactors
                ],
            }
        )
        plan["response"] = (verdicts.get(primary or "") or {}).get("response")
        plan["responses"] = {
            c: (verdicts.get(c) or {}).get("response") for c in present
        }
        return plan

    def reactor_toward(primary: str) -> str | None:
        others = [c for c in present if c != primary]
        if not others:
            return None
        candidate = max(others, key=lambda c: _tension(service, c, primary))
        if service is not None and _tension(service, candidate, primary) <= 0:
            return None
        return candidate if service is not None else others[0]

    addressee = _named_addressee(message, present)
    if addressee:
        reactor = reactor_toward(addressee)
        return finish(addressee, [reactor] if reactor else [])

    if _is_shared_fact(message, classified):
        ranked = sorted(
            present,
            key=lambda c: (-_affinity(service, c), present.index(c)),
        )
        chosen = set(ranked[: min(3, len(present))])
        if len(chosen) == 1:
            return finish(ranked[0], [])
        ordered = [c for c in present if c in chosen]
        plan.update(
            {
                "primary": ranked[0],
                "chorus": True,
                "chorus_speakers": ordered,
                "silent": [c for c in present if c not in chosen],
            }
        )
        plan["response"] = (verdicts.get(ranked[0]) or {}).get("response")
        plan["responses"] = {
            c: (verdicts.get(c) or {}).get("response") for c in present
        }
        return plan

    if topic in INTIMATE_TOPICS:
        primary = max(
            present,
            key=lambda c: (
                float((verdicts.get(c) or {}).get("tension", 0.0)),
                _affinity(service, c),
                -present.index(c),
            ),
        )
    else:
        primary = max(
            present, key=lambda c: (_affinity(service, c), -present.index(c))
        )
    reactor = reactor_toward(primary)
    return finish(primary, [reactor] if reactor else [])


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
    response = plan.get("response") or "none"
    mode = plan.get("action_mode") or "result"
    if plan.get("chorus"):
        who = ", ".join(plan.get("chorus_speakers") or [])
        base = f"Turn plan: chorus ({who}) on {plan['topic']}."
    else:
        primary = plan.get("primary") or "nobody"
        reactors = ", ".join(plan.get("reactors") or []) or "none"
        silent = ", ".join(plan.get("silent") or []) or "none"
        base = (
            f"Turn plan: primary {primary}; reactors {reactors}; silent {silent} "
            f"on {plan['topic']}."
        )
    return f"{base} Action {mode}; response {response}."


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
            "directly in your own voice, in one or two short sentences. Speak in first "
            "person. Do not describe another character in third person; if you address "
            "them, say 'you' or use @name."
        )
    if role == "reactor":
        return (
            "Stage direction: you are a reactor this beat. Add one short reaction, spoken "
            "or a brief action in *asterisks*. If you speak, use first person and address "
            "the person you mean as 'you'; never narrate another character in third person. "
            "Do not take over the scene."
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


def _recent_scene_lines(
    service: WorldService, character: str, limit: int = 12
) -> list[str]:
    phone = service.phone_history(
        character, limit=limit, include_scene=True
    )["messages"]
    lines = [
        ("You: " if item["role"] == "user" else f"{character.title()}: ")
        + item["text"]
        for item in phone
        if item["kind"] == "scene"
    ]
    return lines[-6:]


def _memory_lines(service: WorldService, character: str, message: str) -> list[str]:
    memories = service.recall(character, query=message, limit=6)["memories"]
    return [
        f"- {item['proposition']} (source {item['source']}, "
        f"confidence {item['confidence']:.2f})"
        for item in memories
    ]


def _prompt_for(
    service: WorldService,
    character: str,
    message: str,
    verdict: dict,
    role: str,
    arbiter_note: dict | None = None,
    present: list[str] | None = None,
) -> str:
    social_block = "\n\n".join(
        [
            social.relationship_block(service, character),
            social.policy_block(verdict),
            social.response_block(verdict),
            social.action_block(verdict),
        ]
    )
    if arbiter_note and arbiter_note.get("used"):
        social_block += "\n\n" + social_arbiter.block(arbiter_note)
    if verdict.get("action_mode") == "attempt":
        social_block += (
            "\n\nThis is an attempt on you, not a fact. It is never automatic success: "
            "you decide what, if anything, you allow."
        )
    others = [c.title() for c in (present or []) if c != character]
    address_rule = ""
    if others:
        address_rule = (
            "\n\nIf you are answering another character rather than the user, address "
            f"that character once with @name ({', '.join(others)}). Address at most one "
            "character; never @ the whole room."
        )
    projected = context.project_context(
        social_block=social_block,
        extra=_role_instruction(role),
        message=(
            f'The user says to the room: "{message}"\n\n'
            "Reply only as yourself. Sound like a person in the room, not a narrator: "
            "one concrete detail, one thing left unsaid, no therapy-speak, no summary "
            "of the relationship or the scene, and no question that exists only to keep "
            "the conversation going. Speak in first person; never narrate another "
            "character in third person. Keep it 17+ SFW. Do not mention the policy, the "
            "stage direction, or that you are following instructions. Never write "
            "'@user', '@director', or any line about being online, offline, or needing "
            "to leave — you are present in this room and you answer as yourself."
            f"{address_rule}"
        ),
        scene_lines=_recent_scene_lines(service, character),
        memories=_memory_lines(service, character, message),
        history_label="",
        scene_label="Recent scene (public)",
    )
    return f"@{character} {projected['text']}"


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


__all__ = [
    "BOUNDARY_CONFIDENCE",
    "BOUNDARY_KEY",
    "BOUNDARY_REACTIONS",
    "CHORUS_TOPICS",
    "DEFAULT_CHARACTERS",
    "INTIMATE_TOPICS",
    "MAX_MESSAGE",
    "PLACEHOLDERS",
    "TURN_CAP_SECONDS",
    "_agent_mentions",
    "_beat_mode",
    "_boundary_target",
    "_clean_character",
    "_expression",
    "_is_shared_fact",
    "_limit_words",
    "_memory_lines",
    "_metadata",
    "_named_addressee",
    "_plan_summary",
    "_prompt_for",
    "_recent_scene_lines",
    "_relay_prompt",
    "_role_for",
    "_role_instruction",
    "_sanitise_reply",
    "_speakers",
    "_strip_meta",
    "_turn_id",
    "plan_turn",
]
