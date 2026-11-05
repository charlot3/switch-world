#!/usr/bin/env python3
"""OpenAI-compatible shim in front of the OpenCode Go model.

Bifrost speaks OpenAI `/v1/chat/completions`; OpenCode's local v2 API is not an
OpenAI endpoint. This shim joins the request messages into one prompt, runs

    opencode run --model opencode-go/deepseek-v4.1-flash --format json --auto

and turns the last text event into an OpenAI response. Bifrost still owns routing,
fallbacks, budgets and request logs; this is the provider adapter, not a second gateway.

    OPENCODE_PROXY_TOKEN=... python3 scripts/opencode-gateway.py
    curl http://127.0.0.1:8090/v1/models
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


def run_opencode(prompt: str) -> tuple[str, int]:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    command = [
        "opencode", "run",
        "--model", MODEL,
        "--format", "json",
        "--auto",
        prompt,
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(WORKDIR),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"opencode run timed out after {TIMEOUT:.0f}s") from exc
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
    return "\n".join(texts).strip(), int((time.monotonic() - started) * 1000)


class Handler(BaseHTTPRequestHandler):
    server_version = "switch-world-opencode-gateway/0.1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._json(200, {"ok": True, "model": MODEL})
            return
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._json(200, {
                "object": "list",
                "data": [{
                    "id": MODEL.split("/")[-1],
                    "object": "model",
                    "owned_by": "opencode-go",
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
            text, latency_ms = run_opencode(prompt)
        except Exception as exc:  # noqa: BLE001 - return the provider error to Bifrost
            self._json(502, {"error": {"message": str(exc)}})
            return

        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(text)
        self._json(200, {
            "id": "chatcmpl-" + uuid.uuid4().hex[:24],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL,
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
    WORKDIR.mkdir(parents=True, exist_ok=True)
    print(
        f"OpenCode gateway: 0.0.0.0:{PORT} -> {MODEL} "
        f"(token {'required' if TOKEN else 'off'})",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
