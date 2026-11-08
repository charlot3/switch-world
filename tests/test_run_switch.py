from __future__ import annotations

from switch_world.application.beat_runners import run_beat_switch, run_cafe_switch
from switch_world.application.simulate import user_tells_alice
from switch_world import config
from switch_world.application.facade import WorldService


class FakeSwitch:
    def __init__(self, bodies=None):
        self.bodies = dict(bodies or {})
        self.posts: list[str] = []

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        self.posts.append(content)
        return {}

    def wait_for(self, room_id, character, started, timeout=90.0):
        body = self.bodies.get(character)
        if body is None:
            return None
        return {
            "event_id": f"evt-{character}",
            "sender_name": character,
            "timestamp": started + 1,
            "body": body,
        }

    def history(self, room_id):
        return []


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_cafe_switch_does_not_record_a_placeholder_reply(tmp_path):
    service = make_service(tmp_path)
    user_tells_alice(service)
    switch = FakeSwitch({"alice": "Starting a session to handle this — one moment."})

    result = run_cafe_switch(service, switch=switch, timeout=1.0)

    assert result["alice"] is None
    assert result["emily"] is None
    assert service.events(kind="no_reply")
    assert service.events(kind="dialogue") == []


def test_cafe_switch_does_not_record_a_meta_reply(tmp_path):
    service = make_service(tmp_path)
    user_tells_alice(service)
    switch = FakeSwitch({"alice": "@user — I'm not online in this room, @director."})

    result = run_cafe_switch(service, switch=switch, timeout=1.0)

    assert result["alice"] is None
    assert service.events(kind="no_reply")
    assert all(
        "@user" not in event["summary"] and "@director" not in event["summary"]
        for event in service.events(kind="dialogue")
    )


def test_beat_switch_skips_a_placeholder_character(tmp_path):
    service = make_service(tmp_path)
    switch = FakeSwitch({"alice": "Starting a session to handle this — one moment."})

    result = run_beat_switch(service, "morning-shop", switch=switch, timeout=1.0)

    assert result["transcript"] == []
    assert result["beat"]["id"] == "morning-shop"
    assert service.events(kind="no_reply")
    assert service.events(kind="dialogue") == []
