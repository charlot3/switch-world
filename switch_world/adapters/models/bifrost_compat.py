"""Bifrost (Maxim AI) client for the character model calls.

Bifrost exposes an OpenAI-compatible `/v1/chat/completions`. We keep a small client-side
contract around it so the Geek Room demo can run without a provider key, and so the
per-character model, fallback and budget choices are visible in the repository:

    world/models.json          per-character model, fallbacks, temperature, token budget
    data/logs/bifrost.jsonl    one JSON line per request: character, model, tokens, latency
    data/bifrost_budget.json   daily token usage, reset by UTC date

The gateway itself remains the source of truth for routing, fallbacks, virtual keys and
observability. The local budget file is a second guard so a bad prompt loop cannot burn
through a demo budget.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from switch_world.config import load_settings

MODELS_PATH = Path(load_settings(os.environ).content_root) / "models.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


class BifrostError(RuntimeError):
    pass


class BudgetExceeded(BifrostError):
    pass


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
    """Return a supported effort name, or None for the provider default."""
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
    """Extract the first JSON object from a model reply, tolerating fences/preamble."""
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:]
    try:
        value = json.loads(clean)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end <= start:
        raise BifrostError("model did not return a JSON object")
    value = json.loads(clean[start:end + 1])
    if not isinstance(value, dict):
        raise BifrostError("model JSON was not an object")
    return value


class BifrostClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        models: Mapping[str, CharacterModel] | None = None,
        log_path: Path | str | None = None,
        budget_path: Path | str | None = None,
        transport: Callable[[str, dict, dict], dict] | None = None,
        timeout: float = 180.0,
    ):
        self.base_url = (base_url or os.environ.get("BIFROST_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("BIFROST_API_KEY") or "dummy"
        self.models = dict(models or load_models())
        data_dir = load_settings(os.environ).data_dir
        self.log_path = Path(log_path or data_dir / "logs" / "bifrost.jsonl")
        self.budget_path = Path(budget_path or data_dir / "bifrost_budget.json")
        self.transport = transport or self._http_post
        self.timeout = timeout
        self.requests: list[dict] = []

    # ---- HTTP -------------------------------------------------------------
    def _http_post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise BifrostError(f"Bifrost is unreachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise BifrostError(f"Bifrost HTTP {response.status_code}: {response.text[:400]}")
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
        state["characters"][character] = int(state["characters"].get(character, 0)) + int(tokens)
        self._save_budget(state)

    def _log(self, entry: dict) -> None:
        self.requests.append(entry)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    # ---- chat -------------------------------------------------------------
    def chat(
        self,
        character: str,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        fallbacks: list[str] | None = None,
        extra: dict | None = None,
        reasoning: str | None = None,
    ) -> dict:
        if character not in self.models:
            raise BifrostError(f"no Bifrost model configured for {character}")
        cfg = self.models[character]
        used = int(self._budget()["characters"].get(character, 0))
        if used >= cfg.daily_tokens:
            raise BudgetExceeded(
                f"{character} has used {used}/{cfg.daily_tokens} tokens today; "
                "raise daily_tokens in world/models.json or reset the budget file"
            )

        effort = normalize_reasoning(
            reasoning if reasoning is not None else cfg.reasoning
        )
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature if temperature is None else temperature,
            "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
        }
        if effort:
            # OpenAI-compatible field; the OpenCode shim maps it to a model variant.
            # Bifrost passes it through to the provider.
            payload["reasoning_effort"] = effort
        chain = list(fallbacks or cfg.fallbacks)
        if chain:
            payload["fallbacks"] = chain
        # Qwen/Ollama reasoning models otherwise spend the whole max_tokens budget on
        # hidden reasoning and return an empty content field. Bifrost passes this
        # provider-specific flag through; non-Ollama models do not get it.
        if cfg.model.startswith("ollama/"):
            payload["think"] = False
        if extra:
            payload.update(extra)

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
            response = self.transport(self.base_url + "/chat/completions", payload, headers)
            content = (
                (response.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            usage = response.get("usage") or {}
            tokens = int(
                usage.get("total_tokens")
                or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
                or 0
            )
            self._record_usage(character, tokens)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "character": character,
                "model": response.get("model", cfg.model),
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": tokens,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "reasoning": effort,
                "ok": True,
            }
            self._log(entry)
            return {
                "content": content or "",
                "usage": usage,
                "model": entry["model"],
                "latency_ms": entry["latency_ms"],
            }
        except BifrostError as exc:
            self._log({
                "ts": datetime.now(timezone.utc).isoformat(),
                "character": character,
                "model": cfg.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "reasoning": effort,
                "ok": False,
                "error": str(exc),
            })
            raise

    def chat_json(self, character: str, messages: list[dict], **kwargs) -> dict:
        result = self.chat(character, messages, **kwargs)
        return parse_json(result["content"])

    # ---- evidence ---------------------------------------------------------
    def usage_summary(self) -> dict:
        state = self._budget()
        return {
            "date": state["date"],
            "characters": {
                character: {
                    "used_tokens": int(state["characters"].get(character, 0)),
                    "daily_tokens": cfg.daily_tokens,
                    "model": cfg.model,
                    "fallbacks": list(cfg.fallbacks),
                    "reasoning": cfg.reasoning,
                }
                for character, cfg in self.models.items()
            },
            "requests": len(self.requests),
            "log_path": str(self.log_path),
        }

    def status(self) -> dict:
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(self.base_url + "/models")
            return {"up": response.status_code < 400, "status": response.status_code}
        except httpx.HTTPError as exc:
            return {"up": False, "error": str(exc)}
