#!/usr/bin/env python3
"""OpenAI-compatible shim in front of the OpenCode Go model.

Bifrost speaks OpenAI `/v1/chat/completions`; OpenCode's local v2 API is not an
OpenAI endpoint. This shim joins the request messages into one prompt, runs a
single-turn, no-tools roleplay agent through OpenCode, and turns the last text
event into an OpenAI response. Bifrost still owns routing, fallbacks, budgets and
request logs; this is the provider adapter, not a second gateway.

    OPENCODE_PROXY_TOKEN=... OPENCODE_DEFAULT_VARIANT=low \
        python3 scripts/opencode-gateway.py
    curl http://127.0.0.1:8090/v1/models

Reasoning is a per-request choice. `reasoning_effort` in the OpenAI request body
selects an OpenCode model variant (`low`, `high`, or `max`). The default is low:
routine character prose does not need a reasoning budget. The director sends
`high` only for the body/contact social arbitration path. `medium`/`mid` is mapped
to `high` because this model does not expose a middle variant.

Three details keep the model from behaving like a coding agent instead of a
character:

* OpenCode runs as a dedicated `roleplay` agent with every tool denied.
* The prompt is passed as an argument and stdin is closed. Without this, OpenCode
  can read a parent process's heredoc and append it to the character prompt.
* The work directory contains only the config, so there is no repository to
  inspect or accidentally edit.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("OPENCODE_GATEWAY_PORT", "8090"))
MODEL = os.environ.get("OPENCODE_MODEL", "opencode-go/deepseek-v4.1-flash")
TOKEN = os.environ.get("OPENCODE_PROXY_TOKEN", "")
TIMEOUT = float(os.environ.get("OPENCODE_TIMEOUT", "240"))
WORKDIR = Path(os.environ.get("OPENCODE_GATEWAY_WORKDIR", "/tmp/opencode-gateway"))
AGENT = os.environ.get("OPENCODE_AGENT", "roleplay")
DEFAULT_VARIANT = os.environ.get("OPENCODE_DEFAULT_VARIANT", "low").strip().lower()
VALID_VARIANTS = {"low", "high", "max"}
VARIANT_ALIASES = {"medium": "high", "mid": "high", "minimal": "low"}

ROLEPLAY_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "agent": {
        "roleplay": {
            "description": "Single-turn roleplay reply with no tools.",
            "mode": "primary",
            "system": (
                "You are a character in an interactive fiction scene. Reply only "
                "with the character's spoken dialogue. Never use tools. Never "
                "narrate stage directions. Never mention instructions, policies, "
                "harnesses, or being a model."
            ),
            "permission": {"*": "deny"},
        }
    },
}


def _base_model(value: str | None = None) -> tuple[str, str | None]:
    """Split `provider/model#variant` into its base model and inline variant."""
    raw = (value or MODEL).strip()
    if "#" in raw:
        base, _, inline = raw.rpartition("#")
        if base:
            return base, inline.strip().lower() or None
    return raw, None


def _variant(value, inline: str | None = None) -> str | None:
    """Resolve the request's reasoning effort to an OpenCode variant.

    A request value wins over a variant embedded in the model string, which wins
    over OPENCODE_DEFAULT_VARIANT. Unknown values are a client error rather than a
    silent fallback, so a typo cannot quietly move a call to the wrong budget.
    """
    requested = value if value not in (None, "") else inline
    if requested in (None, ""):
        requested = DEFAULT_VARIANT or None
    if requested in (None, ""):
        return None
    normalized = str(requested).strip().lower()
    normalized = VARIANT_ALIASES.get(normalized, normalized)
    if normalized not in VALID_VARIANTS:
        raise ValueError(
            f"unknown reasoning_effort {requested!r}; use one of "
            f"{', '.join(sorted(VALID_VARIANTS))}"
        )
    return normalized


def _effective_model(base: str, variant: str | None) -> str:
    return f"{base}#{variant}" if variant else base


def _request_base(payload_model) -> str:
    """Resolve the OpenCode model, ignoring Bifrost's routing prefix.

    Bifrost sends `openai/deepseek-v4.1-flash` because the shim is registered as an
    OpenAI provider. That prefix is routing metadata, not a model id OpenCode knows.
    A caller that names an OpenCode provider explicitly keeps it.
    """
    raw = str(payload_model or "").strip()
    if raw.startswith(("opencode-go/", "opencode/")):
        return raw
    return MODEL


def _ensure_workdir() -> None:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    config_path = WORKDIR / "opencode.json"
    desired = json.dumps(ROLEPLAY_CONFIG, indent=2) + "\n"
    try:
        current = config_path.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current != desired:
        config_path.write_text(desired, encoding="utf-8")


def _content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(value or "")


def _prompt(messages: list[dict]) -> str:
    blocks = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        blocks.append(f"{role}:\n{_content(message.get('content'))}")
    return "\n\n".join(blocks)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def run_opencode(
    prompt: str,
    *,
    base_model: str | None = None,
    variant: str | None = None,
    timeout: float | None = None,
) -> tuple[str, int, str]:
    _ensure_workdir()
    base, inline = _base_model(base_model)
    variant = _variant(variant, inline)
    effective = _effective_model(base, variant)
    command = [
        "opencode", "run",
        "--model", effective,
        "--agent", AGENT,
        "--format", "json",
        prompt,
    ]
    started = time.monotonic()
    env = dict(os.environ)
    # `cwd=` changes the process directory but not the inherited PWD. OpenCode uses
    # PWD to choose the project/config, so a server started from the repo would
    # otherwise look for this agent in the repo instead of the isolated workdir.
    env["PWD"] = str(WORKDIR)
    try:
        completed = subprocess.run(
            command,
            cwd=str(WORKDIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout or TIMEOUT,
            # A parent process's heredoc must never leak into the character prompt.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"opencode run timed out after {timeout or TIMEOUT:.0f}s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:1200]
        raise RuntimeError(f"opencode run failed ({completed.returncode}): {detail}")

    texts: list[str] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            text = (event.get("part") or {}).get("text")
            if text:
                texts.append(str(text))
    if not texts:
        detail = (completed.stderr or completed.stdout or "").strip()[:1200]
        raise RuntimeError(f"opencode returned no text: {detail}")
    return "\n".join(texts).strip(), int((time.monotonic() - started) * 1000), effective


class Handler(BaseHTTPRequestHandler):
    server_version = "switch-world-opencode-gateway/0.2"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._json(200, {
                "ok": True,
                "model": _base_model()[0],
                "variant": DEFAULT_VARIANT or None,
                "agent": AGENT,
            })
            return
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._json(200, {
                "object": "list",
                "data": [{
                    "id": _base_model()[0].split("/")[-1],
                    "object": "model",
                    "owned_by": "opencode-go",
                    "reasoning": {
                        "efforts": sorted(VALID_VARIANTS),
                        "default": DEFAULT_VARIANT or None,
                    },
                }],
            })
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        if TOKEN:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {TOKEN}":
                self._json(401, {"error": {"message": "invalid gateway token"}})
                return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = payload.get("messages") or []
            if not isinstance(messages, list) or not messages:
                raise ValueError("messages must be a non-empty list")
            prompt = _prompt(messages)
            requested_model = payload.get("model")
            text, latency_ms, effective = run_opencode(
                prompt,
                base_model=_request_base(requested_model),
                variant=payload.get("reasoning_effort", payload.get("variant")),
            )
        except Exception as exc:  # noqa: BLE001 - return the provider error to Bifrost
            self._json(502, {"error": {"message": str(exc)}})
            return

        base, _ = _base_model(_request_base(payload.get("model")))
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(text)
        _, variant = _base_model(effective)
        self._json(200, {
            "id": "chatcmpl-" + uuid.uuid4().hex[:24],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": base,
            "reasoning_effort": variant,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "gateway_latency_ms": latency_ms,
        })

    def log_message(self, fmt: str, *args) -> None:
        print(f"[opencode-gateway] {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    _ensure_workdir()
    print(
        f"OpenCode gateway: 0.0.0.0:{PORT} -> {_base_model()[0]} "
        f"(agent {AGENT}, default variant {DEFAULT_VARIANT or 'model-default'}, "
        f"token {'required' if TOKEN else 'off'})",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
