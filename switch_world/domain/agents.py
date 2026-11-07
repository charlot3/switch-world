"""Agent replies and the writes a character may commit.

A transport may return a plain line, or -- when it is in band and the model
speaks JSON -- a full envelope with a belief and relationship deltas. The
application parses that envelope once into :class:`AgentReply` and applies the
writes with the speaking character as the actor, so an in-band model has
exactly the same authority as a character calling the MCP tools directly.

This module is stdlib-only and imports only other domain modules.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .ids import CharacterId
from .ports.model import ModelError, ModelReply, Usage


@dataclass(frozen=True)
class MemoryWrite:
    """A belief the character records about itself or the world."""

    proposition: str
    source: str = "observation"
    confidence: float = 0.6
    visibility: str = "private"
    proposition_key: str | None = None


@dataclass(frozen=True)
class RelationshipWrite:
    """A delta on the character's own outgoing relationship edge."""

    other: str
    trust_delta: float = 0.0
    closeness_delta: float = 0.0
    tension_delta: float = 0.0
    reason: str = ""


WorldWrite = MemoryWrite | RelationshipWrite


@dataclass(frozen=True)
class AgentReply:
    """One character's answer, with any writes carried alongside it."""

    character: CharacterId
    text: str
    writes: tuple[WorldWrite, ...] = ()
    usage: Usage = field(default_factory=Usage)
    source: str = "envelope"


def _first_text(data: Mapping[str, Any]) -> str:
    for key in ("reply", "text", "message", "content"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _memory_write(value: Any) -> MemoryWrite | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, Mapping):
        return None
    proposition = str(value.get("proposition") or "").strip()
    if not proposition:
        return None
    try:
        confidence = float(value.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    return MemoryWrite(
        proposition=proposition,
        source=str(value.get("source") or "observation"),
        confidence=confidence,
        visibility=str(value.get("visibility") or "private"),
        proposition_key=value.get("proposition_key"),
    )


def _relationship_writes(value: Any) -> list[RelationshipWrite]:
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, list):
        return []
    writes: list[RelationshipWrite] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        other = str(item.get("other") or "").strip()
        if not other:
            continue
        try:
            writes.append(
                RelationshipWrite(
                    other=other,
                    trust_delta=float(item.get("trust_delta", 0.0)),
                    closeness_delta=float(item.get("closeness_delta", 0.0)),
                    tension_delta=float(item.get("tension_delta", 0.0)),
                    reason=str(item.get("reason") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    return writes


def parse_agent_reply(
    character: str,
    reply: ModelReply,
    *,
    envelope: bool = True,
) -> AgentReply:
    """Turn a model reply into an :class:`AgentReply`.

    ``envelope`` is true when JSON was requested. A JSON reply must carry a
    non-empty ``reply`` field; an empty answer raises :class:`ModelError` so it
    cannot be mistaken for a recorded silence.
    """
    data = reply.data if isinstance(reply.data, Mapping) else None
    if envelope and data is None:
        # A provider may leave parsing to us when the envelope is the whole text.
        text = (reply.text or "").strip()
        if text.startswith("{"):
            import json

            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, Mapping):
                data = parsed

    if data is not None:
        text = _first_text(data)
        if not text:
            raise ModelError(f"{character} returned an empty reply")
        writes: list[WorldWrite] = []
        memory = _memory_write(data.get("memory"))
        if memory is not None:
            writes.append(memory)
        writes.extend(_relationship_writes(data.get("relationships")))
        return AgentReply(
            character=CharacterId(str(character)),
            text=text,
            writes=tuple(writes),
            usage=reply.usage,
            source="envelope",
        )

    text = (reply.text or "").strip()
    if not text:
        raise ModelError(f"{character} returned an empty reply")
    return AgentReply(
        character=CharacterId(str(character)),
        text=text,
        usage=reply.usage,
        source="text",
    )


__all__ = [
    "AgentReply",
    "MemoryWrite",
    "RelationshipWrite",
    "WorldWrite",
    "parse_agent_reply",
]
