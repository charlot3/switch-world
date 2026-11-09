"""Contract for every model adapter.

The same suite runs over Scripted, Bifrost and DeepSeek: text, JSON, fenced
JSON, sampling kwargs, usage accounting, the daily budget and error
propagation. Provider-specific tests pin the defects fixed in step 3.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from switch_world.adapters.models import (
    BifrostModelClient,
    CharacterModel,
    DeepSeekModelClient,
    ScriptedModelClient,
    ScriptedTurn,
)
from switch_world.domain.ports.model import (
    Message,
    ModelBudgetExceeded,
    ModelError,
    ModelFormat,
    Usage,
)

ADAPTERS = ("scripted", "bifrost", "deepseek")
MESSAGES = [Message(role="user", content="hello alice")]


@dataclass
class Harness:
    kind: str
    client: Any
    sent: list[dict[str, Any]]


def make_harness(
    kind: str,
    tmp_path: Path,
    *,
    reply: str = "Hello there",
    error: BaseException | None = None,
    usage_total: int = 5,
    daily_tokens: int | None = None,
    scripted_usage: int | None = None,
) -> Harness:
    sent: list[dict[str, Any]] = []

    if kind == "scripted":
        if error is not None:
            entry: Any = ScriptedTurn(error=error)
        elif scripted_usage is not None:
            entry = ScriptedTurn(
                text=reply,
                usage=Usage(completion_tokens=scripted_usage, total_tokens=scripted_usage),
            )
        else:
            entry = reply
        client = ScriptedModelClient({"alice": [entry]}, daily_tokens=daily_tokens)
        return Harness(kind, client, sent)

    def transport(url: str, payload: dict, headers: dict) -> dict:
        sent.append(payload)
        if error is not None:
            raise error
        return {
            "choices": [{"message": {"content": reply}}],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": usage_total,
            },
            "model": "test-model",
        }

    if kind == "bifrost":
        limit = 60_000 if daily_tokens is None else daily_tokens
        model = CharacterModel(
            character="alice",
            model="openai/test",
            daily_tokens=limit,
        )
        client = BifrostModelClient(
            api_key="test",
            models={"alice": model},
            transport=transport,
            log_path=tmp_path / "bifrost.jsonl",
            budget_path=tmp_path / "bifrost_budget.json",
        )
        return Harness(kind, client, sent)

    client = DeepSeekModelClient(
        api_key="test",
        model="test-model",
        transport=transport,
        budget_path=tmp_path / "deepseek_budget.json",
        log_path=tmp_path / "deepseek.jsonl",
        daily_tokens=60_000 if daily_tokens is None else daily_tokens,
    )
    return Harness(kind, client, sent)


@pytest.mark.parametrize("kind", ADAPTERS)
def test_text_reply(kind, tmp_path):
    harness = make_harness(kind, tmp_path, reply="Hello there")

    reply = harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)

    assert reply.text == "Hello there"
    assert reply.data is None
    assert reply.usage.total_tokens > 0
    assert reply.model
    if kind != "scripted":
        assert "response_format" not in harness.sent[-1]


@pytest.mark.parametrize("kind", ADAPTERS)
def test_json_reply(kind, tmp_path):
    payload = '{"reply": "Hi", "memory": null}'
    harness = make_harness(kind, tmp_path, reply=payload)

    reply = harness.client.generate("alice", MESSAGES, format=ModelFormat.JSON)

    assert reply.text == payload
    assert reply.data == {"reply": "Hi", "memory": None}
    if kind != "scripted":
        assert harness.sent[-1]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("kind", ADAPTERS)
def test_fenced_json_with_a_short_preamble(kind, tmp_path):
    payload = 'Sure, here it is:\n```json\n{"reply": "Hi", "memory": null}\n```\nDone.'
    harness = make_harness(kind, tmp_path, reply=payload)

    reply = harness.client.generate("alice", MESSAGES, format=ModelFormat.JSON)

    assert reply.data == {"reply": "Hi", "memory": None}


@pytest.mark.parametrize("kind", ADAPTERS)
def test_sampling_kwargs_are_passed_through(kind, tmp_path):
    harness = make_harness(kind, tmp_path, reply="Hello there")

    harness.client.generate(
        "alice",
        MESSAGES,
        format=ModelFormat.TEXT,
        temperature=0.1,
        max_tokens=42,
        reasoning="high",
    )

    if kind == "scripted":
        call = harness.client.calls[-1]
        assert call.temperature == 0.1
        assert call.max_tokens == 42
        assert call.reasoning == "high"
        assert call.format is ModelFormat.TEXT
        return

    payload = harness.sent[-1]
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 42
    assert payload["reasoning_effort"] == "high"


@pytest.mark.parametrize("kind", ADAPTERS)
def test_usage_accumulates(kind, tmp_path):
    harness = make_harness(kind, tmp_path, reply="Hello there")

    first = harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)
    second = harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)

    summary = harness.client.usage("alice")
    assert summary.total_tokens == first.usage.total_tokens + second.usage.total_tokens
    assert summary.requests == 2


@pytest.mark.parametrize("kind", ADAPTERS)
def test_daily_budget_is_enforced(kind, tmp_path):
    harness = make_harness(
        kind,
        tmp_path,
        reply="ok",
        usage_total=10,
        scripted_usage=10,
        daily_tokens=10,
    )

    harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)

    with pytest.raises(ModelBudgetExceeded):
        harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)


@pytest.mark.parametrize("kind", ADAPTERS)
def test_errors_propagate_as_model_error(kind, tmp_path):
    harness = make_harness(kind, tmp_path, error=RuntimeError("boom"))

    with pytest.raises(ModelError, match="boom"):
        harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)


# ---- provider-specific guarantees -----------------------------------------


def test_bifrost_routes_each_character_to_its_configured_model(tmp_path):
    sent: list[dict] = []

    def transport(url, payload, headers):
        sent.append(payload)
        return {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"total_tokens": 1},
            "model": payload["model"],
        }

    models = {
        "alice": CharacterModel(character="alice", model="model-a"),
        "emily": CharacterModel(character="emily", model="model-b"),
    }
    client = BifrostModelClient(
        api_key="test",
        models=models,
        transport=transport,
        log_path=tmp_path / "bifrost.jsonl",
        budget_path=tmp_path / "bifrost_budget.json",
    )

    client.generate("alice", MESSAGES, format=ModelFormat.TEXT)
    client.generate("emily", MESSAGES, format=ModelFormat.TEXT)

    assert [payload["model"] for payload in sent] == ["model-a", "model-b"]
    log_lines = (tmp_path / "bifrost.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 2
    assert json.loads(log_lines[0])["ok"] is True


def test_bifrost_text_and_json_envelopes_carry_reasoning(tmp_path):
    """Bifrost's generate() must cover both formats and its reasoning config."""
    sent: list[dict] = []

    def transport(url, payload, headers):
        sent.append(payload)
        content = (
            '{"reply": "Hi", "memory": null}'
            if payload.get("response_format")
            else "Hi"
        )
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
            },
            "model": payload["model"],
        }

    client = BifrostModelClient(
        api_key="test",
        models={
            "alice": CharacterModel(
                character="alice", model="openai/test", reasoning="low"
            )
        },
        transport=transport,
        log_path=tmp_path / "bifrost.jsonl",
        budget_path=tmp_path / "bifrost_budget.json",
    )

    text_reply = client.generate("alice", MESSAGES, format=ModelFormat.TEXT)
    json_reply = client.generate(
        "alice", MESSAGES, format=ModelFormat.JSON, reasoning="high"
    )

    assert text_reply.text == "Hi"
    assert text_reply.data is None
    assert json_reply.data == {"reply": "Hi", "memory": None}
    assert "response_format" not in sent[0]
    assert sent[0]["reasoning_effort"] == "low"
    assert sent[1]["response_format"] == {"type": "json_object"}
    assert sent[1]["reasoning_effort"] == "high"

    entries = [
        json.loads(line)
        for line in (tmp_path / "bifrost.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [entry["reasoning"] for entry in entries] == ["low", "high"]
    assert all(entry["ok"] is True for entry in entries)


def test_deepseek_empty_reply_is_an_error_not_a_silence(tmp_path):
    harness = make_harness("deepseek", tmp_path, reply="   ")

    with pytest.raises(ModelError, match="empty"):
        harness.client.generate("alice", MESSAGES, format=ModelFormat.TEXT)

    log_lines = (tmp_path / "deepseek.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["ok"] is False


def test_deepseek_budget_is_per_character_and_requests_are_logged(tmp_path):
    sent: list[dict] = []

    def transport(url, payload, headers):
        sent.append(payload)
        return {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
            "model": "test-model",
        }

    client = DeepSeekModelClient(
        api_key="test",
        transport=transport,
        budget_path=tmp_path / "deepseek_budget.json",
        log_path=tmp_path / "deepseek.jsonl",
        daily_tokens={"alice": 10, "emily": 100},
    )

    client.generate("alice", MESSAGES, format=ModelFormat.TEXT)
    client.generate("emily", MESSAGES, format=ModelFormat.TEXT)
    with pytest.raises(ModelBudgetExceeded):
        client.generate("alice", MESSAGES, format=ModelFormat.TEXT)

    assert len(sent) == 2
    lines = (tmp_path / "deepseek.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["character"] for line in lines] == ["alice", "emily"]
    assert client.usage("alice").total_tokens == 10
    assert client.usage("emily").total_tokens == 10
