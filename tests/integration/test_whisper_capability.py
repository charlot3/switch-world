"""The whisper branches on transport capabilities, not on ``hasattr``.

* ``capabilities().private_rooms is False`` -> staged: the target is answered by
  the injected model and the result says ``transport: "staged"``.
* ``capabilities().private_rooms is True`` -> the transport's private room
  carries the words; the model is only used for the observers.
* A failed private-room lookup degrades to the staged path.
* The legacy private-room adapter reads ``history`` once and filters
  placeholders through the shared ``clean_scene_line``.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from switch_world.application import social
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.adapters.transports.local import LocalRoomTransport
from switch_world.application.scene import whisper
from switch_world.domain.ports.model import ModelFormat, ModelReply
from switch_world.domain.ports.transport import (
    TransportCapabilities,
    TransportError,
)
from switch_world import config
from switch_world.application.facade import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )


class ScriptedModel:
    """A ModelClient that answers per character and records every call."""

    def __init__(self, replies: dict[str, str] | None = None) -> None:
        self.replies = dict(replies or {})
        self.calls: list[dict[str, Any]] = []

    def generate(self, character, messages, *, format=ModelFormat.JSON, **kwargs):
        name = str(character)
        self.calls.append(
            {"character": name, "messages": list(messages), "format": format}
        )
        return ModelReply(
            text=json.dumps({"reply": self.replies.get(name, "Okay.")}),
            data={"reply": self.replies.get(name, "Okay.")},
            model="test",
        )

    def usage_summary(self) -> dict:
        return {"requests": len(self.calls)}


class NoPrivateTransport:
    """A transport that declares no private rooms and must never be opened."""

    name = "no-private"

    def __init__(self) -> None:
        self.opened = 0

    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format="text",
            write_mode="out_of_band",
            private_rooms=False,
            non_blocking_post=True,
            addressing=True,
            event_id_field="event_id",
        )

    def open_room(self, *, name, private_for=None):
        self.opened += 1
        raise AssertionError("a transport without private rooms was opened")

    def deliver_many(self, *args, **kwargs):
        raise AssertionError("the staged path must not deliver to the transport")

    def collect(self, *args, **kwargs):
        raise AssertionError("the staged path must not collect from the transport")

    def history(self, *args, **kwargs):
        raise AssertionError("the staged path must not read transport history")

    def close(self) -> None:
        return None


class BrokenPrivateTransport(NoPrivateTransport):
    """Declares private rooms, but the lookup fails: staged fallback."""

    name = "broken-private"

    def capabilities(self) -> TransportCapabilities:
        return TransportCapabilities(
            response_format="text",
            write_mode="out_of_band",
            private_rooms=True,
            non_blocking_post=True,
            addressing=True,
            event_id_field="event_id",
        )

    def open_room(self, *, name, private_for=None):
        self.opened += 1
        raise TransportError("no private room for this character")


class LegacyPrivateSwitch:
    """The old private-room surface wrapped by the compatibility adapter."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.history_calls = 0
        self.posts: list[str] = []

    def find_private_room(self, to: str) -> dict:
        return {"room_id": f"private-{to}", "name": f"private-{to}"}

    def history(self, room_id: str) -> list[dict]:
        self.history_calls += 1
        return [{"timestamp": 1000, "body": "older line"}]

    def post(self, room_id: str, content: str) -> dict:
        self.posts.append(content)
        return {}

    def wait_for(self, room_id, sender, started, timeout=None) -> dict:
        return {
            "sender_name": sender,
            "timestamp": 1001,
            "body": self.answer,
        }


def test_staged_when_transport_has_no_private_rooms(service):
    transport = NoPrivateTransport()
    model = ScriptedModel(
        {
            "alice": "Long, but the good kind.",
            "emily": "She glances over.",
            "sophia": "She looks away.",
        }
    )

    result = whisper(
        service, "alice", "how was your day?", model=model, transport=transport
    )

    assert result["transport"] == "staged"
    assert result["target"] == "alice"
    assert result["reply"] == "Long, but the good kind."
    assert result["observers"] == ["emily", "sophia"]
    assert transport.opened == 0
    assert [call["character"] for call in model.calls] == [
        "alice",
        "emily",
        "sophia",
    ]
    # The private events stay private; the observers' lines stay public.
    events = service.state()["events"]
    assert next(e for e in events if e["kind"] == "whisper")["visibility"] == "private"
    assert (
        next(e for e in events if e["kind"] == "whisper_reply")["visibility"]
        == "private"
    )
    assert all(
        e["visibility"] == "public"
        for e in events
        if e["kind"] in {"dialogue", "silence"}
    )


def test_private_room_when_capabilities_say_yes(service):
    transport = LocalRoomTransport(script={"alice": "Meet me after closing."})
    model = ScriptedModel(
        {"emily": "She glances over.", "sophia": "She looks away."}
    )

    result = whisper(
        service, "alice", "meet me after closing", model=model, transport=transport
    )

    assert result["transport"] == "switch"
    assert result["reply"] == "Meet me after closing."
    assert result["observers"] == ["emily", "sophia"]
    # The private room carried the target's answer; the model only saw observers.
    assert "alice" not in [call["character"] for call in model.calls]
    assert [call["character"] for call in model.calls] == ["emily", "sophia"]

    events = service.state()["events"]
    whisper_event = next(e for e in events if e["kind"] == "whisper")
    assert whisper_event["visibility"] == "private"
    assert "meet me after closing" in whisper_event["summary"].lower()
    public = [e for e in events if e["visibility"] == "public"]
    assert public
    assert all("meet me after closing" not in e["summary"].lower() for e in public)


def test_failed_private_lookup_falls_back_to_staged(service):
    transport = BrokenPrivateTransport()
    model = ScriptedModel(
        {"alice": "Okay.", "emily": "She glances over.", "sophia": "She looks away."}
    )

    result = whisper(
        service, "alice", "meet me after closing", model=model, transport=transport
    )

    assert transport.opened == 1
    assert result["transport"] == "staged"
    assert result["reply"] == "Okay."


def test_private_room_reply_takes_the_shared_policy_gate(service):
    """A private-room answer is still a model line: the policy applies."""
    transport = LocalRoomTransport(script={"alice": "Come here and kiss me."})
    model = ScriptedModel(
        {"emily": "She glances over.", "sophia": "She looks away."}
    )

    result = whisper(
        service, "alice", "force a kiss", model=model, transport=transport
    )

    verdict = social.appraise(service, "alice", "force a kiss", public=False)
    assert result["transport"] == "switch"
    assert result["reply"] == social.deflection("alice", verdict, "force a kiss")
    assert "Come here" not in result["reply"]
    reply_event = next(
        event
        for event in service.state()["events"]
        if event["kind"] == "whisper_reply"
    )
    assert result["reply"] in reply_event["summary"]


def test_legacy_private_room_reads_history_once_and_filters_placeholders(service):
    backend = LegacyPrivateSwitch(
        answer="Starting a session to handle this\nMeet me after closing."
    )
    transport = LegacySwitchTransport(backend)
    assert transport.capabilities().private_rooms is True

    result = whisper(
        service,
        "alice",
        "meet me after closing",
        transport=transport,
        timeout=2.0,
    )

    assert result["transport"] == "switch"
    # The shared line filter drops the Switch placeholder line, keeping the rest.
    assert result["reply"] == "Meet me after closing."
    assert backend.history_calls == 1
    assert backend.posts == ["meet me after closing"]
