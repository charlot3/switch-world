from __future__ import annotations

import pytest

from director.beats import BEAT_ORDER, run_arc, run_beat, run_local_beat
from world_engine import config
from world_engine.service import WorldService


def make_service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_morning_beat_is_a_small_demo(tmp_path):
    service = make_service(tmp_path)
    result = run_local_beat(service, "morning-shop")
    assert result["beat"]["id"] == "morning-shop"
    assert len(result["transcript"]) == 6
    assert [h["holder"] for h in service.who_knows("user-leaving-city")["holders"]] == ["alice"]
    assert service.relationship("alice", "user")["closeness"] > 0.35
    assert any(e["kind"] == "beat" and "morning-shop" in e["summary"] for e in service.state()["events"])


def test_truck_beat_leaves_a_private_suspicion(tmp_path):
    service = make_service(tmp_path)
    result = run_local_beat(service, "truck-lunch")
    assert result["beat"]["id"] == "truck-lunch"
    holders = service.who_knows("truck-debt")["holders"]
    assert {h["holder"] for h in holders} == {"mia", "sophia"}
    sophia = next(h for h in holders if h["holder"] == "sophia")
    assert sophia["confidence"] == 0.45
    assert service.relationship("mia", "sophia")["closeness"] > 0.45


def test_aftermath_requires_the_cafe_branch(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError):
        run_local_beat(service, "aftermath")


def test_aftermath_uses_the_ledger_branch(tmp_path):
    service = make_service(tmp_path)
    run_local_beat(service, "cafe", force_share=True)
    result = run_local_beat(service, "aftermath")
    assert result["branch"]["id"] == "disclosure"
    assert result["beat"]["id"] == "aftermath"
    assert "You: I should have told you myself." in result["transcript"]
    assert service.relationship("emily", "alice")["trust"] > 0.75


def test_roundup_exports_a_card(tmp_path):
    service = make_service(tmp_path)
    result = run_local_beat(service, "roundup")
    assert result["beat"]["id"] == "roundup"
    assert "Scene card" in result["card"]["text"]
    assert any(e["kind"] == "beat" and "roundup" in e["summary"] for e in service.state()["events"])


def test_arc_runs_all_five_beats(tmp_path):
    service = make_service(tmp_path)
    result = run_arc(service)
    assert [item["beat"]["id"] for item in result["beats"]] == list(BEAT_ORDER)
    assert result["branch"]["id"] in {"disclosure", "non-disclosure", "partial-leak"}
    beat_ids = {
        event["summary"].split(" — ")[0].replace("Beat: ", "")
        for event in service.state()["events"]
        if event["kind"] == "beat"
    }
    assert beat_ids == set(BEAT_ORDER)


class FakeBifrost:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append((character, messages))
        return self.responses[character]

    def usage_summary(self):
        return {"requests": len(self.calls)}


def test_bifrost_can_run_a_partial_beat(tmp_path):
    service = make_service(tmp_path)
    client = FakeBifrost({
        "alice": {
            "reply": "You're early. The kettle is still deciding.",
            "memory": None,
            "relationships": [],
        }
    })
    result = run_beat(service, "morning-shop", transport="bifrost", client=client)
    assert result["beat"]["id"] == "morning-shop"
    assert result["transport"] == "bifrost"
    assert [call[0] for call in client.calls] == ["alice"]
    assert "You're early" in result["transcript"][0]
    assert result["bifrost"]["requests"] == 1


def test_branch_and_arc_survive_more_than_50_events(tmp_path):
    service = make_service(tmp_path)
    run_local_beat(service, "cafe")
    assert "cafe" in service.completed_beats()
    for index in range(60):
        service.record_event(
            "alice", "dm", f"Alice: later message {index}", ["alice", "user"], "private"
        )
    assert "cafe" in service.completed_beats()
    assert service.latest_event("branch") is not None
    result = run_local_beat(service, "aftermath")
    assert result["beat"]["id"] == "aftermath"
