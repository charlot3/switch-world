from __future__ import annotations

import json

from switch_world.application.switch_log import collect, write_jsonl


class FakeSwitch:
    def _op(self, name):
        assert name == "list_rooms"
        return [
            {"room_id": "room-1", "name": "world", "archived": False},
            {"room_id": "room-2", "name": "Mattermost: Town Square", "archived": False},
        ]

    def history(self, room_id):
        return [{
            "id": "evt-1",
            "kind": "message",
            "sender": "@switch-agent-alice",
            "sender_name": "alice",
            "body": "hello",
            "timestamp": 1793859600000,
            "attachments": [],
        }]


def test_switch_log_collects_and_writes_jsonl(tmp_path):
    events = collect(FakeSwitch(), room="world")
    assert len(events) == 1
    assert events[0]["room_name"] == "world"
    assert events[0]["sender_name"] == "alice"
    assert events[0]["body"] == "hello"
    assert events[0]["timestamp_iso"].startswith("2026-11-05T")

    path = write_jsonl(events, tmp_path / "switch-log.jsonl")
    line = json.loads(path.read_text().strip())
    assert line["event_id"] == "evt-1"
