"""A duplicate event id is a recorded silence beat, not a dropped line.

The old collector skipped an event whose ``message_id`` was already in the
ledger, so a replayed room event vanished from the turn entirely. The recorder
now keeps the turn's shape: the speaker gets a silence row and a silence event,
and the previously recorded line is never written twice.
"""
from __future__ import annotations

from switch_world.adapters.transports import LocalReply, LocalRoomTransport
from switch_world.application.scene import say_in_group
from world_engine import config
from world_engine.service import WorldService


def _service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_duplicate_message_id_records_a_silence_beat(tmp_path):
    service = _service(tmp_path)
    transport = LocalRoomTransport(
        {
            "alice": [
                LocalReply("Still here.", event_id="evt-alice-same"),
                LocalReply("Still here.", event_id="evt-alice-same"),
            ]
        }
    )

    first = say_in_group(
        service,
        "Alice, are you still there?",
        characters=["alice"],
        transport=transport,
        timeout=1.0,
    )
    assert [reply["text"] for reply in first["replies"]] == ["Still here."]

    second = say_in_group(
        service,
        "Alice, still there?",
        characters=["alice"],
        transport=transport,
        timeout=1.0,
    )

    # The duplicate is not re-recorded as dialogue, but it is not dropped either.
    assert second["replies"] == []
    assert second["missing"] == []
    assert len(second["turn"]["lines"]) == 1
    line = second["turn"]["lines"][0]
    assert line["character"] == "alice"
    assert line["mode"] == "silence"

    silence = [
        event
        for event in service.state()["events"]
        if event["kind"] == "silence"
        and event["metadata"].get("turn_id") == second["turn"]["id"]
    ]
    assert len(silence) == 1

    dialogues = [
        event["summary"]
        for event in service.state()["events"]
        if event["kind"] == "dialogue" and event["summary"] == "Alice: Still here."
    ]
    assert len(dialogues) == 1
