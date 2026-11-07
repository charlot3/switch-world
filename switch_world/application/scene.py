"""Scene use cases.

The group turn, the private DM and the whisper all live here. A use case
receives the world service and an injected port -- a
:class:`CharacterTransport` for the group and the whisper's private room, a
:class:`~switch_world.domain.ports.model.ModelClient` for the model-written
replies -- and never constructs one itself.

The DM keeps its historical prompt and envelope exactly: the same system
prompt, the same phone history, the same world-time string and the same
``_parse_envelope`` / ``_apply`` writes. The whisper keeps its private event
order and return shape, and checks ``transport.capabilities().private_rooms``
instead of probing the backend. Every path shares one policy sanitiser
(:func:`_sanitise_reply`) and one meta/placeholder filter
(:func:`clean_scene_line`), so a refusal, leak or placeholder is handled in
exactly one place.
"""
from __future__ import annotations

import re
import time
from typing import Any

from director import context, social
from director.bifrost_scene import _apply, _parse_envelope, _system
from director.canon import load as load_canon, validate
from director.social import clean_scene_line
from director.tavily_beat import world_context
from world_engine.service import WorldService

from switch_world.domain.ids import CharacterId, TurnId
from switch_world.domain.ports.model import ModelClient, ModelFormat
from switch_world.domain.ports.transport import (
    CharacterTransport,
    Prompt,
    RoomHandle,
)

from .group_planning import (
    DEFAULT_CHARACTERS,
    MAX_MESSAGE,
    TURN_CAP_SECONDS,
    _boundary_target,
    _clean_character,
    _metadata,
    _sanitise_reply,
    _strip_meta,
    _turn_id,
    plan_turn,
)
from .turns import TurnRecorder


def resolve_cast(service: WorldService, characters: list[str] | None) -> list[str]:
    """The requested cast, or the active scene's cast, de-duplicated."""
    if characters is None:
        state = service.state()
        scene = state.get("scene") or {}
        cast = (
            scene.get("cast")
            or (state.get("scenario") or {}).get("cast")
            or list(DEFAULT_CHARACTERS)
        )
        requested = [_clean_character(c) for c in cast]
    else:
        requested = [_clean_character(c) for c in characters]
    return list(dict.fromkeys(requested))


def say_in_group(
    service: WorldService,
    message: str,
    characters: list[str] | None = None,
    transport: CharacterTransport | None = None,
    room_name: str = "world",
    timeout: float = TURN_CAP_SECONDS,
    arbiter_client: Any | None = None,
    *,
    time_source: Any | None = None,
) -> dict:
    """Post one user line to the group room and record the planned replies.

    ``transport`` is injected by the composition root; this use case never
    constructs one. The return shape is the legacy group-turn shape.
    """
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message is too long (max {MAX_MESSAGE} characters)")
    if transport is None:
        raise ValueError("transport is required")

    requested = resolve_cast(service, characters)
    # Presence is part of the scene: a character who left is not addressed or posted to.
    present = [c for c in requested if not service.is_absent(c)]
    verdicts = {
        character: social.appraise(service, character, message, public=True)
        for character in present
    }
    turn_id = _turn_id()
    recorder = TurnRecorder(
        service,
        transport,
        room_name=room_name,
        time_source=time_source,
    )

    boundary_target = (
        _boundary_target(message, present, verdicts) if present else None
    )
    if boundary_target:
        return recorder.record_boundary(
            message, present, verdicts, boundary_target, turn_id
        )

    plan = plan_turn(message, present, verdicts, service=service)
    return recorder.record_turn(
        message,
        present,
        verdicts,
        plan,
        turn_id,
        timeout=timeout,
        arbiter_client=arbiter_client,
    )


def dm(
    service: WorldService,
    character: str,
    message: str,
    model: ModelClient | None = None,
    *,
    model_factory: Any | None = None,
) -> dict:
    """Post one private DM and record the character's answer.

    The prompt, system text, phone history and world-time string are the
    historical DM construction, unchanged. The model is injected by the
    composition root (or by the compatibility shim), and its JSON envelope is
    parsed and applied exactly as before.

    ``model_factory`` is only called after the message and character are
    validated, so an invalid request never constructs a model (and so never
    needs provider credentials). The compatibility shim uses it to keep HEAD's
    lazily-built default client.
    """
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message must be at most {MAX_MESSAGE} characters")
    characters = {item["id"] for item in service.characters()}
    if character not in characters:
        raise ValueError(f"unknown character: {character}")
    # Resolve the default client only once the request is known to be valid.
    if model is None and model_factory is not None:
        model = model_factory()
    if model is None:
        raise ValueError("model is required")

    canon = load_canon()
    world = world_context(service)
    phone = service.phone_history(character, limit=100, include_scene=True)["messages"]
    history_lines = [
        ("You: " if item["role"] == "user" else f"{character.title()}: ") + item["text"]
        for item in phone
        if item["kind"] == "dm"
    ]
    scene_lines = [
        ("You: " if item["role"] == "user" else f"{character.title()}: ") + item["text"]
        for item in phone
        if item["kind"] == "scene"
    ][-6:]
    clock = service.clock()["now"]
    verdict = social.appraise(service, character, message, public=False)
    social_block = (
        social.relationship_block(service, character)
        + "\n\n"
        + social.policy_block(verdict)
        + "\n\n"
        + social.response_block(verdict)
        + "\n\n"
        + social.action_block(verdict)
    )
    if verdict["stance"] in {"answer", "tease"}:
        answer_rule = (
            "Be responsive: answer the question directly in the first sentence, before any "
            "joke or deflection. Do not replace the answer with another question."
        )
    else:
        answer_rule = (
            "Do not answer the question. Follow the social policy above and deflect or refuse "
            "in your own voice; do not lecture and do not mention the policy."
        )
    if verdict.get("action_mode") == "attempt":
        answer_rule += (
            " The user is attempting something that affects you. It is never automatic "
            "success: decide for yourself and answer from the response spectrum."
        )
    memories = service.recall(character, query=message, limit=6)["memories"]
    memory_lines = [
        f"- {item['proposition']} (source {item['source']}, "
        f"confidence {item['confidence']:.2f})"
        for item in memories
    ]
    system_prompt = _system(
        character, canon, world, clock=clock, social_block=social_block
    )
    projected = context.project_context(
        extra=(
            "This is a private text DM with the user, not the café scene. Do not describe "
            "the user as physically present or sitting across from you; you are texting.\n\n"
            f"Current world time: {clock}\n\n"
            f"{answer_rule}"
        ),
        message=(
            f'The user says: "{message}"\n'
            "Sound like a person texting: 1-2 sentences, concrete detail, subtext, not a "
            "neat emotional summary or a support-agent answer. Mirror the user's language; "
            "if they wrote Chinese, reply in natural spoken Chinese with no translationese. "
            "Do not start with a meta preface like '认真答' or '说实话'; just answer. Use "
            "short sentences and at most one dash. Use the time and history; do not claim "
            "it is closing time unless the clock is evening. Do not reveal another "
            "character's private facts. All characters are adults; keep it 17+ SFW and "
            "never explicit. Return the JSON envelope."
        ),
        history_lines=history_lines,
        scene_lines=scene_lines,
        memories=memory_lines,
        history_label="Recent private DM",
        scene_label="Recent café context (public)",
        memory_label="Your own memories and public facts",
        reserved=len(system_prompt.encode("utf-8")),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": projected["text"]},
    ]
    # Record the user's turn before the model call. The dashboard polls every 2.5s;
    # if the turn only existed optimistically in the browser it would vanish while the
    # character is thinking.
    service.record_event(
        "user",
        "dm",
        f"You: {message}",
        participants=[character, "user"],
        visibility="private",
    )
    reasoning = "high" if verdict["topic"] in {"body", "contact"} else "low"
    response = model.generate(
        CharacterId(character),
        messages,
        format=ModelFormat.JSON,
        reasoning=reasoning,
    )
    raw = response.data if response.data is not None else response.text
    envelope = _parse_envelope(raw, character)
    reply = clean_scene_line(envelope["reply"])
    if not reply:
        reply = social.deflection(character, verdict, message)
    reply = _sanitise_reply(character, reply, verdict, message)
    envelope["reply"] = reply

    service.record_event(
        character,
        "dm",
        f"{character.title()}: {reply}",
        participants=[character, "user"],
        visibility="private",
    )
    writes = _apply(service, character, envelope)
    social.record_verdict(service, character, verdict)
    social.apply_deltas(service, character, verdict)
    issues = validate(service, canon)
    if issues:
        service.record_event(
            "director",
            "canon_warning",
            "DM worldline check: " + "; ".join(issues),
            participants=[],
            visibility="public",
        )
    return {
        "character": character,
        "reply": reply,
        "social": verdict,
        "reasoning": reasoning,
        "writes": writes,
        "canon_issues": issues,
        "bifrost": _usage_result(model, character),
    }


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


def whisper(
    service: WorldService,
    to: str,
    message: str,
    model: ModelClient | None = None,
    transport: CharacterTransport | None = None,
    *,
    timeout: float = TURN_CAP_SECONDS,
    model_factory: Any | None = None,
) -> dict:
    """Whisper privately to one character while the room watches.

    The private user event is recorded first. If the injected transport declares
    ``capabilities().private_rooms``, the words travel through
    ``transport.open_room(private_for=...)`` and only the target answers. A
    transport without private rooms -- or a private-room lookup that fails --
    falls back to a *staged* answer through ``model``; the result says
    ``transport: "staged"`` so it never claims a privacy the transport cannot
    prove.

    ``model`` is used for the staged answer and, when supplied, the observers'
    public reactions. ``model_factory`` is only called on the staged path, so a
    private-room whisper never constructs a model. The return shape is the
    historical whisper shape.
    """
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
    whisper_event = service.record_event(
        "user",
        "whisper",
        f"You whisper to {to.title()}: {message}",
        participants=[to, "user"],
        visibility="private",
        metadata=_metadata(turn_id, "whisper", "primary", "neutral", to, False),
    )

    private_room = _private_room(transport, to)
    writes: dict = {}
    reply: str
    if private_room is not None:
        reply = _answer_in_private_room(
            transport, private_room, to, message, turn_id, timeout
        )
        # The private room writes its own line, but it is still a model line:
        # the same policy gate applies here as on the staged path.
        reply = _sanitise_reply(to, reply, verdict, message)
        transport_name = "switch"
    else:
        if model is None and model_factory is not None:
            model = model_factory()
        if model is None:
            raise ValueError("model is required")
        raw = _model_data(
            model.generate(
                CharacterId(to),
                _target_messages(service, to, message, verdict),
                format=ModelFormat.JSON,
                reasoning=(
                    "high" if verdict["topic"] in {"body", "contact"} else "low"
                ),
            )
        )
        envelope = _parse_envelope(raw, to)
        reply = clean_scene_line(envelope["reply"])
        if not reply:
            reply = social.deflection(to, verdict, message)
        # The one shared policy path: group, DM and whisper cannot drift.
        reply = _sanitise_reply(to, reply, verdict, message)
        envelope["reply"] = reply
        writes = _apply(service, to, envelope)
        transport_name = "staged"

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
        c
        for c in cast
        if c != to and c in DEFAULT_CHARACTERS and not service.is_absent(c)
    ]
    observers = present[:MAX_OBSERVERS]
    observer_lines = [
        _observe(service, observer, message, to, model, turn_id)
        for observer in observers
    ]

    lines = [
        {
            "character": to,
            "mode": "whisper",
            "role": "primary",
            "text": message,
            "expression": "neutral",
            "event_id": whisper_event["id"],
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
        "transport": transport_name,
        "target": to,
        "reply": reply,
        "verdict": verdict,
        "writes": writes,
        "observers": [line["character"] for line in observer_lines],
        "private_event_id": whisper_event["id"],
        "reply_event_id": private_reply["id"],
        "turn": turn,
    }


def _private_room(transport: CharacterTransport | None, to: str) -> RoomHandle | None:
    """The transport's private room, or ``None`` when there is not one.

    Capabilities decide, never ``hasattr``: a transport that cannot prove a
    private room gets the staged path. A lookup failure is likewise "no private
    room", exactly as HEAD treated a raising ``find_private_room``.
    """
    if transport is None:
        return None
    capabilities = transport.capabilities()
    if not capabilities.private_rooms:
        return None
    try:
        return transport.open_room(
            name=f"whisper-{to}", private_for=CharacterId(to)
        )
    except Exception:
        return None


def _answer_in_private_room(
    transport: CharacterTransport,
    room: RoomHandle,
    to: str,
    message: str,
    turn_id: str,
    timeout: float,
) -> str:
    """Deliver into the private room and wait for the target's own answer."""
    deadline = time.monotonic() + float(timeout)
    delivery = transport.deliver_many(
        room,
        [Prompt(speaker=CharacterId(to), text=message)],
        turn_id=TurnId(turn_id),
        deadline=deadline,
    )
    inbound = list(delivery.inline)
    if not inbound:
        inbound = transport.collect(
            delivery, speakers=[CharacterId(to)], deadline=deadline
        )
    for item in inbound:
        body = clean_scene_line(item.text)
        if body:
            return body
    raise RuntimeError(
        "the private Switch room accepted the whisper but gave no answer"
    )


def _model_data(response: Any) -> Any:
    """The envelope data a model reply carries, or its text for a plain reply."""
    data = getattr(response, "data", None)
    return data if data is not None else getattr(response, "text", None)


def _tokens(text: str) -> set[str]:
    """Every alphanumeric token, including one-letter ones: no leak is too small."""
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _without_tokens(text: str, forbidden: set[str]) -> str:
    """Remove every word whose token is in `forbidden`, preserving the rest."""
    words = re.split(r"(\s+)", text)
    kept = [
        word
        for word in words
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
    return ""


def _recent_whisper_lines(
    service: WorldService, to: str, limit: int = 8
) -> list[str]:
    """The private back-and-forth around this whisper, without the public room."""
    lines: list[tuple[int, str]] = []
    for kind, label in (("whisper", "You"), ("whisper_reply", to.title())):
        for event in service.events(kind=kind)[-limit * 3:]:
            participants = event.get("participants") or []
            if to not in participants or "user" not in participants:
                continue
            summary = event.get("summary") or ""
            if ":" not in summary:
                continue
            text = summary.split(":", 1)[1].strip()
            if text:
                lines.append(
                    (int(event.get("id") or 0), f"{label} (whisper): {text}")
                )
    lines.sort(key=lambda item: item[0])
    return [text for _, text in lines[-limit:]]


def _target_messages(
    service: WorldService, to: str, message: str, verdict: dict
) -> list[dict]:
    canon = load_canon()
    world = world_context(service)
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
    phone = service.phone_history(to, limit=12, include_scene=True)["messages"]
    history_lines = [
        ("You: " if item["role"] == "user" else f"{to.title()}: ") + item["text"]
        for item in phone
        if item["kind"] == "dm"
    ]
    scene_lines = [
        ("You: " if item["role"] == "user" else f"{to.title()}: ") + item["text"]
        for item in phone
        if item["kind"] == "scene"
    ][-6:]
    history_lines.extend(_recent_whisper_lines(service, to))
    current = f"You (whisper): {message}"
    if history_lines and history_lines[-1].strip() == current.strip():
        # The current whisper is already the prompt's message; don't show it twice.
        history_lines.pop()
    system = _system(to, canon, world, clock=clock, social_block=social_block)
    projected = context.project_context(
        extra=(
            "The user leans in and whispers privately to you. No one else can hear it. "
            "This is not the group scene; do not address the room."
        ),
        message=(
            f'The user whispers: "{message}"\n\n'
            "Answer in a whisper in your own voice: one or two short sentences, each "
            "under about 18 words. React to the feeling and the private history, not "
            "just the literal words. Do not ask the user to clarify what they meant and "
            "do not explain their sentence back to them; make a guess, take a side, or "
            "tease. If you ask a question, make it a playful or intimate guess, not a "
            "request for information. All characters are adults and the tone stays "
            "17+ SFW. Return the JSON envelope."
        ),
        history_lines=history_lines,
        scene_lines=scene_lines,
        history_label="Recent private exchange (DM and whisper)",
        scene_label="Recent scene (public)",
        reserved=len(system.encode("utf-8")),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": projected["text"]},
    ]


def _observer_messages(
    service: WorldService, observer: str, message: str
) -> list[dict]:
    canon = load_canon()
    world = world_context(service)
    clock = service.clock()["now"]
    return [
        {
            "role": "system",
            "content": _system(
                observer,
                canon,
                world,
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
    model: ModelClient | None,
    turn_id: str,
) -> dict:
    """One observer's public reaction; empty after cleaning means a real silence."""
    reply = ""
    if model is not None:
        try:
            raw = _model_data(
                model.generate(
                    CharacterId(observer),
                    _observer_messages(service, observer, message),
                    format=ModelFormat.JSON,
                )
            )
            reply = _parse_envelope(raw, observer)["reply"]
        except Exception:
            reply = ""
    # The observers saw the whisper happen, never its words; the shared line
    # filter drops stage machinery and a lone ellipsis placeholder, and the
    # observer fallback keeps a safe, non-leaking public line.
    reaction = _observer_reaction(observer, clean_scene_line(reply), message)
    if not reaction:
        event = service.record_event(
            observer,
            "silence",
            f"{observer.title()} stays silent.",
            participants=[observer],
            visibility="public",
            metadata=_metadata(
                turn_id, "silence", "reactor", "neutral", target, False
            ),
        )
        return {
            "character": observer,
            "mode": "silence",
            "role": "reactor",
            "text": None,
            "expression": "neutral",
            "event_id": event["id"],
            "private": False,
        }
    event = service.record_event(
        observer,
        "dialogue",
        f"{observer.title()}: {reaction}",
        participants=[observer],
        visibility="public",
        metadata=_metadata(
            turn_id, "reaction", "reactor", "alarmed", target, False
        ),
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


def _usage_result(model: ModelClient, character: str) -> Any:
    """The historical ``bifrost`` block: a legacy dict, or a usage summary."""
    usage_summary = getattr(model, "usage_summary", None)
    if callable(usage_summary):
        return usage_summary()
    summary = model.usage(CharacterId(character))
    return {
        "prompt_tokens": summary.prompt_tokens,
        "completion_tokens": summary.completion_tokens,
        "total_tokens": summary.total_tokens,
        "requests": summary.requests,
    }


__all__ = ["_strip_meta", "dm", "resolve_cast", "say_in_group", "whisper"]
