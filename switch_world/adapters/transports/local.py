"""In-process scripted transport for tests and the local demo.

It is deliberately tiny: no HTTP, no model, no clock race. A script maps a
character to one or more replies, and each reply becomes an inbound turn with
a synthetic event id. Because the transport is in band, the replies are on the
:class:`Delivery` and :meth:`collect` has nothing left to poll.

Private rooms are supported (one room per ``(name, private_for)`` pair), which
makes this the double used to test the whisper capability branch.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from switch_world.domain.ids import CharacterId, TurnId
from switch_world.domain.ports.transport import (
    Delivery,
    InboundTurn,
    Prompt,
    RoomHandle,
    TransportCapabilities,
    TransportError,
)

from ._support import dedupe


@dataclass(frozen=True)
class LocalReply:
    """One scripted reply, optionally with a fixed event id."""

    text: str
    event_id: str | None = None


class LocalRoomTransport:
    """A scripted, in-process room."""

    name = "local"

    def __init__(
        self,
        script: Mapping[str, Any] | None = None,
        *,
        default_reply: str = "scripted reply",
        clock: Any | None = None,
    ) -> None:
        self._script: dict[str, list[Any]] = {
            str(character): (
                list(value) if isinstance(value, (list, tuple)) else [value]
            )
            for character, value in (script or {}).items()
        }
        self._indices: dict[str, int] = {}
        self._default_reply = default_reply
        self._clock = clock
        self._rooms: dict[str, list[InboundTurn]] = {}
        self._handles: dict[tuple[str, str | None], RoomHandle] = {}
        self._counter = 0

    # ---- capabilities -----------------------------------------------------
    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format="text",
            write_mode="in_band",
            private_rooms=True,
            non_blocking_post=True,
            addressing=True,
            event_id_field="synthetic",
        )

    # ---- rooms ------------------------------------------------------------
    def open_room(
        self, *, name: str, private_for: CharacterId | None = None
    ) -> RoomHandle:
        key = (name, None if private_for is None else str(private_for))
        existing = self._handles.get(key)
        if existing is not None:
            return existing
        self._counter += 1
        handle = RoomHandle(
            room_id=f"local-{self._counter}",
            name=name,
            private_for=None if private_for is None else CharacterId(str(private_for)),
        )
        self._handles[key] = handle
        self._rooms.setdefault(handle.room_id, [])
        return handle

    # ---- delivery ---------------------------------------------------------
    def deliver_many(
        self,
        room: RoomHandle,
        prompts: Sequence[Prompt],
        *,
        turn_id: TurnId,
        deadline: float | None = None,
    ) -> Delivery:
        events = self._rooms.setdefault(room.room_id, [])
        cursor = f"n:{len(events)}"
        pending: list[InboundTurn] = []
        for index, prompt in enumerate(prompts):
            text, event_id = self._next_reply(
                str(prompt.speaker),
                default_id=f"local-{turn_id}-{index}-{str(prompt.speaker)}",
            )
            pending.append(
                InboundTurn(
                    sender=CharacterId(str(prompt.speaker)),
                    text=text,
                    event_id=event_id,
                    received_at=self._now(),
                )
            )
        events.extend(pending)
        return Delivery(
            room=room,
            turn_id=turn_id,
            cursor=cursor,
            inline=tuple(pending),
        )

    def collect(
        self,
        delivery: Delivery,
        *,
        speakers: Sequence[CharacterId],
        deadline: float,
    ) -> list[InboundTurn]:
        wanted = {str(speaker) for speaker in speakers}
        seen = {str(turn.event_id) for turn in delivery.inline}
        events = self._after_cursor(delivery.room.room_id, delivery.cursor)
        collected = [
            turn
            for turn in events
            if str(turn.sender) in wanted
            and str(turn.event_id) not in seen
            and turn.text.strip()
        ]
        return dedupe(collected)

    def history(self, room: RoomHandle) -> list[InboundTurn]:
        return dedupe(self._rooms.get(room.room_id, []))

    def close(self) -> None:
        return None

    # ---- script -----------------------------------------------------------
    def _next_reply(self, character: str, *, default_id: str) -> tuple[str, Any]:
        entries = self._script.get(character)
        if not entries:
            return self._default_reply, default_id
        index = self._indices.get(character, 0)
        self._indices[character] = index + 1
        entry = entries[min(index, len(entries) - 1)]

        if isinstance(entry, BaseException):
            raise entry
        if isinstance(entry, LocalReply):
            text, event_id = entry.text, entry.event_id or default_id
        elif isinstance(entry, Mapping):
            text = str(entry.get("text") or entry.get("reply") or "")
            event_id = str(entry.get("event_id") or default_id)
        else:
            text, event_id = str(entry), default_id
        if not text.strip():
            raise TransportError(f"{character} scripted an empty reply")
        return text.strip(), event_id

    def _after_cursor(self, room_id: str, cursor: str) -> list[InboundTurn]:
        events = self._rooms.get(room_id, [])
        if cursor.startswith("n:"):
            try:
                return list(events[int(cursor[2:]) :])
            except ValueError:
                return list(events)
        return list(events)

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)


__all__ = ["LocalReply", "LocalRoomTransport"]
