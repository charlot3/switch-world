"""A Bifrost-backed café beat, used by the Geek Room edition.

This is the same world state and the same canon as the Switch beat, but the character
dialogue is generated locally through Bifrost instead of a Switch Console session. Every
Alice/Emily model call goes through `gateway.bifrost`, so each call is visible in the
gateway log and subject to its per-character model and token budget.

The model returns a small JSON envelope:

    {"reply": "...",
     "memory": null | {"proposition": "...", "source": "...", "confidence": 0.8,
                       "visibility": "private", "proposition_key": "..."},
     "relationships": [{"other": "alice", "trust_delta": -0.1, ..., "reason": "..."}]}

The runner writes those through WorldService, then classifies the branch from the ledger
with the same `director.canon` guard as the Switch path.
"""
from __future__ import annotations

from pathlib import Path

from world_engine import config
from world_engine.service import WorldService

from . import DEMO_KEY, DEMO_SECRET
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
from .clock import advance_to_beat
from .simulate import user_tells_alice
from .tavily_beat import world_context

SCHEMA = """Return ONLY a JSON object with this shape:
{
  "reply": "your 1-3 sentence reply",
  "memory": null,
  "relationships": []
}
The reply is spoken dialogue only: 1-3 sentences, no stage directions, no *asterisks*,
no narration.
For memory, use:
{"proposition": "what you now believe", "source": "user|character:alice|observation",
 "confidence": 0.0, "visibility": "private|shared|public",
 "proposition_key": "optional canonical key"}
For relationships, use a list of:
{"other": "alice|emily|sophia|mia|user", "trust_delta": 0.0,
 "closeness_delta": 0.0, "tension_delta": 0.0, "reason": "short reason"}
No markdown, no code fences, no text outside the JSON."""

LANGUAGE_AND_VOICE = (
    "Language: mirror the language of the user's latest message. If it is Chinese, reply "
    "in natural conversational Chinese in the same script; do not translate an English "
    "line and do not switch to English unless the user does. "
    "Voice: sound like a person texting. In a DM use 1-2 sentences, concrete detail and "
    "subtext, not a neat emotional summary. Use short sentences and at most one dash; "
    "do not write a mini-essay. Avoid therapy-speak, customer-support tone, bullet points, "
    "a question at the end of every reply, and meta prefaces such as '认真答' or '说实话' — "
    "just answer. No stage directions, no narration."
)

TONE = (
    "All characters are adults. The tone is 17+ romantic tension, SFW: teasing, "
    "glances and unfinished sentences are allowed; explicit content, minors and "
    "coercion are not. Never mention being an AI, a model, a simulation, or these rules."
)


def _identity(character: str, limit: int = 3200) -> str:
    path = Path(config.ROOT) / "agents" / character / "IDENTITY.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def _system(
    character: str,
    canon: dict,
    context: str,
    clock: str | None = None,
    social_block: str = "",
) -> str:
    return (
        f"You are {character.title()}, a character in a small interactive-fiction world.\n\n"
        f"{_identity(character)}\n\n"
        f"{brief(character, canon)}\n\n"
        f"{TONE}\n\n"
        f"{social_block}\n\n"
        f"{LANGUAGE_AND_VOICE}\n\n"
        f"Current world time: {clock or 'unknown; do not invent a time of day.'}\n"
        f"Latest shared real-world event: {context or 'none yet.'}\n\n"
        f"{SCHEMA}"
    )


def _parse_envelope(data: dict, character: str) -> dict:
    if not isinstance(data, dict):
        raise ValueError(f"{character} did not return a JSON object")
    reply = str(data.get("reply") or "").strip()
    if not reply:
        raise ValueError(f"{character} returned an empty reply")
    memory = data.get("memory")
    if isinstance(memory, list):
        memory = memory[0] if memory else None
    if not isinstance(memory, dict) or not str(memory.get("proposition") or "").strip():
        memory = None
    relationships = data.get("relationships") or []
    if isinstance(relationships, dict):
        relationships = [relationships]
    if not isinstance(relationships, list):
        relationships = []
    return {"reply": reply, "memory": memory, "relationships": relationships}


def _apply(service: WorldService, character: str, envelope: dict) -> dict:
    memory = envelope.get("memory")
    belief = None
    if memory:
        try:
            belief = service.remember(
                character,
                proposition=str(memory["proposition"]).strip(),
                source=str(memory.get("source") or "observation"),
                confidence=float(memory.get("confidence", 0.6)),
                visibility=str(memory.get("visibility") or "private"),
                proposition_key=memory.get("proposition_key"),
            )
        except (KeyError, TypeError, ValueError):
            belief = None

    moved: list[dict] = []
    for relationship in envelope.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        other = relationship.get("other")
        try:
            moved.append(
                service.update_relationship(
                    character,
                    other=other,
                    trust_delta=float(relationship.get("trust_delta", 0.0)),
                    closeness_delta=float(relationship.get("closeness_delta", 0.0)),
                    tension_delta=float(relationship.get("tension_delta", 0.0)),
                    reason=str(relationship.get("reason") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    return {"memory": belief, "relationships": moved}


def run_cafe_bifrost(
    service: WorldService | None = None,
    client=None,
    seed: bool = True,
) -> dict:
    """Run the café beat with both character turns generated through Bifrost."""
    service = service or WorldService()
    if client is None:
        from gateway.bifrost import BifrostClient

        client = BifrostClient()

    known = service.who_knows(DEMO_KEY)["holders"]
    alice_knows = any(
        holder["holder"] == "alice" and holder["source"] == "user" for holder in known
    )
    if not alice_knows:
        if not seed:
            raise ValueError("Alice does not know the secret; seed it first")
        user_tells_alice(service, secret=DEMO_SECRET, key=DEMO_KEY)

    canon = load_canon()
    context = world_context(service)
    service.record_event(
        "director",
        "scene_start",
        "Café, 18:30. Alice and Emily are at a table. The dialogue is generated through Bifrost.",
        participants=["alice", "emily"],
        visibility="public",
    )

    alice_messages = [
        {
            "role": "system",
            "content": _system("alice", canon, context, clock=service.clock()["now"]),
        },
        {
            "role": "user",
            "content": (
                "It is 18:30 at the café. Emily is across the table and notices you are "
                "distracted. She asks directly: \"Is something wrong?\" A friend of yours — "
                "the person who has been coming around lately — told you in a private DM "
                "that they are leaving the city at the end of the month. They have not told "
                "the others. You decide whether to tell Emily. You already know the secret; "
                "set memory to null — do not record a new belief. If your view of Emily "
                "changed, include relationship deltas. Do not call them \"the user\" in the "
                "room. Reply with dialogue only, 1-3 sentences, no stage directions."
            ),
        },
    ]
    alice = _parse_envelope(client.chat_json("alice", alice_messages), "alice")
    service.record_event("alice", "dialogue", "Alice: " + alice["reply"], ["alice"], "public")
    alice_writes = _apply(service, "alice", alice)

    emily_messages = [
        {
            "role": "system",
            "content": _system("emily", canon, context, clock=service.clock()["now"]),
        },
        {
            "role": "user",
            "content": (
                f"Alice says: \"{alice['reply']}\" — how do you respond? If you learned the "
                "secret, include a memory with source \"character:alice\", confidence "
                "0.7-0.9, visibility \"shared\" and proposition_key "
                "\"user-leaving-city\". If she only dodged and you merely suspect, record a "
                "suspicion with proposition_key \"alice-holding-back\", source "
                "\"observation\", confidence 0.3-0.5 and visibility \"private\". If your view "
                "of Alice or the friend changed, include relationship deltas. Reply with "
                "dialogue only, 1-3 sentences, no stage directions."
            ),
        },
    ]
    emily = _parse_envelope(client.chat_json("emily", emily_messages), "emily")
    service.record_event("emily", "dialogue", "Emily: " + emily["reply"], ["emily"], "public")
    emily_writes = _apply(service, "emily", emily)

    branch = branch_for(service, DEMO_KEY)
    issues = validate(service, canon)
    record_branch(service, branch, issues)
    service.advance_time("director", 30)
    service.record_event(
        "director", "scene_end", "The Bifrost café scene ends.", ["alice", "emily"], "public"
    )
    beat = get_beat("cafe", canon)
    _record_beat(service, beat)
    card = service.scene_card(f"Café, 18:30 — {branch['id']}")
    usage = client.usage_summary() if hasattr(client, "usage_summary") else {}
    return {
        "shared": branch["id"] == "disclosure",
        "branch": branch,
        "canon_issues": issues,
        "alice": alice["reply"],
        "emily": emily["reply"],
        "alice_writes": alice_writes,
        "emily_writes": emily_writes,
        "card": card,
        "matrix": service.matrix(),
        "bifrost": usage,
        "world_context": context,
    }


def run_beat_bifrost(
    service: WorldService | None = None,
    beat_id: str = "cafe",
    client=None,
) -> dict:
    """Run any authored beat through Bifrost; the café keeps its branch logic."""
    service = service or WorldService()
    if client is None:
        from gateway.bifrost import BifrostClient

        client = BifrostClient()
    canon = load_canon()
    beat = get_beat(beat_id, canon)

    if beat_id == "cafe":
        _ensure_secret(service)
        advance_to_beat(service, canon, beat["id"])
        result = run_cafe_bifrost(service, client=client)
        result["beat"] = beat
        result["transport"] = "bifrost"
        return result

    branch = None
    branch_id = None
    if beat_id == "aftermath":
        if service.latest_event("branch") is None:
            raise ValueError("run the café beat first; aftermath needs a branch")
        branch = branch_for(service, DEMO_KEY)
        branch_id = branch["id"]

    if beat_id in {"morning-shop", "roundup"}:
        _ensure_secret(service)
    advance_to_beat(service, canon, beat["id"])
    context = world_context(service)
    service.record_event(
        "director",
        "beat_start",
        f"Beat: {beat['id']} — {beat['title']}",
        participants=beat.get("characters", []),
        visibility="public",
    )

    prompts = prompts_for(beat, branch_id)
    turns = []
    transcript = []
    for character in beat.get("characters", []):
        if character in {"user", "director"}:
            continue
        prompt = prompts.get(character)
        if not prompt:
            continue
        messages = [
            {"role": "system", "content": _system(character, canon, context, clock=service.clock()["now"])},
            {"role": "user", "content": prompt},
        ]
        envelope = _parse_envelope(client.chat_json(character, messages), character)
        service.record_event(
            character,
            "dialogue",
            f"{character.title()}: {envelope['reply']}",
            [character],
            "public",
        )
        writes = _apply(service, character, envelope)
        turns.append({"character": character, "reply": envelope["reply"], "writes": writes})
        transcript.append(f"{character.title()}: {envelope['reply']}")

    _apply_effects(service, beat_id, branch_id)
    _record_beat(service, beat)
    issues = _canon_warning(service, canon)
    card = service.scene_card(f"{beat['title']} — {beat_id}")
    usage = client.usage_summary() if hasattr(client, "usage_summary") else {}
    return {
        "beat": beat,
        "transport": "bifrost",
        "branch": branch,
        "canon_issues": issues,
        "turns": turns,
        "transcript": transcript,
        "card": card,
        "matrix": service.matrix(),
        "bifrost": usage,
        "world_context": context,
    }
