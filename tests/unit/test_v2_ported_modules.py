"""The v2 ports behave like the modules they replace.

These tests import the ``switch_world`` modules directly. The v1 compatibility
shims are gone; the behaviour those modules encoded is pinned here.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from switch_world.application import (
    canon,
    clock,
    scenarios,
    social,
    studio,
    takes,
)
from switch_world.application import beat_runners, prompts
from switch_world.application.facade import WorldService
from switch_world.application.simulate import user_tells_alice
from switch_world.config import load_settings
from switch_world.domain.demo import DEMO_KEY


@pytest.fixture()
def settings():
    return load_settings({"WORLD_DATA_DIR": str(Path.cwd() / "data")})


@pytest.fixture()
def service(tmp_path):
    return WorldService(
        db_path=tmp_path / "world.sqlite",
        state_dir=load_settings({}).state_dir,
    )


# ---------------------------------------------------------------------------
# Scenarios and takes
# ---------------------------------------------------------------------------


def test_scenarios_module_lists_and_loads_the_authored_world(service, tmp_path):
    cards = scenarios.list_scenarios()
    assert [card["id"] for card in cards] == scenarios.SCENARIO_ORDER

    loaded = scenarios.load_scenario(service, "w3-quiet-route")
    assert loaded["cast"] == ["alice"]
    assert service.state()["scenario"]["id"] == "w3-quiet-route"
    assert service.state()["clock"]["now"] == "2026-11-03T19:10:00+09:00"

    with pytest.raises(ValueError):
        scenarios.get_scenario("../w1-gift")
    assert scenarios.get_scenario("w1-gift")["id"] == "w1-gift"


def test_scenarios_accepts_an_explicit_directory(tmp_path):
    source = scenarios.SCENARIO_DIR
    copy = tmp_path / "scenarios"
    copy.mkdir()
    (copy / "w1-gift.json").write_text(
        (source / "w1-gift.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert [card["id"] for card in scenarios.list_scenarios(scenario_dir=copy)] == [
        "w1-gift"
    ]


def test_takes_module_loads_a_scene_and_snapshots_it(service):
    assert "w3-quiet-route" in [card["id"] for card in takes.list_takes()]
    result = takes.load_take(service, "w3-quiet-route")
    assert result["take"]["id"] == "w3-quiet-route"
    assert result["index"] == 0
    snapshot = takes.take_snapshot(service)
    assert snapshot["take"]["id"] == "w3-quiet-route"
    assert snapshot["scene"]["index"] == 0
    with pytest.raises(takes.TakeError):
        takes.next_scene(service)


# ---------------------------------------------------------------------------
# Studio projection
# ---------------------------------------------------------------------------


def test_studio_summary_is_injectable_and_offline(service):
    summary = studio.studio_summary(service, prober=lambda url: True)
    assert summary["health"] == {
        "world": True,
        "switch": True,
        "mattermost": True,
        "gateway": True,
        "bifrost": True,
    }
    assert [agent["id"] for agent in summary["agents"]] == [
        "alice",
        "emily",
        "sophia",
        "mia",
    ]
    assert summary["clock"]["mode"] == "mock"
    assert summary["current_beat"]["id"] == "morning-shop"
    assert summary["rooms"][0]["name"] == "world"


# ---------------------------------------------------------------------------
# Social policy and canon
# ---------------------------------------------------------------------------


def test_social_policy_classification_and_appraisal(service):
    verdict = social.appraise(service, "alice", "Can I kiss you?")
    assert verdict["topic"] == "contact"
    assert verdict["action_mode"] == "attempt"
    assert verdict["stance"] in {"refuse", "deflect", "negotiate"}
    assert social.clean_scene_line("@user I am not online in this room.") == ""


def test_canon_branch_and_brief(service):
    user_tells_alice(service)
    branch = canon.branch_for(service, DEMO_KEY)
    assert branch["id"] == "non-disclosure"
    assert "leaving" in canon.brief("alice")
    assert canon.validate(service) == []


# ---------------------------------------------------------------------------
# Story clock
# ---------------------------------------------------------------------------


def test_story_clock_math(service):
    loaded = canon.load()
    now = datetime.fromisoformat("2026-11-03T10:00:00+09:00")
    assert clock.current_beat(loaded, now)["id"] == "morning-shop"
    upcoming, target = clock.next_beat(loaded, now)
    assert upcoming["id"] == "truck-lunch"
    assert target.hour == 12
    advanced = clock.advance_to_beat(service, loaded, "cafe")
    assert advanced["clock"]["now"].startswith("2026-11-03T18:30")


# ---------------------------------------------------------------------------
# Prompt envelope and writes
# ---------------------------------------------------------------------------


def test_prompt_envelope_parsing_and_application(service):
    envelope = prompts._parse_envelope(
        {
            "reply": "Okay.",
            "memory": {
                "proposition": "Alice likes tea.",
                "source": "user",
                "confidence": 0.8,
                "visibility": "private",
                "proposition_key": "alice-likes-tea",
            },
            "relationships": [
                {"other": "user", "trust_delta": 0.05, "reason": "tea"}
            ],
        },
        "alice",
    )
    assert envelope["reply"] == "Okay."
    writes = prompts._apply(service, "alice", envelope)
    assert writes["memory"]["proposition_key"] == "alice-likes-tea"
    assert writes["relationships"][0]["edge"]["a"] == "alice"
    assert "You are Alice" in prompts._system("alice", canon.load(), "")


# ---------------------------------------------------------------------------
# Beat runners and adapters
# ---------------------------------------------------------------------------


def test_application_beat_runner_runs_a_local_beat(service):
    result = beat_runners.run_local_beat(service, "morning-shop")
    assert result["beat"]["id"] == "morning-shop"
    assert result["transport"] == "local"
    assert len(result["transcript"]) == 6
    assert service.completed_beats() == ["morning-shop"]


def test_bifrost_compat_adapter_parses_and_cloud_room_imports():
    from switch_world.adapters.models import bifrost_compat
    from switch_world.adapters.models.cloud_bifrost import CloudBifrost
    from switch_world.adapters.transports.cloud_switch import CloudSwitch

    assert bifrost_compat.parse_json('```json\n{"reply": "hi"}\n```') == {
        "reply": "hi"
    }

    def transport(url, payload, headers):
        assert payload["response_format"] == {"type": "json_object"}
        return {
            "choices": [
                {"message": {"content": '{"reply": "Onion soup."}'}}
            ],
            "usage": {"total_tokens": 12},
        }

    client = CloudBifrost(api_key="test", transport=transport)
    assert client.chat_json(
        "mia", [{"role": "user", "content": "what is cooking?"}]
    )["reply"] == "Onion soup."
    assert client.usage_summary()["total_tokens"] == 12
    assert CloudSwitch is not None


def test_tavily_adapter_uses_the_offline_fixture():
    from switch_world.adapters.search.tavily import TavilyClient

    result = TavilyClient(api_key="", offline=True).search("anything")
    assert result["offline"] is True
    assert "Offline fixture" in result["results"][0]["title"]
