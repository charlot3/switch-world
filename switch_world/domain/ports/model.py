"""Model client contract.

A model client turns a conversation into one character reply. The same
``generate`` call serves plain text and JSON envelopes; callers choose with
:class:`ModelFormat`. There is no provider-specific code in this module.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

from ..ids import CharacterId


class ModelFormat(StrEnum):
    """Wire format requested from the provider."""

    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class Message:
    """One chat message, in provider-neutral form."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    """Token counts for one model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class UsageSummary:
    """Cumulative usage, optionally for one character."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0


@dataclass(frozen=True)
class ModelReply:
    """A parsed model reply.

    ``text`` is always the provider's text content. ``data`` is populated only
    when JSON was requested and parsed successfully.
    """

    text: str
    data: dict[str, Any] | None = None
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)


class ModelError(RuntimeError):
    """A model call failed or returned something unusable.

    Adapters must raise this (or a subclass) instead of returning an empty
    reply: an empty string would be indistinguishable from a recorded silence.
    """


class ModelBudgetExceeded(ModelError):
    """The per-character daily token budget is already spent."""


class ModelClient(Protocol):
    """The single model surface used by the application."""

    def generate(
        self,
        character: CharacterId,
        messages: Sequence[Message],
        *,
        format: ModelFormat = ModelFormat.JSON,
        reasoning: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelReply: ...

    def usage(self, character: CharacterId | None = None) -> UsageSummary: ...


__all__ = [
    "Message",
    "ModelBudgetExceeded",
    "ModelClient",
    "ModelError",
    "ModelFormat",
    "ModelReply",
    "Usage",
    "UsageSummary",
]
