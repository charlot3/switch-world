"""Differential harness: the new whisper pipeline against the HEAD implementation.

Each case runs the same seed, the same fake model replies and the same user
line through:

* ``HEAD:director/whisper.py`` loaded from a vendored fixture as a private
  module, and
* the new ``director.whisper`` shim over
  ``switch_world.application.scene.whisper``.

Normal replies, refusals, an empty observer, the no-private-room fallback,
private-room delivery, an absent target and an invalid target must match the
result, the raised errors, the model calls and the resulting world state
exactly.

Two differences are intentional and asserted rather than hidden:

* the observer path now applies the shared meta sanitiser, so an observer reply
  that is only stage machinery is replaced by the safe fallback dialogue
  instead of a public dialogue line carrying the leak;
* the legacy private-room path reads ``history`` once (to find the start
  marker) instead of twice.
"""
from __future__ import annotations

import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from director import whisper as new_whisper
from world_engine import config
from world_engine.service import WorldService

REPO_ROOT = Path(__file__).resolve().parents[2]
TURN_ID = re.compile(r"^t-[0-9a-f]{12}$")


def _load_head_whisper():
    """Load the pre-step implementation from a vendored fixture."""
    fixture = REPO_ROOT / "tests" / "fixtures" / "legacy_whisper.py"
    if not fixture.exists():
        pytest.skip(f"missing parity baseline: {fixture}")
    source = fixture.read_text(encoding="utf-8")

    module = types.ModuleType("director._head_whisper")
    module.__package__ = "director"
    module.__file__ = str(REPO_ROOT / "director" / "whisper.py")
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


HEAD = _load_head_whisper()


class FakeBifrost:
    """A legacy ``chat_json`` client that records every call."""

    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        self.replies = dict(replies or {})
        self.calls: list[dict[str, Any]] = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append(
            {"character": character, "messages": messages, "kwargs": kwargs}
        )
        return {
            "reply": self.replies.get(character, "Okay."),
            "memory": None,
            "relationships": [],
        }

    def usage_summary(self) -> dict[str, Any]:
        return {"requests": len(self.calls)}


class PlainSwitch:
    """A legacy Switch client with public rooms only."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []

    def find_room(self, name="world") -> dict:
        return {"room_id": "room-world", "name": name}

    def post(self, room_id: str, content: str) -> dict:
        self.posts.append((room_id, content))
        return {}

    def history(self, room_id: str) -> list[dict]:
        return []


class PrivateSwitch(PlainSwitch):
    """A legacy Switch client that can open a verified private room."""

    def __init__(self, answer: str = "Meet me after closing.") -> None:
        super().__init__()
        self.answer = answer
        self.history_calls = 0
        self.waiting: list[dict] = []

    def find_private_room(self, to: str) -> dict:
        return {"room_id": f"private-{to}", "name": f"private-{to}"}

    def history(self, room_id: str) -> list[dict]:
        self.history_calls += 1
        return [{"timestamp": 1000, "body": "earlier private line"}]

    def wait_for(self, room_id: str, sender: str, started: Any, timeout=None) -> dict:
        self.waiting.append(
            {"room_id": room_id, "sender": sender, "started": started, "timeout": timeout}
        )
        return {
            "room_id": room_id,
            "sender_name": sender,
            "timestamp": 1001,
            "body": self.answer,
        }


@dataclass(frozen=True)
class Case:
    message: str
    replies: dict[str, Any] = field(default_factory=dict)
    switch: str | None = None  # None, "plain" or "private"
    absent: str | None = None


CASES: dict[str, Case] = {
    "normal_reply": Case(
        "how was your day?",
        {
            "alice": "Long, but the good kind.",
            "emily": "She glances over.",
            "sophia": "She looks away.",
        },
    ),
    "refusal": Case(
        "force a kiss",
        {
            "alice": "Come here and kiss me.",
            "emily": "She glances over.",
            "sophia": "She looks away.",
        },
    ),
    "meta_leak": Case(
        "are you there?",
        {
            "alice": "@user — I'm not online in this room, @director.",
            "emily": "@user — I'm not online in this room, @director.",
            "sophia": "She looks away.",
        },
    ),
    "empty_observer": Case(
        "do they glance over, then look away when I come in?",
        {
            "alice": "Okay.",
            "emily": "She looks over.",
            "sophia": "She looks over.",
        },
    ),
    "private_room": Case("meet me after closing", switch="private"),
    "no_private_room": Case(
        "meet me after closing",
        {"alice": "Okay.", "emily": "She glances over.", "sophia": "She looks away."},
        switch="plain",
    ),
    "target_absent": Case(
        "hello", {"alice": "Okay.", "emily": "She glances over."}, absent="alice"
    ),
    "invalid_target": Case("hello", {"alice": "Okay."}),
}


def _normalise(value):
    if isinstance(value, dict):
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, str) and TURN_ID.match(value):
        return "<turn>"
    return value


def _run(module, db_path, case_name: str):
    case = CASES[case_name]
    service = WorldService(db_path=db_path, state_dir=config.STATE_DIR)
    if case.absent:
        service.mark_absent(case.absent, reason="left")
    character = "nobody" if case_name == "invalid_target" else "alice"
    client = FakeBifrost(case.replies) if case.switch != "private" else None
    switch = None
    if case.switch == "plain":
        switch = PlainSwitch()
    elif case.switch == "private":
        switch = PrivateSwitch()
    try:
        result = module.whisper_to_character(
            service, character, case.message, client=client, switch=switch
        )
        error = None
    except Exception as exc:  # parity covers the error type and message too
        result = None
        error = (type(exc).__name__, str(exc))
    return {
        "result": result,
        "error": error,
        "calls": client.calls if client is not None else [],
        "switch": switch,
        "service": service,
    }


@pytest.mark.parametrize("case_name", sorted(CASES))
def test_whisper_matches_head(case_name, tmp_path):
    head = _run(HEAD, tmp_path / f"head-{case_name}.sqlite", case_name)
    new = _run(new_whisper, tmp_path / f"new-{case_name}.sqlite", case_name)

    assert head["error"] == new["error"]

    if case_name == "meta_leak":
        _assert_meta_leak_difference(head, new)
        return

    assert _normalise(head["result"]) == _normalise(new["result"])
    assert _normalise(head["calls"]) == _normalise(new["calls"])
    if case_name == "private_room":
        # The private reply and world state are identical; only the number of
        # history reads changed (two in HEAD, one here).
        assert head["switch"].history_calls == 2
        assert new["switch"].history_calls == 1
        assert head["switch"].posts == new["switch"].posts
    assert _normalise(head["service"].state()) == _normalise(new["service"].state())


def _assert_meta_leak_difference(head, new):
    """The observer's stage machinery becomes silence; everything else matches."""
    # The target reply is the policy deflection in both implementations.
    assert head["result"]["reply"] == new["result"]["reply"]
    assert head["result"]["private_event_id"] is not None
    assert _normalise(head["calls"]) == _normalise(new["calls"])

    def public(service):
        return [
            event
            for event in service.state()["events"]
            if event["visibility"] == "public"
        ]

    head_public = public(head["service"])
    new_public = public(new["service"])
    head_meta = [
        event
        for event in head_public
        if event["kind"] == "dialogue" and "@user" in event["summary"]
    ]
    assert head_meta, "HEAD records the observer's meta leak as dialogue"
    assert not [
        event
        for event in new_public
        if event["kind"] == "dialogue" and "@user" in event["summary"]
    ]
    # The sanitised observer reply falls back to the safe, non-leaking line.
    new_safe = [
        event
        for event in new_public
        if event["kind"] == "dialogue"
        and "They glance over, then look away." in event["summary"]
    ]
    assert new_safe
    for event in new_safe:
        metadata = event["metadata"]
        assert metadata["mode"] == "reaction"
        assert metadata["role"] == "reactor"
        assert metadata["target"] == "alice"
    # Removing the meta dialogue from each side leaves the same state.
    head_events = [
        event for event in head["service"].state()["events"]
        if event not in head_meta
    ]
    new_events = [
        event for event in new["service"].state()["events"]
        if event not in new_safe
    ]
    assert _normalise(head_events) == _normalise(new_events)
