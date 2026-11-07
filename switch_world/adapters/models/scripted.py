"""Deterministic model client for tests and demos.

``ScriptedModelClient`` answers from a per-character script. Every call is
recorded so a test can assert the messages and sampling kwargs that the
application passed. A script entry may be:

* a string (plain text, or JSON when ``format=JSON``),
* a mapping (returned as parsed JSON data),
* a :class:`ScriptedTurn` (explicit usage or data), or
* an exception instance (raised unchanged).
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    Message,
    ModelBudgetExceeded,
    ModelError,
    ModelFormat,
    ModelReply,
    Usage,
    UsageSummary,
)

from ._support import as_format, message_text, parse_json_object

DEFAULT_DAILY_TOKENS = 60_000


@dataclass(frozen=True)
class ScriptedTurn:
    """One scripted reply, with optional explicit usage."""

    text: str | None = None
    data: Mapping[str, Any] | None = None
    usage: Usage | None = None
    error: BaseException | None = None


@dataclass(frozen=True)
class ScriptedCall:
    """A record of one ``generate`` call."""

    character: str
    messages: tuple[Message | Mapping[str, Any], ...]
    format: ModelFormat
    reasoning: str | None
    temperature: float | None
    max_tokens: int | None


class ScriptedModelClient:
    """A deterministic :class:`ModelClient` implementation."""

    def __init__(
        self,
        script: Mapping[str, Any] | None = None,
        *,
        default: Any = ScriptedTurn(
            text="scripted reply", data={"reply": "scripted reply"}
        ),
        daily_tokens: int | Mapping[str, int] | None = None,
    ) -> None:
        self._script: dict[str, list[Any]] = {
            character: list(value) if isinstance(value, (list, tuple)) else [value]
            for character, value in (script or {}).items()
        }
        self.default = default
        self.daily_tokens = daily_tokens
        self._indices: dict[str, int] = {}
        self._used: dict[str, Usage] = {}
        self._requests: dict[str, int] = {}
        self.calls: list[ScriptedCall] = []

    # ---- model client -----------------------------------------------------
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
        fmt = as_format(format)
        name = str(character)
        self.calls.append(
            ScriptedCall(
                character=name,
                messages=tuple(messages),
                format=fmt,
                reasoning=reasoning,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        limit = self._limit(name)
        if limit is not None and self._used.get(name, Usage()).total_tokens >= limit:
            used = self._used.get(name, Usage()).total_tokens
            raise ModelBudgetExceeded(
                f"{name} has used {used}/{limit} scripted tokens today"
            )

        entry = self._next(name)
        if isinstance(entry, ScriptedTurn):
            if entry.error is not None:
                raise self._as_model_error(name, entry.error)
            text, data, explicit_usage = entry.text, entry.data, entry.usage
        elif isinstance(entry, BaseException):
            raise self._as_model_error(name, entry)
        elif isinstance(entry, Mapping):
            text, data, explicit_usage = None, dict(entry), None
        elif isinstance(entry, str):
            text, data, explicit_usage = entry, None, None
        else:
            raise TypeError(f"unsupported scripted reply: {type(entry).__name__}")

        if fmt is ModelFormat.JSON:
            if data is None:
                if not text or not text.strip():
                    raise ModelError(f"{name} scripted an empty reply")
                data = parse_json_object(text)
            elif not text:
                text = json.dumps(data, ensure_ascii=False)
        else:
            if text is None:
                if data is None:
                    raise ModelError(f"{name} scripted an empty reply")
                text = json.dumps(data, ensure_ascii=False)
            data = None

        if not text.strip():
            raise ModelError(f"{name} scripted an empty reply")

        usage = explicit_usage or self._estimate_usage(messages, text)
        self._add_usage(name, usage)
        return ModelReply(
            text=text,
            data=data,
            usage=usage,
            model="scripted",
            raw={"scripted": True},
        )

    def usage(self, character: CharacterId | None = None) -> UsageSummary:
        if character is not None:
            name = str(character)
            usage = self._used.get(name, Usage())
            return UsageSummary(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                requests=self._requests.get(name, 0),
            )
        return UsageSummary(
            prompt_tokens=sum(usage.prompt_tokens for usage in self._used.values()),
            completion_tokens=sum(
                usage.completion_tokens for usage in self._used.values()
            ),
            total_tokens=sum(usage.total_tokens for usage in self._used.values()),
            requests=sum(self._requests.values()),
        )

    # ---- internals --------------------------------------------------------
    @staticmethod
    def _as_model_error(character: str, error: BaseException) -> BaseException:
        """Keep typed errors; wrap other ``Exception`` values for the contract."""
        if isinstance(error, ModelError):
            return error
        if isinstance(error, Exception):
            wrapped = ModelError(f"{character} scripted model error: {error}")
            wrapped.__cause__ = error
            return wrapped
        return error

    def _next(self, character: str) -> Any:
        turns = self._script.get(character)
        if not turns:
            return self.default
        index = self._indices.get(character, 0)
        self._indices[character] = index + 1
        return turns[min(index, len(turns) - 1)]

    def _limit(self, character: str) -> int | None:
        if self.daily_tokens is None:
            return None
        if isinstance(self.daily_tokens, Mapping):
            return int(self.daily_tokens.get(character, DEFAULT_DAILY_TOKENS))
        return int(self.daily_tokens)

    @staticmethod
    def _estimate_usage(
        messages: Sequence[Message | Mapping[str, Any]], text: str
    ) -> Usage:
        prompt = len(message_text(messages).split())
        completion = len(text.split())
        return Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    def _add_usage(self, character: str, usage: Usage) -> None:
        previous = self._used.get(character, Usage())
        self._used[character] = Usage(
            prompt_tokens=previous.prompt_tokens + usage.prompt_tokens,
            completion_tokens=previous.completion_tokens + usage.completion_tokens,
            total_tokens=previous.total_tokens + usage.total_tokens,
        )
        self._requests[character] = self._requests.get(character, 0) + 1


__all__ = ["ScriptedCall", "ScriptedModelClient", "ScriptedTurn"]
