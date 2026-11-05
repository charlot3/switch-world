from __future__ import annotations

import time

import pytest

from director.group import say_in_group
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


class FakeSwitch:
    def __init__(self, replies=None, fail_post=False):
        self.replies = replies or {}
        self.fail_post = fail_post
        self.posted = None
        self.posts = []
        self.timestamp = int(time.time() * 1000) + 1

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        if self.fail_post:
            from director.switch_client import SwitchError

            raise SwitchError("gateway down")
        self.posted = content
        self.posts.append(content)
        return {}

    def history(self, room_id):
        return [
            {
                "event_id": f"evt-{name}",
                "sender_name": name,
                "timestamp": self.timestamp,
                "body": text,
            }
            for name, text in self.replies.items()
        ]


def test_group_say_records_both_sides(service):
    switch = FakeSwitch({"alice": "I'm here.", "emily": "Who else?"})
    result = say_in_group(service, "Are we still on for tonight?", switch=switch)
    assert len(switch.posts) == 4
    assert all("@alice" not in post for post in switch.posts[1:])
    assert "Are we still on for tonight?" in switch.posted
    assert "Your relationship with the user" in switch.posted
    assert [reply["character"] for reply in result["replies"]] == ["alice", "emily"]
    assert result["missing"] == ["sophia", "mia"]
    state = service.state()
    summaries = [event["summary"] for event in state["events"]]
    assert "You: Are we still on for tonight?" in summaries
    assert "Alice: I'm here." in summaries


def test_group_say_addresses_a_subset(service):
    switch = FakeSwitch({"mia": "Fries are on."})
    result = say_in_group(service, "Mia, save me a portion.", characters=["mia"], switch=switch)
    assert switch.posted.startswith("@mia ")
    assert result["targets"] == ["mia"]
    assert result["missing"] == []


def test_group_say_ignores_session_placeholders(service):
    switch = FakeSwitch(
        {
            "alice": "Starting a session to handle this — one moment.",
            "emily": "I'm here.",
        }
    )
    result = say_in_group(service, "Hello?", switch=switch, timeout=1.0)
    assert [reply["character"] for reply in result["replies"]] == ["emily"]
    assert "alice" in result["missing"]


def test_group_say_gates_an_intimate_question(service):
    switch = FakeSwitch({name: "Black." for name in ("alice", "emily", "sophia", "mia")})
    before = service.relationship("alice", "user")["tension"]
    result = say_in_group(service, "what color is your underwear?", switch=switch)
    assert all("black" not in reply["text"].lower() for reply in result["replies"])
    assert all(verdict["stance"] in {"refuse", "deflect"} for verdict in result["verdicts"].values())
    assert service.relationship("alice", "user")["tension"] > before
    assert any(event["kind"] == "social_verdict" for event in service.state()["events"])


def test_group_say_reports_a_dead_room(service):
    switch = FakeSwitch(fail_post=True)
    with pytest.raises(RuntimeError, match="gateway"):
        say_in_group(service, "Hello?", switch=switch)
    summaries = [event["summary"] for event in service.state()["events"]]
    assert "You: Hello?" in summaries


def test_group_say_does_not_record_the_same_switch_event_twice(service):
    class ReplayingSwitch(FakeSwitch):
        def history(self, room_id):
            self.timestamp += 1
            return super().history(room_id)

    switch = ReplayingSwitch({"alice": "Still here."})
    first = say_in_group(service, "First line.", characters=["alice"], switch=switch, timeout=1)
    second = say_in_group(service, "Second line.", characters=["alice"], switch=switch, timeout=1)
    assert first["replies"]
    assert second["replies"] == []
    summaries = [event["summary"] for event in service.state()["events"] if event["kind"] == "dialogue"]
    assert summaries.count("Alice: Still here.") == 1
