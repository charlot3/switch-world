from __future__ import annotations

import json

import pytest

from gateway.bifrost import (
    BifrostClient,
    BudgetExceeded,
    CharacterModel,
    parse_json,
)
from gateway.tavily import (
    TavilyClient,
    TavilyNotConfigured,
    format_context,
)


def test_parse_json_tolerates_fences_and_preamble():
    assert parse_json('```json\n{"reply": "hi"}\n```') == {"reply": "hi"}
    assert parse_json('Here you go: {"reply": "hi", "memory": null} done') == {
        "reply": "hi", "memory": None
    }


def test_bifrost_chat_logs_usage_and_enforces_budget(tmp_path):
    calls = []

    def transport(url, payload, headers):
        calls.append((url, payload, headers))
        return {
            "model": "ollama/test",
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
        }

    client = BifrostClient(
        models={"alice": CharacterModel("alice", "ollama/test", daily_tokens=10)},
        log_path=tmp_path / "bifrost.jsonl",
        budget_path=tmp_path / "budget.json",
        transport=transport,
    )
    result = client.chat("alice", [{"role": "user", "content": "hi"}])
    assert result["content"] == "hello"
    assert calls[0][0].endswith("/chat/completions")
    assert calls[0][1]["model"] == "ollama/test"
    assert calls[0][2]["Authorization"] == "Bearer dummy"

    summary = client.usage_summary()
    assert summary["characters"]["alice"]["used_tokens"] == 10
    log = (tmp_path / "bifrost.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(log)["character"] == "alice"
    assert json.loads(log)["total_tokens"] == 10

    with pytest.raises(BudgetExceeded):
        client.chat("alice", [{"role": "user", "content": "again"}])


def test_bifrost_model_env_override(monkeypatch, tmp_path):
    models = tmp_path / "models.json"
    models.write_text(
        json.dumps({
            "alice": {
                "model": "ollama/default",
                "fallbacks": ["ollama/fallback"],
                "daily_tokens": 100,
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("BIFROST_MODEL_ALICE", "anthropic/claude-sonnet-4-5")
    monkeypatch.setenv("BIFROST_FALLBACKS_ALICE", "openai/gpt-4o-mini")
    from gateway.bifrost import load_models

    loaded = load_models(models)
    assert loaded["alice"].model == "anthropic/claude-sonnet-4-5"
    assert loaded["alice"].fallbacks == ("openai/gpt-4o-mini",)


def test_tavily_search_with_transport():
    def transport(url, payload, headers):
        assert url.endswith("/search")
        assert headers["Authorization"] == "Bearer tvly-test"
        assert payload["query"] == "current agents"
        return {
            "answer": "A short answer",
            "results": [
                {
                    "title": "A result",
                    "url": "https://example.com/a",
                    "content": "A snippet",
                    "published_date": "2026-11-05",
                    "score": 0.9,
                }
            ],
        }

    client = TavilyClient(api_key="tvly-test", transport=transport)
    result = client.search("current agents")
    assert result["offline"] is False
    assert result["answer"] == "A short answer"
    assert result["results"][0]["title"] == "A result"
    assert result["results"][0]["url"] == "https://example.com/a"


def test_tavily_offline_fixture_and_missing_key():
    offline = TavilyClient(api_key="", offline=True)
    result = offline.search("anything")
    assert result["offline"] is True
    assert result["results"]
    assert "Offline fixture" in result["results"][0]["title"]

    with pytest.raises(TavilyNotConfigured):
        TavilyClient(api_key="", offline=False).search("anything")


def test_tavily_format_context_keeps_source_url():
    context = format_context([
        {"title": "T", "url": "https://example.com", "content": "C"}
    ])
    assert "T" in context
    assert "https://example.com" in context
