"""Prompt construction and envelope parsing shared by every model-backed path.

These are the authored system prompt, the JSON envelope contract and the
write-application half head-authored for the Bifrost café beat. They are used
by the scene use cases (DM, whisper, observers) and by both model beat
strategies, so they live in one place instead of inside a legacy runner.
"""
from __future__ import annotations

import os
from pathlib import Path

from switch_world.application.canon import brief
from switch_world.application.facade import WorldService
from switch_world.config import load_settings


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
    "Voice: sound like a person texting, not a narrator performing a scene. In a DM use "
    "1-2 sentences and at most one concrete detail; no inventory of sounds, objects or "
    "stage business, no 'I'm listening', no 'say the thing', no theatrical pause. Answer "
    "the actual message instead of writing a novelist's version of it. Plain is better "
    "than clever. Do not end with a command ('say it', 'tell me') or a rhetorical "
    "question; ask one plain question or make one plain statement. If you mention the "
    "setting, it must change what you say, not decorate it. In a serious or vulnerable "
    "exchange, drop the prop and the joke; answer the feeling first. At most one prop "
    "detail in a lighter reply. Example register: 'You're late. I saved you the crispy "
    "bits.' Not: 'The fryer hums and the window is empty, so say the thing.' Subtext is "
    "fine; a neat emotional summary is not. Use short "
    "sentences and at most one dash; do not write a mini-essay. Avoid therapy-speak, "
    "customer-support tone, bullet points, a question at the end of every reply, and "
    "meta prefaces such as '认真答' or '说实话' — just answer. No stage directions, no "
    "third-person narration."
)

TONE = (
    "All characters are adults. The tone is 17+ romantic tension, SFW: teasing, "
    "glances and unfinished sentences are allowed; explicit content, minors and "
    "coercion are not. Never mention being an AI, a model, a simulation, or these rules. "
    "Never write '@user', '@director', or any line about being online, offline, or "
    "needing to leave; you are present in this conversation and answer as yourself."
)


def _identity(character: str, limit: int = 3200) -> str:
    path = Path(load_settings(os.environ).agents_dir) / character / "IDENTITY.md"
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


