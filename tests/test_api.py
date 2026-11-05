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
