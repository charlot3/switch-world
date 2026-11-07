"""Bifrost (Maxim AI) model adapter.

Bifrost exposes an OpenAI-compatible ``/v1/chat/completions``. This module keeps
the routing, fallback, budget and request-log behaviour of the original
``gateway/bifrost.py``, but exposes one provider-neutral ``generate`` method
that serves both plain text and JSON envelopes.

Configuration lives in ``world/models.json`` (per-character model, fallbacks,
temperature and token budget). Each request appends one JSON line to a request
log, and a local budget file is a second guard so a bad prompt loop cannot burn
through a demo budget.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from switch_world.domain.ids import CharacterId
from switch_world.domain.ports.model import (
    Message,
    ModelBudgetExceeded,
    ModelError,
    ModelFormat,
    ModelReply,
    UsageSummary,
)

from ._support import (
    as_format,
    parse_json_object,
    response_content,
    usage_from_response,
    wire_messages,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_PATH = _REPO_ROOT / "world" / "models.json"
DEFAULT_DATA_DIR = _REPO_ROOT / "data"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


class BifrostError(ModelError):
    """A Bifrost request or response could not be used."""


class BudgetExceeded(BifrostError, ModelBudgetExceeded):
    """A character's daily Bifrost budget is spent."""


@dataclass(frozen=True)
class CharacterModel:
    character: str
    model: str
    fallbacks: tuple[str, ...] = ()
    temperature: float = 0.7
    max_tokens: int = 240
    daily_tokens: int = 60_000
    virtual_key_env: str | None = None
    note: str = ""
    reasoning: str | None = None


REASONING_EFFORTS = {"low", "medium", "high", "max"}
REASONING_ALIASES = {"mid": "high", "minimal": "low", "none": None}


def normalize_reasoning(value: str | None) -> str | None:
    """Return a supported effort name, or ``None`` for the provider default."""
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    normalized = REASONING_ALIASES.get(normalized, normalized)
    if normalized is None:
        return None
    if normalized not in REASONING_EFFORTS:
        raise BifrostError(
            f"unknown reasoning effort {value!r}; use one of "
            f"{', '.join(sorted(REASONING_EFFORTS))}"
        )
    return normalized


def load_models(path: Path | str | None = None) -> dict[str, CharacterModel]:
    """Read ``models.json`` with the same environment overrides as before."""
    source = Path(path or MODELS_PATH)
    raw = json.loads(source.read_text(encoding="utf-8"))
    models: dict[str, CharacterModel] = {}
    for character, cfg in raw.items():
        upper = character.upper()
        env_model = os.environ.get(f"BIFROST_MODEL_{upper}")
        env_fallbacks = os.environ.get(f"BIFROST_FALLBACKS_{upper}")
        env_reasoning = os.environ.get(f"BIFROST_REASONING_{upper}")
        fallbacks = (
            tuple(part.strip() for part in env_fallbacks.split(",") if part.strip())
            if env_fallbacks
            else tuple(cfg.get("fallbacks") or ())
        )
        models[character] = CharacterModel(
            character=character,
            model=env_model or cfg["model"],
            fallbacks=fallbacks,
            temperature=float(cfg.get("temperature", 0.7)),
            max_tokens=int(cfg.get("max_tokens", 240)),
            daily_tokens=int(cfg.get("daily_tokens", 60_000)),
            virtual_key_env=cfg.get("virtual_key_env"),
            note=cfg.get("note", ""),
            reasoning=normalize_reasoning(env_reasoning or cfg.get("reasoning")),
        )
    return models


def parse_json(text: str) -> dict:
    """Compatibility helper: tolerant JSON parse that raises ``BifrostError``."""
    try:
        return parse_json_object(text)
    except ModelError as exc:
        raise BifrostError(str(exc)) from exc


class BifrostModelClient:
    """The Bifrost implementation of :class:`ModelClient`."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        models: Mapping[str, CharacterModel] | None = None,
        log_path: Path | str | None = None,
        budget_path: Path | str | None = None,
        transport: Callable[[str, dict, dict], dict] | None = None,
        timeout: float = 180.0,
        models_path: Path | str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("BIFROST_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("BIFROST_API_KEY") or "dummy"
        self.models = dict(models or load_models(models_path))
        data_dir = DEFAULT_DATA_DIR
        self.log_path = Path(log_path or data_dir / "logs" / "bifrost.jsonl")
        self.budget_path = Path(budget_path or data_dir / "bifrost_budget.json")
        self.transport = transport or self._http_post
        self.timeout = timeout
        self.requests: list[dict[str, Any]] = []

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
        if name not in self.models:
            raise BifrostError(f"no Bifrost model configured for {name}")
        cfg = self.models[name]

        used = int(self._budget()["characters"].get(name, 0))
        if used >= cfg.daily_tokens:
            raise BudgetExceeded(
                f"{name} has used {used}/{cfg.daily_tokens} tokens today; "
                "raise daily_tokens in world/models.json or reset the budget file"
            )

        effort = normalize_reasoning(reasoning if reasoning is not None else cfg.reasoning)
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": wire_messages(messages),
            "temperature": cfg.temperature if temperature is None else temperature,
            "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
        }
        if fmt is ModelFormat.JSON:
            payload["response_format"] = {"type": "json_object"}
        if effort:
            # OpenAI-compatible field; Bifrost passes it through to the provider.
            payload["reasoning_effort"] = effort
        fallback_chain = list(cfg.fallbacks)
        if fallback_chain:
            payload["fallbacks"] = fallback_chain
        # Qwen/Ollama reasoning models otherwise spend the whole max_tokens budget on
        # hidden reasoning and return an empty content field. Bifrost passes this
        # provider-specific flag through; other models do not get it.
        if cfg.model.startswith("ollama/"):
            payload["think"] = False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if cfg.virtual_key_env:
            virtual_key = os.environ.get(cfg.virtual_key_env)
            if virtual_key:
                headers["x-bf-vk"] = virtual_key

        started = time.monotonic()
        try:
            response = self.transport(
                self.base_url + "/chat/completions", payload, headers
            )
            content = response_content(response, character=name)
            usage = usage_from_response(response)
            data = parse_json_object(content) if fmt is ModelFormat.JSON else None
        except BifrostError as exc:
            self._log_failure(name, cfg, started, effort, error=str(exc))
            raise
        except Exception as exc:  # provider/transport/parse failure
            self._log_failure(name, cfg, started, effort, error=str(exc))
            raise BifrostError(f"Bifrost request failed: {exc}") from exc

        tokens = usage.total_tokens or (
            usage.prompt_tokens + usage.completion_tokens
        )
        self._record_usage(name, tokens)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "character": name,
            "model": str(response.get("model") or cfg.model),
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": tokens,
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
            raw=response,
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

    # ---- HTTP -------------------------------------------------------------
    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise BifrostError(
                f"Bifrost is unreachable at {self.base_url}: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise BifrostError(
                f"Bifrost HTTP {response.status_code}: {response.text[:400]}"
            )
        return response.json()

    # ---- budget / logs ----------------------------------------------------
    def _budget(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
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

    def _record_usage(self, character: str, tokens: int) -> None:
        state = self._budget()
        state["characters"][character] = (
            int(state["characters"].get(character, 0)) + int(tokens)
        )
        self._save_budget(state)

    def _log(self, entry: dict) -> None:
        self.requests.append(entry)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def _log_failure(
        self,
        character: str,
        cfg: CharacterModel,
        started: float,
        effort: str | None,
        *,
        error: str = "request failed",
    ) -> None:
        self._log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "character": character,
                "model": cfg.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "reasoning": effort,
                "ok": False,
                "error": error,
            }
        )


__all__ = [
    "BifrostError",
    "BifrostModelClient",
    "BudgetExceeded",
    "CharacterModel",
    "load_models",
    "normalize_reasoning",
    "parse_json",
]
