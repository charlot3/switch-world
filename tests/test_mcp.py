from __future__ import annotations

from types import SimpleNamespace

import pytest

from world_engine import config
from world_engine.mcp_server import create_mcp
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def _record_event(service):
    mcp = create_mcp(service)
    return mcp._tool_manager.get_tool("world__record_event").fn


def _ctx(token):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"})


def test_record_event_is_director_only(service):
    record = _record_event(service)
    before = service.events()

    for kind in ("dialogue", "beat", "branch"):
        with pytest.raises(ValueError, match="director-only"):
            record(
                kind=kind,
                summary="Alice: an unsanitised public line.",
                ctx=_ctx("dev-alice"),
                participants=["alice"],
                visibility="public",
            )

    assert service.events() == before


def test_director_can_still_record_an_event(service):
    record = _record_event(service)
    event = record(
        kind="dialogue",
        summary="Alice: the director wrote this.",
        ctx=_ctx("dev-director"),
        participants=["alice"],
        visibility="public",
    )
    assert event["kind"] == "dialogue"
    assert event["summary"] == "Alice: the director wrote this."
    assert service.events()[-1]["id"] == event["id"]
