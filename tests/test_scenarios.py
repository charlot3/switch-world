from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from world_engine import config
from world_engine.api import create_app
from world_engine.scenarios import (
    SCENARIO_ORDER,
    evaluate_ending,
    get_scenario,
    list_scenarios,
    load_scenario,
)
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


@pytest.fixture()
def client(tmp_path):
    service = WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)
    app = create_app(service)
    with TestClient(app) as test_client:
        yield test_client


def _edge(state: dict, a: str, b: str) -> dict:
    return next(
        edge for edge in state["relationships"]
        if edge["a"] == a and edge["b"] == b
    )


def _connection(state: dict, a: str, b: str) -> dict:
    return next(
        row for row in state["connections"]
        if {row["a"], row["b"]} == {a, b}
    )


def test_scenario_inventory_and_cards():
    cards = list_scenarios()
    assert [card["id"] for card in cards] == SCENARIO_ORDER
    assert len(cards) == 7
    for card in cards:
        assert set(card) == {"id", "title", "seed", "ending", "cast", "notes"}
        assert card["cast"]
        assert card["title"]

    good = next(card for card in cards if card["id"] == "w5-good")
    assert good["ending"]["id"] == "good-confession"
    assert good["ending"]["tone"] == "good"
    bad = next(card for card in cards if card["id"] == "w5-bad")
    assert bad["ending"]["id"] == "bad-leak"
    assert bad["ending"]["tone"] == "bad"
    assert next(card for card in cards if card["id"] == "w2-two-clocks")["ending"] is None

    w3 = get_scenario("w3-quiet-route")
    assert w3["cast"] == ["alice"]
    assert w3["outfits"]["alice"]["source_belief"] == "user-prefers-short-skirt"


def test_unknown_or_unsafe_scenario_raises(service):
    for scenario_id in ("nope", "../w1-gift", "w1-gift.json", ""):
        with pytest.raises(ValueError):
            get_scenario(scenario_id)
        with pytest.raises(ValueError):
            load_scenario(service, scenario_id)


def test_scenario_validation_rejects_bad_ids(tmp_path, monkeypatch):
    import json

    from world_engine import scenarios as scenario_module

    folder = tmp_path / "scenarios"
    folder.mkdir()
    good = get_scenario("w1-gift")

    bad_cast = dict(good, id="bad-cast", cast=["nobody"])
    (folder / "bad-cast.json").write_text(json.dumps(bad_cast), encoding="utf-8")

    bad_key = dict(good, id="bad-key")
    bad_key["beliefs"] = [
        {"holder": "alice", "proposition": "x", "key": "Not A Key",
         "source": "user", "confidence": 0.5, "visibility": "private"}
    ]
    (folder / "bad-key.json").write_text(json.dumps(bad_key), encoding="utf-8")

    monkeypatch.setattr(scenario_module, "SCENARIO_DIR", folder)
    with pytest.raises(ValueError):
        scenario_module.get_scenario("bad-cast")
    with pytest.raises(ValueError):
        scenario_module.get_scenario("bad-key")


def test_load_resets_the_world_and_seeds_w3(service):
    service.add_friend("emily")
    service.remember(
        "alice", "I am leaving.", "user", 1.0, "private", "user-leaving-city"
    )
    service.advance_time("director", 30)

    scenario = load_scenario(service, "w3-quiet-route")
    assert scenario["id"] == "w3-quiet-route"
    state = service.state()

    assert state["clock"]["now"] == "2026-11-03T19:10:00+09:00"
    assert state["clock"]["mode"] == "mock"
    assert state["clock"]["scale"] == 1.0
    assert state["friends"] == ["alice"]
    assert state["scenario"]["id"] == "w3-quiet-route"
    assert state["scenario"]["cast"] == ["alice"]
    assert state["scene_art"] == "/static/assets/scenes/beat-date-alice.jpg"
    assert state["cast_art"]["alice"].endswith("alice-date-skirt.jpg")

    # The reset removed the old friend and the old secret.
    assert not any(
        belief["proposition_key"] == "user-leaving-city"
        for belief in state["beliefs"]
    )
    belief = next(
        belief for belief in state["beliefs"]
        if belief["proposition_key"] == "user-prefers-short-skirt"
    )
    assert belief["holder"] == "alice"
    assert belief["source_kind"] == "user"
    assert belief["confidence"] == pytest.approx(0.9)
    assert belief["visibility"] == "private"

    edge = _edge(state, "alice", "user")
    assert (edge["trust"], edge["closeness"], edge["tension"]) == pytest.approx(
        (0.78, 0.72, 0.08)
    )
    assert any(event["kind"] == "scenario_load" for event in state["events"])


def test_loading_another_scenario_replaces_the_previous_seed(service):
    load_scenario(service, "w3-quiet-route")
    assert service.outfits()

    load_scenario(service, "w1-gift")
    state = service.state()
    assert state["scenario"]["id"] == "w1-gift"
    assert state["friends"] == []
    assert state["outfits"] == {}
    assert state["clock"]["now"] == "2026-11-03T18:20:00+09:00"
    assert state["scenario"]["cast"] == ["alice", "emily", "sophia", "mia"]

    items = state["items"]
    assert [item["id"] for item in items] == ["gift-book"]
    assert items[0]["holder"] == "user"
    assert state["item"]["id"] == "gift-book"
    gift = next(
        belief for belief in state["beliefs"]
        if belief["proposition_key"] == "gift-first-edition"
    )
    assert gift["holder"] == "alice"
    assert gift["confidence"] == pytest.approx(1.0)


def test_outfit_is_a_declared_memory_chain(service):
    load_scenario(service, "w3-quiet-route")
    state = service.state()
    outfit = state["outfits"]["alice"]
    assert outfit["outfit_id"] == "date-skirt"
    assert outfit["label"] == "the burgundy skirt"
    assert outfit["reason"] == "because you said you like short skirts"
    assert outfit["art"].endswith("alice-date-skirt.jpg")

    belief = next(
        belief for belief in state["beliefs"]
        if belief["id"] == outfit["source_belief_id"]
    )
    assert belief["proposition_key"] == "user-prefers-short-skirt"
    assert belief["holder"] == "alice"

    event = next(
        event for event in state["events"]
        if event["kind"] == "outfit_change"
    )
    assert event["metadata"]["source_belief_key"] == "user-prefers-short-skirt"
    assert event["metadata"]["outfit_id"] == "date-skirt"

    # A declared outfit can be re-applied; an undeclared one or unknown belief cannot.
    again = service.set_outfit("alice", "date-skirt", reason="for the window seat")
    assert again["reason"] == "for the window seat"
    with pytest.raises(ValueError):
        service.set_outfit("alice", "ballgown")
    with pytest.raises(ValueError):
        service.set_outfit("alice", "date-skirt", source_belief_id=999999)


def test_outfit_requires_a_scenario_declaration(service):
    with pytest.raises(ValueError):
        service.set_outfit("alice", "date-skirt")


def test_give_item_moves_the_chip_and_records_it(service):
    load_scenario(service, "w1-gift")
    given = service.give_item("gift-book", "alice")
    assert given["holder"] == "alice"
    assert given["owner"] == "user"
    state = service.state()
    assert state["item"]["holder"] == "alice"
    assert state["item"]["id"] == "gift-book"
    assert any(event["kind"] == "item_given" for event in state["events"])

    with pytest.raises(ValueError):
        service.give_item("mystery-box", "alice")


def test_connections_are_unordered_character_pairs(service):
    load_scenario(service, "w4-three-of-us")
    state = service.state()
    connections = state["connections"]
    assert len(connections) == 6
    pairs = {frozenset((row["a"], row["b"])) for row in connections}
    assert len(pairs) == 6
    assert all("user" not in pair for pair in pairs)
    for row in connections:
        assert set(row) == {
            "a", "b", "affinity", "tension", "label", "shared_secret_count"
        }
        assert row["label"] in {"close", "steady", "strained", "rival", "distant"}

    pair = _connection(state, "alice", "emily")
    assert pair["affinity"] == pytest.approx(0.3025)
    assert pair["tension"] == pytest.approx(0.46)
    assert pair["label"] == "strained"

    service.remember(
        "alice",
        "Emily told me she is thinking about leaving.",
        source="character:emily",
        confidence=0.7,
        visibility="private",
        proposition_key="emily-leaving",
    )
    pair = _connection(service.state(), "alice", "emily")
    assert pair["shared_secret_count"] == 1


def test_second_hand_belief_counts_as_a_shared_secret(service):
    load_scenario(service, "w5-good")
    state = service.state()
    assert _edge(state, "emily", "alice")["shared_secret_count"] == 1
    pair = _connection(state, "alice", "emily")
    assert pair["shared_secret_count"] == 1


def test_clock_scale_multiplies_realtime(service, monkeypatch):
    anchor = "2026-11-03T18:30:00+09:00"
    real = datetime.now(datetime.fromisoformat(anchor).tzinfo)
    monkeypatch.setattr(WorldService, "_real_now", classmethod(lambda cls: real))

    clock = service.set_clock_mode("realtime", now=anchor, scale=3.0)
    assert clock["scale"] == 3.0
    assert clock["mode"] == "realtime"

    monkeypatch.setattr(
        WorldService, "_real_now", classmethod(lambda cls: real + timedelta(minutes=10))
    )
    scaled = service.clock()
    assert scaled["now"].startswith("2026-11-03T19:00")
    assert scaled["scale"] == 3.0
    assert service.state()["clock"]["scale"] == 3.0

    # Advancing deliberately leaves realtime but keeps the chosen scale.
    moved = service.advance_time("director", 5)
    assert moved["mode"] == "mock"
    assert moved["scale"] == 3.0
    assert moved["now"].startswith("2026-11-03T19:05")


def test_clock_scale_rejects_bad_values(service):
    for bad in (0, -1, "fast", float("inf")):
        with pytest.raises(ValueError):
            service.set_clock_mode("mock", scale=bad)


def test_endings_are_cards_and_idempotent_per_scenario(service):
    load_scenario(service, "w5-good")
    first = evaluate_ending(service)
    assert first["recorded"] is True
    assert first["ending"]["id"] == "good-confession"
    assert first["ending"]["tone"] == "good"
    assert first["ending"]["label"] == "GOOD END — The Confession"
    assert first["evidence"] == [
        "Alice closeness >= 0.65",
        "Emily holds the secret from Alice",
        "no boundary",
    ]

    second = evaluate_ending(service)
    assert second["recorded"] is False
    assert second["event_id"] == first["event_id"]
    assert second["ending"] == first["ending"]
    endings = [event for event in service.state()["events"] if event["kind"] == "ending"]
    assert len(endings) == 1
    assert endings[0]["metadata"]["scenario_id"] == "w5-good"
    assert endings[0]["metadata"]["ending_id"] == "good-confession"

    # Same clock and cast, opposite ledger: the other scenario run records its own card.
    load_scenario(service, "w5-bad")
    bad = evaluate_ending(service)
    assert bad["recorded"] is True
    assert bad["ending"]["id"] == "bad-leak"
    assert bad["ending"]["tone"] == "bad"
    assert bad["evidence"] == [
        "Emily trust <= 0.25",
        "distorted belief from Sophia",
        "Alice tension >= 0.40",
    ]
    endings = [event for event in service.state()["events"] if event["kind"] == "ending"]
    assert len(endings) == 1


def test_w6_is_the_unchanged_tuesday_with_a_neutral_card(service):
    load_scenario(service, "w6-long-tuesday")
    state = service.state()
    assert state["clock"]["now"] == "2026-11-03T08:00:00+09:00"
    assert state["friends"] == []
    assert len(state["beliefs"]) == 16
    assert len(state["relationships"]) == 16
    assert state["scenario"]["ending"]["tone"] == "neutral"
    card = evaluate_ending(service)
    assert card["ending"]["id"] == "neutral-long-tuesday"


def test_api_scenario_endpoints(client):
    listing = client.get("/api/scenarios")
    assert listing.status_code == 200
    assert [card["id"] for card in listing.json()["scenarios"]] == SCENARIO_ORDER

    empty = client.get("/api/scenarios/current").json()
    assert empty["scenario"] is None

    loaded = client.post("/api/scenarios/w1-gift/load")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["scenario"]["id"] == "w1-gift"
    state = body["state"]
    for key in (
        "scenario", "outfits", "items", "item", "cast_art", "scene_art", "connections"
    ):
        assert key in state
    assert state["item"]["id"] == "gift-book"
    assert state["scene_art"].endswith("beat-first-meeting.jpg")

    current = client.get("/api/scenarios/current").json()
    assert current["scenario"]["id"] == "w1-gift"

    fetched = client.get("/api/state").json()
    assert fetched["scenario"]["id"] == "w1-gift"
    assert fetched["clock"]["scale"] == 1.0

    unknown = client.post("/api/scenarios/not-a-world/load")
    assert unknown.status_code == 400
    assert "unknown scenario" in unknown.json()["detail"]


def test_api_clock_mode_accepts_scale(client):
    response = client.post("/api/clock/mode", json={"mode": "mock", "scale": 60})
    assert response.status_code == 200
    assert response.json()["clock"]["scale"] == 60.0
    assert client.get("/api/state").json()["clock"]["scale"] == 60.0

    invalid = client.post("/api/clock/mode", json={"mode": "mock", "scale": 0})
    assert invalid.status_code == 400
    junk = client.post("/api/clock/mode", json={"mode": "mock", "scale": "fast"})
    assert junk.status_code == 400


def test_api_endings_evaluate_is_idempotent(client):
    client.post("/api/scenarios/w5-good/load")
    first = client.post("/api/endings/evaluate")
    assert first.status_code == 200
    body = first.json()
    assert body["recorded"] is True
    assert body["ending"]["id"] == "good-confession"
    assert body["evidence"]

    second = client.post("/api/endings/evaluate").json()
    assert second["recorded"] is False
    assert second["event_id"] == body["event_id"]

    # A scenario with no ending returns no card rather than inventing one.
    client.post("/api/scenarios/w2-two-clocks/load")
    none = client.post("/api/endings/evaluate").json()
    assert none == {"ending": None, "evidence": [], "recorded": False}


def test_api_scenario_load_is_dev_only(client, monkeypatch):
    monkeypatch.setattr(config, "DEV_MODE", False)
    response = client.post("/api/scenarios/w1-gift/load")
    assert response.status_code == 404

    # Reading the catalogue is harmless and stays available.
    assert client.get("/api/scenarios").status_code == 200
