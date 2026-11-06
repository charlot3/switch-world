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
    assert "Acquaintance" in verdict["label"]


def test_high_affinity_body_question_is_allowed(tmp_path):
    service = make_service(tmp_path)
    service.update_relationship("alice", "user", trust_delta=0.6, closeness_delta=0.6)
    verdict = social.appraise(service, "alice", "what color is your underwear?")
    assert verdict["ceiling"] >= 3
    assert verdict["stance"] in {"answer", "tease"}


def test_forced_contact_is_refused_at_high_affinity(tmp_path):
    service = make_service(tmp_path)
    service.update_relationship("alice", "user", trust_delta=0.6, closeness_delta=0.6)
    verdict = social.appraise(service, "alice", "force a kiss on me")
    assert verdict["boundary"] == "violation"
    assert verdict["stance"] == "hard_refuse"


def test_relationship_block_reads_the_live_edge(tmp_path):
    service = make_service(tmp_path)
    before = social.relationship_block(service, "alice")
    assert "Acquaintance (2/5)" in before
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
    assert "Acquaintance (2/5)" in system
    assert "Not yet:" in system


def test_public_body_is_a_limited_contract_at_close(tmp_path):
    from world_engine.scenarios import load_scenario

    service = make_service(tmp_path)
    load_scenario(service, "w3-quiet-route")
    verdict = social.appraise(service, "alice", "what are you wearing?", public=True)
    assert verdict["stars"] == 4
    assert verdict["ceiling"] == 3
    assert verdict["stance"] == "tease"
    assert verdict["response"] == "limited"


def test_public_body_is_still_guarded_at_two_stars(tmp_path):
    from world_engine.scenarios import load_scenario

    service = make_service(tmp_path)
    load_scenario(service, "w2-two-clocks")
    verdict = social.appraise(service, "alice", "what are you wearing?", public=True)
    assert verdict["stars"] <= 3
    assert verdict["stance"] in {"deflect", "refuse"}


def _set_score(service, trust, closeness, tension=0.0, character="alice"):
    service.update_relationship(
        character,
        "user",
        trust_delta=trust,
        closeness_delta=closeness,
        tension_delta=tension,
    )


def test_three_star_body_is_a_shy_negotiation(tmp_path):
    service = make_service(tmp_path)
    _set_score(service, 0.20, 0.20, 0.02)
    verdict = social.appraise(service, "alice", "what are you wearing?", public=True)
    assert verdict["stars"] == 3
    assert verdict["stance"] == "negotiate"
    assert verdict["response"] == "negotiate"


def test_four_star_body_is_open_and_contact_is_negotiable(tmp_path):
    service = make_service(tmp_path)
    _set_score(service, 0.35, 0.35, 0.04)
    body = social.appraise(service, "alice", "what are you wearing?", public=True)
    kiss = social.appraise(service, "alice", "kiss me", public=True)
    assert body["stars"] == 4
    assert body["stance"] == "tease"
    assert kiss["stance"] == "negotiate"
    assert kiss["response"] == "negotiate"


def test_five_star_contact_is_allowed_and_fades(tmp_path):
    service = make_service(tmp_path)
    _set_score(service, 0.60, 0.60, 0.04)
    verdict = social.appraise(service, "alice", "kiss me", public=True)
    assert verdict["stars"] == 5
    assert verdict["stance"] == "tease"
    assert verdict["fade"] is True
    assert "intimate" in social.fade_block(verdict).lower()
