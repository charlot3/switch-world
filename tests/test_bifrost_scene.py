from __future__ import annotations

from switch_world.application.prompts import _system
from switch_world.application.beat_runners import run_cafe_bifrost
from switch_world.application.canon import load as load_canon
from switch_world import config
from switch_world.application.facade import WorldService


class FakeBifrost:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append((character, messages))
        return self.responses[character]

    def usage_summary(self):
        return {
            "date": "test",
            "characters": {
                "alice": {"used_tokens": 120, "model": "ollama/test"},
                "emily": {"used_tokens": 140, "model": "ollama/test"},
            },
            "requests": 2,
        }


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_bifrost_disclosure_writes_the_same_ledger(tmp_path):
    service = make_service(tmp_path)
    client = FakeBifrost({
        "alice": {
            "reply": "I shouldn't be telling you this, but our friend is leaving at the end of the month.",
            "memory": None,
            "relationships": [],
        },
        "emily": {
            "reply": "They told you before they told me? I don't know whether to be flattered or worried.",
            "memory": {
                "proposition": "The user is leaving the city at the end of the month.",
                "source": "character:alice",
                "confidence": 0.8,
                "visibility": "shared",
                "proposition_key": "user-leaving-city",
            },
            "relationships": [{
                "other": "alice",
                "trust_delta": -0.1,
                "closeness_delta": 0.02,
                "tension_delta": 0.05,
                "reason": "heard the news second-hand",
            }],
        },
    })

    result = run_cafe_bifrost(service, client=client)

    assert [call[0] for call in client.calls] == ["alice", "emily"]
    assert result["shared"] is True
    assert result["branch"]["id"] == "disclosure"
    assert result["canon_issues"] == []
    assert result["bifrost"]["requests"] == 2

    holders = {h["holder"]: h for h in service.who_knows("user-leaving-city")["holders"]}
    assert holders["alice"]["confidence"] == 1.0
    assert holders["emily"]["confidence"] == 0.8
    assert holders["emily"]["source"] == "character:alice"

    edge = service.relationship("emily", "alice")
    assert edge["trust"] < 0.85
    assert "Scene card" in result["card"]["text"]


def test_bifrost_suspicion_is_non_disclosure(tmp_path):
    service = make_service(tmp_path)
    client = FakeBifrost({
        "alice": {
            "reply": "I'm just tired. Tell me something good.",
            "memory": None,
            "relationships": [],
        },
        "emily": {
            "reply": "You're deflecting. I won't push tonight, but I noticed.",
            "memory": {
                "proposition": "Alice is holding something back.",
                "source": "observation",
                "confidence": 0.4,
                "visibility": "private",
                "proposition_key": "alice-holding-back",
            },
            "relationships": [],
        },
    })

    result = run_cafe_bifrost(service, client=client)

    assert result["shared"] is False
    assert result["branch"]["id"] == "non-disclosure"
    assert [h["holder"] for h in service.who_knows("user-leaving-city")["holders"]] == ["alice"]
    assert service.who_knows("alice-holding-back")["holders"][0]["holder"] == "emily"


def test_system_prompt_forbids_meta_room_lines():
    system = _system("alice", load_canon(), "")
    assert "@user" in system
    assert "offline" in system


def test_bifrost_meta_reply_is_not_recorded_as_dialogue(tmp_path):
    service = make_service(tmp_path)
    meta = "@user — I'm not online in this room, @director."
    envelope = {"reply": meta, "memory": None, "relationships": []}
    client = FakeBifrost({"alice": envelope, "emily": envelope})

    result = run_cafe_bifrost(service, client=client)

    assert result["alice"] is None
    assert result["emily"] is None
    dialogues = service.events(kind="dialogue")
    assert all(
        "@user" not in event["summary"] and "@director" not in event["summary"]
        for event in dialogues
    )
    assert "@user" not in result["card"]["text"]
    assert "@director" not in result["card"]["text"]
    assert service.events(kind="no_reply")
