"""Switch (Console) transport.

This is the port-shaped successor to ``director/switch_client.py``. It keeps
the same wire semantics -- the director is a Switch agent and the room is
discovered by name -- but fixes the transport defects found in the audit:

* the ``httpx.Client`` is injected, so tests never reach the network and the
  application owns connection pooling and shutdown;
* every call passes an explicit timeout instead of relying on library defaults;
* the cursor is captured **before** the first post, so a reply written in the
  same millisecond as the post is still part of the turn;
* history events are normalized from either ``id`` or ``event_id`` to a single
  ``InboundTurn.event_id`` (the old code read ``event["event_id"]`` from a
  history event that actually used ``id``).
"""
from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from switch_world.domain.ids import CharacterId, TurnId
from switch_world.domain.ports.transport import (
    Delivery,
    InboundTurn,
    Prompt,
    RoomHandle,
    TransportCapabilities,
    TransportError,
)

from ._support import dedupe, event_id_of, to_inbound


class SwitchTransport:
    """A :class:`CharacterTransport` over the Switch Console HTTP API."""

    name = "switch"

    def __init__(
        self,
        *,
        client: httpx.Client,
        agent_id: str,
        token: str,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 20.0,
        poll_interval: float = 1.0,
        clock: Any | None = None,
        own_client: bool = False,
    ) -> None:
        self._client = client
        self._agent_id = agent_id
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout)
        self._poll_interval = max(0.0, float(poll_interval))
        self._clock = clock
        self._own_client = own_client

    # ---- capabilities -----------------------------------------------------
    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format="text",
            write_mode="out_of_band",
            private_rooms=False,
            non_blocking_post=True,
            addressing=True,
            event_id_field="event_id",
        )

    # ---- rooms ------------------------------------------------------------
    def open_room(
        self, *, name: str, private_for: CharacterId | None = None
    ) -> RoomHandle:
        if private_for is not None:
            raise TransportError(
                "Switch transport has no private rooms; use a DM transport"
            )
        rooms = self._op("list_rooms")
        if isinstance(rooms, Mapping):
            rooms = rooms.get("result", rooms.get("rooms", []))
        if not isinstance(rooms, list):
            raise TransportError("Switch list_rooms returned an unexpected payload")
        for room in rooms:
            if isinstance(room, Mapping) and room.get("name") == name:
                return RoomHandle(
                    room_id=str(room.get("room_id") or room.get("id") or name),
                    name=name,
                )
        raise TransportError(f"Switch room not found: {name}")

    # ---- delivery ---------------------------------------------------------
    def deliver_many(
        self,
        room: RoomHandle,
        prompts: Sequence[Prompt],
        *,
        turn_id: TurnId,
    ) -> Delivery:
        # Capture the boundary first: the reply may share the post's timestamp.
        cursor = self._cursor(room.room_id)
        for prompt in prompts:
            self._post_message(room.room_id, prompt.text)
        return Delivery(room=room, turn_id=turn_id, cursor=cursor)

    def collect(
        self,
        delivery: Delivery,
        *,
        speakers: Sequence[CharacterId],
        deadline: float,
    ) -> list[InboundTurn]:
        wanted = {str(speaker) for speaker in speakers}
        seen = {str(turn.event_id) for turn in delivery.inline}
        collected: list[InboundTurn] = []

        while True:
            try:
                events = self._raw_history(delivery.room.room_id)
            except TransportError:
                events = []
            for index, event in enumerate(self._after_cursor(events, delivery.cursor)):
                turn = to_inbound(event, room=delivery.room.room_id, index=index)
                key = str(turn.event_id)
                if key in seen:
                    continue
                if str(turn.sender) not in wanted:
                    continue
                if not turn.text.strip():
                    continue
                seen.add(key)
                collected.append(turn)
            if self._all_seen(collected, wanted):
                break
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            time.sleep(min(self._poll_interval, remaining))
        return collected

    def history(self, room: RoomHandle) -> list[InboundTurn]:
        events = self._raw_history(room.room_id)
        turns = [
            to_inbound(event, room=room.room_id, index=index)
            for index, event in enumerate(events)
        ]
        return dedupe(turns)

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    # ---- HTTP -------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                timeout=httpx.Timeout(self._timeout),
            )
        except httpx.HTTPError as exc:
            raise TransportError(f"{method} {path} failed: {exc}") from exc
        if response.status_code != 200:
            raise TransportError(
                f"{method} {path}: {response.status_code} {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TransportError(f"{method} {path} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TransportError(f"{method} {path} returned a non-object body")
        return payload

    def _op(self, name: str, payload: Mapping[str, Any] | None = None) -> Any:
        body = self._request(
            "POST", f"/agents/{self._agent_id}/ops/{name}", json=payload or {}
        )
        return body.get("result", {})

    def _post_message(self, room_id: str, content: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/agents/{self._agent_id}/message",
            json={"room_id": room_id, "content": content},
        )

    def _raw_history(self, room_id: str) -> list[Mapping[str, Any]]:
        body = self._request(
            "GET", f"/agents/{self._agent_id}/rooms/{room_id}/history"
        )
        events = body.get("events", body.get("result", body))
        if isinstance(events, Mapping):
            events = events.get("events", [])
        if not isinstance(events, list):
            raise TransportError("Switch history returned an unexpected payload")
        return [event for event in events if isinstance(event, Mapping)]

    # ---- cursor -----------------------------------------------------------
    def _cursor(self, room_id: str) -> str:
        """The last event id (or timestamp) before this turn's posts."""
        events = self._raw_history(room_id)
        if not events:
            return ""
        last = events[-1]
        event_id = event_id_of(last)
        if event_id is not None:
            return f"id:{event_id}"
        timestamp = last.get("timestamp")
        if timestamp is not None:
            return f"ts:{timestamp}"
        return ""

    @staticmethod
    def _after_cursor(
        events: Sequence[Mapping[str, Any]], cursor: str
    ) -> list[Mapping[str, Any]]:
        if not cursor:
            return list(events)
        if cursor.startswith("id:"):
            wanted = cursor[len("id:") :]
            for index, event in enumerate(events):
                if event_id_of(event) == wanted:
                    return list(events[index + 1 :])
            # The cursor event fell out of the window: return the snapshot.
            return list(events)
        if cursor.startswith("ts:"):
            try:
                floor = float(cursor[len("ts:") :])
            except ValueError:
                return list(events)
            return [
                event
                for event in events
                if _number(event.get("timestamp")) > floor
            ]
        return list(events)

    @staticmethod
    def _all_seen(collected: Sequence[InboundTurn], wanted: set[str]) -> bool:
        if not wanted:
            return True
        return wanted <= {str(turn.sender) for turn in collected}

    def _monotonic(self) -> float:
        if self._clock is not None:
            return float(self._clock.monotonic())
        return time.monotonic()


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = ["SwitchTransport"]
