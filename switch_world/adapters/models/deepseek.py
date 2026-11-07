"""DeepSeek model adapter.

The original cloud path lived inside ``director/cloud_switch.py`` and had four
known defects. This adapter keeps the same DeepSeek API shape but fixes them:

* an error or an empty reply raises :class:`ModelError`; it is never returned
  as a silent empty string,
* JSON replies may be fenced and/or preceded by a short preamble,
* each character has a persisted daily token budget and every request is
  appended to a JSONL request log,
* there is no turn cutoff based on ``time.time() * 1000``; a turn boundary is
  the caller's job (the transport passes a captured cursor).
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.clock import Clock
from switch_world.domain.ports.model import (
    Message,
    ModelBudgetExceeded,
    ModelError,
    ModelFormat,
    ModelReply,
    Usage,
    UsageSummary,
)

from ._support import (
    as_format,
    parse_json_object,
    response_content,
    usage_from_response,
    wire_messages,
)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_DAILY_TOKENS = 60_000

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _REPO_ROOT / "data"


class DeepSeekModelClient:
    """The DeepSeek implementation of :class:`ModelClient`."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        transport: Callable[[str, dict, dict], dict] | None = None,
        *,
        budget_path: Path | str | None = None,
        log_path: Path | str | None = None,
        daily_tokens: int | Mapping[str, int] | None = None,
        clock: Clock | None = None,
        reasoning: str | None = None,
        temperature: float = 0.75,
        max_tokens: int | None = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("WORLD_CLOUD_API_KEY")
            or ""
        )
        if not self.api_key:
            raise ModelError(
                "DeepSeek needs DEEPSEEK_API_KEY (or WORLD_CLOUD_API_KEY)"
            )
        self.base_url = (
            base_url or os.environ.get("WORLD_CLOUD_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = model or os.environ.get("WORLD_CLOUD_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self.transport = transport or self._http_post
        self.clock = clock
        self.reasoning = (
            reasoning
            if reasoning is not None
            else os.environ.get("WORLD_CLOUD_REASONING", "low")
        )
        self.default_temperature = float(temperature)
        self.default_max_tokens = int(
            max_tokens
            if max_tokens is not None
            else os.environ.get("WORLD_CLOUD_MAX_TOKENS", "900")
        )
        if daily_tokens is None:
            daily_tokens = int(
                os.environ.get("WORLD_CLOUD_DAILY_TOKENS", str(DEFAULT_DAILY_TOKENS))
            )
        self.daily_tokens = daily_tokens
        self.budget_path = Path(budget_path or DEFAULT_DATA_DIR / "deepseek_budget.json")
        self.log_path = Path(log_path or DEFAULT_DATA_DIR / "logs" / "deepseek.jsonl")
        self.requests: list[dict[str, Any]] = []
        # The historical cloud client exposed the last raw provider ``usage``
        # object; keep it so the DM return shape does not change.
        self.last_usage: dict[str, Any] = {}

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

        limit = self._limit(name)
        used = int(self._budget()["characters"].get(name, 0))
        if used >= limit:
            raise ModelBudgetExceeded(
                f"{name} has used {used}/{limit} DeepSeek tokens today"
            )

        effort = reasoning if reasoning is not None else self.reasoning
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": wire_messages(messages),
            "temperature": (
                self.default_temperature if temperature is None else temperature
            ),
            "max_tokens": (
                self.default_max_tokens if max_tokens is None else max_tokens
            ),
        }
        if fmt is ModelFormat.JSON:
            payload["response_format"] = {"type": "json_object"}
        if effort:
            payload["reasoning_effort"] = effort

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.monotonic()
        try:
            raw = self.transport(
                self.base_url + "/chat/completions", payload, headers
            )
            raw_usage = raw.get("usage") if isinstance(raw, Mapping) else None
            self.last_usage = (
                dict(raw_usage) if isinstance(raw_usage, Mapping) else {}
            )
            content = response_content(raw, character=name)
            usage = usage_from_response(raw)
            data = parse_json_object(content) if fmt is ModelFormat.JSON else None
        except ModelError as exc:
            self._log_failure(name, started, effort, str(exc))
            raise
        except Exception as exc:  # transport failure of any kind
            error = ModelError(f"DeepSeek request failed: {exc}")
            self._log_failure(name, started, effort, str(error))
            raise error from exc

        self._record_usage(name, usage)
        entry = {
            "ts": self._now().isoformat(),
            "character": name,
            "model": str(raw.get("model") or self.model),
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "reasoning": effort,
            "ok": True,
        }
        self._log(entry)
        return ModelReply(
            text=content,
            data=data,
            usage=usage,
            model=entry["model"],
            raw=raw,
        )

    def usage(self, character: CharacterId | None = None) -> UsageSummary:
        state = self._budget()
        if character is not None:
            name = str(character)
            total = int(state["characters"].get(name, 0))
            entries = [
                entry
                for entry in self.requests
                if entry.get("ok") and entry.get("character") == name
            ]
        else:
            total = sum(int(value) for value in state["characters"].values())
            entries = [entry for entry in self.requests if entry.get("ok")]
        return UsageSummary(
            prompt_tokens=sum(int(entry.get("prompt_tokens", 0)) for entry in entries),
            completion_tokens=sum(
                int(entry.get("completion_tokens", 0)) for entry in entries
            ),
            total_tokens=total,
            requests=len(entries),
        )

    def usage_summary(self) -> dict[str, Any]:
        """The historical cloud evidence block: the last raw provider usage."""
        return dict(self.last_usage)

    # ---- HTTP -------------------------------------------------------------
    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ModelError(f"model endpoint unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise ModelError(
                f"model HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.json()

    # ---- budget / logs ----------------------------------------------------
    def _now(self) -> datetime:
        return self.clock.now() if self.clock is not None else datetime.now(timezone.utc)

    def _limit(self, character: str) -> int:
        if isinstance(self.daily_tokens, Mapping):
            return int(
                self.daily_tokens.get(character, DEFAULT_DAILY_TOKENS)
            )
        return int(self.daily_tokens)

    def _budget(self) -> dict:
        today = self._now().date().isoformat()
        if self.budget_path.exists():
            try:
                state = json.loads(self.budget_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}
        else:
            state = {}
        if state.get("date") != today:
            state = {"date": today, "characters": {}}
        state.setdefault("characters", {})
        return state

    def _save_budget(self, state: dict) -> None:
        self.budget_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.budget_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(self.budget_path)

    def _record_usage(self, character: str, usage: Usage) -> None:
        state = self._budget()
        state["characters"][character] = (
            int(state["characters"].get(character, 0)) + int(usage.total_tokens)
        )
        self._save_budget(state)

    def _log(self, entry: dict[str, Any]) -> None:
        self.requests.append(entry)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def _log_failure(
        self,
        character: str,
        started: float,
        effort: str | None,
        error: str,
    ) -> None:
        self._log(
            {
                "ts": self._now().isoformat(),
                "character": character,
                "model": self.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "reasoning": effort,
                "ok": False,
                "error": error,
            }
        )


__all__ = ["DeepSeekModelClient"]
