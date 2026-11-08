"""The four historical beat runners, now application use cases.

Each runner resolves a :class:`~switch_world.application.beats.BeatSpec`, picks a
strategy from :mod:`switch_world.application.beat_strategies`, and adapts the
pipeline result back to the return shape the HTTP routes, the CLI and the
existing tests expect. The lifecycle itself lives in
:mod:`switch_world.application.beats`; this module only dispatches.

``director.beats``, ``director.bifrost_scene``, ``director.run_switch`` and
``director.simulate`` are compatibility shims over these functions until the
caller migration lands.
"""
from __future__ import annotations

import math
from datetime import datetime

from switch_world.adapters.clock import SystemClock
from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.adapters.transports.switch_client import SwitchClient
from switch_world.application.beat_strategies import (
    SWITCH_ALICE_PROMPT as ALICE_PROMPT,
    SWITCH_EMILY_PROMPT as EMILY_PROMPT,
    BifrostBeatStrategy,
    CloudBeatStrategy,
    LocalBeatStrategy,
    SwitchBeatStrategy,
    _lines_for,
)
from switch_world.application.beats import (
    _apply_effects,
    _canon_warning,
    _ensure_secret as _pipeline_ensure_secret,
    _record_beat,
    get_beat,
    load_spec,
    prompts_for,
    run_beat as _pipeline_run_beat,
)
from switch_world.application.canon import (
    brief,
    branch_for,
    load as load_canon,
    record_branch,
    validate,
)
from switch_world.application.clock import advance_to_beat
from switch_world.application.facade import WorldService
from switch_world.application.prompts import (
    LANGUAGE_AND_VOICE,
    SCHEMA,
    TONE,
    _apply,
    _identity,
    _parse_envelope,
    _system,
)
from switch_world.application.social import appraise, clean_scene_line
from switch_world.application.simulate import run_cafe, user_tells_alice
from switch_world.application.tavily_beat import world_context
from switch_world.domain.demo import DEMO_KEY

# Reads the lazily resolved process settings, which tests patch as
# ``switch_world.config.AGENT_MODE``.
from switch_world import config

BEAT_ORDER = ("morning-shop", "truck-lunch", "cafe", "aftermath", "roundup")


def advance_to(service: WorldService, time_text: str) -> None:
    """Move the world clock to a beat's HH:MM on the same day, never backwards."""
    now = datetime.fromisoformat(service.clock()["now"])
    hour, minute = (int(part) for part in time_text.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = max(0, math.ceil((target - now).total_seconds() / 60))
    if delta:
        service.advance_time("director", delta)


def _ensure_secret(service: WorldService, key: str = DEMO_KEY) -> None:
    _pipeline_ensure_secret(service, key)


def _record_lines(service: WorldService, lines: list[dict]) -> list[dict]:
    """Historical helper kept for callers that record authored lines directly."""
    recorded = []
    for line in lines:
        speaker = line["speaker"]
        label = "You" if speaker == "user" else speaker.title()
        recorded.append(
            service.record_event(
                speaker,
                "dialogue",
                f"{label}: {line['text']}",
                participants=[speaker],
                visibility="public",
            )
        )
    return recorded


def _agent_mode() -> str:
    return str(getattr(config, "AGENT_MODE", "switch")).strip().lower()


def _cloud_model(client=None, timeout: float = 90.0):
    """Resolve the ``ModelClient`` a cloud beat should use."""
    from switch_world.adapters.models import DeepSeekModelClient

    if client is not None:
        if hasattr(client, "generate"):
            return client
        if hasattr(client, "chat_json"):
            return LegacyModelClient(client)
        raise ValueError(
            "cloud transport needs a ModelClient or a legacy chat_json client"
        )

    import os

    from switch_world.config import load_settings

    settings = load_settings(os.environ)
    return DeepSeekModelClient(
        api_key=settings.cloud_api_key or None,
        base_url=settings.cloud_base_url,
        model=settings.cloud_model,
        timeout=timeout,
        clock=SystemClock(),
        budget_path=settings.data_dir / "deepseek_budget.json",
        log_path=settings.data_dir / "logs" / "deepseek.jsonl",
    )


def _run_cloud(
    service: WorldService,
    beat_id: str,
    client=None,
    timeout: float = 90.0,
) -> dict:
    model = _cloud_model(client, timeout)
    return _pipeline_run_beat(
        load_spec(beat_id, transport="cloud", timeout=timeout),
        CloudBeatStrategy(model, timeout=timeout),
        service,
        SystemClock(),
    )


def run_local_beat(
    service: WorldService,
    beat_id: str,
    force_share: bool | None = None,
) -> dict:
    if beat_id == "cafe":
        # Keep the historical order: seed, move to 18:30, then run the café.
        _ensure_secret(service)
        advance_to_beat(service, load_canon(), beat_id)
        result = run_cafe(service, force_share=force_share)
        # ``run_cafe`` is the direct café runner and never recorded these two
        # events itself; ``run_local_beat`` historically did, in this order.
        _record_beat(service, get_beat(beat_id))
        _canon_warning(service, load_canon())
        return {
            "beat": get_beat(beat_id),
            "transport": "local",
            "branch": result["branch"],
            "canon_issues": result["canon_issues"],
            "transcript": result["transcript"],
            "card": result["card"],
            "matrix": result["matrix"],
            "clock": result["clock"],
        }

    result = _pipeline_run_beat(
        load_spec(beat_id, transport="local", force_share=force_share),
        LocalBeatStrategy(),
        service,
        SystemClock(),
    )
    return {
        "beat": result["beat"],
        "transport": result["transport"],
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "transcript": result["transcript"],
        "card": result["card"],
        "matrix": result["matrix"],
        "clock": result["clock"],
    }


def run_arc(service: WorldService, force_share: bool | None = None) -> dict:
    results = []
    for beat_id in BEAT_ORDER:
        results.append(run_local_beat(service, beat_id, force_share=force_share))
    last = results[-1]
    cafe = next(item for item in results if item["beat"]["id"] == "cafe")
    return {
        "beats": results,
        "branch": cafe["branch"],
        "card": last["card"],
        "matrix": service.matrix(),
        "clock": service.clock(),
    }


def run_beat(
    service: WorldService,
    beat_id: str,
    transport: str = "local",
    force_share: bool | None = None,
    client=None,
    switch=None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    if transport == "local":
        return run_local_beat(service, beat_id, force_share=force_share)
    if transport == "bifrost":
        return run_beat_bifrost(service, beat_id, client=client)
    if transport == "cloud":
        return _run_cloud(service, beat_id, client=client, timeout=timeout)
    if transport == "switch":
        # The guest deployment has no Switch Console: serve the same beat from
        # the cloud model instead of opening a room.
        if _agent_mode() == "cloud":
            return _run_cloud(service, beat_id, client=client, timeout=timeout)
        return run_beat_switch(
            service,
            beat_id,
            switch=switch,
            room_name=room_name,
            timeout=timeout,
        )
    raise ValueError("transport must be local, bifrost, switch or cloud")


# ---------------------------------------------------------------------------
# Bifrost runners
# ---------------------------------------------------------------------------


def _group_writes(items) -> dict:
    """The historical ``_apply`` shape from the pipeline's applied-write list."""
    memory = None
    relationships: list[dict] = []
    for item in items or ():
        if isinstance(item, dict) and "memory" in item:
            memory = item["memory"]
        elif isinstance(item, dict):
            relationships.append(item)
    return {"memory": memory, "relationships": relationships}


def _usage(client) -> dict:
    summary = getattr(client, "usage_summary", None)
    return summary() if callable(summary) else {}


def _run_cafe_bifrost(
    service: WorldService,
    client,
    *,
    seed: bool,
    advance: bool,
    prompts=None,
) -> dict:
    known = service.who_knows(DEMO_KEY)["holders"]
    alice_knows = any(
        holder["holder"] == "alice" and holder["source"] == "user"
        for holder in known
    )
    if not alice_knows and not seed:
        raise ValueError("Alice does not know the secret; seed it first")

    context = world_context(service)
    result = _pipeline_run_beat(
        load_spec(
            "cafe",
            transport="bifrost",
            seed=seed,
            advance=advance,
        ),
        BifrostBeatStrategy(
            LegacyModelClient(client),
            prompts=prompts or prompts_for,
        ),
        service,
        SystemClock(),
    )

    turns = {turn["character"]: turn for turn in result["turns"]}
    usage = _usage(client)
    if "alice" not in turns:
        return {
            "shared": None,
            "branch": None,
            "canon_issues": [],
            "alice": None,
            "emily": None,
            "alice_writes": None,
            "emily_writes": None,
            "card": result["card"],
            "matrix": result["matrix"],
            "bifrost": usage,
            "world_context": context,
        }

    alice = turns["alice"]["reply"]
    emily_turn = turns.get("emily")
    return {
        "shared": (result["branch"] or {}).get("id") == "disclosure",
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "alice": alice,
        "emily": emily_turn["reply"] if emily_turn else "",
        "alice_writes": _group_writes(turns["alice"]["writes"]),
        "emily_writes": (
            _group_writes(emily_turn["writes"])
            if emily_turn
            else {"memory": None, "relationships": []}
        ),
        "card": result["card"],
        "matrix": result["matrix"],
        "bifrost": usage,
        "world_context": context,
    }


def run_cafe_bifrost(
    service: WorldService | None = None,
    client=None,
    seed: bool = True,
    prompts=None,
) -> dict:
    """Run the café beat with both character turns generated through Bifrost.

    The caller owns the clock: like the historical function, this does not move
    the world to 18:30. ``director.beats`` and ``run_beat_bifrost`` do that
    before calling in.
    """
    service = service or WorldService()
    if client is None:
        from switch_world.adapters.models.bifrost_compat import BifrostClient

        client = BifrostClient()
    return _run_cafe_bifrost(
        service, client, seed=seed, advance=False, prompts=prompts
    )


def run_beat_bifrost(
    service: WorldService | None = None,
    beat_id: str = "cafe",
    client=None,
    prompts=None,
) -> dict:
    """Run any authored beat through Bifrost; the café keeps its branch logic."""
    service = service or WorldService()
    if client is None:
        from switch_world.adapters.models.bifrost_compat import BifrostClient

        client = BifrostClient()
    canon = load_canon()
    beat = get_beat(beat_id, canon)

    if beat_id == "cafe":
        _pipeline_ensure_secret(service, DEMO_KEY)
        advance_to_beat(service, canon, beat["id"])
        result = run_cafe_bifrost(service, client=client, prompts=prompts)
        result["beat"] = beat
        result["transport"] = "bifrost"
        return result

    context = world_context(service)
    result = _pipeline_run_beat(
        load_spec(beat_id, transport="bifrost"),
        BifrostBeatStrategy(
            LegacyModelClient(client),
            prompts=prompts or prompts_for,
        ),
        service,
        SystemClock(),
    )
    turns = [
        {
            "character": turn["character"],
            "reply": turn["reply"],
            "writes": _group_writes(turn["writes"]),
        }
        for turn in result["turns"]
    ]
    return {
        "beat": result["beat"],
        "transport": result["transport"],
        "branch": result["branch"],
        "canon_issues": result["canon_issues"],
        "turns": turns,
        "transcript": result["transcript"],
        "card": result["card"],
        "matrix": result["matrix"],
        "bifrost": _usage(client),
        "world_context": context,
    }


# ---------------------------------------------------------------------------
# Switch runners
# ---------------------------------------------------------------------------


def run_cafe_switch(
    service: WorldService | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = 90.0,
) -> dict:
    import time

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
    import time

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
    "BEAT_ORDER",
    "EMILY_PROMPT",
    "LANGUAGE_AND_VOICE",
    "SCHEMA",
    "TONE",
    "_apply",
    "_apply_effects",
    "_canon_warning",
    "_ensure_secret",
    "_group_writes",
    "_identity",
    "_lines_for",
    "_parse_envelope",
    "_record_beat",
    "_record_lines",
    "_system",
    "_usage",
    "advance_to",
    "advance_to_beat",
    "appraise",
    "branch_for",
    "brief",
    "clean_scene_line",
    "load_canon",
    "record_branch",
    "run_arc",
    "run_beat",
    "run_beat_bifrost",
    "run_beat_switch",
    "run_cafe_bifrost",
    "run_cafe_switch",
    "run_local_beat",
    "user_tells_alice",
    "validate",
    "world_context",
]
