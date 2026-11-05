from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from director import clock as story_clock
from world_engine import config
from world_engine.service import WorldService

CANON = json.loads((config.ROOT / "world" / "canon.json").read_text())


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_mock_clock_advances_to_next_beat(service):
    assert service.clock()["mode"] == "mock"
    moved = story_clock.advance_to_next(service, CANON)
    assert moved["beat"]["id"] == "morning-shop"
    assert service.clock()["now"].startswith("2026-11-03T09:10")
    assert service.clock()["mode"] == "mock"


def test_mock_clock_wraps_to_the_next_day(service):
    start = datetime.fromisoformat(service.clock()["now"])
    end_of_day = start.replace(hour=23, minute=0)
    service.advance_time("director", int((end_of_day - start).total_seconds() // 60))
    moved = story_clock.advance_to_next(service, CANON)
    assert moved["beat"]["id"] == "morning-shop"
    assert moved["clock"]["now"].startswith("2026-11-04T09:10")


def test_same_time_beat_does_not_jump_a_day(service):
    story_clock.advance_to_next(service, CANON)  # 09:10
    moved = story_clock.advance_to_beat(service, CANON, "morning-shop")
    assert moved["clock"]["now"].startswith("2026-11-03T09:10")


def test_advance_to_named_beat(service):
    moved = story_clock.advance_to_beat(service, CANON, "roundup")
    assert moved["beat"]["id"] == "roundup"
    assert moved["clock"]["now"].startswith("2026-11-03T22:10")


def test_realtime_is_anchored_to_the_next_beat(service):
    moved = story_clock.align_realtime(service, CANON)
    assert service.clock()["mode"] == "realtime"
    now = datetime.fromisoformat(service.clock()["now"])
    real = datetime.now(now.tzinfo)
    assert timedelta(0) <= now - real < timedelta(days=1)
    assert now.strftime("%H:%M") in {beat["time"] for beat in CANON["beats"]}
    assert moved["beat"]["id"] == story_clock.current_beat(CANON, now)["id"]


def test_realtime_clock_runs_with_the_wall_clock(service, monkeypatch):
    anchored = "2026-11-03T18:30:00+09:00"
    real = datetime.now(datetime.fromisoformat(anchored).tzinfo)
    monkeypatch.setattr(WorldService, "_real_now", classmethod(lambda cls: real))
    service.set_clock_mode("realtime", now=anchored)
    monkeypatch.setattr(
        WorldService, "_real_now", classmethod(lambda cls: real + timedelta(minutes=5))
    )
    assert service.clock()["now"].startswith("2026-11-03T18:35")


def test_advance_leaves_realtime(service):
    service.set_clock_mode("realtime", now="2026-11-03T18:30:00+09:00")
    service.advance_time("director", 10)
    assert service.clock()["mode"] == "mock"
    assert service.clock()["now"].startswith("2026-11-03T18:40")


def test_beat_jump_does_not_land_before_the_beat(service):
    with service._conn() as conn:
        conn.execute(
            "UPDATE clock SET now = ?, day = ?, mode = 'mock', anchor_real = NULL WHERE id = 1",
            ("2026-11-03T09:08:30+09:00", "2026-11-03"),
        )
    moved = story_clock.advance_to_beat(service, CANON, "cafe")
    assert moved["beat"]["id"] == "cafe"
    assert service.clock()["now"] >= "2026-11-03T18:30:00"
    assert story_clock.current_beat(CANON, datetime.fromisoformat(service.clock()["now"]))["id"] == "cafe"
