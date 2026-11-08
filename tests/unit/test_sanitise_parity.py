"""One sanitiser, one metadata shape, for group, DM, whisper and beat paths.

The group turn, the DM and the whisper all record a model line through the same
``_sanitise_reply`` policy helper; the beat runner and every path's meta filter
go through the same ``clean_scene_line``. These tests feed one raw reply through
each path and require the same sanitised line, and require the turn metadata to
have one shape no matter which path recorded it.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from switch_world.application import beat_runners as bifrost_scene, social
from switch_world.adapters.transports.local import LocalRoomTransport
from switch_world.application import group_planning, scene
from switch_world.application.group_planning import _sanitise_reply
from switch_world.application.scene import dm, say_in_group, whisper
from switch_world.application.turns import _metadata as turns_metadata
from switch_world.domain.ports.model import ModelFormat, ModelReply
from switch_world import config
from switch_world.application.facade import WorldService

META_KEYS = {"turn_id", "mode", "role", "expression", "target", "chorus"}


class ScriptedModel:
    """A ModelClient that returns a per-character JSON envelope."""

    def __init__(self, replies: dict[str, str]) -> None:
        self.replies = dict(replies)
        self.calls: list[str] = []

    def generate(self, character, messages, *, format=ModelFormat.JSON, **kwargs):
        name = str(character)
        self.calls.append(name)
        reply = self.replies.get(name, "Okay.")
        return ModelReply(
            text=json.dumps({"reply": reply}),
            data={"reply": reply},
            model="test",
        )

    def usage_summary(self) -> dict[str, Any]:
        return {"requests": len(self.calls)}


class FakeBeatClient:
    """A legacy ``chat_json`` client for the authored beat runner."""

    def __init__(self, replies: dict[str, str]) -> None:
        self.replies = dict(replies)
        self.calls: list[str] = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append(character)
        return {
            "reply": self.replies.get(character, "Okay."),
            "memory": None,
            "relationships": [],
        }

    def usage_summary(self) -> dict[str, Any]:
        return {"requests": len(self.calls)}


def _service(tmp_path, name: str) -> WorldService:
    return WorldService(
        db_path=tmp_path / f"{name}.sqlite", state_dir=config.STATE_DIR
    )


def _fresh(service: WorldService) -> None:
    return None


def _limited(service: WorldService) -> None:
    """Four stars: contact is limited, never a flat refusal."""
    service.update_relationship(
        "alice", "user", trust_delta=0.4, closeness_delta=0.4
    )


# (case, setup, user message, raw model reply)
SCENARIOS = {
    "normal": (_fresh, "How was your day?", "Long, but the good kind."),
    "refusal": (_fresh, "what color is your underwear?", "Black. Why?"),
    "limited_refusal": (
        _limited,
        "I will hug you there",
        "I'm going to pretend you asked me about the weather.",
    ),
}
META_BODY = "@user — I'm not online in this room, @director."


@pytest.mark.parametrize("case", sorted(SCENARIOS))
def test_same_reply_sanitises_identically_through_dm_whisper_and_beat(
    case, tmp_path, monkeypatch
):
    setup, message, body = SCENARIOS[case]

    # The policy line all three turn paths must produce.
    verdict_service = _service(tmp_path, f"verdict-{case}")
    setup(verdict_service)
    verdict = social.appraise(verdict_service, "alice", message, public=False)
    expected = _sanitise_reply("alice", body, verdict, message)

    # Group: the shared helper imported by the turn recorder.
    group_service = _service(tmp_path, f"group-{case}")
    setup(group_service)
    group_verdict = social.appraise(group_service, "alice", message, public=False)
    assert _sanitise_reply("alice", body, group_verdict, message) == expected

    # DM.
    dm_service = _service(tmp_path, f"dm-{case}")
    setup(dm_service)
    dm_result = dm(
        dm_service, "alice", message, ScriptedModel({"alice": body})
    )
    assert dm_result["reply"] == expected

    # Whisper (staged).
    whisper_service = _service(tmp_path, f"whisper-{case}")
    setup(whisper_service)
    whisper_result = whisper(
        whisper_service,
        "alice",
        message,
        model=ScriptedModel(
            {
                "alice": body,
                "emily": "She glances over.",
                "sophia": "She looks away.",
            }
        ),
    )
    assert whisper_result["reply"] == expected

    # Beat: the real authored Bifrost runner, given the same user message as its
    # prompt, must take the same policy path instead of the test calling the
    # helper itself.
    beat_service = _service(tmp_path, f"beat-{case}")
    setup(beat_service)
    monkeypatch.setattr(
        bifrost_scene,
        "prompts_for",
        lambda beat, branch_id=None: {"alice": message},
    )
    beat_result = bifrost_scene.run_beat_bifrost(
        beat_service, "roundup", client=FakeBeatClient({"alice": body})
    )
    assert beat_result["turns"][0]["reply"] == expected


def test_meta_leak_is_dropped_by_every_paths_shared_filter(tmp_path):
    message = "are you there?"

    # The beat runner, the group recorder and the DM all clean through the same
    # function; the whisper observer path applies its meta half directly.
    assert social.clean_scene_line(META_BODY) == ""
    assert group_planning._strip_meta(META_BODY) == ""
    assert scene._strip_meta(META_BODY) == ""

    # A model that leaks only stage machinery cannot reach the private feed.
    service = _service(tmp_path, "meta-dm")
    result = dm(service, "alice", message, ScriptedModel({"alice": META_BODY}))
    assert result["reply"]
    assert "@user" not in result["reply"]
    assert "@director" not in result["reply"]
    assert result["reply"] == social.deflection(
        "alice", social.appraise(service, "alice", message, public=False), message
    )


def test_an_ellipsis_only_line_is_a_placeholder_on_every_path(tmp_path):
    """A lone ellipsis is "no line", not dialogue, whichever path records it."""
    assert social.clean_scene_line("…") == ""
    assert social.clean_scene_line("Hello.\n…") == "Hello."

    service = _service(tmp_path, "ellipsis-whisper")
    result = whisper(
        service,
        "alice",
        "how was your day?",
        model=ScriptedModel(
            {"alice": "…", "emily": "…", "sophia": "…"}
        ),
    )
    assert result["reply"]
    events = service.state()["events"]
    assert all("…" not in (event["summary"] or "") for event in events)


def test_metadata_shape_is_the_same_for_group_and_whisper(tmp_path):
    # One helper object, re-exported, not a copy per path.
    assert turns_metadata is group_planning._metadata
    assert scene._metadata is group_planning._metadata
    shape = group_planning._metadata(
        "t-example", "reaction", "reactor", "alarmed", "alice", False
    )
    assert set(shape) == META_KEYS

    # A real group turn and a real whisper both record through that shape.
    group_service = _service(tmp_path, "meta-group")
    transport = LocalRoomTransport(
        script={
            "alice": "Long, but the good kind.",
            "emily": "She glances over.",
        }
    )
    say_in_group(
        group_service,
        "Alice, how was your day?",
        characters=["alice", "emily"],
        transport=transport,
    )
    group_events = [
        event
        for event in group_service.state()["events"]
        if event["kind"] in {"dialogue", "silence", "action"}
    ]
    assert group_events
    assert all(set(event["metadata"]) == META_KEYS for event in group_events)

    whisper_service = _service(tmp_path, "meta-whisper")
    whisper(
        whisper_service,
        "alice",
        "how was your day?",
        model=ScriptedModel(
            {
                "alice": "Long, but the good kind.",
                "emily": "She glances over.",
                "sophia": "She looks away.",
            }
        ),
    )
    whisper_events = [
        event
        for event in whisper_service.state()["events"]
        if event["kind"]
        in {"whisper", "whisper_reply", "dialogue", "silence", "action"}
    ]
    assert whisper_events
    assert all(set(event["metadata"]) == META_KEYS for event in whisper_events)
