"""A private DM through the same Bifrost/OpenCode character model.

The phone panel in the dashboard posts here. It is deliberately separate from the
authored beats: a DM can range freely, but it still writes only through WorldService and
still has to respect the canon/private-fact rules.

The model returns the same small JSON envelope as the beat runner, so a DM can leave a
belief or move a relationship with provenance instead of vanishing into a transcript.
"""
from __future__ import annotations

from world_engine.service import WorldService

from . import social
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
    phone = service.phone_history(character, limit=100)["messages"]
    history = [message for message in phone if message["kind"] == "dm"]
    scene = [message for message in phone if message["kind"] == "scene"][-6:]
    history_text = "\n".join(
        ("You: " if message["role"] == "user" else f"{character.title()}: ") + message["text"]
        for message in history
    ) or "(no earlier DMs)"
    scene_text = "\n".join(
        ("You: " if message["role"] == "user" else f"{character.title()}: ") + message["text"]
        for message in scene
    ) or "(no recent scene lines)"
    clock = service.clock()["now"]
    verdict = social.appraise(service, character, message, public=False)
    social_block = social.relationship_block(service, character) + "\n\n" + social.policy_block(verdict)
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
    memories = service.recall(character, query=message, limit=6)["memories"]
    memory_text = "\n".join(
        f"- {item['proposition']} (source {item['source']}, confidence {item['confidence']:.2f})"
        for item in memories
    ) or "(nothing relevant)"
    messages = [
        {"role": "system", "content": _system(character, canon, context, clock=clock, social_block=social_block)},
        {
            "role": "user",
            "content": (
                "This is a private text DM with the user, not the café scene. Do not describe the user \n"
                "as physically present or sitting across from you; you are texting.\n\n"
                f"Current world time: {clock}\n"
                f"Your own memories and public facts:\n{memory_text}\n\n"
                f"Recent café context (public):\n{scene_text}\n\n"
                f"Recent private DM:\n{history_text}\n\n"
                f'The user says: "{message}"\n'
                f"{answer_rule} Sound like a person texting: 1-2 sentences, "
                "concrete detail, subtext, not a neat emotional summary or a support-agent "
                "answer. Mirror the user's language; if they wrote Chinese, reply in "
                "natural spoken Chinese with no translationese. Do not start with a meta "
                "preface like '认真答' or '说实话'; just answer. Use short sentences and at "
                "most one dash. Use the time and history; "
                "do not claim it is closing time unless the clock is evening. Do not reveal "
                "another character's private facts. All characters are adults; keep it 17+ "
                "SFW and never explicit. Return the JSON envelope."
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
    if verdict["stance"] in {"refuse", "hard_refuse"} or social.contains_leak(reply, verdict):
        reply = social.deflection(character, verdict, message)
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
    usage = client.usage_summary() if hasattr(client, "usage_summary") else {}
    return {
        "character": character,
        "reply": reply,
        "social": verdict,
        "writes": writes,
        "canon_issues": issues,
        "bifrost": usage,
    }
