"""The composition root: settings in, constructed objects out.

Deliberately framework-free. Importing this module builds nothing; only
calling :func:`build_container` creates clients and opens the world store.

The transport and model are resolved here from ``Settings.agent_mode`` and
injected into the HTTP app, so no route constructs a provider client:

* ``switch`` -- :class:`SwitchTransport` carrying prompts to live agents;
* ``cloud``  -- :class:`CloudRoomTransport` over :class:`DeepSeekModelClient`;
* ``bifrost`` -- :class:`CloudRoomTransport` over :class:`BifrostModelClient`,
  so group, DM, whisper and beat calls all go through the Bifrost gateway;
* ``local``  -- :class:`LocalRoomTransport` for the scripted demo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from switch_world.adapters.artifacts.files import FileArtifactStore
from switch_world.adapters.clock import SystemClock
from switch_world.adapters.models import BifrostModelClient, DeepSeekModelClient
from switch_world.adapters.transports import (
    CloudRoomTransport,
    LocalRoomTransport,
    SwitchTransport,
)
from switch_world.config import Settings
from switch_world.domain.ports.artifacts import ArtifactStore
from switch_world.domain.ports.model import ModelClient
from switch_world.domain.ports.transport import CharacterTransport
from switch_world.application.facade import WorldService


@dataclass
class Container:
    settings: Settings
    service: WorldService
    transport: CharacterTransport | None = None
    model: ModelClient | None = None
    clock: SystemClock | None = None
    artifacts: ArtifactStore | None = None

    def close(self) -> None:
        """Release any transport-owned resources (HTTP pools, workers)."""
        closer = getattr(self.transport, "close", None)
        if callable(closer):
            closer()


def _switch_credentials(settings: Settings) -> dict[str, str]:
    """Settings first, then the historical director credentials file."""
    creds = {
        "base_url": settings.switch_base_url,
        "agent_id": settings.switch_agent_id,
        "token": settings.switch_token,
    }
    if creds["token"]:
        return creds
    path = Path(settings.root) / ".switch" / "agents" / "director.json"
    if not path.exists():
        return creds
    try:
        env = json.loads(path.read_text(encoding="utf-8")).get("env", {})
    except (OSError, ValueError):
        return creds
    return {
        "base_url": env.get("SWITCH_API_ENDPOINT") or creds["base_url"],
        "agent_id": env.get("SWITCH_AGENT_ID") or creds["agent_id"],
        "token": env.get("SWITCH_API_TOKEN") or creds["token"],
    }


def build_container(settings: Settings) -> Container:
    """Construct the object graph the HTTP app needs today."""
    service = WorldService(
        db_path=settings.db_path,
        state_dir=settings.state_dir,
        tokens=settings.token_map(),
    )
    clock = SystemClock()
    mode = (settings.agent_mode or "switch").strip().lower()

    transport: CharacterTransport
    model: ModelClient
    if mode == "switch":
        creds = _switch_credentials(settings)
        transport = SwitchTransport(
            client=httpx.Client(),
            agent_id=creds["agent_id"],
            token=creds["token"],
            base_url=creds["base_url"],
            clock=clock,
            own_client=True,
        )
        model = BifrostModelClient(
            log_path=settings.data_dir / "logs" / "bifrost.jsonl",
            budget_path=settings.data_dir / "bifrost_budget.json",
            models_path=settings.content_root / "models.json",
        )
    elif mode == "cloud":
        model = DeepSeekModelClient(
            api_key=settings.cloud_api_key or None,
            base_url=settings.cloud_base_url,
            model=settings.cloud_model,
            clock=clock,
            budget_path=settings.data_dir / "deepseek_budget.json",
            log_path=settings.data_dir / "logs" / "deepseek.jsonl",
        )
        transport = CloudRoomTransport(model, clock=clock)
    elif mode == "bifrost":
        # One gateway for every character call. The per-character model,
        # fallbacks, temperature, budget and reasoning come from
        # ``world/models.json``; no DeepSeek key is needed here because Bifrost
        # owns the provider credentials.
        model = BifrostModelClient(
            base_url=settings.bifrost_url,
            api_key=settings.bifrost_api_key or None,
            models_path=(
                settings.bifrost_models_path
                or settings.content_root / "models.json"
            ),
            log_path=settings.data_dir / "logs" / "bifrost.jsonl",
            budget_path=settings.data_dir / "bifrost_budget.json",
        )
        transport = CloudRoomTransport(
            model, clock=clock, name="bifrost", room_prefix="bifrost"
        )
    elif mode == "local":
        transport = LocalRoomTransport(clock=clock)
        model = BifrostModelClient(
            log_path=settings.data_dir / "logs" / "bifrost.jsonl",
            budget_path=settings.data_dir / "bifrost_budget.json",
            models_path=settings.content_root / "models.json",
        )
    else:
        raise ValueError(
            "WORLD_AGENT_MODE must be one of switch, cloud, bifrost, local "
            f"(got {settings.agent_mode!r})"
        )

    return Container(
        settings=settings,
        service=service,
        transport=transport,
        model=model,
        clock=clock,
        artifacts=FileArtifactStore(settings.export_dir),
    )


__all__ = ["Container", "build_container"]
