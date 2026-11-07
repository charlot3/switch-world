"""GET /api/state must use one SQLite connection, not one per subprojection.

The dashboard projection used to call ``service.state()`` (which opened several
connections for matrix/outfits/items/presence) and then ``clock_view()`` plus
``take_snapshot()`` on top. This test wraps ``sqlite3.connect`` around the request
and asserts the whole endpoint costs exactly one connection.
"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from world_engine import config
from world_engine.api import create_app
from world_engine.service import WorldService


def test_api_state_opens_exactly_one_connection(tmp_path, monkeypatch):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    app = create_app(service)

    with TestClient(app) as client:
        opened: list[object] = []
        real_connect = sqlite3.connect

        def counting_connect(*args, **kwargs):
            opened.append(args[0] if args else kwargs.get("database"))
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", counting_connect)
        response = client.get("/api/state")

    assert response.status_code == 200
    body = response.json()
    assert len(body["characters"]) == 4
    assert body["matrix"]
    assert opened == [str(service.db_path)]


def test_api_state_with_an_active_take_still_opens_one_connection(tmp_path, monkeypatch):
    service = WorldService(
        db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR
    )
    app = create_app(service)

    with TestClient(app) as client:
        loaded = client.post("/api/takes/w2-two-clocks/load")
        assert loaded.status_code == 200

        opened: list[object] = []
        real_connect = sqlite3.connect

        def counting_connect(*args, **kwargs):
            opened.append(args[0] if args else kwargs.get("database"))
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", counting_connect)
        response = client.get("/api/state")

    assert response.status_code == 200
    body = response.json()
    assert body["take"]["id"] == "w2-two-clocks"
    assert body["scene"]["id"] == "before-six"
    assert opened == [str(service.db_path)]
