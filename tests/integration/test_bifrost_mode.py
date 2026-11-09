"""``WORLD_AGENT_MODE=bifrost`` routes every character call through Bifrost.

The composition root must build a ``CloudRoomTransport`` over a
``BifrostModelClient`` pointed at ``BIFROST_URL`` with the per-character models
from ``world/models.json``. A group turn then travels over the Bifrost HTTP
transport, applies the JSON envelope's writes, and records the request usage in
the standard Bifrost log and budget files.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from switch_world.adapters.models import BifrostModelClient
from switch_world.adapters.transports import CloudRoomTransport
from switch_world.application import social
from switch_world.application.group_planning import _prompt_for, _relay_prompt
from switch_world.config import load_settings
from switch_world.container import build_container
from switch_world.interfaces.http.app import create_app


class FakeBifrostHTTP:
    """An OpenAI-compatible ``/chat/completions`` double for the Bifrost route."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, payload: dict, headers: dict) -> dict:
        self.calls.append((url, payload, headers))
        envelope = {
            "reply": "The lease renewal came back with a different number.",
            "memory": {
                "proposition": "The user asked Alice about the bookshop lease",
                "source": "user",
                "confidence": 0.7,
                "visibility": "private",
                "proposition_key": "bifrost-lease-renewal",
            },
            "relationships": [
                {
                    "other": "user",
                    "trust_delta": 0.1,
                    "closeness_delta": 0.05,
                    "reason": "asked about the shop",
                }
            ],
        }
        return {
            "model": "openai/deepseek-v4.1-flash",
            "choices": [{"message": {"content": json.dumps(envelope)}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


class ProseUnlessAskedHTTP(FakeBifrostHTTP):
    """A provider that ignores ``response_format`` and speaks prose.

    The OpenCode adapter behind Bifrost has no OpenAI ``response_format`` field,
    so it only answers in JSON when the prompt itself asks for the envelope.
    This double reproduces that provider, which is why the group prompt must
    carry the envelope contract.
    """

    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []

    def __call__(self, url: str, payload: dict, headers: dict) -> dict:
        prompt = "\n".join(
            str(message.get("content") or "") for message in payload["messages"]
        )
        self.prompts.append(prompt)
        content = (
            json.dumps(
                {"reply": "Same as ever.", "memory": None, "relationships": []}
            )
            if "Return ONLY a JSON object" in prompt
            else "Same as ever."
        )
        return {
            "model": "openai/deepseek-v4.1-flash",
            "choices": [{"message": {"content": content}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


def _bifrost_settings(tmp_path):
    return load_settings(
        {
            "WORLD_AGENT_MODE": "bifrost",
            "WORLD_DATA_DIR": str(tmp_path),
            "WORLD_DB": str(tmp_path / "world.sqlite"),
            "WORLD_DEV": "1",
            "BIFROST_URL": "http://bifrost.test/v1/",
            "BIFROST_API_KEY": "test-key",
        }
    )


def test_bifrost_mode_routes_a_group_turn_and_records_its_usage(tmp_path):
    settings = _bifrost_settings(tmp_path)
    container = build_container(settings)

    assert isinstance(container.model, BifrostModelClient)
    assert isinstance(container.transport, CloudRoomTransport)
    assert container.transport.name == "bifrost"
    assert container.model.base_url == "http://bifrost.test/v1"
    assert container.model.api_key == "test-key"
    assert container.transport._model is container.model  # the room uses this model

    fake = FakeBifrostHTTP()
    container.model.transport = fake

    app = create_app(container.service, settings, container=container)
    with TestClient(app) as client:
        response = client.post(
            "/api/group/say",
            json={
                "message": "Alice, did the lease renewal come back?",
                "characters": ["alice"],
                "timeout": 2,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["replies"][0]["character"] == "alice"

    assert len(fake.calls) == 1
    url, payload, headers = fake.calls[0]
    assert url == "http://bifrost.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["model"] == "openai/deepseek-v4.1-flash"
    assert payload["reasoning_effort"] == "low"

    # The JSON envelope's memory write is applied with Alice as the actor.
    memories = container.service.recall("alice")["memories"]
    assert any(item["key"] == "bifrost-lease-renewal" for item in memories)

    # The standard Bifrost log and local budget both record the call.
    log_lines = (tmp_path / "logs" / "bifrost.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(log_lines) == 1
    entry = json.loads(log_lines[0])
    assert entry["character"] == "alice"
    assert entry["ok"] is True
    assert entry["total_tokens"] == 18
    assert entry["reasoning"] == "low"

    budget = json.loads(
        (tmp_path / "bifrost_budget.json").read_text(encoding="utf-8")
    )
    assert budget["characters"]["alice"] == 18


def test_group_prompt_carries_the_envelope_for_a_json_model(tmp_path):
    settings = _bifrost_settings(tmp_path)
    container = build_container(settings)
    fake = ProseUnlessAskedHTTP()
    container.model.transport = fake

    app = create_app(container.service, settings, container=container)
    with TestClient(app) as client:
        response = client.post(
            "/api/group/say",
            json={
                "message": "Alice, how was your day?",
                "characters": ["alice"],
                "timeout": 2,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["replies"][0]["text"] == "Same as ever."
    assert len(fake.prompts) == 1
    assert "Return ONLY a JSON object" in fake.prompts[0]
    assert '"reply"' in fake.prompts[0]


def test_plain_text_group_prompt_stays_prose(tmp_path):
    settings = _bifrost_settings(tmp_path)
    container = build_container(settings)
    message = "Alice, how was your day?"
    verdict = social.appraise(container.service, "alice", message, public=True)

    plain = _prompt_for(
        container.service, "alice", message, verdict, "primary", present=["alice"]
    )
    enveloped = _prompt_for(
        container.service,
        "alice",
        message,
        verdict,
        "primary",
        present=["alice"],
        envelope=True,
    )

    assert "Return ONLY a JSON object" not in plain
    assert "Return ONLY a JSON object" in enveloped


def test_relay_prompt_carries_the_envelope_for_a_json_model(tmp_path):
    settings = _bifrost_settings(tmp_path)
    container = build_container(settings)

    enveloped = _relay_prompt(
        container.service, "alice", "emily", "Did you know?", envelope=True
    )
    plain = _relay_prompt(container.service, "alice", "emily", "Did you know?")

    assert "Return ONLY a JSON object" in enveloped
    assert "world__remember" not in enveloped
    assert "Return ONLY a JSON object" not in plain
    assert "world__remember" in plain
