from __future__ import annotations

import sqlite3

from switch_world import config
from switch_world.application.facade import WorldService

OLD_EVENTS = """
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]',
    visibility TEXT NOT NULL DEFAULT 'public',
    created_at TEXT NOT NULL,
    room_id TEXT,
    message_id TEXT,
    supersedes INTEGER
)
"""


def test_old_database_gains_metadata_json_and_keeps_working(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(OLD_EVENTS)
    conn.commit()
    conn.close()

    service = WorldService(db_path=path, state_dir=config.STATE_DIR)

    # The migration ran on the pre-existing events table.
    with sqlite3.connect(str(path)) as check:
        columns = {row[1] for row in check.execute("PRAGMA table_info(events)")}
    assert "metadata_json" in columns

    created = service.record_event(
        "director",
        "note",
        "A turn starts.",
        ["alice"],
        "public",
        metadata={"turn_id": "t-abc", "mode": "speech", "role": "primary"},
    )
    assert created["metadata"]["turn_id"] == "t-abc"
    assert created["metadata"]["mode"] == "speech"

    state = service.state()
    stored = next(event for event in state["events"] if event["id"] == created["id"])
    assert stored["metadata"] == {"turn_id": "t-abc", "mode": "speech", "role": "primary"}

    # Events seeded before the column existed read back with an empty object.
    seeded = next(event for event in state["events"] if event["kind"] == "world_start")
    assert seeded["metadata"] == {}

    # Migration is idempotent: booting the same file again does not fail.
    again = WorldService(db_path=path, state_dir=config.STATE_DIR)
    assert again.events()[-1]["metadata"]["turn_id"] == "t-abc"


def test_metadata_survives_message_id_and_latest_event_lookups(tmp_path):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    service.record_event(
        "alice",
        "dialogue",
        "Alice: hi.",
        ["alice"],
        "public",
        message_id="switch-1",
        metadata={"mode": "speech", "turn_id": "t-1"},
    )
    by_message = service.event_by_message_id("switch-1")
    assert by_message["metadata"] == {"mode": "speech", "turn_id": "t-1"}
    latest = service.latest_event("dialogue")
    assert latest["metadata"]["turn_id"] == "t-1"
