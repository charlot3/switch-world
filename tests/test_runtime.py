"""Runtime upgrades: action mode, response spectrum, connection planner, idempotency,
revision, context budget, off-screen beats and the safety pause."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from director import context, social
from director.dm import reply_to_dm
from director.group import plan_turn, say_in_group
from world_engine import config
from world_engine.api import create_app
from world_engine.service import WorldService

PRESENT = ["alice", "emily", "sophia", "mia"]


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


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


@pytest.fixture()
def client(tmp_path, monkeypatch):
    service = WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)
    monkeypatch.setattr(
        "director.group.SwitchClient", lambda: FakeSwitch({"alice": "I'm here."})
    )
    app = create_app(service)
    with TestClient(app) as test_client:
        yield test_client, service


def _verdicts(service, message):
    return {
        character: social.appraise(service, character, message, public=True)
        for character in PRESENT
    }


# ---- action mode ----------------------------------------------------------


def test_classify_separates_result_attempt_continue_and_wait():
    assert social.classify("")["action_mode"] == "wait"
    assert social.classify("   ")["action_mode"] == "wait"
    assert social.classify("wait")["action_mode"] == "wait"
    assert social.classify("continue")["action_mode"] == "continue"
    assert social.classify("go on")["action_mode"] == "continue"

    assert social.classify(
        "I sit down by the window and open my notebook."
    )["action_mode"] == "result"
    assert social.classify("I order another coffee.")["action_mode"] == "result"
    assert social.classify("I hug my knees.")["action_mode"] == "result"


def test_attempts_affecting_an_npc_are_never_results():
    assert social.classify("I kiss you")["action_mode"] == "attempt"
    assert social.classify("I hold your hand")["action_mode"] == "attempt"
    assert social.classify("Hold my hand.")["action_mode"] == "attempt"
    assert social.classify("@alice, come here.")["action_mode"] == "attempt"
    assert social.classify("I give you the book")["action_mode"] == "attempt"


# ---- response spectrum ----------------------------------------------------


def test_response_spectrum_is_gated_by_the_topic_stance(service):
    refused = social.appraise(service, "alice", "what color is your underwear?")
    assert refused["response"] in social.RESPONSES
    assert refused["stance"] in {"deflect", "refuse"}
    assert refused["response"] == "refuse"

    forced = social.appraise(service, "alice", "kiss me")
    assert forced["stance"] == "hard_refuse"
    assert forced["response"] == "refuse"

    service.update_relationship(
        "alice", "user", trust_delta=0.6, closeness_delta=0.6
    )
    allowed = social.appraise(service, "alice", "how was your day?")
    assert allowed["response"] in {"sincere", "surface", "limited"}


def test_group_plan_and_prompt_carry_the_response_spectrum(service):
    switch = FakeSwitch({"alice": "Quiet, mostly."})
    result = say_in_group(
        service,
        "Alice, how was your day?",
        characters=["alice"],
        switch=switch,
        timeout=1,
    )
    plan = result["turn"]["plan"]
    assert plan["primary"] == "alice"
    assert plan["response"] in social.RESPONSES
    assert plan["action_mode"] == "result"
    assert "Response spectrum" in switch.posts[0]
    assert "Action mode" in switch.posts[0]


def test_attempt_prompt_says_it_is_never_automatic_success(service):
    switch = FakeSwitch({"alice": "I step back."})
    result = say_in_group(
        service,
        "@alice hold my hand",
        characters=["alice"],
        switch=switch,
        timeout=1,
    )
    assert result["turn"]["plan"]["action_mode"] == "attempt"
    prompt = switch.posts[0]
    assert "attempt" in prompt.lower()
    assert "never automatic success" in prompt.lower()


# ---- connection-based planner --------------------------------------------


def test_planner_primary_is_highest_affinity_and_chorus_is_capped(service):
    message = "Are we still on for tonight?"
    plan = plan_turn(message, PRESENT, _verdicts(service, message), service=service)
    assert plan["primary"] == "mia"  # strongest user affinity in the seed
    assert plan["chorus"] is True
    assert len(plan["chorus_speakers"]) == 3
    assert plan["silent"] == ["sophia"]


def test_planner_does_not_turn_a_body_result_into_a_chorus(service):
    message = "I sit down by the window."
    plan = plan_turn(message, PRESENT, _verdicts(service, message), service=service)
    assert plan["action_mode"] == "result"
    assert plan["chorus"] is False
    assert plan["primary"] == "mia"
    assert len(plan["reactors"]) == 1


def test_planner_named_addressee_wins(service):
    message = "Emily, how was your day?"
    plan = plan_turn(message, PRESENT, _verdicts(service, message), service=service)
    assert plan["primary"] == "emily"
    assert plan["chorus"] is False
    # Reactor is the strongest character->character tension toward Emily.
    assert plan["reactors"] == ["sophia"]


def test_planner_intimate_reactor_is_a_real_character_stake(service):
    message = "I feel lonely tonight."
    plan = plan_turn(message, PRESENT, _verdicts(service, message), service=service)
    assert plan["chorus"] is False
    assert plan["primary"] == "mia"  # tensions tie at zero, affinity breaks the tie
    assert len(plan["reactors"]) == 1
    reactor = plan["reactors"][0]
    assert service.relationship(reactor, plan["primary"])["tension"] > 0
    assert set(plan["silent"]) | set(plan["reactors"]) | {plan["primary"]} == set(PRESENT)


def test_only_planned_speakers_are_posted_to(service):
    switch = FakeSwitch({"alice": "I'm here.", "emily": "Same."})
    result = say_in_group(service, "Are we still on?", switch=switch, timeout=1)
    speakers = set(result["turn"]["plan"]["chorus_speakers"])
    posted = {post.split(" ", 1)[0].lstrip("@") for post in switch.posts}
    assert posted == speakers
    assert result["silent"] == ["sophia"]
    silences = [
        event for event in service.state()["events"] if event["kind"] == "silence"
    ]
    assert any(event["metadata"].get("role") == "silent" for event in silences)


# ---- idempotency and revision --------------------------------------------


def test_group_say_replays_the_same_request_id_without_a_second_turn(client):
    test_client, service = client
    payload = {
        "message": "Alice, are we still on?",
        "timeout": 1,
        "request_id": "req_group_0001",
    }
    first = test_client.post("/api/group/say", json=payload)
    assert first.status_code == 200
    turns = [
        event for event in service.state()["events"] if event["kind"] == "turn_plan"
    ]
    assert len(turns) == 1

    second = test_client.post("/api/group/say", json=payload)
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["turn"]["id"] == first.json()["turn"]["id"]
    turns = [
        event for event in service.state()["events"] if event["kind"] == "turn_plan"
    ]
    assert len(turns) == 1


def test_reusing_a_request_id_with_a_different_payload_is_a_conflict(client):
    test_client, _ = client
    payload = {
        "message": "Alice, are we still on?",
        "timeout": 1,
        "request_id": "req_group_0002",
    }
    assert test_client.post("/api/group/say", json=payload).status_code == 200
    conflict = test_client.post(
        "/api/group/say",
        json={**payload, "message": "Alice, something else entirely?"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "REQUEST_CONFLICT"


def test_stale_expected_revision_is_409(client):
    test_client, service = client
    current = service.revision()
    stale = test_client.post(
        "/api/group/say",
        json={
            "message": "Alice, are we still on?",
            "timeout": 1,
            "expected_revision": current - 1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "STALE_REVISION"
    assert stale.json()["detail"]["revision"] >= current

    fresh = test_client.post(
        "/api/group/say",
        json={
            "message": "Alice, are we still on?",
            "timeout": 1,
            "expected_revision": current,
        },
    )
    assert fresh.status_code == 200


def test_state_exposes_revision_and_turn(client):
    test_client, _ = client
    state = test_client.get("/api/state").json()
    assert isinstance(state["revision"], int) and state["revision"] > 0
    assert isinstance(state["turn"], int)
    assert state["paused"] is False


def test_take_next_accepts_request_id_and_stale_revision(client):
    test_client, service = client
    loaded = test_client.post("/api/takes/w2-two-clocks/load")
    assert loaded.status_code == 200

    stale = test_client.post(
        "/api/takes/next",
        json={"request_id": "req_take_next_01", "expected_revision": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] in {"STALE_REVISION", "NOTHING_CHANGED"}

    cue = test_client.post("/api/takes/cue", json={"line": "A table before six."})
    assert cue.status_code == 200
    current = service.revision()
    advanced = test_client.post(
        "/api/takes/next",
        json={"request_id": "req_take_next_02", "expected_revision": current},
    )
    assert advanced.status_code == 200
    replay = test_client.post(
        "/api/takes/next",
        json={"request_id": "req_take_next_02", "expected_revision": current},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True


# ---- context budget -------------------------------------------------------


def test_context_projection_keeps_social_and_trims_old_history_first():
    history = [f"old line {index} " + ("x" * 400) for index in range(40)]
    scene = [f"scene line {index} " + ("y" * 200) for index in range(10)]
    memories = [f"- memory {index}" for index in range(9)]
    projected = context.project_context(
        social_block="SOCIAL BLOCK — never trimmed",
        history_lines=history,
        scene_lines=scene,
        memories=memories,
        message='The user says: "hello"',
        budget=2500,
    )
    assert "SOCIAL BLOCK" in projected["text"]
    assert projected["size"] <= 2500
    assert projected["trimmed"]["history"] > 0
    assert len(projected["memory_text"].splitlines()) <= context.MEMORY_LIMIT
    assert history[-1] in projected["text"] or projected["trimmed"]["history"] > 0


def test_context_projection_clips_multibyte_text_safely():
    clipped = context.clip_bytes("秘密" * 100, 7)
    assert len(clipped.encode("utf-8")) <= 7
    clipped.encode("utf-8")  # decodes; no half codepoint


def test_dm_prompt_stays_inside_the_context_budget(tmp_path):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    for index in range(80):
        service.record_event(
            "user", "dm", f"You: old message {index} " + ("z" * 300),
            ["user", "alice"], "private",
        )
        service.record_event(
            "alice", "dm", f"Alice: old reply {index} " + ("z" * 300),
            ["alice", "user"], "private",
        )
    captured = {}

    class CapturingBifrost:
        def chat_json(self, character, messages, **kwargs):
            captured["messages"] = messages
            return {"reply": "Okay.", "memory": None, "relationships": []}

        def usage_summary(self):
            return {}

    reply_to_dm(service, "alice", "Still there?", client=CapturingBifrost())
    messages = captured["messages"]
    total = sum(len(message["content"].encode("utf-8")) for message in messages)
    assert total <= context.CONTEXT_BUDGET_BYTES
    # The latest exchange survives the trim; the oldest does not.
    user_prompt = messages[1]["content"]
    assert "old message 79" in user_prompt
    assert "old message 0 " not in user_prompt


def test_group_prompt_stays_inside_the_context_budget(service):
    for index in range(120):
        service.record_event(
            "alice", "dialogue", f"Alice: old scene {index} " + ("q" * 250),
            ["alice"], "public",
        )
    switch = FakeSwitch({"alice": "Still here."})
    say_in_group(
        service, "Alice, still there?", characters=["alice"], switch=switch, timeout=1
    )
    assert len(switch.posts[0].encode("utf-8")) <= context.CONTEXT_BUDGET_BYTES + 8


# ---- off-screen beat ------------------------------------------------------


def test_offscreen_advance_records_one_public_event_without_beliefs(client):
    test_client, service = client
    before = len(service.state()["beliefs"])
    response = test_client.post(
        "/api/clock/advance", json={"offscreen": True, "character": "alice"}
    )
    assert response.status_code == 200
    event = response.json()["offscreen"]
    assert event["kind"] == "offscreen"
    assert event["visibility"] == "public"
    assert event["participants"] == ["alice"]
    assert event["metadata"]["offscreen"] is True
    assert event["metadata"]["kind"] in {"promise", "rumor", "errand"}
    assert len(service.state()["beliefs"]) == before

    second = test_client.post("/api/clock/advance", json={"offscreen": True})
    assert second.status_code == 200
    assert second.json()["offscreen"]["metadata"]["kind"] in {
        "promise", "rumor", "errand",
    }


# ---- safety pause ---------------------------------------------------------


def test_pause_blocks_group_and_dm_writes_until_resumed(client):
    test_client, _ = client
    assert test_client.post("/api/friends/alice").status_code == 200

    paused = test_client.post("/api/safety/pause", json={"paused": True})
    assert paused.status_code == 200
    assert paused.json()["paused"] is True
    assert test_client.get("/api/state").json()["paused"] is True

    group = test_client.post("/api/group/say", json={"message": "Hello?"})
    assert group.status_code == 423
    assert "paused" in group.json()["detail"].lower()
    dm = test_client.post(
        "/api/dm", json={"character": "alice", "message": "hello"}
    )
    assert dm.status_code == 423

    resumed = test_client.post("/api/safety/pause", json={"paused": False})
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False
    assert test_client.get("/api/state").json()["paused"] is False

    # The write path works again after resume.
    after = test_client.post("/api/group/say", json={"message": "Hello?", "timeout": 1})
    assert after.status_code == 200


def test_pause_survives_a_new_service_instance(tmp_path):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    service.set_paused(True)
    reopened = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    assert reopened.paused() is True
    reopened.set_paused(False)
    assert reopened.paused() is False
