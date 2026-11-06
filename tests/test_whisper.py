from __future__ import annotations

import re

import pytest

from director.whisper import whisper_to_character
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


class FakeBifrost:
    def __init__(self, replies=None):
        self.replies = dict(replies or {})
        self.calls: list[tuple[str, list[dict]]] = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append((character, messages))
        return {
            "reply": self.replies.get(character, "Okay."),
            "memory": None,
            "relationships": [],
        }

    def usage_summary(self):
        return {"requests": len(self.calls)}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def test_whisper_is_private_and_observers_never_get_the_words(service):
    message = "the lighthouse key is under the blue jar"
    client = FakeBifrost(
        {
            "alice": "Meet me after closing.",
            "emily": "She leans closer.",
            "sophia": "Sophia looks away.",
        }
    )
    result = whisper_to_character(service, "alice", message, client=client)

    assert result["transport"] == "staged"
    assert result["target"] == "alice"
    assert result["reply"] == "Meet me after closing."
    assert result["observers"] == ["emily", "sophia"]

    events = service.state()["events"]
    whispers = [event for event in events if event["kind"] == "whisper"]
    answers = [event for event in events if event["kind"] == "whisper_reply"]
    assert len(whispers) == 1 and whispers[0]["visibility"] == "private"
    assert "lighthouse key" in whispers[0]["summary"]
    assert whispers[0]["metadata"]["mode"] == "whisper"
    assert len(answers) == 1 and answers[0]["visibility"] == "private"
    assert "Meet me after closing." in answers[0]["summary"]
    assert answers[0]["metadata"]["mode"] == "whisper_reply"

    forbidden = _tokens(message)
    for character, messages in client.calls:
        content = messages[-1]["content"]
        if character == "alice":
            # The target is the only prompt that contains the words.
            assert "lighthouse key" in content
            continue
        prompt_tokens = _tokens(content)
        assert not (prompt_tokens & forbidden), (character, content)

    # Observer reactions are public reaction beats; no private line leaks into them.
    public = [event for event in events if event["kind"] == "dialogue"]
    assert public
    assert all(event["visibility"] == "public" for event in public)
    assert all(event["metadata"]["mode"] == "reaction" for event in public)
    assert all("lighthouse" not in event["summary"].lower() for event in public)

    # Whisper kinds are not DMs, so the phone history stays empty.
    assert service.phone_history("alice")["messages"] == []


def test_observer_reply_cannot_echo_the_private_words(service):
    message = "the lighthouse key is under the blue jar"
    client = FakeBifrost(
        {
            "alice": "Okay.",
            "emily": "Did she just say lighthouse key?",
            "sophia": "I heard nothing.",
        }
    )
    whisper_to_character(service, "alice", message, client=client)
    public = [
        event["summary"]
        for event in service.state()["events"]
        if event["kind"] == "dialogue"
    ]
    assert all("lighthouse" not in summary.lower() for summary in public)
    assert all("blue jar" not in summary.lower() for summary in public)


def test_whisper_refusal_is_replaced_and_private(service):
    client = FakeBifrost(
        {
            "alice": "Come here and kiss me.",
            "emily": "She glances over.",
            "sophia": "Sophia says nothing.",
        }
    )
    result = whisper_to_character(service, "alice", "kiss me", client=client)
    assert result["verdict"]["stance"] == "hard_refuse"
    assert "kiss" not in result["reply"].lower()
    answer = next(
        event for event in service.state()["events"] if event["kind"] == "whisper_reply"
    )
    assert "kiss" not in answer["summary"].lower()


def test_whisper_validates_target_and_message(service):
    service.mark_absent("alice", reason="left")
    with pytest.raises(ValueError):
        whisper_to_character(service, "nobody", "hello", client=FakeBifrost())
    with pytest.raises(ValueError):
        whisper_to_character(service, "alice", "hello", client=FakeBifrost())
    with pytest.raises(ValueError):
        whisper_to_character(service, "emily", "   ", client=FakeBifrost())


def test_whisper_respects_the_take_cast(service):
    from world_engine.takes import load_take

    load_take(service, "w3-quiet-route")
    client = FakeBifrost({"alice": "Ask me."})
    result = whisper_to_character(service, "alice", "Can I ask you something?", client=client)
    assert result["observers"] == []
    assert all(character == "alice" for character, _ in client.calls)

    with pytest.raises(ValueError, match="not in the scene"):
        whisper_to_character(service, "emily", "Are you there?", client=client)
