"""Compatibility shim: free-form group chat through the application pipeline.

The turn itself now lives in :mod:`switch_world.application.turns` and
:mod:`switch_world.application.scene`. This module keeps the historical public
name, signature and return shape for the director CLI and older callers, and
re-exports the planning helpers other modules import.

New code should call ``switch_world.application.scene.say_in_group`` with a
transport from the composition root; this shim exists until step 10.
"""
from __future__ import annotations

import time

from world_engine.service import WorldService

from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.application.group_planning import (  # noqa: F401  (re-exports)
    BOUNDARY_CONFIDENCE,
    BOUNDARY_KEY,
    BOUNDARY_REACTIONS,
    CHORUS_TOPICS,
    DEFAULT_CHARACTERS,
    INTIMATE_TOPICS,
    MAX_MESSAGE,
    PLACEHOLDERS,
    TURN_CAP_SECONDS,
    _affinity,
    _agent_mentions,
    _beat_mode,
    _boundary_target,
    _clean_character,
    _expression,
    _is_shared_fact,
    _limit_words,
    _memory_lines,
    _metadata,
    _named_addressee,
    _plan_summary,
    _prompt_for,
    _recent_scene_lines,
    _relay_prompt,
    _role_for,
    _role_instruction,
    _sanitise_reply,
    _speakers,
    _strip_meta,
    _tension,
    _turn_id,
    plan_turn,
)
from switch_world.application.scene import say_in_group as _say_in_group

from .switch_client import SwitchClient, SwitchError

__all__ = [
    "BOUNDARY_CONFIDENCE",
    "BOUNDARY_KEY",
    "BOUNDARY_REACTIONS",
    "CHORUS_TOPICS",
    "DEFAULT_CHARACTERS",
    "INTIMATE_TOPICS",
    "MAX_MESSAGE",
    "PLACEHOLDERS",
    "SwitchClient",
    "SwitchError",
    "TURN_CAP_SECONDS",
    "plan_turn",
    "say_in_group",
]


def say_in_group(
    service: WorldService,
    message: str,
    characters: list[str] | None = None,
    switch: SwitchClient | None = None,
    room_name: str = "world",
    timeout: float = TURN_CAP_SECONDS,
    arbiter_client=None,
) -> dict:
    """Post one user line to the room and collect the planned speakers' replies.

    Kept as a shim over :func:`switch_world.application.scene.say_in_group`.
    ``switch`` accepts any legacy object with ``find_room`` / ``post`` /
    ``history``; ``None`` builds the historical ``SwitchClient`` so existing
    tooling and tests that patch it keep working. New code injects a
    :class:`~switch_world.domain.ports.transport.CharacterTransport` instead.
    """
    if switch is None:
        # Defer construction until the room is actually opened: validation and
        # the empty-room path must not need Switch credentials.
        transport = LegacySwitchTransport(
            client_factory=SwitchClient, time_source=time
        )
    else:
        transport = LegacySwitchTransport(switch, time_source=time)
    return _say_in_group(
        service,
        message,
        characters,
        transport=transport,
        room_name=room_name,
        timeout=timeout,
        arbiter_client=arbiter_client,
        time_source=time,
    )
