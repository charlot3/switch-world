"""The Switch-driven café beat.

This posts scene turns into the live `#world` room and waits for the OpenCode/Claude sessions
to answer. The characters' own world MCP calls are what write beliefs and relationships; the
director only records the public dialogue/feed and exports the scene card.

The lifecycle now lives in :mod:`switch_world.application.beats`; this module
keeps the historical public names and return shape and supplies the live-room
half through :class:`SwitchBeatStrategy` over a
:class:`LegacySwitchTransport`.
"""
from __future__ import annotations

import time

from world_engine.service import WorldService

from switch_world.adapters.clock import SystemClock
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.application.beat_strategies import (
    SWITCH_ALICE_PROMPT as ALICE_PROMPT,
    SWITCH_EMILY_PROMPT as EMILY_PROMPT,
    SwitchBeatStrategy,
)
from switch_world.application.beats import (
    _ensure_secret as _pipeline_ensure_secret,
    get_beat,
    load_spec,
    prompts_for,
    run_beat as _pipeline_run_beat,
)

from . import DEMO_KEY
from .canon import (  # noqa: F401  (re-exports)
    brief,
    branch_for,
    load as load_canon,
    record_branch,
    validate,
)
from .clock import advance_to_beat
from .social import appraise, clean_scene_line  # noqa: F401  (re-exports)
from .switch_client import SwitchClient


def run_cafe_switch(
    service: WorldService | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    service = service or WorldService()
    switch = switch or SwitchClient()

    known = service.who_knows(DEMO_KEY)["holders"]
    if not any(h["holder"] == "alice" and h["source"] == "user" for h in known):
        raise ValueError(
            "Alice does not know the secret in the world state yet; run "
            "`uv run director --tell-alice` first."
        )

    room = switch.find_room(room_name)
    transport = LegacySwitchTransport(switch, time_source=time)
    result = _pipeline_run_beat(
        load_spec(
            "cafe",
            transport="switch",
            room_name=room_name,
            timeout=timeout,
            seed=False,
            advance=False,
        ),
        SwitchBeatStrategy(
            transport,
            timeout=timeout,
            prompts=prompts_for,
        ),
        service,
        SystemClock(),
    )

    turns = {turn["character"]: turn for turn in result["turns"]}
    if "alice" not in turns:
        return {
            "shared": None,
            "alice": None,
            "emily": None,
            "card": result["card"],
            "room": room,
        }

    emily = turns.get("emily")
    return {
        "shared": (result["branch"] or {}).get("id") == "disclosure",
        "beat": result["beat"],
        "transport": "switch",
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "alice": turns["alice"]["reply"],
        "emily": emily["reply"] if emily else "",
        "card": result["card"],
        "room": room,
        "matrix": result["matrix"],
    }


def run_beat_switch(
    service: WorldService | None = None,
    beat_id: str = "cafe",
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    """Run any authored beat through the live Switch room."""
    service = service or WorldService()
    switch = switch or SwitchClient()
    canon = load_canon()
    beat = get_beat(beat_id, canon)

    if beat_id == "cafe":
        _pipeline_ensure_secret(service, DEMO_KEY)
        advance_to_beat(service, canon, beat["id"])
        result = run_cafe_switch(
            service=service,
            switch=switch,
            room_name=room_name,
            timeout=timeout,
        )
        result["beat"] = beat
        result["transport"] = "switch"
        return result

    room = switch.find_room(room_name)
    transport = LegacySwitchTransport(switch, time_source=time)
    result = _pipeline_run_beat(
        load_spec(
            beat_id,
            transport="switch",
            room_name=room_name,
            timeout=timeout,
        ),
        SwitchBeatStrategy(
            transport,
            timeout=timeout,
            prompts=prompts_for,
        ),
        service,
        SystemClock(),
    )
    return {
        "beat": result["beat"],
        "transport": "switch",
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "transcript": result["transcript"],
        "card": result["card"],
        "room": room,
        "matrix": result["matrix"],
    }


__all__ = [
    "ALICE_PROMPT",
    "EMILY_PROMPT",
    "appraise",
    "branch_for",
    "brief",
    "clean_scene_line",
    "load_canon",
    "record_branch",
    "run_beat_switch",
    "run_cafe_switch",
    "validate",
]
