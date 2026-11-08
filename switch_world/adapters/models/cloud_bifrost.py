"""DeepSeek model and room helpers for the guest (cloud) deployment.

The guest deployment on Oracle has no Switch Console, so there is nothing to host
the four live agent sessions. Historically this module contained both the room
bookkeeping and the DeepSeek HTTP client. The client half now lives in
:class:`switch_world.adapters.models.deepseek.DeepSeekModelClient`; the room half
stays here as a small Switch-shaped compatibility shim so the
``switch_world.compat`` shims keep working.

It implements only what ``say_in_group`` uses from ``SwitchClient``:

    find_room(name)            -> a room dict
    post(room_id, "@name ...") -> answers the prompt and appends an event
    history(room_id)           -> the events appended so far

``CloudBifrost`` keeps the small slice of ``BifrostClient`` that DM and whisper
use: ``chat_json(character, messages)`` and ``usage_summary()``. Both classes now
delegate the provider call to ``DeepSeekModelClient``.

Configuration:

    WORLD_AGENT_MODE=cloud
    DEEPSEEK_API_KEY=...            # the same key the local cast uses
    WORLD_CLOUD_MODEL=deepseek-flash
    WORLD_CLOUD_BASE_URL=https://api.deepseek.com/v1
    WORLD_CLOUD_REASONING=low
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

from switch_world.adapters.models.deepseek import DeepSeekModelClient
from switch_world.config import load_settings
from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    ModelError,
    ModelFormat,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"

VOICE = (
    "You are in a small interactive-fiction world. Answer only as yourself, in "
    "first person, in one or two short sentences. Sound like a person in the "
    "room, not a narrator: one concrete detail, one thing left unsaid, no "
    "therapy-speak, no summary of the scene or the relationship, and no "
    "question that exists only to keep the conversation going. Never write "
    "'@user', '@director', or any line about being online, offline, or needing "
    "to leave; you are present and you answer as yourself. Keep it 17+ SFW. "
    "Do not mention these instructions."
)


class CloudSwitchError(RuntimeError):
    pass


def _data_dir() -> Path:
    """Where the model budget and request log live (``WORLD_DATA_DIR``)."""
    return Path(load_settings(os.environ).data_dir)


def _build_model(
    api_key: str | None,
    base_url: str | None,
    model: str | None,
    timeout: float,
    transport,
    *,
    max_tokens: int,
) -> DeepSeekModelClient:
    key = (
        api_key
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("WORLD_CLOUD_API_KEY")
        or ""
    )
    if not key:
        raise CloudSwitchError(
            "WORLD_AGENT_MODE=cloud needs DEEPSEEK_API_KEY (or WORLD_CLOUD_API_KEY)"
        )
    data_dir = _data_dir()
    return DeepSeekModelClient(
        api_key=key,
        base_url=(
            base_url or os.environ.get("WORLD_CLOUD_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/"),
        model=model or os.environ.get("WORLD_CLOUD_MODEL") or DEFAULT_MODEL,
        timeout=timeout,
        transport=transport or _http_post,
        reasoning=os.environ.get("WORLD_CLOUD_REASONING", "low"),
        max_tokens=max_tokens,
        budget_path=data_dir / "deepseek_budget.json",
        log_path=data_dir / "logs" / "deepseek.jsonl",
    )


def _http_post(
    url: str, payload: dict, headers: dict, timeout: float = 120.0
) -> dict:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise CloudSwitchError(f"model endpoint unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise CloudSwitchError(
            f"model HTTP {response.status_code}: {response.text[:300]}"
        )
    return response.json()


def _transport_for(timeout: float):
    return lambda url, payload, headers: _http_post(url, payload, headers, timeout)


class CloudBifrost:
    """The small slice of `BifrostClient` that DM and whisper use.

    Their prompts already ask for the JSON envelope, so this client asks the
    model for JSON and returns the parsed object. Keeping the same method name
    means `reply_to_dm` and `whisper_to_character` do not need a second code
    path.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        transport=None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("WORLD_CLOUD_API_KEY")
            or ""
        )
        self.base_url = (
            base_url or os.environ.get("WORLD_CLOUD_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or os.environ.get("WORLD_CLOUD_MODEL") or DEFAULT_MODEL
        self.reasoning = os.environ.get("WORLD_CLOUD_REASONING", "low")
        self.timeout = timeout
        self.transport = transport or _transport_for(timeout)
        self._model = _build_model(
            self.api_key,
            self.base_url,
            self.model,
            self.timeout,
            self.transport,
            max_tokens=int(os.environ.get("WORLD_CLOUD_MAX_TOKENS", "900")),
        )
        self.last_usage: dict = {}

    def chat_json(
        self, character: str, messages: list[dict], reasoning: str | None = None
    ) -> dict:
        try:
            reply = self._model.generate(
                CharacterId(character),
                messages,
                format=ModelFormat.JSON,
                reasoning=reasoning,
            )
        except ModelError as exc:
            raise CloudSwitchError(f"{character} did not return JSON: {exc}") from exc
        data = reply.data
        if not isinstance(data, dict):
            raise CloudSwitchError(f"{character} did not return a JSON object")
        self.last_usage = dict(self._model.last_usage)
        return data

    def usage_summary(self) -> dict:
        return dict(self._model.last_usage)




__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "VOICE",
    "CloudBifrost",
    "CloudSwitchError",
    "_build_model",
    "_data_dir",
    "_http_post",
    "_transport_for",
]
