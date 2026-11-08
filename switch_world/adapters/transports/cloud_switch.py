"""Cloud (DeepSeek) room adapter with the historical Switch-shaped surface.

This is the room half of the deleted v1 ``director/cloud_switch.py``: a drop-in
object for ``switch_world.application.scene.say_in_group`` (through
``switch_world.compat``) backed by DeepSeek. It is kept for the compatibility
shims while callers migrate to
:class:`switch_world.adapters.transports.CloudRoomTransport`.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path

from switch_world.adapters.models.cloud_bifrost import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    VOICE,
    _build_model,
    _transport_for,
)
from switch_world.config import load_settings
from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    Message,
    ModelFormat,
)

logger = logging.getLogger(__name__)


def _identity(character: str, limit: int = 3200) -> str:
    """Read one character identity from the injected content root."""
    path = Path(load_settings(os.environ).agents_dir) / character / "IDENTITY.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]

class CloudSwitch:
    """Drop-in room for ``switch_world.application.scene.say_in_group`` backed by DeepSeek."""

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
            max_tokens=int(os.environ.get("WORLD_CLOUD_MAX_TOKENS", "700")),
        )
        self.room = {
            "room_id": "cloud-world",
            "name": "world",
            "description": "Guest demo room",
            "connected": True,
            "archived": False,
        }
        self._events: list[dict] = []
        self._last_ts = 0
        self._turn_cutoff = 0

    # -- SwitchClient surface ------------------------------------------------

    def find_room(self, name: str = "world") -> dict:
        # `say_in_group` resolves the room once at the start of every turn.
        # Everything older than that belongs to a previous turn and must not be
        # mistaken for this turn's reply.
        self._turn_cutoff = max(int(time.time() * 1000), self._last_ts)
        return {**self.room, "name": name}

    def post(self, room_id: str, content: str) -> dict:
        text = (content or "").strip()
        match = re.match(r"@([A-Za-z0-9_]+)\s+(.*)", text, re.S)
        if not match:
            return {}
        character = match.group(1).lower()
        prompt = match.group(2).strip()
        # Unique per turn: the recorder treats a repeated message id as an
        # already-recorded event and would drop the whole reply.
        event_id = f"cloud-{uuid.uuid4().hex}"
        try:
            reply = self._answer(character, prompt)
        except Exception as exc:  # a dead model must not erase the user's turn
            logger.warning("cloud reply failed for %s: %s", character, exc)
            reply = ""
        if not reply:
            # No event: the planned speaker becomes a recorded silence.
            return {"event_id": event_id, "empty": True}
        timestamp = max(int(time.time() * 1000), self._last_ts + 1)
        self._last_ts = timestamp
        self._events.append(
            {
                "event_id": event_id,
                "sender_name": character,
                "timestamp": timestamp,
                "body": reply,
            }
        )
        return {"event_id": event_id}

    def history(self, room_id: str) -> list[dict]:
        return [event for event in self._events if event["timestamp"] > self._turn_cutoff]

    # -- model ---------------------------------------------------------------

    def _system(self, character: str) -> str:
        identity = _identity(character, limit=2400)
        return f"You are {character.title()}, a character in a small interactive-fiction world.\n\n{identity}\n\n{VOICE}"

    def _answer(self, character: str, prompt: str) -> str:
        reply = self._model.generate(
            CharacterId(character),
            [
                Message("system", self._system(character)),
                Message("user", prompt),
            ],
            format=ModelFormat.TEXT,
            reasoning=self.reasoning,
        )
        return (reply.text or "").strip()




__all__ = ["CloudSwitch"]
