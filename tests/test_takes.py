from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from world_engine import config
from world_engine.api import create_app
from world_engine.service import WorldService
from world_engine.takes import (
    TAKE_ORDER,
    TakeNotChanged,
    apply_cues,
    current_take,
    get_take,
    list_takes,
    load_take,
    next_scene,
    scene_changed,
    validate_takes,
)


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


@pytest.fixture()
def client(tmp_path):
    service = WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)
    app = create_app(service)
    with TestClient(app) as test_client:
        yield test_client


def _belief(service: WorldService, holder: str, key: str) -> dict | None:
    for belief in service.state()["beliefs"]:
        if belief["holder"] == holder and belief["proposition_key"] == key:
            return belief
    return None


def test_take_inventory_matches_the_authored_order():
    cards = list_takes()
    assert [card["id"] for card in cards] == TAKE_ORDER
    assert len(cards) == 8
    for card in cards:
        assert set(card) == {"id", "title", "scenario", "scene_count", "ending"}
        assert card["title"]
        assert card["scene_count"] >= 1
        assert get_take(card["id"])["id"] == card["id"]

    good = next(card for card in cards if card["id"] == "w5-good")
    bad = next(card for card in cards if card["id"] == "w5-bad")
    assert good["ending"] == "good-confession"
    assert bad["ending"] == "bad-leak"
    assert validate_takes() == []


def test_load_take_resets_the_world_and_starts_scene_zero(service):
    loaded = load_take(service, "w3-quiet-route")

    assert loaded["take"]["id"] == "w3-quiet-route"
    assert loaded["index"] == 0
    assert loaded["scene"]["id"] == "quiet-close"
    assert loaded["scene"]["index"] == 0
    assert loaded["scene"]["opening"]
    assert loaded["scene"]["choices"]
    assert loaded["state"]["take"]["id"] == "w3-quiet-route"
    assert loaded["state"]["take_index"] == 0

    state = service.state()
    assert state["scenario"]["id"] == "w3-quiet-route"
    # solo scene: only Alice is present
    assert state["absent_characters"] == []
    assert any(event["kind"] == "take_load" for event in state["events"])

    current = current_take(service)
    assert current["index"] == 0
    assert current["scene"]["id"] == "quiet-close"


def test_last_call_is_a_four_heart_route_for_the_warmest_character(service):
    from director import social

    load_take(service, "w7-last-call")
    affinity = social.affinity(service, "mia")
    assert affinity["stars"] == 4
    assert service.state()["scenario"]["cast"] == ["mia"]
    assert current_take(service)["scene"]["id"] == "truck-dusk"


def test_next_scene_refuses_until_something_changes(service):
    load_take(service, "w1-gift")
    assert scene_changed(service) is False

    with pytest.raises(TakeNotChanged):
        next_scene(service)

    # A matching cue changes recorded state (the gift moves to Alice).
    result = apply_cues(service, user_line="I brought you something.")
    assert result["changed"] is True
    assert [row["op"] for row in result["applied"]] == [
        "give_item",
        "remember_preference",
    ]
    assert service.state()["item"]["holder"] == "alice"
    assert scene_changed(service) is True

    advanced = next_scene(service)
    assert advanced["index"] == 1
    assert advanced["scene"]["id"] == "cafe"
    assert scene_changed(service) is False


def test_force_advances_without_a_turn(service):
    load_take(service, "w2-two-clocks")
    with pytest.raises(TakeNotChanged):
        next_scene(service)
    advanced = next_scene(service, force=True)
    assert advanced["index"] == 1
    assert advanced["scene"]["id"] == "cafe"


def test_scene_cast_controls_presence_across_scenes(service):
    load_take(service, "w4-three-of-us")
    assert set(service.state()["absent_characters"]) == {"emily", "mia"}

    apply_cues(service, user_line="Are you and Emily okay?")
    next_scene(service)
    state = service.state()
    assert state["absent_characters"] == []


def test_cue_remember_preference_writes_a_belief(service):
    take = get_take("w3-quiet-route")
    load_take(service, "w3-quiet-route")

    assert _belief(service, "alice", "user-likes-quiet-walks") is None
    result = apply_cues(service, take, 0, user_line="I like the quiet route home.")
    ops = [row["op"] for row in result["applied"]]
    assert "remember_preference" in ops

    belief = _belief(service, "alice", "user-likes-quiet-walks")
    assert belief is not None
    assert belief["proposition"] == "The user likes the quiet route home."
    assert belief["source_kind"] == "user"

    # Re-applying the same cue is idempotent for the belief.
    again = apply_cues(service, take, 0, user_line="the quiet route home again")
    remembered = [
        row for row in again["applied"]
        if row["op"] == "remember_preference"
        and row.get("key") == "user-likes-quiet-walks"
    ]
    assert remembered and remembered[0]["skipped"] is True
    assert _belief(service, "alice", "user-likes-quiet-walks") is not None


def test_cue_set_outfit_uses_the_declared_scenario_outfit(service):
    take = get_take("w3-quiet-route")
    load_take(service, "w3-quiet-route")

    apply_cues(service, take, 0, user_line="That skirt is unfair.")
    advanced = next_scene(service)
    assert advanced["scene"]["id"] == "quiet-walk"
    outfit = service.state()["outfits"]["alice"]
    assert outfit["outfit_id"] == "date-skirt"
    assert outfit["source_belief_key"] == "user-prefers-short-skirt"
    events = [event for event in service.state()["events"] if event["kind"] == "outfit_change"]
    assert events


def test_ending_cue_records_the_authored_card_once(service):
    load_take(service, "w5-good")
    apply_cues(service, user_line="I'm staying.")
    next_scene(service)

    result = apply_cues(service, user_line="Alice, say it.")
    ending_rows = [row for row in result["applied"] if row["op"] == "ending"]
    assert ending_rows and ending_rows[0]["id"] == "good-confession"

    endings = [event for event in service.state()["events"] if event["kind"] == "ending"]
    assert len(endings) == 1
    assert endings[0]["metadata"]["ending_id"] == "good-confession"

    # A second application is idempotent: no second ending event.
    apply_cues(service, user_line="Alice, say it again.")
    endings = [event for event in service.state()["events"] if event["kind"] == "ending"]
    assert len(endings) == 1


def test_validation_reports_bad_takes_with_paths(tmp_path):
    good = json.loads(
        (config.ROOT / "world" / "takes" / "w3-quiet-route.json").read_text(
            encoding="utf-8"
        )
    )

    bad_cast = json.loads(json.dumps(good))
    bad_cast["id"] = "bad-cast"
    bad_cast["scenes"][0]["cast"] = ["nobody"]
    bad_cast["scenes"][1]["cast"] = ["nobody"]
    (tmp_path / "bad-cast.json").write_text(json.dumps(bad_cast), encoding="utf-8")

    bad_art = json.loads(json.dumps(good))
    bad_art["id"] = "bad-art"
    bad_art["scenes"][0]["art"] = "/static/assets/scenes/missing.jpg"
    (tmp_path / "bad-art.json").write_text(json.dumps(bad_art), encoding="utf-8")

    bad_next = json.loads(json.dumps(good))
    bad_next["id"] = "bad-next"
    bad_next["scenes"][0]["next"] = "nowhere"
    (tmp_path / "bad-next.json").write_text(json.dumps(bad_next), encoding="utf-8")

    bad_cue = json.loads(json.dumps(good))
    bad_cue["id"] = "bad-cue"
    bad_cue["scenes"][0]["cues"] = [{"op": "teleport"}]
    (tmp_path / "bad-cue.json").write_text(json.dumps(bad_cue), encoding="utf-8")

    errors = validate_takes(tmp_path)
    joined = "\n".join(errors)
    assert str(tmp_path / "bad-cast.json") in joined
    assert str(tmp_path / "bad-art.json") in joined
    assert str(tmp_path / "bad-next.json") in joined
    assert str(tmp_path / "bad-cue.json") in joined
    assert "unknown character" in joined
    assert "does not exist" in joined
    assert "next scene" in joined
    assert "op must be one of" in joined


def test_api_take_flow_and_state_projection(client):
    listing = client.get("/api/takes")
    assert listing.status_code == 200
    assert [card["id"] for card in listing.json()["takes"]] == TAKE_ORDER

    empty = client.get("/api/takes/current").json()
    assert empty["take"] is None
    assert empty["scene"] is None

    loaded = client.post("/api/takes/w2-two-clocks/load")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["take"]["id"] == "w2-two-clocks"
    assert body["scene"]["id"] == "before-six"
    assert body["state"]["take"]["id"] == "w2-two-clocks"

    current = client.get("/api/takes/current").json()
    assert current["index"] == 0
    assert current["scene"]["title"] == "Before six"

    refused = client.post("/api/takes/next", json={})
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "NOTHING_CHANGED"

    cue = client.post("/api/takes/cue", json={"line": "I wanted a table before the crowd."})
    assert cue.status_code == 200
    assert cue.json()["changed"] is True

    advanced = client.post("/api/takes/next", json={})
    assert advanced.status_code == 200
    assert advanced.json()["index"] == 1

    state = client.get("/api/state").json()
    assert state["take"]["id"] == "w2-two-clocks"
    assert state["take_index"] == 1
    assert state["scene"]["id"] == "cafe"
    assert state["scene"]["place"]
    assert state["scene"]["opening"]
    assert state["scene"]["choices"]
    # The clock/beat view still rides along for the existing Story stage.
    assert "current_beat" in state["scene"]


def test_group_say_applies_the_current_scene_cues(client, monkeypatch):
    class FakeSwitch:
        def find_room(self, name):
            return {"room_id": "room-world"}

        def post(self, room_id, content):
            return {}

        def history(self, room_id):
            return [
                {
                    "event_id": "evt-alice",
                    "sender_name": "alice",
                    "timestamp": 10 ** 15,
                    "body": "You brought me something?",
                }
            ]

    monkeypatch.setattr("director.group.SwitchClient", lambda: FakeSwitch())
    client.post("/api/takes/w1-gift/load")

    response = client.post(
        "/api/group/say",
        json={"message": "I brought you something.", "timeout": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cues"]["changed"] is True
    assert any(row["op"] == "give_item" for row in body["cues"]["applied"])
    assert client.get("/api/state").json()["item"]["holder"] == "alice"


def test_api_unknown_take_is_400(client):
    response = client.post("/api/takes/not-a-take/load")
    assert response.status_code == 400
    assert "unknown take" in response.json()["detail"]
