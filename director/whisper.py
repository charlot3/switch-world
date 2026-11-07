"""Compatibility shim: a whisper through the application pipeline.

The whisper itself now lives in :mod:`switch_world.application.scene.whisper`.
This module keeps the historical public name, signature and return shape for
the dashboard route and older callers, and resolves the legacy objects the old
module used to build for itself:

* a caller-supplied ``chat_json`` client is wrapped in
  :class:`~switch_world.adapters.models.legacy.LegacyModelClient`;
* a caller-supplied legacy Switch object is wrapped in
  :class:`~switch_world.adapters.transports.legacy.LegacySwitchTransport`, whose
  capabilities report a private room when the backend exposes
  ``find_private_room``;
* with neither, the default model is built lazily exactly as HEAD did, and only
  when the staged path actually needs it.

New code should inject a :class:`~switch_world.domain.ports.model.ModelClient`
and a :class:`~switch_world.domain.ports.transport.CharacterTransport` into
``switch_world.application.scene.whisper``; this shim disappears in step 10.
"""
from __future__ import annotations

from world_engine.service import WorldService

from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.application.scene import MAX_MESSAGE, whisper as _whisper

__all__ = ["MAX_MESSAGE", "whisper_to_character"]


def _default_model() -> LegacyModelClient:
    """Build the model the old module built lazily, selected by agent mode."""
    from world_engine import config

    if str(getattr(config, "AGENT_MODE", "switch")).strip().lower() == "cloud":
        from .cloud_switch import CloudBifrost

        return LegacyModelClient(CloudBifrost())
    from gateway.bifrost import BifrostClient

    return LegacyModelClient(BifrostClient())


def whisper_to_character(
    service: WorldService,
    to: str,
    message: str,
    client=None,
    switch=None,
    timeout: float = 35.0,
) -> dict:
    """Whisper privately to one character and return the historical result shape.

    ``client`` accepts a legacy ``chat_json`` object, a
    :class:`~switch_world.domain.ports.model.ModelClient`, or ``None`` to build
    one from ``AGENT_MODE`` when the staged path needs it. ``switch`` accepts a
    legacy Switch client; when it can provide a private room, the whisper uses
    it and no model is constructed.
    """
    model = None
    if client is not None:
        if callable(getattr(client, "generate", None)):
            model = client
        else:
            model = LegacyModelClient(client)
    transport = (
        LegacySwitchTransport(switch) if switch is not None else None
    )
    return _whisper(
        service,
        to,
        message,
        model=model,
        transport=transport,
        timeout=timeout,
        model_factory=_default_model if model is None else None,
    )
