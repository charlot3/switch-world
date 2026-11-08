"""The last compatibility edge for legacy-shaped callers.

The v2 application talks in ports: ``scene.say_in_group`` takes a
:class:`~switch_world.domain.ports.transport.CharacterTransport`,
``scene.dm`` / ``scene.whisper`` take a
:class:`~switch_world.domain.ports.model.ModelClient`. A few tests, the
dev-gated HTTP branch and older tooling still hand in a Switch-shaped object
(``find_room`` / ``post`` / ``history``) or a ``chat_json`` client instead.

This module is the single adapter that narrows those legacy objects onto the
ports. It lives outside ``domain/``, ``application/`` and ``adapters/`` on
purpose: it is an edge, not part of the architecture, and it disappears when
the last legacy-shaped caller is gone.
"""
from __future__ import annotations

import time

from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.adapters.transports.switch_client import SwitchClient, SwitchError
from switch_world.application.defaults import (
    default_dm_model as _default_dm_model,
    default_whisper_model as _default_whisper_model,
)
from switch_world.application.facade import WorldService
from switch_world.application.group_planning import TURN_CAP_SECONDS
from switch_world.application.scene import (
    MAX_MESSAGE,
    dm as _dm,
    say_in_group as _say_in_group,
    whisper as _whisper,
)

__all__ = [
    "MAX_MESSAGE",
    "SwitchClient",
    "SwitchError",
    "TURN_CAP_SECONDS",
    "reply_to_dm",
    "say_in_group",
    "whisper_to_character",
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

    ``switch`` accepts any legacy object with ``find_room`` / ``post`` /
    ``history``; ``None`` builds the historical ``SwitchClient`` lazily so
    validation and the empty-room path never need Switch credentials.
    """
    if switch is None:
        transport = LegacySwitchTransport(client_factory=SwitchClient, time_source=time)
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


def reply_to_dm(
    service: WorldService,
    character: str,
    message: str,
    client=None,
) -> dict:
    """Post one private DM and return the historical DM result shape.

    ``client`` accepts a legacy ``chat_json`` object, a
    :class:`~switch_world.domain.ports.model.ModelClient`, or ``None`` to build
    one from ``AGENT_MODE`` exactly as HEAD did.
    """
    if client is None:
        return _dm(service, character, message, model_factory=_default_dm_model)
    if callable(getattr(client, "generate", None)):
        model = client
    else:
        model = LegacyModelClient(client)
    return _dm(service, character, message, model)


def whisper_to_character(
    service: WorldService,
    to: str,
    message: str,
    client=None,
    switch=None,
    timeout: float = 35.0,
) -> dict:
    """Whisper privately to one character and return the historical result shape.

    A legacy ``chat_json`` client is wrapped in
    :class:`~switch_world.adapters.models.legacy.LegacyModelClient`; a legacy
    Switch object is wrapped in
    :class:`~switch_world.adapters.transports.legacy.LegacySwitchTransport`.
    With neither, the default model is built lazily exactly as HEAD did, and
    only when the staged path actually needs it.
    """
    model = None
    if client is not None:
        if callable(getattr(client, "generate", None)):
            model = client
        else:
            model = LegacyModelClient(client)
    transport = LegacySwitchTransport(switch) if switch is not None else None
    return _whisper(
        service,
        to,
        message,
        model=model,
        transport=transport,
        timeout=timeout,
        model_factory=_default_whisper_model if model is None else None,
    )
