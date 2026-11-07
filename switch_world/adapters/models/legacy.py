"""Compatibility model client over a legacy ``chat_json`` object.

The pre-v2 DM and whisper clients expose ``chat_json(character, messages,
reasoning=...)`` and ``usage_summary()``. This adapter narrows that surface to
:class:`~switch_world.domain.ports.model.ModelClient` so the application can
call ``generate`` and never depend on the legacy class. It is a bridge only:
production code injects a real adapter (Bifrost or DeepSeek).
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    Message,
    ModelFormat,
    ModelReply,
    UsageSummary,
)

from ._support import wire_messages


class LegacyModelClient:
    """A :class:`ModelClient` over an object with ``chat_json`` / ``usage_summary``."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def generate(
        self,
        character: CharacterId,
        messages: Sequence[Message | Mapping[str, Any]],
        *,
        format: ModelFormat = ModelFormat.JSON,
        reasoning: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelReply:
        kwargs: dict[str, Any] = {}
        if reasoning is not None:
            kwargs["reasoning"] = reasoning
        data = self._client.chat_json(
            str(character), wire_messages(messages), **kwargs
        )
        if isinstance(data, Mapping):
            return ModelReply(
                text=json.dumps(dict(data), ensure_ascii=False),
                data=dict(data),
                model="legacy",
            )
        # A non-object answer is left in ``text``; the envelope parser raises
        # the same ValueError HEAD raised for it.
        return ModelReply(
            text="" if data is None else str(data),
            data=None,
            model="legacy",
        )

    def usage(self, character: CharacterId | None = None) -> UsageSummary:
        summary = self.usage_summary()
        if not isinstance(summary, Mapping):
            return UsageSummary()
        if character is not None:
            wanted = str(character)
            characters = summary.get("characters")
            if isinstance(characters, Mapping):
                entry = characters.get(wanted)
                if isinstance(entry, Mapping):
                    total = int(entry.get("used_tokens") or 0)
                    return UsageSummary(total_tokens=total)
            return UsageSummary()
        return UsageSummary(
            prompt_tokens=int(summary.get("prompt_tokens") or 0),
            completion_tokens=int(summary.get("completion_tokens") or 0),
            total_tokens=int(summary.get("total_tokens") or 0),
            requests=int(summary.get("requests") or 0),
        )

    def usage_summary(self) -> Any:
        """The legacy block, unchanged, so a caller's return shape is preserved."""
        summary = getattr(self._client, "usage_summary", None)
        if not callable(summary):
            return {}
        value = summary()
        return dict(value) if isinstance(value, Mapping) else value


__all__ = ["LegacyModelClient"]
