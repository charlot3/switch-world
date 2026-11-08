from __future__ import annotations

import sqlite3

import pytest

from switch_world.application.canon import branch_for, brief, validate
from switch_world.application.simulate import run_cafe, user_tells_alice
from switch_world import config
from switch_world.application.facade import WorldService


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
    assert result["branch"]["id"] == "disclosure"
    assert result["canon_issues"] == []
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
    assert result["branch"]["id"] == "non-disclosure"
    assert result["canon_issues"] == []
    holders = [h["holder"] for h in service.who_knows("user-leaving-city")["holders"]]
    assert holders == ["alice"]


def test_suspicion_is_not_a_disclosure(service):
    """Emily's low-confidence 'Alice is hiding something' is not the secret."""
    user_tells_alice(service)
    service.remember(
        "emily",
        "Alice is holding something back.",
        source="character:alice",
        confidence=0.45,
        visibility="private",
        proposition_key="user-leaving-city",
    )
    branch = branch_for(service, "user-leaving-city")
    assert branch["id"] == "non-disclosure"


def test_direct_disclosure_and_third_party_leak(service):
    user_tells_alice(service)
    service.remember(
        "emily",
        "The user is leaving the city at the end of the month.",
        source="character:alice",
        confidence=0.8,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    assert branch_for(service, "user-leaving-city")["id"] == "disclosure"

    service.remember(
        "sophia",
        "The user is leaving the city at the end of the month.",
        source="character:emily",
        confidence=0.7,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    assert branch_for(service, "user-leaving-city")["id"] == "partial-leak"


def test_misattributed_secret_is_a_leak(service):
    """A confident belief that Alice is the one leaving is a distortion, not a disclosure."""
    user_tells_alice(service)
    service.remember(
        "emily",
        "Alice is leaving the city at the end of the month.",
        source="character:alice",
        confidence=0.8,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    assert branch_for(service, "user-leaving-city")["id"] == "partial-leak"


def test_branch_prefers_the_direct_belief_over_a_suspicion(service):
    user_tells_alice(service)
    service.remember(
        "emily",
        "Alice is holding something back.",
        source="character:alice",
        confidence=0.45,
        visibility="private",
        proposition_key="user-leaving-city",
    )
    service.remember(
        "emily",
        "The user is leaving the city at the end of the month.",
        source="character:alice",
        confidence=0.92,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    assert branch_for(service, "user-leaving-city")["id"] == "disclosure"


def test_direct_belief_below_confidence_floor_is_not_a_disclosure(service):
    user_tells_alice(service)
    service.remember(
        "emily",
        "The user is leaving the city at the end of the month.",
        source="character:alice",
        confidence=0.59,
        visibility="shared",
        proposition_key="user-leaving-city",
    )
    assert branch_for(service, "user-leaving-city")["id"] == "non-disclosure"


def test_brief_keeps_private_facts_per_actor():
    alice = brief("alice")
    emily = brief("emily")
    assert "lease" in alice
    assert "offered a job" in emily
    assert "offered a job" not in alice
    assert "The user is leaving" not in emily


def test_validate_flags_unknown_relationship_endpoint(service):
    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            """INSERT INTO relationships(a, b, trust, closeness, tension,
                                         shared_secret_count, last_interaction)
               VALUES (?,?,?,?,?,?,?)""",
            ("alice", "ghost", 0.5, 0.5, 0.0, 0, "2026-11-03T08:00:00+09:00"),
        )
    issues = validate(service)
    assert any("ghost" in issue for issue in issues)


def test_validate_accepts_legacy_display_name_participants(service):
    with sqlite3.connect(service.db_path) as conn:
        conn.execute(
            """INSERT INTO events(kind, summary, participants_json, visibility, created_at)
               VALUES (?,?,?,?,?)""",
            ("note", "legacy", '["Alice", "Emily", "user"]', "public",
             "2026-11-03T08:00:00+09:00"),
        )
    assert validate(service) == []
