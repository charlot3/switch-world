"""Shared parsing and wiring helpers for model adapters."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from switch_world.domain.ports.model import Message, ModelError, ModelFormat, Usage


def as_format(value: ModelFormat | str) -> ModelFormat:
    """Coerce a caller-supplied format, with a clear error on a typo."""
    if isinstance(value, ModelFormat):
        return value
    try:
        return ModelFormat(str(value))
    except ValueError as exc:
        raise ValueError(
            f"unknown model format {value!r}; use {ModelFormat.TEXT.value!r} "
            f"or {ModelFormat.JSON.value!r}"
        ) from exc


def wire_messages(messages: Sequence[Message | Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert :class:`Message` objects (or plain mappings) to provider dicts."""
    wire: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, Message):
            wire.append({"role": message.role, "content": message.content})
        elif isinstance(message, Mapping):
            wire.append(
                {
                    "role": str(message.get("role", "user")),
                    "content": str(message.get("content", "")),
                }
            )
        else:
            raise TypeError(f"unsupported message type: {type(message).__name__}")
    return wire


def message_text(messages: Sequence[Message | Mapping[str, Any]]) -> str:
    """Flatten messages for deterministic token accounting in test doubles."""
    parts: list[str] = []
    for message in messages:
        if isinstance(message, Message):
            parts.append(message.content)
        elif isinstance(message, Mapping):
            parts.append(str(message.get("content", "")))
    return "\n".join(parts)


def usage_from_response(raw: Mapping[str, Any]) -> Usage:
    """Read usage from an OpenAI-compatible response, tolerating omissions."""
    usage = raw.get("usage") or {}
    if not isinstance(usage, Mapping):
        usage = {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion) or 0)
    return Usage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def response_content(raw: Mapping[str, Any], *, character: str = "") -> str:
    """Extract ``choices[0].message.content`` or raise :class:`ModelError`."""
    try:
        choices = raw["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        who = f"{character} " if character else ""
        raise ModelError(f"{who}model returned an unexpected response: {exc}") from exc
    if not isinstance(content, str) or not content.strip():
        who = f"{character} " if character else ""
        raise ModelError(f"{who}model returned an empty reply")
    return content


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating fences, a preface and trailing prose."""
    if not isinstance(text, str) or not text.strip():
        raise ModelError("model returned an empty reply")

    clean = text.strip()
    if clean.startswith("```"):
        clean = clean[3:]
        newline = clean.find("\n")
        if newline != -1:
            language = clean[:newline].strip().lower()
            clean = clean[newline + 1 :]
            if language not in ("", "json", "jsonc"):
                clean = f"{language}\n{clean}"
        closing = clean.rfind("```")
        if closing != -1:
            clean = clean[:closing]

    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        if start == -1:
            raise ModelError("model did not return a JSON object") from None
        try:
            value, _ = json.JSONDecoder().raw_decode(clean[start:])
        except json.JSONDecodeError as exc:
            raise ModelError(f"model did not return valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise ModelError("model JSON was not an object")
    return value


__all__ = [
    "as_format",
    "message_text",
    "parse_json_object",
    "response_content",
    "usage_from_response",
    "wire_messages",
]
