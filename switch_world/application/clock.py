"""The story clock: mock fast-forward and real-time alignment.

The world stores one story datetime. In `mock` mode it only moves when the showrunner
advances it, which is how a demo unlocks the next beat in seconds. In `realtime` mode the
stored datetime is an anchor and the story runs at 1x from the wall clock, so the next
authored beat arrives when its time of day actually arrives.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from switch_world.application.facade import WorldService


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = (int(part) for part in value.split(":"))
    return hour, minute


def _at(day, value: str, tz) -> datetime:
    hour, minute = _hhmm(value)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)


def beats_in_order(canon: dict) -> list[dict]:
    return sorted(canon.get("beats", []), key=lambda beat: beat.get("order", 0))


def current_beat(canon: dict, now: datetime) -> dict:
    """The last beat whose time of day has started; the first beat before the day starts."""
    started = [beat for beat in beats_in_order(canon) if _at(now.date(), beat["time"], now.tzinfo) <= now]
    return started[-1] if started else beats_in_order(canon)[0]


def next_beat(canon: dict, now: datetime) -> tuple[dict, datetime]:
    """The next authored beat and its datetime, wrapping to the next day."""
    for beat in beats_in_order(canon):
        target = _at(now.date(), beat["time"], now.tzinfo)
        if target > now:
            return beat, target
    first = beats_in_order(canon)[0]
    return first, _at(now.date() + timedelta(days=1), first["time"], now.tzinfo)


def done_beats(service: WorldService) -> set[str]:
    return set(service.completed_beats())


def next_unplayed(canon: dict, done: set[str]) -> dict | None:
    for beat in beats_in_order(canon):
        if beat["id"] not in done:
            return beat
    return None


def advance_to_next(service: WorldService, canon: dict) -> dict:
    """Jump to the next beat. This deliberately leaves realtime for mock mode."""
    now = datetime.fromisoformat(service.clock()["now"])
    beat, target = next_beat(canon, now)
    minutes = max(1, math.ceil((target - now).total_seconds() / 60))
    clock = service.advance_time("director", minutes)
    return {"beat": beat, "clock": clock, "target": target.isoformat(timespec="seconds")}


def advance_to_beat(service: WorldService, canon: dict, beat_id: str) -> dict:
    """Jump to a named beat today (or tomorrow if its time has passed)."""
    now = datetime.fromisoformat(service.clock()["now"])
    for beat in beats_in_order(canon):
        if beat["id"] != beat_id:
            continue
        target = _at(now.date(), beat["time"], now.tzinfo)
        if target < now:
            target += timedelta(days=1)
        minutes = max(0, math.ceil((target - now).total_seconds() / 60))
        clock = service.advance_time("director", minutes)
        return {"beat": beat, "clock": clock, "target": target.isoformat(timespec="seconds")}
    raise ValueError("unknown beat: " + beat_id)


def align_realtime(service: WorldService, canon: dict, scale: float | None = None) -> dict:
    """Enter realtime at the next point where story time and wall time line up.

    If it is 14:00, the story jumps to 18:30 (the café) and then runs at `scale` times
    the wall clock (1x unless a demo asks for a faster clock). If the last beat of the
    day has passed, it aligns to the first beat tomorrow.
    """
    current = datetime.fromisoformat(service.clock()["now"])
    real = datetime.now(current.tzinfo)
    target = None
    beat = None
    for candidate in beats_in_order(canon):
        moment = _at(real.date(), candidate["time"], real.tzinfo)
        if moment > real:
            target, beat = moment, candidate
            break
    if target is None:
        beat = beats_in_order(canon)[0]
        target = _at(real.date() + timedelta(days=1), beat["time"], real.tzinfo)
    clock = service.set_clock_mode(
        "realtime", now=target.isoformat(timespec="seconds"), scale=scale
    )
    return {"beat": beat, "clock": clock, "target": target.isoformat(timespec="seconds")}
