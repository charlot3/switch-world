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
        self.timestamp = int(time.time() * 1000) + 1

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        if self.fail_post:
            from director.switch_client import SwitchError

            raise SwitchError("gateway down")
        self.posted = content
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
    assert "@alice @emily @sophia @mia" in switch.posted
    assert "Are we still on for tonight?" in switch.posted
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


def test_group_say_reports_a_dead_room(service):
    switch = FakeSwitch(fail_post=True)
    with pytest.raises(RuntimeError, match="gateway"):
        say_in_group(service, "Hello?", switch=switch)
    summaries = [event["summary"] for event in service.state()["events"]]
    assert "You: Hello?" in summaries
