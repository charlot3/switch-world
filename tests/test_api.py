from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from world_engine import config
from world_engine.api import create_app
from world_engine.service import WorldService


@pytest.fixture()
def client(tmp_path):
    service = WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)
    app = create_app(service)
    with TestClient(app) as test_client:
        yield test_client


def test_state_and_dashboard(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert len(data["characters"]) == 4
    assert data["matrix"]

    index = client.get("/")
    assert index.status_code == 200
    assert "switch-world" in index.text

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True


def test_canon_is_exposed(client):
    response = client.get("/api/canon")
    assert response.status_code == 200
    canon = response.json()
    assert canon["act"] == "Act I — The Secret"
    assert any("bookshop" in fact for fact in canon["public_facts"])
    assert [beat["id"] for beat in canon["beats"]][2] == "cafe"
    assert {branch["id"] for branch in canon["branches"]} == {
        "disclosure", "non-disclosure", "partial-leak"
    }

    state = client.get("/api/state").json()
    assert state["canon"]["secret"]["key"] == "user-leaving-city"


def test_tell_alice_and_cafe(client):
    response = client.post("/api/dev/tell-alice", json={})
    assert response.status_code == 200
    assert response.json()["belief"]["proposition_key"] == "user-leaving-city"

    response = client.post("/api/dev/run-cafe", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["shared"] is True
    assert "scene card" not in result["card"]["text"].lower() or "Scene card" in result["card"]["text"]

    matrix = client.get("/api/matrix").json()["matrix"]
    row = next(r for r in matrix if r["key"] == "user-leaving-city")
    assert row["holders"]["alice"]["confidence"] == 1.0
    assert row["holders"]["emily"]["confidence"] == 0.8

    who = client.get("/api/who-knows/user-leaving-city").json()
    assert {h["holder"] for h in who["holders"]} == {"alice", "emily"}


def test_cafe_without_secret_is_400(client):
    response = client.post("/api/dev/run-cafe", json={})
    assert response.status_code == 400
    assert "Alice does not know" in response.json()["detail"]


def test_scene_card_download(client):
    client.post("/api/dev/tell-alice", json={})
    client.post("/api/dev/run-cafe", json={})
    response = client.get("/api/scene-card.md")
    assert response.status_code == 200
    assert "Scene card" in response.text
    assert "Who knows what" in response.text


def test_reset(client):
    client.post("/api/dev/tell-alice", json={})
    response = client.post("/api/dev/reset", json={})
    assert response.status_code == 200
    matrix = client.get("/api/matrix").json()["matrix"]
    row = next((r for r in matrix if r["key"] == "user-leaving-city"), None)
    assert row is None


def test_dev_tavily_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "director.tavily_beat.fetch_world_event",
        lambda service, query=None: {
            "query": query,
            "offline": False,
            "event": {"id": 1, "summary": "Real world: test"},
            "key": "world-test",
            "title": "test",
            "url": "https://example.com",
            "holders": ["alice", "emily", "sophia", "mia"],
            "results": [],
        },
    )
    response = client.post("/api/dev/tavily-event", json={"query": "agents"})
    assert response.status_code == 200
    assert response.json()["key"] == "world-test"


def test_dev_bifrost_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "director.bifrost_scene.run_cafe_bifrost",
        lambda service: {
            "branch": {"id": "disclosure", "label": "The Confession"},
            "bifrost": {"requests": 2},
        },
    )
    response = client.post("/api/dev/run-bifrost", json={})
    assert response.status_code == 200
    assert response.json()["branch"]["id"] == "disclosure"


def test_run_beat_and_arc_endpoints(client):
    beat = client.post(
        "/api/dev/run-beat",
        json={"beat": "morning-shop", "transport": "local"},
    )
    assert beat.status_code == 200
    assert beat.json()["beat"]["id"] == "morning-shop"

    arc = client.post("/api/dev/run-arc", json={})
    assert arc.status_code == 200
    assert [item["beat"]["id"] for item in arc.json()["beats"]] == [
        "morning-shop", "truck-lunch", "cafe", "aftermath", "roundup"
    ]


def test_phone_is_locked_until_friendship(client):
    locked = client.get("/api/dm/alice?limit=100")
    assert locked.status_code == 403
    assert "friend" in locked.json()["detail"].lower()

    added = client.post("/api/friends/alice")
    assert added.status_code == 200
    assert added.json()["friends"][0]["character"] == "alice"

    response = client.get("/api/dm/alice?limit=100")
    assert response.status_code == 200
    body = response.json()
    assert body["character"] == "alice"
    assert body["messages"] == []
    assert body["has_more"] is False

    state = client.get("/api/state").json()
    assert state["friends"] == ["alice"]


def test_clock_endpoints(client):
    view = client.get("/api/clock").json()
    assert view["mode"] == "mock"
    assert view["current_beat"]["id"] == "morning-shop"
    assert view["next_beat"]["id"] == "morning-shop"

    advanced = client.post("/api/clock/advance", json={})
    assert advanced.status_code == 200
    body = advanced.json()
    assert body["beat"]["id"] == "morning-shop"
    assert body["clock"]["now"].startswith("2026-11-03T09:10")

    played = client.post("/api/clock/advance", json={"run": True})
    assert played.status_code == 200
    assert played.json()["beat"]["id"] == "morning-shop"
    assert played.json()["played"]["beat"]["id"] == "morning-shop"

    following = client.post("/api/clock/advance", json={"run": True})
    assert following.json()["beat"]["id"] == "truck-lunch"
    assert following.json()["played"]["beat"]["id"] == "truck-lunch"

    for _ in range(5):
        arc = client.post("/api/clock/advance", json={"run": True})
        assert arc.status_code == 200
    complete = client.post("/api/clock/advance", json={"run": True})
    assert complete.status_code == 200
    assert complete.json()["arc_complete"] is True
    assert complete.json()["played"] is None

    realtime = client.post("/api/clock/mode", json={"mode": "realtime"})
    assert realtime.status_code == 200
    assert realtime.json()["clock"]["mode"] == "realtime"
    mocked = client.post("/api/clock/mode", json={"mode": "mock"})
    assert mocked.status_code == 200
    assert mocked.json()["clock"]["mode"] == "mock"
