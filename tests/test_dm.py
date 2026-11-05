from __future__ import annotations

import pytest

from director.dm import reply_to_dm
from world_engine import config
from world_engine.service import WorldService


class FakeBifrost:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append((character, messages))
        return self.response

    def usage_summary(self):
        return {"requests": len(self.calls)}


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_dm_records_a_private_exchange_and_provenance(tmp_path):
    service = make_service(tmp_path)
    client = FakeBifrost({
        "reply": "You're allowed to be quiet with me, you know.",
        "memory": {
            "proposition": "The user is worried about telling the group.",
            "source": "observation",
            "confidence": 0.55,
            "visibility": "private",
            "proposition_key": "user-worried-about-group",
        },
        "relationships": [{
            "other": "user",
            "closeness_delta": 0.03,
            "reason": "trusted me with the quiet part",
        }],
    })
    result = reply_to_dm(service, "alice", "I don't know how to tell them.", client=client)
    assert result["character"] == "alice"
    assert "quiet" in result["reply"]
    assert client.calls[0][0] == "alice"

    events = [e for e in service.state()["events"] if e["kind"] == "dm"]
    assert len(events) == 2
    assert all(e["visibility"] == "private" for e in events)
    assert "You: I don't know" in events[0]["summary"]
    assert "Alice:" in events[1]["summary"]
    assert service.relationship("alice", "user")["closeness"] > 0.35
    assert any(
        h["holder"] == "alice"
        for h in service.who_knows("user-worried-about-group")["holders"]
    )


def test_dm_validates_character_and_message(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError):
        reply_to_dm(service, "director", "hello", client=object())
    with pytest.raises(ValueError):
        reply_to_dm(service, "alice", "   ", client=object())
