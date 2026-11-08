"""Differential harness: the one beat pipeline against the four old runners.

Each case seeds two fresh worlds identically, runs the old public runner and the
new ``switch_world.application.beats.run_beat`` with the same fake replies, and
requires the branch, the ledger effects, the recorded events and the scene card
to match once ids and the card's wall-clock stamp are normalised.

The cloud cases have no old runner by design: they prove a cloud beat runs on
the injected :class:`ModelClient` alone, with no ``wait_for`` and no room, and
finishes in seconds.
"""
from __future__ import annotations

import importlib
import re
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

from switch_world.domain import demo as director
from switch_world.adapters.clock.system import SystemClock
from switch_world.adapters.models.legacy import LegacyModelClient
from switch_world.adapters.models.scripted import ScriptedModelClient
from switch_world.adapters.transports.legacy import LegacySwitchTransport
from switch_world.application.beat_strategies import (
    BifrostBeatStrategy,
    CloudBeatStrategy,
    LocalBeatStrategy,
    SwitchBeatStrategy,
)
from switch_world.application.beats import load_spec, run_beat
from switch_world import config
from switch_world.application.facade import WorldService

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_DIR = REPO_ROOT / "tests" / "fixtures" / "legacy_beats"


def _load_legacy_beats():
    """Load the vendored pre-step runners as a private package.

    The four historical runners import each other relatively, so the fixture
    directory is executed as a private package with the shared application
    modules (canon, clock, social, ...) aliased under it. This is the same
    differential baseline pattern used by ``legacy_group.py``: the old side must
    not resolve to the wrappers under test.
    """
    if not (LEGACY_DIR / "beats.py").exists():
        pytest.skip(f"missing parity baseline: {LEGACY_DIR}")
    package_name = "_legacy_beats_parity"
    package = types.ModuleType(package_name)
    package.__package__ = package_name
    package.__path__ = []
    package.DEMO_KEY = director.DEMO_KEY
    package.DEMO_SECRET = director.DEMO_SECRET
    sys.modules[package_name] = package
    aliases = {
        "canon": "switch_world.application.canon",
        "clock": "switch_world.application.clock",
        "social": "switch_world.application.social",
        "switch_client": "switch_world.adapters.transports.switch_client",
        "tavily_beat": "switch_world.application.tavily_beat",
    }
    for name, target in aliases.items():
        sys.modules[f"{package_name}.{name}"] = importlib.import_module(target)
    for name in ("simulate", "beats", "bifrost_scene", "run_switch"):
        source = (LEGACY_DIR / f"{name}.py").read_text(encoding="utf-8")
        module = types.ModuleType(f"{package_name}.{name}")
        module.__package__ = package_name
        module.__file__ = str(LEGACY_DIR / f"{name}.py")
        sys.modules[module.__name__] = module
        setattr(package, name, module)
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    package.run_local_beat = package.beats.run_local_beat
    package.run_beat_bifrost = package.bifrost_scene.run_beat_bifrost
    package.run_beat_switch = package.run_switch.run_beat_switch
    return package


LEGACY = _load_legacy_beats()


SECRET_KEY = "user-leaving-city"

BIFROST_DISCLOSURE = {
    "alice": {
        "reply": (
            "I shouldn't be telling you this, but our friend is leaving at the "
            "end of the month."
        ),
        "memory": None,
        "relationships": [],
    },
    "emily": {
        "reply": (
            "They told you before they told me? I don't know whether to be "
            "flattered or worried."
        ),
        "memory": {
            "proposition": "The user is leaving the city at the end of the month.",
            "source": "character:alice",
            "confidence": 0.8,
            "visibility": "shared",
            "proposition_key": SECRET_KEY,
        },
        "relationships": [
            {
                "other": "alice",
                "trust_delta": -0.1,
                "closeness_delta": 0.02,
                "tension_delta": 0.05,
                "reason": "heard the news second-hand",
            }
        ],
    },
}

BIFROST_NON_DISCLOSURE = {
    "alice": {
        "reply": "I'm just tired. Tell me something good.",
        "memory": None,
        "relationships": [],
    },
    "emily": {
        "reply": "You're deflecting. I won't push tonight, but I noticed.",
        "memory": {
            "proposition": "Alice is holding something back.",
            "source": "observation",
            "confidence": 0.4,
            "visibility": "private",
            "proposition_key": "alice-holding-back",
        },
        "relationships": [],
    },
}

LATER_BEAT_REPLY = {
    "alice": {
        "reply": "You're early. The kettle is still deciding.",
        "memory": None,
        "relationships": [],
    }
}

SWITCH_CAFE_CASES = {
    "non-disclosure": (
        {
            "alice": "I've had a long week. Tell me something good.",
            "emily": "You're deflecting. I won't push tonight, but I noticed.",
        },
        {},
    ),
    "disclosure": (
        {
            "alice": "Our friend is leaving at the end of the month.",
            "emily": "They told you before they told me?",
        },
        {
            "emily": [
                {
                    "proposition": (
                        "The user is leaving the city at the end of the month."
                    ),
                    "source": "character:alice",
                    "confidence": 0.8,
                    "visibility": "shared",
                    "proposition_key": SECRET_KEY,
                }
            ]
        },
    ),
}


def _service(path) -> WorldService:
    path.mkdir(parents=True, exist_ok=True)
    return WorldService(db_path=path / "world.sqlite", state_dir=config.STATE_DIR)


def _normalise_events(service: WorldService) -> list[dict[str, Any]]:
    fields = ("kind", "summary", "participants", "visibility", "created_at", "metadata")
    return [
        {key: event.get(key) for key in fields}
        for event in service.events()
    ]


def _effects(service: WorldService) -> dict[str, Any]:
    state = service.state()
    beliefs = [
        {key: value for key, value in belief.items() if key != "id"}
        for belief in state["beliefs"]
    ]
    return {
        "beliefs": beliefs,
        "relationships": state["relationships"],
        "matrix": state["matrix"],
        "done_beats": state["done_beats"],
        "clock": state["clock"],
    }


def _card(result: dict) -> str:
    lines = [
        line
        for line in result["card"]["text"].splitlines()
        if not line.startswith("**Generated:**")
    ]
    return "\n".join(lines)


def _branch_id(result: dict) -> str | None:
    branch = result.get("branch")
    return None if branch is None else branch["id"]


def _assert_parity(
    old_service: WorldService,
    new_service: WorldService,
    old_result: dict,
    new_result: dict,
    *,
    transcript: bool = True,
) -> None:
    assert _branch_id(old_result) == _branch_id(new_result)
    assert _normalise_events(old_service) == _normalise_events(new_service)
    assert _effects(old_service) == _effects(new_service)
    assert _card(old_result) == _card(new_result)
    if transcript and "transcript" in old_result and "transcript" in new_result:
        assert old_result["transcript"] == new_result["transcript"]


class FakeBifrost:
    """The legacy ``chat_json`` client both the old and the wrapped new path use."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Any]] = []

    def chat_json(self, character, messages, **kwargs):
        self.calls.append((character, messages))
        return self.responses[character]

    def usage_summary(self) -> dict:
        return {"requests": len(self.calls)}


class ParitySwitch:
    """A Switch-shaped fake that answers both ``wait_for`` and ``history``.

    The old runner polls ``wait_for``; the new pipeline wraps this object in
    :class:`LegacySwitchTransport`, which polls ``history``. ``post`` appends the
    scripted body (and, optionally, simulates a character's own MCP writes), so
    both paths observe the same room.
    """

    def __init__(
        self,
        service: WorldService,
        bodies: dict[str, str],
        writes: dict[str, list[dict]] | None = None,
    ) -> None:
        self.service = service
        self.bodies = dict(bodies)
        self.writes = dict(writes or {})
        self.posts: list[str] = []
        self.events: list[dict] = []

    def find_room(self, name: str = "world") -> dict:
        return {"room_id": "room-world", "name": name}

    def post(self, room_id: str, content: str) -> dict:
        self.posts.append(content)
        match = re.match(r"@([A-Za-z0-9_]+)\s+(.*)", content, re.S)
        if not match:
            return {}
        character = match.group(1).lower()
        for write in self.writes.get(character, []):
            self.service.remember(character, **write)
        body = self.bodies.get(character)
        if body is not None:
            self.events.append(
                {
                    "event_id": f"evt-{len(self.events)}",
                    "sender_name": character,
                    "timestamp": int(time.time() * 1000) + len(self.events),
                    "body": body,
                }
            )
        return {}

    def wait_for(self, room_id, character, started, timeout=90.0):
        body = self.bodies.get(character)
        if body is None:
            return None
        return {
            "event_id": f"evt-{character}",
            "sender_name": character,
            "timestamp": started + 1,
            "body": body,
        }

    def history(self, room_id) -> list[dict]:
        return list(self.events)


# ---------------------------------------------------------------------------
# Local runner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("force_share", [True, False])
def test_local_cafe_parity(tmp_path, force_share):
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    old = LEGACY.run_local_beat(old_service, "cafe", force_share=force_share)
    new = run_beat(
        load_spec("cafe", transport="local", force_share=force_share),
        LocalBeatStrategy(),
        new_service,
        SystemClock(),
    )
    _assert_parity(old_service, new_service, old, new)


@pytest.mark.parametrize("force_share", [True, False])
def test_cafe_runner_parity(tmp_path, force_share):
    """The direct ``run_cafe`` public runner must keep its pre-step events.

    Unlike ``run_local_beat``, ``run_cafe`` never recorded the ``beat`` or
    ``canon_warning`` events itself; direct callers (``director --simulate`` and
    ``POST /api/dev/run-cafe``) observe the feed, so an extra lifecycle event is
    a visible regression.
    """
    from switch_world.application.simulate import run_cafe

    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    LEGACY.simulate.user_tells_alice(old_service)
    LEGACY.simulate.user_tells_alice(new_service)

    old = LEGACY.simulate.run_cafe(old_service, force_share=force_share)
    new = run_cafe(new_service, force_share=force_share)
    _assert_parity(old_service, new_service, old, new)


@pytest.mark.parametrize("beat_id", ["morning-shop", "truck-lunch", "roundup"])
def test_local_later_beat_parity(tmp_path, beat_id):
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    old = LEGACY.run_local_beat(old_service, beat_id)
    new = run_beat(
        load_spec(beat_id, transport="local"),
        LocalBeatStrategy(),
        new_service,
        SystemClock(),
    )
    _assert_parity(old_service, new_service, old, new)


def test_local_aftermath_parity(tmp_path):
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    LEGACY.run_local_beat(old_service, "cafe", force_share=True)
    run_beat(
        load_spec("cafe", transport="local", force_share=True),
        LocalBeatStrategy(),
        new_service,
        SystemClock(),
    )
    old = LEGACY.run_local_beat(old_service, "aftermath")
    new = run_beat(
        load_spec("aftermath", transport="local"),
        LocalBeatStrategy(),
        new_service,
        SystemClock(),
    )
    _assert_parity(old_service, new_service, old, new)


# ---------------------------------------------------------------------------
# Bifrost runner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "responses", [BIFROST_DISCLOSURE, BIFROST_NON_DISCLOSURE], ids=["disclosure", "non-disclosure"]
)
def test_bifrost_cafe_parity(tmp_path, responses):
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    old_client = FakeBifrost(responses)
    new_client = FakeBifrost(responses)

    old = LEGACY.run_beat_bifrost(old_service, "cafe", client=old_client)
    new = run_beat(
        load_spec("cafe", transport="bifrost"),
        BifrostBeatStrategy(LegacyModelClient(new_client)),
        new_service,
        SystemClock(),
    )

    assert [call[0] for call in old_client.calls] == [
        call[0] for call in new_client.calls
    ]
    assert [call[1] for call in old_client.calls] == [
        call[1] for call in new_client.calls
    ]
    _assert_parity(old_service, new_service, old, new)


def test_bifrost_later_beat_parity(tmp_path):
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")
    old_client = FakeBifrost(LATER_BEAT_REPLY)
    new_client = FakeBifrost(LATER_BEAT_REPLY)

    old = LEGACY.run_beat_bifrost(old_service, "morning-shop", client=old_client)
    new = run_beat(
        load_spec("morning-shop", transport="bifrost"),
        BifrostBeatStrategy(LegacyModelClient(new_client)),
        new_service,
        SystemClock(),
    )

    assert [call[1] for call in old_client.calls] == [
        call[1] for call in new_client.calls
    ]
    _assert_parity(old_service, new_service, old, new)


# ---------------------------------------------------------------------------
# Switch runner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(SWITCH_CAFE_CASES))
def test_switch_cafe_parity(tmp_path, case):
    bodies, writes = SWITCH_CAFE_CASES[case]
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")

    old = LEGACY.run_beat_switch(
        old_service,
        "cafe",
        switch=ParitySwitch(old_service, bodies, writes),
        timeout=2.0,
    )
    new = run_beat(
        load_spec("cafe", transport="switch", timeout=2.0),
        SwitchBeatStrategy(
            LegacySwitchTransport(ParitySwitch(new_service, bodies, writes)),
            timeout=2.0,
        ),
        new_service,
        SystemClock(),
    )
    _assert_parity(old_service, new_service, old, new)


def test_switch_later_beat_parity(tmp_path):
    bodies = {"alice": "Starting a session to handle this — one moment."}
    old_service = _service(tmp_path / "old")
    new_service = _service(tmp_path / "new")

    old = LEGACY.run_beat_switch(
        old_service,
        "morning-shop",
        switch=ParitySwitch(old_service, bodies),
        timeout=2.0,
    )
    new = run_beat(
        load_spec("morning-shop", transport="switch", timeout=2.0),
        SwitchBeatStrategy(
            LegacySwitchTransport(ParitySwitch(new_service, bodies)),
            timeout=2.0,
        ),
        new_service,
        SystemClock(),
    )
    _assert_parity(old_service, new_service, old, new)


# ---------------------------------------------------------------------------
# Cloud: no room and no wait_for, only the injected ModelClient
# ---------------------------------------------------------------------------


def test_cloud_cafe_completes_in_seconds(tmp_path):
    service = _service(tmp_path)
    model = ScriptedModelClient(
        {
            "alice": {
                "reply": "Our friend is leaving at the end of the month.",
                "memory": None,
                "relationships": [],
            },
            "emily": {
                "reply": "They told you first?",
                "memory": {
                    "proposition": (
                        "The user is leaving the city at the end of the month."
                    ),
                    "source": "character:alice",
                    "confidence": 0.8,
                    "visibility": "shared",
                    "proposition_key": SECRET_KEY,
                },
                "relationships": [],
            },
        }
    )

    started = time.monotonic()
    result = run_beat(
        load_spec("cafe", transport="cloud"),
        CloudBeatStrategy(model),
        service,
        SystemClock(),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0
    assert result["transport"] == "cloud"
    assert _branch_id(result) == "disclosure"
    assert [call.character for call in model.calls] == ["alice", "emily"]
    assert "Scene card" in result["card"]["text"]


def test_cloud_later_beat_completes_in_seconds(tmp_path):
    service = _service(tmp_path)
    model = ScriptedModelClient(
        {
            "alice": {
                "reply": "You're early. The kettle is still deciding.",
                "memory": None,
                "relationships": [],
            }
        }
    )

    started = time.monotonic()
    result = run_beat(
        load_spec("morning-shop", transport="cloud"),
        CloudBeatStrategy(model),
        service,
        SystemClock(),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0
    assert result["beat"]["id"] == "morning-shop"
    assert result["transcript"] == ["Alice: You're early. The kettle is still deciding."]
    assert "Scene card" in result["card"]["text"]
