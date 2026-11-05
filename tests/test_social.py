from __future__ import annotations

import pytest

from director import social
from director.dm import reply_to_dm
from world_engine import config
from world_engine.service import WorldService


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


class FakeBifrost:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append(messages)
        return {"reply": self.reply, "memory": None, "relationships": []}

    def usage_summary(self):
        return {}


def test_low_affinity_body_question_is_not_answered(tmp_path):
    service = make_service(tmp_path)
    verdict = social.appraise(service, "alice", "what color is your underwear?")
    assert verdict["tier"] == 3
    assert verdict["ceiling"] == 1
    assert verdict["stance"] in {"deflect", "refuse"}
    assert "Cordial" in verdict["label"]


def test_high_affinity_body_question_is_allowed(tmp_path):
    service = make_service(tmp_path)
    service.update_relationship("alice", "user", trust_delta=0.6, closeness_delta=0.6)
    verdict = social.appraise(service, "alice", "what color is your underwear?")
    assert verdict["ceiling"] >= 3
    assert verdict["stance"] in {"answer", "tease"}


def test_forced_contact_is_refused_at_high_affinity(tmp_path):
    service = make_service(tmp_path)
    service.update_relationship("alice", "user", trust_delta=0.6, closeness_delta=0.6)
    verdict = social.appraise(service, "alice", "kiss me")
    assert verdict["boundary"] == "violation"
    assert verdict["stance"] == "hard_refuse"


def test_relationship_block_reads_the_live_edge(tmp_path):
    service = make_service(tmp_path)
    before = social.relationship_block(service, "alice")
    assert "Cordial (2/5)" in before
    service.update_relationship("alice", "user", trust_delta=0.2, closeness_delta=0.2)
    after = social.relationship_block(service, "alice")
    assert before != after
    assert "trust" in after


def test_dm_replaces_a_leaking_refusal(tmp_path):
    service = make_service(tmp_path)
    before = service.relationship("alice", "user")["tension"]
    client = FakeBifrost("Black. Why?")
    result = reply_to_dm(service, "alice", "what color is your underwear?", client=client)
    assert "Black" not in result["reply"]
    assert "underwear" not in result["reply"].lower()
    assert result["social"]["stance"] in {"deflect", "refuse"}
    assert service.relationship("alice", "user")["tension"] > before
    assert any(event["kind"] == "social_verdict" for event in service.state()["events"])


def test_dm_keeps_a_direct_answer_when_the_tier_allows_it(tmp_path):
    service = make_service(tmp_path)
    service.update_relationship("alice", "user", trust_delta=0.6, closeness_delta=0.6)
    result = reply_to_dm(service, "alice", "what color is your underwear?", client=FakeBifrost("Black."))
    assert result["social"]["stance"] in {"answer", "tease"}
    assert result["reply"] == "Black."


def test_dm_prompt_carries_the_relationship_contract(tmp_path):
    service = make_service(tmp_path)
    client = FakeBifrost("Okay.")
    reply_to_dm(service, "alice", "how was work?", client=client)
    system = client.calls[0][0]["content"]
    assert "Your relationship with the user right now" in system
    assert "Cordial (2/5)" in system
    assert "Not yet:" in system
