"""Domain failures become the documented HTTP status codes exactly once."""
from __future__ import annotations

from fastapi.testclient import TestClient

from switch_world.adapters.artifacts.files import FileArtifactStore
from switch_world.config import load_settings
from switch_world.container import Container
from switch_world.interfaces.http.app import create_app
from switch_world import config
from switch_world.application.facade import WorldService


def _service(tmp_path):
    return WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )


def _client(tmp_path, **app_kwargs):
    settings = load_settings(
        {"WORLD_DEV": "1", "WORLD_DATA_DIR": str(tmp_path / "data")}
    )
    return create_app(_service(tmp_path), settings=settings, **app_kwargs)


def test_400_bad_request(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        response = client.post("/api/takes/cue", json={"choice": "not-an-int"})
    assert response.status_code == 400
    assert response.json() == {"detail": "choice must be an integer"}


def test_400_unknown_take(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        response = client.post("/api/takes/not-a-take/load")
    assert response.status_code == 400
    assert "unknown take" in response.json()["detail"]


def test_403_non_friend_phone(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        response = client.get("/api/dm/alice")
    assert response.status_code == 403
    assert "friend" in response.json()["detail"].lower()


def test_404_unknown_character(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        response = client.get("/api/dm/nobody")
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown character: nobody"


def test_404_dev_route_when_dev_is_off(tmp_path):
    settings = load_settings(
        {"WORLD_DEV": "0", "WORLD_DATA_DIR": str(tmp_path / "data")}
    )
    app = create_app(_service(tmp_path), settings=settings)
    with TestClient(app) as client:
        response = client.post("/api/dev/reset")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_409_take_has_not_changed(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        client.post("/api/takes/w2-two-clocks/load")
        response = client.post("/api/takes/next", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "NOTHING_CHANGED"


def test_409_stale_revision(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        response = client.post(
            "/api/takes/next", json={"expected_revision": 999999}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "STALE_REVISION"


def test_423_scene_is_paused(tmp_path):
    with TestClient(_client(tmp_path)) as client:
        client.post("/api/safety/pause", json={"paused": True})
        response = client.post(
            "/api/dm", json={"character": "alice", "message": "hello"}
        )
    assert response.status_code == 423
    assert "paused" in response.json()["detail"].lower()


def test_502_upstream_failure(tmp_path, monkeypatch):
    def explode(service, force_share=None):
        raise RuntimeError("bifrost went away")

    monkeypatch.setattr("switch_world.application.simulate.run_cafe", explode)
    with TestClient(_client(tmp_path)) as client:
        response = client.post("/api/dev/run-cafe", json={})
    assert response.status_code == 502
    assert "cafe failed" in response.json()["detail"]


def test_503_absent_transport_and_model(tmp_path):
    settings = load_settings({"WORLD_DATA_DIR": str(tmp_path / "data")})
    service = _service(tmp_path)
    container = Container(
        settings=settings,
        service=service,
        transport=None,
        model=None,
        artifacts=FileArtifactStore(tmp_path / "exports"),
    )
    app = create_app(service, settings=settings, container=container)
    with TestClient(app) as client:
        log = client.get("/api/switch-log")
        usage = client.get("/api/bifrost/usage")
        client.post("/api/friends/alice")
        dm = client.post("/api/dm", json={"character": "alice", "message": "hi"})
    assert log.status_code == 503
    assert "transport" in log.json()["detail"]
    assert usage.status_code == 503
    assert "model provider" in usage.json()["detail"]
    assert dm.status_code == 503
    assert "model provider" in dm.json()["detail"]
