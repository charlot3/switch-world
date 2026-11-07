"""The MCP edge and the store agree on who may write what.

The token is the only identity a character controls: the server maps it to an
actor and every mutating tool passes that actor down.  These tests exercise the
edge (the tool) and the store (the last line of defence) separately, so a future
caller cannot reintroduce the old give_item/record_event bypass.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from switch_world.interfaces.mcp.server import create_mcp
from world_engine import config
from world_engine.scenarios import load_scenario
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def _tool(service, name):
    return create_mcp(service)._tool_manager.get_tool(name).fn


def _ctx(token: str):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"})


# ---- give_item -------------------------------------------------------------


def test_non_holder_token_cannot_give_an_item(service):
    load_scenario(service, "w1-gift")
    assert service.item("gift-book")["holder"] == "user"

    give = _tool(service, "world__give_item")
    before = service.item("gift-book")
    with pytest.raises(PermissionError):
        give(ctx=_ctx("dev-alice"), item_id="gift-book", to="emily")
    assert service.item("gift-book") == before


def test_the_holder_can_give_an_item(service):
    load_scenario(service, "w1-gift")
    # The human (a trusted in-process caller) hands the book to Alice first.
    service.give_item("gift-book", "alice")

    give = _tool(service, "world__give_item")
    given = give(ctx=_ctx("dev-alice"), item_id="gift-book", to="emily", note="for you")
    assert given["holder"] == "emily"


def test_the_director_can_hand_over_any_item(service):
    load_scenario(service, "w1-gift")
    give = _tool(service, "world__give_item")
    given = give(ctx=_ctx("dev-director"), item_id="gift-book", to="emily")
    assert given["holder"] == "emily"


def test_give_item_without_an_actor_keeps_the_trusted_internal_path(service):
    load_scenario(service, "w1-gift")
    given = service.give_item("gift-book", "alice")
    assert given["holder"] == "alice"


# ---- record_event ----------------------------------------------------------


def test_character_token_cannot_write_a_public_turn_event(service):
    record = _tool(service, "world__record_event")
    before = service.events()
    with pytest.raises(ValueError, match="director-only"):
        record(
            ctx=_ctx("dev-alice"),
            kind="turn_plan",
            summary="Alice: a forged plan.",
            participants=["alice"],
            visibility="public",
        )
    assert service.events() == before


def test_store_rejects_a_character_public_turn_event_without_the_tool(service):
    before = service.events()
    with pytest.raises(PermissionError):
        service.record_event("alice", "turn_plan", "forged", ["alice"], "public")
    assert service.events() == before


def test_director_can_still_record_a_public_turn_event(service):
    event = service.record_event("director", "turn_plan", "The plan.", [], "public")
    assert event["kind"] == "turn_plan"
    assert service.events()[-1]["id"] == event["id"]


def test_characters_can_still_write_their_own_lines(service):
    dialogue = service.record_event(
        "alice", "dialogue", "Alice: hello.", ["alice"], "public"
    )
    dm = service.record_event(
        "alice", "dm", "Alice: psst.", ["alice", "user"], "private"
    )
    assert dialogue["kind"] == "dialogue"
    assert dm["kind"] == "dm"


def test_visibility_and_participants_are_still_canonicalised(service):
    event = service.record_event(
        "director", "note", "display names", ["Alice", "user", "Emily"], "public"
    )
    assert event["participants"] == ["alice", "user", "emily"]
