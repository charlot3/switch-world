from __future__ import annotations

import pytest

from director.cloud_switch import CloudSwitch
from director.group import say_in_group
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def _transport(replies):
    calls = []

    def call(url, payload, headers):
        calls.append(payload)
        character = payload["messages"][0]["content"].split("You are ", 1)[1].split(",", 1)[0]
        text = replies.get(character.lower(), f"{character} answers.")
        return {"choices": [{"message": {"content": text}}]}

    return call, calls


def test_cloud_switch_answers_planned_speakers(service):
    transport, calls = _transport({"alice": "I'm here.", "emily": "Who else?"})
    switch = CloudSwitch(api_key="test", transport=transport)
    result = say_in_group(service, "Are we still on for tonight?", switch=switch)
    assert calls, "the cloud room must actually call the model"
    assert result["replies"], "at least one planned speaker should answer"
    assert all(reply["text"] for reply in result["replies"])
    assert result["room"]["room_id"] == "cloud-world"


def test_cloud_switch_empty_reply_becomes_silence(service):
    transport, _ = _transport({"mia": ""})
    switch = CloudSwitch(api_key="test", transport=transport)
    result = say_in_group(
        service,
        "Mia, how are the onions?",
        characters=["mia"],
        switch=switch,
        timeout=1.0,
    )
    assert result["replies"] == []
    assert result["missing"] == ["mia"]


def test_cloud_switch_requires_a_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("WORLD_CLOUD_API_KEY", raising=False)
    with pytest.raises(Exception):
        CloudSwitch(api_key="")


def test_cloud_bifrost_parses_json_envelope():
    from director.cloud_switch import CloudBifrost

    def transport(url, payload, headers):
        assert payload["response_format"] == {"type": "json_object"}
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"reply": "Onion soup.", "memory": null, "relationships": []}'
                    }
                }
            ],
            "usage": {"total_tokens": 12},
        }

    client = CloudBifrost(api_key="test", transport=transport)
    envelope = client.chat_json(
        "mia", [{"role": "user", "content": "what is cooking?"}]
    )
    assert envelope["reply"] == "Onion soup."
    assert client.usage_summary()["total_tokens"] == 12


def test_cloud_switch_drops_a_meta_only_reply(service):
    transport, _ = _transport(
        {"mia": "@user — I'm not online in this room, and @director needs me.."}
    )
    switch = CloudSwitch(api_key="test", transport=transport)
    result = say_in_group(
        service,
        "Mia, how are the onions?",
        characters=["mia"],
        switch=switch,
        timeout=1.0,
    )
    assert result["replies"] == []
    assert result["missing"] == ["mia"]


def test_two_cloud_turns_both_record_replies(service):
    transport, _ = _transport({"alice": "Still here."})
    switch = CloudSwitch(api_key="test", transport=transport)
    first = say_in_group(
        service, "Alice, are you around?", characters=["alice"], switch=switch
    )
    second = say_in_group(
        service, "Alice, still around?", characters=["alice"], switch=switch
    )
    assert [r["text"] for r in first["replies"]] == ["Still here."]
    assert [r["text"] for r in second["replies"]] == ["Still here."]
