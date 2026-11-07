"""Normalization helpers shared by the transport adapters.

Switch returns ``id`` from history but ``event_id`` from a post, and the cloud
adapter invents its own ids. Every adapter funnels a wire event through
:func:`event_id_of` so the port exposes exactly one field, ``InboundTurn.event_id``.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Mapping

from switch_world.domain.ids import CharacterId, MessageId
from switch_world.domain.ports.transport import InboundTurn


def text_of(event: Mapping[str, Any]) -> str:
    """The message body under any of the wire names the providers use."""
    for key in ("body", "text", "content"):
        value = event.get(key)
        if value is not None:
            return str(value)
    return ""


def event_id_of(event: Mapping[str, Any]) -> str | None:
    """Accept ``id`` or ``event_id`` and return one normalized value.

    This is the fix for the audited split-brain id: history events carry
    ``id`` while post replies carry ``event_id``. Callers only ever see
    ``InboundTurn.event_id``.
    """
    for key in ("event_id", "id"):
        value = event.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def sender_of(event: Mapping[str, Any]) -> str:
    """The character name, stripped of a Switch agent prefix or ``@``."""
    value = (
        event.get("sender_name")
        or event.get("sender")
        or event.get("character")
        or ""
    )
    name = str(value).strip().lstrip("@")
    if name.startswith("switch-agent-"):
        name = name[len("switch-agent-") :]
    return name


def timestamp_of(event: Mapping[str, Any], *, fallback: datetime | None = None) -> datetime:
    """Read a millisecond timestamp, an ISO string, or fall back to now."""
    raw = event.get("timestamp") or event.get("received_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        seconds = raw / 1000.0 if abs(raw) > 100_000_000_000 else float(raw)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(raw, str) and raw.strip():
        try:
            return timestamp_of({"timestamp": int(raw.strip())}, fallback=fallback)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None:
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return fallback or datetime.now(timezone.utc)


def to_inbound(
    event: Mapping[str, Any],
    *,
    room: str,
    index: int,
    fallback: datetime | None = None,
) -> InboundTurn:
    """Turn one wire event into an :class:`InboundTurn`.

    A missing id gets a deterministic synthetic value scoped to the room and
    position so dedupe still works inside a snapshot.
    """
    event_id = event_id_of(event)
    if event_id is None:
        event_id = f"{room}:{index}"
    return InboundTurn(
        sender=CharacterId(sender_of(event)),
        text=text_of(event),
        event_id=MessageId(event_id),
        received_at=timestamp_of(event, fallback=fallback),
    )


def dedupe(turns: Iterable[InboundTurn]) -> list[InboundTurn]:
    """Keep the first occurrence of each event id, in input order."""
    seen: set[str] = set()
    unique: list[InboundTurn] = []
    for turn in turns:
        key = str(turn.event_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(turn)
    return unique


__all__ = [
    "dedupe",
    "event_id_of",
    "sender_of",
    "text_of",
    "timestamp_of",
    "to_inbound",
]
