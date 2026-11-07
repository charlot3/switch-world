"""Compatibility shim: a private DM through the application pipeline.

The DM itself now lives in :mod:`switch_world.application.scene.dm`. This
module keeps the historical public name, signature and return shape for the
dashboard route, the director CLI and older callers, and resolves the model
client the old module used to build for itself:

* ``cloud`` -- :class:`DeepSeekModelClient`;
* otherwise -- :class:`BifrostModelClient`.

A caller-supplied legacy ``chat_json`` client is wrapped in
:class:`LegacyModelClient`; a real :class:`ModelClient` is passed straight
through. New code should inject the model from the composition root and call
``switch_world.application.scene.dm`` directly; this shim disappears in step
10.
"""
from __future__ import annotations

from pathlib import Path

from world_engine.service import WorldService

from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.application.scene import MAX_MESSAGE, dm as _dm

__all__ = ["MAX_MESSAGE", "reply_to_dm"]


def _default_model():
    """Build the model the old module built lazily, selected by agent mode."""
    from world_engine import config

    data_dir = config.DATA_DIR
    if str(getattr(config, "AGENT_MODE", "switch")).strip().lower() == "cloud":
        from switch_world.adapters.models import DeepSeekModelClient

        return DeepSeekModelClient(
            budget_path=data_dir / "deepseek_budget.json",
            log_path=data_dir / "logs" / "deepseek.jsonl",
        )
    from switch_world.adapters.models import BifrostModelClient

    return BifrostModelClient(
        log_path=data_dir / "logs" / "bifrost.jsonl",
        budget_path=data_dir / "bifrost_budget.json",
        models_path=Path(config.CONTENT_ROOT) / "models.json",
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
    one from ``AGENT_MODE`` exactly as HEAD did. The default client is built by
    a factory inside the use case, so an invalid message or character is
    rejected before any provider client (or credential check) is constructed.
    """
    if client is None:
        return _dm(service, character, message, model_factory=_default_model)
    if callable(getattr(client, "generate", None)):
        model = client
    else:
        model = LegacyModelClient(client)
    return _dm(service, character, message, model)
