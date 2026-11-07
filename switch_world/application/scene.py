"""Scene use cases.

Step 4 ports the group turn only. DM and whisper keep their existing modules
until step 5; both already apply the same policy and writes by hand, so
nothing here is shared with them yet.
"""
from __future__ import annotations

from typing import Any

from director import social
from world_engine.service import WorldService

from switch_world.domain.ports.transport import CharacterTransport

from .group_planning import (
    DEFAULT_CHARACTERS,
    MAX_MESSAGE,
    TURN_CAP_SECONDS,
    _boundary_target,
    _clean_character,
    _turn_id,
    plan_turn,
)
from .turns import TurnRecorder


def resolve_cast(service: WorldService, characters: list[str] | None) -> list[str]:
    """The requested cast, or the active scene's cast, de-duplicated."""
    if characters is None:
        state = service.state()
        scene = state.get("scene") or {}
        cast = (
            scene.get("cast")
            or (state.get("scenario") or {}).get("cast")
            or list(DEFAULT_CHARACTERS)
        )
        requested = [_clean_character(c) for c in cast]
    else:
        requested = [_clean_character(c) for c in characters]
    return list(dict.fromkeys(requested))


def say_in_group(
    service: WorldService,
    message: str,
    characters: list[str] | None = None,
    transport: CharacterTransport | None = None,
    room_name: str = "world",
    timeout: float = TURN_CAP_SECONDS,
    arbiter_client: Any | None = None,
    *,
    time_source: Any | None = None,
) -> dict:
    """Post one user line to the group room and record the planned replies.

    ``transport`` is injected by the composition root; this use case never
    constructs one. The return shape is the legacy group-turn shape.
    """
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    if len(message) > MAX_MESSAGE:
        raise ValueError(f"message is too long (max {MAX_MESSAGE} characters)")
    if transport is None:
        raise ValueError("transport is required")

    requested = resolve_cast(service, characters)
    # Presence is part of the scene: a character who left is not addressed or posted to.
    present = [c for c in requested if not service.is_absent(c)]
    verdicts = {
        character: social.appraise(service, character, message, public=True)
        for character in present
    }
    turn_id = _turn_id()
    recorder = TurnRecorder(
        service,
        transport,
        room_name=room_name,
        time_source=time_source,
    )

    boundary_target = (
        _boundary_target(message, present, verdicts) if present else None
    )
    if boundary_target:
        return recorder.record_boundary(
            message, present, verdicts, boundary_target, turn_id
        )

    plan = plan_turn(message, present, verdicts, service=service)
    return recorder.record_turn(
        message,
        present,
        verdicts,
        plan,
        turn_id,
        timeout=timeout,
        arbiter_client=arbiter_client,
    )


__all__ = ["resolve_cast", "say_in_group"]
