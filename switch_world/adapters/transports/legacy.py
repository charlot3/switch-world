"""Compatibility transport over the deleted v1 ``director.switch_client.SwitchClient``.

The v2 application talks to :class:`CharacterTransport`. Older callers (and the
compatibility shim in ``switch_world.compat``) still pass a Switch-shaped object
with ``find_room`` / ``post`` / ``history``. This adapter narrows that surface
without letting the application depend on the legacy class, and normalizes the
wire event id through the same helper as :class:`SwitchTransport` so an event
that carries ``id`` instead of ``event_id`` is no longer a split-brain.

It is a compatibility bridge only: production code uses ``SwitchTransport``.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
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

from switch_world.adapters.transports.switch_client import SwitchError

from ._support import dedupe, to_inbound


class LegacySwitchTransport:
    """A :class:`CharacterTransport` over the old Switch client interface."""

    name = "switch-legacy"

    def __init__(
        self,
        client: Any | None = None,
        *,
        client_factory: Any | None = None,
        time_source: Any | None = None,
    ) -> None:
        if client is None and client_factory is None:
            raise ValueError("client or client_factory is required")
        self._client = client
        self._client_factory = client_factory
        self._time = time_source or time

    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format="text",
            write_mode="out_of_band",
            private_rooms=self._has_private_rooms(),
            non_blocking_post=True,
            addressing=True,
            event_id_field="event_id",
        )

    def _has_private_rooms(self) -> bool:
        """The legacy Switch client exposed private rooms through ``find_private_room``.

        The probe lives in the adapter boundary, not the application: a
        factory-backed transport cannot know before construction and reports
        ``False`` (the group path never asks for a private room).
        """
        if self._client is None:
            return False
        return callable(getattr(self._client, "find_private_room", None))

    def open_room(
        self, *, name: str, private_for: CharacterId | None = None
    ) -> RoomHandle:
        if private_for is not None:
            finder = getattr(self._backend(), "find_private_room", None)
            if not callable(finder):
                raise TransportError(
                    "Switch transport has no private rooms; use a DM transport"
                )
            try:
                room = finder(str(private_for))
            except Exception as exc:  # a failed lookup is simply "no private room"
                raise TransportError(str(exc)) from exc
            if not isinstance(room, dict) or not room.get("room_id"):
                raise TransportError(f"no private room for {private_for}")
            return RoomHandle(
                room_id=str(room["room_id"]),
                name=name,
                private_for=private_for,
            )
        room = self._backend().find_room(name)
        room_id = str(room.get("room_id") or room.get("id") or name)
        return RoomHandle(room_id=room_id, name=name)

    def deliver_many(
        self,
        room: RoomHandle,
        prompts: Sequence[Prompt],
        *,
        turn_id: TurnId,
        deadline: float | None = None,
    ) -> Delivery:
        if room.private_for is not None:
            # HEAD read ``history`` twice to find the start marker; read it once
            # and carry it as the delivery cursor for ``collect``.
            started = self._private_started(room.room_id)
            try:
                for prompt in prompts:
                    if deadline is not None and self._monotonic() >= deadline:
                        break
                    self._backend().post(room.room_id, prompt.text)
            except SwitchError as exc:
                raise TransportError(str(exc)) from exc
            return Delivery(room=room, turn_id=turn_id, cursor=f"ts:{started}")

        # Same turn boundary the old code used: events older than half a second
        # before the first post belong to a previous turn.
        cutoff = int(self._time.time() * 1000) - 500
        try:
            for prompt in prompts:
                if deadline is not None and self._monotonic() >= deadline:
                    break
                self._backend().post(room.room_id, prompt.text)
        except SwitchError as exc:
            # The port owns failures: the application catches TransportError
            # and its message stays the historical one.
            raise TransportError(str(exc)) from exc
        return Delivery(room=room, turn_id=turn_id, cursor=f"ms:{cutoff}")

    def collect(
        self,
        delivery: Delivery,
        *,
        speakers: Sequence[CharacterId],
        deadline: float,
    ) -> list[InboundTurn]:
        if delivery.room.private_for is not None:
            return self._collect_private(delivery, deadline=deadline)
        wanted = {str(speaker) for speaker in speakers}
        if not wanted:
            return []
        cutoff = self._cutoff(delivery.cursor)
        seen: set[str] = set()
        collected: list[InboundTurn] = []
        # The deadline gates polling itself, as in HEAD: once the turn is over
        # this poll must not answer with events that arrived after the cap.
        while self._monotonic() < deadline:
            try:
                events = self._backend().history(delivery.room.room_id)
            except Exception:
                # A transient history failure is a missed poll, exactly as before.
                events = []
            for index, event in enumerate(events or []):
                if not isinstance(event, dict):
                    continue
                if str(event.get("sender_name") or "").strip() not in wanted:
                    continue
                try:
                    stamp = int(event.get("timestamp") or 0)
                except (TypeError, ValueError):
                    stamp = 0
                if stamp <= cutoff:
                    continue
                turn = to_inbound(event, room=delivery.room.room_id, index=index)
                key = str(turn.event_id)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(turn)
            if wanted <= {str(turn.sender) for turn in collected}:
                break
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            interval = 0.5 if str(delivery.turn_id).endswith("-relay") else 1.0
            self._time.sleep(min(interval, remaining))
        return dedupe(collected)

    def history(self, room: RoomHandle) -> list[InboundTurn]:
        try:
            events = self._backend().history(room.room_id)
        except Exception:
            events = []
        turns = [
            to_inbound(event, room=room.room_id, index=index)
            for index, event in enumerate(events or [])
            if isinstance(event, dict)
        ]
        return dedupe(turns)

    # ---- private rooms ---------------------------------------------------
    def _private_started(self, room_id: str) -> Any:
        """The last event timestamp before the whisper, from one history read."""
        try:
            events = self._backend().history(room_id) or []
        except Exception:
            events = []
        if not events:
            return 0
        last = events[-1]
        return last.get("timestamp", 0) if isinstance(last, dict) else 0

    def _collect_private(
        self, delivery: Delivery, *, deadline: float
    ) -> list[InboundTurn]:
        wait = getattr(self._backend(), "wait_for", None)
        if not callable(wait):
            return []
        started = self._cursor_ts(delivery.cursor)
        if deadline is None:
            timeout = 0.0
        else:
            timeout = max(0.0, float(deadline) - self._monotonic())
        try:
            event = wait(
                delivery.room.room_id,
                str(delivery.room.private_for),
                started,
                timeout=timeout,
            )
        except Exception:
            return []
        if not isinstance(event, dict):
            return []
        return [to_inbound(event, room=delivery.room.room_id, index=0)]

    @staticmethod
    def _cursor_ts(cursor: str) -> Any:
        if cursor.startswith("ts:"):
            raw = cursor[3:]
            try:
                return int(raw)
            except ValueError:
                return raw
        return 0

    def close(self) -> None:
        return None

    # ---- helpers ----------------------------------------------------------
    def _backend(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    @staticmethod
    def _cutoff(cursor: str) -> int:
        if cursor.startswith("ms:"):
            try:
                return int(cursor[3:])
            except ValueError:
                return 0
        return 0

    def _monotonic(self) -> float:
        monotonic = getattr(self._time, "monotonic", None)
        if callable(monotonic):
            return float(monotonic())
        return float(self._time.time())


def deferred_transport(mode: str) -> LegacySwitchTransport:
    """Build the historical transport for a caller with no composition root.

    The client is resolved on first use, so a monkeypatched
    ``switch_world.compat.SwitchClient`` still drives older tests.  This is the
    one compatibility bridge; production code injects a real transport.
    """
    if str(mode).strip().lower() == "cloud":

        def client_factory():
            from switch_world.adapters.transports.cloud_switch import CloudSwitch

            return CloudSwitch()

    else:

        def client_factory():
            # Imported at call time so a caller can still patch
            # ``switch_world.compat.SwitchClient`` (the legacy test seam).
            from switch_world.compat import SwitchClient

            return SwitchClient()

    return LegacySwitchTransport(client_factory=client_factory)


__all__ = ["LegacySwitchTransport", "deferred_transport"]
