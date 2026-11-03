from __future__ import annotations

import pytest

from director.simulate import run_cafe, user_tells_alice
from world_engine import config
from world_engine.service import WorldService


@pytest.fixture()
def service(tmp_path):
    return WorldService(db_path=tmp_path / "world.sqlite", state_dir=config.STATE_DIR)


def test_user_tells_alice(service):
    belief = user_tells_alice(service)
    assert belief["holder"] == "alice"
    assert belief["source_kind"] == "user"
    assert belief["visibility"] == "private"
    assert belief["proposition_key"] == "user-leaving-city"
    # idempotent for the same key + source
    again = user_tells_alice(service)
    assert again["holder"] == "alice"
    known = [h for h in service.who_knows("user-leaving-city")["holders"] if h["holder"] == "alice"]
    assert len(known) == 1


def test_cafe_beat(service):
    user_tells_alice(service)
    result = run_cafe(service)
    assert result["shared"] is True
    assert len(result["transcript"]) == 2

    holders = {h["holder"]: h for h in service.who_knows("user-leaving-city")["holders"]}
    assert holders["alice"]["confidence"] == 1.0
    assert holders["emily"]["confidence"] == 0.8
    assert holders["emily"]["source"] == "character:alice"

    edge = service.relationship("emily", "alice")
    assert edge["trust"] < 0.85
    assert edge["shared_secret_count"] == 1

    card = result["card"]
    assert "Scene card" in card["text"]
    assert "Alice told Emily" in card["text"]


def test_cafe_requires_secret(service):
    with pytest.raises(ValueError):
        run_cafe(service)


def test_cafe_non_disclosure(service):
    user_tells_alice(service)
    result = run_cafe(service, force_share=False)
    assert result["shared"] is False
    holders = [h["holder"] for h in service.who_knows("user-leaving-city")["holders"]]
    assert holders == ["alice"]
