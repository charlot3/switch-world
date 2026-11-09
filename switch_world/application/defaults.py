"""Default model factories for callers with no composition root.

The composition root injects adapters explicitly. These factories keep the
historical lazy selection (``WORLD_AGENT_MODE=cloud`` -> DeepSeek, otherwise
Bifrost) for the compatibility shims in ``switch_world.compat``.
"""
from __future__ import annotations

import os
from pathlib import Path

from switch_world.adapters.models.cloud_bifrost import CloudBifrost
from switch_world.adapters.models.deepseek import DeepSeekModelClient
from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.config import load_settings

# The lazily resolved process settings; tests patch
# ``switch_world.config.AGENT_MODE`` / ``DATA_DIR``.
from switch_world import config


def _agent_mode() -> str:
    return str(getattr(config, "AGENT_MODE", "switch")).strip().lower()


def default_dm_model():
    """The model ``switch_world.compat.reply_to_dm`` builds from process settings."""
    data_dir = Path(config.DATA_DIR)
    if _agent_mode() == "cloud":
        return DeepSeekModelClient(
            budget_path=data_dir / "deepseek_budget.json",
            log_path=data_dir / "logs" / "deepseek.jsonl",
        )
    from switch_world.adapters.models import BifrostModelClient

    return BifrostModelClient(
        log_path=data_dir / "logs" / "bifrost.jsonl",
        budget_path=data_dir / "bifrost_budget.json",
        models_path=load_settings(os.environ).content_root / "models.json",
    )


def default_whisper_model() -> LegacyModelClient:
    """The model ``switch_world.compat.whisper_to_character`` builds from settings."""
    if _agent_mode() == "cloud":
        return LegacyModelClient(CloudBifrost())
    from switch_world.adapters.models.bifrost_compat import BifrostClient

    return LegacyModelClient(BifrostClient())


def cloud_room_transport(model):
    """An in-band room for a model-backed discussion with no transport injected.

    ``prepare_briefing`` accepts either a transport or a model. When the caller
    supplies only a model, this wraps it in the same in-band transport the cloud
    and Bifrost composition roots use, so the use case never names the adapter.
    """
    from switch_world.adapters.transports import CloudRoomTransport

    return CloudRoomTransport(model)


def default_artifact_store(export_dir=None):
    """The filesystem artifact store under the process export directory."""
    from switch_world.adapters.artifacts.files import FileArtifactStore

    return FileArtifactStore(Path(export_dir) if export_dir else Path(config.EXPORT_DIR))


__all__ = [
    "cloud_room_transport",
    "default_artifact_store",
    "default_dm_model",
    "default_whisper_model",
]
