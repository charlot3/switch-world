"""A private DM through the same Bifrost/OpenCode character model.

The phone panel in the dashboard posts here. It is deliberately separate from the
authored beats: a DM can range freely, but it still writes only through WorldService and
still has to respect the canon/private-fact rules.

The model returns the same small JSON envelope as the beat runner, so a DM can leave a
belief or move a relationship with provenance instead of vanishing into a transcript.
"""
from __future__ import annotations

from world_engine.service import WorldService

from .bifrost_scene import _apply, _parse_envelope, _system
from .canon import load as load_canon, validate
from .tavily_beat import world_context

MAX_MESSAGE = 800


def reply_to_dm(
    service: WorldService,
    character: str,
    message: str,
    client=None,
) -> dict:
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message must be at most {MAX_MESSAGE} characters")
    characters = {item["id"] for item in service.characters()}
    if character not in characters:
        raise ValueError(f"unknown character: {character}")
    if client is None:
        from gateway.bifrost import BifrostClient

        client = BifrostClient()

    canon = load_canon()
    context = world_context(service)
    history = [
        event for event in service.state()["events"]
        if event["kind"] == "dm" and character in (event.get("participants") or [])
    ][-8:]
    history_text = "\n".join(event["summary"] for event in history) or "(no earlier DMs)"
    memories = service.recall(character, query=message, limit=6)["memories"]
    memory_text = "\n".join(
        f"- {item['proposition']} (source {item['source']}, confidence {item['confidence']:.2f})"
        for item in memories
    ) or "(nothing relevant)"
    messages = [
        {"role": "system", "content": _system(character, canon, context)},
        {
            "role": "user",
            "content": (
                "This is a private one-to-one DM with the user, not the café scene.\n\n"
                f"Your own memories and public facts:\n{memory_text}\n\n"
                f"Recent private DM:\n{history_text}\n\n"
                f'The user says: "{message}"\n'
                "Reply in character in 1-3 sentences, dialogue only, no stage directions. "
                "Use the history; do not contradict it. Do not reveal another character's "
                "private facts. All characters are adults; keep it 17+ SFW and never "
                "explicit. Return the JSON envelope."
            ),
        },
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
    envelope = _parse_envelope(client.chat_json(character, messages), character)
    reply = envelope["reply"]

    service.record_event(
        character,
        "dm",
        f"{character.title()}: {reply}",
        participants=[character, "user"],
        visibility="private",
    )
    writes = _apply(service, character, envelope)
    issues = validate(service, canon)
    if issues:
        service.record_event(
            "director",
            "canon_warning",
            "DM worldline check: " + "; ".join(issues),
            participants=[],
            visibility="public",
        )
    usage = client.usage_summary() if hasattr(client, "usage_summary") else {}
    return {
        "character": character,
        "reply": reply,
        "writes": writes,
        "canon_issues": issues,
        "bifrost": usage,
    }
