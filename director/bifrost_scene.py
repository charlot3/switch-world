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

The lifecycle now lives in :mod:`switch_world.application.beats`; this module
keeps the historical public names and return shapes and supplies the prompt
and model half through :class:`BifrostBeatStrategy`.
"""
from __future__ import annotations

from pathlib import Path

from world_engine import config
from world_engine.service import WorldService

from switch_world.adapters.clock import SystemClock
from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.application.beat_strategies import BifrostBeatStrategy
from switch_world.application.beats import (
    _ensure_secret as _pipeline_ensure_secret,
    get_beat,
    load_spec,
    prompts_for,
    run_beat as _pipeline_run_beat,
)

from . import DEMO_KEY, DEMO_SECRET
from .canon import (  # noqa: F401  (branch_for/record_branch/validate re-exports)
    brief,
    branch_for,
    load as load_canon,
    record_branch,
    validate,
)
from .clock import advance_to_beat
from .social import appraise, clean_scene_line  # noqa: F401  (re-exports)
from .simulate import user_tells_alice  # noqa: F401  (re-export)
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
    path = Path(config.AGENTS_DIR) / character / "IDENTITY.md"
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


def _group_writes(items) -> dict:
    """The historical ``_apply`` shape from the pipeline's applied-write list."""
    memory = None
    relationships: list[dict] = []
    for item in items or ():
        if isinstance(item, dict) and "memory" in item:
            memory = item["memory"]
        elif isinstance(item, dict):
            relationships.append(item)
    return {"memory": memory, "relationships": relationships}


def _usage(client) -> dict:
    summary = getattr(client, "usage_summary", None)
    return summary() if callable(summary) else {}


def _run_cafe_bifrost(
    service: WorldService,
    client,
    *,
    seed: bool,
    advance: bool,
) -> dict:
    known = service.who_knows(DEMO_KEY)["holders"]
    alice_knows = any(
        holder["holder"] == "alice" and holder["source"] == "user"
        for holder in known
    )
    if not alice_knows and not seed:
        raise ValueError("Alice does not know the secret; seed it first")

    context = world_context(service)
    result = _pipeline_run_beat(
        load_spec(
            "cafe",
            transport="bifrost",
            seed=seed,
            advance=advance,
        ),
        BifrostBeatStrategy(
            LegacyModelClient(client),
            prompts=prompts_for,
        ),
        service,
        SystemClock(),
    )

    turns = {turn["character"]: turn for turn in result["turns"]}
    usage = _usage(client)
    if "alice" not in turns:
        return {
            "shared": None,
            "branch": None,
            "canon_issues": [],
            "alice": None,
            "emily": None,
            "alice_writes": None,
            "emily_writes": None,
            "card": result["card"],
            "matrix": result["matrix"],
            "bifrost": usage,
            "world_context": context,
        }

    alice = turns["alice"]["reply"]
    emily_turn = turns.get("emily")
    return {
        "shared": (result["branch"] or {}).get("id") == "disclosure",
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "alice": alice,
        "emily": emily_turn["reply"] if emily_turn else "",
        "alice_writes": _group_writes(turns["alice"]["writes"]),
        "emily_writes": (
            _group_writes(emily_turn["writes"])
            if emily_turn
            else {"memory": None, "relationships": []}
        ),
        "card": result["card"],
        "matrix": result["matrix"],
        "bifrost": usage,
        "world_context": context,
    }


def run_cafe_bifrost(
    service: WorldService | None = None,
    client=None,
    seed: bool = True,
) -> dict:
    """Run the café beat with both character turns generated through Bifrost.

    The caller owns the clock: like the historical function, this does not move
    the world to 18:30.  ``director.beats`` and ``run_beat_bifrost`` do that
    before calling in.
    """
    service = service or WorldService()
    if client is None:
        from gateway.bifrost import BifrostClient

        client = BifrostClient()
    return _run_cafe_bifrost(service, client, seed=seed, advance=False)


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
        _pipeline_ensure_secret(service, DEMO_KEY)
        advance_to_beat(service, canon, beat["id"])
        result = run_cafe_bifrost(service, client=client)
        result["beat"] = beat
        result["transport"] = "bifrost"
        return result

    context = world_context(service)
    result = _pipeline_run_beat(
        load_spec(beat_id, transport="bifrost"),
        BifrostBeatStrategy(
            LegacyModelClient(client),
            prompts=prompts_for,
        ),
        service,
        SystemClock(),
    )
    turns = [
        {
            "character": turn["character"],
            "reply": turn["reply"],
            "writes": _group_writes(turn["writes"]),
        }
        for turn in result["turns"]
    ]
    return {
        "beat": result["beat"],
        "transport": result["transport"],
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "turns": turns,
        "transcript": result["transcript"],
        "card": result["card"],
        "matrix": result["matrix"],
        "bifrost": _usage(client),
        "world_context": context,
    }


__all__ = [
    "DEMO_SECRET",
    "LANGUAGE_AND_VOICE",
    "SCHEMA",
    "TONE",
    "_apply",
    "_identity",
    "_parse_envelope",
    "_system",
    "appraise",
    "branch_for",
    "clean_scene_line",
    "load_canon",
    "record_branch",
    "run_beat_bifrost",
    "run_cafe_bifrost",
    "user_tells_alice",
    "validate",
]
