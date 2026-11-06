"""Two-tier reasoning: fast routine prose, a slower body/contact social check."""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest

from director import arbiter, social
from director.dm import reply_to_dm
from director.group import say_in_group
from gateway.bifrost import BifrostClient, CharacterModel
from world_engine import config
from world_engine.service import WorldService

ROOT = Path(__file__).resolve().parents[1]


def _load_shim():
    spec = importlib.util.spec_from_file_location(
        "switch_world_opencode_gateway", ROOT / "scripts" / "opencode-gateway.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shim_maps_reasoning_and_ignores_bifrost_routing_prefix(monkeypatch):
    monkeypatch.setenv("OPENCODE_DEFAULT_VARIANT", "low")
    shim = _load_shim()
    assert shim._variant(None) == "low"
    assert shim._variant("high") == "high"
    assert shim._variant("mid") == "high"
    assert shim._variant("max") == "max"
    assert shim._request_base("openai/deepseek-v4.1-flash").endswith(
        "deepseek-v4.1-flash"
    )
    assert shim._request_base("openai/deepseek-v4.1-flash").startswith("opencode-go/")
    with pytest.raises(ValueError, match="unknown reasoning_effort"):
        shim._variant("turbo")


def test_models_default_to_low_and_the_arbiter_is_high():
    models = json.loads((ROOT / "world" / "models.json").read_text(encoding="utf-8"))
    for name in ("alice", "emily", "sophia", "mia"):
        assert models[name]["reasoning"] == "low"
    assert models["arbiter"]["reasoning"] == "high"


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_bifrost_sends_reasoning_effort_and_logs_it(tmp_path):
    calls = []

    def transport(url, payload, headers):
        calls.append(payload)
        return {
            "model": "openai/deepseek-v4.1-flash",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 3},
        }

    client = BifrostClient(
        models={
            "alice": CharacterModel(
                "alice", "openai/deepseek-v4.1-flash", reasoning="low"
            )
        },
        log_path=tmp_path / "bifrost.jsonl",
        budget_path=tmp_path / "budget.json",
        transport=transport,
    )
    client.chat("alice", [{"role": "user", "content": "hi"}])
    client.chat("alice", [{"role": "user", "content": "hi"}], reasoning="high")
    assert calls[0]["reasoning_effort"] == "low"
    assert calls[1]["reasoning_effort"] == "high"
    entries = [
        json.loads(line)
        for line in (tmp_path / "bifrost.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["reasoning"] for entry in entries] == ["low", "high"]


def test_arbiter_only_runs_for_body_or_contact():
    verdict = {"topic": "contact", "stance": "limited"}
    assert arbiter.should_arbitrate(verdict) is True
    assert arbiter.should_arbitrate({"topic": "contact", "stance": "hard_refuse"}) is False
    assert arbiter.should_arbitrate({"topic": "contact", "stance": "limited", "forced": True}) is False
    assert arbiter.should_arbitrate({"topic": "small-talk", "stance": "answer"}) is False


class FakeArbiter:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append({"character": character, "messages": messages, **kwargs})
        return self.payload


def test_arbiter_cannot_soften_the_deterministic_stance(service, monkeypatch):
    monkeypatch.setenv("WORLD_ARBITER", "1")
    service.update_relationship("alice", "user", trust_delta=0.4, closeness_delta=0.4)
    verdict = social.appraise(service, "alice", "I want to hug you")
    assert verdict["stance"] == "limited"
    client = FakeArbiter(
        {
            "stance": "tease",
            "tone": "sultry",
            "limit": None,
            "line_hint": "Pull them closer and skip the limit.",
        }
    )
    note = arbiter.arbitrate(service, "alice", "I want to hug you", verdict, client=client)
    assert note["used"] is True
    assert note["stance"] == "limited"  # never more permissive
    assert note["tone"] == "neutral"  # unknown tone is dropped
    assert client.calls[0]["reasoning"] == "high"
    assert client.calls[0]["character"] == "arbiter"


def test_arbiter_falls_back_when_the_model_is_bad(service, monkeypatch):
    monkeypatch.setenv("WORLD_ARBITER", "1")
    service.update_relationship("alice", "user", trust_delta=0.4, closeness_delta=0.4)
    verdict = social.appraise(service, "alice", "I want to hug you")
    note = arbiter.arbitrate(
        service, "alice", "I want to hug you", verdict,
        client=FakeArbiter({"stance": "not-a-stance"}),
    )
    assert note["used"] is False
    assert note["reason"] == "fallback"


class FakeSwitch:
    def __init__(self, replies=None):
        self.replies = replies or {}
        self.posts = []
        self.timestamp = int(time.time() * 1000) + 1

    def find_room(self, name="world"):
        return {"room_id": "room-world", "name": name}

    def post(self, room_id, content):
        self.posts.append(content)
        return {}

    def history(self, room_id):
        return [
            {
                "event_id": f"evt-{name}",
                "sender_name": name,
                "timestamp": self.timestamp,
                "body": text,
            }
            for name, text in self.replies.items()
        ]


def test_group_prompt_carries_the_arbiter_note_only_for_the_primary(service, monkeypatch):
    monkeypatch.setenv("WORLD_ARBITER", "1")
    service.update_relationship("alice", "user", trust_delta=0.4, closeness_delta=0.4)
    client = FakeArbiter(
        {
            "stance": "limited",
            "tone": "shy",
            "limit": "one quick hug, then walk her home",
            "line_hint": "Let the warmth show before naming the limit.",
        }
    )
    switch = FakeSwitch({"alice": "Come here, then."})
    result = say_in_group(
        service,
        "I want to hug you right here.",
        characters=["alice"],
        switch=switch,
        timeout=1,
        arbiter_client=client,
    )
    assert result["turn"]["plan"]["arbiter"]["used"] is True
    assert "Off-stage social check" in switch.posts[0]
    assert "one quick hug" in switch.posts[0]
    assert any(
        event["kind"] == "social_arbiter"
        for event in service.state()["events"]
    )


def test_group_does_not_call_the_arbiter_for_small_talk(service, monkeypatch):
    monkeypatch.setenv("WORLD_ARBITER", "1")
    client = FakeArbiter({"stance": "answer", "tone": "warm"})
    switch = FakeSwitch({"alice": "I'm here."})
    say_in_group(
        service, "Alice, how was your day?", characters=["alice"],
        switch=switch, timeout=1, arbiter_client=client,
    )
    assert client.calls == []
    assert "Off-stage social check" not in switch.posts[0]


class DmClient:
    def __init__(self):
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append(kwargs)
        return {"reply": "Okay.", "memory": None, "relationships": []}

    def usage_summary(self):
        return {}


def test_dm_raises_only_a_contact_turn_to_high(tmp_path):
    service = WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)
    service.update_relationship("alice", "user", trust_delta=0.4, closeness_delta=0.4)
    client = DmClient()
    contact = reply_to_dm(service, "alice", "I want to hug you.", client=client)
    assert contact["reasoning"] == "high"
    assert client.calls[-1]["reasoning"] == "high"

    ordinary = reply_to_dm(service, "alice", "How was your day?", client=client)
    assert ordinary["reasoning"] == "low"
    assert client.calls[-1]["reasoning"] == "low"

