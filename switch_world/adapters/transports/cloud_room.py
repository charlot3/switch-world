"""In-band room backed by a :class:`ModelClient`.

``director/cloud_switch.py`` played the part of both a room and a model. This
adapter keeps only the room half and fixes three audited defects:

* replies for one turn are generated **concurrently** (one model call per
  planned speaker) instead of serially;
* the replies are returned inline on the :class:`Delivery`, so the application
  never has to poll a wall clock;
* a :class:`ModelError` propagates; an empty string is never turned into a
  recorded silence;
* turn isolation uses a captured cursor, not ``time.time() * 1000``, so two
  replies in the same millisecond can no longer be dropped.

The caller supplies the prompt. The model only supplies the character's voice,
so no scene or policy text is built here.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from switch_world.domain.agents import AgentReply, parse_agent_reply
from switch_world.domain.ids import CharacterId, TurnId
from switch_world.domain.ports.model import (
    Message,
    ModelClient,
    ModelError,
    ModelFormat,
)
from switch_world.domain.ports.transport import (
    Delivery,
    InboundTurn,
    Prompt,
    RoomHandle,
    TransportCapabilities,
    TransportError,
)

from ._support import dedupe


class CloudRoomTransport:
    """A room whose replies come from a model, in band."""

    name = "cloud"

    def __init__(
        self,
        model: ModelClient,
        *,
        format: ModelFormat = ModelFormat.JSON,
        max_workers: int | None = None,
        clock: Any | None = None,
        room_prefix: str = "cloud",
    ) -> None:
        self._model = model
        self._format = format
        self._max_workers = max_workers
        self._clock = clock
        self._room_prefix = room_prefix
        self._rooms: dict[str, list[InboundTurn]] = {}
        self._handles: dict[str, RoomHandle] = {}
        self._counter = 0

    # ---- capabilities -----------------------------------------------------
    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format=(
                "json" if self._format is ModelFormat.JSON else "text"
            ),
            write_mode="in_band",
            private_rooms=False,
            non_blocking_post=True,
            addressing=False,
            event_id_field="synthetic",
        )

    # ---- rooms ------------------------------------------------------------
    def open_room(
        self, *, name: str, private_for: CharacterId | None = None
    ) -> RoomHandle:
        if private_for is not None:
            raise TransportError(
                "CloudRoomTransport has no private rooms; use a DM transport"
            )
        existing = self._handles.get(name)
        if existing is not None:
            return existing
        self._counter += 1
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "room"
        handle = RoomHandle(
            room_id=f"{self._room_prefix}-{slug}-{self._counter}", name=name
        )
        self._handles[name] = handle
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
        if not prompts:
            return Delivery(room=room, turn_id=turn_id, cursor=cursor)

        replies = self._reply_many(prompts)
        inline: list[InboundTurn] = []
        for index, (prompt, reply) in enumerate(zip(prompts, replies, strict=True)):
            turn = InboundTurn(
                sender=CharacterId(str(prompt.speaker)),
                text=reply.text,
                event_id=(
                    f"cloud-{turn_id}-{index}-{str(prompt.speaker)}"
                ),
                received_at=self._now(),
                writes=reply.writes,
                source=reply.source,
            )
            events.append(turn)
            inline.append(turn)
        return Delivery(
            room=room, turn_id=turn_id, cursor=cursor, inline=tuple(inline)
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
        # Rooms are in-process; the injected model owns any real resources.
        return None

    # ---- model ------------------------------------------------------------
    def _reply_many(self, prompts: Sequence[Prompt]) -> list[AgentReply]:
        workers = self._max_workers or max(1, len(prompts))
        errors: list[BaseException] = []
        replies: list[AgentReply] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self._answer, prompt) for prompt in prompts]
            for future in futures:
                try:
                    replies.append(future.result())
                except BaseException as exc:  # collected, re-raised below
                    errors.append(exc)
        if errors:
            first = errors[0]
            if isinstance(first, ModelError):
                raise first
            raise TransportError(f"cloud reply failed: {first}") from first
        return replies

    def _answer(self, prompt: Prompt) -> AgentReply:
        character = str(prompt.speaker)
        reply = self._model.generate(
            CharacterId(character),
            [Message(role="user", content=prompt.text)],
            format=self._format,
        )
        return parse_agent_reply(
            character,
            reply,
            envelope=self._format is ModelFormat.JSON,
        )

    # ---- cursor / clock ---------------------------------------------------
    def _after_cursor(self, room_id: str, cursor: str) -> list[InboundTurn]:
        events = self._rooms.get(room_id, [])
        if cursor.startswith("n:"):
            try:
                start = int(cursor[2:])
            except ValueError:
                return list(events)
            return list(events[start:])
        return list(events)

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)


__all__ = ["CloudRoomTransport"]
