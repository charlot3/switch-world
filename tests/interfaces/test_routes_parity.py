"""The v2 route split keeps every v1 path and method byte-identical."""
from __future__ import annotations

from fastapi.testclient import TestClient

from switch_world.interfaces.http.app import create_app
from world_engine import config
from world_engine.service import WorldService

# The 39 routes the v1 app defined, in (method, path) form.
OLD_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/state"),
    ("GET", "/api/canon"),
    ("GET", "/api/matrix"),
    ("GET", "/api/scenarios"),
    ("GET", "/api/scenarios/current"),
    ("POST", "/api/scenarios/{scenario_id}/load"),
    ("POST", "/api/endings/evaluate"),
    ("GET", "/api/takes"),
    ("GET", "/api/takes/current"),
    ("POST", "/api/takes/{take_id}/load"),
    ("POST", "/api/takes/next"),
    ("POST", "/api/takes/cue"),
    ("GET", "/api/clock"),
    ("POST", "/api/clock/mode"),
    ("POST", "/api/clock/advance"),
    ("GET", "/api/friends"),
    ("POST", "/api/friends/{character}"),
    ("POST", "/api/safety/pause"),
    ("POST", "/api/safety/resume"),
    ("GET", "/api/safety"),
    ("GET", "/api/who-knows/{key}"),
    ("GET", "/api/scene-card"),
    ("GET", "/api/scene-card.md"),
    ("POST", "/api/dev/tell-alice"),
    ("POST", "/api/dev/run-cafe"),
    ("GET", "/api/dm/{character}"),
    ("POST", "/api/dm"),
    ("POST", "/api/group/say"),
    ("POST", "/api/group/whisper"),
    ("GET", "/api/studio/summary"),
    ("POST", "/api/dev/run-beat"),
    ("POST", "/api/dev/run-arc"),
    ("POST", "/api/dev/tavily-event"),
    ("POST", "/api/dev/run-bifrost"),
    ("GET", "/api/switch-log"),
    ("GET", "/api/bifrost/usage"),
    ("POST", "/api/dev/reset"),
}

NEW_ROUTES = {("POST", "/api/dev/scene-card/export")}


def _app(tmp_path):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    return create_app(service)


def _documented_routes(app) -> set[tuple[str, str]]:
    """Every JSON route in the document plus the root file response."""
    document = app.openapi()
    routes = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method in operations
    }
    # ``/`` intentionally stays out of the schema (it serves index.html).
    routes.add(("GET", "/"))
    return routes


def test_all_39_old_paths_are_still_present(tmp_path):
    routes = _documented_routes(_app(tmp_path))
    assert OLD_ROUTES - routes == set()


def test_old_paths_keep_exactly_their_old_methods(tmp_path):
    document = _app(tmp_path).openapi()

    by_path: dict[str, set[str]] = {}
    for method, path in OLD_ROUTES:
        by_path.setdefault(path, set()).add(method.lower())

    for path, methods in by_path.items():
        if path == "/":
            # The root is a FileResponse and is not in the JSON document.
            continue
        assert set(document["paths"][path]) == methods, path


def test_the_only_new_route_is_the_scene_card_export(tmp_path):
    routes = _documented_routes(_app(tmp_path))
    assert routes - OLD_ROUTES == NEW_ROUTES


def test_the_old_routes_actually_answer(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/api/state").status_code == 200
        assert client.get("/api/scene-card").status_code == 200
