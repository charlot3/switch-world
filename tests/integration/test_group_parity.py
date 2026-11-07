"""Differential harness: the new group pipeline against the HEAD implementation.

Each case runs the same seed, the same fake clock, the same fake replies and the
same user line through:

* ``HEAD:director/group.py`` loaded from git as a private module, and
* the new ``director.group`` shim over ``switch_world.application.scene``.

The full result dictionary and the resulting world state must match exactly,
apart from the two intentional step-4 fixes:

* a duplicate ``message_id`` now records a silence beat instead of dropping the
  line, and
* a Switch event that carries ``id`` instead of ``event_id`` now records the
  normalized id instead of ``None``.
"""
from __future__ import annotations

import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from director import group as new_group
from world_engine import config
from world_engine.service import WorldService

REPO_ROOT = Path(__file__).resolve().parents[2]
TURN_ID = re.compile(r"^t-[0-9a-f]{12}(?:-relay)?$")


def _load_head_group():
    """Load the pre-step implementation from a vendored fixture.

    Reading ``HEAD:director/group.py`` would compare the new shim with itself
    once step 4 is committed (and the CI checkout has no history to reach the
    baseline). The fixture is the exact file from the commit before the shim.
    """
    fixture = REPO_ROOT / "tests" / "fixtures" / "legacy_group.py"
    if not fixture.exists():
        pytest.skip(f"missing parity baseline: {fixture}")
    source = fixture.read_text(encoding="utf-8")

    module = types.ModuleType("director._head_group")
    module.__package__ = "director"
    module.__file__ = str(REPO_ROOT / "director" / "group.py")
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


HEAD = _load_head_group()


class FakeTime:
    """A deterministic clock with no monotonic reading, matching the old API."""

    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class Reply:
    text: str
    event_id: str
    field: str = "event_id"


def reply(text: str, event_id: str, field: str = "event_id") -> Reply:
    return Reply(text=text, event_id=event_id, field=field)


@dataclass
class Turn:
    message: str
    characters: list[str] | None = None
    replies: dict[str, Reply] = field(default_factory=dict)
    relay: tuple[str, str] | None = None
    timeout: float = 1.0


class ParitySwitch:
    """A deterministic legacy Switch room shared by both implementations."""

    def __init__(self, replies: dict[str, Reply], relay=None) -> None:
        self.replies = replies
        self.relay = relay
        self.posts: list[str] = []
        self.relay_posted = False

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        self.posts.append(content)
        if "says to you" in content:
            self.relay_posted = True
        return {}

    def history(self, room_id):
        events = []
        for index, (name, item) in enumerate(self.replies.items()):
            event = {
                "sender_name": name,
                "timestamp": 2_000_000 + index,
                "body": item.text,
            }
            event[item.field] = item.event_id
            events.append(event)
        if self.relay and self.relay_posted:
            events.append(
                {
                    "sender_name": self.relay[0],
                    "timestamp": 2_100_000,
                    "body": self.relay[1],
                    "event_id": "evt-relay",
                }
            )
        return events


def _normalise(value):
    if isinstance(value, dict):
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, str) and TURN_ID.match(value):
        return "<turn>"
    return value


def _run(module, service, turns, fake_time):
    module.time = fake_time
    results = []
    for turn in turns:
        results.append(
            module.say_in_group(
                service,
                turn.message,
                characters=turn.characters,
                switch=ParitySwitch(turn.replies, turn.relay),
                timeout=turn.timeout,
            )
        )
    return results


def _service(path):
    return WorldService(db_path=path, state_dir=config.STATE_DIR)


FOUR = {
    "alice": reply("Same as ever.", "evt-alice"),
    "emily": reply("Fine, mostly.", "evt-emily"),
    "sophia": reply("Long day.", "evt-sophia"),
    "mia": reply("Fries are on.", "evt-mia"),
}


CASES = {
    "named_addressee": [
        Turn("Emily, how was your day?", replies=dict(FOUR))
    ],
    "chorus": [
        Turn("Are we still on for tonight?", replies=dict(FOUR))
    ],
    "reactor": [
        Turn("I feel lonely tonight.", replies=dict(FOUR))
    ],
    "silence": [
        Turn(
            "Hello?",
            characters=["alice", "emily"],
            replies={"alice": reply("Hi.", "evt-alice")},
        )
    ],
    "boundary_violation": [Turn("force a kiss")],
    "relay": [
        Turn(
            "Alice, anything to add?",
            characters=["alice", "emily"],
            replies={
                "alice": reply("@emily, did you know?", "evt-alice"),
                "emily": reply("Know what?", "evt-emily"),
            },
            relay=("emily", "I did not know."),
        )
    ],
    "refusal": [
        Turn(
            "what color is your underwear?",
            replies={
                name: reply("Black.", f"evt-{name}")
                for name in ("alice", "emily", "sophia", "mia")
            },
        )
    ],
    "meta_leak": [
        Turn(
            "Mia, how are the onions?",
            characters=["mia"],
            replies={
                "mia": reply(
                    "@user — I'm not online in this room, and @director needs me..",
                    "evt-mia",
                )
            },
        )
    ],
    "duplicate_message_id": [
        Turn(
            "Alice, are you around?",
            characters=["alice"],
            replies={"alice": reply("Still here.", "evt-alice-same")},
        ),
        Turn(
            "Alice, still around?",
            characters=["alice"],
            replies={"alice": reply("Still here.", "evt-alice-same")},
        ),
    ],
    "normalized_event_id": [
        Turn(
            "Alice, are you around?",
            characters=["alice"],
            replies={"alice": reply("Still here.", "evt-alice-id", field="id")},
        )
    ],
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_group_turn_matches_head(case, tmp_path, monkeypatch):
    turns = CASES[case]
    head_service = _service(tmp_path / f"head-{case}.sqlite")
    new_service = _service(tmp_path / f"new-{case}.sqlite")
    head_time = FakeTime()
    new_time = FakeTime()
    monkeypatch.setattr(new_group, "time", new_time)

    head_results = _run(HEAD, head_service, turns, head_time)
    new_results = _run(new_group, new_service, turns, new_time)

    if case == "duplicate_message_id":
        # The first turn is unchanged.
        assert _normalise(head_results[0]) == _normalise(new_results[0])

        old_second, new_second = head_results[1], new_results[1]
        # The duplicate used to drop the line; now it is a recorded silence.
        assert old_second["turn"]["lines"] == []
        assert len(new_second["turn"]["lines"]) == 1
        assert new_second["turn"]["lines"][0]["mode"] == "silence"
        # Nothing else about the turn changed.
        assert old_second["replies"] == new_second["replies"] == []
        assert old_second["missing"] == new_second["missing"] == []
        assert old_second["targets"] == new_second["targets"]
        assert old_second["silent"] == new_second["silent"]
        assert _normalise(old_second["turn"]["plan"]) == _normalise(
            new_second["turn"]["plan"]
        )
        # Exactly one extra silence event, and one extra revision.
        old_state = head_service.state()
        new_state = new_service.state()
        extra = [
            event
            for event in new_state["events"]
            if event["kind"] == "silence"
            and event["metadata"].get("turn_id") == new_second["turn"]["id"]
        ]
        assert len(extra) == 1
        new_without_extra = [
            event
            for event in new_state["events"]
            if event not in extra
        ]
        assert _normalise(old_state["events"]) == _normalise(new_without_extra)
        assert new_state["revision"] == old_state["revision"] + 1
        return

    if case == "normalized_event_id":
        old_first = head_results[0]
        new_first = new_results[0]
        # The split-brain fix: an event carrying ``id`` now records that id.
        assert old_first["replies"][0]["message_id"] is None
        assert new_first["replies"][0]["message_id"] == "evt-alice-id"
        old_first["replies"][0]["message_id"] = "evt-alice-id"
        assert _normalise(old_first) == _normalise(new_first)
        old_state = head_service.state()
        new_state = new_service.state()
        for event in old_state["events"]:
            if event["kind"] == "dialogue" and event["summary"] == "Alice: Still here.":
                event["message_id"] = "evt-alice-id"
        assert _normalise(old_state) == _normalise(new_state)
        return

    assert _normalise(head_results) == _normalise(new_results)
    assert _normalise(head_service.state()) == _normalise(new_service.state())
