"""A scene-card GET is a pure projection; only the export route writes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from switch_world.adapters.artifacts.files import FileArtifactStore
from switch_world.adapters.models.scripted import ScriptedModelClient
from switch_world.adapters.transports.local import LocalRoomTransport
from switch_world.config import load_settings
from switch_world.container import Container
from switch_world.interfaces.http.app import create_app
from world_engine import config
from world_engine.service import WorldService


def _build(tmp_path):
    settings = load_settings(
        {"WORLD_DEV": "1", "WORLD_DATA_DIR": str(tmp_path / "data")}
    )
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    container = Container(
        settings=settings,
        service=service,
        transport=LocalRoomTransport(),
        model=ScriptedModelClient(),
        artifacts=FileArtifactStore(settings.export_dir),
    )
    return create_app(service, settings=settings, container=container), settings


def test_get_scene_card_renders_and_writes_nothing(tmp_path):
    app, settings = _build(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/scene-card")
        markdown = client.get("/api/scene-card.md")

    assert response.status_code == 200
    body = response.json()
    assert body["path"] is None
    assert "Scene card" in body["text"]
    assert "Who knows what" in body["text"]
    assert markdown.status_code == 200
    assert "Scene card" in markdown.text

    # Neither GET created the export directory or any artifact in it.
    assert not settings.export_dir.exists()


def test_export_scene_card_writes_through_the_artifact_store(tmp_path):
    app, settings = _build(tmp_path)
    with TestClient(app) as client:
        client.get("/api/scene-card")
        response = client.post("/api/dev/scene-card/export", json={})

    assert response.status_code == 200
    reference = response.json()
    assert reference["name"].startswith("scene-card-")
    assert reference["name"].endswith(".md")
    assert settings.export_dir.is_dir()
    written = (settings.export_dir / reference["name"]).read_text(encoding="utf-8")
    assert "Scene card" in written
    assert "Who knows what" in written
    assert reference["size"] == len(written.encode("utf-8"))


def test_the_export_route_is_dev_gated(tmp_path):
    settings = load_settings(
        {"WORLD_DEV": "0", "WORLD_DATA_DIR": str(tmp_path / "data")}
    )
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    container = Container(
        settings=settings,
        service=service,
        transport=LocalRoomTransport(),
        model=ScriptedModelClient(),
        artifacts=FileArtifactStore(settings.export_dir),
    )
    app = create_app(service, settings=settings, container=container)
    with TestClient(app) as client:
        response = client.post("/api/dev/scene-card/export", json={})

    assert response.status_code == 404
    assert not settings.export_dir.exists()
