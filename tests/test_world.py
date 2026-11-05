from __future__ import annotations

import json

import pytest

from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_seed(service):
    state = service.state()
    assert len(state["characters"]) == 4
    assert len(state["beliefs"]) == 16
    assert len(state["relationships"]) == 16
    assert state["clock"]["now"] == config.WORLD_START


def test_token_mapping(service):
    assert service.actor_for_token("dev-alice") == "alice"
    assert service.actor_for_token("dev-director") == "director"
    with pytest.raises(PermissionError):
        service.actor_for_token("nope")
    assert service.actor_from_headers({"Authorization": "Bearer dev-emily"}) == "emily"
    with pytest.raises(PermissionError):
        service.actor_from_headers({})


def test_private_belief_is_scoped(service):
    service.remember(
        "alice",
        "The user is leaving the city.",
        source="user",
        confidence=1.0,
        visibility="private",
        proposition_key="user-leaving-city",
    )
    alice = service.recall("alice", "leaving city")
    emily = service.recall("emily", "leaving city")
    assert any(m["key"] == "user-leaving-city" for m in alice["memories"])
    assert not any(m["key"] == "user-leaving-city" for m in emily["memories"])


def test_second_hand_belief_and_shared_secret(service):
    service.remember(
        "alice",
        "I am leaving the city.",
        source="user",
        confidence=1.0,
        visibility="private",
        proposition_key="user-leaving-city",
    )
    service.remember(
        "emily",
        "Alice is leaving the city.",
        source="character:alice",
        confidence=0.8,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    emily = service.recall("emily", "leaving city")
    match = next(m for m in emily["memories"] if m["key"] == "user-leaving-city")
    assert match["source"] == "character:alice"
    assert match["confidence"] == 0.8

    who = service.who_knows("user-leaving-city")
    holders = {h["holder"]: h for h in who["holders"]}
    assert set(holders) == {"alice", "emily"}
    assert holders["alice"]["confidence"] == 1.0
    assert holders["emily"]["confidence"] == 0.8

    rel = service.relationship("emily", "alice")
    assert rel["shared_secret_count"] == 1


def test_relationship_update_clamps_and_records(service):
    result = service.update_relationship(
        "emily", "alice", trust_delta=-10, closeness_delta=10, tension_delta=-10,
        reason="test",
    )
    edge = result["edge"]
    assert edge["trust"] == 0.0
    assert edge["closeness"] == 1.0
    assert edge["tension"] == 0.0
    events = service.state()["events"]
    assert any(e["kind"] == "relationship_update" and "test" in e["summary"] for e in events)


def test_relationship_names_resolve_to_one_edge(service):
    before = service.relationship("alice", "emily")
    result = service.update_relationship(
        "alice", "Emily", trust_delta=0.01, reason="name, not id"
    )
    assert result["edge"]["b"] == "emily"
    after = service.relationship("alice", "emily")
    assert after["trust"] == pytest.approx(min(1.0, before["trust"] + 0.01))
    rows = [
        edge for edge in service.state()["relationships"]
        if edge["a"] == "alice" and str(edge["b"]).lower() == "emily"
    ]
    assert len(rows) == 1


def test_event_participants_normalize(service):
    event = service.record_event(
        "director", "note", "display-name participants", ["Alice", "user", "Emily"], "public"
    )
    assert event["participants"] == ["alice", "user", "emily"]


def test_matrix_groups_on_proposition_key(service):
    service.remember(
        "alice", "I am leaving.", "user", 1.0, "private", "user-leaving-city"
    )
    service.remember(
        "emily", "Alice is leaving.", "character:alice", 0.8, "shared", "user-leaving-city"
    )
    row = next(r for r in service.matrix() if r["key"] == "user-leaving-city")
    assert set(row["holders"]) == {"alice", "emily"}
    assert row["holders"]["alice"]["confidence"] == 1.0
    assert row["holders"]["emily"]["confidence"] == 0.8


def test_scene_card(service):
    service.remember(
        "alice", "I am leaving.", "user", 1.0, "private", "user-leaving-city"
    )
    card = service.scene_card("test scene")
    assert "Scene card" in card["text"]
    assert "The user is leaving the city" in card["text"]
    assert "Who knows what" in card["text"]
    with open(card["path"]) as fh:
        assert fh.read() == card["text"]


def test_director_only_clock(service):
    before = service.clock()["now"]
    after = service.advance_time("director", 30)["now"]
    assert after != before
    with pytest.raises(PermissionError):
        service.advance_time("alice", 30)


def test_record_event(service):
    event = service.record_event(
        "director", "scene_start", "A scene begins.", ["alice", "emily"], "public"
    )
    assert event["id"] > 0
    assert event["participants"] == ["alice", "emily"]
    assert json.dumps(event["participants"])
