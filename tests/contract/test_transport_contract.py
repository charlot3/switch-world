"""Contract for every character transport.

The same suite runs over Switch (respx), CloudRoom (ScriptedModel) and Local
(scripted in-process). It pins the properties the old adapters got wrong:

* ``deliver_many`` returns a cursor captured before the first post;
* history is isolated per turn even when every event has the same timestamp;
* ``id`` and ``event_id`` normalize to one ``InboundTurn.event_id``;
* a duplicate event id appears once;
* the capability record describes the transport truthfully;
* private rooms are either supported or explicitly refused.

Provider-specific tests below pin the Switch cursor order, the concurrent
CloudRoom generation and ModelError propagation.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from switch_world.adapters.models import ScriptedModelClient, ScriptedTurn
from switch_world.adapters.transports import (
    CloudRoomTransport,
    LocalRoomTransport,
    SwitchTransport,
)
from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    ModelError,
    ModelFormat,
    ModelReply,
    UsageSummary,
)
from switch_world.domain.ports.transport import (
    Prompt,
    TransportCapabilities,
    TransportError,
)

SWITCH_BASE = "https://switch.test"
FIXED_TIMESTAMP = 1_790_000_000_000


# ---- fakes -----------------------------------------------------------------


class FakeSwitchAPI:
    """A tiny Switch API with an intentionally constant event timestamp.

    A millisecond cutoff would collapse every turn; an id cursor cannot.
    Event ids are derived from the posted content, so replaying the same turn
    produces duplicate ids for the dedupe test.
    """

    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, Any]]] = {"room-world": []}
        self.calls: list[tuple[str, str]] = []
        self.posts: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))

        if path == "/agents/director/ops/list_rooms":
            return httpx.Response(
                200,
                json={"result": [{"room_id": "room-world", "name": "world"}]},
            )

        if path == "/agents/director/message":
            payload = json.loads(request.content)
            self.posts.append(payload)
            room = payload["room_id"]
            content = payload["content"]
            match = re.match(r"@([A-Za-z0-9_]+)", content)
            speaker = match.group(1) if match else "director"
            event_id = "evt-" + hashlib.sha1(content.encode()).hexdigest()[:10]
            event: dict[str, Any] = {
                "sender_name": speaker,
                "body": f"{speaker} replies",
                "timestamp": FIXED_TIMESTAMP,
            }
            # Alternate the two wire shapes so normalization is exercised.
            if len(self.events[room]) % 2 == 0:
                event["id"] = event_id
            else:
                event["event_id"] = event_id
            self.events[room].append(event)
            return httpx.Response(200, json={"event_id": event_id})

        match = re.match(r"/agents/director/rooms/([^/]+)/history", path)
        if match:
            return httpx.Response(
                200, json={"events": self.events[match.group(1)]}
            )

        return httpx.Response(404, json={"error": path})


@dataclass
class Harness:
    kind: str
    transport: Any
    api: FakeSwitchAPI | None = None


@pytest.fixture(params=["switch", "cloud", "local"])
def harness(request, tmp_path: Path):
    kind = request.param
    if kind == "switch":
        api = FakeSwitchAPI()
        with respx.mock(assert_all_called=False) as router:
            router.route(host="switch.test").mock(side_effect=api)
            client = httpx.Client()
            transport = SwitchTransport(
                client=client,
                base_url=SWITCH_BASE,
                agent_id="director",
                token="test-token",
                timeout=2.0,
                poll_interval=0.01,
            )
            try:
                yield Harness(kind, transport, api)
            finally:
                transport.close()
                client.close()
        return

    if kind == "cloud":
        model = ScriptedModelClient(
            {
                "alice": [{"reply": "Alice here."}],
                "emily": [{"reply": "Emily here."}],
            }
        )
        yield Harness(kind, CloudRoomTransport(model))
        return

    transport = LocalRoomTransport(
        {"alice": ["Alice here."], "emily": ["Emily here."]}
    )
    yield Harness(kind, transport)


class FrozenClock:
    """A clock that never advances, to expose any millisecond cutoff."""

    def __init__(self) -> None:
        self._now = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return 0.0


# ---- helpers ---------------------------------------------------------------


def _replies(harness: Harness, delivery, speakers: list[str]):
    inline = list(delivery.inline)
    if inline:
        return inline
    return harness.transport.collect(
        delivery,
        speakers=[CharacterId(speaker) for speaker in speakers],
        deadline=time.monotonic() + 2.0,
    )


def _default_prompts() -> list[Prompt]:
    return [
        Prompt(speaker=CharacterId("alice"), text="@alice hello"),
        Prompt(speaker=CharacterId("emily"), text="@emily hello"),
    ]


# ---- contract --------------------------------------------------------------


def test_deliver_many_returns_a_turn_scoped_delivery(harness):
    room = harness.transport.open_room(name="world")
    delivery = harness.transport.deliver_many(
        room, _default_prompts(), turn_id="turn-1"
    )

    assert delivery.room == room
    assert str(delivery.turn_id) == "turn-1"
    assert isinstance(delivery.cursor, str)
    replies = _replies(harness, delivery, ["alice", "emily"])
    assert {str(turn.sender) for turn in replies} == {"alice", "emily"}
    assert all(turn.text.strip() for turn in replies)

    if harness.kind == "switch":
        assert delivery.inline == ()
    else:
        assert len(delivery.inline) == 2


def test_history_is_isolated_per_turn_even_with_one_timestamp(harness):
    room = harness.transport.open_room(name="world")

    first = harness.transport.deliver_many(
        room,
        [Prompt(speaker=CharacterId("alice"), text="@alice first")],
        turn_id="turn-1",
    )
    first_replies = _replies(harness, first, ["alice"])

    second = harness.transport.deliver_many(
        room,
        [Prompt(speaker=CharacterId("emily"), text="@emily second")],
        turn_id="turn-2",
    )
    second_replies = _replies(harness, second, ["emily"])

    first_ids = {str(turn.event_id) for turn in first_replies}
    second_ids = {str(turn.event_id) for turn in second_replies}
    assert first_ids and second_ids
    assert first_ids.isdisjoint(second_ids)
    assert {str(turn.sender) for turn in first_replies} == {"alice"}
    assert {str(turn.sender) for turn in second_replies} == {"emily"}

    history = harness.transport.history(room)
    history_ids = {str(turn.event_id) for turn in history}
    assert first_ids <= history_ids
    assert second_ids <= history_ids

    if harness.kind == "switch":
        # The cursor is the event id, not the timestamp.
        assert second.cursor.startswith("id:")
        assert {turn.received_at for turn in history} == {
            datetime.fromtimestamp(FIXED_TIMESTAMP / 1000, tz=timezone.utc)
        }


def test_event_id_is_normalised_to_one_field(harness):
    room = harness.transport.open_room(name="world")
    harness.transport.deliver_many(
        room,
        [
            Prompt(speaker=CharacterId("alice"), text="@alice one"),
            Prompt(speaker=CharacterId("emily"), text="@emily two"),
        ],
        turn_id="turn-1",
    )

    history = harness.transport.history(room)
    assert history
    assert all(str(turn.event_id).strip() for turn in history)
    assert all(not hasattr(turn, "id") for turn in history)

    if harness.kind == "switch":
        raw = harness.api.events["room-world"]
        shapes = {"id" if "id" in event else "event_id" for event in raw}
        assert shapes == {"id", "event_id"}
        for wire, turn in zip(raw, history, strict=True):
            expected = wire.get("id") or wire.get("event_id")
            assert str(turn.event_id) == str(expected)


def test_duplicate_event_ids_are_suppressed(harness):
    room = harness.transport.open_room(name="world")
    prompts = [
        Prompt(speaker=CharacterId("alice"), text="@alice same"),
        Prompt(speaker=CharacterId("emily"), text="@emily same"),
    ]

    first = harness.transport.deliver_many(room, prompts, turn_id="duplicate-turn")
    _replies(harness, first, ["alice", "emily"])
    second = harness.transport.deliver_many(room, prompts, turn_id="duplicate-turn")
    _replies(harness, second, ["alice", "emily"])

    history = harness.transport.history(room)
    ids = [str(turn.event_id) for turn in history]
    assert len(ids) == len(set(ids)) == 2

    collected = harness.transport.collect(
        second,
        speakers=[CharacterId("alice"), CharacterId("emily")],
        deadline=time.monotonic() + 1.0,
    )
    collected_ids = [str(turn.event_id) for turn in collected]
    assert len(collected_ids) == len(set(collected_ids))


def test_capability_flags_describe_the_transport(harness):
    expected = {
        "switch": TransportCapabilities(
            response_format="text",
            write_mode="out_of_band",
            private_rooms=False,
            non_blocking_post=True,
            addressing=True,
            event_id_field="event_id",
        ),
        "cloud": TransportCapabilities(
            response_format="json",
            write_mode="in_band",
            private_rooms=False,
            non_blocking_post=True,
            addressing=False,
            event_id_field="synthetic",
        ),
        "local": TransportCapabilities(
            response_format="text",
            write_mode="in_band",
            private_rooms=True,
            non_blocking_post=True,
            addressing=True,
            event_id_field="synthetic",
        ),
    }
    assert harness.transport.capabilities() == expected[harness.kind]
    assert harness.transport.name == harness.kind


def test_private_rooms_are_supported_or_explicitly_refused(harness):
    public = harness.transport.open_room(name="world")
    harness.transport.deliver_many(
        public,
        [Prompt(speaker=CharacterId("alice"), text="@alice public")],
        turn_id="turn-public",
    )

    if not harness.transport.capabilities().private_rooms:
        with pytest.raises(TransportError):
            harness.transport.open_room(
                name="dm-alice", private_for=CharacterId("alice")
            )
        return

    private = harness.transport.open_room(
        name="dm-alice", private_for=CharacterId("alice")
    )
    assert private.private_for == "alice"
    assert private.room_id != public.room_id
    assert harness.transport.history(private) == []

    delivery = harness.transport.deliver_many(
        private,
        [Prompt(speaker=CharacterId("alice"), text="a secret")],
        turn_id="turn-private",
    )
    private_replies = _replies(harness, delivery, ["alice"])
    assert {str(turn.text) for turn in private_replies} == {"Alice here."}

    public_ids = {str(turn.event_id) for turn in harness.transport.history(public)}
    private_ids = {
        str(turn.event_id) for turn in harness.transport.history(private)
    }
    assert private_ids
    assert public_ids.isdisjoint(private_ids)


# ---- provider-specific guarantees -----------------------------------------


def test_switch_captures_the_cursor_before_posting():
    api = FakeSwitchAPI()
    with respx.mock(assert_all_called=False) as router:
        router.route(host="switch.test").mock(side_effect=api)
        client = httpx.Client()
        transport = SwitchTransport(
            client=client,
            base_url=SWITCH_BASE,
            agent_id="director",
            token="test-token",
            timeout=1.0,
        )
        room = transport.open_room(name="world")
        start = len(api.calls)

        transport.deliver_many(
            room,
            [Prompt(speaker=CharacterId("alice"), text="@alice hi")],
            turn_id="turn-1",
        )

        turn_calls = api.calls[start:]
        assert turn_calls[0] == (
            "GET",
            "/agents/director/rooms/room-world/history",
        )
        assert all(method == "POST" for method, _path in turn_calls[1:])
        client.close()


def test_switch_non_200_is_a_transport_error():
    api = FakeSwitchAPI()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/agents/director/ops/list_rooms":
            return api(request)
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json={"events": []})
        return httpx.Response(503, text="switch is down")

    with respx.mock(assert_all_called=False) as router:
        router.route(host="switch.test").mock(side_effect=handler)
        client = httpx.Client()
        transport = SwitchTransport(
            client=client,
            base_url=SWITCH_BASE,
            agent_id="director",
            token="test-token",
            timeout=1.0,
        )
        room = transport.open_room(name="world")
        with pytest.raises(TransportError, match="503"):
            transport.deliver_many(
                room,
                [Prompt(speaker=CharacterId("alice"), text="@alice hi")],
                turn_id="turn-1",
            )
        client.close()


def test_cloud_generates_replies_concurrently():
    barrier = threading.Barrier(2, timeout=3.0)

    class BarrierModel:
        def generate(
            self,
            character,
            messages,
            *,
            format=ModelFormat.JSON,
            reasoning=None,
            temperature=None,
            max_tokens=None,
        ) -> ModelReply:
            barrier.wait()
            return ModelReply(
                text='{"reply": "together"}', data={"reply": "together"}
            )

        def usage(self, character=None) -> UsageSummary:
            return UsageSummary()

    transport = CloudRoomTransport(BarrierModel())
    room = transport.open_room(name="world")

    delivery = transport.deliver_many(
        room,
        [
            Prompt(speaker=CharacterId("alice"), text="alice prompt"),
            Prompt(speaker=CharacterId("emily"), text="emily prompt"),
        ],
        turn_id="turn-1",
    )

    assert len(delivery.inline) == 2
    assert {str(turn.text) for turn in delivery.inline} == {"together"}


def test_cloud_propagates_model_error_and_records_nothing():
    model = ScriptedModelClient(
        {"alice": [ScriptedTurn(error=ModelError("model is down"))]}
    )
    transport = CloudRoomTransport(model)
    room = transport.open_room(name="world")

    with pytest.raises(ModelError, match="model is down"):
        transport.deliver_many(
            room,
            [Prompt(speaker=CharacterId("alice"), text="alice prompt")],
            turn_id="turn-1",
        )

    assert transport.history(room) == []


@pytest.mark.parametrize("kind", ["cloud", "local"])
def test_in_band_turns_survive_a_frozen_millisecond_clock(kind):
    clock = FrozenClock()
    if kind == "cloud":
        model = ScriptedModelClient(
            {
                "alice": [{"reply": "Alice here."}],
                "emily": [{"reply": "Emily here."}],
            }
        )
        transport = CloudRoomTransport(model, clock=clock)
    else:
        transport = LocalRoomTransport(
            {"alice": ["Alice here."], "emily": ["Emily here."]}, clock=clock
        )

    room = transport.open_room(name="world")
    first = transport.deliver_many(
        room,
        [Prompt(speaker=CharacterId("alice"), text="one")],
        turn_id="turn-1",
    )
    second = transport.deliver_many(
        room,
        [Prompt(speaker=CharacterId("emily"), text="two")],
        turn_id="turn-2",
    )

    assert [str(turn.text) for turn in first.inline] == ["Alice here."]
    assert [str(turn.text) for turn in second.inline] == ["Emily here."]
    assert len(transport.history(room)) == 2
    assert first.inline[0].received_at == second.inline[0].received_at
