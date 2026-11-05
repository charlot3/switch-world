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

    # The next turn sees the first exchange in its prompt, so context is not lost.
    reply_to_dm(service, "alice", "I'm still not sure.", client=client)
    second_prompt = client.calls[1][1][1]["content"]
    assert "I don't know how to tell them." in second_prompt
    assert "quiet" in second_prompt


def test_dm_validates_character_and_message(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError):
        reply_to_dm(service, "director", "hello", client=object())
    with pytest.raises(ValueError):
        reply_to_dm(service, "alice", "   ", client=object())


def test_user_turn_is_recorded_before_the_model_thinks(tmp_path):
    service = make_service(tmp_path)

    class InspectingBifrost:
        def chat_json(self, character, messages, **kwargs):
            events = [
                e for e in service.state()["events"]
                if e["kind"] == "dm" and "You: hello" in e["summary"]
            ]
            assert events, "the user's turn must exist while the model is still thinking"
            return {"reply": "Hi.", "memory": None, "relationships": []}

        def usage_summary(self):
            return {"requests": 1}

    result = reply_to_dm(service, "alice", "hello", client=InspectingBifrost())
    assert result["reply"] == "Hi."


def test_dm_prompt_has_language_and_voice_contract(tmp_path):
    service = make_service(tmp_path)
    captured = {}

    class CapturingBifrost:
        def chat_json(self, character, messages, **kwargs):
            captured["messages"] = messages
            return {"reply": "先吃饭。天塌了也得先吃饭。", "memory": None, "relationships": []}

        def usage_summary(self):
            return {}

    reply_to_dm(service, "mia", "你今天还好吗？", client=CapturingBifrost())
    system = captured["messages"][0]["content"]
    user = captured["messages"][1]["content"]
    assert "Language:" in system
    assert "中文口吻" in system
    assert "1-2 sentences" in user
    assert "natural spoken Chinese" in user


def test_dm_prompt_labels_the_users_group_line_as_you(tmp_path):
    service = make_service(tmp_path)
    service.record_event(
        "user", "dialogue", "You: are we still on for tonight?", ["user", "alice"], "public"
    )
    service.record_event("alice", "dialogue", "Alice: I'll be there.", ["alice"], "public")
    captured = {}

    class CapturingBifrost:
        def chat_json(self, character, messages, **kwargs):
            captured["messages"] = messages
            return {"reply": "Of course.", "memory": None, "relationships": []}

        def usage_summary(self):
            return {}

    reply_to_dm(service, "alice", "Good.", client=CapturingBifrost())
    user_prompt = captured["messages"][1]["content"]
    assert "You: are we still on for tonight?" in user_prompt
    assert "Alice: are we still on for tonight?" not in user_prompt
